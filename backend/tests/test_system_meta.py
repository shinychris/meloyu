"""v0.17.1 回归：/system/meta desktop 形态 data_dir 必须可 JSON 序列化。

真实桌面运行时发现（2026-10-28 模拟用户测试）：desktop 形态把 Path 对象
直接放进响应体，json.dumps 抛 TypeError → 50001。后果链——裸浏览器直连
桌面后端时前端 desktop 判定兜底失败（退化 cloud 卡登录页）、设置页
「数据目录」缺失、meta 枚举退化为前端 en 兜底。云形态不下发 data_dir。
"""
from __future__ import annotations

import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.database import get_db
from app.main import app
from tests.db import new_test_engine, reset_db


class SystemMetaDesktopTest(unittest.TestCase):
    """desktop 形态 /system/meta：data_dir 下发为字符串；cloud 形态不下发。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = (settings.data_dir, settings.app_mode)
        settings.data_dir = self.tmp.name
        settings.app_mode = "desktop"
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
        settings.data_dir, settings.app_mode = self._old
        self.tmp.cleanup()

    def test_desktop_meta_data_dir_serializable(self):
        resp = self.client.get("/api/v1/system/meta")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["app_mode"], "desktop")
        self.assertIsInstance(data["data_dir"], str)
        self.assertTrue(data["data_dir"])
        # 下发值即 settings.data_path 的字符串形态（设置页展示口径）
        self.assertEqual(data["data_dir"], str(settings.data_path))

    def test_cloud_meta_omits_data_dir(self):
        settings.app_mode = "cloud"
        try:
            resp = self.client.get("/api/v1/system/meta")
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertNotIn("data_dir", resp.json()["data"])
        finally:
            settings.app_mode = "desktop"


if __name__ == "__main__":
    unittest.main()
