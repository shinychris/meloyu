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


if __name__ == "__main__":
    unittest.main()
