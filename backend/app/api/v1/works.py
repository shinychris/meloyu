"""作品库路由（6 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import err_validation
from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import WorkPatchRequest
from app.services import works as works_svc

router = APIRouter(prefix="/works", tags=["works"])


@router.get("")
def list_works(q: str | None = Query(default=None, max_length=50),
               tag: str | None = Query(default=None, max_length=12),
               favorite: bool | None = Query(default=None),
               status: str = Query(default="active"),
               sort: str = Query(default="updated_at"),
               order: str = Query(default="desc"),
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=20, ge=1, le=100),
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if status not in ("active", "trash", "all"):
        raise err_validation("status 必须为 active/trash/all")
    if sort not in ("updated_at", "created_at", "title"):
        raise err_validation("sort 必须为 updated_at/created_at/title")
    if order not in ("desc", "asc"):
        raise err_validation("order 必须为 desc/asc")
    return ok(works_svc.list_works(db, user, q=q, tag=tag, favorite=favorite,
                                   status=status, sort=sort, order=order,
                                   page=page, page_size=min(page_size, 100)))


@router.get("/{work_id}")
def get_work(work_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return ok(works_svc.get_work(db, work_id, user))


@router.patch("/{work_id}")
def patch_work(work_id: str, body: WorkPatchRequest,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(works_svc.update_work(db, work_id, user, title=body.title,
                                    tags=body.tags, favorite=body.favorite))


@router.delete("/{work_id}")
def delete_work(work_id: str, permanent: bool = Query(default=False),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(works_svc.delete_work(db, work_id, user, permanent))


@router.post("/{work_id}/restore")
def restore_work(work_id: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return ok(works_svc.restore_work(db, work_id, user))


@router.get("/{work_id}/events")
def list_events(work_id: str, page: int = Query(default=1, ge=1),
                page_size: int = Query(default=20, ge=1, le=100),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(works_svc.list_events(db, work_id, user, page, min(page_size, 100)))
