"""团队空间与协作评论服务（v0.8.3）。

权限模型：作品属主恒为 owner；作品共享到空间后，成员按 rank 判权
（viewer 读 / commenter 评论 / editor 写 / owner 全权=空间所有者）。
三个归属检查点（works._get_work_owned / get_version_owned / audio_files.check_owner）
统一走 require_work_access，min_role 按端点语义给定。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import (
    err_conflict,
    err_forbidden,
    err_not_found,
    err_payment_required,
    err_validation,
)
from app.core.i18n import tr
from app.models import MarketOrder, TeamMember, TeamSpace, User, Work, WorkComment
from app.models.base import utc_now_iso
from app.models.team import ROLE_RANK, TEAM_ROLES

# ---- 判权 ----

def role_for_work(db: Session, work: Work, user: User) -> str | None:
    """用户对该作品的角色（owner=作品属主恒 owner；空间成员按成员角色；
    市场买家=viewer 只读（v0.10.2：购买订单即非独占使用授权凭证，买家可读/可下载）；
    无则 None）。"""
    if work.user_id == user.id:
        return "owner"
    if work.space_id:
        m = db.execute(select(TeamMember).where(
            TeamMember.space_id == work.space_id,
            TeamMember.user_id == user.id)).scalars().first()
        if m:
            return m.role
    bought = db.execute(select(MarketOrder.id).where(
        MarketOrder.work_id == work.id,
        MarketOrder.buyer_user_id == user.id)).first()
    if bought:
        return "viewer"
    return None


def require_work_access(db: Session, work: Work, user: User,
                        min_role: str = "viewer") -> str:
    """按最低角色要求校验访问，返回实际角色（owner/editor/commenter/viewer）。"""
    role = role_for_work(db, work, user)
    if role is None or ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise err_forbidden()
    return role


# ---- 空间 ----

def space_to_dict(db: Session, sp: TeamSpace, for_user: User) -> dict:
    members = db.execute(select(TeamMember).where(
        TeamMember.space_id == sp.id).order_by(TeamMember.created_at)).scalars().all()
    n_works = len(db.execute(select(Work.id).where(Work.space_id == sp.id)).all())
    return {
        "id": sp.id, "name": sp.name, "owner_user_id": sp.owner_user_id,
        "is_owner": sp.owner_user_id == for_user.id,
        "my_role": next((m.role for m in members if m.user_id == for_user.id), None),
        "member_count": len(members),
        "work_count": n_works,
        "members": [{"user_id": m.user_id, "role": m.role,
                     "created_at": m.created_at} for m in members],
        "created_at": sp.created_at,
    }


def get_space(db: Session, user: User, space_id: str) -> TeamSpace:
    sp = db.get(TeamSpace, space_id)
    if sp is None:
        raise err_not_found(tr("团队空间不存在", "Team space not found"))
    member = db.execute(select(TeamMember).where(
        TeamMember.space_id == sp.id, TeamMember.user_id == user.id)).scalars().first()
    if sp.owner_user_id != user.id and member is None:
        raise err_not_found(tr("团队空间不存在", "Team space not found"))
    return sp


def require_space_owner(db: Session, user: User, space_id: str) -> TeamSpace:
    sp = get_space(db, user, space_id)
    if sp.owner_user_id != user.id:
        raise err_forbidden()
    return sp


def _seat_gate(db: Session, user: User) -> tuple[int, int]:
    """（2026-09-26）：团队席位与档位挂钩。

    free 档：1 个空间 × 3 席位（体验协作）；pro：3 空间 × 8 席位；
    studio/team/admin：不受限（team 档走联系销售的企业口径）。
    返回 (空间上限, 席位上限)。
    """
    if getattr(user, "is_admin", False) or user.plan in ("studio", "team"):
        return 10**6, 10**6
    return (1, 3) if user.plan == "free" else (3, 8)


def _check_space_quota(db: Session, user: User) -> None:
    max_spaces, _ = _seat_gate(db, user)
    owned = db.execute(select(func.count()).select_from(TeamSpace).where(
        TeamSpace.owner_user_id == user.id)).scalar_one()
    if owned >= max_spaces:
        raise err_payment_required(tr(
            f"当前档位最多创建 {max_spaces} 个团队空间，升级或联系销售解锁更多",
            f"Your plan allows up to {max_spaces} team space(s); upgrade or contact "
            "sales for more"))


def _check_seat_quota(db: Session, user: User, sp: TeamSpace) -> None:
    _, max_seats = _seat_gate(db, user)
    members = db.execute(select(func.count()).select_from(TeamMember).where(
        TeamMember.space_id == sp.id)).scalar_one()
    if members >= max_seats:
        raise err_payment_required(tr(
            f"当前档位团队空间最多 {max_seats} 个席位（含所有者），升级解锁更多席位",
            f"Your plan allows up to {max_seats} seats per space (owner included); "
            "upgrade for more seats"))


def create_space(db: Session, user: User, name: str) -> dict:
    name = (name or "").strip()
    if not 1 <= len(name) <= 60:
        raise err_validation(tr("空间名须为 1~60 字符", "Space name must be 1-60 chars"))
    _check_space_quota(db, user)
    now = utc_now_iso()
    sp = TeamSpace(name=name, owner_user_id=user.id, created_at=now, updated_at=now)
    db.add(sp)
    db.flush()
    db.add(TeamMember(space_id=sp.id, user_id=user.id, role="owner",
                      invited_by=user.id, created_at=now))
    db.commit()
    db.refresh(sp)
    return space_to_dict(db, sp, user)


def list_spaces(db: Session, user: User) -> dict:
    rows = db.execute(
        select(TeamSpace).join(TeamMember, TeamMember.space_id == TeamSpace.id)
        .where(TeamMember.user_id == user.id)
        .order_by(TeamSpace.created_at.desc())).scalars().all()
    return {"items": [space_to_dict(db, sp, user) for sp in rows], "total": len(rows)}


def add_member(db: Session, user: User, space_id: str, email: str, role: str) -> dict:
    sp = require_space_owner(db, user, space_id)
    if role not in TEAM_ROLES or role == "owner":
        raise err_validation(tr("角色须为 editor/commenter/viewer",
                            "role must be editor/commenter/viewer"))
    target = db.execute(select(User).where(User.email == email.strip().lower())).scalars().first()
    if target is None:
        raise err_not_found(tr("该邮箱尚未注册（成员须为已注册用户）",
                           "That email is not registered (members must have accounts)"))
    exists = db.execute(select(TeamMember).where(
        TeamMember.space_id == sp.id, TeamMember.user_id == target.id)).scalars().first()
    if exists:
        raise err_conflict(tr("该用户已是空间成员", "User is already a member"))
    _check_seat_quota(db, user, sp)
    db.add(TeamMember(space_id=sp.id, user_id=target.id, role=role,
                      invited_by=user.id, created_at=utc_now_iso()))
    sp.updated_at = utc_now_iso()
    db.commit()
    return space_to_dict(db, sp, user)


def change_member_role(db: Session, user: User, space_id: str, member_user_id: str,
                       role: str) -> dict:
    sp = require_space_owner(db, user, space_id)
    if role not in TEAM_ROLES:
        raise err_validation(tr("角色须为 owner/editor/commenter/viewer",
                            "role must be owner/editor/commenter/viewer"))
    m = db.execute(select(TeamMember).where(
        TeamMember.space_id == sp.id,
        TeamMember.user_id == member_user_id)).scalars().first()
    if m is None:
        raise err_not_found(tr("成员不存在", "Member not found"))
    if m.role == "owner" and role != "owner":
        raise err_conflict(tr("空间所有者不可降级（转让须先删除空间）",
                          "The space owner cannot be demoted"))
    m.role = role
    sp.updated_at = utc_now_iso()
    db.commit()
    return space_to_dict(db, sp, user)


def remove_member(db: Session, user: User, space_id: str, member_user_id: str) -> dict:
    sp = require_space_owner(db, user, space_id)
    if member_user_id == sp.owner_user_id:
        raise err_conflict(tr("不能移除空间所有者", "Cannot remove the space owner"))
    m = db.execute(select(TeamMember).where(
        TeamMember.space_id == sp.id,
        TeamMember.user_id == member_user_id)).scalars().first()
    if m is None:
        raise err_not_found(tr("成员不存在", "Member not found"))
    db.delete(m)
    sp.updated_at = utc_now_iso()
    db.commit()
    return space_to_dict(db, sp, user)


def list_space_works(db: Session, user: User, space_id: str) -> dict:
    sp = get_space(db, user, space_id)
    from app.services.works import _serialize
    rows = db.execute(select(Work).where(Work.space_id == sp.id)
                      .order_by(Work.updated_at.desc())).scalars().all()
    return {"items": [_serialize(db, w, user) for w in rows], "total": len(rows)}


# ---- 共享 ----

def share_work(db: Session, user: User, work_id: str, space_id: str) -> dict:
    work = db.get(Work, work_id)
    if work is None or work.user_id != user.id:
        raise err_not_found(tr("作品不存在", "Work not found"))
    sp = get_space(db, user, space_id)  # 属主共享要求自己是空间成员（任何角色）
    if work.space_id == sp.id:
        raise err_conflict(tr("作品已共享到该空间", "Work already shared to this space"))
    work.space_id = sp.id
    work.updated_at = utc_now_iso()
    db.commit()
    return {"work_id": work.id, "space_id": sp.id}


def unshare_work(db: Session, user: User, work_id: str) -> dict:
    work = db.get(Work, work_id)
    if work is None or work.user_id != user.id:
        raise err_not_found(tr("作品不存在", "Work not found"))
    if not work.space_id:
        raise err_conflict(tr("作品未共享", "Work is not shared"))
    work.space_id = None
    work.updated_at = utc_now_iso()
    db.commit()
    return {"work_id": work.id, "space_id": None}


# ---- 评论 ----

def comment_to_dict(c: WorkComment) -> dict:
    return {
        "id": c.id, "work_id": c.work_id, "version_id": c.version_id,
        "author_id": c.author_id, "author_nickname": c.author_nickname,
        "time_sec": round(c.time_sec, 2), "body": c.body, "resolved": c.resolved,
        "created_at": c.created_at,
    }


def add_comment(db: Session, user: User, work_id: str, *, time_sec: float,
                body: str, version_id: str | None) -> dict:
    work = db.get(Work, work_id)
    if work is None:
        raise err_not_found(tr("作品不存在", "Work not found"))
    require_work_access(db, work, user, min_role="commenter")
    body = (body or "").strip()
    if not 1 <= len(body) <= 1000:
        raise err_validation(tr("评论须为 1~1000 字符", "Comment must be 1-1000 chars"))
    if not 0 <= time_sec <= max(1.0, float(work.duration_sec or 0)) + 5:
        raise err_validation(tr(f"评论锚点超出作品时间轴（0~{work.duration_sec}s）",
                            f"Comment anchor is outside the timeline (0-{work.duration_sec}s)"))
    c = WorkComment(work_id=work.id, version_id=version_id, author_id=user.id,
                    author_nickname=user.nickname or "", time_sec=time_sec,
                    body=body, created_at=utc_now_iso())
    db.add(c)
    db.commit()
    db.refresh(c)
    return comment_to_dict(c)


def list_comments(db: Session, user: User, work_id: str) -> dict:
    work = db.get(Work, work_id)
    if work is None:
        raise err_not_found(tr("作品不存在", "Work not found"))
    require_work_access(db, work, user, min_role="viewer")
    rows = db.execute(select(WorkComment).where(WorkComment.work_id == work.id)
                      .order_by(WorkComment.time_sec, WorkComment.created_at)).scalars().all()
    return {"items": [comment_to_dict(c) for c in rows], "total": len(rows)}


def resolve_comment(db: Session, user: User, comment_id: str, resolved: bool) -> dict:
    c = db.get(WorkComment, comment_id)
    if c is None:
        raise err_not_found(tr("评论不存在", "Comment not found"))
    work = db.get(Work, c.work_id)
    role = require_work_access(db, work, user, min_role="commenter")
    if role == "commenter" and c.author_id != user.id:
        raise err_forbidden()  # commenter 仅能处理自己的评论
    c.resolved = bool(resolved)
    db.commit()
    return comment_to_dict(c)


def delete_comment(db: Session, user: User, comment_id: str) -> dict:
    c = db.get(WorkComment, comment_id)
    if c is None:
        raise err_not_found(tr("评论不存在", "Comment not found"))
    work = db.get(Work, c.work_id)
    role = require_work_access(db, work, user, min_role="commenter")
    if role == "commenter" and c.author_id != user.id:
        raise err_forbidden()
    db.delete(c)
    db.commit()
    return {"ok": True}
