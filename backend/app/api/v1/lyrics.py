"""歌词路由（4 接口同步 + V1.1 草稿持久化 2 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    LyricDraftRequest,
    LyricGenerateRequest,
    LyricPolishRequest,
    LyricTextRequest,
)
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


@router.get("/draft")
def get_draft(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """V1.1：歌词草稿读取（无草稿时 text=""、updated_at=null）。"""
    return ok(lyrics_svc.get_draft(db, user))


@router.put("/draft")
def put_draft(body: LyricDraftRequest, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """V1.1：歌词草稿保存（单用户单草稿，upsert）。"""
    return ok(lyrics_svc.save_draft(db, user, body.text))
