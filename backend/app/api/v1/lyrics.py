"""歌词路由（4 接口，同步）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.responses import ok
from app.core.security import get_current_user
from app.models import User
from app.schemas.auth import LyricGenerateRequest, LyricPolishRequest, LyricTextRequest
from app.services import lyrics as lyrics_svc

router = APIRouter(prefix="/lyrics", tags=["lyrics"])


@router.post("/generate")
def generate(body: LyricGenerateRequest, user: User = Depends(get_current_user)):
    return ok(lyrics_svc.generate(body.theme, body.style_hint, body.mood,
                                  body.language, body.sections))


@router.post("/polish")
def polish(body: LyricPolishRequest, user: User = Depends(get_current_user)):
    return ok(lyrics_svc.polish(body.lyrics, body.target_section, body.style_hint,
                                body.locked_lines or []))


@router.post("/rhyme-check")
def rhyme_check(body: LyricTextRequest, user: User = Depends(get_current_user)):
    return ok(lyrics_svc.rhyme_check(body.lyrics))


@router.post("/complete-tags")
def complete_tags(body: LyricTextRequest, user: User = Depends(get_current_user)):
    return ok(lyrics_svc.complete_tags(body.lyrics))
