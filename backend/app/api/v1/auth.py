"""auth 路由（3 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth as auth_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.register(db, body.email, body.password, body.nickname), status_code=201)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.login(db, body.email, body.password))


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(auth_svc.me(db, user))
