"""auth 账号体系（P1-3）+ Stripe webhook（P1-1）+ switch_plan 止血（P0-4）单测。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
全部走内存 SQLite（services 层直调，不起 HTTP 服务）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.core.errors import BizError
from app.models import Base, CreditTransaction, Order, Plan, Subscription, User
from app.models.base import utc_now_iso
from app.services import auth as auth_svc
from app.services import billing as billing_svc
from app.services import stripe_billing


class _DBTestCase(unittest.TestCase):
    """每个用例独立内存库。"""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
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
        self.assertEqual(user.credit_balance, settings and 200)
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

    def _login_refresh(self) -> str:
        out, refresh, _ttl = auth_svc.login(self.db, self.EMAIL, "Passw0rd123")
        return refresh

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


class TestSwitchPlanHardening(_DBTestCase):
    """P0-4：付费档不可白拿（无论 Stripe 是否配置，switch 都不发付费档）。"""

    def _user(self, plan="free"):
        from app.core.security import hash_password
        ts = utc_now_iso()
        u = User(email=f"{plan}@t.local", password_hash=hash_password("Passw0rd123"),
                 nickname="n", plan=plan, created_at=ts, updated_at=ts)
        self.db.add(u)
        self.db.commit()
        return u

    def test_paid_switch_rejected_without_stripe(self):
        settings.stripe_secret_key = ""
        user = self._user()
        with self.assertRaises(BizError) as ctx:
            billing_svc.switch_plan(self.db, user, "pro")
        self.assertEqual(ctx.exception.code, 40901)

    def test_paid_switch_rejected_even_with_stripe(self):
        settings.stripe_secret_key = "sk_test_dummy"
        try:
            user = self._user()
            with self.assertRaises(BizError) as ctx:
                billing_svc.switch_plan(self.db, user, "studio")
            self.assertEqual(ctx.exception.code, 40901)
            # 没有订阅行、没有积分、档位未变
            self.assertEqual(user.plan, "free")
            self.assertEqual(
                self.db.query(Subscription).filter(
                    Subscription.plan == "studio").count(), 0)
        finally:
            settings.stripe_secret_key = ""

    def test_downgrade_to_free_allowed(self):
        user = self._user(plan="studio")
        out = billing_svc.switch_plan(self.db, user, "free")
        self.assertEqual(out["plan"], "free")

    def test_same_plan_idempotent(self):
        user = self._user(plan="free")
        out = billing_svc.switch_plan(self.db, user, "free")
        self.assertEqual(out["plan"], "free")


class TestStripeWebhook(_DBTestCase):
    """webhook 验签 + 事件处理（不发起真实 Stripe 调用）。"""

    SECRET = "whsec_test_dummy"

    def setUp(self):
        super().setUp()
        self._old_secret = settings.stripe_secret_key
        self._old_wh = settings.stripe_webhook_secret
        settings.stripe_secret_key = "sk_test_dummy"
        settings.stripe_webhook_secret = self.SECRET
        stripe_billing._seen_events.clear()
        ts = utc_now_iso()
        self.user = User(email="pay@t.local", password_hash="x" * 60, nickname="p",
                         plan="free", created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        settings.stripe_secret_key = self._old_secret
        settings.stripe_webhook_secret = self._old_wh
        super().tearDown()

    def _sign(self, payload: bytes) -> str:
        t = str(int(time.time()))
        mac = hmac.new(self.SECRET.encode(), f"{t}.".encode() + payload,
                       hashlib.sha256).hexdigest()
        return f"t={t},v1={mac}"

    def _event(self, etype: str, obj: dict, event_id: str) -> bytes:
        return json.dumps({"id": event_id, "type": etype, "data": {"object": obj}}).encode()

    def test_signature_rejected(self):
        payload = self._event("checkout.session.completed", {"id": "cs_x"}, "evt_1")
        with self.assertRaises(BizError):
            stripe_billing.verify_and_parse_webhook(payload, "t=1,v1=bad")

    def test_topup_paid_grants_credits_and_idempotent(self):
        order = Order(user_id=self.user.id, kind="topup", credits=1000,
                      amount_usd=999, status="pending",
                      stripe_checkout_id="cs_test_topup_1",
                      created_at=utc_now_iso(), updated_at=utc_now_iso())
        self.db.add(order)
        self.db.commit()
        payload = self._event("checkout.session.completed", {
            "id": "cs_test_topup_1", "customer": "cus_test_1",
            "metadata": {"order_id": order.id, "user_id": self.user.id,
                         "kind": "topup", "credits": "1000"},
        }, "evt_topup_1")
        event = stripe_billing.verify_and_parse_webhook(payload, self._sign(payload))
        out = stripe_billing.handle_webhook_event(self.db, event)
        self.assertTrue(out["received"])
        self.db.refresh(order)
        self.db.refresh(self.user)
        self.assertEqual(order.status, "paid")
        self.assertEqual(self.user.credit_balance, 1000)
        self.assertEqual(
            self.db.query(CreditTransaction).filter(
                CreditTransaction.reason == "topup").count(), 1)
        # 重放同一事件：幂等
        out2 = stripe_billing.handle_webhook_event(
            self.db, stripe_billing.verify_and_parse_webhook(payload, self._sign(payload)))
        self.assertTrue(out2.get("duplicate"))
        self.db.refresh(self.user)
        self.assertEqual(self.user.credit_balance, 1000)

    def test_subscription_activation_and_cancellation(self):
        order = Order(user_id=self.user.id, kind="subscription", plan="pro",
                      interval="monthly", credits=0, amount_usd=58, status="pending",
                      stripe_checkout_id="cs_test_sub_1",
                      created_at=utc_now_iso(), updated_at=utc_now_iso())
        self.db.add(order)
        self.db.commit()
        payload = self._event("checkout.session.completed", {
            "id": "cs_test_sub_1", "customer": "cus_test_2",
            "subscription": "sub_test_1",
            "metadata": {"order_id": order.id, "user_id": self.user.id,
                         "kind": "subscription", "plan": "pro"},
        }, "evt_sub_1")
        event = stripe_billing.verify_and_parse_webhook(payload, self._sign(payload))
        stripe_billing.handle_webhook_event(self.db, event)
        self.db.refresh(self.user)
        self.assertEqual(self.user.plan, "pro")
        self.assertEqual(self.user.credit_balance, 2500)
        sub = self.db.query(Subscription).filter(
            Subscription.user_id == self.user.id,
            Subscription.status == "active").one()
        self.assertEqual(sub.source, "stripe")

        # 订阅取消 → 降级 free
        payload2 = self._event("customer.subscription.deleted",
                               {"id": "sub_test_1"}, "evt_sub_del")
        stripe_billing.handle_webhook_event(
            self.db, stripe_billing.verify_and_parse_webhook(payload2, self._sign(payload2)))
        self.db.refresh(self.user)
        self.assertEqual(self.user.plan, "free")
        self.assertEqual(
            self.db.query(Subscription).filter(
                Subscription.user_id == self.user.id,
                Subscription.status == "active").count(), 0)

    def test_refund_deducts_credits(self):
        self.user.credit_balance = 800
        self.db.commit()
        order = Order(user_id=self.user.id, kind="topup", credits=1000,
                      amount_usd=999, status="paid",
                      stripe_checkout_id="cs_test_refund_1",
                      created_at=utc_now_iso(), updated_at=utc_now_iso())
        self.db.add(order)
        self.db.commit()
        payload = self._event("charge.refunded", {
            "amount_refunded": 999,
            "metadata": {"checkout_session_id": "cs_test_refund_1",
                         "user_id": self.user.id},
        }, "evt_refund_1")
        stripe_billing.handle_webhook_event(
            self.db, stripe_billing.verify_and_parse_webhook(payload, self._sign(payload)))
        self.db.refresh(self.user)
        self.db.refresh(order)
        self.assertEqual(order.status, "refunded")
        self.assertEqual(self.user.credit_balance, 0, "余额不足扣至 0，不为负")


if __name__ == "__main__":
    unittest.main()
