"""Pydantic 请求模型（与契约一一对应；响应走 serializers 组装 dict）。"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.core.i18n import tr
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
    # P0-6：email_verification_enabled 开启时必填（6 位数字验证码）
    code: str | None = Field(default=None, max_length=6)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError(tr("email 格式不正确", "invalid email format"))
        return v.lower()

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError(tr("密码须同时包含字母和数字",
                             "password must contain both letters and numbers"))
        return v


class LoginRequest(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError(tr("email 格式不正确", "Invalid email address"))
        return v.lower()


# ---- P1-3 账号体系补全（v0.7.0）----


class RefreshRequest(BaseModel):
    # v0.13.0：refresh 主通道为 HttpOnly Cookie，body 字段降为可选（旧客户端
    # 兼容）；两者皆空时由服务层按无效令牌拒绝（40103）
    refresh_token: str = Field(default="", max_length=128)


class SendCodeRequest(BaseModel):
    email: str = Field(max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError(tr("email 格式不正确", "Invalid email address"))
        return v.lower()


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError(tr("email 格式不正确", "Invalid email address"))
        return v.lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError(tr("密码须同时包含字母和数字",
                             "password must contain both letters and numbers"))
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError(tr("密码须同时包含字母和数字",
                             "password must contain both letters and numbers"))
        return v


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=64)


class KeySchema(BaseModel):
    tonic: str = Field(default="A")
    mode: str = Field(default="minor")

    @field_validator("tonic")
    @classmethod
    def _tonic(cls, v: str) -> str:
        v = v.upper()
        if v not in TONICS:
            raise ValueError(tr(f"tonic 必须为 {TONICS} 之一", f"tonic must be one of {TONICS}"))
        return v

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in KEY_MODES:
            raise ValueError(tr("mode 必须为 major/minor", "mode must be major/minor"))
        return v


class GenerationParams(BaseModel):
    bpm: int = Field(default=90, ge=60, le=174)
    key: KeySchema = Field(default_factory=KeySchema)
    time_signature: str = Field(default="4/4")
    duration_sec: int = Field(default=210, ge=30, le=240)
    vocal: str = Field(default="female_air")
    language: str = Field(default="zh")
    instrument_density: int = Field(default=65, ge=0, le=100)
    # FR-5（v0.8.2）：vocal=voice_clone 时必填（已验证的本人音色档案）
    voice_profile_id: str | None = Field(default=None, max_length=32)
    # v0.11.0 哼唱成歌：[[semi_rel(-24..24), dur_beats(0.25..4)], ...] ≤64 项，
    # 仅本地引擎；来自 POST /hum/analyze 的音高轮廓（前端展示确认后透传）
    hum_melody: list | None = Field(default=None)

    @field_validator("hum_melody")
    @classmethod
    def _hum(cls, v: list | None) -> list | None:
        if v is None:
            return None
        if not 2 <= len(v) <= 64:
            raise ValueError(tr("hum_melody 需为 2~64 个音符",
                            "hum_melody must contain 2-64 notes"))
        for item in v:
            if (not isinstance(item, (list, tuple)) or len(item) != 2
                    or not isinstance(item[0], (int, float)) or not isinstance(item[1], (int, float))):
                raise ValueError(tr("hum_melody 每项须为 [半音, 拍长]",
                                "each hum_melody item must be [semitone, beats]"))
            if not -24 <= item[0] <= 24 or not 0.25 <= item[1] <= 4:
                raise ValueError(tr("hum_melody 半音须 -24~24、拍长须 0.25~4",
                                "hum_melody semitones must be -24 to 24, beats 0.25 to 4"))
        return v

    @field_validator("time_signature")
    @classmethod
    def _ts(cls, v: str) -> str:
        if v not in TIME_SIGNATURES:
            raise ValueError(tr("time_signature 必须为 4/4、3/4、6/8",
                            "time_signature must be 4/4, 3/4 or 6/8"))
        return v

    @field_validator("vocal")
    @classmethod
    def _vocal(cls, v: str) -> str:
        if v not in VOCALS:
            raise ValueError(tr(f"vocal 必须为 {VOCALS} 之一", f"vocal must be one of {VOCALS}"))
        return v

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if v not in LANGUAGES:
            raise ValueError(tr("language 必须为 zh/yue/en/ja", "language must be zh/yue/en/ja"))
        return v


def _check_uuid(v: str | None) -> str | None:
    if v is None:
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{32}", v):
        raise ValueError(tr("id 必须为 32 位 UUID hex", "id must be 32-char UUID hex"))
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
    # FR-4 参考音频（v0.8.1）：特征级参考——分析值覆盖 bpm/调性/器乐密度
    reference_track_id: str | None = Field(default=None, max_length=32)

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in MODES:
            raise ValueError(tr("mode 必须为 simple/custom", "mode must be simple/custom"))
        return v

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        if v not in MODELS:
            raise ValueError(tr("model 必须为 v1_pro/v1_fast", "model must be v1_pro/v1_fast"))
        return v

    @field_validator("work_id", "parent_version_id", "reference_track_id")
    @classmethod
    def _uuids(cls, v: str | None) -> str | None:
        return _check_uuid(v)

    @model_validator(mode="after")
    def _mode_required(self):
        if self.mode == "simple" and not (self.simple_prompt or "").strip():
            raise ValueError(tr("mode=simple 时 simple_prompt 必填",
                            "simple_prompt is required when mode=simple"))
        if self.mode == "custom" and not (self.style_prompt or "").strip():
            raise ValueError(tr("mode=custom 时 style_prompt 必填",
                            "style_prompt is required when mode=custom"))
        return self

    def payload(self) -> dict:
        p = self.params.model_dump()
        return {
            "mode": self.mode, "simple_prompt": self.simple_prompt,
            "style_prompt": self.style_prompt, "lyrics": self.lyrics,
            "negative_prompt": self.negative_prompt, "model": self.model,
            "work_id": self.work_id, "parent_version_id": self.parent_version_id,
            "simplified": self.simplified, "seed": self.seed, "params": p,
            "reference_track_id": self.reference_track_id,
        }


class ReleaseMeta(BaseModel):
    """FR-11 发行导出元数据表单（metadata.json 的 track 段；发行方人工确认项）。"""
    title: str = Field(min_length=1, max_length=80)
    artist: str = Field(min_length=1, max_length=60)
    album: str = Field(default="", max_length=80)
    explicit: bool = False
    language: str = Field(default="", max_length=20)
    genre: str = Field(default="", max_length=30)
    release_date: str = Field(default="", pattern=r"^\d{4}-\d{2}-\d{2}$")
    isrc: str = Field(default="", max_length=15)
    upc: str = Field(default="", max_length=15)
    lyrics_copyright: str = Field(default="", max_length=120)
    songwriter: str = Field(default="", max_length=120)
    # v0.11.0 自定义封面：PNG base64（解码后 ≤4MB、≥600x600；缺省用系统占位图）
    cover_png_b64: str | None = Field(default=None, max_length=6_000_000)


class ExportRequest(BaseModel):
    version_id: str
    format: str
    # FR-11 发行导出预设：format=release 时必填 platform（douyin/streaming），
    # meta 为发行元数据表单（缺省 title/artist 由作品标题/账号邮箱前缀兜底）
    # validate_default：platform 缺省也要跑校验（release 时 None 必须报错）
    platform: str | None = Field(default=None, validate_default=True)
    meta: ReleaseMeta | None = None

    @field_validator("format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        if v not in ("mp3", "wav", "midi", "stems", "release"):
            raise ValueError(tr("format 必须为 mp3/wav/midi/stems/release",
                            "format must be mp3/wav/midi/stems/release"))
        return v

    @field_validator("platform")
    @classmethod
    def _platform(cls, v: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("format") == "release":
            if v not in ("douyin", "streaming"):
                raise ValueError(tr("format=release 时 platform 必须为 douyin/streaming",
                                "platform must be douyin/streaming when format=release"))
        elif v:
            raise ValueError(tr("platform 仅在 format=release 时允许",
                            "platform is only allowed when format=release"))
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


class RetuneRequest(BaseModel):
    """V2 编辑器（v0.9.0）：变速/变调——至少一项（确定性同 seed 重渲染）。"""
    bpm: int | None = Field(default=None, ge=60, le=174)
    key: KeySchema | None = None


class NoteEdit(BaseModel):
    """单条音符编辑：beat=词谱绝对拍号（0.001 精度），semi=移调半音数。"""
    beat: float = Field(ge=0, le=10000)
    semi: int = Field(ge=-12, le=12)


class PitchEditRequest(BaseModel):
    """V2 /pitch 修调（v0.11.0）：音符级移调 + 可选节奏量化（确定性重渲染）。"""
    edits: list[NoteEdit] = Field(min_length=1, max_length=200)
    quantize: str = "off"

    @field_validator("quantize")
    @classmethod
    def _q(cls, v: str) -> str:
        if v not in ("off", "8", "16"):
            raise ValueError(tr("quantize 必须为 off/8/16", "quantize must be off/8/16"))
        return v

    def payload(self) -> list[dict]:
        return [{"beat": e.beat, "semi": e.semi} for e in self.edits]


class RegenSectionRequest(BaseModel):
    """契约 v1.2 §5.7：仅重生成指定段落的第 occurrence 次出现（1 起始，默认 1）。"""
    section: str
    occurrence: int = Field(default=1, ge=1)

    @field_validator("section")
    @classmethod
    def _sec(cls, v: str) -> str:
        if v not in SECTIONS:
            raise ValueError(tr(f"section 必须为 {SECTIONS} 之一",
                            f"section must be one of {SECTIONS}"))
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
            raise ValueError(tr("plan 必须为 free/pro/studio/team",
                            "plan must be free/pro/studio/team"))
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
            raise ValueError(tr("tags 最多 8 个", "at most 8 tags"))
        for t in v:
            if not (1 <= len(t) <= 12):
                raise ValueError(tr("每个 tag 长度须为 1~12 字",
                            "each tag must be 1-12 characters"))
        return v

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.title is None and self.tags is None and self.favorite is None:
            raise ValueError(tr("至少传入一个待更新字段",
                            "provide at least one field to update"))
        return self


class LyricGenerateRequest(BaseModel):
    # v0.12.3：theme 升级为「创作想法」，容纳多行故事/画面描述
    theme: str = Field(min_length=1, max_length=600)
    style_hint: str = Field(default="", max_length=100)
    mood: str | None = Field(default=None, max_length=50)
    language: str = Field(default="zh")
    sections: list[str] | None = None

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if v not in ("zh", "en"):
            raise ValueError(tr("language 必须为 zh/en", "language must be zh/en"))
        return v

    @field_validator("sections")
    @classmethod
    def _sections(cls, v: list[str] | None):
        if v is None:
            return None
        if len(v) > 12:
            raise ValueError(tr("sections 最多 12 段", "at most 12 sections"))
        for s in v:
            if s not in SECTIONS:
                raise ValueError(tr(f"section 必须为 {SECTIONS} 之一", f"section must be one of {SECTIONS}"))
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
            raise ValueError(tr(f"target_section 必须为 {SECTIONS} 之一",
                            f"target_section must be one of {SECTIONS}"))
        return v

    @field_validator("locked_lines")
    @classmethod
    def _locked(cls, v: list[int] | None):
        if v is None:
            return None
        if any(n < 1 for n in v):
            raise ValueError(tr("locked_lines 为全局 1 起始行号",
                            "locked_lines are 1-based global line numbers"))
        return v


class LyricTextRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=4000)
