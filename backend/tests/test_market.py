"""V2-c 市场单测（v0.10.1）：上架/浏览/购买分账/防重/下架。"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.core.errors import BizError
from app.models import Base, User, Work
from app.models.base import utc_now_iso
from app.models.user import CreditTransaction
from app.services import market as market_svc


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


if __name__ == "__main__":
    unittest.main()
