"""生成提交路由（POST /generations）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import GenerationRequest
from app.services import generation as gen_svc

router = APIRouter(tags=["generations"])


@router.post("/generations", status_code=201)
def submit_generation(body: GenerationRequest, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return ok(gen_svc.submit_generation(db, user, body.payload()), status_code=201)
