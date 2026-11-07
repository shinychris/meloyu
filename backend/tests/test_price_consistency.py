"""价格口径守门（2026-11-06 开源免费口径调整）。

对外展示面（落地页 / portal 页面）已转为开源免费口径，不再出现付费价格；
价格事实源仅保留在 app.config，供计费功能使用（billing API 下发、
既有授权与企业/商用证书服务）。本测试钉住两件事：

1. 前端 landing-data.ts 不再内嵌付费价格字面量（防免费口径回退）；
2. app.config 价格常量保持计费不变式（0 < SALE ≤ PRICE）。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.config import LICENSE_PRICE_USD, LICENSE_SALE_PRICE_USD

_LANDING = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "landing-data.ts"


class PriceConsistencyTest(unittest.TestCase):
    def test_frontend_landing_carries_no_paid_price(self) -> None:
        """落地页数据源为开源免费口径：不得再出现 price/salePrice 付费字面量。"""
        text = _LANDING.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"\b(price|salePrice):\s*\d", text),
            "落地页已转开源免费口径，不应再内嵌付费价格字面量（结构变更时同步更新本测试）",
        )

    def test_backend_price_config_invariants(self) -> None:
        """计费功能保留：价格常量仍满足 0 < SALE ≤ PRICE（既有授权/企业服务在用）。"""
        self.assertGreater(LICENSE_PRICE_USD, 0)
        self.assertLessEqual(LICENSE_SALE_PRICE_USD, LICENSE_PRICE_USD)


if __name__ == "__main__":
    unittest.main()
