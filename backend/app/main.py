"""FastAPI 入口：CORS、locale（i18n）、错误包裹、request_id 中间件、启动建表与自愈。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.v1.router import api_router
from app.config import API_PREFIX, APP_VERSION, settings
from app.core.errors import BizError
from app.core.i18n import LocaleMiddleware, tr
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
# locale 中间件（纯 ASGI，最后注册=最外层）：contextvar 先于一切下游设置
app.add_middleware(LocaleMiddleware)


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


_FIELD_LABELS = {
    "simple_prompt": ("一句话描述", "one-line description"),
    "style_prompt": ("风格描述", "style description"),
    "lyrics": ("歌词", "lyrics"),
    "negative_prompt": ("排除元素", "excluded elements"),
    "mode": ("创作模式", "mode"), "model": ("模型", "model"),
    "email": ("邮箱", "email"), "password": ("密码", "password"),
    "format": ("格式", "format"), "version_id": ("版本", "version"),
    "work_id": ("作品", "work"), "parent_version_id": ("父版本", "parent version"),
    "params.duration_sec": ("时长", "duration"), "params.bpm": ("BPM", "BPM"),
    "params.vocal": ("人声", "vocal"),
    "params.language": ("语言", "language"),
    "params.time_signature": ("拍号", "time signature"),
    "params.key.tonic": ("调性（主音）", "key (tonic)"),
    "params.key.mode": ("调性（大小调）", "key (major/minor)"),
    "params.instrument_density": ("器乐密度", "instrument density"),
}


def _localize_validation(field: str, msg: str) -> str:
    """pydantic 校验消息 → 面向用户的本地化提示（真实业务测试发现 #10）。"""
    import re as _re

    if msg.startswith("Value error, "):  # pydantic v2 包装自定义 ValueError 的前缀
        msg = msg[len("Value error, "):]
    pair = _FIELD_LABELS.get(field)
    label = tr(pair[0], pair[1]) if pair else None
    fallback_label = label or tr("该字段", "this field")
    m = _re.match(r"String should have at most (\d+) characters", msg)
    if m:
        return (tr(f"{fallback_label}不能超过 {m.group(1)} 字",
                   f"{fallback_label} must be at most {m.group(1)} characters"))
    m = _re.match(r"String should have at least (\d+) characters", msg)
    if m:
        return (tr(f"{fallback_label}不能少于 {m.group(1)} 字",
                   f"{fallback_label} must be at least {m.group(1)} characters"))
    if msg == "Field required":
        return (tr(f"缺少必填字段：{label or field}",
                   f"Missing required field: {label or field}"))
    # 其余（自定义 validator 消息已自带字段名，经 tr 双语化）原样返回
    return msg


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x not in ("body", "query"))
        raw = str(err.get("msg", tr("校验失败", "validation failed")))
        details.append({"field": loc or ".", "message": _localize_validation(loc, raw)})
    first = details[0]["message"] if details else tr("参数错误", "Invalid parameters")
    return JSONResponse(
        status_code=422,
        content={"code": 40001,
                 "message": tr("参数校验失败：", "Validation failed: ") + first,
                 "data": {"details": details}, "request_id": _request_id.get()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(f"unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 50001, "message": tr("服务内部错误", "Internal server error"),
                 "data": None, "request_id": _request_id.get()},
    )


app.include_router(api_router, prefix=API_PREFIX)


def _startup() -> None:
    # import 顺序保证全部模型注册到同一 Base.metadata
    from app import models  # noqa: F401
    from app.core.tasks import recover_zombie_tasks
    from app.services.works import purge_expired

    Base.metadata.create_all(engine)
    from app.core.migrations import run as run_migrations
    run_migrations(engine)
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
