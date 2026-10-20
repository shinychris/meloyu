"""模型通道配置与模型操作记录（V1.2「本地开源模型 + 外部 API」批；V1.3 增歌曲通道；
V1.4 增开源歌曲模型目录通道）。

- llm_settings：全局单行（id="global"），歌词引擎与歌曲引擎的后端选择与连接配置；
- model_ops：本地模型下载/删除操作的任务留痕（进度可轮询）。
"""
from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import BaseModel

SETTING_ID = "global"


class LLMSetting(BaseModel):
    """全局模型通道配置（单行）。

    lyrics_backend ∈ localsynth|ollama|openai_compat（V1.2）；
    music_backend ∈ localsynth|api|replicate|musicgen_local
    （V1.3 增 api=Suno 兼容网关；V1.4 增 replicate=Replicate 托管开源模型、
    musicgen_local=本机 MusicGen，二者共用 music_model 从目录选择）。
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
    replicate_api_token: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    music_model: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # Replicate 模型 slug 覆盖（dict[model_id, slug]，社区托管 slug 变动由用户维护）
    replicate_slugs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # 自托管推理服务端点（V1.5.1，dict[channel, base_url]；mmax_local=SGLang-Omni、
    # songgen_local=SongGeneration-Studio，用户在任意环境起服务后在此配置）
    local_service_hosts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LLMSetting backend={self.lyrics_backend}>"


class ModelOp(BaseModel):
    """本地模型操作任务：op_type ∈ pull|delete|music_pull|music_delete|
    acestep_deploy（v0.16.3 增组件部署）；status ∈ queued|running|succeeded|failed。"""

    __tablename__ = "model_ops"
    __table_args__ = (Index("ix_model_ops_status_target", "status", "target"),)

    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    op_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(nullable=False, default=0)
    message: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelOp {self.op_type} {self.target} {self.status} {self.progress}%>"
