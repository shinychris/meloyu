"""V2-c 市场单测（v0.10.1）：上架/浏览/购买分账/防重/下架。"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.core.errors import BizError
from app.models import Base, User, Work
from app.models.base import utc_now_iso
from app.models.task import File
from app.models.user import CreditTransaction
from app.models.work import Candidate, Version
from app.services import market as market_svc
from app.services.team import role_for_work


class TestMarket(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
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
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_publish_browse_delist(self):
        l = market_svc.publish(self.db, self.seller, self.work.id, 120)
        self.assertEqual(l["status"], "active")
        self.assertEqual(l["price_credits"], 120)
        self.assertEqual(l["seller"]["nickname"], "seller")
        # 非属主不能上架/下架
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.buyer, self.work.id, 100)
        with self.assertRaises(BizError):
            market_svc.delist(self.db, self.buyer, l["id"])
        # 重复上架 40901；越界价 40001
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.seller, self.work.id, 100)
        with self.assertRaises(BizError):
            market_svc.publish(self.db, self.seller, self.work.id, 0)
        browse = market_svc.browse(self.db)
        self.assertEqual(browse["total"], 1)
        self.assertEqual(browse["items"][0]["title"], "热卖节拍")
        # 下架后浏览不可见，重复购买路径守卫
        market_svc.delist(self.db, self.seller, l["id"])
        self.assertEqual(market_svc.browse(self.db)["total"], 0)
        # 重新上架（改价）
        l2 = market_svc.publish(self.db, self.seller, self.work.id, 80)
        self.assertEqual(l2["price_credits"], 80)

    def test_purchase_ledger_and_duplicate_guard(self):
        l = market_svc.publish(self.db, self.seller, self.work.id, 100)
        order = market_svc.purchase(self.db, self.buyer, l["id"])
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
            market_svc.purchase(self.db, self.buyer, l["id"])
        with self.assertRaises(BizError):
            market_svc.purchase(self.db, self.seller, l["id"])
        # 余额不足 40201
        with self.assertRaises(BizError):
            market_svc.purchase(self.db, self.other, l["id"])
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


if __name__ == "__main__":
    unittest.main()
