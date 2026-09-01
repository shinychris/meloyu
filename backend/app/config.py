"""应用配置（pydantic-settings）。

价格常量与档位权益数值按架构文档 D11 / §9.1 落 config 常量（不落表）。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

API_PREFIX = "/api/v1"
APP_VERSION = "0.1.0"

# 模型积分单价（架构 §9.1：v1_pro=12、v1_fast=6）
MODEL_CREDIT_COST: dict[str, int] = {"v1_pro": 12, "v1_fast": 6}
# V1.1 派生操作积分单价（extend/variant/regen-section，约为整曲生成一半）
EDIT_OPERATION_CREDIT_COST: dict[str, int] = {"extend": 6, "variant": 6, "regen_section": 6}
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
# 自托管推理服务默认端点（MiniMax Music 3=SGLang-Omni / SongGeneration=Studio model server）
SELFHOSTED_DEFAULT_HOSTS = {"mmax_local": "http://127.0.0.1:8300",
                            "songgen_local": "http://127.0.0.1:42100"}
SELFHOSTED_PROBE_TIMEOUT_SEC = 2.0
# Replicate 官方 API（V1.4 开源模型托管通道；测试连接支持 base 覆盖以便自建代理）
REPLICATE_API_BASE = "https://api.replicate.com"
# 免费档回收站清扫天数
TRASH_RETENTION_DAYS = 30
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
    # HuggingFace 端点覆盖（.env 配 HF_ENDPOINT=https://hf-mirror.com 走国内镜像）
    hf_endpoint: str = ""
    # ACE-Step 独立部署目录（默认 backend/data/acestep：代码+独立 venv+checkpoints，
    # gitignored；其依赖钉死 torch 2.7.1+cu128 与后端 venv 互斥，故隔离部署）
    acestep_home: str = ""

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


settings = Settings()
