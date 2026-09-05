"""v0.10.2 业务可用性批回归单测：

1. P0-A：本地引擎小节取整产出的 29s 候选（30s 请求 ±5% 容差内）采纳不再触发
   ck_works_duration 违例（旧约束 30~240 → 50001，现放宽 25~300）。
2. P0-A 迁移：带旧约束的既有库经 migrations.run 重建为 25~300，且旧行全量保留。

运行：.venv/Scripts/python.exe -m unittest tests.test_adopt_duration -v
"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.core import migrations
from app.models import Base, Candidate, User, Version, Work
from app.models.base import utc_now_iso
from app.services.generation import adopt_candidate


def _mk(db, wid: str, uid: str, work_duration: int):
    ts = utc_now_iso()
    db.add(User(id=uid, email=f"{uid[:3]}@test.local", password_hash="x",
                nickname="u", plan="free", credit_balance=10,
                created_at=ts, updated_at=ts))
    db.add(Work(id=wid, user_id=uid, display_code=f"ML-{wid[:4]}", title="t",
                tags=[], bpm=90, key_tonic="A", key_mode="minor",
                duration_sec=work_duration, model="v1_fast", version_count=1,
                created_at=ts, updated_at=ts))
    db.flush()


class TestAdoptShortCandidate(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        _mk(self.db, "w" * 32, "u" * 32, 30)
        ts = utc_now_iso()
        self.db.add(Version(id="v" * 32, work_id="w" * 32, version_no="v1",
                            source="generate", candidate_count=2, params={},
                            lyrics="", created_at=ts, updated_at=ts))
        # 30s 请求 @90bpm 4/4 → 11 小节 = 29.33s → 引擎落库 29（±5% 容差内）
        for i, label in enumerate("AB"):
            self.db.add(Candidate(id=f"c{i}" + "c" * 30, version_id="v" * 32,
                                  label=label, adopted=False, seed=i, quality_score=90,
                                  duration_sec=29, bpm=90, key_tonic="A",
                                  key_mode="minor", time_signature="4/4",
                                  vocal="female_air", language="zh", style_tags=[],
                                  structure=[], applied_negative=[],
                                  created_at=ts, updated_at=ts))
        self.db.commit()
        self.user = self.db.get(User, "u" * 32)

    def tearDown(self):
        self.db.close()

    def test_adopt_29s_candidate_succeeds(self):
        # 旧约束（30~240）下该写入触发 IntegrityError → 接口 50001；v0.10.2 起应成功
        cand = self.db.execute(
            text("SELECT id FROM candidates WHERE label='A'")).scalar_one()
        out = adopt_candidate(self.db, cand, self.user)
        self.assertEqual(out["active_candidate_id"], cand)
        self.assertEqual(self.db.get(Work, "w" * 32).duration_sec, 29)

    def test_work_duration_bounds_25_300(self):
        # 新约束边界：25/300 可写，24/301 拒绝（数据完整性下限仍生效）
        w = self.db.get(Work, "w" * 32)
        for ok in (25, 29, 300):
            w.duration_sec = ok
            self.db.commit()
        from sqlalchemy.exc import IntegrityError
        for bad in (24, 301):
            w.duration_sec = bad
            with self.assertRaises(IntegrityError):
                self.db.commit()
            self.db.rollback()


class TestWorksMigration(unittest.TestCase):
    def test_old_constraint_rebuilt(self):
        engine = create_engine("sqlite:///:memory:",
                               connect_args={"check_same_thread": False})
        # 建一套「旧约束」的 works 表（模拟 v0.10.1 及以前的存量库）
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("""
                CREATE TABLE works (
                    id VARCHAR(32) PRIMARY KEY,
                    created_at VARCHAR(40), updated_at VARCHAR(40),
                    user_id VARCHAR(32) NOT NULL,
                    display_code VARCHAR(12) NOT NULL UNIQUE,
                    title VARCHAR(50) NOT NULL,
                    status VARCHAR(8) NOT NULL DEFAULT 'active',
                    favorite BOOLEAN NOT NULL DEFAULT 0,
                    tags JSON NOT NULL DEFAULT '[]',
                    bpm INTEGER NOT NULL,
                    key_tonic VARCHAR(2) NOT NULL,
                    key_mode VARCHAR(8) NOT NULL,
                    duration_sec INTEGER NOT NULL
                        CHECK (duration_sec BETWEEN 30 AND 240),
                    model VARCHAR(8) NOT NULL,
                    cover_color VARCHAR(7),
                    version_count INTEGER NOT NULL DEFAULT 0,
                    active_version_id VARCHAR(32),
                    preview_file_id VARCHAR(32),
                    trashed_at VARCHAR(40),
                    space_id VARCHAR(32)
                )"""))
            conn.execute(text("""
                INSERT INTO works (id, created_at, updated_at, user_id, display_code,
                    title, status, favorite, tags, bpm, key_tonic, key_mode,
                    duration_sec, model, version_count)
                VALUES ('w1', 't', 't', 'u1', 'ML-0001', 'old', 'active', 0, '[]',
                        90, 'A', 'minor', 120, 'v1_pro', 1)"""))
            # 其余表按当前模型建全（迁移只重建 works；_rebuild_table 依赖完整模型）
            Base.metadata.create_all(engine, tables=[
                t for n, t in Base.metadata.tables.items() if n != "works"])
            applied = migrations.run(engine)
            self.assertIn("works.duration CHECK 放宽 25~300", applied)
            ddl = conn.execute(text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='works'"
            )).scalar_one()
            self.assertIn("duration_sec BETWEEN 25 AND 300", ddl)
            # 旧数据保留；25s 行在迁移后可写入（旧行 UPDATE 也放行）
            n = conn.execute(text("SELECT COUNT(*) FROM works")).scalar_one()
            self.assertEqual(n, 1)
            conn.execute(text("UPDATE works SET duration_sec = 25 WHERE id='w1'"))
            # 幂等：重跑不再触发 works 重建
            self.assertNotIn("works.duration CHECK 放宽 25~300", migrations.run(engine))


if __name__ == "__main__":
    unittest.main()
