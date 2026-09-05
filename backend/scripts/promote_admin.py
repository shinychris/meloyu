r"""Meloyu 管理员提升脚本（v0.10.2，业务可用性批 P1）。

背景：users.is_admin 仅在注册时按 ADMIN_EMAILS 授予。若部署时未配置该变量、
或管理员在配置生效前已注册，模型中心全部写操作（通道切换/密钥配置/模型下载，
9 个 admin-only 接口）将永久 40301 且无任何运行时补救通道——本脚本补上该通道。

用法（幂等，重复执行无副作用）：
    python scripts/promote_admin.py alice@example.com          # 提升为管理员
    python scripts/promote_admin.py --revoke alice@example.com # 收回管理员
    python scripts/promote_admin.py --list                    # 列出全部管理员

说明：
- 直连 SQLite（与运行中服务并发安全：单行 UPDATE，WAL 模式）；
- 提升即时生效（每次请求实时读 users.is_admin，无缓存）；
- 收回权限前校验至少保留一名管理员，避免把自己锁死。

退出码：0 成功；1 目标不存在/参数错误；2 最后一名管理员不可收回。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="提升/收回 Meloyu 管理员（users.is_admin）")
    parser.add_argument("email", nargs="?", help="目标账号邮箱（--list 时可省略）")
    parser.add_argument("--revoke", action="store_true", help="收回管理员权限")
    parser.add_argument("--list", action="store_true", help="列出全部管理员")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.list:
            admins = db.query(User).filter(User.is_admin.is_(True)).all()
            for u in admins:
                print(f"{u.email:40s} {u.nickname}")
            print(f"共 {len(admins)} 名管理员（db: {settings.db_path}）")
            return 0

        if not args.email:
            parser.error("需要邮箱参数（或使用 --list）")
            return 1
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if not user:
            print(f"错误：账号不存在（{args.email}，db: {settings.db_path}）")
            return 1

        if args.revoke:
            n_admins = db.query(User).filter(User.is_admin.is_(True)).count()
            if user.is_admin and n_admins <= 1:
                print("错误：这是最后一名管理员，收回将锁死模型中心管理操作；"
                      "请先提升另一名管理员。")
                return 2
            user.is_admin = False
            db.commit()
            print(f"已收回管理员权限：{user.email}")
            return 0

        user.is_admin = True
        db.commit()
        print(f"已提升为管理员：{user.email}（模型中心写操作即时可用）")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
