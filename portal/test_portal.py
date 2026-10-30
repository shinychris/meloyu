"""License Portal 单测（backend venv 下运行：python -m unittest test_portal）。"""
from __future__ import annotations

import atexit
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PORTAL_DIR))
sys.path.insert(0, str(PORTAL_DIR.parent / "backend"))

# 评审 F-XC-07：临时目录用 TemporaryDirectory + atexit 自动清理，
# 不再在仓库根残留 .ptmp_check 类产物
_tmpdir = tempfile.TemporaryDirectory(prefix="meloyu-portal-test-")
atexit.register(_tmpdir.cleanup)
os.environ["PORTAL_DATA_DIR"] = _tmpdir.name
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
portal_db.init(Path(_tmpdir.name) / "portal.db")
# server._startup（lifespan）负责创建 updates 目录，但 TestClient 不跑 lifespan——
# 此处手工补齐（starlette 1.6 对挂载目录做请求期存在性检查）
(Path(_tmpdir.name) / "updates").mkdir(parents=True, exist_ok=True)

ADMIN = {"Authorization": "Bearer test-admin-token"}


class TestPortal(unittest.TestCase):
    def setUp(self):
        # 限流器进程内累计（同一 TestClient 来源 IP），用例间清零互不干扰
        portal_server.ADMIN_LIMITER.reset()
        portal_server.ACTIVATE_LIMITER.reset()
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
        # 同设备重复上报：幂等；第 2 台设备占满额度（devices=2 → 两台均放行）
        r2 = self.client.post("/api/activate-report",
                              json={"license_key": key, "device_id": "dev-x"})
        self.assertTrue(r2.json()["ok"])  # 评审 F-PT-13：显式断言替换恒真绕断言
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

    def test_activation_code_online_redeem_flow(self):
        # 签发（带账户）→ 激活码兑换全链路：成功/账户不符/未知码/吊销/设备满额
        r = self.client.post("/api/admin/licenses", headers=ADMIN,
                             json={"tier": "lifetime", "account": "buyer@t.local",
                                   "devices": 1})
        self.assertEqual(r.status_code, 200)
        code = r.json()["activation_code"]
        self.assertRegex(code, r"^MELOYU-[A-Z2-9]{8}-[A-Z2-9]{8}$")
        dev = {"device_id": "dev-1"}
        # 账户不符 → 拒绝
        bad = self.client.post("/api/activate",
                               json={"account": "other@t.local", "code": code, **dev})
        self.assertFalse(bad.json()["ok"])
        self.assertEqual(bad.json()["reason"], "account_mismatch")
        # 正确账户 → 兑换出完整签名密钥
        ok = self.client.post("/api/activate",
                              json={"account": "buyer@t.local", "code": code, **dev})
        d = ok.json()
        self.assertTrue(d["ok"])
        self.assertTrue(d["license_key"].startswith("v1."))
        self.assertEqual(d["tier"], "lifetime")
        # 同设备重复兑换：幂等放行
        ok2 = self.client.post("/api/activate",
                               json={"account": "buyer@t.local", "code": code, **dev})
        self.assertTrue(ok2.json()["ok"])
        # 第 2 台设备：devices=1 → 满额拒绝
        full = self.client.post("/api/activate",
                                json={"account": "buyer@t.local", "code": code,
                                      "device_id": "dev-2"})
        self.assertFalse(full.json()["ok"])
        self.assertEqual(full.json()["reason"], "device_limit")
        # 未知激活码
        unknown = self.client.post("/api/activate",
                                   json={"account": "buyer@t.local",
                                         "code": "MELOYU-AAAAAAAA-AAAAAAAA", **dev})
        self.assertEqual(unknown.json()["reason"], "invalid_code")
        # 吊销后拒绝
        lid = r.json()["license_id"]
        self.client.post(f"/api/admin/licenses/{lid}/revoke", headers=ADMIN)
        revoked = self.client.post("/api/activate",
                                   json={"account": "buyer@t.local",
                                         "code": code, "device_id": "dev-3"})
        self.assertEqual(revoked.json()["reason"], "revoked")

    def test_buy_manual_mode_default(self):
        # 未配 PAYMENT_LINK_URL（默认零外部依赖模式）：人工签发售卖页 200，
        # 而非 503 错误页（2026-10-04 用户口径：桌面软件无需 Stripe 支付）
        r = self.client.get("/buy")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Lifetime License", r.text)
        # 2026-10-04 口径：邮件交付账户+激活码
        self.assertIn("activation email", r.text)
        self.assertIn("activation code", r.text)

    def test_device_unbind_frees_quota(self):
        """换机解绑（2026-10-16 补全）：满额设备解绑后新设备可激活。"""
        r = self.client.post("/api/admin/licenses", headers=ADMIN,
                             json={"tier": "lifetime", "account": "swap@t.local",
                                   "devices": 1})
        lid = r.json()["license_id"]
        code = r.json()["activation_code"]
        self.assertTrue(self.client.post("/api/activate", json={
            "account": "swap@t.local", "code": code, "device_id": "old-pc"}).json()["ok"])
        # 满额：新机被拒
        full = self.client.post("/api/activate", json={
            "account": "swap@t.local", "code": code, "device_id": "new-mac"})
        self.assertEqual(full.json()["reason"], "device_limit")
        # 管理端解绑旧机 → 新机激活成功
        un = self.client.delete(f"/api/admin/activations/{lid}/old-pc", headers=ADMIN)
        self.assertEqual(un.status_code, 200)
        self.assertTrue(un.json()["unbound"])
        ok = self.client.post("/api/activate", json={
            "account": "swap@t.local", "code": code, "device_id": "new-mac"})
        self.assertTrue(ok.json()["ok"])
        # 解绑不存在的记录 → 404
        nf = self.client.delete(f"/api/admin/activations/{lid}/ghost", headers=ADMIN)
        self.assertEqual(nf.status_code, 404)
        # 鉴权同其他 admin 端点
        self.assertEqual(
            self.client.delete(f"/api/admin/activations/{lid}/new-mac").status_code, 401)

    def test_generic_code_binds_account_on_first_redeem(self):
        """通用码首触绑定（2026-10-16）：未指定账户的码首次兑换锁定账户，
        他账户再兑被拒（account_mismatch）。"""
        r = self.client.post("/api/admin/licenses", headers=ADMIN,
                             json={"tier": "lifetime", "devices": 3})  # 未填 account
        self.assertEqual(r.status_code, 200)
        code = r.json()["activation_code"]
        first = self.client.post("/api/activate", json={
            "account": "first@t.local", "code": code, "device_id": "d1"})
        self.assertTrue(first.json()["ok"])
        second = self.client.post("/api/activate", json={
            "account": "stranger@t.local", "code": code, "device_id": "d2"})
        self.assertFalse(second.json()["ok"])
        self.assertEqual(second.json()["reason"], "account_mismatch")

    def test_marketing_index_and_updates_mount(self):
        # F7：dist-landing 已构建 → 首页为落地页 SPA（默认英文营销站）；
        # 未构建 → 兜底基座页（两句式断言兼容 CI 无前端构建产物的场景）
        index_html = self.client.get("/").text
        self.assertTrue("yours for life" in index_html
                        or "landing-main" in index_html or "/assets/" in index_html)
        self.assertEqual(self.client.get("/updates/").status_code, 404)  # 空目录，挂载存在

    # ---------------- 评审整改新增（F-PT-02/03/04/05/07/08/09/10/11） ----------------

    def test_activate_rate_limited(self):
        """F-PT-03：/api/activate 按 IP 限流 10/min，超限 429（防激活码枚举/
        签名密钥刷取）。"""
        body = {"account": "rl@t.local", "code": "MELOYU-AAAAAAAA-AAAAAAAA",
                "device_id": "d"}
        for _ in range(10):
            r = self.client.post("/api/activate", json=body)
            self.assertEqual(r.status_code, 200)  # 业务层 invalid_code，未触发限流
        self.assertEqual(self.client.post("/api/activate", json=body).status_code, 429)

    def test_admin_rate_limited_and_failures_counted(self):
        """F-PT-02：admin 端点 30/min/IP；鉴权失败路径同样计数——
        连续 30 次无凭据 401 后，携带正确 token 的请求也被限流。"""
        for _ in range(30):
            self.assertEqual(self.client.get("/api/admin/licenses").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/licenses", headers=ADMIN).status_code,
                         429)

    def test_admin_issue_validation_422(self):
        """F-PT-07：devices/seats 越界或非数字 → 422（不再 500），合法值放行。"""
        for devices in (0, 11, "abc", None):
            r = self.client.post("/api/admin/licenses", headers=ADMIN,
                                 json={"tier": "lifetime", "devices": devices})
            self.assertEqual(r.status_code, 422, f"devices={devices!r}")
        r = self.client.post("/api/admin/licenses", headers=ADMIN,
                             json={"tier": "enterprise", "seats": 0})
        self.assertEqual(r.status_code, 422)
        ok = self.client.post("/api/admin/licenses", headers=ADMIN,
                              json={"tier": "lifetime", "devices": 1})
        self.assertEqual(ok.status_code, 200)

    def test_admin_keygen_removed(self):
        """F-PT-04：keygen 端点删除——私钥一律离线 license_tools 生成，不经 HTTP。

        （状态码随 dist-landing 是否构建而异：未构建 404；已构建被兜底 "/"
        StaticFiles 挂载接住 → 405，两形态皆非 200 即端点确不存在）"""
        routes = {getattr(r, "path", None) for r in portal_server.app.routes}
        self.assertNotIn("/api/admin/keygen", routes)
        r = self.client.post("/api/admin/keygen", headers=ADMIN)
        self.assertNotEqual(r.status_code, 200)
        self.assertNotIn("private_key", r.text)

    def test_thanks_session_id_validated(self):
        """F-PT-10：/thanks 的 session_id 强格式校验（防拼入 Stripe API 路径）；
        放行页面带 Cache-Control: no-store（F-PT-05）。"""
        self.assertEqual(self.client.get("/thanks").status_code, 422)
        self.assertEqual(self.client.get("/thanks", params={"session_id": "../evil"}).status_code,
                         422)
        self.assertEqual(self.client.get("/thanks", params={"session_id": "cs_x_bad"}).status_code,
                         422)
        # 合法格式（本部署未配 Stripe）→ 未启用提示页 200 且 no-store
        r = self.client.get("/thanks", params={"session_id": "cs_test_ABCdef123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("cache-control"), "no-store")

    def test_buy_escapes_contact(self):
        """F-PT-05：/buy 的联系人邮箱插值经 html.escape（防御纵深）。"""
        portal_server.SALES_EMAIL = '"><script>alert(1)</script>'
        try:
            r = self.client.get("/buy")
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("<script>", r.text)
            self.assertIn("&lt;script&gt;", r.text)
        finally:
            portal_server.SALES_EMAIL = ""

    def test_mask_code(self):
        """F-PT-08：激活码日志脱敏——前5后3，短/空输入整体打码。"""
        full = "MELOYU-ABCD2345-EFGH6789"
        masked = portal_server.mask_code(full)
        self.assertEqual(masked, "MELOY…789")
        self.assertNotIn(full, masked)
        self.assertNotIn("ABCD2345", masked)
        self.assertEqual(portal_server.mask_code(""), "MELOYU-***")
        self.assertEqual(portal_server.mask_code("short"), "MELOYU-***")

    def test_price_constants_from_backend_config(self):
        """F-PT-11：价格常量与 backend config 同源（删除本地重复定义）。"""
        import app.config as cfg
        self.assertEqual(portal_server.PRICE_USD, cfg.LICENSE_PRICE_USD)
        self.assertEqual(portal_server.SALE_PRICE_USD, cfg.LICENSE_SALE_PRICE_USD)

    def test_sqlite_wal_and_fk(self):
        """F-PT-09：WAL 持久化生效；activations.lid 外键约束生效（悬空引用被拒）。"""
        with portal_db.conn() as c:
            mode = c.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")
        with self.assertRaises(sqlite3.IntegrityError):
            with portal_db.conn() as c:
                c.execute("INSERT INTO activations (lid, device_id, activated_at, "
                          "last_seen_at) VALUES ('no-such-lid', 'd', 't', 't')")


if __name__ == "__main__":
    unittest.main()
