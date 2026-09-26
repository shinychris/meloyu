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
# M-20260902-a/b：v0.7.0 商业化批（users/certificates 补列）
# 元素：(表名, 列名, DDL)
_ADD_COLUMNS: list[tuple[str, str, str]] = [
    ("llm_settings", "music_backend",
     "ALTER TABLE llm_settings ADD COLUMN music_backend VARCHAR(16) NOT NULL DEFAULT 'localsynth'"),
    ("llm_settings", "music_api_base_url",
     "ALTER TABLE llm_settings ADD COLUMN music_api_base_url VARCHAR(300) NOT NULL DEFAULT ''"),
    ("llm_settings", "music_api_key",
     "ALTER TABLE llm_settings ADD COLUMN music_api_key VARCHAR(300) NOT NULL DEFAULT ''"),
    ("llm_settings", "music_api_model",
     "ALTER TABLE llm_settings ADD COLUMN music_api_model VARCHAR(120) NOT NULL DEFAULT ''"),
    ("llm_settings", "replicate_api_token",
     "ALTER TABLE llm_settings ADD COLUMN replicate_api_token VARCHAR(300) NOT NULL DEFAULT ''"),
    ("llm_settings", "music_model",
     "ALTER TABLE llm_settings ADD COLUMN music_model VARCHAR(60) NOT NULL DEFAULT ''"),
    ("llm_settings", "replicate_slugs",
     "ALTER TABLE llm_settings ADD COLUMN replicate_slugs JSON NOT NULL DEFAULT '{}'"),
    # M-20260901-b：V1.5.1 自托管推理服务通道端点（mmax_local/songgen_local）
    ("llm_settings", "local_service_hosts",
     "ALTER TABLE llm_settings ADD COLUMN local_service_hosts JSON NOT NULL DEFAULT '{}'"),
    # M-20260902-a：v0.7.0 商业化批——users 补 admin/邮箱验证/刷新令牌列
    ("users", "is_admin",
     "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"),
    ("users", "email_verified",
     "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"),
    ("users", "refresh_token_hash",
     "ALTER TABLE users ADD COLUMN refresh_token_hash VARCHAR(64)"),
    # M-20260902-b：certificates 补证书×许可分流等级列（P0-1）
    ("certificates", "license_grade",
     "ALTER TABLE certificates ADD COLUMN license_grade VARCHAR(16) NOT NULL DEFAULT ''"),
    # M-20260904-c：v0.8.3 团队空间——works 补共享空间列（FR-13）
    ("works", "space_id", "ALTER TABLE works ADD COLUMN space_id VARCHAR(32)"),
    # M-20260926-c：v0.14.0——subscriptions 记录当前生效 Stripe 订阅 id
    ("subscriptions", "stripe_subscription_id",
     "ALTER TABLE subscriptions ADD COLUMN stripe_subscription_id VARCHAR(120)"),
    # M-20260926-d：v0.14.0——plans 档位配额（并发任务/存储）
    ("plans", "max_concurrent_tasks",
     "ALTER TABLE plans ADD COLUMN max_concurrent_tasks INTEGER"),
    ("plans", "storage_quota_mb",
     "ALTER TABLE plans ADD COLUMN storage_quota_mb INTEGER"),
]


def run(engine: Engine) -> list[str]:
    """执行全部未应用的迁移，返回应用清单（供启动日志与冒烟观测）。"""
    applied: list[str] = []
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        table_cols: dict[str, set[str]] = {}
        for table, column, ddl in _ADD_COLUMNS:
            if table not in table_cols:
                table_cols[table] = {row[1] for row in
                                     conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in table_cols[table]:
                conn.execute(text(ddl))
                applied.append(f"{table}.{column}")

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

        # M-20260902-c：v0.7.0 商业化批——credit_transactions.reason 补 topup（Stripe 充值）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='credit_transactions'")
        ).scalar_one_or_none()
        if ddl and "'topup'" not in ddl:
            _rebuild_table(conn, "credit_transactions", "credit_transactions__v07")
            applied.append("credit_transactions.reason 增加 topup 枚举")

        # M-20260902-d：subscriptions.source 补 stripe（webhook 激活订阅）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='subscriptions'")
        ).scalar_one_or_none()
        if ddl and "'stripe'" not in ddl:
            _rebuild_table(conn, "subscriptions", "subscriptions__v07")
            applied.append("subscriptions.source 增加 stripe 枚举")

        # M-20260904-a：v0.8.0 发行导出预设（FR-11）——tasks.format 补 release、
        # files.kind 补 export_release_zip（两表均带 CHECK 约束，走表重建）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
        ).scalar_one_or_none()
        if ddl and "'release'" not in ddl:
            _rebuild_table(conn, "tasks", "tasks__v08")
            applied.append("tasks.format 增加 release 枚举")
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='files'")
        ).scalar_one_or_none()
        if ddl and "'export_release_zip'" not in ddl:
            _rebuild_table(conn, "files", "files__v08")
            applied.append("files.kind 增加 export_release_zip 枚举")

        # M-20260905-b：v0.10.1 市场——credit_transactions.reason 补 market_sale
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='credit_transactions'")
        ).scalar_one_or_none()
        if ddl and "'market_sale'" not in ddl:
            _rebuild_table(conn, "credit_transactions", "credit_transactions__v101")
            applied.append("credit_transactions.reason 增加 market_sale 枚举")

        # M-20260905-a：v0.9.0 V2 编辑器——versions.source 补 retune/mixdown
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='versions'")
        ).scalar_one_or_none()
        if ddl and "'retune'" not in ddl:
            _rebuild_table(conn, "versions", "versions__v09")
            applied.append("versions.source 增加 retune/mixdown 枚举")

        # M-20260904-b：v0.8.1 人声克隆——candidates.vocal 补 voice_clone（FR-5）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='candidates'")
        ).scalar_one_or_none()
        if ddl and "'voice_clone'" not in ddl:
            _rebuild_table(conn, "candidates", "candidates__v081")
            applied.append("candidates.vocal 增加 voice_clone 枚举")

        # M-20260905-c：v0.10.2 业务可用性批——works.duration CHECK 30~240 → 25~300
        # （本地引擎小节取整实际区间 28.5~252，旧约束使 29s 候选采纳必 500）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='works'")
        ).scalar_one_or_none()
        if ddl and "duration_sec BETWEEN 30 AND 240" in ddl:
            _rebuild_table(conn, "works", "works__v102")
            applied.append("works.duration CHECK 放宽 25~300")

        # M-20260905-e：v0.11.0 /pitch 修调——versions.source 补 pitch_edit
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='versions'")
        ).scalar_one_or_none()
        if ddl and "'pitch_edit'" not in ddl:
            _rebuild_table(conn, "versions", "versions__v011")
            applied.append("versions.source 增加 pitch_edit 枚举")

        # M-20260905-d：v0.10.2 市场——credit_transactions.reason 补 market_purchase
        # （买家扣款与卖家入账区分 reason，账本审计可辨方向）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='credit_transactions'")
        ).scalar_one_or_none()
        if ddl and "'market_purchase'" not in ddl:
            _rebuild_table(conn, "credit_transactions", "credit_transactions__v102")
            applied.append("credit_transactions.reason 增加 market_purchase 枚举")

        # M-20260926-b：v0.14.0——edit_events.action 补支付生命周期枚举
        # （payment_failed / subscription_past_due，dunning 留痕）
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='edit_events'")
        ).scalar_one_or_none()
        if ddl and "'payment_failed'" not in ddl:
            _rebuild_table(conn, "edit_events", "edit_events__v014")
            applied.append("edit_events.action 增加 payment_failed/past_due 枚举")

        # M-20260926-a：v0.14.0 币种统一 USD（P0-5）——存量库 plans 价格从人民币
        # 口径一次性迁到 USD 分值；仅匹配旧值行（运营已自定义改价的行不动），
        # 新库由 seed 直接写 USD。幂等：迁移后再次执行匹配 0 行。
        n1 = conn.execute(text(
            "UPDATE plans SET price_monthly = 799, price_yearly = 639, updated_at = '2026-09-26T00:00:00Z' "
            "WHERE code = 'pro' AND price_monthly = 58")).rowcount
        n2 = conn.execute(text(
            "UPDATE plans SET price_monthly = 2299, price_yearly = 1839, updated_at = '2026-09-26T00:00:00Z' "
            "WHERE code = 'studio' AND price_monthly = 168")).rowcount
        if n1 or n2:
            applied.append(f"plans 价格口径 ¥ → USD 分值（pro x{n1}, studio x{n2}）")
    if applied:
        logger.info(f"sqlite migrations applied: {', '.join(applied)}")
    return applied


def _rebuild_table(conn, table_name: str, tmp_name: str) -> None:
    """标准表重建：建临时表→拷贝→删旧表→改名→补建索引（CHECK 约束/列约束变更走此路径）。"""
    from sqlalchemy.schema import CreateIndex, CreateTable

    from app.models.plan import Subscription
    from app.models.task import File, Task
    from app.models.user import CreditTransaction
    from app.models.work import Candidate, EditEvent, Version, Work

    tables = {"candidates": Candidate.__table__, "tasks": Task.__table__,
              "credit_transactions": CreditTransaction.__table__,
              "subscriptions": Subscription.__table__,
              "files": File.__table__,
              "versions": Version.__table__,
              "works": Work.__table__,
              "edit_events": EditEvent.__table__}
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
