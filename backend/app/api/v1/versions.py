"""版本路由（4 接口）+ 版本候选列表（candidates 列表归此处路径）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audio_files as af
from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.i18n import tr
from app.core.responses import ok
from app.core.security import get_current_user, get_current_user_optional
from app.database import get_db
from app.models import File, User
from app.services import certificate as cert_svc
from app.services import generation as gen_svc
from app.services import works as works_svc
from app.services.serializers import version_to_dict

router = APIRouter(tags=["versions"])


@router.get("/works/{work_id}/versions")
def version_tree(work_id: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return ok(works_svc.version_tree(db, work_id, user))


@router.get("/versions/{version_id}")
def get_version(version_id: str, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    version = works_svc.get_version_owned(db, version_id, user)
    return ok(version_to_dict(version))


@router.get("/versions/{version_id}/candidates")
def list_candidates(version_id: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return ok(gen_svc.list_candidates(db, version_id, user))


@router.get("/versions/{version_id}/audio")
def version_audio(version_id: str, request: Request,
                  user: User | None = Depends(get_current_user_optional),
                  db: Session = Depends(get_db)):
    u = af.user_from_request_or_token(db, request, user)
    version = works_svc.get_version_owned(db, version_id, u)
    if not version.active_candidate_id:
        raise err_conflict(tr("该版本尚未采用候选", "No candidate adopted for this version yet"))
    f = db.execute(select(File).where(
        File.candidate_id == version.active_candidate_id,
        File.kind == "master")).scalars().first()
    if not f:
        raise err_not_found(tr("版本音频不存在", "Version audio not found"))
    af.check_owner(db, f, u)
    return af.file_stream_response(request, f)


@router.get("/versions/{version_id}/certificate")
def version_certificate(version_id: str,
                        format: str = Query(default="json"),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """授权证书下载（format=json 契约 §8.4；format=pdf 为 V1.1 扩展）。"""
    if format not in cert_svc.CERT_FORMATS:
        raise err_validation(
            tr(f"format 必须为 {'/'.join(cert_svc.CERT_FORMATS)}",
               f"format must be {'/'.join(cert_svc.CERT_FORMATS)}"))
    version = works_svc.get_version_owned(db, version_id, user)
    _, filename, payload, mime = cert_svc.issue_certificate(db, user, version, fmt=format)
    return Response(
        content=payload,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
