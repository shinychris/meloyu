"""轻量 SQLite 幂等迁移（无 Alembic 依赖）：启动时按需补列/改列。

每条迁移自检是否已应用（查 PRAGMA table_info / sqlite_master），重复执行无副作用。
新增列用 ADD COLUMN；需要改列约束（如 NOT NULL → NULL）时走「建新表→拷贝→删旧→改名」
标准流程，全程 AUTOCOMMIT 连接以便 PRAGMA foreign_keys 生效。
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.logging import logger

# M-20260831-a：llm_settings 补 V1.3 歌曲模型通道列（localsynth|api）
# M-20260901-a：llm_settings 补 V1.4 开源歌曲模型目录通道列（replicate/musicgen_local）
_ADD_COLUMNS: list[tuple[str, str]] = [
    ("music_backend",
     "ALTER TABLE llm_settings ADD COLUMN music_backend VARCHAR(16) NOT NULL DEFAULT 'localsynth'"),
    ("music_api_base_url",
     "ALTER TABLE llm_settings ADD COLUMN music_api_base_url VARCHAR(300) NOT NULL DEFAULT ''"),
    ("music_api_key",
     "ALTER TABLE llm_settings ADD COLUMN music_api_key VARCHAR(300) NOT NULL DEFAULT ''"),
    ("music_api_model",
     "ALTER TABLE llm_settings ADD COLUMN music_api_model VARCHAR(120) NOT NULL DEFAULT ''"),
    ("replicate_api_token",
     "ALTER TABLE llm_settings ADD COLUMN replicate_api_token VARCHAR(300) NOT NULL DEFAULT ''"),
    ("music_model",
     "ALTER TABLE llm_settings ADD COLUMN music_model VARCHAR(60) NOT NULL DEFAULT ''"),
    ("replicate_slugs",
     "ALTER TABLE llm_settings ADD COLUMN replicate_slugs JSON NOT NULL DEFAULT '{}'"),
]


def run(engine: Engine) -> list[str]:
    """执行全部未应用的迁移，返回应用清单（供启动日志与冒烟观测）。"""
    applied: list[str] = []
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(llm_settings)"))}
        for name, ddl in _ADD_COLUMNS:
            if name not in cols:
                conn.execute(text(ddl))
                applied.append(f"llm_settings.{name}")

        # M-20260831-b：candidates.quality_score NOT NULL → 可空（外部模型候选无 AI 质量分，
        # 不再造分——见 ADR-012）。SQLite 中 NULL 可通过 CHECK 约束，无需改约束本身。
        info = [r for r in conn.execute(text("PRAGMA table_info(candidates)"))
                if r[1] == "quality_score"]
        if info and info[0][3]:  # 第 4 列 = notnull 标志
            _rebuild_table(conn, "candidates", "candidates__v13")
            applied.append("candidates.quality_score → nullable")

        # M-20260831-c：tasks.stage_key 约束补 V1.3/V1.4 枚举（writing / api_* / model_*）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
        ).scalar_one_or_none()
        if ddl and "'model_load'" not in ddl:
            _rebuild_table(conn, "tasks", "tasks__v14")
            applied.append("tasks.stage_key 增加 model_* 枚举")
    if applied:
        logger.info(f"sqlite migrations applied: {', '.join(applied)}")
    return applied


def _rebuild_table(conn, table_name: str, tmp_name: str) -> None:
    """标准表重建：建临时表→拷贝→删旧表→改名→补建索引（CHECK 约束/列约束变更走此路径）。"""
    from sqlalchemy.schema import CreateIndex, CreateTable

    from app.models.task import Task
    from app.models.work import Candidate

    tables = {"candidates": Candidate.__table__, "tasks": Task.__table__}
    table = tables[table_name]

    conn.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        ddl = str(CreateTable(table).compile(dialect=conn.dialect)).strip()
        tmp_ddl = ddl.replace(f"CREATE TABLE {table_name} (",
                              f"CREATE TABLE {tmp_name} (", 1)
        if tmp_ddl == ddl:  # 表名未被替换（DDL 形态变化）→ 显式失败，不做危险操作
            raise RuntimeError(f"{table_name} 建表 DDL 形态不符合预期，迁移中止")
        conn.execute(text(tmp_ddl))
        cols = ", ".join(c.name for c in table.columns)
        conn.execute(text(f"INSERT INTO {tmp_name} ({cols}) SELECT {cols} FROM {table_name}"))
        conn.execute(text(f"DROP TABLE {table_name}"))
        # RENAME 会把 files 等表的外键引用改写回原表名，随后重建外键完整性检查
        conn.execute(text(f"ALTER TABLE {tmp_name} RENAME TO {table_name}"))
        for idx in table.indexes:  # 独立索引随 DROP TABLE 消失，需按新表补建
            conn.execute(CreateIndex(idx))
        conn.execute(text("PRAGMA foreign_key_check"))
    finally:
        conn.execute(text("PRAGMA foreign_keys=ON"))
