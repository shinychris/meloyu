"""买断价格常量同源守门（2026-10-27）。

价格事实源是 app.config（portal 已改为直接 import，天然同源）；本测试钉住
前端 landing-data.ts 的两处字面量必须与 backend config 一致——缺这道守门时，
2026-10-17 的 $129 调价 README 就是漏网漂移实例。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.config import LICENSE_PRICE_USD, LICENSE_SALE_PRICE_USD

_LANDING = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "landing-data.ts"


class PriceConsistencyTest(unittest.TestCase):
    def test_frontend_landing_price_matches_config(self) -> None:
        text = _LANDING.read_text(encoding="utf-8")
        price_m = re.search(r"\bprice:\s*(\d+)", text)
        sale_m = re.search(r"\bsalePrice:\s*(\d+)", text)
        self.assertIsNotNone(price_m, "landing-data.ts 缺少 price 常量（结构变更时同步更新本测试）")
        self.assertIsNotNone(sale_m, "landing-data.ts 缺少 salePrice 常量（结构变更时同步更新本测试）")
        self.assertEqual(int(price_m.group(1)), LICENSE_PRICE_USD)
        self.assertEqual(int(sale_m.group(1)), LICENSE_SALE_PRICE_USD)

    def test_sale_price_not_above_list_price(self) -> None:
        self.assertLessEqual(LICENSE_SALE_PRICE_USD, LICENSE_PRICE_USD)


if __name__ == "__main__":
    unittest.main()
