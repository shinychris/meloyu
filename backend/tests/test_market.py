""" 市场单测（v0.10.1）：上架/浏览/购买分账/防重/下架。"""
from __future__ import annotations

import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.core.errors import BizError
from app.models import Certificate, MarketListing, MarketOrder, User, Work
from app.models.base import utc_now_iso
from app.models.task import File
from app.models.user import CreditTransaction
from app.models.work import Candidate, Version
from app.services import market as market_svc
from app.services.team import role_for_work
from tests.db import new_test_engine, reset_db, seed_plans


class TestMarket(unittest.TestCase):
    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：播种档位行（users.plan → plans.code 外键）
        seed_plans(self.db)
        ts = utc_now_iso()

        def mk(i, email, bal):
            u = User(id=f"u{i}" * 16, email=email, password_hash="x",
                     nickname=email.split("@")[0], plan="studio", credit_balance=bal,
                     created_at=ts, updated_at=ts)
            self.db.add(u)
            return u

        self.seller = mk(1, "seller@test.local", 100)
        self.buyer = mk(2, "buyer@test.local", 500)
        self.other = mk(3, "other@test.local", 50)
        self.work = Work(id="w" * 32, user_id=self.seller.id, display_code="ML-0001",
                         title="热卖节拍", tags=["hiphop"], bpm=96, key_tonic="A",
                         key_mode="minor", duration_sec=120, model="v1_pro",
                         version_count=1, created_at=ts, updated_at=ts)
        self.db.add(self.work)
        self.db.flush()
        # 已采纳候选的最小夹具（v0.10.2 起上架要求试听文件）
        ver = Version(id="v" * 32, work_id=self.work.id, version_no="v1",
                      source="generate", candidate_count=1, params={}, lyrics="",
                      created_at=ts, updated_at=ts)
        cand = Candidate(id="c" * 32, version_id=ver.id, label="A", adopted=True,
                         seed=1, quality_score=88, duration_sec=120, bpm=96,
                         key_tonic="A", key_mode="minor", time_signature="4/4",
                         vocal="female_air", language="zh", style_tags=[], structure=[],
                         applied_negative=[], created_at=ts, updated_at=ts)
        self.db.add_all([ver, cand])
        self.db.flush()
        pf = File(id="p" * 32, work_id=self.work.id, version_id=ver.id,
                  candidate_id=cand.id, kind="preview", name="preview.mp3",
                  path=f"{self.work.id}/{ver.id}/preview.mp3", mime="audio/mpeg",
                  bytes=1000, duration_sec=120.0, sample_rate=44100,
                  sha256="0" * 64, created_at=ts, updated_at=ts)
        self.db.add(pf)
        self.work.preview_file_id = pf.id
        # （v0.14.0）：上架需最近一次签发证书为商用授权
        self.db.add(Certificate(
            certificate_code="MY-CERT-T1", work_id=self.work.id, version_id=ver.id,
            provider="localsynth", provider_display="Local", model="v1_pro", seed=1,
            generated_at=ts, license_type="commercial", license_grade="standard",
            plan_at_issuance="studio", license_valid=True, edit_events_count=0,
            human_summary=[], master_sha256="", preview_sha256="", disclosure="",
            issued_at=ts, created_at=ts, updated_at=ts))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_publish_browse_delist(self):
        item = market_svc.publish(self.db, self.seller, self.work.id, 120)
        self.assertEqual(item["status"], "active")
        self.assertEqual(item["price_credits"], 120)
        self.assertEqual(item["seller"]["nickname"], "seller")
        # 非属主不能上架/下架
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.buyer, self.work.id, 100)
        with self.assertRaises(BizError):
            market_svc.delist(self.db, self.buyer, item["id"])
        # 重复上架 40901；越界价 40001
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.seller, self.work.id, 100)
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.seller, self.work.id, 0)
        browse = market_svc.browse(self.db)
        self.assertEqual(browse["total"], 1)
        self.assertEqual(browse["items"][0]["title"], "热卖节拍")
        # 下架后浏览不可见，重复购买路径守卫
        market_svc.delist(self.db, self.seller, item["id"])
        self.assertEqual(market_svc.browse(self.db)["total"], 0)
        # 重新上架（改价）
        l2 = market_svc.publish(self.db, self.seller, self.work.id, 80)
        self.assertEqual(l2["price_credits"], 80)

    def test_purchase_ledger_and_duplicate_guard(self):
        item = market_svc.publish(self.db, self.seller, self.work.id, 100)
        order = market_svc.purchase(self.db, self.buyer, item["id"])
        self.assertEqual(order["price_credits"], 100)
        self.assertEqual(order["seller_earnings"], 90)
        self.assertEqual(order["platform_fee"], 10)
        self.assertIn("非独占", order["license"])
        self.db.refresh(self.buyer)
        self.db.refresh(self.seller)
        self.assertEqual(self.buyer.credit_balance, 400)
        self.assertEqual(self.seller.credit_balance, 190)
        # 账本：买家扣减 + 卖家入账各一条
        rows = self.db.query(CreditTransaction).all()
        deltas = sorted(r.delta for r in rows)
        # 买家 -100（atomic_deduct 落账）+ 卖家 +90（market_sale 入账），两条流水
        self.assertEqual(deltas, [-100, 90])
        self.assertEqual(len([r for r in rows if r.user_id == self.seller.id]), 1)
        self.assertEqual(len([r for r in rows if r.user_id == self.buyer.id]), 1)
        # 账本 reason：买家 market_purchase / 卖家 market_sale（v0.10.2 拆分，方向可辨）
        reasons = {(r.user_id, r.reason) for r in rows}
        self.assertIn((self.buyer.id, "market_purchase"), reasons)
        self.assertIn((self.seller.id, "market_sale"), reasons)
        # v0.10.2：购买即授予买家只读访问权（订单=非独占授权凭证）
        self.assertEqual(role_for_work(self.db, self.work, self.buyer), "viewer")
        self.assertIsNone(role_for_work(self.db, self.work, self.other))
        self.assertEqual(role_for_work(self.db, self.work, self.seller), "owner")
        # 重复购买 40901；买自己 40901
        with self.assertRaises(BizError):
            market_svc.purchase(self.db, self.buyer, item["id"])
        with self.assertRaises(BizError):
            market_svc.purchase(self.db, self.seller, item["id"])
        # 余额不足 40201
        with self.assertRaises(BizError):
            market_svc.purchase(self.db, self.other, item["id"])
        self.assertEqual(market_svc.my_orders(self.db, self.buyer)["total"], 1)
        self.assertEqual(market_svc.my_listings(self.db, self.seller)["total"], 1)

    def test_publish_requires_preview(self):
        # v0.10.2：无试听文件（未采纳候选）不可上架——否则买家无法验货
        self.work.preview_file_id = None
        self.db.commit()
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.seller, self.work.id, 100)

    def test_listing_preview_guard(self):
        lst = market_svc.publish(self.db, self.seller, self.work.id, 100)
        # 正常条目返回流式响应（文件不存在于磁盘 → BizError 40401，而非 403/500）
        with self.assertRaises(BizError):
            market_svc.listing_preview(self.db, lst["id"], None)
        # 下架后 40401
        market_svc.delist(self.db, self.seller, lst["id"])
        with self.assertRaises(BizError):
            market_svc.listing_preview(self.db, lst["id"], None)
        # 不存在的条目
        with self.assertRaises(BizError):
            market_svc.listing_preview(self.db, "x" * 32, None)

class TestMarketGovernance(unittest.TestCase):
    """v0.14.0 市场治理回归。"""

    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：播种档位行（users.plan → plans.code 外键）
        seed_plans(self.db)
        ts = utc_now_iso()
        self.seller = User(id="s" * 32, email="s@g.local", password_hash="x",
                           nickname="s", plan="studio", credit_balance=100,
                           created_at=ts, updated_at=ts)
        self.buyer = User(id="b" * 32, email="b@g.local", password_hash="x",
                          nickname="b", plan="free", credit_balance=500,
                          created_at=ts, updated_at=ts)
        self.db.add_all([self.seller, self.buyer])
        self.work = Work(id="gw" * 16, user_id=self.seller.id, display_code="ML-0002",
                         title="安全曲", tags=[], bpm=96, key_tonic="A",
                         key_mode="minor", duration_sec=120, model="v1_pro",
                         version_count=1, created_at=ts, updated_at=ts)
        self.db.add(self.work)
        self.db.flush()
        ver = Version(id="gv" * 16, work_id=self.work.id, version_no="v1",
                      source="generate", candidate_count=1, params={}, lyrics="",
                      created_at=ts, updated_at=ts)
        self.db.add(ver)
        self.db.flush()
        pf = File(id="gp" * 16, work_id=self.work.id, version_id=ver.id,
                  kind="preview", name="p.mp3",
                  path=f"{self.work.id}/{ver.id}/p.mp3", mime="audio/mpeg",
                  bytes=1000, duration_sec=120.0, sha256="0" * 64,
                  created_at=ts, updated_at=ts)
        self.db.add(pf)
        self.work.preview_file_id = pf.id
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _add_cert(self, license_type: str = "commercial", issued_at: str | None = None):
        from app.models.base import utc_now_iso as _now
        ts = issued_at or _now()
        ver = self.db.execute(select(Version).where(
            Version.work_id == self.work.id)).scalars().first()
        self.db.add(Certificate(
            certificate_code=f"MY-CERT-{license_type}", work_id=self.work.id,
            version_id=ver.id, provider="localsynth", provider_display="Local",
            model="v1_pro", seed=1, generated_at=ts, license_type=license_type,
            license_grade="standard", plan_at_issuance="studio", license_valid=True,
            edit_events_count=0, human_summary=[], master_sha256="",
            preview_sha256="", disclosure="", issued_at=ts,
            created_at=ts, updated_at=ts))
        self.db.commit()

    def test_publish_requires_commercial_certificate(self):
        with self.assertRaises(BizError):  # 无证书 → 拒绝
            market_svc.publish(self.db, self.seller, self.work.id, 100)
        self._add_cert("non_commercial", issued_at="2026-01-01T00:00:00Z")
        with self.assertRaises(BizError):  # 非商用证书 → 拒绝
            market_svc.publish(self.db, self.seller, self.work.id, 100)
        self._add_cert("commercial", issued_at="2026-02-01T00:00:00Z")  # 更近签发为商用 → 放行
        item = market_svc.publish(self.db, self.seller, self.work.id, 100)
        self.assertEqual(item["status"], "active")

    def test_purchase_rejects_deleted_work_and_delists(self):
        self._add_cert("commercial")
        item = market_svc.publish(self.db, self.seller, self.work.id, 100)
        # 模拟作品已被物理删除但 listing 残留 active（历史数据形态）
        from app.models.task import File as _F
        self.db.query(_F).filter(_F.work_id == self.work.id).delete()
        self.db.query(Version).filter(Version.work_id == self.work.id).delete()
        self.db.delete(self.work)
        self.db.commit()
        with self.assertRaises(BizError):
            market_svc.purchase(self.db, self.buyer, item["id"])
        row = self.db.get(MarketListing, item["id"])
        self.assertEqual(row.status, "delisted", "成交前发现作品已删 → 联动下架")
        self.db.refresh(self.buyer)
        self.assertEqual(self.buyer.credit_balance, 500, "买家积分未被扣")

    def test_physical_delete_delists_active_listing(self):
        from app.services import works as works_svc
        self._add_cert("commercial")
        market_svc.publish(self.db, self.seller, self.work.id, 100)
        self.work.status = "trash"
        self.work.trashed_at = "2000-01-01T00:00:00Z"
        self.db.commit()
        import tempfile
        from unittest import mock

        from app.config import settings
        wid = self.work.id
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(settings, "data_dir", tmp):
            works_svc._physical_delete(self.db, self.work)
        row = self.db.execute(select(MarketListing).where(
            MarketListing.work_id == wid)).scalars().one()
        self.assertEqual(row.status, "delisted")

    def test_admin_delist_governance(self):
        self._add_cert("commercial")
        item = market_svc.publish(self.db, self.seller, self.work.id, 100)
        with self.assertRaises(BizError):  # 非 admin 拒绝
            market_svc.admin_delist(self.db, self.buyer, item["id"], "test")
        self.seller.is_admin = True
        self.db.commit()
        out = market_svc.admin_delist(self.db, self.seller, item["id"], "violation test")
        self.assertEqual(out["status"], "delisted")

    def test_purchase_duplicate_blocked_by_unique_index(self):
        """（2026-10-27）：并发双单由 uq_market_order_buyer 硬约束兜底。

        绕过应用层已购查重直插第二单（模拟并发 double-click 的后提交者），
        唯一索引必须拒绝；应用层 purchase 的 IntegrityError 转译为 409 业务码。
        """
        from sqlalchemy.exc import IntegrityError
        self._add_cert("commercial")
        item = market_svc.publish(self.db, self.seller, self.work.id, 100)
        market_svc.purchase(self.db, self.buyer, item["id"])
        self.db.commit()
        dup = MarketOrder(listing_id=item["id"], work_id=self.work.id,
                          buyer_user_id=self.buyer.id, seller_user_id=self.seller.id,
                          price_credits=100, seller_earnings=90, platform_fee=10,
                          created_at=utc_now_iso())
        self.db.add(dup)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
        orders = self.db.execute(select(MarketOrder).where(
            MarketOrder.buyer_user_id == self.buyer.id)).scalars().all()
        self.assertEqual(len(orders), 1, "同买家同条目至多一单")

    def test_purchase_unique_violation_translates_to_409(self):
        """唯一索引兜底分支：已购查重被并发窗口绕过时，IntegrityError 转 409
        且扣款/入账/订单同事务回滚（积分不丢）。"""
        from unittest import mock
        self._add_cert("commercial")
        item = market_svc.publish(self.db, self.seller, self.work.id, 100)
        self.db.commit()
        # 预置「并发对手方已落单」的既成事实（等价于另一事务已提交的同键订单）
        self.db.add(MarketOrder(listing_id=item["id"], work_id=self.work.id,
                                buyer_user_id=self.buyer.id, seller_user_id=self.seller.id,
                                price_credits=100, seller_earnings=90, platform_fee=10,
                                created_at=utc_now_iso()))
        self.db.commit()
        self.db.expire_all()
        # 绕过应用层已购查重（模拟两个事务都读到「未购买」的窗口），purchase
        # 应在提交时撞唯一索引并转 40901
        with mock.patch.object(market_svc, "_already_owned", return_value=False):
            with self.assertRaises(BizError) as ctx:
                market_svc.purchase(self.db, self.buyer, item["id"])
        self.assertEqual(ctx.exception.code, 40901)
        orders = self.db.execute(select(MarketOrder).where(
            MarketOrder.buyer_user_id == self.buyer.id)).scalars().all()
        self.assertEqual(len(orders), 1, "冲突后只保留先提交的一单")
        self.db.refresh(self.buyer)
        self.assertEqual(self.buyer.credit_balance, 500, "回滚后买家积分未被双扣")
        rows = self.db.execute(select(CreditTransaction)).scalars().all()
        buyer_tx = [r for r in rows if r.user_id == self.buyer.id]
        self.assertEqual(buyer_tx, [], "被回滚事务的扣款流水不得残留")

if __name__ == "__main__":
    unittest.main()
