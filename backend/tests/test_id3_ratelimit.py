"""AIGC 标识写入（P0-3）与限流中间件（P0-6）单测。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import io
import struct
import time
import unittest
import wave as wav_mod

from app.core.ratelimit import _RULES, _hit, _match_rule
from app.synth.id3 import AIGC_MARK_TEXT, id3v2_tag, mark_mp3, mark_wav


class TestAigcMp3Marking(unittest.TestCase):
    def test_tag_structure_and_payload_preserved(self):
        raw = b"\xff\xfb\x90\x00" + b"\x00" * 100
        marked = mark_mp3(raw)
        self.assertEqual(marked[:3], b"ID3")
        self.assertEqual(marked[3], 4)  # v2.4
        self.assertIn(b"TXXX", marked)
        self.assertIn(b"AIGC", marked)
        self.assertIn(b"COMM", marked)
        self.assertTrue(marked.endswith(raw), "原始 mp3 数据必须完整保留")
        # syncsafe 长度自洽：10 头 + tag 长度 = 前缀
        size = ((marked[6] & 0x7F) << 21) | ((marked[7] & 0x7F) << 14) | \
               ((marked[8] & 0x7F) << 7) | (marked[9] & 0x7F)
        self.assertEqual(10 + size + len(raw), len(marked))

    def test_existing_tag_appended_not_replaced(self):
        first = mark_mp3(b"\xff\xfb\x00\x00" + b"\x01" * 10)
        second = mark_mp3(first)
        self.assertEqual(second.count(b"ID3"), 2)
        self.assertTrue(second.endswith(b"\x01" * 10))

    def test_deterministic(self):
        self.assertEqual(id3v2_tag(), id3v2_tag())


class TestAigcWavMarking(unittest.TestCase):
    def _tiny_wav(self) -> bytes:
        buf = io.BytesIO()
        with wav_mod.open(buf, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x01\x00\x02\x00" * 100)
        return buf.getvalue()

    def test_list_info_injected_and_wave_readable(self):
        marked = mark_wav(self._tiny_wav())
        self.assertEqual(marked[:4], b"RIFF")
        self.assertIn(b"LIST", marked)
        self.assertIn(b"ICMT", marked)
        self.assertIn(AIGC_MARK_TEXT[:20].encode("ascii"), marked)
        # python wave 模块可跳过 LIST 块正常解析（导出登记读采样率依赖此）
        with wav_mod.open(io.BytesIO(marked), "rb") as wf:
            self.assertEqual(wf.getframerate(), 44100)
            self.assertEqual(wf.getnchannels(), 2)
            self.assertEqual(len(wf.readframes(wf.getnframes())), 400)
        # RIFF 总长字段正确
        declared = struct.unpack("<I", marked[4:8])[0]
        self.assertEqual(declared, len(marked) - 8)

    def test_non_riff_passthrough(self):
        junk = b"not a wav at all"
        self.assertEqual(mark_wav(junk), junk)


class TestRateLimit(unittest.TestCase):
    def test_rule_matching_longest_prefix_first(self):
        self.assertEqual(_match_rule("/api/v1/auth/login"), (60, 10))
        self.assertEqual(_match_rule("/api/v1/auth/register"), (3600, 20))
        self.assertEqual(_match_rule("/api/v1/auth/send-code"), (3600, 3))
        self.assertEqual(_match_rule("/api/v1/generations"), (3600, 30))
        # webhook 显式豁免（0,0）
        self.assertEqual(_match_rule("/api/v1/billing/webhook"), (0, 0))
        # 其余 API 全局兜底
        self.assertEqual(_match_rule("/api/v1/works"), (60, 300))
        self.assertIsNone(_match_rule("/api/docs"))

    def test_rules_ordered_specific_before_global(self):
        # 豁免/具体规则必须出现在 /api/v1/ 兜底之前
        prefixes = [r[0] for r in _RULES]
        self.assertLess(prefixes.index("/api/v1/billing/webhook"),
                        prefixes.index("/api/v1/"))

    def test_hit_window_exhaustion(self):
        calls = []
        for _ in range(10):
            calls.append(_hit("k", 60, 3))
        self.assertEqual(calls, [True, True, True, False, False, False, False,
                                 False, False, False])

    def test_hit_recovery_after_window(self):
        from app.core import ratelimit
        # 用已过期时间戳预填队列：窗口滑过后应放行
        now = time.monotonic()
        ratelimit._hits["recover-key"] = __import__("collections").deque(
            [now - 61, now - 61, now - 61])
        self.assertTrue(_hit("recover-key", 60, 3))


if __name__ == "__main__":
    unittest.main()
