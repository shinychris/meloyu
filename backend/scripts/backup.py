r"""Meloyu 数据备份脚本（P1-8）。

功能：
1. SQLite 在线备份：backend/data/meloyu.db（WAL 模式）→
   backend/data/backups/meloyu-YYYYMMDD-HHMMSS.db。
   使用 sqlite3Connection.backup() 页级 API，服务运行中执行安全，
   产出为自包含快照（不依赖 -wal/-shm）。
2. 音频产物增量复制：backend/data/audio/ → backend/data/backups/audio/。
   仅复制 size 或 mtime 与备份侧不一致的文件（os.walk 递归，保持相对目录结构）。
3. 轮换：backups/ 下 .db 快照保留最近 N 份（默认 7，--keep 可调）；
   audio 备份为增量镜像，不参与轮换。

用法（在仓库根或任意目录均可，路径基于脚本自身定位）：
    backend/.venv/Scripts/python.exe backend/scripts/backup.py            # 全量（db + audio）
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --keep 14  # 保留 14 份 db 快照
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --db-only      # 仅备份数据库
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --audio-only   # 仅增量复制音频
    backend/.venv/Scripts/python.exe backend/scripts/backup.py --dry-run      # 只统计不落盘

Windows 计划任务（每天 03:30 执行，一行命令）：
    schtasks /Create /TN "Meloyu Backup" /SC DAILY /ST 03:30 /TR "D:\Codebase\Meloyu\backend\.venv\Scripts\python.exe D:\Codebase\Meloyu\backend\scripts\backup.py"

退出码：0 成功；1 备份过程出错（源库损坏/磁盘不可写等）。
"""
from __future__ import annotations

import argparse
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


def backup_db(keep: int, dry_run: bool) -> bool:
    """SQLite 在线备份 + 轮换。返回是否成功。"""
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
    size_mb = dest.stat().st_size / 1024 / 1024
    print(f"[db] 已备份 {DB_PATH.name} -> {dest.name}（{size_mb:.1f} MB）")
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
    parser = argparse.ArgumentParser(description="Meloyu 备份：SQLite 在线快照 + 音频增量复制")
    parser.add_argument("--keep", type=int, default=7, metavar="N",
                        help="保留最近 N 份 .db 快照（默认 7；audio 不轮换）")
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
