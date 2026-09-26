"""版本号一致性门禁（P1-15，2026-09-26）。

三处版本事实源必须一致，否则"线上到底是哪个版本"没有可信答案
（v0.12.2 曾实际翻车：APP_VERSION/package.json 停在 0.12.1）：
  ① backend/app/config.py 的 APP_VERSION
  ② frontend/package.json 的 version
  ③ CHANGELOG.md 最新版本条目标题

运行：.venv/Scripts/python.exe -m unittest tests.test_version_consistency -v
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from app.config import APP_VERSION

REPO = Path(__file__).resolve().parent.parent.parent
CHANGELOG = REPO / "CHANGELOG.md"
PACKAGE_JSON = REPO / "frontend" / "package.json"


class TestVersionConsistency(unittest.TestCase):
    def test_backend_frontend_changelog_aligned(self):
        pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(pkg["version"], APP_VERSION,
                         f"package.json({pkg['version']}) 与 APP_VERSION({APP_VERSION}) 不一致")

        first = next(
            (ln.strip() for ln in CHANGELOG.read_text(encoding="utf-8").splitlines()
             if ln.strip().startswith("## ")),
            "",
        )
        m = re.match(r"##\s*v(\d+\.\d+\.\d+)", first)
        self.assertIsNotNone(m, f"CHANGELOG 首个版本条目无法解析：{first!r}")
        self.assertEqual(m.group(1), APP_VERSION,
                         f"CHANGELOG 最新条目({m.group(1)}) 与 APP_VERSION({APP_VERSION}) 不一致")


if __name__ == "__main__":
    unittest.main()
