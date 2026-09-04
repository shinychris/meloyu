"""作品库服务：CRUD / 收藏 / 回收站 / 事件留痕 / 版本树 / 导出格式徽标。"""
from __future__ import annotations

import shutil
from datetime import UTC

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.config import TRASH_RETENTION_DAYS, settings
from app.core.errors import err_conflict, err_forbidden, err_not_found
from app.core.i18n import tr
from app.models import EditEvent, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.repositories import counters
from app.services.serializers import event_to_dict, work_to_dict


def _get_work_owned(db: Session, work_id: str, user: User,
                    min_role: str = "editor", owner_only: bool = False) -> Work:
    """归属/权限校验取行（FR-13 角色化：共享作品的团队成员按 rank 判权）。

    min_role：viewer（读）/ commenter（评论，服务层内部用）/ editor（写）；
    owner_only=True 时仅作品属主本人（破坏性操作：删除/回收站/共享管理）。
    """
    work = db.get(Work, work_id)
    if not work:
        raise err_not_found(tr("作品不存在", "Work not found"))
    if owner_only:
        if work.user_id != user.id:
            raise err_forbidden()
        return work
    from app.services.team import require_work_access
    require_work_access(db, work, user, min_role=min_role)
    return work


def get_work_row(db: Session, work_id: str, user: User) -> Work:
    """公开的归属校验取行（services 间复用）。"""
    return _get_work_owned(db, work_id, user)


def exported_formats_map(db: Session, work_ids: list[str]) -> dict[str, list[str]]:
    """一批 work 的已导出格式（succeeded 导出任务 format 去重升序）。

    一条聚合查询消除前端列表页 N+1 拉导出任务的根因（契约 §14 R1 转正）。
    """
    if not work_ids:
        return {}
    rows = db.execute(
        select(Task.work_id, Task.format).where(
            Task.work_id.in_(work_ids), Task.type == "export",
            Task.status == "succeeded").distinct()
    ).all()
    grouped: dict[str, set[str]] = {}
    for wid, fmt in rows:
        grouped.setdefault(wid, set()).add(fmt)
    return {wid: sorted(fmts) for wid, fmts in grouped.items()}


def _serialize(db: Session, work: Work, user: User | None = None) -> dict:
    fmts = exported_formats_map(db, [work.id]).get(work.id, [])
    out = work_to_dict(work, exported_formats=fmts)
    if user is not None:
        # FR-13：协作上下文（共享空间/是否属主/我的角色）——前端据此渲染评论与共享入口
        from app.services.team import role_for_work
        out["space_id"] = work.space_id
        out["is_owner"] = work.user_id == user.id
        out["my_role"] = role_for_work(db, work, user)
    return out


def list_works(db: Session, user: User, *, q: str | None, tag: str | None,
               favorite: bool | None, status: str, sort: str, order: str,
               page: int, page_size: int) -> dict:
    purge_expired(db, user.id)
    conds = [Work.user_id == user.id]
    if status == "active":
        conds.append(Work.status == "active")
    elif status == "trash":
        conds.append(Work.status == "trash")
    if favorite is not None and favorite:
        conds.append(Work.favorite.is_(True))
    if tag:
        # SQLite JSON 列以文本落库：精确匹配一个标签用引号包裹的 LIKE（参数化）
        conds.append(Work.tags.like(f'%"{tag}"%'))
    if q:
        like = f"%{q}%"
        title_cond = Work.title.like(like)
        lyrics_cond = select(Version.id).where(
            Version.work_id == Work.id, Version.lyrics.like(like)).exists()
        conds.append(or_(title_cond, lyrics_cond))
    base = select(Work).where(*conds)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    sort_col = {"updated_at": Work.updated_at, "created_at": Work.created_at,
                "title": Work.title}[sort]
    order_col = sort_col.desc() if order == "desc" else sort_col.asc()
    rows = db.execute(base.order_by(order_col, Work.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    fmt_map = exported_formats_map(db, [w.id for w in rows])
    items = [work_to_dict(w, exported_formats=fmt_map.get(w.id, [])) for w in rows]
    from app.services.credits import paginate_meta
    return paginate_meta(items, total, page, page_size)


def get_work(db: Session, work_id: str, user: User) -> dict:
    return _serialize(db, _get_work_owned(db, work_id, user, min_role="viewer"), user)


def update_work(db: Session, work_id: str, user: User, *, title: str | None,
                tags: list[str] | None, favorite: bool | None) -> dict:
    work = _get_work_owned(db, work_id, user)
    changes: dict = {}
    if title is not None:
        work.title = title
        changes["title"] = title
    if tags is not None:
        work.tags = tags
        changes["tags"] = tags
    if favorite is not None:
        work.favorite = favorite
        changes["favorite"] = favorite
    work.updated_at = utc_now_iso()
    db.add(EditEvent(user_id=user.id, work_id=work.id, version_id=work.active_version_id,
                     action="update", actor="human", detail=changes))
    db.commit()
    db.refresh(work)
    return _serialize(db, work, user)


def delete_work(db: Session, work_id: str, user: User, permanent: bool) -> dict:
    work = _get_work_owned(db, work_id, user, owner_only=True)
    if permanent:
        if work.status != "trash":
            raise err_conflict(tr("作品不在回收站，无法直接物理删除（先移入回收站）",
                            "Work is not in the trash; move it to trash before permanent deletion"))
        _physical_delete(db, work)
        return {"deleted": True, "permanent": True}
    work.status = "trash"
    work.trashed_at = utc_now_iso()
    work.updated_at = utc_now_iso()
    db.add(EditEvent(user_id=user.id, work_id=work.id, version_id=None,
                     action="trash", actor="human", detail={"permanent": False}))
    db.commit()
    return {"deleted": True, "permanent": False}


def restore_work(db: Session, work_id: str, user: User) -> dict:
    work = _get_work_owned(db, work_id, user, owner_only=True)
    if work.status != "trash":
        raise err_conflict(tr("作品不在回收站", "Work is not in the trash"))
    work.status = "active"
    work.trashed_at = None
    work.updated_at = utc_now_iso()
    db.add(EditEvent(user_id=user.id, work_id=work.id, version_id=None,
                     action="restore", actor="human", detail={}))
    db.commit()
    db.refresh(work)
    return _serialize(db, work, user)


def _physical_delete(db: Session, work: Work) -> None:
    """物理删除：解除自引用外键 → 删磁盘目录 → DELETE 触发级联。"""
    work.active_version_id = None
    work.preview_file_id = None
    db.flush()
    audio_dir = settings.audio_path / work.id
    if audio_dir.exists():
        shutil.rmtree(audio_dir, ignore_errors=True)
    db.execute(text("DELETE FROM works WHERE id = :id"), {"id": work.id})
    db.commit()


def purge_expired(db: Session, user_id: str | None = None) -> int:
    """回收站 30 天清扫（列表查询时顺带触发）。"""
    from datetime import datetime, timedelta
    cutoff = (datetime.now(UTC) - timedelta(days=TRASH_RETENTION_DAYS)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = select(Work).where(Work.status == "trash", Work.trashed_at < cutoff)
    if user_id:
        q = q.where(Work.user_id == user_id)
    expired = db.execute(q).scalars().all()
    for w in expired:
        _physical_delete(db, w)
    return len(expired)


def list_events(db: Session, work_id: str, user: User, page: int, page_size: int) -> dict:
    work = _get_work_owned(db, work_id, user)
    base = select(EditEvent).where(EditEvent.work_id == work.id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(EditEvent.created_at.desc(), EditEvent.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    from app.services.credits import paginate_meta
    return paginate_meta([event_to_dict(e) for e in rows], total, page, page_size)


def version_tree(db: Session, work_id: str, user: User) -> dict:
    work = _get_work_owned(db, work_id, user, min_role="viewer")
    rows = db.execute(select(Version).where(Version.work_id == work.id)
                      .order_by(Version.created_at.asc(), Version.id.asc())).scalars().all()
    nodes = [{
        "id": v.id, "version_no": v.version_no, "parent_version_id": v.parent_version_id,
        "source": v.source, "active_candidate_id": v.active_candidate_id,
        "candidate_count": v.candidate_count, "created_at": v.created_at,
    } for v in rows]
    # 电流向解析：优先采用链回写的 active_version_id；无采用记录时取最近「非空」版本，
    # 跳过取消/失败残留的空版本（candidate_count=0），避免「当前指向空版本」
    current = None
    if work.active_version_id:
        current = work.active_version_id
    else:
        nonempty = [v for v in rows if v.candidate_count > 0]
        current = nonempty[-1].id if nonempty else (rows[-1].id if rows else None)
    return {"current_version_id": current, "nodes": nodes}


def get_version_owned(db: Session, version_id: str, user: User,
                      min_role: str = "editor") -> Version:
    version = db.get(Version, version_id)
    if not version:
        raise err_not_found(tr("版本不存在", "Version not found"))
    work = db.get(Work, version.work_id)
    if not work:
        raise err_not_found(tr("作品不存在", "Work not found"))
    from app.services.team import require_work_access
    require_work_access(db, work, user, min_role=min_role)
    return version


def new_display_code(db: Session) -> str:
    value = counters.next_counter(db, "work_display")
    return f"MY-{value:05d}"


def add_event(db: Session, user_id: str, action: str, actor: str, detail: dict,
              work_id: str | None = None, version_id: str | None = None) -> None:
    db.add(EditEvent(user_id=user_id, work_id=work_id, version_id=version_id,
                     action=action, actor=actor, detail=detail))
