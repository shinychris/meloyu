"""系统路由（2 接口，无鉴权）。meta 标签按请求 Accept-Language 输出（zh/en）。"""
from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import APP_VERSION, EDIT_OPERATION_CREDIT_COST, MODEL_CREDIT_COST
from app.core.i18n import tr
from app.core.responses import ok
from app.database import get_db
from app.models import File, Task
from app.models.enums import LANGUAGES, TIME_SIGNATURES, TONICS

router = APIRouter(prefix="/system", tags=["system"])

_STARTED_AT = time.time()

# (zh, en) 双语标签；输出经 tr() 按当前 locale 取值
_VOCAL_LABELS = {
    "female_air": ("女声 · 气声", "Female · breathy"),
    "female_bright": ("女声 · 清亮", "Female · bright"),
    "female_deep": ("女声 · 浑厚", "Female · deep"),
    "male_magnetic": ("男声 · 磁性", "Male · magnetic"),
    "male_clear": ("男声 · 清朗", "Male · clear"),
    "choir": ("合唱", "Choir"),
    "instrumental": ("纯器乐", "Instrumental"),
    # FR-5（v0.8.2）：本人音色档案（需已验证 voice_profile_id，仅本地引擎）
    "voice_clone": ("我的音色（已验证）", "My voice (verified)"),
}
_LANG_LABELS = {"zh": ("中文（普通话）", "Chinese (Mandarin)"), "yue": ("粤语", "Cantonese"),
                "en": ("英语", "English"), "ja": ("日语", "Japanese")}
_TONIC_ZH = {"C": "C", "C#": "升C", "D": "D", "D#": "升D", "E": "E", "F": "F", "F#": "升F",
             "G": "G", "G#": "升G", "A": "A", "A#": "升A", "B": "B"}

_SCENES = (("短视频 BGM", "Short-video BGM"), ("广告片", "Ad film"),
           ("游戏配乐", "Game score"), ("个人单曲", "Solo single"))
_MOODS = (("治愈", "Healing"), ("忧郁", "Melancholy"), ("热血", "Energetic"),
          ("浪漫", "Romantic"), ("紧张", "Tense"))
_GENRES = (("华语流行", "Mandopop"), ("国风", "Chinese traditional"), ("嘻哈", "Hip-hop"),
           ("EDM", "EDM"), ("Lo-fi", "Lo-fi"), ("摇滚", "Rock"), ("民谣", "Folk"),
           ("R&B", "R&B"))
_INSTRUMENTS = (("钢琴", "Piano"), ("吉他", "Guitar"), ("弦乐", "Strings"),
                ("古筝", "Guzheng"), ("合成器", "Synth"), ("808", "808"))


@router.get("/health")
def health(db: Session = Depends(get_db)):
    tasks_running = db.execute(select(func.count()).select_from(Task)
                               .where(Task.status == "running")).scalar_one()
    audio_files = db.execute(select(func.count()).select_from(File)).scalar_one()
    return ok({
        "status": "ok",
        "version": APP_VERSION,
        "uptime_sec": int(time.time() - _STARTED_AT),
        "db": "ok",
        "tasks_running": tasks_running,
        "audio_files": audio_files,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


@router.get("/meta")
def meta():
    keys = []
    for mode_chunk in (list(zip(TONICS, ["major"] * 12, strict=True)) + list(zip(TONICS, ["minor"] * 12, strict=True))):
        tonic, mode = mode_chunk
        zh_label = f"{_TONIC_ZH[tonic]}{'大调' if mode == 'major' else '小调'}"
        en_label = f"{tonic} {'Major' if mode == 'major' else 'Minor'}"
        keys.append({"tonic": tonic, "mode": mode, "label": tr(zh_label, en_label)})
    keys.sort(key=lambda k: (k["mode"], TONICS.index(k["tonic"])))
    return ok({
        "models": [
            {"value": "v1_pro", "label": tr("V1 Pro · 高质", "V1 Pro · High quality"),
             "credit_cost": MODEL_CREDIT_COST["v1_pro"],
             "capabilities": {"vocals": True, "midi": True, "stems": 4}},
            {"value": "v1_fast", "label": tr("V1 · 快速草稿", "V1 · Fast draft"),
             "credit_cost": MODEL_CREDIT_COST["v1_fast"],
             "capabilities": {"vocals": True, "midi": True, "stems": 4}},
        ],
        "edit_operations": [
            {"value": "extend", "label": tr("续写", "Extend"),
             "endpoint": "/candidates/{id}/extend",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["extend"],
             "limits": {"min_seconds": 15, "max_seconds": 60}},
            {"value": "variant", "label": tr("风格变奏", "Style variant"),
             "endpoint": "/candidates/{id}/variant",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["variant"],
             "limits": {"max_style_prompt": 500}},
            {"value": "regen_section", "label": tr("段落重生成", "Section regen"),
             "endpoint": "/candidates/{id}/regen-section",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["regen_section"],
             "limits": {"sections": ["intro", "verse", "pre_chorus", "chorus",
                                     "bridge", "outro"],
                        "occurrence": tr(
                            "1 起始，默认 1（重生成该段落第 N 次出现）",
                            "1-based, default 1 (regenerate the Nth occurrence "
                            "of the section)")}},
        ],
        "keys": keys,
        "time_signatures": list(TIME_SIGNATURES),
        "vocal_types": [{"value": v, "label": tr(*lbl)} for v, lbl in _VOCAL_LABELS.items()],
        "languages": [{"value": v, "label": tr(*_LANG_LABELS[v])} for v in LANGUAGES],
        "structure_tags": [
            {"tag": "[Intro]", "section": "intro", "label": "Intro"},
            {"tag": "[Verse]", "section": "verse", "label": "Verse"},
            {"tag": "[Pre-Chorus]", "section": "pre_chorus", "label": "Pre"},
            {"tag": "[Chorus]", "section": "chorus", "label": "Chorus"},
            {"tag": "[Bridge]", "section": "bridge", "label": "Bridge"},
            {"tag": "[Outro]", "section": "outro", "label": "Outro"},
        ],
        "generation_limits": {
            "min_duration_sec": 30, "max_duration_sec": 240,
            "min_bpm": 60, "max_bpm": 174,
            "max_style_prompt": 500, "max_lyrics": 4000, "max_negative_prompt": 100,
        },
        "inspiration": {
            "scenes": [tr(*x) for x in _SCENES],
            "moods": [tr(*x) for x in _MOODS],
            "genres": [tr(*x) for x in _GENRES],
            "instruments": [tr(*x) for x in _INSTRUMENTS],
        },
    })
