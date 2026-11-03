"""License Portal 存储（stdlib sqlite3，零额外依赖）。

表：
- licenses：签发记录（lid 主键；stripe_session_id 唯一——Payment Link 履约幂等）
- activations：在线激活上报（lid×device_id 唯一；仅治理数据，离线验签不依赖）

并发约束：SQLite 单写入方，portal **必须单进程单 worker 运行**
（README 部署节同款约束）；连接带 30s busy timeout + WAL 缓解偶发并写，
但不构成多 worker 许可。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH: Path | None = None
_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init(db_path: Path) -> None:
    global _DB_PATH
    _DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        # WAL（持久属性，库级一次设置、幂等重设无害）：读写不互斥；
        # 写写冲突由 conn() 的 30s busy timeout 兜底
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS licenses (
            lid            TEXT PRIMARY KEY,
            key            TEXT NOT NULL UNIQUE,
            code           TEXT UNIQUE,
            tier           TEXT NOT NULL,
            account        TEXT,
            note           TEXT,
            devices        INTEGER NOT NULL DEFAULT 3,
            seats          INTEGER,
            status         TEXT NOT NULL DEFAULT 'active',
            stripe_session_id TEXT UNIQUE,
            created_at     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lid           TEXT NOT NULL REFERENCES licenses(lid),
            device_id     TEXT NOT NULL,
            activated_at  TEXT NOT NULL,
            last_seen_at  TEXT NOT NULL,
            UNIQUE(lid, device_id)
        );
        """)
        # 存量库防御：2026-10-04 激活码批次前建的表补列（列已存在则忽略）。
        # 注：REFERENCES 外键仅新库建表生效；旧库沿用原有结构不受影响
        # （IF NOT EXISTS 语义不会改动已存在的表）
        for ddl in ("ALTER TABLE licenses ADD COLUMN code TEXT",
                    "ALTER TABLE licenses ADD COLUMN account TEXT"):
            try:
                c.execute(ddl)
            except sqlite3.OperationalError:
                pass


@contextmanager
def conn():
    if _DB_PATH is None:
        raise RuntimeError("portal.db not initialised (call init())")
    with _LOCK:
        # timeout=30：写锁占用时等待而非立刻 OperationalError（
        # CLI 工具/管理操作偶发并写的兜底；单进程约束见模块 docstring）
        c = sqlite3.connect(_DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        # REFERENCES 需按连接开启才真正生效（portal 全库无删除 licenses 路径，
        # 无级联/孤儿风险）；存量库无外键声明时开启亦无副作用
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        finally:
            c.close()
