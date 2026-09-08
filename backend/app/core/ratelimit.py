"""轻量接口限流中间件（P0-6，盘点报告 R-11 修复；自研零依赖替代 slowapi）。

按 (client_ip, bucket) 滑动窗口计数，命中规则超限返回 429 + 业务码 42901。
单进程内存实现（当前单机部署形态）；多副本部署时替换为 Redis 后端（接缝：
_bucket_key/_hit 两个函数）。

规则（bucket 前缀匹配，长前缀优先）：
- /api/v1/auth/login|refresh          10/min   —— 防爆破
- /api/v1/auth/register              20/hour   —— 防批量注册（主防线=邮箱验证）
- /api/v1/auth/send-code|forgot-password 3/hour —— 防邮件轰炸
- /api/v1/generations                 30/hour  —— 防算力刷取（叠加免费档日限）
- 其余 /api/v1/*                      300/min  —— 全局兜底
- /api/v1/billing/webhook             不限     —— Stripe 服务器 IP 调用
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.i18n import tr

# (路径前缀, 窗口秒, 上限)；按最长前缀优先匹配
_RULES: list[tuple[str, int, int]] = [
    ("/api/v1/auth/login", 60, 10),
    ("/api/v1/auth/refresh", 60, 10),
    ("/api/v1/auth/register", 3600, 20),  # 邮箱验证为主防线，IP 限流为辅（20/h）
    ("/api/v1/auth/send-code", 3600, 3),
    ("/api/v1/auth/forgot-password", 3600, 3),
    ("/api/v1/generations", 3600, 30),
    ("/api/v1/public/generations", 3600, 30),  # FR-19 开放 API β：与站内同额度
    ("/api/v1/billing/webhook", 0, 0),  # 0 = 不限流（显式豁免）
    ("/api/v1/", 60, 300),
]

_hits: dict[str, deque[float]] = defaultdict(deque)
_MAX_KEYS = 20000  # 内存上限：超量整体重置（防地址随机化撑爆内存）


def _client_ip(request: Request) -> str:
    """限流计数的客户端 IP。

    安审计 H-1（2026-09-09）：无条件取 X-Forwarded-For 链首=攻击者可控，
    轮换伪造头即可绕过全部按 IP 限流（登录防爆破、注册防批量）。现改为：
    - 默认（TRUST_PROXY=false，直连部署）：只用 TCP 对端地址，忽略一切转发头；
    - TRUST_PROXY=true（自有反代之后）：优先 X-Real-IP（nginx 以 $remote_addr
      覆写，不可伪造），退取 XFF 链尾（最近一跳可信代理追加的真实 IP）。
      链首（客户端自带值）永远不采信。
    """
    from app.config import settings
    if settings.trust_proxy:
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _match_rule(path: str) -> tuple[int, int] | None:
    for prefix, window, limit in _RULES:
        if path.startswith(prefix):
            return window, limit
    return None


def _hit(key: str, window: int, limit: int) -> bool:
    """记录一次命中；返回是否放行。"""
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:
        _hits.clear()
    q = _hits[key]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    rule = _match_rule(path)
    if rule is not None:
        window, limit = rule
        if limit > 0:
            key = f"{_client_ip(request)}|{path.split('?')[0]}"
            if not _hit(key, window, limit):
                return JSONResponse(
                    status_code=429,
                    content={"code": 42901,
                             "message": tr("请求过于频繁，请稍后再试",
                                           "Too many requests; please retry later"),
                             "data": None, "request_id": ""},
                    headers={"Retry-After": str(window // 2 or 1)},
                )
    return await call_next(request)
