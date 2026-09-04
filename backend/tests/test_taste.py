"""V2-b 我的口味单测（v0.9.1）：画像统计 + 幂等重建。"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.models import Base, Candidate, User, Version, Work
from app.models.base import utc_now_iso
from app.services import taste as taste_svc


class TestTaste(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="taste@test.local", password_hash="x",
                         nickname="t", plan="studio", credit_balance=100,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        # 三首作品：bpm 90/120/150（中位 120）、A minor ×2（众数）、标签 pop×2 电子×1
        for i, (bpm, tonic) in enumerate([(90, "A"), (120, "A"), (150, "D")]):
            w = Work(id=f"w{i}" * 16, user_id=self.user.id,
                     display_code=f"ML-000{i}", title=f"歌{i}", tags=[],
                     bpm=bpm, key_tonic=tonic, key_mode="minor", duration_sec=120,
                     model="v1_pro", version_count=1, created_at=ts, updated_at=ts)
            v = Version(id=f"v{i}" * 16, work_id=w.id, version_no="v1",
                        source="generate", candidate_count=1,
                        params={"instrument_density": 60 + i * 10},
                        created_at=ts, updated_at=ts)
            c = Candidate(id=f"c{i}" * 16, version_id=v.id, label="A", adopted=True,
                          seed=i, bpm=bpm, duration_sec=120, key_tonic=tonic,
                          key_mode="minor", time_signature="4/4",
                          vocal="female_air" if i < 2 else "male_clear",
                          language="zh", style_tags=["pop"] if i < 2 else ["电子"],
                          structure=[], created_at=ts, updated_at=ts)
            v.active_candidate_id = c.id
            w.active_version_id = v.id
            self.db.add_all([w, v, c])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_rebuild_stats_and_idempotent(self):
        out = taste_svc.rebuild(self.db, self.user)
        p = out["profile"]
        self.assertEqual(p["bpm"], 120)              # 中位数
        self.assertEqual(p["key"], "A minor")        # 众数
        self.assertEqual(p["density"], 70)           # 60/70/80 中位
        self.assertEqual(p["vocal"], "female_air")   # 众数
        self.assertEqual(p["top_tags"][0], "pop")
        self.assertEqual(out["sample_count"], 3)
        self.assertEqual(out["semantics"][0], "suggestions_only")
        # 幂等重建：行数仍 1
        out2 = taste_svc.rebuild(self.db, self.user)
        self.assertEqual(out2["profile"], p)
        self.assertEqual(
            len(self.db.query(models.TasteProfile).all()), 1)

    def test_empty_library(self):
        u2 = User(id="z" * 32, email="z@t.local", password_hash="x", nickname="z",
                  plan="free", credit_balance=0, created_at=utc_now_iso(),
                  updated_at=utc_now_iso())
        self.db.add(u2)
        self.db.commit()
        out = taste_svc.rebuild(self.db, u2)
        self.assertEqual(out["sample_count"], 0)
        self.assertIsNone(out["profile"]["bpm"])


if __name__ == "__main__":
    unittest.main()
