"""歌词创作链路单测。

覆盖：括号表演标记剥离（parse_lyrics 层，合成/韵脚/行号全线安全）；
LLM 生成提示词（想法驱动 + 括号标记指令，坏输出如实上抛不静默兜底）；
LyricGenerateRequest.theme 放宽到 600 字；/system/meta 下发段落 desc 与
performance_marks。

运行：.venv/Scripts/python.exe -m unittest tests.test_lyrics_creation -v
"""
from __future__ import annotations

import json
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.enums import SECTIONS
from app.providers.llm.base import LLMError
from app.providers.lyrics_llm import LLMLyricsProvider
from app.schemas.auth import LyricGenerateRequest
from app.synth.structure import parse_lyrics, plan_sections, strip_paren_marks
from tests.db import new_test_engine, reset_db


class StripParenMarksTest(unittest.TestCase):
    """括号表演标记剥离：中英括号、独立行、行内、行尾。"""

    def test_strip_variants(self):
        cases = {
            "（轻声吟唱）": "",
            "(piano interlude)": "",
            "（轻声吟唱）我们把未来说得太轻": "我们把未来说得太轻",
            "我们把未来说得太轻（渐弱）": "我们把未来说得太轻",
            "leave the door open (soft)": "leave the door open",
            "无标记的普通行": "无标记的普通行",
        }
        for line, expect in cases.items():
            self.assertEqual(strip_paren_marks(line), expect, line)

    def test_parse_inline_and_standalone_marks(self):
        lyrics = (
            "[Verse]\n（钢琴渐入）\n（轻声吟唱）雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n"
            "[Chorus]\n我们把未来说得太轻（渐弱）\n（合唱）像风穿过无人的街心"
        )
        parsed, has_tags = parse_lyrics(lyrics)
        self.assertTrue(has_tags)
        self.assertEqual(
            parsed,
            [("verse", ["雨停在凌晨三点的窗台", "霓虹把影子拉得好白"]),
             ("chorus", ["我们把未来说得太轻", "像风穿过无人的街心"])],
        )

    def test_parse_without_marks_unchanged(self):
        parsed, has_tags = parse_lyrics("[Verse]\n行一\n行二")
        self.assertTrue(has_tags)
        self.assertEqual(parsed, [("verse", ["行一", "行二"])])

    def test_plan_sections_tolerates_marks(self):
        # 带标记歌词照常规划段落（纯标记行不产生可唱行，但段落不丢）
        lyrics = "[Intro]\n（弦乐铺底）\n[Verse]\n（轻声）行一\n行二\n[Outro]"
        parsed, has_tags = parse_lyrics(lyrics)
        plans, inferred = plan_sections(parsed, has_tags, bpm=120,
                                        time_signature="4/4", duration_sec=60)
        self.assertFalse(inferred)
        self.assertEqual([p.section for p in plans], ["intro", "verse", "outro"])

class _CapturedChat:
    """捕获 system/prompt 的假 chat；按构造时响应序列返回。"""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self._replies.pop(0)

SAMPLE_LYRICS = (
    "[Verse]\n（钢琴渐入）\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n"
    "便利店的灯还亮着\n像没说完的对白\n[Chorus]\n（轻声吟唱）我们把未来说得太轻\n"
    "像风穿过无人的街心\n承诺若只剩回音\n至少今夜还有雨声"
)

class LLMPromptTest(unittest.TestCase):
    """LLM Provider：生成提示词含想法驱动与括号标记指令；带标记歌词全链路可用。"""

    def _provider(self, replies: list[str]) -> tuple[LLMLyricsProvider, _CapturedChat]:
        chat = _CapturedChat(replies)
        return LLMLyricsProvider(chat=chat, engine="fake-llm", display_name="Fake LLM"), chat

    def test_generate_prompt_mentions_idea_and_marks(self):
        long_idea = "雨夜便利店等待的故事，" * 12  # >100 字：v0.12.3 起合法
        provider, chat = self._provider(
            [json.dumps({"lyrics": SAMPLE_LYRICS, "alternatives": []}, ensure_ascii=False)])
        out = provider.generate(long_idea, mood="忧郁")
        system, prompt = chat.calls[0]
        self.assertIn("括号表演标记", system)
        self.assertIn("创作想法", prompt)
        self.assertIn(long_idea, prompt)
        self.assertIn("（轻声吟唱）", prompt)  # 示例标记进入指令
        self.assertNotIn("fallback", out)  # 无兜底引擎，回退字段退役
        # 返回的歌词原文保留标记（供支持标记的歌唱引擎消费）
        self.assertIn("（轻声吟唱）", out["lyrics"])
        # structure 按剥离标记后的真实行计（chorus 4 行）
        by_sec = {d["section"]: d["line_count"] for d in out["structure"]}
        self.assertEqual(by_sec["verse"], 4)
        self.assertEqual(by_sec["chorus"], 4)

    def test_generate_marks_not_counted_as_lines(self):
        # 全标记行不算内容行：行数校验按真实歌词行
        lyrics = "[Verse]\n（轻声）行一\n[Chorus]\n（合唱）行二\n行三\n行四\n行五"
        provider, chat = self._provider(
            [json.dumps({"lyrics": lyrics, "alternatives": []}, ensure_ascii=False)])
        out = provider.generate("主题")
        self.assertNotIn("fallback", out)

    def test_polish_prompt_keeps_marks(self):
        provider, chat = self._provider(
            [json.dumps({"lyrics": SAMPLE_LYRICS}, ensure_ascii=False)])
        out = provider.polish(SAMPLE_LYRICS)
        _, prompt = chat.calls[0]
        self.assertIn("括号表演标记", prompt)
        self.assertNotIn("fallback", out)

    def test_bad_output_raises_no_silent_fallback(self):
        # 坏输出不再静默回退规则引擎，如实上抛 LLMError 由服务层报错
        provider, _ = self._provider(["这不是 JSON"])
        with self.assertRaises(LLMError):
            provider.generate("主题")

class ThemeSchemaTest(unittest.TestCase):
    """LyricGenerateRequest.theme：1~600 字（v0.12.3 想法输入）。"""

    def test_long_idea_accepted(self):
        req = LyricGenerateRequest(theme="想" * 600)
        self.assertEqual(len(req.theme), 600)

    def test_over_limit_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            LyricGenerateRequest(theme="想" * 601)

    def test_empty_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            LyricGenerateRequest(theme="")

class MetaLyricsCreationTest(unittest.TestCase):
    """/system/meta：段落 desc 说明 + performance_marks 词表（zh 默认 locale）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = new_test_engine()
        reset_db(self.engine)

        def _test_db():
            session = sessionmaker(bind=self.engine)()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _test_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        settings.data_dir = self._old
        self.tmp.cleanup()

    def test_structure_tags_have_desc(self):
        data = self.client.get("/api/v1/system/meta",
                               headers={"Accept-Language": "zh"}).json()["data"]
        tags = data["structure_tags"]
        self.assertEqual(len(tags), len(SECTIONS))
        for tg in tags:
            self.assertTrue(tg.get("desc"), f"{tg['section']} 缺 desc")
        by_sec = {tg["section"]: tg for tg in tags}
        self.assertIn("叙事", by_sec["verse"]["desc"])
        self.assertIn("记忆点", by_sec["chorus"]["desc"])

    def test_performance_marks_delivered(self):
        data = self.client.get("/api/v1/system/meta",
                               headers={"Accept-Language": "zh"}).json()["data"]
        marks = data["performance_marks"]
        self.assertGreaterEqual(len(marks), 14)
        values = [m["mark"] for m in marks]
        for mark in ("（轻声吟唱）", "（合唱）", "（钢琴间奏）", "（渐强）"):
            self.assertIn(mark, values)
        groups = {m["group"] for m in marks}
        self.assertEqual(groups, {"vocal", "music"})
        # 标记须与解析层的剥离规则兼容（成对中文括号）
        for m in marks:
            parsed, _ = parse_lyrics(f"[Verse]\n{m['mark']}行一")
            self.assertEqual(parsed[0][1], ["行一"], m["mark"])

if __name__ == "__main__":
    unittest.main()
