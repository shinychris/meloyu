"""发号器仓储（sequence_counters，事务自增）。"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def next_counter(db: Session, key: str) -> int:
    """事务内自增取号（SQLite 写锁保证串行）。"""
    row = db.execute(
        text("UPDATE sequence_counters SET value = value + 1, updated_at = :now "
             "WHERE key = :k RETURNING value"),
        {"k": key, "now": _now()},
    ).fetchone()
    if row is None:
        db.execute(
            text("INSERT INTO sequence_counters (key, value, created_at, updated_at) "
                 "VALUES (:k, 1, :now, :now)"),
            {"k": key, "now": _now()},
        )
        return 1
    return int(row[0])


def peek_counter(db: Session, key: str) -> int:
    row = db.execute(text("SELECT value FROM sequence_counters WHERE key = :k"),
                     {"k": key}).fetchone()
    return int(row[0]) if row else 0


def set_counter(db: Session, key: str, value: int) -> None:
    row = db.execute(text("SELECT value FROM sequence_counters WHERE key = :k"),
                     {"k": key}).fetchone()
    if row is None:
        db.execute(
            text("INSERT INTO sequence_counters (key, value, created_at, updated_at) "
                 "VALUES (:k, :v, :now, :now)"),
            {"k": key, "v": value, "now": _now()})
    else:
        db.execute(
            text("UPDATE sequence_counters SET value = :v, updated_at = :now WHERE key = :k"),
            {"k": key, "v": value, "now": _now()})


def _now() -> str:
    from app.models.base import utc_now_iso
    return utc_now_iso()
