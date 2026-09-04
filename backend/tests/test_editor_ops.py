"""V2 编辑器后端单测（v0.9.0）：retune 派生提交 + mixdown 回存闭环。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import io
import tempfile
import unittest
import wave as wav_mod
from unittest import mock

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.config import settings
from app.core.errors import BizError
from app.models import Base, Candidate, File, Plan, User, Version, Work
from app.models.base import utc_now_iso
from app.services import editing as edit_svc


def _tone_wav(seconds: float = 8.0, sr: int = 48000) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    x = 0.5 * np.sin(2 * np.pi * 440 * t)
    pcm = (x * 32767).astype("<i2")
    buf = io.BytesIO()
    with wav_mod.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.repeat(pcm, 2).tobytes())
    return buf.getvalue()


class _EditorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="ed@test.local", password_hash="x",
                         nickname="ed", plan="studio", credit_balance=10000,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.add(Plan(code="studio", name="Studio", price_monthly=168,
                         price_yearly=134, daily_generations=None,
                         monthly_credits=10000, max_export="wav",
                         commercial_license=True, watermark=False, features=[],
                         switchable=True, sort_order=2, created_at=ts, updated_at=ts))
        ts2 = utc_now_iso()
        self.work = Work(id="w" * 32, user_id=self.user.id, display_code="ML-0001",
                         title="编辑器之歌", tags=[], bpm=96, key_tonic="A",
                         key_mode="minor", duration_sec=120, model="v1_pro",
                         version_count=1, created_at=ts2, updated_at=ts2)
        self.version = Version(id="v" * 32, work_id=self.work.id, version_no="v1",
                               source="generate", candidate_count=1,
                               params={"mode": "custom", "style_prompt": "dream pop",
                                       "bpm": 96, "key": {"tonic": "A", "mode": "minor"},
                                       "duration_sec": 120, "vocal": "female_air",
                                       "language": "zh", "time_signature": "4/4",
                                       "instrument_density": 65},
                               lyrics="[Verse]\n测试", created_at=ts2, updated_at=ts2)
        self.cand = Candidate(id="c" * 32, version_id=self.version.id, label="A",
                              adopted=True, seed=42, bpm=96, duration_sec=120,
                              key_tonic="A", key_mode="minor", time_signature="4/4",
                              vocal="female_air", language="zh",
                              style_tags=["pop"],
                              structure=[{"section": "verse", "bars": 16,
                                          "start_sec": 0, "end_sec": 60},
                                         {"section": "chorus", "bars": 16,
                                          "start_sec": 60, "end_sec": 120}],
                              created_at=ts2, updated_at=ts2)
        self.version.active_candidate_id = self.cand.id
        self.work.active_version_id = self.version.id
        self.db.add_all([self.work, self.version, self.cand])
        # 产物文件（master/preview/4 stems 落盘登记）
        base = settings.audio_path / self.work.id / self.version.id / "candidates/A"
        (base / "stems").mkdir(parents=True, exist_ok=True)
        wav = _tone_wav()
        ts3 = utc_now_iso()
        layout = [("master.wav", "master", None, "audio/wav"),
                  ("preview.mp3", "preview", None, "audio/mpeg"),
                  ("stems/vocals.wav", "stem", "vocals", "audio/wav"),
                  ("stems/drums.wav", "stem", "drums", "audio/wav"),
                  ("stems/bass.wav", "stem", "bass", "audio/wav"),
                  ("stems/other.wav", "stem", "other", "audio/wav")]
        rows = []
        for rel, kind, stem, mime in layout:
            fp = base / rel
            fp.write_bytes(wav)
            rows.append(File(work_id=self.work.id, version_id=self.version.id,
                             candidate_id=self.cand.id, kind=kind, stem_name=stem,
                             name=rel.replace("/", "_"),
                             path=str(fp.relative_to(settings.audio_path)).replace(chr(92), "/"),
                             mime=mime, bytes=len(wav), duration_sec=8.0,
                             sample_rate=48000, sha256="0" * 64,
                             created_at=ts3, updated_at=ts3))
        self.db.add_all(rows)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        settings.data_dir = self._old
        self.tmp.cleanup()


class TestRetune(_EditorTestCase):
    def test_submit_validation_and_task(self):
        with self.assertRaises(BizError):
            edit_svc.submit_retune(self.db, self.user, self.cand.id, None, None)
        with self.assertRaises(BizError):
            edit_svc.submit_retune(self.db, self.user, self.cand.id, 300, None)
        with mock.patch("app.core.tasks.schedule_generation"):
            out = edit_svc.submit_retune(self.db, self.user, self.cand.id,
                                         120, {"tonic": "D", "mode": "major"})
        from app.models import Task
        row = self.db.get(Task, out["task"]["id"])
        self.assertEqual(row.provider, "localsynth")
        self.assertEqual(row.cost_credits, 6)
        spec = row.request_payload["_derived"]
        self.assertEqual(spec["op"], "retune")
        self.assertEqual(spec["retune_bpm"], 120)
        self.assertEqual(spec["retune_key"], {"tonic": "D", "mode": "major"})
        child = self.db.get(Version, row.version_id)
        self.assertEqual(child.source, "retune")
        self.assertEqual(child.params["bpm"], 120)
        self.assertEqual(child.params["key"], {"tonic": "D", "mode": "major"})

    def test_key_only(self):
        with mock.patch("app.core.tasks.schedule_generation"):
            out = edit_svc.submit_retune(self.db, self.user, self.cand.id,
                                         None, {"tonic": "E", "mode": "minor"})
        from app.models import Task
        row = self.db.get(Task, out["task"]["id"])
        child = self.db.get(Version, row.version_id)
        self.assertEqual(child.params["bpm"], 96)  # bpm 保持
        self.assertEqual(child.params["key"]["tonic"], "E")


class TestMixdown(_EditorTestCase):
    def test_upload_creates_child_version_with_files_and_event(self):
        out = edit_svc.submit_mixdown(self.db, self.user, self.version.id,
                                      _tone_wav(35.0), notes="人声+2dB，低切鼓组")
        child = self.db.get(Version, out["version"]["id"])
        self.assertEqual(child.source, "mixdown")
        self.assertEqual(child.version_no, "v2")
        self.assertEqual(child.candidate_count, 1)
        cand = self.db.get(Candidate, child.active_candidate_id)
        self.assertTrue(cand.adopted)
        self.assertIsNone(cand.quality_score)  # 人工混音不造假分
        files = self.db.query(File).filter(File.version_id == child.id).all()
        kinds = {f.kind for f in files}
        self.assertEqual(kinds, {"master", "preview"})
        master = next(f for f in files if f.kind == "master")
        self.assertTrue((settings.audio_path / master.path).exists())
        # work 快照回写
        self.assertEqual(self.work.active_version_id, child.id)
        self.assertEqual(self.work.duration_sec, 35)
        # 人类参与留痕（事件 detail 带 notes 与 auto_adopted）
        from app.models import EditEvent
        ev = self.db.query(EditEvent).filter(EditEvent.version_id == child.id).one()
        self.assertEqual(ev.actor, "human")
        self.assertEqual(ev.detail["op"], "mixdown")
        self.assertIn("人声+2dB", ev.detail["notes"])

    def test_duration_and_parse_guards(self):
        with self.assertRaises(BizError):
            edit_svc.submit_mixdown(self.db, self.user, self.version.id, b"not wav")
        with self.assertRaises(BizError):
            edit_svc.submit_mixdown(self.db, self.user, self.version.id, _tone_wav(3.0))


if __name__ == "__main__":
    unittest.main()
