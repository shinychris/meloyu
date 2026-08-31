"""系统路由（2 接口，无鉴权）。"""
from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import APP_VERSION, EDIT_OPERATION_CREDIT_COST, MODEL_CREDIT_COST
from app.core.responses import ok
from app.database import get_db
from app.models import File, Task
from app.models.enums import LANGUAGES, TIME_SIGNATURES, TONICS

router = APIRouter(prefix="/system", tags=["system"])

_STARTED_AT = time.time()

_VOCAL_LABELS = {
    "female_air": "女声 · 气声", "female_bright": "女声 · 清亮", "female_deep": "女声 · 浑厚",
    "male_magnetic": "男声 · 磁性", "male_clear": "男声 · 清朗", "choir": "合唱",
    "instrumental": "纯器乐",
}
_LANG_LABELS = {"zh": "中文（普通话）", "yue": "粤语", "en": "英语", "ja": "日语"}
_TONIC_ZH = {"C": "C", "C#": "升C", "D": "D", "D#": "升D", "E": "E", "F": "F", "F#": "升F",
             "G": "G", "G#": "升G", "A": "A", "A#": "升A", "B": "B"}


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
        keys.append({
            "tonic": tonic, "mode": mode,
            "label": f"{_TONIC_ZH[tonic]}{'大调' if mode == 'major' else '小调'}",
        })
    keys.sort(key=lambda k: (k["mode"], TONICS.index(k["tonic"])))
    return ok({
        "models": [
            {"value": "v1_pro", "label": "V1 Pro · 高质",
             "credit_cost": MODEL_CREDIT_COST["v1_pro"],
             "capabilities": {"vocals": True, "midi": True, "stems": 4}},
            {"value": "v1_fast", "label": "V1 · 快速草稿",
             "credit_cost": MODEL_CREDIT_COST["v1_fast"],
             "capabilities": {"vocals": True, "midi": True, "stems": 4}},
        ],
        "edit_operations": [
            {"value": "extend", "label": "续写", "endpoint": "/candidates/{id}/extend",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["extend"],
             "limits": {"min_seconds": 15, "max_seconds": 60}},
            {"value": "variant", "label": "风格变奏", "endpoint": "/candidates/{id}/variant",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["variant"],
             "limits": {"max_style_prompt": 500}},
            {"value": "regen_section", "label": "段落重生成",
             "endpoint": "/candidates/{id}/regen-section",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["regen_section"],
             "limits": {"sections": ["intro", "verse", "pre_chorus", "chorus",
                                     "bridge", "outro"]}},
        ],
        "keys": keys,
        "time_signatures": list(TIME_SIGNATURES),
        "vocal_types": [{"value": v, "label": lbl} for v, lbl in _VOCAL_LABELS.items()],
        "languages": [{"value": v, "label": _LANG_LABELS[v]} for v in LANGUAGES],
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
            "scenes": ["短视频 BGM", "广告片", "游戏配乐", "个人单曲"],
            "moods": ["治愈", "忧郁", "热血", "浪漫", "紧张"],
            "genres": ["华语流行", "国风", "嘻哈", "EDM", "Lo-fi", "摇滚", "民谣", "R&B"],
            "instruments": ["钢琴", "吉他", "弦乐", "古筝", "合成器", "808"],
        },
    })
