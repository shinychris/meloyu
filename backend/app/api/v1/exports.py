"""导出路由（POST /exports）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import ExportRequest
from app.services import export as export_svc

router = APIRouter(tags=["exports"])


@router.post("/exports", status_code=202)
def create_export(body: ExportRequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return ok(export_svc.create_export(db, user, body.version_id, body.format,
                                       platform=body.platform,
                                       meta=(body.meta.model_dump() if body.meta else None)),
              status_code=202)
