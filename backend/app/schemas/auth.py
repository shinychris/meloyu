"""Pydantic 请求模型（与契约一一对应；响应走 serializers 组装 dict）。"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    KEY_MODES,
    LANGUAGES,
    MODELS,
    MODES,
    SECTIONS,
    TIME_SIGNATURES,
    TONICS,
    VOCALS,
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class RegisterRequest(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=24)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("email 格式不正确")
        return v.lower()

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密码须同时包含字母和数字")
        return v


class LoginRequest(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("email 格式不正确")
        return v.lower()


class KeySchema(BaseModel):
    tonic: str = Field(default="A")
    mode: str = Field(default="minor")

    @field_validator("tonic")
    @classmethod
    def _tonic(cls, v: str) -> str:
        v = v.upper()
        if v not in TONICS:
            raise ValueError(f"tonic 必须为 {TONICS} 之一")
        return v

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in KEY_MODES:
            raise ValueError("mode 必须为 major/minor")
        return v


class GenerationParams(BaseModel):
    bpm: int = Field(default=90, ge=60, le=174)
    key: KeySchema = Field(default_factory=KeySchema)
    time_signature: str = Field(default="4/4")
    duration_sec: int = Field(default=210, ge=30, le=240)
    vocal: str = Field(default="female_air")
    language: str = Field(default="zh")
    instrument_density: int = Field(default=65, ge=0, le=100)

    @field_validator("time_signature")
    @classmethod
    def _ts(cls, v: str) -> str:
        if v not in TIME_SIGNATURES:
            raise ValueError("time_signature 必须为 4/4、3/4、6/8")
        return v

    @field_validator("vocal")
    @classmethod
    def _vocal(cls, v: str) -> str:
        if v not in VOCALS:
            raise ValueError(f"vocal 必须为 {VOCALS} 之一")
        return v

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if v not in LANGUAGES:
            raise ValueError("language 必须为 zh/yue/en/ja")
        return v


def _check_uuid(v: str | None) -> str | None:
    if v is None:
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{32}", v):
        raise ValueError("id 必须为 32 位 UUID hex")
    return v.lower()


class GenerationRequest(BaseModel):
    mode: str
    simple_prompt: str | None = Field(default=None, max_length=200)
    style_prompt: str | None = Field(default=None, max_length=500)
    lyrics: str | None = Field(default=None, max_length=4000)
    negative_prompt: str = Field(default="", max_length=100)
    model: str = Field(default="v1_pro")
    work_id: str | None = None
    parent_version_id: str | None = None
    simplified: bool = False
    seed: int | None = Field(default=None, ge=0, le=4294967295)
    params: GenerationParams = Field(default_factory=GenerationParams)

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in MODES:
            raise ValueError("mode 必须为 simple/custom")
        return v

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        if v not in MODELS:
            raise ValueError("model 必须为 v1_pro/v1_fast")
        return v

    @field_validator("work_id", "parent_version_id")
    @classmethod
    def _uuids(cls, v: str | None) -> str | None:
        return _check_uuid(v)

    @model_validator(mode="after")
    def _mode_required(self):
        if self.mode == "simple" and not (self.simple_prompt or "").strip():
            raise ValueError("mode=simple 时 simple_prompt 必填")
        if self.mode == "custom" and not (self.style_prompt or "").strip():
            raise ValueError("mode=custom 时 style_prompt 必填")
        return self

    def payload(self) -> dict:
        p = self.params.model_dump()
        return {
            "mode": self.mode, "simple_prompt": self.simple_prompt,
            "style_prompt": self.style_prompt, "lyrics": self.lyrics,
            "negative_prompt": self.negative_prompt, "model": self.model,
            "work_id": self.work_id, "parent_version_id": self.parent_version_id,
            "simplified": self.simplified, "seed": self.seed, "params": p,
        }


class ExportRequest(BaseModel):
    version_id: str
    format: str

    @field_validator("format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        if v not in ("mp3", "wav", "midi", "stems"):
            raise ValueError("format 必须为 mp3/wav/midi/stems")
        return v

    @field_validator("version_id")
    @classmethod
    def _vid(cls, v: str) -> str:
        return _check_uuid(v)


class ExtendRequest(BaseModel):
    """契约 §5.5：从候选结尾续写 15~60 秒。"""
    seconds: int = Field(ge=15, le=60)


class VariantRequest(BaseModel):
    """契约 §5.6：同结构换编曲风格（style_prompt ≤500 字）。"""
    style_prompt: str = Field(min_length=1, max_length=500)


class RegenSectionRequest(BaseModel):
    """契约 §5.7：仅重生成指定段落（section 枚举，须存在于候选 structure）。"""
    section: str

    @field_validator("section")
    @classmethod
    def _sec(cls, v: str) -> str:
        if v not in SECTIONS:
            raise ValueError(f"section 必须为 {SECTIONS} 之一")
        return v


class LyricDraftRequest(BaseModel):
    """V1.1 歌词草稿云端持久化（单用户单草稿）。"""
    text: str = Field(default="", max_length=4000)


class SwitchPlanRequest(BaseModel):
    plan: str

    @field_validator("plan")
    @classmethod
    def _plan(cls, v: str) -> str:
        if v not in ("free", "pro", "studio", "team"):
            raise ValueError("plan 必须为 free/pro/studio/team")
        return v


class WorkPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=50)
    tags: list[str] | None = None
    favorite: bool | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None):
        if v is None:
            return None
        if len(v) > 8:
            raise ValueError("tags 最多 8 个")
        for t in v:
            if not (1 <= len(t) <= 12):
                raise ValueError("每个 tag 长度须为 1~12 字")
        return v

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.title is None and self.tags is None and self.favorite is None:
            raise ValueError("至少传入一个待更新字段")
        return self


class LyricGenerateRequest(BaseModel):
    theme: str = Field(min_length=1, max_length=100)
    style_hint: str = Field(default="", max_length=100)
    mood: str | None = Field(default=None, max_length=50)
    language: str = Field(default="zh")
    sections: list[str] | None = None

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if v not in ("zh", "en"):
            raise ValueError("language 必须为 zh/en")
        return v

    @field_validator("sections")
    @classmethod
    def _sections(cls, v: list[str] | None):
        if v is None:
            return None
        if len(v) > 12:
            raise ValueError("sections 最多 12 段")
        for s in v:
            if s not in SECTIONS:
                raise ValueError(f"section 必须为 {SECTIONS} 之一")
        return v


class LyricPolishRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=4000)
    target_section: str | None = None
    style_hint: str = Field(default="", max_length=100)
    locked_lines: list[int] | None = None

    @field_validator("target_section")
    @classmethod
    def _sec(cls, v: str | None):
        if v is not None and v not in SECTIONS:
            raise ValueError(f"target_section 必须为 {SECTIONS} 之一")
        return v

    @field_validator("locked_lines")
    @classmethod
    def _locked(cls, v: list[int] | None):
        if v is None:
            return None
        if any(n < 1 for n in v):
            raise ValueError("locked_lines 为全局 1 起始行号")
        return v


class LyricTextRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=4000)
