"""P0-9 回归（2026-09-26 商业化审查）：磁盘水位防护。

写入密集入口前置 disk_guard 检查；health 回报真实水位。本文件覆盖：
①低于阈值抛 40901（携带水位）；②充足时放行；③extra_bytes 抬高本次阈值；
④submit_generation 已接线（低水位拒绝提交）。

运行：.venv/Scripts/python.exe -m unittest tests.test_disk_guard -v
"""
from __future__ import annotations

import unittest
from unittest import mock

from app.config import settings
from app.core.disk_guard import disk_free_gb, ensure_disk_available
from app.core.errors import BizError


def _usage(free_gb: float):
    return mock.MagicMock(free=int(free_gb * (1 << 30)), total=1 << 40, used=0)

class TestDiskGuard(unittest.TestCase):
    def test_passes_when_plenty_free(self):
        with mock.patch("app.core.disk_guard.shutil.disk_usage",
                        return_value=_usage(500)):
            ensure_disk_available()  # 不抛
            self.assertGreater(disk_free_gb(), 100)

    def test_raises_when_below_threshold(self):
        with mock.patch("app.core.disk_guard.shutil.disk_usage",
                        return_value=_usage(5)):
            with self.assertRaises(BizError) as ctx:
                ensure_disk_available()
            self.assertEqual(ctx.exception.code, 40901)

    def test_extra_bytes_raises_threshold(self):
        # 剩 12GB>10GB 基线，但本次写入预估 3GB → 12 < 10+3 应拒绝
        with mock.patch("app.core.disk_guard.shutil.disk_usage",
                        return_value=_usage(12)):
            ensure_disk_available()
            with self.assertRaises(BizError):
                ensure_disk_available(extra_bytes=3 * (1 << 30))

    def test_threshold_configurable(self):
        with mock.patch.object(settings, "disk_min_free_gb", 1.0):
            with mock.patch("app.core.disk_guard.shutil.disk_usage",
                            return_value=_usage(5)):
                ensure_disk_available()

    def test_submit_generation_wired(self):
        # 接线验证：低水位时生成提交在扣积分/建任务前被拒
        from app.services import generation as gen
        db = mock.MagicMock()
        user = mock.MagicMock()
        payload = {"mode": "simple", "simple_prompt": "lofi chill",
                   "params": {"language": "zh"}}
        with mock.patch.object(gen, "check_generation_content"), \
             mock.patch.object(gen, "check_free_daily_limit"), \
             mock.patch.object(gen, "check_account_hourly_limit"), \
             mock.patch.object(gen, "check_inflight_limit"), \
             mock.patch.object(gen, "check_storage_quota"), \
             mock.patch("app.core.disk_guard.shutil.disk_usage",
                        return_value=_usage(1)):
            with self.assertRaises(BizError) as ctx:
                gen.submit_generation(db, user, payload)
            self.assertEqual(ctx.exception.code, 40901)
        db.add.assert_not_called()  # 未建 work/version/task

if __name__ == "__main__":
    unittest.main()
