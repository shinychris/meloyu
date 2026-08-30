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
# 注册赠送积分
SIGNUP_BONUS_CREDITS = 200
# 任务超时熔断（秒）：单候选渲染超过该值中止并退款（架构 §7.9 为 70s，留余量取整任务 90s）
GENERATION_TASK_TIMEOUT_SEC = 180
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
    music_provider: str = "localsynth"
    cors_origins: str = "http://localhost:5173"

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


settings = Settings()
