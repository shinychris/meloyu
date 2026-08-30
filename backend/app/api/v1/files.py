"""文件路由（3 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import API_PREFIX, STREAM_TOKEN_TTL_SEC
from app.core import audio_files as af
from app.core.responses import ok
from app.core.security import get_current_user, get_current_user_optional, make_stream_token
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}/stream")
def stream(file_id: str, request: Request,
           user: User | None = Depends(get_current_user_optional),
           db: Session = Depends(get_db)):
    u = af.user_from_request_or_token(db, request, user)
    f = af.resolve_file(db, file_id)
    af.check_owner(db, f, u)
    return af.file_stream_response(request, f)


@router.get("/{file_id}/download")
def download(file_id: str, request: Request,
             user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    f = af.resolve_file(db, file_id)
    af.check_owner(db, f, user)
    return af.file_stream_response(request, f, download=True, filename=f.name)


@router.post("/{file_id}/stream-token")
def stream_token(file_id: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    f = af.resolve_file(db, file_id)
    af.check_owner(db, f, user)
    token = make_stream_token(f.id, user.id, STREAM_TOKEN_TTL_SEC)
    return ok({"url": f"{API_PREFIX}/files/{f.id}/stream?st={token}",
               "expires_in": STREAM_TOKEN_TTL_SEC})
