"""MiniMax 社区许可三项义务落实的单测（义务②"持续测试"的组成部分）。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
- 义务①（UI 署名）：provider 显示名映射——MiniMax 产出在证书/导出中署名 MiniMax-Music3
- 义务②（防侵权防护）：ip_protection 冒用检测（服务端强制）
- 义务③（AUP 披露）：导出标识带引擎署名
- 商用开放：义务落实后 mmax 条件型 commercial（含 $20M 门槛 basis 与回退开关）
"""
from __future__ import annotations

import io
import unittest
import wave as wav_mod

from app.core.errors import BizError
from app.services import ip_protection as ip
from app.services import licensing
from app.services.certificate import provider_attribution
from app.synth.id3 import mark_mp3, mark_wav


class TestObligation1Attribution(unittest.TestCase):
    """义务①：MiniMax 产出在证书与导出标识中显著署名 "MiniMax-Music3"。"""

    def test_all_channels_have_display(self):
        for channel in ("localsynth", "api", "replicate", "musicgen_local",
                        "acestep_local", "mmax_local", "songgen_local"):
            self.assertTrue(provider_attribution(channel),
                            f"channel {channel} must have a display name")

    def test_mmax_attribution_prominent(self):
        self.assertIn("MiniMax-Music3", provider_attribution("mmax_local"))

    def test_unknown_channel_falls_back(self):
        self.assertEqual(provider_attribution("mystery_channel"), "mystery_channel")


class TestObligation2IpProtection(unittest.TestCase):
    """义务②：在世艺术家名义/声音冒用拦截（服务端强制、无开关）。"""

    def test_english_impersonation_blocked(self):
        for text in ("a song in the style of Taylor Swift",
                     "Sounds like BEYONCE on the chorus",
                     "voice of Ed Sheeran, acoustic",
                     "sing like Drake about summer",
                     "cover by Ariana Grande"):
            self.assertIsNotNone(ip.detect_impersonation(text), text)

    def test_chinese_impersonation_blocked(self):
        for text in ("像周杰伦唱的慢歌", "模仿林俊杰的高音", "邓紫棋的声音",
                     "用陈奕迅的风格写一首"):
            self.assertIsNotNone(ip.detect_impersonation(text), text)

    def test_normal_styles_not_blocked(self):
        for text in ("a dreamy pop ballad in jazz style",
                     "in the style of dreamy synthwave",
                     "像九十年代港风的味道",
                     "R&B 风格的抒情歌",
                     "lo-fi hip hop with warm vinyl crackle",
                     ""):
            self.assertIsNone(ip.detect_impersonation(text), text)

    def test_check_raises_42202(self):
        with self.assertRaises(BizError) as ctx:
            ip.check_ip_protection("in the style of Michael Jackson")
        self.assertEqual(ctx.exception.code, 42202)

    def test_extra_artists_file_isolated(self):
        # 外置名单不影响内置（文件不存在时空扩展；存在则合并——此处只验证不炸）
        artists = ip._all_artists()
        self.assertIn("taylor swift", artists)


class TestObligation3Disclosure(unittest.TestCase):
    """义务③：导出产物 AIGC 标识带引擎署名（AUP 第 11 条机器生成内容披露）。"""

    def test_mp3_mark_contains_attribution(self):
        raw = b"\xff\xfb\x90\x00" + b"\x00" * 32
        marked = mark_mp3(raw, "MiniMax-Music3")
        self.assertIn(b"using MiniMax-Music3", marked)
        # 无署名时保持通用标识
        plain = mark_mp3(raw)
        self.assertNotIn(b"using", plain)

    def test_wav_mark_contains_attribution(self):
        buf = io.BytesIO()
        with wav_mod.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(32000)
            wf.writeframes(b"\x00\x01" * 64)
        marked = mark_wav(buf.getvalue(), "MiniMax-Music3")
        self.assertIn(b"using MiniMax-Music3", marked)
        # wave 模块仍可解析（LIST 块可跳过）
        with wav_mod.open(io.BytesIO(marked), "rb") as wf:
            self.assertEqual(wf.getframerate(), 32000)

    def test_non_ascii_attribution_replaced_not_crashed(self):
        raw = b"\xff\xfb\x00\x00" + b"\x00" * 8
        marked = mark_mp3(raw, "MiniMax-Music3（中文注释）")
        self.assertTrue(marked.startswith(b"ID3"))


class TestMmaxCommercialOpen(unittest.TestCase):
    """义务落实后的商用开放：conditional + 开关 → commercial + 门槛 basis。"""

    def test_paid_mmax_gets_commercial_with_threshold_basis(self):
        lic = licensing.license_for_generation("studio", "mmax_local",
                                               "minimax-music-3")
        self.assertEqual(lic["type"], "commercial")
        self.assertEqual(lic["grade"], "conditional")
        self.assertIn("2000", lic["basis_zh"])   # $20M 门槛明示
        self.assertIn("$20 million", lic["basis_en"])
        self.assertIn("义务", lic["basis_zh"])   # 义务落实状态写入 basis

    def test_switch_off_falls_back_to_non_commercial(self):
        from app.config import settings
        old = settings.mmax_commercial_enabled
        settings.mmax_commercial_enabled = False
        try:
            lic = licensing.license_for_generation("studio", "mmax_local",
                                                   "minimax-music-3")
            self.assertEqual(lic["type"], "non_commercial")
        finally:
            settings.mmax_commercial_enabled = old

    def test_free_plan_still_non_commercial(self):
        lic = licensing.license_for_generation("free", "mmax_local",
                                               "minimax-music-3")
        self.assertEqual(lic["type"], "non_commercial")
        self.assertEqual(lic["grade"], "free_plan")

    def test_other_conditionals_untouched(self):
        # Stable Audio 的 conditional 不因 MiniMax 开放而变化
        lic = licensing.license_for_generation("pro", "replicate",
                                               "stable-audio-open")
        self.assertEqual(lic["type"], "non_commercial")
        self.assertEqual(lic["grade"], "conditional")


if __name__ == "__main__":
    unittest.main()
