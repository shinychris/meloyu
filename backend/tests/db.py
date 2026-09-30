"""测试数据库引擎工厂（v0.15.0 PG 切库配套）。

默认：SQLite 内存库（零依赖，CI/本机快速路径）。
设环境变量 MELOYU_TEST_DATABASE_URL 后整套测试跑在 PostgreSQL 上
（生产方言门禁，语义差异——ILIKE/CHECK 约束/并发 upsert 等——在 PG 上真实
暴露）：
    MELOYU_TEST_DATABASE_URL=postgresql+psycopg2://meloyu:pwd@127.0.0.1:5433/meloyu_test \
        python -m unittest discover -s tests

测试方法间隔离：SQLite 内存库每引擎天然新库；PG 库持久，reset_db 先
drop_all 再 create_all 保证每用例空库起步。
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def new_test_engine():
    """构造测试引擎：环境变量指向 PG 则用 PG，否则 SQLite 内存共享连接。"""
    url = os.environ.get("MELOYU_TEST_DATABASE_URL", "")
    if url:
        return create_engine(url, pool_pre_ping=True)
    # StaticPool 单连接共享：TestClient 工作线程与本线程同库（否则各自空库）
    return create_engine("sqlite:///:memory:",
                         connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


def reset_db(engine) -> None:
    """空库起步：PG 持久库先 drop；SQLite 内存库 drop 空库为无害空操作。

    PG 附加保护：先终止库上其余后端连接——部分测试会话不显式 close（SQLite
    时代无感知），其 idle-in-transaction 连接会拿住表锁，令下一次 drop_all
    永久等待（实测 test_model_center_docker_host 即中招）。
    """
    from app.models import Base
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed_plans(db, skip: frozenset[str] | set[str] = frozenset()) -> None:
    """播种档位行（users.plan → plans.code 外键的测试侧前提）。

    PG 强制外键而 SQLite 测试引擎从未开启——夹具建用户前需保证 plan code
    存在。skip：夹具自带定制 Plan 行的 code（如 quotas 的 free/pro 定制
    配额值），跳过避免主键冲突。merge 幂等，可重复调用。
    """
    from app.models import Plan
    from app.models.base import utc_now_iso
    ts = utc_now_iso()
    for i, code in enumerate(("free", "pro", "studio", "team")):
        if code in skip:
            continue
        db.merge(Plan(code=code, name=code.title(), price_monthly=None,
                      price_yearly=None, daily_generations=None,
                      monthly_credits=None, max_export="mp3",
                      commercial_license=False, watermark=True, features=[],
                      switchable=True, sort_order=i, created_at=ts, updated_at=ts))
