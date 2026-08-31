"""FastAPI 入口：CORS、错误包裹、request_id 中间件、启动建表与自愈。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.v1.router import api_router
from app.config import API_PREFIX, APP_VERSION, settings
from app.core.errors import BizError
from app.core.logging import setup_logging
from app.core.responses import _request_id, fail, new_request_id
from app.database import engine
from app.models import Base

setup_logging()

app = FastAPI(title="Meloyu API", version=APP_VERSION, docs_url="/api/docs",
              openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = new_request_id()
    _request_id.set(rid)
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    return fail(exc)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x not in ("body", "query"))
        details.append({"field": loc or ".", "message": str(err.get("msg", "校验失败"))})
    first = details[0]["message"] if details else "参数错误"
    return JSONResponse(
        status_code=422,
        content={"code": 40001, "message": f"参数校验失败：{first}",
                 "data": {"details": details}, "request_id": _request_id.get()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(f"unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 50001, "message": "服务内部错误", "data": None,
                 "request_id": _request_id.get()},
    )


app.include_router(api_router, prefix=API_PREFIX)


def _startup() -> None:
    # import 顺序保证全部模型注册到同一 Base.metadata
    from app import models  # noqa: F401
    from app.core.tasks import recover_zombie_tasks
    from app.services.works import purge_expired

    Base.metadata.create_all(engine)
    recovered = recover_zombie_tasks()
    from app.services.model_center import recover_stale_ops
    stale_ops = recover_stale_ops()
    if stale_ops:
        logger.info(f"startup: recovered {stale_ops} stale model ops")
    from app.database import SessionLocal
    with SessionLocal() as db:
        purge_expired(db)
    if recovered:
        logger.info(f"startup: recovered {recovered} zombie tasks")
    # 首次启动（无 demo 账号）时后台线程灌种子（渲染音频耗时数分钟，不阻塞启动）
    from app.seed_data import ensure_seeded_in_background
    ensure_seeded_in_background()


@app.on_event("startup")
async def on_startup() -> None:
    _startup()
