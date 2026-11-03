"""团队空间与协作评论路由（v0.8.3）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.services import team as team_svc

router = APIRouter(tags=["team"])


class CreateSpaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class AddMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    role: str


class ChangeRoleRequest(BaseModel):
    role: str


class CommentRequest(BaseModel):
    """评论：锚定作品时间轴 time_sec（0~duration，前端取播放器当前时间默认）。"""
    time_sec: float = Field(default=0.0, ge=0, le=600)
    body: str = Field(min_length=1, max_length=1000)
    version_id: str | None = Field(default=None, max_length=32)


class ResolveCommentRequest(BaseModel):
    resolved: bool


# ---- 空间 ----

@router.post("/team/spaces", status_code=201)
def create_space(body: CreateSpaceRequest,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.create_space(db, user, body.name), status_code=201)


@router.get("/team/spaces")
def list_spaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.list_spaces(db, user))


@router.get("/team/spaces/{space_id}")
def get_space(space_id: str, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    return ok(team_svc.space_to_dict(db, team_svc.get_space(db, user, space_id), user))


@router.post("/team/spaces/{space_id}/members")
def add_member(space_id: str, body: AddMemberRequest,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.add_member(db, user, space_id, body.email, body.role))


@router.patch("/team/spaces/{space_id}/members/{member_user_id}")
def change_member_role(space_id: str, member_user_id: str, body: ChangeRoleRequest,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.change_member_role(db, user, space_id, member_user_id, body.role))


@router.delete("/team/spaces/{space_id}/members/{member_user_id}")
def remove_member(space_id: str, member_user_id: str,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.remove_member(db, user, space_id, member_user_id))


@router.get("/team/spaces/{space_id}/works")
def list_space_works(space_id: str, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return ok(team_svc.list_space_works(db, user, space_id))


# ---- 共享 ----

@router.post("/works/{work_id}/share")
def share_work(work_id: str, body: dict = Body(...),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.share_work(db, user, work_id, str(body.get("space_id", ""))))


@router.delete("/works/{work_id}/share")
def unshare_work(work_id: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return ok(team_svc.unshare_work(db, user, work_id))


# ---- 评论 ----

@router.post("/works/{work_id}/comments", status_code=201)
def add_comment(work_id: str, body: CommentRequest,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.add_comment(db, user, work_id, time_sec=body.time_sec,
                                   body=body.body, version_id=body.version_id),
              status_code=201)


@router.get("/works/{work_id}/comments")
def list_comments(work_id: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return ok(team_svc.list_comments(db, user, work_id))


@router.patch("/comments/{comment_id}")
def resolve_comment(comment_id: str, body: ResolveCommentRequest,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(team_svc.resolve_comment(db, user, comment_id, body.resolved))


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return ok(team_svc.delete_comment(db, user, comment_id))
