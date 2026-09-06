"""2026-09-06 恢复脚本：WAL 跨 Docker bind 并发后主库 b-tree 损坏（versions 树
1419 坏 cell + files rowid>4500 坏块），宿主机冷读亦 malformed。

策略：新库重建 schema + 逐表分块搬运（坏块跳过并计数），坏区间数据如实丢弃
（经核对主要为冒烟测试数据）。用法（确保所有写入方已停）：

    cd backend && ./.venv/Scripts/python.exe scripts/recover_db_20260906.py

产物：data/meloyu.recovered.db；校验通过后人工替换 data/meloyu.db。
损坏存证：data/backups/meloyu-corrupt-20260906.db。
"""
from __future__ import annotations

import sys
from pathlib import Path

import sqlite3

DATA = Path(__file__).resolve().parent.parent / "data"
SRC = DATA / "meloyu.db"
DST = DATA / "meloyu.recovered.db"
CHUNK = 200  # 分块行数：坏块只丢一小段，而非整表


def main() -> int:
    if DST.exists():
        DST.unlink()
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    dst = sqlite3.connect(str(DST))
    dst.execute("PRAGMA journal_mode=WAL")

    # 1. schema 原样重建（表/索引/触发器；sqlite_master 的 sql 即权威 DDL）
    objs = src.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    for typ, name, sql in objs:
        if typ in ("table", "index", "trigger"):
            dst.execute(sql)
            print(f"schema {typ}: {name}")

    report: list[tuple[str, int, int]] = []  # (table, copied, lost_chunks)
    tables = [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        cols = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
        col_list = ", ".join(f'"{c}"' for c in cols)
        ph = ", ".join("?" for _ in cols)
        copied = 0
        bad_chunks = 0
        consecutive_bad = 0
        start = 1
        # rowid 硬上限 + 连续坏块熔断：坏区之后探测持续报错时不再无限推进
        while start <= 10_000_000 and consecutive_bad < 20:
            try:
                rows = src.execute(
                    f'SELECT {col_list} FROM "{table}" WHERE rowid >= ? AND rowid < ? '
                    f'ORDER BY rowid', (start, start + CHUNK)).fetchall()
            except sqlite3.DatabaseError:
                bad_chunks += 1  # 该块所在页损坏：跳过一个 rowid 窗口
                consecutive_bad += 1
                start += CHUNK
                continue
            consecutive_bad = 0
            if not rows:
                # 空块：可能是窗口越界或坏区——探测后续是否还有行
                try:
                    more = src.execute(
                        f'SELECT 1 FROM "{table}" WHERE rowid >= ? LIMIT 1',
                        (start + CHUNK,)).fetchone()
                except sqlite3.DatabaseError:
                    consecutive_bad += 1
                    start += CHUNK
                    continue
                if not more:
                    break
                start += CHUNK
                continue
            dst.executemany(
                f'INSERT OR IGNORE INTO "{table}" ({col_list}) VALUES ({ph})', rows)
            copied += len(rows)
            start += CHUNK
        report.append((table, copied, bad_chunks))

    # sqlite_sequence（AUTOINCREMENT 续号）
    try:
        seq = src.execute("SELECT name, seq FROM sqlite_sequence").fetchall()
        for name, seq_v in seq:
            dst.execute("INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                        (name, seq_v))
        print(f"sqlite_sequence: {len(seq)} rows")
    except sqlite3.DatabaseError:
        print("sqlite_sequence: unreadable (autoincrement counters reset to max rowid)")

    dst.commit()
    print("\n=== 搬运报告 ===")
    for table, copied, bad in report:
        flag = "  ⚠ BAD CHUNKS" if bad else ""
        print(f"{table}: copied={copied}, bad_chunks={bad}{flag}")

    print("\nintegrity:", dst.execute("PRAGMA integrity_check").fetchall()[:3])
    dst.close()
    src.close()
    print(f"\nOK → {DST}（校验通过后手动替换 meloyu.db）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
