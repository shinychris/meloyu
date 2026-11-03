""" 人声克隆单测（v0.8.2）：活体流程门禁 + 声纹一致性 + 音色映射 + 生成接驳。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
合成「说话人」：谐波源 + 固定共振峰峰（同一人=同一 f0 中心与共振峰；不同人=显著错开）。
"""
from __future__ import annotations

import tempfile
import unittest
import wave as wav_mod
from pathlib import Path
from unittest import mock

import numpy as np
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.core.errors import BizError
from app.models import SETTING_ID, LLMSetting, User
from app.models.base import utc_now_iso
from app.services import voice as voice_svc
from tests.db import new_test_engine, reset_db, seed_plans


def _speaker_wav(path: Path, *, f0: float, formant: float, sr: int = 22050,
                 dur: float = 4.0, seed: int = 7) -> bytes:
    """模拟朗读：谐波声源（f0 基频）+ 双共振峰（formant 比例），音高微抖模拟语调。"""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    t = np.arange(n) / sr
    f0_t = f0 * (1.0 + 0.03 * np.sin(2 * np.pi * 1.7 * t) + 0.01 * rng.standard_normal(n).cumsum() / n)
    phase = 2 * np.pi * np.cumsum(f0_t) / sr
    x = np.zeros(n)
    for k in range(1, 25):
        x += (1.0 / k) * np.sin(k * phase)
    # 共振峰强调（频域带通近似的时域模拟：加共振频率的正弦痕迹）
    x += 0.6 * np.sin(2 * np.pi * 800 * formant * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
    x += 0.4 * np.sin(2 * np.pi * 1200 * formant * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2.2 * t))
    x = (x / np.abs(x).max() * 0.6 * 32767).astype("<i2")
    with wav_mod.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(x.tobytes())
    return path.read_bytes()

class TestSimilarity(unittest.TestCase):
    """声纹一致性：同人多文本显著高于不同人。"""

    def test_same_vs_different_speaker(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        from app.services.reference_analysis import read_wav_mono
        from app.services.voice import extract_features, similarity

        def feats(f0, formant, seed):
            p = d / f"s_{f0}_{formant}_{seed}.wav"
            _speaker_wav(p, f0=f0, formant=formant, seed=seed)
            x, sr = read_wav_mono(p)
            return extract_features(x, sr)

        a = feats(180, 1.0, seed=1)   # 说话人A（偏亮女声）
        a2 = feats(180, 1.0, seed=2)  # 同人另一段（不同语调抖动种子）
        b = feats(95, 0.78, seed=3)   # 说话人B（低沉男声、共振峰低）
        self.assertGreater(similarity(a, a2), similarity(a, b))
        self.assertGreaterEqual(similarity(a, a2), voice_svc.verify_threshold(),
                                f"同人应过阈值：{similarity(a, a2):.3f}")
        self.assertLess(similarity(a, b), voice_svc.verify_threshold(),
                        f"不同人应低于阈值：{similarity(a, b):.3f}")

class TestTimbreMapping(unittest.TestCase):
    def test_timbre_fields_and_clamps(self):
        timbre = voice_svc.timbre_from_features(
            {"bands": [1.0] * 24, "f0": 110.0, "centroid": 900.0})
        self.assertEqual(
            set(timbre), {"center_midi", "f1_scale", "f2_scale", "harm_scale", "basis"})
        self.assertTrue(40 <= timbre["center_midi"] <= 76)
        # f0=110Hz（A2，男低）→ midi ≈ 45
        self.assertAlmostEqual(timbre["center_midi"], 45, delta=1)
        self.assertTrue(0.8 <= timbre["f1_scale"] <= 1.25)
        self.assertTrue(0.8 <= timbre["f2_scale"] <= 1.25)

class _VoiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：播种档位行（users.plan → plans.code 外键）
        seed_plans(self.db)
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="voice@test.local", password_hash="x",
                         nickname="v", plan="studio", credit_balance=10000,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        # 歌词引擎守卫：生成用例需自动写词，须配置真实 LLM 通道
        self.db.add(LLMSetting(id=SETTING_ID, lyrics_backend="ollama",
                               ollama_model="qwen2.5:7b"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        settings.data_dir = self._old
        self.tmp.cleanup()

    def _sample(self, f0: float, formant: float, seed: int = 1) -> bytes:
        return _speaker_wav(Path(self.tmp.name) / f"s{f0}_{formant}_{seed}.wav",
                            f0=f0, formant=formant, seed=seed)

class TestEnrollFlow(_VoiceTestCase):
    def test_two_phrase_liveness(self):
        p = voice_svc.enroll(self.db, self.user, "我的音色")
        self.assertEqual(p["status"], "pending")
        self.assertTrue(p["phrase1"])
        self.assertIsNone(p["phrase2"])
        # 样本1 → 短语2下发且不同于短语1（防重放）
        p1 = voice_svc.submit_sample(self.db, self.user, p["id"], 1,
                                     self._sample(180, 1.0))
        self.assertTrue(p1["phrase2"])
        self.assertNotEqual(p1["phrase1"], p1["phrase2"])
        # 同人样本2 → verified + timbre + 协议留痕两条
        p2 = voice_svc.submit_sample(self.db, self.user, p["id"], 2,
                                     self._sample(180, 1.0, seed=11))
        self.assertEqual(p2["status"], "verified")
        self.assertIsNotNone(p2["timbre"])
        self.assertIsNotNone(p2["verify_score"])
        self.assertEqual(len(p2["consent_log"]), 2)
        self.assertTrue(all("sample_sha256" in e and "phrase" in e for e in p2["consent_log"]))

    def test_different_speaker_rejected(self):
        p = voice_svc.enroll(self.db, self.user, "作弊档案")
        voice_svc.submit_sample(self.db, self.user, p["id"], 1, self._sample(180, 1.0))
        # 他人音频（低沉男声）做样本2 → 不通过，仍 pending
        p2 = voice_svc.submit_sample(self.db, self.user, p["id"], 2,
                                     self._sample(95, 0.75, seed=5))
        self.assertEqual(p2["status"], "pending")
        self.assertGreaterEqual(p2["verify_attempts"], 1)
        with self.assertRaises(BizError):
            voice_svc.get_verified_owned(self.db, self.user, p["id"])

    def test_attempts_exhaust_rejected(self):
        p = voice_svc.enroll(self.db, self.user, "屡败档案")
        voice_svc.submit_sample(self.db, self.user, p["id"], 1, self._sample(180, 1.0))
        for _ in range(3):
            voice_svc.submit_sample(self.db, self.user, p["id"], 2,
                                    self._sample(95, 0.75, seed=9))
        row = voice_svc.get_owned(self.db, self.user, p["id"])
        self.assertEqual(row.status, "rejected")
        self.assertEqual(row.verify_attempts, 3)

    def test_sample2_before_sample1_conflict(self):
        p = voice_svc.enroll(self.db, self.user, "乱序")
        with self.assertRaises(BizError):
            voice_svc.submit_sample(self.db, self.user, p["id"], 2, self._sample(180, 1.0))

    def test_too_short_sample_rejected(self):
        p = voice_svc.enroll(self.db, self.user, "短采样")
        buf = Path(self.tmp.name) / "short.wav"
        with wav_mod.open(str(buf), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(np.zeros(11025, dtype="<i2").tobytes())  # 0.5s
        with self.assertRaises(BizError):
            voice_svc.submit_sample(self.db, self.user, p["id"], 1, buf.read_bytes())

    def test_delete_removes_samples(self):
        p = voice_svc.enroll(self.db, self.user, "待删")
        voice_svc.submit_sample(self.db, self.user, p["id"], 1, self._sample(180, 1.0))
        row = voice_svc.get_owned(self.db, self.user, p["id"])
        s1 = settings.audio_path / row.sample1_path
        self.assertTrue(s1.exists())
        self.assertEqual(voice_svc.delete_profile(self.db, self.user, p["id"]), {"ok": True})
        self.assertFalse(s1.exists())
        with self.assertRaises(BizError):
            voice_svc.get_owned(self.db, self.user, p["id"])

class TestGenerationGate(_VoiceTestCase):
    def test_voice_clone_requires_verified_profile(self):
        from app.services.generation import submit_generation
        # plan 行由基类 seed_plans 提供（studio 等 4 档齐备）
        # 1) 缺 voice_profile_id → 40001
        with self.assertRaises(BizError) as cm:
            with mock.patch("app.core.tasks.schedule_generation"):
                submit_generation(self.db, self.user, {
                    "mode": "custom", "style_prompt": "dream pop",
                    "params": {"vocal": "voice_clone", "duration_sec": 30},
                })
        self.assertEqual(cm.exception.code, 40001)
        # 2) 未验证档案 → 40901
        p = voice_svc.enroll(self.db, self.user, "未验证")
        with self.assertRaises(BizError) as cm:
            with mock.patch("app.core.tasks.schedule_generation"):
                submit_generation(self.db, self.user, {
                    "mode": "custom", "style_prompt": "dream pop",
                    "params": {"vocal": "voice_clone", "duration_sec": 30,
                               "voice_profile_id": p["id"]},
                })
        self.assertEqual(cm.exception.code, 40901)
        # 3) 验证后 → 提交成功，timbre 进参数快照，voice 留痕
        voice_svc.submit_sample(self.db, self.user, p["id"], 1, self._sample(180, 1.0))
        p2 = voice_svc.submit_sample(self.db, self.user, p["id"], 2,
                                     self._sample(180, 1.0, seed=3))
        self.assertEqual(p2["status"], "verified")
        with mock.patch("app.core.tasks.schedule_generation"):
            out = submit_generation(self.db, self.user, {
                "mode": "custom", "style_prompt": "dream pop",
                "params": {"vocal": "voice_clone", "duration_sec": 30,
                           "voice_profile_id": p["id"]},
            })
        from app.models import Task as TaskRow
        from app.models import Version
        row = self.db.get(TaskRow, out["task"]["id"])
        self.assertEqual(row.request_payload["voice"]["voice_profile_id"], p["id"])
        self.assertTrue(row.request_payload["voice"]["voice_clone"])
        version = self.db.get(Version, row.version_id)
        self.assertEqual(version.params["voice_timbre"], p2["timbre"])
        self.assertEqual(version.params["vocal"], "voice_clone")

if __name__ == "__main__":
    unittest.main()
