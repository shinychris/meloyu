"""octet-stream 请求体的流式读取（大小上限在接收过程中即断，不先全量缓冲）。

2026-10-27：原 hum/reference/voice 端点用 `body: bytes = Body(...)`——FastAPI
在整个请求体读入内存后才轮到业务层的大小校验，超限请求照样吃满带宽与内存
（内存放大 DoS）。本 helper 逐块读取、累计越过上限立即抛业务错误断开；
versions.upload_mixdown 的 yield_body 即此写法，抽此处共用。
"""
from __future__ import annotations

from fastapi import Request

from app.core.errors import err_validation
from app.core.i18n import tr


async def read_body_limited(request: Request, max_bytes: int,
                            exceed_zh: str, exceed_en: str) -> bytes:
    """流式读取请求体；累计超过 max_bytes 立即抛 40001 断开（不再继续接收）。"""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise err_validation(tr(exceed_zh, exceed_en))
        chunks.append(chunk)
    return b"".join(chunks)
