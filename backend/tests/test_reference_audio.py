"""FR-4 参考音频单测（v0.8.1）：分析器精度 + 上传/补传/删除 + 生成参数应用。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
内存 SQLite + 临时 audio 目录；生成集成用例 mock 掉调度（不起真实合成）。
"""
from __future__ import annotations
import tempfile
import unittest
import wave as wav_mod
from pathlib import Path
from unittest import mock

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.core.errors import BizError
from app.models import Base, Plan, User
from app.models.base import utc_now_iso
from app.services import reference as reference_svc
from app.services import reference_analysis
from app.services.generation import submit_generation


def synth_click_wav(path: Path, bpm: int, sr: int = 22050, dur: float = 30.0,
                    noise: float = 0.02) -> None:
    """拍点测试轨：噪声底 + 每拍 2kHz 衰减脉冲（BPM 检测的标准可控信号）。"""
    n = int(dur * sr)
    x = np.random.default_rng(7).normal(0, noise, n)
    beat = int(sr * 60.0 / bpm)
    for k in range(0, n - sr // 40, beat):
        length = sr // 40
        env = np.exp(-np.linspace(0, 8, length))
        x[k:k + length] += 0.8 * env * np.sin(2 * np.pi * 2000 * np.arange(length) / sr)
    x = (x / np.abs(x).max() * 0.7 * 32767).astype("<i2")
    with wav_mod.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(x.tobytes())


class TestAnalysis(unittest.TestCase):
    """分析器：BPM 拍点轨（谱通量+先验）、调性三和弦、能量/亮度边界。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _wav(self, bpm: int) -> Path:
        p = Path(self.tmp.name) / f"b{bpm}.wav"
        synth_click_wav(p, bpm)
        return p

    def test_bpm_click_tracks(self):
        # 150 的半速 75 是自相关等价解（±1 倍频程歧义文档化），其余必须精确
        for bpm in (74, 90, 96, 120, 132):
            x, sr = reference_analysis.read_wav_mono(self._wav(bpm))
            self.assertEqual(reference_analysis.detect_bpm(x, sr), bpm)

    def test_bpm_octave_ambiguity_is_valid(self):
        x, sr = reference_analysis.read_wav_mono(self._wav(150))
        detected = reference_analysis.detect_bpm(x, sr)
        self.assertIn(detected, (75, 150), "倍频歧义二选一均合法（估计值语义）")

    def test_analysis_fields_and_ranges(self):
        r = reference_analysis.analyze_wav(self._wav(120))
        self.assertEqual(set(r), {"bpm", "key_tonic", "key_mode", "energy",
                                  "brightness", "duration_sec"})
        self.assertTrue(60 <= r["bpm"] <= 174)
        self.assertIn(r["key_tonic"], ("C", "C#", "D", "D#", "E", "F", "F#",
                                       "G", "G#", "A", "A#", "B"))
        self.assertIn(r["key_mode"], ("major", "minor"))
        self.assertTrue(0 <= r["energy"] <= 1)
        self.assertTrue(0 <= r["brightness"] <= 1)
        self.assertAlmostEqual(r["duration_sec"], 30.0, delta=0.2)

    def test_key_triads(self):
        def pad(path: Path, triad: tuple[float, float, float]):
            sr, dur = 22050, 30.0
            n = int(dur * sr)
            t = np.arange(n) / sr
            rng = np.random.default_rng(3)
            x = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) for f in triad)
            x = (x / np.abs(x).max() * 0.7 * 32767).astype("<i2")
            with wav_mod.open(str(path), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
                wf.writeframes(x.tobytes())
        cases = [((220.0, 261.63, 329.63), "A", "minor"),   # A3 C4 E4
                 ((261.63, 329.63, 392.0), "C", "major"),   # C4 E4 G4
                 ((164.81, 196.0, 246.94), "E", "minor")]   # E3 G3 B3
        for triad, tonic, mode in cases:
            p = Path(self.tmp.name) / f"pad_{tonic}{mode}.wav"
            pad(p, triad)
            x, sr = reference_analysis.read_wav_mono(p)
            self.assertEqual(reference_analysis.detect_key(x, sr), (tonic, mode))


class _RefTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="ref@test.local",
                         password_hash="x", nickname="ref",
                         plan="studio", credit_balance=10000,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        settings.data_dir = self._old
        self.tmp.cleanup()

    def _wav_bytes(self, bpm: int = 120) -> bytes:
        p = Path(self.tmp.name) / "tmp.wav"
        synth_click_wav(p, bpm, dur=20.0)
        return p.read_bytes()


class TestTrackCrud(_RefTestCase):
    def test_create_wav_analyzed_immediately(self):
        out = reference_svc.create_track(self.db, self.user,
                                         filename="demo.wav",
                                         content=self._wav_bytes(96))
        self.assertTrue(out["analyzed"])
        self.assertTrue(60 <= out["analysis"]["bpm"] <= 174)
        # 合规提示双语固定（不随 locale 漂移）
        self.assertIn("非采样", out["notice"])
        self.assertIn("no waveform", out["notice"])

    def test_create_mp3_then_attach_analysis(self):
        out = reference_svc.create_track(self.db, self.user, filename="song.mp3",
                                         content=b"\xff\xfb" + b"0" * 4096)
        self.assertFalse(out["analyzed"])
        # 未分析的参考不能用于生成
        with self.assertRaises(BizError):
            reference_svc.resolve_for_generation(self.db, self.user, out["id"])
        out2 = reference_svc.attach_analysis_wav(self.db, self.user, out["id"],
                                                 self._wav_bytes(120))
        self.assertTrue(out2["analyzed"])
        self.assertIn(out2["analysis"]["bpm"], (60, 120))  # 120 拍点或其合法倍频
        reference_svc.resolve_for_generation(self.db, self.user, out["id"])  # 不再抛

    def test_bad_extension_rejected(self):
        with self.assertRaises(BizError):
            reference_svc.create_track(self.db, self.user, filename="a.flac",
                                       content=b"x" * 100)

    def test_duration_limit(self):
        p = Path(self.tmp.name) / "long.wav"
        sr = 8000
        n = int(490 * sr)
        with wav_mod.open(str(p), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(np.zeros(n, dtype="<i2").tobytes())
        with self.assertRaises(BizError):
            reference_svc.create_track(self.db, self.user, filename="long.wav",
                                       content=p.read_bytes())

    def test_list_and_delete(self):
        a = reference_svc.create_track(self.db, self.user, filename="a.wav",
                                       content=self._wav_bytes())
        b = reference_svc.create_track(self.db, self.user, filename="b.mp3",
                                       content=b"\xff\xfb" + b"0" * 100)
        lst = reference_svc.list_tracks(self.db, self.user)
        self.assertEqual(lst["total"], 2)
        # created_at 秒级同刻时以 id 决胜——此处仅断言集合与分页字段
        self.assertEqual({t["name"] for t in lst["items"]}, {"a.wav", "b.mp3"})
        rel_path = (self.db.query(models.ReferenceTrack)
                    .filter_by(id=a["id"]).one().path)
        self.assertTrue((settings.audio_path / rel_path).exists())
        self.assertEqual(reference_svc.delete_track(self.db, self.user, a["id"]),
                         {"ok": True})
        self.assertFalse((settings.audio_path / rel_path).exists())
        with self.assertRaises(BizError):
            reference_svc.get_owned(self.db, self.user, a["id"])


class TestApplyToParams(unittest.TestCase):
    def test_overrides_bpm_key_density_with_clamp(self):
        out = reference_svc.apply_to_params(
            {"bpm": 90, "key": {"tonic": "C", "mode": "major"},
             "instrument_density": 30, "vocal": "female_air", "duration_sec": 120},
            {"bpm": 132, "key_tonic": "E", "key_mode": "minor", "energy": 0.72,
             "brightness": 0.4, "duration_sec": 100})
        self.assertEqual(out["bpm"], 132)
        self.assertEqual(out["key"], {"tonic": "E", "mode": "minor"})
        self.assertEqual(out["instrument_density"], 72)
        self.assertEqual(out["vocal"], "female_air")  # 用户选择保留

    def test_clamps(self):
        out = reference_svc.apply_to_params(
            {"bpm": 90, "key": {"tonic": "A", "mode": "minor"}, "instrument_density": 50},
            {"bpm": 40, "key_tonic": "A", "key_mode": "minor", "energy": 1.4,
             "brightness": 0.5, "duration_sec": 10})
        self.assertEqual(out["bpm"], 60)      # 折进下限
        self.assertEqual(out["instrument_density"], 100)


class TestGenerationIntegration(_RefTestCase):
    def test_submit_applies_reference_params(self):
        # plan 行（免费额度检查依赖）
        ts = utc_now_iso()
        self.db.add(Plan(code="studio", name="Studio", price_monthly=168,
                         price_yearly=134, daily_generations=None,
                         monthly_credits=10000, max_export="wav",
                         commercial_license=True, watermark=False, features=[],
                         switchable=True, sort_order=2,
                         created_at=ts, updated_at=ts))
        self.db.commit()
        track = reference_svc.create_track(self.db, self.user, filename="r.wav",
                                           content=self._wav_bytes(96))
        payload = {
            "mode": "custom", "style_prompt": "cinematic pop",
            "lyrics": "", "negative_prompt": "", "model": "v1_pro",
            "params": {"bpm": 90, "key": {"tonic": "C", "mode": "major"},
                       "duration_sec": 30, "vocal": "instrumental",
                       "instrument_density": 40},
            "reference_track_id": track["id"],
        }
        with mock.patch("app.core.tasks.schedule_generation") as sched:
            out = submit_generation(self.db, self.user, payload)
        sched.assert_called_once()
        task = out["task"]
        # 留痕断言取 DB 原行（task_to_dict 的对外口径不含 request_payload 全量）
        from app.models import Task as TaskRow, Version
        row = self.db.get(TaskRow, task["id"])
        ref = row.request_payload["reference"]
        self.assertEqual(ref["reference_track_id"], track["id"])
        self.assertTrue(ref["feature_level"] and ref["ack_rights"])
        version = self.db.get(Version, row.version_id)
        self.assertEqual(version.params["key"]["tonic"],
                         track["analysis"]["key_tonic"])
        self.assertEqual(version.params["bpm"], track["analysis"]["bpm"])
        # 积分照扣
        self.assertEqual(row.cost_credits, 12)


if __name__ == "__main__":
    unittest.main()
