"""FastAPI 入口：CORS、locale（i18n）、错误包裹、request_id 中间件、启动建表与自愈。"""
from __future__ import annotations

import ipaddress

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

# 生产环境关闭交互式 API 文档（信息收敛）；dev 保持可用
_is_production = settings.env.strip().lower() == "production"
# desktop（单机 sidecar）/ enterprise（私有化）形态标记
_is_desktop = settings.app_mode == "desktop"
_is_enterprise = settings.app_mode == "enterprise"

app = FastAPI(title="Meloyu API", version=APP_VERSION,
              docs_url=None if _is_production else "/api/docs",
              openapi_url=None if _is_production else "/api/openapi.json")


def _assert_production() -> None:
    """ 生产启动断言：弱密钥/危险 CORS 直接拒启（fail-fast 而非静默生效）。"""
    problems: list[str] = []
    if settings.jwt_secret in ("meloyu-dev-secret-do-not-use-in-production", ""):
        problems.append("JWT_SECRET 仍为开发默认值/为空——生产必须配置强随机密钥")
    if settings.server_nonce == "meloyu-local-nonce-v1":
        problems.append("SERVER_NONCE 仍为开发默认值——生产必须配置强随机值")
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if "*" in origins:
        problems.append("CORS_ORIGINS 含 * 且 allow_credentials=True——禁止，请列明来源域名")
    #（2026-09-09）：第三方 API Key 落库加密密钥漏配时静默明文存储
    if not settings.key_encryption_secret:
        problems.append("KEY_ENCRYPTION_SECRET 为空——llm_settings 中的第三方 API Key "
                        "将明文落库；生产必须配置 Fernet 密钥（openssl rand -base64 32）")
    # v0.10.2：APP_BASE_URL 指向 localhost 时密码重置邮件链接会指到
    # 开发地址（不拒启：反代/本地生产栈可合法回环，但必须可见地告警）
    if "localhost" in settings.app_base_url or "127.0.0.1" in settings.app_base_url:
        logger.warning(f"APP_BASE_URL 指向本机地址（{settings.app_base_url}）——"
                       "对外部署时密码重置链接将不可达，请在 .env 配置对外域名")
    # v0.15.0：生产数据库必须为 PostgreSQL（SQLite 单写入方约束与两次库损坏
    # 事故的根治项；SQLite 回退仅限本机开发）——DATABASE_URL 未配置或非 PG 拒启
    if engine.dialect.name != "postgresql":
        problems.append("DATABASE_URL 未配置 PostgreSQL 连接串——v0.15.0 起生产强制 "
                        "PostgreSQL（本地栈由 compose 的 postgres 服务提供，云端可用 "
                        "Supabase；SQLite 仅限本机开发回退）")
    # v0.13.0 审计延伸（2026-09-26）：邮件"半配置"静默通过是
    # 公网配置期的高危窗口——开了邮箱验证没配 SMTP 时注册入口直接不可用。
    if settings.email_verification_enabled and not settings.smtp_host:
        problems.append("EMAIL_VERIFICATION_ENABLED=true 但 SMTP_HOST 为空——"
                        "注册验证码发不出，注册入口不可用；请配置 SMTP 或关闭验证")
    if problems:
        raise RuntimeError("production startup assertions failed:\n- " + "\n- ".join(problems))


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
# locale 中间件（纯 ASGI，最后注册=最外层）：contextvar 先于一切下游设置
app.add_middleware(LocaleMiddleware)

# 接口限流（IP+路径滑动窗口；生产/开发一致启用，豁免见表）
from app.core.ratelimit import rate_limit_middleware  # noqa: E402

app.middleware("http")(rate_limit_middleware)

# Sentry 接缝（可选依赖：pip install sentry-sdk 并配 SENTRY_DSN 后生效）
if settings.sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, release=f"meloyu@{APP_VERSION}")
        logger.info("sentry initialized")
    except ImportError:
        logger.warning("SENTRY_DSN configured but sentry-sdk not installed; skipping")


#（2026-09-09）：dev 形态来源守卫——非回环请求一律拒绝。
# dev 实例带固定密码 demo 管理员账号、开放 /api/docs，仅应本机可达；绑定地址
# 无法可靠探测（uvicorn CLI 可脱离 settings.host 传 --host 0.0.0.0），故按
# 实际到达的客户端来源拦截：LAN 联调需显式配置 ALLOW_LAN_DEV=true 自担风险。
# 生产栈（ENV=production）不受影响——backend 容器内 nginx 转发来源本就非回环。
@app.middleware("http")
async def dev_loopback_guard_middleware(request: Request, call_next):
    if not _is_production and not settings.allow_lan_dev:
        client_host = request.client.host if request.client else ""
        # 仅拦截"真实远程 IP"：非 IP 字面量（如 TestClient 的 "testclient"、
        # "localhost"）与回环地址放行
        try:
            addr = ipaddress.ip_address(client_host)
        except ValueError:
            addr = None
        if addr is not None and not addr.is_loopback:
            logger.warning(f"dev instance rejecting non-loopback client {client_host} "
                           f"on {request.url.path} (set ALLOW_LAN_DEV=true to override)")
            return JSONResponse(
                status_code=403,
                content={"code": 40302,
                         "message": tr("开发实例仅限本机访问（如需局域网联调，配置 ALLOW_LAN_DEV=true）",
                                       "Dev instance is local-only "
                                       "(set ALLOW_LAN_DEV=true for LAN debugging)"),
                         "data": None, "request_id": _request_id.get()},
            )
    return await call_next(request)


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
    logger.exception(f"unhandled error on {request.method} {_log_url(request)}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 50001, "message": tr("服务内部错误", "Internal server error"),
                 "data": None, "request_id": _request_id.get()},
    )


def _log_url(request: Request) -> str:
    """日志侧请求 URL：query 的 st（stream-token 签名，15 分钟有效的播放凭证）
    出日志前脱敏（2026-10-27）——日志可被采集/外发，签名入日志等于凭证入日志；
    只影响日志呈现，不影响实际请求处理。"""
    from urllib.parse import urlencode
    params = [(k, v) for k, v in request.query_params.multi_items()]
    if any(k == "st" for k, _ in params):
        params = [(k, "***" if k == "st" else v) for k, v in params]
    qs = urlencode(params)
    return request.url.path + (f"?{qs}" if qs else "")


app.include_router(api_router, prefix=API_PREFIX)


def _startup() -> None:
    if _is_production:
        _assert_production()
    if _is_desktop:
        # B1 补全（2026-10-16）：首启生成/加载实例密钥（jwt + Key 落库加密），
        # 须先于 reencrypt_plaintext_secrets 等密钥消费点
        from app.services.desktop import ensure_desktop_secrets
        ensure_desktop_secrets()
    # enterprise 形态：启动即校验 License（fail-fast，防未授权部署）
    from app.services.license import assert_enterprise_license
    assert_enterprise_license()
    # import 顺序保证全部模型注册到同一 Base.metadata
    from app import models  # noqa: F401
    from app.core.tasks import recover_zombie_tasks
    from app.services.works import purge_expired

    Base.metadata.create_all(engine)
    #（2026-09-09）：生产库若复用自 dev，固定密码 demo 账号仍可登录
    # ——启动即禁用（随机密码+摘除 admin+吊销刷新令牌；账号行保留不破坏外键）
    from app.seed_data import disable_seed_demo_accounts
    if _is_production:
        disabled = disable_seed_demo_accounts()
        if disabled:
            logger.warning(f"production startup: disabled {disabled} fixed-password "
                           "seed demo account(s) (dev-DB reuse residue)")
    from app.core.migrations import run as run_migrations
    run_migrations(engine)
    # 配置了加密密钥时，把历史明文 API Key 行升级为密文
    from app.core.crypto import reencrypt_plaintext_secrets
    reencrypted = reencrypt_plaintext_secrets()
    if reencrypted:
        logger.info(f"startup: re-encrypted {reencrypted} plaintext API key field(s)")
    recovered = recover_zombie_tasks()
    from app.services.model_center import recover_stale_ops
    stale_ops = recover_stale_ops()
    if stale_ops:
        logger.info(f"startup: recovered {stale_ops} stale model ops")
    from app.database import SessionLocal
    with SessionLocal() as db:
        purge_expired(db)
        if _is_desktop:
            # B6/B1：桌面首启——仅灌 plans 档位行（配额/导出闸门查表），自动建档
            # 本地用户（随机密码+is_admin，模型中心即用户配置面），同时落试用起点
            from app.seed_data import ensure_plans_seeded
            from app.services.desktop import ensure_local_user
            ensure_plans_seeded(db)
            local = ensure_local_user(db)
            logger.info(f"desktop mode: local profile ready (user={local.email}, "
                        f"plan={local.plan}, data at {settings.data_path})")
            # v0.16.3：默认安装即部署完成——ACE-Step 组件（买断制主打引擎）
            # 首启后台自动部署（源码+uv 引导+独立 venv，约 4GB，进度见模型中心
            # 「本地组件」；env ACESTEP_AUTO_DEPLOY=false 关闭改手动触发）。
            # 受理失败仅记日志，部署失败落在 ops 记录，均不阻塞启动；
            # 未完成时下次启动自愈续跑（部署链路幂等只补缺口）。
            if settings.acestep_auto_deploy:
                from app.services.model_center import start_acestep_deploy
                try:
                    if start_acestep_deploy(db, local.id, auto=True) is None:
                        logger.info("desktop mode: ACE-Step component already ready")
                    else:
                        logger.info("desktop mode: ACE-Step component auto-deploy started")
                except Exception as e:  # noqa: BLE001 —— 已有操作进行中/库异常不拦启动
                    logger.warning(f"acestep auto-deploy not started: {e}")
    # （2026-09-26）：清扫不再挂列表读路径，改守护线程定时全量触发
    from app.services.works import start_periodic_purge
    start_periodic_purge()
    # v0.14.0：应用内每日备份（GPU 容器 docker exec 受 seccomp 限制不可用，
    # 备份必须不依赖 exec；见 services/ops_backup.py）
    from app.services.ops_backup import start_periodic_backup
    start_periodic_backup()
    if recovered:
        logger.info(f"startup: recovered {recovered} zombie tasks")
    # 首次启动（无 demo 账号）时后台线程灌种子（渲染音频耗时数分钟，不阻塞启动）
    # 生产环境禁用演示账号自动播种（固定密码账号=后门）
    # 2026-10-03：desktop 形态跳过演示播种（首启秒级、无固定密码账号）
    from app.seed_data import ensure_seeded_in_background
    if _is_production or _is_desktop:
        logger.warning("seed demo accounts skipped (production/desktop startup)")
    else:
        ensure_seeded_in_background()


@app.on_event("startup")
async def on_startup() -> None:
    _startup()


# B8：桌面形态 sidecar 同源托管前端 SPA（StaticFiles html=True 兜底 / → index.html；
# HashRouter 无服务端路由重写需求）。API 路由已先注册，mount("/") 只接剩余流量。
if _is_desktop and settings.static_path is not None:
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(settings.static_path), html=True),
              name="spa")
