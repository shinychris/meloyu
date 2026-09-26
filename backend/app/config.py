"""应用配置（pydantic-settings）。

价格常量与档位权益数值按架构文档 D11 / §9.1 落 config 常量（不落表）。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

API_PREFIX = "/api/v1"
APP_VERSION = "0.13.0"

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
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"
    # 运行环境：dev（默认，本地开发）| production（启用生产断言：弱密钥拒启动、
    # 禁 demo 播种、关闭 /api/docs；见 main.py _assert_production）
    env: str = "dev"
    # 是否信任反代注入的客户端 IP 头（X-Real-IP / X-Forwarded-For）。
    # false：限流一律按 TCP 对端地址计数（直连部署防 XFF 伪造绕过）；
    # true：仅当部署在自有反代（如 deploy/nginx.conf）之后时开启——优先取
    # X-Real-IP（nginx 以 $remote_addr 覆写，客户端不可伪造），退取 XFF 链尾
    # （最近一跳可信代理追加的真实 IP），二者皆取链首以外的值，防伪造。
    trust_proxy: bool = False
    # dev 环境是否放行非回环来源请求（LAN 联调用；默认拒绝——demo 固定密码
    # 种子账号/开放 /api/docs 只应本机可达，见 main.py dev 来源守卫）
    allow_lan_dev: bool = False
    # ---- Stripe 支付（D-2 决策：海外市场 Stripe；未配置时付费档不可订阅）----
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # 对外可达基础 URL（Checkout 回跳/门户跳转用；如 https://app.meloyu.example）
    app_base_url: str = "http://localhost:5173"
    # 订阅价格 ID（Stripe Dashboard 创建后填入；月/年 x pro/studio）
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_yearly: str = ""
    stripe_price_studio_monthly: str = ""
    stripe_price_studio_yearly: str = ""
    # 积分充值包（一次性）：金额美分 → 积分（默认值可按运营调整）
    stripe_topup_price: str = ""
    stripe_topup_amount_usd: int = 999   # $9.99
    stripe_topup_credits: int = 1000
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
    # 人声克隆同人校验余弦阈值（FR-5；0=用服务默认 0.55，运营可调）
    voice_verify_threshold: float = 0
    # 数据盘最低剩余空间（GB）：生成/导出/上传入口的前置水位线（P0-9），低于即拒绝
    disk_min_free_gb: float = 10.0
    # 账号维度每小时生成任务上限（P1-7：叠加在 IP 限流之上，防付费账号直刷/脚本刷量）
    account_generation_hourly_limit: int = 30
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
    # MiniMax Music 3 本机 audio.cpp 部署目录（默认 backend/data/audiocpp：CLI+
    # GGUF 权重，gitignored；.env 可覆盖）
    audiocpp_home: str = ""

    @property
    def data_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).resolve()
        return (BACKEND_DIR / "data").resolve()

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
