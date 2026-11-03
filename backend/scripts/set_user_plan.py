"""企业私有化部署：用户档位分配工具（管理员 CLI，P4）。

enterprise 形态多用户，权益档位由管理员指派（无自助订阅）：
    python -m scripts.set_user_plan <email> <free|pro|studio|team> [--credits N]
    python -m scripts.set_user_plan --list

档位语义：enterprise 席位建议 team（空间/席位配额放开）；
studio=全功能个人档。配额读 plans 表，随档位生效。
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Plan, User
from app.models.base import utc_now_iso
from app.services import credits as credits_svc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="enterprise user plan assignment")
    parser.add_argument("email", nargs="?", help="user email")
    parser.add_argument("plan", nargs="?", choices=("free", "pro", "studio", "team"))
    parser.add_argument("--credits", type=int, default=0, help="bonus credits to grant")
    parser.add_argument("--list", action="store_true", help="list users and plans")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.list:
            rows = db.execute(select(User).order_by(User.created_at)).scalars().all()
            for u in rows:
                print(f"{u.email:40s} plan={u.plan:8s} admin={u.is_admin}")
            return 0
        if not (args.email and args.plan):
            parser.error("email and plan are required (or --list)")
        user = db.execute(select(User).where(
            User.email == args.email.strip().lower())).scalars().first()
        if user is None:
            print(f"[ERROR] user not found: {args.email}", file=sys.stderr)
            return 1
        if db.get(Plan, args.plan) is None:
            print(f"[ERROR] plan row missing in DB: {args.plan}", file=sys.stderr)
            return 1
        user.plan = args.plan
        user.updated_at = utc_now_iso()
        if args.credits > 0:
            credits_svc.grant(db, user, args.credits, "plan_switch")
        db.commit()
        print(f"[OK] {user.email} -> plan={user.plan}"
              + (f" (+{args.credits} credits)" if args.credits else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
