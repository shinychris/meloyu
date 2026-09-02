"""积分服务：原子扣减/退款/发放 + 月度发放惰性触发 + 流水查询。"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import err_payment_required
from app.core.i18n import tr
from app.models import CreditTransaction, Plan, User
from app.models.base import utc_now_iso


def _add_transaction(db: Session, user_id: str, delta: int, reason: str,
                     ref_task_id: str | None, balance_after: int) -> None:
    db.add(CreditTransaction(user_id=user_id, delta=delta, reason=reason,
                             ref_task_id=ref_task_id, balance_after=balance_after))


def atomic_deduct(db: Session, user_id: str, amount: int, reason: str,
                  ref_task_id: str | None) -> int:
    """原子扣减：UPDATE ... WHERE balance >= amount；失败抛 40201。"""
    if amount <= 0:
        return _get_balance(db, user_id)
    result = db.execute(
        text("UPDATE users SET credit_balance = credit_balance - :amt, updated_at = :now "
             "WHERE id = :uid AND credit_balance >= :amt"),
        {"amt": amount, "uid": user_id, "now": utc_now_iso()},
    )
    if result.rowcount == 0:
        balance = _get_balance(db, user_id)
        raise err_payment_required(
            tr(f"积分不足：需 {amount}，余额 {balance}",
               f"Not enough credits: {amount} needed, balance {balance}"))
    new_balance = _get_balance(db, user_id)
    _add_transaction(db, user_id, -amount, reason, ref_task_id, new_balance)
    return new_balance


def refund(db: Session, user_id: str, amount: int, ref_task_id: str | None) -> int:
    """退款（幂等：同任务至多一笔 refund）。"""
    if amount <= 0:
        return _get_balance(db, user_id)
    exists = db.execute(
        select(CreditTransaction.id).where(CreditTransaction.ref_task_id == ref_task_id,
                                           CreditTransaction.reason == "refund")
    ).fetchone() if ref_task_id else None
    if exists:
        return _get_balance(db, user_id)
    db.execute(
        text("UPDATE users SET credit_balance = credit_balance + :amt, updated_at = :now "
             "WHERE id = :uid"),
        {"amt": amount, "uid": user_id, "now": utc_now_iso()},
    )
    new_balance = _get_balance(db, user_id)
    _add_transaction(db, user_id, amount, "refund", ref_task_id, new_balance)
    return new_balance


def grant(db: Session, user: User, amount: int, reason: str,
          set_carry_over: bool = False) -> int:
    """入账（signup_bonus / plan_grant / plan_switch）。"""
    before = user.credit_balance
    db.execute(
        text("UPDATE users SET credit_balance = credit_balance + :amt, updated_at = :now "
             "WHERE id = :uid"),
        {"amt": amount, "uid": user.id, "now": utc_now_iso()},
    )
    db.refresh(user)
    _add_transaction(db, user.id, amount, reason, None, user.credit_balance)
    if set_carry_over:
        user.credit_carried_over = before
    return user.credit_balance


def lazy_monthly_grant(db: Session, user: User) -> None:
    """月度发放惰性触发：next_grant_at 已过则按当前档位发放并顺延。"""
    if not user.credit_next_grant_at:
        return
    now = utc_now_iso()
    if user.credit_next_grant_at > now:
        return
    plan = db.get(Plan, user.plan)
    monthly = plan.monthly_credits if plan and plan.monthly_credits else 0
    if monthly > 0:
        grant(db, user, monthly, "plan_grant", set_carry_over=True)
    else:
        user.credit_monthly_grant = 0
    user.credit_monthly_grant = monthly
    user.credit_next_grant_at = _next_month_first_day()
    db.flush()


def _next_month_first_day(offset_months: int = 1) -> str:
    now = datetime.now(UTC)
    month = now.month + offset_months
    year = now.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return f"{year:04d}-{month:02d}-01T00:00:00Z"


def _get_balance(db: Session, user_id: str) -> int:
    row = db.execute(text("SELECT credit_balance FROM users WHERE id = :uid"),
                     {"uid": user_id}).fetchone()
    return int(row[0]) if row else 0


def balance_dict(user: User) -> dict:
    return {
        "balance": user.credit_balance,
        "monthly_grant": user.credit_monthly_grant,
        "carried_over": user.credit_carried_over,
        "plan": user.plan,
        "next_grant_at": user.credit_next_grant_at,
    }


def list_transactions(db: Session, user_id: str, page: int, page_size: int) -> dict:
    base = select(CreditTransaction).where(CreditTransaction.user_id == user_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    items = [{
        "id": t.id, "delta": t.delta, "reason": t.reason,
        "ref_task_id": t.ref_task_id, "balance_after": t.balance_after,
        "created_at": t.created_at,
    } for t in rows]
    return paginate_meta(items, total, page, page_size)


def paginate_meta(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)) if total else 0,
    }
