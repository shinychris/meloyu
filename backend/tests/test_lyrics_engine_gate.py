"""歌词引擎守卫单测（v0.18.0）：离线规则引擎移除后的无兜底口径。

覆盖：
- current_lyrics_backend/get_lyrics_provider 的未配置判定（含历史遗留值归一）；
- 设置写入 localsynth（历史值）→ 归一为 none；
- /lyrics/generate 与 /lyrics/polish 未配置 → 40901 引导配置；
- 需要自动写词的生成提交未配置 → 40901；自带歌词不受影响；
- 歌词引擎通道异常如实报错（50002），不再静默回退。

运行：.venv/Scripts/python.exe -m unittest tests.test_lyrics_engine_gate -v
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.core.errors import BizError
from app.models import SETTING_ID, LLMSetting, User
from app.models.base import utc_now_iso
from app.services import generation as gen
from app.services import lyrics as lyrics_svc
from app.services import model_center
from tests.db import new_test_engine, reset_db

_VALID_LLM_JSON = json.dumps({
    "lyrics": "[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n便利店的灯还亮着\n"
              "[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心\n承诺若只剩回音\n"
              "至少今夜还有雨声",
    "alternatives": [],
}, ensure_ascii=False)


class _GateTestCase(unittest.TestCase):
    """每个用例独立内存库 + 一个用户。"""

    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        ts = utc_now_iso()
        self.user = User(id="u" + "x" * 31, email="u@t.dev", password_hash="x",
                         nickname="U", plan="studio",
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _set(self, **kw):
        row = LLMSetting(id=SETTING_ID, **kw)
        self.db.add(row)
        self.db.commit()
        return row


class LyricsEngineGateTest(_GateTestCase):
    """未配置/历史值归一：provider 为 None、通道族为 none、设置写读归一。"""

    def test_unconfigured_provider_is_none(self):
        self.assertIsNone(model_center.get_lyrics_provider(self.db))
        self.assertEqual(model_center.current_lyrics_backend(self.db), "none")

    def test_legacy_localsynth_reads_as_none(self):
        # 存量行历史值 localsynth（原离线规则引擎，已移除）视同未配置
        self._set(lyrics_backend="localsynth")
        self.assertIsNone(model_center.get_lyrics_provider(self.db))
        self.assertEqual(model_center.current_lyrics_backend(self.db), "none")

    def test_settings_write_normalizes_legacy_localsynth(self):
        out = model_center.update_settings(self.db, {"lyrics_backend": "localsynth"})
        self.assertEqual(out["lyrics_backend"], "none")

    def test_settings_accepts_none(self):
        out = model_center.update_settings(self.db, {"lyrics_backend": "none"})
        self.assertEqual(out["lyrics_backend"], "none")

    def test_settings_rejects_unknown_backend(self):
        with self.assertRaises(BizError) as ctx:
            model_center.update_settings(self.db, {"lyrics_backend": "bogus"})
        self.assertEqual(ctx.exception.code, 40001)


class LyricsServiceGateTest(_GateTestCase):
    """/lyrics/generate 与 /lyrics/polish：未配置 40901；LLM 异常 50002 如实上报。"""

    def test_generate_unconfigured_conflict(self):
        with self.assertRaises(BizError) as ctx:
            lyrics_svc.generate(self.db, theme="夜航", style_hint="", mood=None,
                                language="zh", sections=None)
        self.assertEqual(ctx.exception.code, 40901)
        # 双语任一口径（tr 按 locale 输出）
        self.assertTrue("歌词引擎未配置" in ctx.exception.message
                        or "not configured" in ctx.exception.message,
                        ctx.exception.message)

    def test_polish_unconfigured_conflict(self):
        with self.assertRaises(BizError) as ctx:
            lyrics_svc.polish(self.db, lyrics="[Verse]\n行一\n行二", target_section=None,
                              style_hint="", locked_lines=[])
        self.assertEqual(ctx.exception.code, 40901)

    def test_generate_with_fake_llm_channel(self):
        # openai_compat 配置齐全 + 假客户端：服务层正常产出（engine 透传，无 fallback 字段）
        self._set(lyrics_backend="openai_compat",
                  external_base_url="https://api.example.com/v1",
                  external_model="glm-4.7")
        fake_client = mock.MagicMock()
        fake_client.chat.return_value = _VALID_LLM_JSON
        with mock.patch.object(model_center, "OpenAICompatClient",
                               return_value=fake_client):
            out = lyrics_svc.generate(self.db, theme="雨夜", style_hint="", mood=None,
                                      language="zh", sections=None)
        self.assertEqual(out["engine"], "openai-compat:glm-4.7")
        self.assertNotIn("fallback", out)
        self.assertIn("[Chorus]", out["lyrics"])

    def test_rhyme_check_works_without_engine(self):
        # 确定性分析与引擎配置无关（未配置恒可用，响应不再带 engine/fallback）
        out = lyrics_svc.rhyme_check(self.db, "[Verse]\n行一\n行二")
        self.assertIn("sections", out)
        self.assertNotIn("engine", out)
        tags = lyrics_svc.complete_tags(self.db, "行一\n行二\n行三\n行四")
        self.assertTrue(tags["inferred"])


class SubmitAutoLyricsGateTest(_GateTestCase):
    """提交期守卫：需自动写词未配置 → 40901；自带歌词不受影响。"""

    def test_auto_lyrics_requires_engine(self):
        resolved = gen.resolve_generation_request(
            {"mode": "simple", "simple_prompt": "夜航西飞", "params": {"language": "zh"}})
        self.assertTrue(resolved["auto_lyrics"])
        with self.assertRaises(BizError) as ctx:
            gen.ensure_lyrics_engine_for_auto(self.db, resolved)
        self.assertEqual(ctx.exception.code, 40901)

    def test_auto_lyrics_passes_when_configured(self):
        self._set(lyrics_backend="ollama", ollama_model="qwen2.5:7b")
        resolved = gen.resolve_generation_request(
            {"mode": "simple", "simple_prompt": "夜航西飞", "params": {"language": "zh"}})
        gen.ensure_lyrics_engine_for_auto(self.db, resolved)  # 不抛

    def test_explicit_lyrics_bypasses_gate(self):
        resolved = gen.resolve_generation_request(
            {"mode": "custom", "style_prompt": "city pop", "lyrics": "[Verse]\n行一",
             "params": {"vocal": "female_air"}})
        self.assertFalse(resolved["auto_lyrics"])
        gen.ensure_lyrics_engine_for_auto(self.db, resolved)  # 不抛

    def test_instrumental_bypasses_gate(self):
        resolved = gen.resolve_generation_request(
            {"mode": "custom", "style_prompt": "ambient",
             "params": {"vocal": "instrumental"}})
        self.assertFalse(resolved["auto_lyrics"])
        gen.ensure_lyrics_engine_for_auto(self.db, resolved)  # 不抛


if __name__ == "__main__":
    unittest.main()
