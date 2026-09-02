"""候选路由（6 接口 + 版本候选列表在 versions.py；extend/variant/regen-section 为 V1.1 真实实现）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audio_files as af
from app.core.errors import err_not_found, err_validation
from app.core.i18n import tr
from app.core.responses import ok
from app.core.security import get_current_user, get_current_user_optional
from app.database import get_db
from app.models import File, User
from app.schemas.auth import ExtendRequest, RegenSectionRequest, VariantRequest
from app.services import editing as edit_svc
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
        raise err_validation(tr("quality 必须为 preview/master", "quality must be preview/master"))
    u = af.user_from_request_or_token(db, request, user)
    cand = gen_svc.get_candidate_owned(db, candidate_id, u)
    f = db.execute(select(File).where(
        File.candidate_id == cand.id, File.kind == quality)).scalars().first()
    if not f:
        raise err_not_found(tr("候选音频不存在", "Candidate audio not found"))
    af.check_owner(db, f, u)
    return af.file_stream_response(request, f)


@router.post("/{candidate_id}/extend", status_code=201)
def extend(candidate_id: str, body: ExtendRequest,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """从候选结尾续写 15~60 秒：同 key/BPM/风格/人声，尾部延续并交叉淡化拼接建子版本。"""
    return ok(edit_svc.submit_extend(db, user, candidate_id, body.seconds), status_code=201)


@router.post("/{candidate_id}/variant", status_code=201)
def variant(candidate_id: str, body: VariantRequest,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """同结构（段落划分/时长逐段一致）换编曲风格，生成新候选建子版本。"""
    return ok(edit_svc.submit_variant(db, user, candidate_id, body.style_prompt),
              status_code=201)


@router.post("/{candidate_id}/regen-section", status_code=201)
def regen_section(candidate_id: str, body: RegenSectionRequest,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """仅重生成指定段落的第 occurrence 次出现（1 起始，默认 1）：
    其余段（含同名其他出现）音频逐字节不变（sha256 校验），建子版本。"""
    return ok(edit_svc.submit_regen_section(db, user, candidate_id, body.section,
                                            body.occurrence), status_code=201)
