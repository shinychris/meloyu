"""版本路由（4 接口）+ 版本候选列表（candidates 列表归此处路径）。"""
from __future__ import annotations

from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audio_files as af
from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.i18n import tr
from app.core.responses import ok
from app.core.security import get_current_user, get_current_user_optional
from app.core.uploads import read_body_limited
from app.database import get_db
from app.models import File, User
from app.services import certificate as cert_svc
from app.services import editing as edit_svc
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
    version = works_svc.get_version_owned(db, version_id, user, min_role="viewer")
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
    version = works_svc.get_version_owned(db, version_id, u, min_role="viewer")
    if not version.active_candidate_id:
        raise err_conflict(tr("该版本尚未采用候选", "No candidate adopted for this version yet"))
    f = db.execute(select(File).where(
        File.candidate_id == version.active_candidate_id,
        File.kind == "master")).scalars().first()
    if not f:
        raise err_not_found(tr("版本音频不存在", "Version audio not found"))
    af.check_owner(db, f, u)
    return af.file_stream_response(request, f)


@router.post("/versions/{version_id}/mixdown", status_code=201)
async def upload_mixdown(version_id: str, request: Request,
                         notes: str = Query(default="", max_length=500),
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """V2 编辑器混音回存（octet-stream wav）→ 子版本 source=mixdown（人类参与留痕）。

    请求体流式读取（超 200MB 即断）；wav 解析/转码为 CPU 密集，包进工作线程
    执行（2026-10-27：此前整段跑在事件循环上，处理期间全部并发请求被冻结）。
    """
    body = await read_body_limited(request, 200 * 1024 * 1024,
                                   "混音文件超过 200MB 上限",
                                   "Mixdown exceeds the 200MB limit")
    result = await to_thread.run_sync(
        partial(edit_svc.submit_mixdown, db, user, version_id, body, notes=notes))
    return ok(result, status_code=201)


@router.get("/versions/{version_id}/leadsheet")
def version_leadsheet(version_id: str,
                      format: str = Query(default="pdf"),
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """词谱（v0.10.0）：候选 MIDI → 简谱+歌词+和弦；format=pdf|json。

    仅本地引擎候选（有 MIDI 产物；外部整曲 40901）。读权限（团队 viewer 可读）。
    """
    from app.core.errors import err_validation
    from app.core.i18n import tr
    from app.services import leadsheet as ls_svc
    if format not in ("pdf", "json"):
        raise err_validation(tr("format 必须为 pdf/json", "format must be pdf/json"))
    version = works_svc.get_version_owned(db, version_id, user, min_role="viewer")
    if not version.active_candidate_id:
        from app.core.errors import err_conflict
        raise err_conflict(tr("该版本尚未采用候选", "No candidate adopted for this version yet"))
    from app.models import Candidate as _C
    from app.models import Work as _W
    cand = db.get(_C, version.active_candidate_id)
    work = db.get(_W, version.work_id)
    data = ls_svc.build_leadsheet(work, version, cand)
    if format == "json":
        return ok(data)
    payload = ls_svc.render_leadsheet_pdf(data)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="{work.display_code}_{version.version_no}_leadsheet.pdf"'},
    )


@router.get("/versions/{version_id}/certificate")
def version_certificate(version_id: str,
                        format: str = Query(default="json"),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """授权证书下载（format=json ；format=pdf 为 V1.1 扩展）。"""
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
