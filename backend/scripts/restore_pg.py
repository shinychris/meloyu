r"""Meloyu PostgreSQL 恢复脚本（v0.15.0，配套 scripts/backup.py 的 pg-copy 产物）。

用法（backend venv）：
    python scripts/restore_pg.py <转储目录> --url postgresql+psycopg2://... [--verify-only]

流程：
1. 读 manifest.json，按其中表顺序（FK 父表在前）恢复；
2. --verify-only：只比对库内行数与 manifest，不写任何数据；
3. 常规恢复：TRUNCATE 全部表（RESTART IDENTITY CASCADE，一次事务）→
   逐表 COPY FROM STDIN（text 格式）→ 提交后回读行数校验。

⚠ 恢复会清空目标库现有数据；仅对停写状态的目标库执行（应用停机或维护窗口）。
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Meloyu PG 备份恢复")
    parser.add_argument("dump_dir", help="backup.py 产出的 pg-meloyu-* 目录")
    parser.add_argument("--url", default="",
                        help="目标库连接串（缺省用 app 配置的 DATABASE_URL）")
    parser.add_argument("--verify-only", action="store_true",
                        help="只校验行数，不写入")
    args = parser.parse_args(argv)

    url = args.url
    if not url:
        from app.config import settings
        url = settings.database_url
        if not url:
            print("[restore] 未指定 --url 且应用未配置 DATABASE_URL", file=sys.stderr)
            return 1

    dump_dir = Path(args.dump_dir)
    manifest_path = dump_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"[restore] manifest 缺失：{manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "pg-copy-text":
        print(f"[restore] 不支持的备份格式：{manifest.get('format')}", file=sys.stderr)
        return 1

    from sqlalchemy import create_engine, text
    from sqlalchemy.schema import AddConstraint, DropConstraint

    from app import models  # noqa: F401
    from app.models import Base
    engine = create_engine(url, pool_pre_ping=True)
    tables = [e["table"] for e in manifest["tables"]]
    # 循环外键（works↔versions/files 等 use_alter）：整表 COPY 顺序无法同时满足
    # 双向引用——载入前临时 DROP 约束，载入后重建（不需超级用户，
    # session_replication_mode 在 Supabase 等托管库不可用）
    alter_constraints = [fk.constraint for t in Base.metadata.sorted_tables
                          for fk in t.foreign_keys if fk.use_alter]

    try:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            mismatches = []
            has_data = False
            for entry in manifest["tables"]:
                rows = conn.execute(
                    text(f'SELECT count(*) FROM "{entry["table"]}"')).scalar_one()
                if rows:
                    has_data = True
                if rows != entry["rows"]:
                    mismatches.append(f'{entry["table"]}: 库内 {rows} != 备份 {entry["rows"]}')
            if args.verify_only:
                if mismatches:
                    print("[restore] 校验不一致：\n  " + "\n  ".join(mismatches),
                          file=sys.stderr)
                    return 1
                print("[restore] 校验通过：全部表行数与备份一致")
                return 0
            if has_data and mismatches:
                # 守卫只拦"非空且与备份不一致"的覆盖（疑似异构数据）；空库或
                # 与备份完全一致的库（幂等重放）直接放行
                print("[restore] 目标库非空且行数与备份不一致；如确认覆盖请先手动清库"
                      "（TRUNCATE）后重试：\n  " + "\n  ".join(mismatches[:5]), file=sys.stderr)
                return 1
            all_tables = ", ".join(f'"{t}"' for t in tables)
            for cons in alter_constraints:
                conn.execute(text(f'ALTER TABLE "{cons.table.name}" '
                                  f'DROP CONSTRAINT IF EXISTS "{cons.name}"'))
            conn.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
            raw = conn.connection.dbapi_connection  # type: ignore[attr-defined]
            with raw.cursor() as cur:
                for entry in manifest["tables"]:
                    part = dump_dir / entry["file"]
                    with gzip.open(part, "rb") as gz:
                        cur.copy_expert(f'COPY "{entry["table"]}" FROM STDIN', gz)
                    print(f'[restore] {entry["table"]}: {entry["rows"]} 行已载入')
            for cons in alter_constraints:
                conn.execute(AddConstraint(cons))
            print(f"[restore] 循环外键约束已重建（{len(alter_constraints)} 个）")
        # 回读校验（独立事务，确认提交后状态）
        with engine.connect() as conn:
            for entry in manifest["tables"]:
                rows = conn.execute(
                    text(f'SELECT count(*) FROM "{entry["table"]}"')).scalar_one()
                if rows != entry["rows"]:
                    print(f'[restore] 恢复后校验失败：{entry["table"]} '
                          f'{rows} != {entry["rows"]}', file=sys.stderr)
                    return 1
        print(f"[restore] 恢复完成：{len(tables)} 表 / {manifest.get('total_rows')} 行")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
