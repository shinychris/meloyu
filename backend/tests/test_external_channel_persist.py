"""P0-7 回归（2026-09-26 商业化审查）：外部通道 preview/master 同源 relpath 落库。

修复前契约破坏：music_api / music_replicate(mp3 输出模型) 对同一物理文件注册
preview+master 两条元数据，_persist_success 无条件登记两行 File 同 path →
UNIQUE(files.path) IntegrityError → 兜底 except 把任务判 failed+退款——外部
通道每个任务在最后落库步必败。修复后：同源第二条复制为独立物理文件
（{stem}_{kind}.ext）再登记，preview/master 语义与导出母带解析不受影响。

运行：.venv/Scripts/python.exe -m unittest tests.test_external_channel_persist -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.models import File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.providers.base import CandidateArtifact, GenerationOutput
from app.services import generation as gen
from tests.db import new_test_engine, reset_db, seed_plans


def _mk_artifact(label: str, relpath: str) -> CandidateArtifact:
    fmeta = dict(relpath=relpath, kind="preview", stem_name=None, mime="audio/mpeg",
                 bytes=1000, duration_sec=120.0, sample_rate=None, sha256="a" * 64)
    return CandidateArtifact(
        label=label, seed=1, quality_score=None, duration_sec=120.0,
        structure=[], style_tags=[], bpm=96, tonic="A", mode="minor",
        time_signature="4/4", vocal="female_air", language="zh",
        files=[fmeta, {**fmeta, "kind": "master"}])

class TestSamePathDedupPersist(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # data_dir 指向临时目录：audio_path 随之切换（同源复制落真实文件）
        self._patch = mock.patch.object(settings, "data_dir", self._tmp.name)
        self._patch.start()
        self.addCleanup(self._patch.stop)

        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：播种档位行（users.plan → plans.code 外键）
        seed_plans(self.db)
        ts = utc_now_iso()
        self.db.add(User(id="u" * 32, email="a@test.local", password_hash="x",
                         nickname="a", plan="pro", credit_balance=100,
                         created_at=ts, updated_at=ts))
        work = Work(id="w" * 32, user_id="u" * 32, display_code="ML-0001",
                    title="t", status="active", favorite=False, tags=[], bpm=96,
                    key_tonic="A", key_mode="minor", duration_sec=120,
                    model="v1_pro", version_count=1, created_at=ts, updated_at=ts)
        version = Version(id="v" * 32, work_id=work.id, version_no="v1",
                          source="generate", candidate_count=0, params={}, lyrics="",
                          created_at=ts, updated_at=ts)
        task = Task(id="t" * 32, user_id="u" * 32, type="generation",
                    status="running", progress=50, stage_key="model_sample",
                    stage_label="s", work_id=work.id, version_id=version.id,
                    provider="api", seed=1, cost_credits=12, request_payload={},
                    created_at=ts, updated_at=ts)
        # 裸 FK 列不进 unit-of-work 依赖图：先落地父行（PG 方言门禁）
        self.db.add_all([work, version])
        self.db.flush()
        self.db.add(task)
        self.db.commit()
        # provider 已落盘的同源整曲（外部通道：preview 与 master 同一物理文件）
        rel = Path(self._tmp.name) / "audio" / work.id / version.id / "candidates/A/preview.mp3"
        rel.parent.mkdir(parents=True, exist_ok=True)
        rel.write_bytes(b"mp3-bytes" * 100)

        output = GenerationOutput([_mk_artifact("A", "candidates/A/preview.mp3")],
                                  [], False)
        provider = SimpleNamespace(name="api", display_name="External API")
        gen._persist_success(self.db, "t" * 32, "u" * 32, output, provider)

    def tearDown(self):
        self.db.close()

    def test_persist_succeeds_with_distinct_paths(self):
        task = self.db.get(Task, "t" * 32)
        self.assertEqual(task.status, "succeeded")
        rows = self.db.execute(select(File).where(
            File.work_id == "w" * 32)).scalars().all()
        kinds = sorted(r.kind for r in rows)
        self.assertEqual(kinds, ["master", "preview"])
        self.assertNotEqual(rows[0].path, rows[1].path)  # UNIQUE(path) 不再冲突
        # 同源第二条已复制为独立物理文件，内容一致
        audio = Path(self._tmp.name) / "audio"
        for r in rows:
            p = audio / r.path
            self.assertTrue(p.exists(), p)
            self.assertEqual(p.read_bytes(), b"mp3-bytes" * 100)

    def test_preview_file_id_backfilled(self):
        task = self.db.get(Task, "t" * 32)
        cand = task.result["candidates"][0]
        self.assertIsNotNone(cand["preview_file_id"])
        row = self.db.get(File, cand["preview_file_id"])
        self.assertEqual(row.kind, "preview")

    def test_export_master_lookup_resolves(self):
        # 导出链路按 candidate+kind 解析母带：master 行必须存在且物理文件可达
        row = self.db.execute(select(File).where(
            File.kind == "master", File.version_id == "v" * 32)).scalars().one()
        self.assertTrue((Path(self._tmp.name) / "audio" / row.path).exists())

if __name__ == "__main__":
    unittest.main()
