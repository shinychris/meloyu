"""取消/退款并发正确性回归（2026-10-27）。

原实现两处 check-then-act 竞态可致积分双花：
- cancel_task 读 status → 置 canceled + 退款，无状态守卫，并发取消双退款；
- credits.refund 的 exists 检查与插入非原子，同一窗口双发。
修复后：cancel 走条件 UPDATE（queued→canceled 仅首个事务胜出，退款只随胜者
事务落账）；refund 以部分唯一索引 uq_ct_refund_per_task 在插入侧硬保证幂等。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.core.errors import BizError
from app.models import CreditTransaction, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.services import credits as credits_svc
from app.services import generation as gen_svc
from tests.db import new_test_engine, reset_db, seed_plans


class _CancelRefundTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        seed_plans(self.db)
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="cr@test.local", password_hash="x",
                         nickname="cr", plan="studio", credit_balance=100,
                         created_at=ts, updated_at=ts)
        self.work = Work(id="w" * 32, user_id=self.user.id, display_code="MY-0001",
                         title="退款之歌", status="active", favorite=False, tags=[],
                         bpm=90, key_tonic="A", key_mode="minor", duration_sec=120,
                         model="v1_pro", version_count=1,
                         created_at=ts, updated_at=ts)
        self.version = Version(id="v" * 32, work_id=self.work.id, version_no="v1",
                               source="generate", candidate_count=0, params={},
                               lyrics="", created_at=ts, updated_at=ts)
        self.db.add_all([self.user, self.work, self.version])
        self.db.flush()
        self.task = Task(id="t" * 32, user_id=self.user.id, type="generation",
                         status="queued", progress=0, stage_key="queued",
                         stage_label="q", work_id=self.work.id,
                         version_id=self.version.id, provider="localsynth", seed=1,
                         cost_credits=12, request_payload={},
                         created_at=ts, updated_at=ts)
        self.db.add(self.task)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _refund_rows(self) -> list[CreditTransaction]:
        return list(self.db.execute(select(CreditTransaction).where(
            CreditTransaction.reason == "refund")).scalars())


class TestRefundIdempotency(_CancelRefundTestCase):
    def test_double_refund_same_task_adds_once(self):
        """同 ref_task_id 两次 refund 只加一次款、只落一笔流水。"""
        b1 = credits_svc.refund(self.db, self.user.id, 12, self.task.id)
        b2 = credits_svc.refund(self.db, self.user.id, 12, self.task.id)
        self.db.expire_all()
        self.db.refresh(self.user)
        self.assertEqual(b1, 112)
        self.assertEqual(b2, 112, "第二次退款必须被幂等挡下（不再加款）")
        self.assertEqual(self.user.credit_balance, 112)
        self.assertEqual(len(self._refund_rows()), 1)

    def test_partial_unique_index_blocks_second_refund_row(self):
        """绕过应用层直插第二笔同任务 refund → 部分唯一索引拒绝。"""
        credits_svc.refund(self.db, self.user.id, 12, self.task.id)
        self.db.commit()  # 第一笔退款落库（refund 本身不 commit，由调用方提交）
        self.db.add(CreditTransaction(user_id=self.user.id, delta=12, reason="refund",
                                      ref_task_id=self.task.id, balance_after=124))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(len(self._refund_rows()), 1)

    def test_different_task_refunds_are_independent(self):
        """幂等键是 ref_task_id：不同任务各退各的，互不挡。"""
        ts = utc_now_iso()
        other = Task(id="o" * 32, user_id=self.user.id, type="generation",
                     status="failed", progress=0, stage_key="done", stage_label="d",
                     work_id=self.work.id, version_id=self.version.id,
                     provider="localsynth", seed=1, cost_credits=6,
                     request_payload={}, created_at=ts, updated_at=ts)
        self.db.add(other)
        self.db.commit()
        credits_svc.refund(self.db, self.user.id, 12, self.task.id)
        credits_svc.refund(self.db, self.user.id, 6, other.id)
        self.db.expire_all()
        self.db.refresh(self.user)
        self.assertEqual(self.user.credit_balance, 118)
        self.assertEqual(len(self._refund_rows()), 2)


class TestCancelTaskStateGuard(_CancelRefundTestCase):
    def test_cancel_queued_refunds_with_winner(self):
        out = gen_svc.cancel_task(self.db, self.user, self.task.id)
        self.assertEqual(out["status"], "canceled")
        self.assertEqual(len(self._refund_rows()), 1)
        self.db.expire_all()
        self.db.refresh(self.user)
        self.assertEqual(self.user.credit_balance, 112)

    def test_cancel_twice_second_conflicts_without_refund(self):
        gen_svc.cancel_task(self.db, self.user, self.task.id)
        with self.assertRaises(BizError) as ctx:
            gen_svc.cancel_task(self.db, self.user, self.task.id)
        self.assertEqual(ctx.exception.code, 40901)
        self.assertEqual(len(self._refund_rows()), 1, "二次取消不得再退款")

    def test_cancel_running_sets_flag_never_refunds(self):
        """非 queued（running）取消：只置标志，退款由执行线程终态分支负责。"""
        self.task.status = "running"
        self.db.commit()
        out = gen_svc.cancel_task(self.db, self.user, self.task.id)
        self.assertEqual(out["status"], "running")
        self.assertTrue(out["stage_label"], "取消中 stage_label 已置")
        self.db.expire_all()
        self.db.refresh(self.task)
        self.assertTrue(self.task.cancel_requested)
        self.assertEqual(self._refund_rows(), [], "running 取消不得在此处退款")
        self.db.refresh(self.user)
        self.assertEqual(self.user.credit_balance, 100)

    def test_cancel_finished_conflicts(self):
        self.task.status = "succeeded"
        self.db.commit()
        with self.assertRaises(BizError):
            gen_svc.cancel_task(self.db, self.user, self.task.id)
        self.assertEqual(self._refund_rows(), [])


if __name__ == "__main__":
    unittest.main()
