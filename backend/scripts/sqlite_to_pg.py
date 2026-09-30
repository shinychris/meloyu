r"""Meloyu SQLite → PostgreSQL 数据迁移（v0.15.0 切库工具）。

用法（backend venv）：
    # 目标 = app 配置的 DATABASE_URL（.env / 环境变量）
    python scripts/sqlite_to_pg.py
    # 显式指定两端
    python scripts/sqlite_to_pg.py --sqlite data/meloyu.db \
        --url postgresql+psycopg2://meloyu:pwd@127.0.0.1:5433/meloyu
    # 目标库已有数据时强制清空重导
    python scripts/sqlite_to_pg.py --force

流程：
1. 源 SQLite 经 SQLAlchemy 以**模型同款 Table**读取——JSON 反序列化为
   dict/list、0/1 还原为 bool、时间戳保持 ISO 字符串，再以同款类型绑定写入
   PG（双方言各走各的 TypeEngine 序列化，无裸文本直灌）；
2. 目标库先 create_all 建终态 schema（模型已含全部历史迁移结果）；
3. 按 Base.metadata.sorted_tables 的 FK 依赖序（父表在前）分批搬运；
4. 逐表行数校验；--force 时先 TRUNCATE 全表。

注意：
- 源库必须是已跑到 v0.14.0 迁移的库（schema 与模型一致）；
- 音频文件不入库（磁盘 bind 挂载不变），本脚本只搬元数据；
- 建议在应用停写源库后执行（切库窗口内一次性完成）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

BATCH = 500

# 历史 SQLite 库的 33 字符 id（种子期 "e"+"0"*31+序号 构造笔误，SQLite 不校验
# 长度无感存续；v0.15.0 起种子已改 32 字符）：PG 侧 String(32) 拒写。在途改写
# 为 32 字符（掐掉第 2 位），不改动源库（迁移前冷备已另行保护）。
# 幂等：长度合规的值原样通过。
_REMAP_LEN32 = {"users.id", "certificates.id"}


def _legacy_remap(table: str, column: str, value):
    if (f"{table}.{column}" in _REMAP_LEN32 or column.endswith("user_id")) \
            and isinstance(value, str) and len(value) > 32:
        return value[0] + value[2:]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Meloyu SQLite → PostgreSQL 迁移")
    parser.add_argument("--sqlite", default=str(BACKEND_DIR / "data" / "meloyu.db"),
                        help="源 SQLite 库路径（默认 backend/data/meloyu.db）")
    parser.add_argument("--url", default="",
                        help="目标 PG 连接串（缺省用 app 配置的 DATABASE_URL）")
    parser.add_argument("--force", action="store_true",
                        help="目标库非空时先 TRUNCATE 全部表再导入")
    args = parser.parse_args(argv)

    from sqlalchemy import create_engine, text

    from app import models  # noqa: F401 —— 注册全部模型到 Base.metadata
    from app.models import Base

    src_path = Path(args.sqlite)
    if not src_path.is_file():
        print(f"[migrate] 源库不存在：{src_path}", file=sys.stderr)
        return 1
    url = args.url
    if not url:
        from app.config import settings
        url = settings.database_url
    if not url or not url.startswith("postgresql"):
        print("[migrate] 目标必须是 PostgreSQL 连接串（--url 或 DATABASE_URL）",
              file=sys.stderr)
        return 1

    src = create_engine(f"sqlite:///{src_path.as_posix()}")
    dst = create_engine(url, pool_pre_ping=True)
    tables = Base.metadata.sorted_tables  # FK 依赖序：父表在前

    try:
        Base.metadata.create_all(dst)
        all_tables = ", ".join(f'"{t.name}"' for t in tables)

        with dst.begin() as conn:
            nonempty = [t.name for t in tables if conn.execute(
                text(f'SELECT 1 FROM "{t.name}" LIMIT 1')).first()]
        if nonempty:
            if not args.force:
                print(f"[migrate] 目标库非空（{len(nonempty)} 表有数据）；确认覆盖请加 --force",
                      file=sys.stderr)
                return 1
            # 先 drop 再 create：create_all 不会 ALTER 既有列（首跑可能用了旧列宽），
            # --force 语义即"以当前模型终态 schema 重建"
            Base.metadata.drop_all(dst)
            Base.metadata.create_all(dst)
            print(f"[migrate] --force：已按当前模型重建 {len(tables)} 张表")

        total_rows = 0
        # ---- 孤儿数据治理 ----
        # 源库为 SQLite 历史积累（含 09-05/06 事故恢复搬运），存在指向已删父行
        # 的孤儿：非空外键孤儿整行剔除（死数据，任何 join 不可达）；可空外键
        # 孤儿置 NULL（SET NULL 语义，保留行）。逐表计数留痕。
        fk_cols: dict[str, list] = {t.name: list(t.foreign_keys) for t in tables}
        parent_sets: dict[str, set] = {}
        orphans: dict[str, int] = {}

        def _parent_set(ptable: str, pcol: str) -> set:
            key = f"{ptable}.{pcol}"
            if key not in parent_sets:
                vals = {r[0] for r in sconn.execute(
                    text(f'SELECT "{pcol}" FROM "{ptable}" WHERE "{pcol}" IS NOT NULL'))}
                if ptable in ("users", "certificates"):  # 历史 33 字符 id 与子表 remap 对齐
                    vals = {_legacy_remap(ptable, pcol, v) if isinstance(v, str) else v
                            for v in vals}
                parent_sets[key] = vals
            return parent_sets[key]

        def _sanitize(table_name: str, row: dict) -> dict | None:
            for fk in fk_cols.get(table_name, ()):
                pset = _parent_set(fk.column.table.name, fk.column.name)
                v = row.get(fk.parent.name)
                if v is None or v in pset:
                    continue
                if fk.parent.nullable:
                    row[fk.parent.name] = None
                else:
                    orphans[f"{table_name}.{fk.parent.name}"] = (
                        orphans.get(f"{table_name}.{fk.parent.name}", 0) + 1)
                    return None
            return row

        # 循环外键（use_alter，works↔versions / works↔files）：父表先入库但指向
        # 后入库的表——先置 NULL 入库，全部表搬完后统一 UPDATE 回填
        deferred: dict[tuple, list] = {}
        use_alter_cols: dict[str, list] = {
            t.name: [fk for fk in t.foreign_keys if fk.use_alter] for t in tables}
        stripped = sum(1 for v in use_alter_cols.values() for _ in v)
        if stripped:
            print(f"[migrate] 循环外键列 {stripped} 个：入库置 NULL，尾部统一回填")

        with src.connect() as sconn:
            for table in tables:
                name = table.name
                src_cols = {r[1] for r in sconn.execute(text(f"PRAGMA table_info({name})"))}
                want = [c.name for c in table.columns if c.name in src_cols]
                missing = [c.name for c in table.columns if c.name not in src_cols]
                if missing:
                    print(f"[migrate] ⚠ {name}: 源库缺列 {missing}（这些列留默认值/NULL）")
                rows = sconn.execution_options(stream_results=True).execute(
                    table.select().with_only_columns(*[table.c[c] for c in want]))
                moved = dropped = 0
                alters = {fk.parent.name for fk in use_alter_cols.get(name, ())}
                while True:
                    chunk = rows.fetchmany(BATCH)
                    if not chunk:
                        break
                    payload = []
                    for r in chunk:
                        row = _sanitize(
                            name,
                            {k: _legacy_remap(name, k, v)
                             for k, v in zip(want, r, strict=True)})
                        if row is None:
                            dropped += 1
                            continue
                        for col in alters:
                            if row.get(col) is not None:
                                deferred.setdefault((name, col), []).append(
                                    (row["id"], row[col]))
                                row[col] = None
                        payload.append(row)
                    if payload:
                        with dst.begin() as conn:
                            conn.execute(table.insert(), payload)
                    moved += len(payload)
                rows.close()
                with dst.connect() as conn:
                    got = conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
                if got != moved:
                    print(f"[migrate] ✗ {name}: 导入 {moved} 行但目标有 {got} 行", file=sys.stderr)
                    return 1
                total_rows += moved
                note = f"（剔除孤儿 {dropped} 行）" if dropped else ""
                print(f"[migrate] {name}: {moved} 行{note}")
        # 尾部回填循环外键值
        for (tname, col), pairs in deferred.items():
            tmeta = next(t for t in tables if t.name == tname)
            with dst.begin() as conn:
                for rid, val in pairs:
                    conn.execute(
                        tmeta.update().where(tmeta.c.id == rid).values({col: val}))
            print(f"[migrate] 回填 {tname}.{col}: {len(pairs)} 行")
        if orphans:
            print(f"[migrate] 孤儿剔除汇总: {orphans}")
        print(f"[migrate] 完成：{len(tables)} 表 / {total_rows} 行已迁至 PostgreSQL")
        return 0
    finally:
        src.dispose()
        dst.dispose()


if __name__ == "__main__":
    sys.exit(main())
