"""License 请求模型（B2：买断制激活）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ActivateLicenseRequest(BaseModel):
    license_key: str = Field(min_length=10, max_length=2048)
