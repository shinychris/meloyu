"""统一响应包裹 {code,message,data,request_id} + request_id 中间件。"""
from __future__ import annotations

import secrets
from contextvars import ContextVar

from fastapi.responses import JSONResponse

from app.core.errors import BizError

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id.get()


def new_request_id() -> str:
    return secrets.token_hex(4)


def ok(data=None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": 0, "message": "ok", "data": data, "request_id": current_request_id()},
    )


def fail(exc: BizError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": exc.data,
                 "request_id": current_request_id()},
    )
