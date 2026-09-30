"""licensing 证书×许可分流单测（P0-1）。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
事实源对齐 docs/06-商业化/2026-09-02-通道许可核验.md。
"""
from __future__ import annotations

import unittest

from app.services import licensing

class TestGrades(unittest.TestCase):
    def test_allowed_channels(self):
        self.assertEqual(licensing.commercial_grade("localsynth"), "allowed")
        self.assertEqual(licensing.commercial_grade("acestep_local", "ace-step"), "allowed")

    def test_nc_channels_and_models(self):
        self.assertEqual(licensing.commercial_grade("musicgen_local", "musicgen-small"), "nc")
        self.assertEqual(licensing.commercial_grade("songgen_local", "songgeneration-2"), "nc")
        self.assertEqual(licensing.commercial_grade("replicate", "musicgen-large"), "nc")
        self.assertEqual(licensing.commercial_grade("replicate", "khala"), "nc")

    def test_conditional(self):
        self.assertEqual(licensing.commercial_grade("mmax_local", "minimax-music-3"),
                         "conditional")
        self.assertEqual(licensing.commercial_grade("replicate", "stable-audio-open"),
                         "conditional")

    def test_apache_models_allowed(self):
        self.assertEqual(licensing.commercial_grade("replicate", "yue"), "allowed")
        self.assertEqual(licensing.commercial_grade("replicate", "diffrhythm"), "allowed")

    def test_tos_and_unknown(self):
        self.assertEqual(licensing.commercial_grade("api"), "tos")
        # 未知通道保守 unverified
        self.assertEqual(licensing.commercial_grade("nonexistent-channel"), "unverified")

    def test_full_catalog_covered(self):
        from app.providers.music_catalog import MUSIC_CATALOG
        self.assertEqual(
            {m["id"] for m in MUSIC_CATALOG}, set(licensing.COMMERCIAL_USE),
            "目录每个模型都必须有 commercial_use 判定")

class TestLicenseForGeneration(unittest.TestCase):
    def test_free_plan_always_non_commercial(self):
        lic = licensing.license_for_generation("free", "acestep_local", "ace-step")
        self.assertEqual(lic["type"], "non_commercial")
        self.assertEqual(lic["grade"], "free_plan")

    def test_paid_allowed_commercial(self):
        lic = licensing.license_for_generation("pro", "acestep_local", "ace-step")
        self.assertEqual(lic["type"], "commercial")
        self.assertEqual(lic["grade"], "allowed")
        self.assertTrue(lic["basis_zh"] and lic["basis_en"])

    def test_paid_nc_model_still_non_commercial(self):
        # 付费档 + NC 模型 → 非商用（R-01 核心分流）
        lic = licensing.license_for_generation("studio", "musicgen_local", "musicgen-small")
        self.assertEqual(lic["type"], "non_commercial")
        self.assertEqual(lic["grade"], "nc")

    def test_paid_conditional(self):
        # v0.7.0 义务落实后：MiniMax conditional → commercial（basis 明示 $20M 门槛，
        # 回退开关行为见 tests/test_mmax_obligations.py）
        lic = licensing.license_for_generation("studio", "mmax_local", "minimax-music-3")
        self.assertEqual(lic["type"], "commercial")
        self.assertEqual(lic["grade"], "conditional")
        self.assertIn("2000", lic["basis_zh"])
        self.assertIn("$20 million", lic["basis_en"])

if __name__ == "__main__":
    unittest.main()
