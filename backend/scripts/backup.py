r"""Meloyu 数据备份脚本（v0.15.0 增 PostgreSQL 通道）。

功能：
1a. PostgreSQL 备份（DATABASE_URL 已配置时的主通道）：逐表 COPY ... TO STDOUT
    （text 格式，NULL 转义无歧义）→ gzip → backups/pg-meloyu-YYYYMMDD-HHMMSS/
    目录（manifest.json 记录表清单/行数/顺序 + 每表 NNN-表名.copy.gz）。
    纯 Python 实现，不依赖 pg_dump 二进制与 docker exec——GPU 容器在 Docker
    Desktop/Win11 下 exec 受 seccomp errno 524 限制（见 services/ops_backup.py），
    且远端托管 PG（Supabase）同样可用。服务运行中执行安全（MVCC 快照）。
    恢复用配套脚本 scripts/restore_pg.py。
1b. SQLite 在线备份（无 DATABASE_URL 的开发回退）：backend/data/meloyu.db
    （WAL 模式）→ backend/data/backups/meloyu-YYYYMMDD-HHMMSS.db，
    sqlite3Connection.backup() 页级 API，服务运行中执行安全。
2. 快照完整性校验：SQLite 快照执行 PRAGMA integrity_check；PG 转储逐表
    回读行数与 manifest 比对（gzip CRC 保证传输完整）。校验失败即删除并
    报错（防"备了个坏的"——，2026-09-26）。
3. 音频产物增量复制：backend/data/audio/ → backend/data/backups/audio/。
   仅复制 size 或 mtime 与备份侧不一致的文件（os.walk 递归，保持相对目录结构）。
4. 轮换：db 产物（.db 快照或 pg-* 目录）保留最近 N 份（默认 7，--keep 可调）；
   audio 备份为增量镜像，不参与轮换。

用法（在仓库根或任意目录均可，路径基于脚本自身定位）：
    backend/.venv/Scripts/python.exe backend/scripts/backup.py            # 全量（db + audio）
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --keep 14  # 保留 14 份 db 产物
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --db-only      # 仅备份数据库
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --audio-only   # 仅增量复制音频
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --dry-run      # 只统计不落盘

退出码：0 成功；1 备份过程出错（源库损坏/快照校验失败/磁盘不可写等）。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "meloyu.db"
BACKUP_DIR = DATA_DIR / "backups"
AUDIO_SRC = DATA_DIR / "audio"
AUDIO_DST = BACKUP_DIR / "audio"
SNAPSHOT_GLOB = "meloyu-*.db"
PG_DUMP_GLOB = "pg-meloyu-*"


def _pg_database_url() -> str:
    """配置了 PG 连接串则返回（app.config），否则空串（= SQLite 回退）。"""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.config import settings
    return settings.database_url


def _pg_tables() -> list[str]:
    """全部表名，FK 依赖序（父表在前；Base.metadata.sorted_tables）。"""
    from app import models  # noqa: F401 —— 注册全部模型
    from app.models import Base
    return [t.name for t in Base.metadata.sorted_tables]


def backup_postgres(keep: int, dry_run: bool) -> bool:
    """PG 逐表 COPY 转储（text 格式 + gzip）+ 清单 + 轮换。返回是否成功。"""
    url = _pg_database_url()
    tables = _pg_tables()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = BACKUP_DIR / f"pg-meloyu-{stamp}"
    if dry_run:
        print(f"[db] dry-run：将转储 {len(tables)} 张表 -> {dest_dir}")
        return True
    from sqlalchemy import create_engine, text
    engine = create_engine(url, pool_pre_ping=True)
    manifest: dict[str, object] = {"format": "pg-copy-text", "created": stamp,
                                   "dialect": "postgresql", "tables": []}
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            raw = conn.connection.dbapi_connection  # type: ignore[attr-defined]
            total_rows = 0
            for i, table in enumerate(tables, 1):
                qtable = f'"{table}"'
                rows = conn.execute(text(f"SELECT count(*) FROM {qtable}")).scalar_one()
                part = dest_dir / f"{i:03d}-{table}.copy.gz"
                with gzip.open(part, "wb") as gz, raw.cursor() as cur:
                    cur.copy_expert(f"COPY {qtable} TO STDOUT", gz)
                manifest["tables"].append({"table": table, "rows": rows, "file": part.name})
                total_rows += rows
            manifest["total_rows"] = total_rows
    except Exception as exc:  # noqa: BLE001 —— 转储失败整体作废
        print(f"[db] PG 转储失败：{exc}", file=sys.stderr)
        shutil.rmtree(dest_dir, ignore_errors=True)
        return False
    finally:
        engine.dispose()
    # 转储即校验——逐文件 gzip 解压回读（CRC）+ 行数与 manifest 比对
    for entry in manifest["tables"]:
        part = dest_dir / entry["file"]
        try:
            with gzip.open(part, "rb") as gz:
                n = sum(1 for _ in gz)
        except (OSError, EOFError) as exc:
            print(f"[db] 转储校验失败（{part.name}：{exc}），已删除整个目录", file=sys.stderr)
            shutil.rmtree(dest_dir, ignore_errors=True)
            return False
        if n != entry["rows"]:
            print(f"[db] 转储校验失败（{entry['table']}：转储 {n} 行 != 库内 "
                  f"{entry['rows']} 行），已删除整个目录", file=sys.stderr)
            shutil.rmtree(dest_dir, ignore_errors=True)
            return False
    (dest_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    size_mb = sum(p.stat().st_size for p in dest_dir.iterdir()) / 1024 / 1024
    print(f"[db] 已转储 {len(tables)} 表 / {total_rows} 行 -> {dest_dir.name}"
          f"（{size_mb:.1f} MB，行数校验 ok）")
    rotate_pg_dumps(keep)
    return True


def rotate_pg_dumps(keep: int) -> int:
    """删除超出保留份数的旧 pg-* 转储目录（名字典序 = 时间序），返回删除数。"""
    dumps = sorted(p for p in BACKUP_DIR.glob(PG_DUMP_GLOB) if p.is_dir())
    doomed = dumps[:-keep] if keep > 0 else dumps
    for old in doomed:
        shutil.rmtree(old)
        print(f"[db] 轮换：删除旧转储目录 {old.name}")
    return len(doomed)


def backup_db(keep: int, dry_run: bool) -> bool:
    """数据库备份入口：按配置分流 PG 转储 / SQLite 快照。返回是否成功。"""
    if _pg_database_url():
        return backup_postgres(keep, dry_run)
    return backup_sqlite(keep, dry_run)


def backup_sqlite(keep: int, dry_run: bool) -> bool:
    """SQLite 在线备份 + 轮换（开发回退路径）。返回是否成功。"""
    if not DB_PATH.is_file():
        print(f"[db] 源库不存在，跳过：{DB_PATH}")
        return True
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"meloyu-{stamp}.db"
    if dry_run:
        existing = len(list(BACKUP_DIR.glob(SNAPSHOT_GLOB))) if BACKUP_DIR.is_dir() else 0
        print(f"[db] dry-run：将备份 {DB_PATH} -> {dest}")
        print(f"[db] dry-run：现有快照 {existing} 份，备份后按 --keep={keep} 轮换")
        return True
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)  # 页级在线备份，WAL 安全
        finally:
            dst.close()
            src.close()
    except sqlite3.Error as exc:
        print(f"[db] 备份失败：{exc}", file=sys.stderr)
        dest.unlink(missing_ok=True)
        return False
    # 快照即校验——integrity_check 不过的快照等于没有备份
    check = sqlite3.connect(dest)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()
    finally:
        check.close()
    if not result or result[0] != "ok":
        print(f"[db] 快照完整性校验失败（{result[0] if result else 'no result'}），"
              f"已删除：{dest.name}", file=sys.stderr)
        dest.unlink(missing_ok=True)
        return False
    size_mb = dest.stat().st_size / 1024 / 1024
    print(f"[db] 已备份 {DB_PATH.name} -> {dest.name}（{size_mb:.1f} MB，integrity ok）")
    rotate_snapshots(keep)
    return True


def rotate_snapshots(keep: int) -> int:
    """删除超出保留份数的旧 .db 快照（按文件名字典序 = 时间序），返回删除数。"""
    snapshots = sorted(p for p in BACKUP_DIR.glob(SNAPSHOT_GLOB) if p.is_file())
    doomed = snapshots[:-keep] if keep > 0 else snapshots
    for old in doomed:
        old.unlink()
        print(f"[db] 轮换：删除旧快照 {old.name}")
    return len(doomed)


def backup_audio(dry_run: bool) -> bool:
    """增量复制 audio/ → backups/audio/（mtime 或 size 变化才复制）。返回是否成功。"""
    if not AUDIO_SRC.is_dir():
        print(f"[audio] 源目录不存在，跳过：{AUDIO_SRC}")
        return True
    copied = skipped = scanned = 0
    for root, _dirs, files in os.walk(AUDIO_SRC):
        rel_dir = Path(root).relative_to(AUDIO_SRC)
        for name in files:
            scanned += 1
            src_file = Path(root) / name
            dst_file = AUDIO_DST / rel_dir / name
            src_stat = src_file.stat()
            if dst_file.is_file():
                dst_stat = dst_file.stat()
                if dst_stat.st_size == src_stat.st_size and int(dst_stat.st_mtime) == int(
                    src_stat.st_mtime
                ):
                    skipped += 1
                    continue
            copied += 1
            if dry_run:
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)  # copy2 保留 mtime，供下次增量比对
    action = "dry-run：待复制" if dry_run else "已复制"
    print(f"[audio] 扫描 {scanned} 个文件，{action} {copied} 个，未变化跳过 {skipped} 个")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Meloyu 备份：PostgreSQL COPY 转储（或 SQLite 在线快照）+ 音频增量复制")
    parser.add_argument("--keep", type=int, default=7, metavar="N",
                        help="保留最近 N 份 db 备份产物（默认 7；audio 不轮换）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--db-only", action="store_true", help="仅备份数据库")
    mode.add_argument("--audio-only", action="store_true", help="仅增量复制音频")
    parser.add_argument("--dry-run", action="store_true", help="只统计与打印目标路径，不写任何文件")
    args = parser.parse_args(argv)

    print(f"== Meloyu backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
          f"{'(dry-run)' if args.dry_run else ''}".rstrip())
    do_db = not args.audio_only
    do_audio = not args.db_only
    ok = True
    if do_db:
        ok = backup_db(args.keep, args.dry_run) and ok
    if do_audio:
        ok = backup_audio(args.dry_run) and ok
    print("== 备份完成" if ok else "== 备份失败（见上方错误）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
