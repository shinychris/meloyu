"""auth 账号体系（P1-3）+ 买断制 License（B2/B12）+ 计量模式（B5）单测。

2026-10-03 定位转型：Stripe 订阅链路已拆除（B3），本文件覆盖——
- 账号体系（注册/刷新轮换/改密/注销/导出）行为不变；
- License Ed25519 签发/验签/激活/幂等/解除；
- 试用闸门（D-2：14 天试用，到期未激活 40203 拦截生成/导出）；
- license 模式积分纯计量（不扣减不拒绝）+ 月度发放水位拆除；
- switch_plan 在 cloud/license 两模式下的引导语义。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
全部走内存 SQLite（services 层直调，不起 HTTP 服务）。
"""
from __future__ import annotations

import json
import unittest

from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.core.errors import BizError
from app.models import CreditTransaction, Plan, Subscription, User
from app.models.base import utc_now_iso
from app.services import auth as auth_svc
from app.services import billing as billing_svc
from app.services import license as license_svc
from tests.db import new_test_engine, reset_db


class _DBTestCase(unittest.TestCase):
    """每个用例独立内存库。"""

    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # 三个订阅档位（外键与限额依赖）
        ts = utc_now_iso()
        self.db.add_all([
            Plan(code="free", name="Free", price_monthly=None, price_yearly=None,
                 daily_generations=5, monthly_credits=None, max_export="mp3",
                 commercial_license=False, watermark=True, features=[],
                 switchable=True, sort_order=0, created_at=ts, updated_at=ts),
            Plan(code="pro", name="Pro", price_monthly=58, price_yearly=46,
                 daily_generations=None, monthly_credits=2500, max_export="wav",
                 commercial_license=True, watermark=False, features=[],
                 switchable=True, sort_order=1, created_at=ts, updated_at=ts),
            Plan(code="studio", name="Studio", price_monthly=168, price_yearly=134,
                 daily_generations=None, monthly_credits=10000, max_export="wav",
                 commercial_license=True, watermark=False, features=[],
                 switchable=True, sort_order=2, created_at=ts, updated_at=ts),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()


class TestAuthFlow(_DBTestCase):
    EMAIL = "u1@test.local"

    def _register(self) -> tuple[dict, str]:
        """注册并返回 (响应体, refresh token)——v0.13.0 起 refresh 不再进响应体
        （HttpOnly Cookie 通道，服务层返回 (body, refresh, ttl) 三元组）。"""
        out, refresh, _ttl = auth_svc.register(self.db, self.EMAIL, "Passw0rd123", "tester")
        return out, refresh

    def test_register_grants_bonus_and_admin_flag(self):
        settings.admin_emails = "u1@test.local"
        try:
            out, refresh = self._register()
        finally:
            settings.admin_emails = ""
        user = self.db.query(User).filter(User.email == self.EMAIL).one()
        self.assertTrue(user.is_admin)
        self.assertEqual(user.credit_balance, 200)
        self.assertTrue(out["access_token"])
        self.assertTrue(refresh)
        self.assertNotIn("refresh_token", out, "refresh 必须走 HttpOnly Cookie，不进响应体")

    def test_refresh_rotation_and_revocation(self):
        _out, stale = self._register()
        first_hash = self.db.query(User).one().refresh_token_hash
        out, new_refresh, _ttl = auth_svc.refresh(self.db, stale)
        user = self.db.query(User).one()
        self.assertNotEqual(user.refresh_token_hash, first_hash, "轮换必须覆写")
        # 轮换后旧 refresh 立即失效
        with self.assertRaises(BizError):
            auth_svc.refresh(self.db, stale)
        # 新 refresh 可用
        again, again_refresh, _ = auth_svc.refresh(self.db, new_refresh)
        self.assertTrue(again["access_token"])
        self.assertTrue(again_refresh)

    def test_logout_revokes(self):
        self._register()
        user = self.db.query(User).one()
        auth_svc.logout(self.db, user)
        self.assertIsNone(user.refresh_token_hash)
        with self.assertRaises(BizError):
            auth_svc.refresh(self.db, "whatever-token")

    def test_change_password_revokes_sessions(self):
        self._register()
        user = self.db.query(User).one()
        auth_svc.change_password(self.db, user, "Passw0rd123", "NewPass456")
        self.assertIsNone(user.refresh_token_hash)
        self.assertTrue(auth_svc.login(self.db, self.EMAIL, "NewPass456"))

    def test_reset_password_via_token(self):
        self._register()
        user = self.db.query(User).one()
        from app.core.security import create_reset_token
        token = create_reset_token(user)
        auth_svc.reset_password(self.db, token, "Reset789pass")
        self.assertTrue(auth_svc.login(self.db, self.EMAIL, "Reset789pass"))
        # access token 禁用作凭证：reset typ 的 JWT 不能过 get_current_user 校验
        from app.core.errors import BizError as BE
        with self.assertRaises(BE):
            from app.core.security import decode_access_token
            decode_access_token(token)

    def test_delete_account_anonymizes_and_removes_works(self):
        self._register()
        user = self.db.query(User).one()
        out = auth_svc.delete_account(self.db, user, "Passw0rd123")
        self.assertTrue(out["ok"])
        self.db.refresh(user)
        self.assertNotEqual(user.email, self.EMAIL)
        self.assertFalse(user.is_admin)
        # 账本保留（财务合规），余额清零
        txs = self.db.query(CreditTransaction).count()
        self.assertGreaterEqual(txs, 1)
        self.assertEqual(user.credit_balance, 0)
        # 错误密码拒绝
        auth_svc.register(self.db, "u2@test.local", "Passw0rd123", "t2")
        with self.assertRaises(BizError):
            auth_svc.delete_account(
                self.db, self.db.query(User).filter(User.email == "u2@test.local").one(),
                "WrongPass99")

    def test_export_data_zip(self):
        self._register()
        user = self.db.query(User).one()
        filename, payload = auth_svc.export_data(self.db, user)
        self.assertTrue(filename.endswith(".zip"))
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            data = json.loads(zf.read("meloyu-data-export.json"))
        self.assertEqual(data["profile"]["email"], self.EMAIL)


class TestSwitchPlanSemantics(_DBTestCase):
    """B4：订阅停售（cloud）→ 40901 转型公告；license 模式 → 40901 引导激活。"""

    def _user(self, plan="free"):
        from app.core.security import hash_password
        ts = utc_now_iso()
        u = User(email=f"{plan}@t.local", password_hash=hash_password("Passw0rd123"),
                 nickname="n", plan=plan, created_at=ts, updated_at=ts)
        self.db.add(u)
        self.db.commit()
        return u

    def test_cloud_paid_switch_rejected(self):
        user = self._user()
        with self.assertRaises(BizError) as ctx:
            billing_svc.switch_plan(self.db, user, "pro")
        self.assertEqual(ctx.exception.code, 40901)
        self.assertEqual(user.plan, "free")
        self.assertEqual(
            self.db.query(Subscription).filter(Subscription.plan == "studio").count(), 0)

    def test_license_mode_switch_guided_to_activation(self):
        old = settings.app_mode
        settings.app_mode = "desktop"
        try:
            user = self._user()
            with self.assertRaises(BizError) as ctx:
                billing_svc.switch_plan(self.db, user, "studio")
            self.assertEqual(ctx.exception.code, 40901)
        finally:
            settings.app_mode = old

    def test_downgrade_to_free_allowed(self):
        user = self._user(plan="studio")
        out = billing_svc.switch_plan(self.db, user, "free")
        self.assertEqual(out["plan"], "free")

    def test_same_plan_idempotent(self):
        user = self._user(plan="free")
        out = billing_svc.switch_plan(self.db, user, "free")
        self.assertEqual(out["plan"], "free")

    def test_list_plans_carries_license_block(self):
        user = self._user()
        out = billing_svc.list_plans(self.db, user)
        self.assertEqual(out["mode"], "subscription")
        self.assertEqual(out["license"]["price_usd"], 39900)
        self.assertEqual(out["license"]["sale_price_usd"], 15900)


class TestLicenseLifecycle(_DBTestCase):
    """B2：Ed25519 签发/验签/激活/幂等/解除 + B12 试用闸门 + B6 桌面注册闸。"""

    def setUp(self):
        super().setUp()
        self._old = (settings.app_mode, settings.license_public_key)
        self.priv, self.pub = license_svc.generate_keypair()
        settings.license_public_key = self.pub
        settings.app_mode = "desktop"
        ts = utc_now_iso()
        self.user = User(email="buyer@t.local", password_hash="x" * 60, nickname="b",
                         plan="studio", created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        settings.app_mode, settings.license_public_key = self._old
        super().tearDown()

    def _issue(self, tier="lifetime", **extra) -> str:
        import time
        import uuid
        payload = {"lid": uuid.uuid4().hex, "tier": tier, "devices": 3,
                   "acct": "buyer@t.local",
                   "iat": int(time.time()), "note": "buyer@t.local"}
        payload.update(extra)
        return license_svc.sign_license(payload, self.priv)

    def _fetch_factory(self, key: str):
        """模拟 portal /api/activate 响应的单测注入。"""
        def _fetch(account: str, code: str, device_id: str) -> dict:
            if code != "MELOYU-GOODCODE-00000000":
                return {"ok": False, "reason": "invalid_code"}
            return {"ok": True, "license_key": key, "tier": "lifetime"}
        return _fetch

    def test_keypair_roundtrip(self):
        key = self._issue()
        payload = license_svc.verify_license_key(key)
        self.assertEqual(payload["tier"], "lifetime")
        self.assertEqual(payload["devices"], 3)

    def test_bad_signature_rejected(self):
        key = self._issue()
        body, sig = key.split(".")[1], key.split(".")[2]
        tampered = f"v1.{body}.{'A' if not sig.startswith('A') else 'B'}{sig[1:]}"
        with self.assertRaises(BizError) as ctx:
            license_svc.verify_license_key(tampered)
        self.assertEqual(ctx.exception.code, 40202)

    def test_garbage_key_rejected(self):
        for bad in ("", "not-a-key", "v2.abc.def", "v1.only-two"):
            with self.assertRaises(BizError):
                license_svc.verify_license_key(bad)

    def test_activate_sets_state_and_plan(self):
        key = self._issue()
        out = license_svc.activate(self.db, key, user=self.user)
        self.assertTrue(out["activated"])
        self.assertEqual(out["license"]["tier"], "lifetime")
        self.db.refresh(self.user)
        self.assertEqual(self.user.plan, "studio")
        # 幂等：重复激活同一 Key 不报错不重复写
        out2 = license_svc.activate(self.db, key, user=self.user)
        self.assertTrue(out2["activated"])

    def test_activate_enterprise_tier_maps_team(self):
        key = self._issue(tier="enterprise", seats=20)
        license_svc.activate(self.db, key, user=self.user)
        self.db.refresh(self.user)
        self.assertEqual(self.user.plan, "team")

    def test_deactivate_restores_trial_gate_semantics(self):
        key = self._issue()
        license_svc.activate(self.db, key, user=self.user)
        out = license_svc.deactivate(self.db)
        self.assertFalse(out["activated"])
        self.assertFalse(out["trial"]["expired"], "刚起的试用未到期")

    def test_trial_gate_blocks_after_expiry_until_activated(self):
        state = license_svc.get_state(self.db)
        state.trial_started_at = "2020-01-01T00:00:00Z"  # 早已到期
        self.db.commit()
        with self.assertRaises(BizError) as ctx:
            license_svc.ensure_generation_allowed(self.db)
        self.assertEqual(ctx.exception.code, 40203)
        # 激活后放行
        license_svc.activate(self.db, self._issue(), user=self.user)
        license_svc.ensure_generation_allowed(self.db)  # 不抛即通过

    def test_trial_gate_allows_within_trial(self):
        license_svc.ensure_generation_allowed(self.db)  # 刚建档：试用期内，不抛

    def test_trial_gate_inert_in_cloud_mode(self):
        settings.app_mode = "cloud"
        state = license_svc.get_state(self.db)
        state.trial_started_at = "2020-01-01T00:00:00Z"
        self.db.commit()
        license_svc.ensure_generation_allowed(self.db)  # cloud 模式不适用，不抛

    def test_desktop_register_guard(self):
        with self.assertRaises(BizError) as ctx:
            auth_svc.register(self.db, "new@t.local", "Passw0rd123", "n")
        self.assertEqual(ctx.exception.code, 40901)

    def test_desktop_login_guard(self):
        # 桌面客户端无鉴权：凭据登录入口整体关闭（2026-10-04 用户口径）
        with self.assertRaises(BizError) as ctx:
            auth_svc.login(self.db, "whoever@t.local", "Passw0rd123")
        self.assertEqual(ctx.exception.code, 40901)

    def test_activate_online_success_and_failures(self):
        # 成功：账户+激活码 → portal 兑换签名密钥 → 本地验签落激活态
        key = self._issue()
        out = license_svc.activate_online(
            self.db, self.user, "buyer@t.local", "meloyu-goodcode-00000000 ",
            _fetch=self._fetch_factory(key))
        self.assertTrue(out["activated"])
        self.db.refresh(self.user)
        self.assertEqual(self.user.plan, "studio")
        # 幂等：重复兑换同码
        out2 = license_svc.activate_online(
            self.db, self.user, "buyer@t.local", "MELOYU-GOODCODE-00000000",
            _fetch=self._fetch_factory(key))
        self.assertTrue(out2["activated"])
        # 失败：无效激活码 → 40202
        with self.assertRaises(BizError) as ctx:
            license_svc.activate_online(
                self.db, self.user, "buyer@t.local", "MELOYU-WRONG0000-00000000",
                _fetch=self._fetch_factory(key))
        self.assertEqual(ctx.exception.code, 40202)
        # 失败：portal 报账户不符 → 40202 带原因文案
        def _mismatch(a, c, d):
            return {"ok": False, "reason": "account_mismatch"}
        with self.assertRaises(BizError) as ctx:
            license_svc.activate_online(self.db, self.user, "x@t.local",
                                        "MELOYU-GOODCODE-00000000", _fetch=_mismatch)
        self.assertIn("account", ctx.exception.message)
        # 失败：网络不可达 → 40901 引导离线激活
        def _net_fail(a, c, d):
            raise RuntimeError("connection refused")
        with self.assertRaises(BizError) as ctx:
            license_svc.activate_online(self.db, self.user, "buyer@t.local",
                                        "MELOYU-GOODCODE-00000000", _fetch=_net_fail)
        self.assertEqual(ctx.exception.code, 40901)

    def test_status_dict_shape(self):
        out = license_svc.status_dict(self.db)
        self.assertEqual(out["mode"], "desktop")
        self.assertEqual(out["billing_mode"], "license")
        self.assertFalse(out["activated"])
        self.assertEqual(out["trial"]["days"], 14)
        self.assertEqual(out["price_usd"], 39900)
        self.assertTrue(out["device_id"])


class TestLicenseMetering(_DBTestCase):
    """B5：license 模式积分纯计量（记账不扣减不拒绝）+ 水位拆除。"""

    def setUp(self):
        super().setUp()
        self._old = settings.app_mode
        settings.app_mode = "desktop"
        from app.core.security import hash_password
        ts = utc_now_iso()
        self.user = User(email="m@t.local", password_hash=hash_password("Passw0rd123"),
                         nickname="m", plan="studio", credit_balance=0,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        settings.app_mode = self._old
        super().tearDown()

    def test_deduct_records_but_never_refuses(self):
        from app.services import credits as credits_svc
        balance = credits_svc.atomic_deduct(self.db, self.user.id, 12, "generation", "t1")
        self.assertEqual(balance, 0, "计量模式余额不动")
        self.db.refresh(self.user)
        self.assertEqual(self.user.credit_balance, 0)
        tx = self.db.query(CreditTransaction).filter(
            CreditTransaction.ref_task_id == "t1").one()
        self.assertEqual(tx.delta, -12, "用量照常记账（统计口径）")
        self.assertEqual(tx.balance_after, 0)

    def test_lazy_grant_disarms_watermark(self):
        from app.services import credits as credits_svc
        self.user.credit_next_grant_at = "2000-01-01T00:00:00Z"
        self.db.commit()
        credits_svc.lazy_monthly_grant(self.db, self.user)
        self.db.refresh(self.user)
        self.assertIsNone(self.user.credit_next_grant_at, "license 模式拆除月度水位")
        self.assertEqual(self.user.credit_balance, 0, "不发放")


if __name__ == "__main__":
    unittest.main()
