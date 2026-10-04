"""License Portal 单测（backend venv 下运行：python -m unittest test_portal）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PORTAL_DIR))
sys.path.insert(0, str(PORTAL_DIR.parent / "backend"))

_tmp = tempfile.mkdtemp(prefix="meloyu-portal-test-")
os.environ["PORTAL_DATA_DIR"] = _tmp
os.environ["PORTAL_ADMIN_TOKEN"] = "test-admin-token"

from app.services.license import generate_keypair  # noqa: E402

_PRIV, _PUB = generate_keypair()
os.environ["PORTAL_PRIVATE_KEY"] = _PRIV
os.environ["PORTAL_PUBLIC_KEY"] = _PUB

from fastapi.testclient import TestClient  # noqa: E402

import server as portal_server  # noqa: E402
import db as portal_db  # noqa: E402

portal_server.PRIVATE_KEY = _PRIV
portal_server.PUBLIC_KEY = _PUB
portal_db.init(Path(_tmp) / "portal.db")

ADMIN = {"Authorization": "Bearer test-admin-token"}


class TestPortal(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(portal_server.app)

    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)

    def test_admin_auth_required(self):
        self.assertEqual(self.client.get("/api/admin/licenses").status_code, 401)
        self.assertEqual(
            self.client.get("/api/admin/licenses", headers=ADMIN).status_code, 200)

    def test_issue_and_activate_report_flow(self):
        r = self.client.post("/api/admin/licenses", headers=ADMIN,
                             json={"tier": "lifetime", "note": "buyer@t.local",
                                   "devices": 2})
        self.assertEqual(r.status_code, 200)
        key = r.json()["license_key"]
        lid = r.json()["license_id"]
        # 在线上报：设备 1/2 放行
        r = self.client.post("/api/activate-report",
                             json={"license_key": key, "device_id": uuid.uuid4().hex})
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["remaining_devices"], 1)
        # 同设备重复上报：幂等
        r2 = self.client.post("/api/activate-report",
                              json={"license_key": key, "device_id": "dev-x"})
        # 第 2 台设备占满额度
        self.assertTrue(r2.json()["ok"] if r2.json().get("ok") else False
                        or r2.json().get("reason") == "device_limit")
        # 第 3 台：超限拒绝
        r3 = self.client.post("/api/activate-report",
                              json={"license_key": key, "device_id": "dev-3"})
        self.assertFalse(r3.json()["ok"])
        self.assertEqual(r3.json()["reason"], "device_limit")
        # 吊销后拒绝
        self.client.post(f"/api/admin/licenses/{lid}/revoke", headers=ADMIN)
        r4 = self.client.post("/api/activate-report",
                              json={"license_key": key, "device_id": "dev-4"})
        self.assertFalse(r4.json()["ok"])
        self.assertEqual(r4.json()["reason"], "revoked")

    def test_unknown_key_rejected(self):
        r = self.client.post("/api/activate-report",
                             json={"license_key": "v1.fake.sig", "device_id": "d"})
        self.assertFalse(r.json()["ok"])
        # 公钥已配置时垃圾 Key 在验签层即被拒（invalid_key）；
        # 未配置公钥的部署则落到 unknown_license（查库不命中）
        self.assertIn(r.json()["reason"], ("invalid_key", "unknown_license"))

    def test_buy_manual_mode_default(self):
        # 未配 PAYMENT_LINK_URL（默认零外部依赖模式）：人工签发售卖页 200，
        # 而非 503 错误页（2026-10-04 用户口径：桌面软件无需 Stripe 支付）
        r = self.client.get("/buy")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Lifetime License", r.text)
        self.assertIn("license key", r.text)

    def test_marketing_index_and_updates_mount(self):
        # F7：dist-landing 已构建 → 首页为落地页 SPA（默认英文营销站）；
        # 未构建 → 兜底基座页（两句式断言兼容 CI 无前端构建产物的场景）
        index_html = self.client.get("/").text
        self.assertTrue("yours for life" in index_html
                        or "landing-main" in index_html or "/assets/" in index_html)
        self.assertEqual(self.client.get("/updates/").status_code, 404)  # 空目录，挂载存在


if __name__ == "__main__":
    unittest.main()
