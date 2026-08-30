"""任务路由（3 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import err_validation
from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.models.enums import TASK_STATUSES, TASK_TYPES
from app.services import generation as gen_svc
from app.services.serializers import task_to_dict

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(type: str | None = Query(default=None),
               status: str | None = Query(default=None),
               work_id: str | None = Query(default=None),
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=20, ge=1, le=100),
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if type is not None and type not in TASK_TYPES:
        raise err_validation("type 必须为 generation/export")
    if status is not None and status not in TASK_STATUSES:
        raise err_validation("status 取值非法")
    return ok(gen_svc.list_tasks(db, user, type_=type, status=status, work_id=work_id,
                                 page=page, page_size=min(page_size, 100)))


@router.get("/{task_id}")
def get_task(task_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    task = gen_svc.get_task_owned(db, task_id, user)
    return ok(task_to_dict(task))


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return ok(gen_svc.cancel_task(db, user, task_id))
