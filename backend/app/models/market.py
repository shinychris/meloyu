"""作品市场（V2-c，v0.10.1）：站内上架/浏览/积分购买与非独占授权记录。

分账口径：卖家得 90%、平台 10%（落 market_orders + credit_transactions 双向
流水，reason=market_purchase（买家扣减）/ market_sale（卖家入账），积分账本
可审计）；买家获**非独占、不可转让**使用授权（订单即凭证，AIGC 署名随产物
保留）；上架须属主确认持有该作品的商用授权（ack_commercial 落库合规留痕）。
发行分发对接：发行打包见 FR-11 release 导出，外部平台提交为人工路径
（发行清单在 marketplace UI 提供）。
"""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp, new_uuid, utc_now_iso

MARKET_STATUSES = ("active", "delisted")


class MarketListing(BaseModel):
    """市场在售条目（作品级；非独占——可多单）。"""

    __tablename__ = "market_listings"
    __table_args__ = (
        CheckConstraint("price_credits BETWEEN 1 AND 100000", name="ck_listing_price"),
        Index("ix_listing_status_created", "status", "created_at"),
        Index("uq_listing_work", "work_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    work_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seller_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    price_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    preview_file_id: Mapped[str | None] = mapped_column(String(32))
    # 合规：上架确认持有商用授权（作品生成档位×通道许可口径）
    ack_commercial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<MarketListing id={self.id} work={self.work_id} price={self.price_credits}>"


class MarketOrder(BaseModel):
    """购买订单（非独占授权凭证 + 分账记录）。"""

    __tablename__ = "market_orders"
    __table_args__ = (
        Index("ix_market_orders_buyer", "buyer_user_id", "created_at"),
        Index("ix_market_orders_listing", "listing_id"),
        # 购买防双单（2026-10-27）：已购校验是 check-then-act，并发 double-click
        # 可双双下单双扣；订单无取消态（业务上终身一单），直接全列唯一约束
        Index("uq_market_order_buyer", "listing_id", "buyer_user_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    listing_id: Mapped[str] = mapped_column(String(32), nullable=False)
    work_id: Mapped[str] = mapped_column(String(32), nullable=False)
    buyer_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seller_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    price_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_earnings: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<MarketOrder id={self.id} listing={self.listing_id} price={self.price_credits}>"
