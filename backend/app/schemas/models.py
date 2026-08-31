"""模型中心请求模型（契约 v1.3 §5.8）。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.providers.lyrics_llm import valid_model_tag


class ModelPullRequest(BaseModel):
    """POST /models/pull：从 Ollama 仓库拉取本地模型。"""
    model: str = Field(min_length=1, max_length=100)

    @field_validator("model")
    @classmethod
    def _tag(cls, v: str) -> str:
        v = v.strip()
        if not valid_model_tag(v):
            raise ValueError("模型 tag 格式不合法（允许字母数字与 . _ : @ / + -）")
        return v


class ModelDeleteRequest(ModelPullRequest):
    """POST /models/delete：删除本地模型（选用中被删则引擎自动回退）。"""


class LLMSettingsRequest(BaseModel):
    """PUT /models/settings：切换引擎通道与连接配置（*_api_key 空串=保持不变）。

    V1.3 新增歌曲生成通道：music_backend ∈ localsynth|api（api=Suno 兼容外部歌曲 API）。
    """
    lyrics_backend: str | None = None
    ollama_host: str | None = Field(default=None, max_length=200)
    ollama_model: str | None = Field(default=None, max_length=120)
    external_base_url: str | None = Field(default=None, max_length=300)
    external_model: str | None = Field(default=None, max_length=120)
    external_api_key: str | None = Field(default=None, max_length=300)
    music_backend: str | None = None
    music_api_base_url: str | None = Field(default=None, max_length=300)
    music_api_model: str | None = Field(default=None, max_length=120)
    music_api_key: str | None = Field(default=None, max_length=300)

    @field_validator("lyrics_backend")
    @classmethod
    def _backend(cls, v: str | None) -> str | None:
        if v is not None and v not in ("localsynth", "ollama", "openai_compat"):
            raise ValueError("lyrics_backend 必须为 localsynth/ollama/openai_compat")
        return v

    @field_validator("music_backend")
    @classmethod
    def _music_backend(cls, v: str | None) -> str | None:
        if v is not None and v not in ("localsynth", "api"):
            raise ValueError("music_backend 必须为 localsynth/api")
        return v


class ExternalTestRequest(BaseModel):
    """POST /models/test-external：OpenAI 兼容端点连通性测试（不落库）。"""
    base_url: str = Field(min_length=1, max_length=300)
    api_key: str = Field(default="", max_length=300)
    model: str = Field(min_length=1, max_length=120)


class MusicTestRequest(BaseModel):
    """POST /models/test-music：Suno 兼容歌曲 API 端点探活（不落库）。"""
    base_url: str = Field(min_length=1, max_length=300)
    api_key: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)
