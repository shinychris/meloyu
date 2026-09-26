"""i18n 单元测试（stdlib unittest，无新增依赖）。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
覆盖：Accept-Language 解析、tr/set_locale、纯 ASGI 中间件 contextvar 传播、
run_with_locale 线程恢复、目录英文展开完整性（无中文残留/技术字段不动）、阶段标签。
"""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.i18n import (
    LocaleMiddleware,
    current_locale,
    parse_accept_language,
    run_with_locale,
    set_locale,
    tr,
)
from app.providers.base import stage_label
from app.providers.music_catalog import MUSIC_CATALOG, localized_entry


class TestParseAcceptLanguage(unittest.TestCase):
    def test_zh_variants(self):
        for header in ("zh", "zh-CN", "zh-CN,zh;q=0.9,en;q=0.8", "ZH-TW", "zh-Hans"):
            self.assertEqual(parse_accept_language(header), "zh")

    def test_en_and_misc(self):
        for header in ("en", "en-US,en;q=0.9", "fr-CH", "ja", "*", "", None):
            self.assertEqual(parse_accept_language(header), "en")


class TestTr(unittest.TestCase):
    def tearDown(self):
        set_locale("en")  # 恢复默认，避免污染其他用例

    def test_default_is_en(self):
        set_locale("en")
        self.assertEqual(tr("中文", "English"), "English")

    def test_zh(self):
        set_locale("zh")
        self.assertEqual(tr("中文", "English"), "中文")

    def test_set_locale_fallback_on_unsupported(self):
        set_locale("fr")
        self.assertEqual(current_locale(), "en")
        self.assertEqual(tr("中文", "English"), "English")


class TestLocaleMiddleware(unittest.TestCase):
    """纯 ASGI 中间件：Accept-Language → contextvar → 下游（含同步端点线程池）。"""

    def _client(self) -> TestClient:
        app = FastAPI()
        app.add_middleware(LocaleMiddleware)

        @app.get("/echo")
        def echo():
            return {"locale": current_locale(), "msg": tr("排队中", "Queued")}

        return TestClient(app)

    def test_en_default_and_explicit(self):
        client = self._client()
        for headers, expected in ((None, "Queued"), ({"Accept-Language": "en"}, "Queued"),
                                  ({"Accept-Language": "zh"}, "排队中"),
                                  ({"Accept-Language": "zh-CN,zh;q=0.9"}, "排队中")):
            with self.subTest(headers=headers):
                body = client.get("/echo", headers=headers).json()
                self.assertEqual(body["msg"], expected)
                self.assertEqual(body["locale"], "zh" if expected == "排队中" else "en")

    def test_missing_header_defaults_en(self):
        body = self._client().get("/echo").json()
        self.assertEqual(body["locale"], "en")


class TestRunWithLocale(unittest.TestCase):
    def test_restores_previous_locale(self):
        set_locale("zh")
        try:
            out = {}
            run_with_locale("en", lambda: out.update(msg=tr("中", "en"), loc=current_locale()))
            self.assertEqual(out["msg"], "en")
            self.assertEqual(out["loc"], "en")
            self.assertEqual(current_locale(), "zh")  # 恢复现场
            self.assertEqual(tr("中", "en"), "中")
        finally:
            set_locale("en")

    def test_invalid_locale_falls_back_en(self):
        run_with_locale("jp", lambda: None)  # 不抛错


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in str(s or ""))


class TestCatalogLocalization(unittest.TestCase):
    def test_en_has_no_chinese_display_fields(self):
        set_locale("en")
        try:
            for m in MUSIC_CATALOG:
                e = localized_entry(m)
                for f in ("name", "vendor", "license", "params", "local_note",
                          "recommend_reason"):
                    self.assertFalse(_has_cjk(e.get(f)),
                                     f"{m['id']}.{f} still Chinese: {e.get(f)!r}")
                self.assertFalse(_has_cjk(e["capabilities"]["languages"]),
                                 f"{m['id']}.capabilities.languages still Chinese")
                for f in ("source", "notes"):
                    self.assertFalse(_has_cjk(e["benchmark"][f]),
                                     f"{m['id']}.benchmark.{f} still Chinese")
        finally:
            set_locale("en")

    def test_zh_returns_original_entries(self):
        set_locale("zh")
        try:
            for m in MUSIC_CATALOG:
                self.assertIs(localized_entry(m), m)  # zh 原样（同对象）
        finally:
            set_locale("en")

    def test_technical_fields_unchanged(self):
        set_locale("en")
        try:
            for m in MUSIC_CATALOG:
                e = localized_entry(m)
                for f in ("id", "channels", "local_hf_id", "local_size_mb",
                          "replicate_slug", "local_runnable", "recommended"):
                    self.assertEqual(e.get(f), m.get(f), f"{m['id']}.{f} must not change")
                self.assertEqual(e["benchmark"]["score"], m["benchmark"]["score"])
                self.assertEqual(e["capabilities"]["max_duration_sec"],
                                 m["capabilities"]["max_duration_sec"])
        finally:
            set_locale("en")


class TestStageLabels(unittest.TestCase):
    def test_bilingual(self):
        set_locale("en")
        self.assertEqual(stage_label("vocal"), "Synthesizing vocals")
        self.assertEqual(stage_label("done"), "Done")
        set_locale("zh")
        self.assertEqual(stage_label("vocal"), "人声合成")
        set_locale("en")


class TestTrEnglishHalvesSweep(unittest.TestCase):
    """静态扫描全部 tr(zh, en) 调用：英文侧（含 f-string 字面部分）不得出现中文。

    防回归网：后续新增 tr() 时英文侧误写中文会在本测试暴露。
    """

    def test_no_chinese_in_en_halves(self):
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "app"
        checked = 0
        problems: list[str] = []
        for py in root.rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if fname != "tr" or len(node.args) < 2:
                    continue
                parts: list[str] = []
                en_arg = node.args[1]
                for sub in ast.walk(en_arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        parts.append(sub.value)
                text = "".join(parts)
                if not text:
                    continue  # 全变量拼接，无法静态判定
                checked += 1
                if _has_cjk(text):
                    problems.append(f"{py.name}:{node.lineno} {text[:60]!r}")
        self.assertTrue(checked > 50, f"sweep unexpectedly scanned only {checked} calls")
        self.assertEqual(problems, [], "tr() English halves contain Chinese:\n"
                         + "\n".join(problems))


class TestEnglishOutputNoChinese(unittest.TestCase):
    """v0.7.2 i18n 收口回归：英文 locale 下各输出面零中文。"""

    def tearDown(self):
        set_locale("en")

    def test_rhyme_suggestion_en_uses_latin_finals(self):
        from app.providers.lyrics_local import LocalLyricsProvider
        lyrics = ("[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好长\n"
                  "[Chorus]\n我们把未来说得太轻\n像风穿过无人的巷口")
        set_locale("en")
        res = LocalLyricsProvider().rhyme_check(lyrics)
        lines_by_no = {ln["line_no"]: ln for sec in res["sections"] for ln in sec["lines"]}
        for s in res["suggestions"]:
            if s["type"] != "rhyme":
                continue
            # 引用的尾字本身是歌词内容（允许），剥离后不得再有中文（辙名等）
            stripped = s["message"].replace(lines_by_no[s["line_no"]]["tail_char"], "")
            self.assertFalse(_has_cjk(stripped),
                             f"en rhyme message has Chinese: {s['message']!r}")
        set_locale("zh")
        res_zh = LocalLyricsProvider().rhyme_check(lyrics)
        self.assertTrue(any(_has_cjk(s["message"]) for s in res_zh["suggestions"]
                            if s["type"] == "rhyme"), "zh 侧应保持中文文案")

    def test_style_tags_en(self):
        from app.providers.music_local import _style_tags
        set_locale("en")
        tags = _style_tags("", "guofeng")
        self.assertEqual(tags, ["Chinese traditional"])
        set_locale("zh")
        self.assertEqual(_style_tags("", "guofeng"), ["国风"])

    def test_synth_raise_messages_bilingual(self):
        import tempfile
        import wave
        from types import SimpleNamespace

        import numpy as np
        from app.synth import editing as editing_mod
        from app.synth import wav_io as wav_mod
        from app.synth.ir import SAMPLE_RATE

        set_locale("en")
        with self.assertRaises(ValueError) as ctx:
            editing_mod.regenerate_sections(
                SimpleNamespace(sections=[]), "chorus", 1, None)  # type: ignore[arg-type]
        self.assertFalse(_has_cjk(str(ctx.exception)),
                         f"editing en message has Chinese: {ctx.exception!r}")
        with self.assertRaises(ValueError) as ctx2:
            editing_mod.splice_regen(np.zeros(100), np.zeros(90), None, 0)  # type: ignore[arg-type]
        self.assertFalse(_has_cjk(str(ctx2.exception)),
                         f"splice en message has Chinese: {ctx2.exception!r}")
        # 错采样率的真实 wav → read_wav 触发采样率不符
        import pathlib
        wrong_sr = pathlib.Path(tempfile.gettempdir()) / "meloyu_test_wrong_sr.wav"
        with wave.open(str(wrong_sr), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE // 2)
            wf.writeframes(b"\x00\x00" * 8)
        try:
            with self.assertRaises(ValueError) as ctx3:
                wav_mod.read_wav(wrong_sr)
            self.assertFalse(_has_cjk(str(ctx3.exception)),
                             f"wav_io en message has Chinese: {ctx3.exception!r}")
        finally:
            wrong_sr.unlink(missing_ok=True)
        set_locale("zh")
        with self.assertRaises(ValueError) as ctx4:
            editing_mod.splice_regen(np.zeros(100), np.zeros(90), None, 0)  # type: ignore[arg-type]
        self.assertTrue(_has_cjk(str(ctx4.exception)), "zh 侧应保持中文文案")

    def test_expand_style_llm_en_prompt(self):
        from app.services import generation as gen
        captured = {}

        def fake_chat(system: str, user: str) -> str:
            captured["system"], captured["user"] = system, user
            return ("A warm indie-pop ballad with soft piano arpeggios, airy synth "
                    "pads, gentle percussion, and an emotionally building bridge.")

        set_locale("en")
        out = gen.expand_style_by_llm(fake_chat, "a rainy night in the city")
        self.assertFalse(_has_cjk(out))
        self.assertFalse(_has_cjk(captured["system"]))
        self.assertFalse(_has_cjk(captured["user"]))
        set_locale("zh")
        gen.expand_style_by_llm(fake_chat, "城市雨夜")
        self.assertTrue(_has_cjk(captured["system"]))

    def test_mail_single_language_per_locale(self):
        # v0.14.0：验证码落库（send/verify/consume 均带 db），邮件文案口径不变
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from unittest.mock import patch
        from app import models  # noqa: F401
        from app.models import Base
        from app.services import mail
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        sent: list[tuple[str, str, str]] = []
        with patch.object(mail, "_send", lambda to, subject, body: sent.append((to, subject, body))):
            with patch.object(mail, "smtp_configured", lambda: True):
                set_locale("en")
                mail.send_verification_code(db, "u@x.com")
                mail.send_password_reset_email("u@x.com", "https://r")
                set_locale("zh")
                mail.send_verification_code(db, "u2@x.com")
                mail.send_password_reset_email("u2@x.com", "https://r")
        en_sub, en_body = sent[0][1], sent[0][2]
        self.assertFalse(_has_cjk(en_sub), f"en mail subject has Chinese: {en_sub!r}")
        self.assertFalse(_has_cjk(en_body), f"en mail body has Chinese: {en_body!r}")
        self.assertFalse(_has_cjk(sent[1][1]) or _has_cjk(sent[1][2]))
        self.assertTrue(_has_cjk(sent[2][1]) and _has_cjk(sent[3][2]))
        # 验证码落库可校验（10 分钟内有效）
        code_row = db.execute(
            __import__("sqlalchemy").select(
                __import__("app.models", fromlist=["EmailCode"]).EmailCode)
        ).scalars().first()
        self.assertIsNotNone(code_row)
        mail.consume_code(db, "u@x.com")
        mail.consume_code(db, "u2@x.com")


if __name__ == "__main__":
    unittest.main()
