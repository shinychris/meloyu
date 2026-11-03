"""数据库引擎与会话（v0.15.0 起：PostgreSQL 为主，SQLite 保留为本机开发回退）。

生产/Supabase：settings.database_url（postgresql+psycopg2://...，SSL 经 URL
query 参数 sslmode=require 传递）；本地 Docker 栈由 compose 的 postgres 服务
提供。SQLite 回退仅服务无 PG 环境（裸 dev / 单元测试），沿用 WAL + 跨线程
共享的既有形态。

历史上 SQLite 单写入方约束（两次库损坏事故，2026-09-05/06）随 PG 切换解除：
PG 为多写入方 MVCC 并发模型，dev uvicorn 与 8180 容器可安全并存（仍建议
指向不同库实例避免数据混淆）。
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings


def _build_engine():
    if settings.database_url:
        # PostgreSQL：连接池默认 5+10 溢出，对 Supabase pooler 足够（其事务
        # 模式建议客户端小池）。pool_pre_ping 吸收 pgBouncer/云端闪断。
        return create_engine(settings.database_url, pool_pre_ping=True)

    # ---- SQLite 开发回退（data 目录 + WAL + 线程共享） ----
    settings.data_path.mkdir(parents=True, exist_ok=True)
    sqlite_engine = create_engine(
        f"sqlite:///{settings.db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    @event.listens_for(sqlite_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    return sqlite_engine


def is_postgres() -> bool:
    return engine.dialect.name == "postgresql"


engine = _build_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
