"""模型通道配置与模型操作记录（V1.2「本地开源模型 + 外部 API」批；V1.3 增歌曲通道）。

- llm_settings：全局单行（id="global"），歌词引擎与歌曲引擎的后端选择与连接配置；
- model_ops：本地模型下载/删除操作的任务留痕（进度可轮询）。
"""
from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel

SETTING_ID = "global"


class LLMSetting(BaseModel):
    """全局模型通道配置（单行）。

    lyrics_backend ∈ localsynth|ollama|openai_compat（V1.2）；
    music_backend ∈ localsynth|api（V1.3：api=外部歌曲生成 API，Suno 兼容协议）。
    """

    __tablename__ = "llm_settings"

    lyrics_backend: Mapped[str] = mapped_column(String(16), nullable=False, default="localsynth")
    ollama_host: Mapped[str] = mapped_column(String(200), nullable=False,
                                             default="http://localhost:11434")
    ollama_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    external_base_url: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    external_api_key: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    external_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    music_backend: Mapped[str] = mapped_column(String(16), nullable=False, default="localsynth")
    music_api_base_url: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    music_api_key: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    music_api_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LLMSetting backend={self.lyrics_backend}>"


class ModelOp(BaseModel):
    """本地模型操作任务：op_type ∈ pull|delete；status ∈ queued|running|succeeded|failed。"""

    __tablename__ = "model_ops"
    __table_args__ = (Index("ix_model_ops_status_target", "status", "target"),)

    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    op_type: Mapped[str] = mapped_column(String(8), nullable=False)
    target: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(nullable=False, default=0)
    message: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelOp {self.op_type} {self.target} {self.status} {self.progress}%>"
