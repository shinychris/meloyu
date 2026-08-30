"""ORM 公共基础设施：UUID 主键、UTC ISO 时间戳、BaseModel。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def new_uuid() -> str:
    """主键生成：uuid4 hex（32 位小写，无连字符）。"""
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    """当前 UTC 时间，定长 ISO 8601 格式（字典序=时间序）。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ISOTimestamp(TypeDecorator[str]):
    """SQLite 无原生 datetime：统一以 'YYYY-MM-DDTHH:MM:SSZ' 字符串落库。"""

    impl = String(30)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return str(value)

    def process_result_value(self, value, dialect):
        return value  # 已是 Z 结尾字符串，原样返回


class Base(DeclarativeBase):
    """全局 DeclarativeBase。"""


class BaseModel(Base):
    """公共字段：id / created_at / updated_at + repr + to_dict。"""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    created_at: Mapped[str] = mapped_column(
        ISOTimestamp(), nullable=False, default=utc_now_iso
    )
    updated_at: Mapped[str] = mapped_column(
        ISOTimestamp(), nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    _dict_exclude: frozenset[str] = frozenset()

    def to_dict(self, *, exclude: set[str] | None = None) -> dict:
        hidden = self._dict_exclude | (exclude or set())
        return {
            c.key: getattr(self, c.key)
            for c in self.__table__.columns
            if c.key not in hidden
        }
