"""P1-8/P1-11 配额回归（2026-09-26 商业化审查）。

- 在途任务上限：free 1 / pro 3 / studio 5（Plan 表可覆盖）
- 存储配额：files 登记字节 ≥ 档位配额 → 拒绝提交（40901）
- 失败任务孤儿清理：版本无登记文件 → 删版本目录
"""
from __future__ import annotations

import tempfile
import unittest
from unittest import mock

from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.config import settings
from app.core.errors import BizError
from app.models import File, Plan, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.services import generation as gen
from tests.db import new_test_engine, reset_db, seed_plans


class _QuotaTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：补齐夹具未自带的档位行（users.plan 外键）
        seed_plans(self.db, skip={'free', 'pro'})
        ts = utc_now_iso()
        self.db.add_all([
            Plan(code="free", name="Free", price_monthly=None, price_yearly=None,
                 daily_generations=5, monthly_credits=None, max_export="mp3",
                 commercial_license=False, watermark=True, features=[],
                 switchable=True, sort_order=0, max_concurrent_tasks=1,
                 storage_quota_mb=2, created_at=ts, updated_at=ts),
            Plan(code="pro", name="Pro", price_monthly=799, price_yearly=639,
                 daily_generations=None, monthly_credits=2500, max_export="wav",
                 commercial_license=True, watermark=False, features=[],
                 switchable=True, sort_order=1, max_concurrent_tasks=3,
                 storage_quota_mb=20, created_at=ts, updated_at=ts),
        ])
        self.user = User(id="q" * 32, email="q@t.local", password_hash="x",
                         nickname="q", plan="free", credit_balance=100,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    _seq = 0

    def _mk_task(self, status: str) -> Task:
        self._seq += 1
        n = self._seq
        ts = utc_now_iso()
        work = Work(id=f"w{n:031}".ljust(32, "x")[:32], user_id=self.user.id,
                    display_code=f"MY-{n:05d}", title="t", status="active",
                    favorite=False, tags=[], bpm=90, key_tonic="A", key_mode="minor",
                    duration_sec=120, model="v1_pro", version_count=1,
                    created_at=ts, updated_at=ts)
        version = Version(id=f"v{n:031}".ljust(32, "x")[:32], work_id=work.id,
                          version_no="v1", source="generate", candidate_count=0,
                          params={}, lyrics="", created_at=ts, updated_at=ts)
        task = Task(id=f"t{n:031}".ljust(32, "x")[:32], user_id=self.user.id,
                    type="generation", status=status, progress=0, stage_key="queued",
                    stage_label="q", work_id=work.id, version_id=version.id,
                    provider="localsynth", seed=1, cost_credits=12,
                    request_payload={}, created_at=ts, updated_at=ts)
        # 裸 FK 列不进 unit-of-work 依赖图（Task↔Work/Version 无 relationship）：
        # 先 flush 父行，PG 才不会先插 tasks 撞外键
        self.db.add_all([work, version])
        self.db.flush()
        self.db.add(task)
        self.db.commit()
        return task

class TestInflightLimit(_QuotaTestCase):

    def test_free_blocked_at_one_inflight(self):
        self._mk_task("running")
        with self.assertRaises(BizError) as ctx:
            gen.check_inflight_limit(self.db, self.user)
        self.assertEqual(ctx.exception.code, 40901)

    def test_pro_allows_three(self):
        self.user.plan = "pro"
        self.db.commit()
        for s in ("queued", "running", "succeeded"):
            self._mk_task(s)
        gen.check_inflight_limit(self.db, self.user)  # 2 在途 < 3 不抛
        self._mk_task("queued")
        with self.assertRaises(BizError):
            gen.check_inflight_limit(self.db, self.user)  # 3 在途 ≥ 3

    def test_terminal_tasks_do_not_count(self):
        for s in ("succeeded", "failed", "canceled"):
            self._mk_task(s)
        gen.check_inflight_limit(self.db, self.user)


class TestFreeDailyLimit(_QuotaTestCase):
    """F-BE-13（2026-10-27）：免费档日限不含 failed/canceled（失败即退款，
    失败也扣次数=对已退款请求二次收费——口径与退款对齐）。"""

    def test_refunded_states_do_not_count(self):
        self.db.get(Plan, "free").daily_generations = 2
        self.db.commit()
        self._mk_task("failed")
        self._mk_task("canceled")
        gen.check_free_daily_limit(self.db, self.user)  # 已退款状态不计入
        self._mk_task("queued")
        gen.check_free_daily_limit(self.db, self.user)  # 1 < 2
        self._mk_task("succeeded")
        with self.assertRaises(BizError) as ctx:  # 2 ≥ 2（失败单未占次数才可能触顶）
            gen.check_free_daily_limit(self.db, self.user)
        self.assertEqual(ctx.exception.code, 40201)

class TestStorageQuota(_QuotaTestCase):
    def test_quota_blocks_when_full(self):
        ts = utc_now_iso()
        work = Work(id="sw" * 16, user_id=self.user.id, display_code="MY-Q1",
                    title="t", status="active", favorite=False, tags=[], bpm=90,
                    key_tonic="A", key_mode="minor", duration_sec=120,
                    model="v1_pro", version_count=1, created_at=ts, updated_at=ts)
        version = Version(id="sv" * 16, work_id=work.id, version_no="v1",
                          source="generate", candidate_count=1, params={}, lyrics="",
                          created_at=ts, updated_at=ts)
        self.db.add_all([work, version])
        self.db.flush()
        # 2MB 配额 → 登记 2MB 即满
        self.db.add(File(work_id=work.id, version_id=version.id, kind="master",
                         name="m.wav", path=f"{work.id}/{version.id}/m.wav",
                         mime="audio/wav", bytes=2 * 1024 * 1024, sha256="0" * 64,
                         created_at=ts, updated_at=ts))
        self.db.commit()
        with self.assertRaises(BizError) as ctx:
            gen.check_storage_quota(self.db, self.user)
        self.assertEqual(ctx.exception.code, 40901)
        # 别人的文件不占我的配额
        other = User(id="o" * 32, email="o@t.local", password_hash="x",
                     nickname="o", plan="free", created_at=ts, updated_at=ts)
        self.db.add(other)
        self.db.commit()
        gen.check_storage_quota(self.db, other)

class TestFailedAudioCleanup(unittest.TestCase):
    def test_cleanup_removes_unregistered_version_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(settings, "data_dir", tmp):
                engine = new_test_engine()
                reset_db(engine)
                db = sessionmaker(bind=engine)()
                seed_plans(db)  # PG 方言门禁：默认 plan=free 的用户需档位行存在
                ts = utc_now_iso()
                user = User(id="c" * 32, email="c@t.local", password_hash="x",
                            nickname="c", created_at=ts, updated_at=ts)
                work = Work(id="cw" * 16, user_id=user.id, display_code="MY-C1",
                            title="t", status="active", favorite=False, tags=[],
                            bpm=90, key_tonic="A", key_mode="minor",
                            duration_sec=120, model="v1_pro", version_count=1,
                            created_at=ts, updated_at=ts)
                version = Version(id="cv" * 16, work_id=work.id, version_no="v1",
                                  source="generate", candidate_count=0, params={},
                                  lyrics="", created_at=ts, updated_at=ts)
                task = Task(id="ct" * 16, user_id=user.id, type="generation",
                            status="failed", progress=0, stage_key="done",
                            stage_label="q", work_id=work.id,
                            version_id=version.id, provider="localsynth", seed=1,
                            cost_credits=12, request_payload={},
                            created_at=ts, updated_at=ts)
                db.add(user)
                db.flush()  # 裸 FK 列不进 unit-of-work 依赖图：逐层落地父行
                db.add_all([work, version])
                db.flush()
                db.add(task)
                db.commit()
                dest = settings.audio_path / work.id / version.id
                dest.mkdir(parents=True)
                (dest / "candidates").mkdir()
                (dest / "candidates" / "A_preview.mp3").write_bytes(b"x" * 100)

                with mock.patch.object(gen, "SessionLocal",
                                       lambda: _SessionCtx(db)):
                    gen._cleanup_failed_audio("ct" * 16)
                self.assertFalse(dest.exists(), "无登记文件的失败版本目录应被清扫")

                # 有登记文件（persist 后异常）不清理
                dest.mkdir(parents=True)
                db.add(File(work_id=work.id, version_id=version.id, kind="preview",
                            name="p.mp3", path=f"{work.id}/{version.id}/p.mp3",
                            mime="audio/mpeg", bytes=100, sha256="0" * 64,
                            created_at=ts, updated_at=ts))
                db.commit()
                with mock.patch.object(gen, "SessionLocal",
                                       lambda: _SessionCtx(db)):
                    gen._cleanup_failed_audio("ct" * 16)
                self.assertTrue(dest.exists(), "已有登记文件的目录不得清理")
                db.close()

class _SessionCtx:
    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, *exc):
        return False

if __name__ == "__main__":
    unittest.main()
