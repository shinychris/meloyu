"""v0.11.0 占位转正批单测：/pitch 修调 + 哼唱成歌（分析与旋律覆写）+ 自定义封面。

运行：.venv/Scripts/python.exe -m unittest tests.test_placeholders -v
"""
from __future__ import annotations

import io
import unittest
import wave as wav_mod
from unittest import mock

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.core.errors import BizError
from app.models import Base, Candidate, Plan, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.services import editing as edit_svc
from app.services import hum as hum_svc
from app.synth.ir import Note, SongIR, SongRequest
from app.synth.melody import apply_hum_melody


def _hum_wav(freqs: list[float], sec_each: float = 0.5, sr: int = 22050) -> bytes:
    x = []
    for hz in freqs:
        t = np.arange(int(sr * sec_each)) / sr
        seg = 0.6 * np.sin(2 * np.pi * hz * t)
        env = np.minimum(1, np.arange(len(t)) / (sr * 0.02)) * np.minimum(
            1, (len(t) - np.arange(len(t))) / (sr * 0.02))
        x.append(seg * env)
    x = np.concatenate(x)
    buf = io.BytesIO()
    with wav_mod.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((x * 32767).astype("<i2").tobytes())
    return buf.getvalue()


class TestHumAnalysis(unittest.TestCase):
    def test_pitch_contour_intervals(self):
        # A3→C4→E4→D4：相对中位音 [-5,-2,2,0]，音程 [3,4,-2]（物理精确）
        r = hum_svc.analyze_hum(_hum_wav([220.0, 261.63, 329.63, 293.66]))
        semis = [n["semi"] for n in r["notes"]]
        self.assertGreaterEqual(len(semis), 4)
        ivs = [b - a for a, b in zip(semis, semis[1:])]
        self.assertTrue(all(abs(x - y) <= 1 for x, y in zip(ivs[:3], [3, 4, -2])), (semis, ivs))
        self.assertIn(0, semis)  # 中位归一：与自身中位音同高的音符为 0
        self.assertTrue(60 <= r["bpm_hint"] <= 174)
        self.assertTrue(0 < r["confidence"] <= 1)
        self.assertTrue(all(0.25 <= d <= 4 for _, d in r["hum_melody"]))

    def test_guards(self):
        with self.assertRaises(BizError):
            hum_svc.analyze_hum(b"not a wav")                      # 非 wav
        with self.assertRaises(BizError):
            hum_svc.analyze_hum(_hum_wav([220.0], sec_each=0.3))   # 太短
        # 静音（近零振幅）
        sr = 22050
        t = np.arange(sr) / sr
        silent = (0.001 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
        buf = io.BytesIO()
        with wav_mod.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(silent.tobytes())
        with self.assertRaises(BizError):
            hum_svc.analyze_hum(buf.getvalue())


class TestApplyHumMelody(unittest.TestCase):
    def _ir(self, vocal="female_air"):
        req = SongRequest(style_prompt="x", negative_prompt="", model="v1_pro",
                          lyrics="[Verse]\n测试歌词", bpm=90, tonic="A", mode="minor",
                          time_signature="4/4", duration_sec=30, vocal=vocal,
                          language="zh", instrument_density=65, seed=42)
        ir = SongIR(req=req, seed=42)
        ir.vocal_notes = [Note(start=i * 0.5, dur=0.4, midi=67, vel=0.8, syllable="测")
                          for i in range(6)]
        return ir

    def test_contour_mapped_range_clamped(self):
        ir = self._ir()
        n = apply_hum_melody(ir, [[0, 1], [3, 1], [7, 1], [12, 1]])
        self.assertEqual(n, 6)  # 全部人声音符已映射
        midis = [x.midi for x in ir.vocal_notes]
        # 音程关系保留（+3/+4/+5 序列循环保留）
        self.assertEqual(midis[1] - midis[0], 3)
        self.assertEqual(midis[2] - midis[1], 4)
        # 音域钳制（female_air 中心 72 ±9）
        self.assertTrue(all(63 <= m <= 81 for m in midis), midis)
        # 无 hum 时不动作
        ir2 = self._ir()
        self.assertEqual(apply_hum_melody(ir2, None), 0)
        self.assertEqual(apply_hum_melody(ir2, []), 0)


class TestPitchEditSubmit(unittest.TestCase):
    def setUp(self):
        import tempfile
        from app.config import settings
        self.tmp = tempfile.TemporaryDirectory()
        self._old_data = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="pe@test.local", password_hash="x",
                         nickname="pe", plan="studio", credit_balance=10000,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.add(Plan(code="studio", name="Studio", price_monthly=168,
                         price_yearly=134, daily_generations=None, monthly_credits=10000,
                         max_export="wav", commercial_license=True, watermark=False,
                         features=[], switchable=True, sort_order=2,
                         created_at=ts, updated_at=ts))
        ts2 = utc_now_iso()
        self.work = Work(id="w" * 32, user_id=self.user.id, display_code="ML-0001",
                         title="修调之歌", tags=[], bpm=90, key_tonic="A",
                         key_mode="minor", duration_sec=30, model="v1_pro",
                         version_count=1, created_at=ts2, updated_at=ts2)
        self.version = Version(id="v" * 32, work_id=self.work.id, version_no="v1",
                               source="generate", candidate_count=1,
                               params={"mode": "custom", "style_prompt": "pop", "bpm": 90,
                                       "key": {"tonic": "A", "mode": "minor"},
                                       "duration_sec": 30, "vocal": "female_air",
                                       "language": "zh", "time_signature": "4/4",
                                       "instrument_density": 65},
                               lyrics="[Verse]" + chr(10) + "测试",
                               created_at=ts2, updated_at=ts2)
        self.cand = Candidate(id="c" * 32, version_id=self.version.id, label="A",
                              adopted=True, seed=42, quality_score=90, duration_sec=30,
                              bpm=90, key_tonic="A", key_mode="minor",
                              time_signature="4/4", vocal="female_air", language="zh",
                              style_tags=["pop"],
                              structure=[{"section": "verse", "bars": 8,
                                          "start_sec": 0, "end_sec": 15},
                                         {"section": "chorus", "bars": 4,
                                          "start_sec": 15, "end_sec": 30}],
                              created_at=ts2, updated_at=ts2)
        self.version.active_candidate_id = self.cand.id
        self.work.active_version_id = self.version.id
        from app.models.task import File as FileRow
        ts3 = utc_now_iso()
        rows = [FileRow(id=("f%03d" % i) + "f" * 29, work_id=self.work.id,
                        version_id=self.version.id, candidate_id=self.cand.id,
                        kind=kind, stem_name=stem, name=f"{kind}.x",
                        path=f"{self.work.id}/{self.version.id}/"
                             f"{kind}{'_' + stem if stem else ''}.x",
                        mime="audio/wav", bytes=1000, duration_sec=30.0,
                        sample_rate=48000, sha256="0" * 64,
                        created_at=ts3, updated_at=ts3)
                for i, (kind, stem) in enumerate(
                    [("master", None), ("preview", None), ("stem", "vocals"),
                     ("stem", "drums"), ("stem", "bass"), ("stem", "other")])]
        self.db.add_all([self.work, self.version, self.cand] + rows)
        self.db.commit()
        # 磁盘产物占位（_source_context 校验存在性；本用例不执行渲染）
        from app.config import settings as _st
        import wave as _w
        base = _st.audio_path / self.work.id / self.version.id / "candidates/A/stems"
        base.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        with _w.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(48000)
            wf.writeframes(bytes(960))
        for rel in ("master.wav", "preview.mp3", "stems/vocals.wav",
                    "stems/drums.wav", "stems/bass.wav", "stems/other.wav"):
            (base.parent / rel).write_bytes(buf.getvalue())

    def tearDown(self):
        from app.config import settings
        self.db.close()
        settings.data_dir = self._old_data
        self.tmp.cleanup()

    def test_submit_and_spec(self):
        with mock.patch("app.core.tasks.schedule_generation"):
            out = edit_svc.submit_pitch_edit(
                self.db, self.user, self.cand.id,
                [{"beat": 0.0, "semi": 1}, {"beat": 4.0, "semi": -2}], quantize="8")
        row = self.db.get(Task, out["task"]["id"])
        self.assertEqual(row.cost_credits, 6)
        spec = row.request_payload["_derived"]
        self.assertEqual(spec["op"], "pitch_edit")
        self.assertEqual(spec["note_edits"],
                         [{"beat": 0.0, "semi": 1}, {"beat": 4.0, "semi": -2}])
        self.assertEqual(spec["quantize"], "8")
        child = self.db.get(Version, row.version_id)
        self.assertEqual(child.source, "pitch_edit")

    def test_validation_guards(self):
        with self.assertRaises(BizError):
            edit_svc.submit_pitch_edit(self.db, self.user, self.cand.id, [])
        with self.assertRaises(BizError):
            edit_svc.submit_pitch_edit(self.db, self.user, self.cand.id,
                                       [{"beat": 0, "semi": 99}])
        with mock.patch("app.core.tasks.schedule_generation"):
            with self.assertRaises(BizError):
                edit_svc.submit_pitch_edit(self.db, self.user, self.cand.id,
                                           [{"beat": 0, "semi": 1}], quantize="32")


class TestGenerationParamsHum(unittest.TestCase):
    def test_hum_melody_validation(self):
        from app.schemas.auth import GenerationParams
        ok = GenerationParams(hum_melody=[[0, 1], [3, 0.5]])
        self.assertEqual(ok.hum_melody, [[0, 1], [3, 0.5]])
        with self.assertRaises(Exception):
            GenerationParams(hum_melody=[[0, 1]])            # <2 项
        with self.assertRaises(Exception):
            GenerationParams(hum_melody=[[30, 1], [0, 1]])   # semi 越界
        with self.assertRaises(Exception):
            GenerationParams(hum_melody=[[0, 9], [0, 1]])    # 拍长越界
        self.assertIsNone(GenerationParams().hum_melody)


if __name__ == "__main__":
    unittest.main()
