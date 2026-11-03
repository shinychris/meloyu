"""模型中心请求模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.i18n import tr
from app.providers.lyrics_llm import valid_model_tag


class ModelPullRequest(BaseModel):
    """POST /models/pull：从 Ollama 仓库拉取本地模型。"""
    model: str = Field(min_length=1, max_length=100)

    @field_validator("model")
    @classmethod
    def _tag(cls, v: str) -> str:
        v = v.strip()
        if not valid_model_tag(v):
            raise ValueError(tr("模型 tag 格式不合法（允许字母数字与 . _ : @ / + -）",
                          "invalid model tag (allowed: alphanumerics and . _ : @ / + -)"))
        return v


class ModelDeleteRequest(ModelPullRequest):
    """POST /models/delete：删除本地模型（选用中被删则引擎自动回退）。"""


class LLMSettingsRequest(BaseModel):
    """PUT /models/settings：切换引擎通道与连接配置（*_api_key/token 空串=保持不变）。

    V1.3 新增歌曲生成通道：music_backend ∈ localsynth|api；
    V1.4 扩展：music_backend 增 replicate|musicgen_local（开源模型目录通道，
    music_model 为目录模型 id；replicate_slugs 覆盖目录默认 slug）。
    V1.5 扩展：music_backend 增 acestep_local（本机 ACE-Step v1.5 人声成曲）。
    V1.5.1 扩展：music_backend 增 mmax_local|songgen_local（自托管推理服务通道，
    local_service_hosts 配置端点）。
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
    music_model: str | None = Field(default=None, max_length=60)
    replicate_api_token: str | None = Field(default=None, max_length=300)
    replicate_slugs: dict[str, str] | None = None
    local_service_hosts: dict[str, str] | None = None

    @field_validator("lyrics_backend")
    @classmethod
    def _backend(cls, v: str | None) -> str | None:
        if v == "localsynth":  # 历史遗留值（原离线规则引擎通道，已移除）→ 未配置
            return "none"
        if v is not None and v not in ("none", "ollama", "openai_compat"):
            raise ValueError(tr("lyrics_backend 必须为 none/ollama/openai_compat",
                                "lyrics_backend must be none/ollama/openai_compat"))
        return v

    @field_validator("music_backend")
    @classmethod
    def _music_backend(cls, v: str | None) -> str | None:
        if v is not None and v not in (
                "localsynth", "api", "replicate", "musicgen_local", "acestep_local",
                "mmax_local", "songgen_local"):
            raise ValueError(tr("music_backend 必须为 localsynth/api/replicate/"
                             "musicgen_local/acestep_local/mmax_local/songgen_local",
                             "music_backend must be localsynth/api/replicate/"
                             "musicgen_local/acestep_local/mmax_local/songgen_local"))
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


class ReplicateTestRequest(BaseModel):
    """POST /models/test-replicate：Replicate Token 校验 + 可选模型存在性（不落库）。"""
    api_token: str = Field(min_length=1, max_length=300)
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)


class CatalogModelRequest(BaseModel):
    """POST /models/music-pull | /models/music-delete：目录模型 id（如 musicgen-small）。"""
    model: str = Field(min_length=1, max_length=60)
