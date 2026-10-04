"""License 请求模型（B2：买断制激活）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ActivateLicenseRequest(BaseModel):
    license_key: str = Field(min_length=10, max_length=2048)


class OnlineActivateRequest(BaseModel):
    """在线激活（2026-10-04 用户口径：账户 + 激活码，邮件交付）。"""
    account: str = Field(min_length=3, max_length=120)
    code: str = Field(min_length=6, max_length=64)
