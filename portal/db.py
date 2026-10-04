"""License Portal 存储（stdlib sqlite3，零额外依赖）。

表：
- licenses：签发记录（lid 主键；stripe_session_id 唯一——Payment Link 履约幂等）
- activations：在线激活上报（lid×device_id 唯一；仅治理数据，离线验签不依赖）
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
        c.executescript("""
        CREATE TABLE IF NOT EXISTS licenses (
            lid            TEXT PRIMARY KEY,
            key            TEXT NOT NULL UNIQUE,
            tier           TEXT NOT NULL,
            note           TEXT,
            devices        INTEGER NOT NULL DEFAULT 3,
            seats          INTEGER,
            status         TEXT NOT NULL DEFAULT 'active',
            stripe_session_id TEXT UNIQUE,
            created_at     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lid           TEXT NOT NULL,
            device_id     TEXT NOT NULL,
            activated_at  TEXT NOT NULL,
            last_seen_at  TEXT NOT NULL,
            UNIQUE(lid, device_id)
        );
        """)


@contextmanager
def conn():
    if _DB_PATH is None:
        raise RuntimeError("portal.db not initialised (call init())")
    with _LOCK:
        c = sqlite3.connect(_DB_PATH)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()
