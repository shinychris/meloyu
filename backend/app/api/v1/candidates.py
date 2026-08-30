"""候选路由（6 接口 + 版本候选列表在 versions.py）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audio_files as af
from app.core.errors import err_not_found, err_not_implemented, err_validation
from app.core.responses import ok
from app.core.security import get_current_user, get_current_user_optional
from app.database import get_db
from app.models import File, User
from app.services import generation as gen_svc
from app.services.serializers import candidate_to_dict

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/{candidate_id}")
def get_candidate(candidate_id: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    cand = gen_svc.get_candidate_owned(db, candidate_id, user)
    return ok(candidate_to_dict(cand))


@router.post("/{candidate_id}/adopt")
def adopt(candidate_id: str, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    return ok(gen_svc.adopt_candidate(db, candidate_id, user))


@router.get("/{candidate_id}/audio")
def candidate_audio(candidate_id: str, request: Request,
                    quality: str = Query(default="preview"),
                    user: User | None = Depends(get_current_user_optional),
                    db: Session = Depends(get_db)):
    if quality not in ("preview", "master"):
        raise err_validation("quality 必须为 preview/master")
    u = af.user_from_request_or_token(db, request, user)
    cand = gen_svc.get_candidate_owned(db, candidate_id, u)
    f = db.execute(select(File).where(
        File.candidate_id == cand.id, File.kind == quality)).scalars().first()
    if not f:
        raise err_not_found("候选音频不存在")
    af.check_owner(db, f, u)
    return af.file_stream_response(request, f)


@router.post("/{candidate_id}/extend")
def extend(candidate_id: str, user: User = Depends(get_current_user)):
    raise err_not_implemented("extend")


@router.post("/{candidate_id}/variant")
def variant(candidate_id: str, user: User = Depends(get_current_user)):
    raise err_not_implemented("variant")


@router.post("/{candidate_id}/regen-section")
def regen_section(candidate_id: str, user: User = Depends(get_current_user)):
    raise err_not_implemented("regen-section")
