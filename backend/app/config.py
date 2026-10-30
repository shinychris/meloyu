"""应用配置（pydantic-settings）。

价格常量与档位权益数值按架构文档 D11 / §9.1 落 config 常量（不落表）。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

API_PREFIX = "/api/v1"
APP_VERSION = "0.17.1"

# ---- 买断制定价（D-1 定案，USD 分值；与前端 landing LICENSE_SKU / portal 一致）----
# 原价锚 $399（划线展示）+ 折扣成交价；折扣支持：SALE ≥ PRICE 或非正时
# 前端自动回退单价格局（env 调整 LICENSE_SALE_PRICE_USD 即可开关/改折扣）
LICENSE_PRICE_USD = 39900        # $399 终身授权（原价锚）
LICENSE_SALE_PRICE_USD = 12900   # 限时买断价 $129（2026-10-17 起，原首发 $159）
# 桌面版试用期天数（D-2：无免费层，14 天全功能试用）
LICENSE_TRIAL_DAYS = 14

# 模型积分单价（架构 §9.1：v1_pro=12、v1_fast=6）
MODEL_CREDIT_COST: dict[str, int] = {"v1_pro": 12, "v1_fast": 6}
# V1.1 派生操作积分单价（extend/variant/regen-section，约为整曲生成一半）
EDIT_OPERATION_CREDIT_COST: dict[str, int] = {"extend": 6, "variant": 6, "regen_section": 6,
                                               "retune": 6, "pitch_edit": 6}
# 注册赠送积分
SIGNUP_BONUS_CREDITS = 200
# 任务超时熔断（秒）：单候选渲染超过该值中止并退款（架构 §7.9 为 70s，留余量取整任务 90s）
GENERATION_TASK_TIMEOUT_SEC = 180
# 外部歌曲 API 通道的任务超时（秒）：云端整曲生成实测 1~5 分钟（ADR-010）
MUSIC_API_TASK_TIMEOUT_SEC = 900
# 本机 MusicGen 通道的任务超时（秒）：CPU 上 30s 器乐约 2~6 分钟（small），留足余量
MUSICGEN_TASK_TIMEOUT_SEC = 1800
# 本机 ACE-Step 通道的任务超时（秒）：GPU turbo 档 1~3 分钟/首，首次含 venv 冷启动留余量
ACESTEP_TASK_TIMEOUT_SEC = 1800
# 自托管推理服务通道（V1.5.1，ADR-017）的任务超时：大模型 CPU offload / 双卡服务不确定度高，留足
SELFHOSTED_TASK_TIMEOUT_SEC = 1800
# MiniMax Music 3 本机 audio.cpp 形态超时：Q4 量化 4060 Ti 实测 RTF~94（10s 曲约 16 分钟，
# 双候选 30 分钟+），按双候选 300s 曲上限放宽
AUDIOCPP_TASK_TIMEOUT_SEC = 4 * 3600
# 自托管推理服务默认端点（MiniMax Music 3=SGLang-Omni / SongGeneration=Studio model server）
SELFHOSTED_DEFAULT_HOSTS = {"mmax_local": "http://127.0.0.1:8300",
                            "songgen_local": "http://127.0.0.1:42100"}
SELFHOSTED_PROBE_TIMEOUT_SEC = 2.0
# Replicate 官方 API（V1.4 开源模型托管通道；测试连接支持 base 覆盖以便自建代理）
REPLICATE_API_BASE = "https://api.replicate.com"
# 免费档回收站清扫天数
TRASH_RETENTION_DAYS = 30
# 导出任务软超时（秒）：导出阶段边界检查，超时判失败（P1-10；导出已隔离到
# 独立单 worker 池，最坏只影响后续导出排队，不拖累生成通道）
EXPORT_TASK_TIMEOUT_SEC = 600
# stream-token 有效期（秒）
STREAM_TOKEN_TTL_SEC = 900


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    jwt_secret: str = "meloyu-dev-secret-do-not-use-in-production"
    server_nonce: str = "meloyu-local-nonce-v1"
    data_dir: str = ""
    # 主数据库连接串（v0.15.0 起生产环境为 PostgreSQL）：
    #   本地 Docker 栈：postgresql+psycopg2://meloyu:<密码>@postgres:5432/meloyu
    #   Supabase（事务池化端口 6543，走 pgBouncer；psycopg2 无服务端预编译语句，
    #   与 transaction mode 兼容）：
    #     postgresql+psycopg2://postgres.<ref>:<密码>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
    #   Supabase（直连 5432，仅迁移/一次性作业用）：
    #     postgresql+psycopg2://postgres.<ref>:<密码>@db.<ref>.supabase.co:5432/postgres?sslmode=require
    # 空 = 回退 SQLite 文件（data_path/meloyu.db，仅限本机开发/测试；生产启动断言强制 PG）
    database_url: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"
    # 运行环境：dev（默认，本地开发）| production（启用生产断言：弱密钥拒启动、
    # 禁 demo 播种、关闭 /api/docs；见 main.py _assert_production）
    env: str = "dev"
    # 产品形态（2026-10-03 定位转型，D-1~D-7）：
    #   cloud      —— 云端 SaaS 形态（存量，转型过渡期保留）
    #   desktop    —— 桌面单机版 sidecar：SQLite、单用户短路、试用期+License 激活、
    #                 积分转纯计量、托管前端静态文件
    #   enterprise —— 企业私有化部署：多用户 + PG（生产断言照常）+ 启动时校验 License
    app_mode: str = "cloud"
    # 是否信任反代注入的客户端 IP 头（X-Real-IP / X-Forwarded-For）。
    # false：限流一律按 TCP 对端地址计数（直连部署防 XFF 伪造绕过）；
    # true：仅当部署在自有反代（如 deploy/nginx.conf）之后时开启——优先取
    # X-Real-IP（nginx 以 $remote_addr 覆写，客户端不可伪造），退取 XFF 链尾
    # （最近一跳可信代理追加的真实 IP），二者皆取链首以外的值，防伪造。
    trust_proxy: bool = False
    # dev 环境是否放行非回环来源请求（LAN 联调用；默认拒绝——demo 固定密码
    # 种子账号/开放 /api/docs 只应本机可达，见 main.py dev 来源守卫）
    allow_lan_dev: bool = False
    # ---- License（买断制，desktop/enterprise 形态）----
    # Ed25519 公钥（base64，32 字节原始公钥）；空 = License 激活不可用（dev 默认）。
    # keypair 生成：python -m scripts.license_tools keygen
    license_public_key: str = ""
    # enterprise 形态启动必须携带的 License Key（env MELOYU_LICENSE_KEY）
    meloyu_license_key: str = ""
    # 桌面壳托管的 SPA 静态目录（默认 <repo>/frontend/dist；打包时由壳注入）
    desktop_static_dir: str = ""
    # License Portal（在线激活码兑换端点；激活成功后本地持有签名密钥，离线可用）
    portal_base_url: str = "https://meloyu.com"
    portal_activate_timeout_sec: float = 15.0
    # 对外可达基础 URL（密码重置邮件链接用；如 https://www.meloyu.com）
    app_base_url: str = "http://localhost:5173"
    # ---- SMTP 邮件（找回密码/注册验证码；未配置 host 时相关功能禁用）----
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Meloyu <no-reply@meloyu.example>"
    email_verification_enabled: bool = False
    # ---- 安全/加密 ----
    # llm_settings API Key 落库加密密钥（Fernet，32 字节 base64）；空 = 明文存储（dev）
    key_encryption_secret: str = ""
    # 注册时自动授予管理员角色的邮箱（逗号分隔；模型中心写操作需 admin）
    admin_emails: str = ""
    # ---- 监控 ----
    sentry_dsn: str = ""
    # 人声克隆同人校验余弦阈值（FR-5；0=用服务默认 0.9——services/voice.py
    # DEFAULT_VERIFY_THRESHOLD，实测同人≈1.0 / 异人≤0.84；运营可调）
    voice_verify_threshold: float = 0
    # 数据盘最低剩余空间（GB）：生成/导出/上传入口的前置水位线（P0-9），低于即拒绝
    disk_min_free_gb: float = 10.0
    # 账号维度每小时生成任务上限（P1-7：叠加在 IP 限流之上，防付费账号直刷/脚本刷量）
    account_generation_hourly_limit: int = 30
    # 维护模式（P1-13）：true 时生成/派生/导出提交一律 50301 拒绝（发布窗口防新任务
    # 进队列被重启杀掉）；.env 置 MAINTENANCE_MODE=true 后 up -d 生效
    maintenance_mode: bool = False
    # MiniMax-Music3 商用开放开关（义务①署名/②防侵权防护/③AUP 披露已落实，默认开放；
    # 条款修订或营收接近 $20M 门槛时置 false 回退非商用签发）
    mmax_commercial_enabled: bool = True
    # 团队版联系邮箱（v0.11.0：空=不展示联系方式，团队档按钮保持提示口径）
    sales_contact_email: str = ""
    # HuggingFace 端点覆盖（.env 配 HF_ENDPOINT=https://hf-mirror.com 走国内镜像）
    hf_endpoint: str = ""
    # ACE-Step 独立部署目录（默认 backend/data/acestep：代码+独立 venv+checkpoints，
    # gitignored；其依赖钉死 torch 2.7.1+cu128 与后端 venv 互斥，故隔离部署）
    acestep_home: str = ""
    # desktop 形态首启自动部署 ACE-Step 组件（v0.16.3：默认安装即部署完成——
    # 完整应用开箱体验；env ACESTEP_AUTO_DEPLOY=false 关闭，改为组件中心手动触发）
    acestep_auto_deploy: bool = True
    # MiniMax Music 3 本机 audio.cpp 部署目录（默认 backend/data/audiocpp：CLI+
    # GGUF 权重，gitignored；.env 可覆盖）
    audiocpp_home: str = ""

    @property
    def billing_mode(self) -> str:
        """商业化模式：license（买断制，desktop/enterprise）| subscription（云端订阅，存量）。"""
        return "license" if self.app_mode in ("desktop", "enterprise") else "subscription"

    @property
    def data_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).resolve()
        # 桌面形态默认数据目录迁至用户主目录（B9：随包只带代码不带数据）
        if self.app_mode == "desktop":
            return (Path.home() / "Meloyu").resolve()
        return (BACKEND_DIR / "data").resolve()

    @property
    def static_path(self) -> Path | None:
        """桌面壳 SPA 静态目录（B8：sidecar 同源托管前端；不存在返回 None）。"""
        raw = self.desktop_static_dir or str(REPO_DIR / "frontend" / "dist")
        p = Path(raw)
        return p.resolve() if p.is_dir() else None

    @property
    def db_path(self) -> Path:
        return self.data_path / "meloyu.db"

    @property
    def audio_path(self) -> Path:
        return self.data_path / "audio"

    @property
    def acestep_path(self) -> Path:
        if self.acestep_home:
            return Path(self.acestep_home).resolve()
        return self.data_path / "acestep"

    @property
    def audiocpp_path(self) -> Path:
        if self.audiocpp_home:
            return Path(self.audiocpp_home).resolve()
        return self.data_path / "audiocpp"


settings = Settings()
