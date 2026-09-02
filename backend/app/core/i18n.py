"""请求级 i18n：Accept-Language → contextvar，tr() 双语取值（默认 en）。

纯 ASGI 中间件（非 BaseHTTPMiddleware）：contextvar 在 await call_app 之前 set，
随上下文复制传播到下游（路由、anyio 同步端点线程池、BaseHTTPMiddleware 内层任务），
不受 BaseHTTPMiddleware 的 task 隔离问题影响。

注意：ThreadPoolExecutor.submit 直接提交的 worker 线程不复制 contextvar——
后台任务（生成/导出/模型下载）在提交处用 run_with_locale 捕获请求 locale
并在 worker 内恢复，保证进度/错误文案按提交时语言生成（可接受的持久化语义）。
"""
from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar

SUPPORTED_LOCALES = ("en", "zh")
DEFAULT_LOCALE = "en"

_locale: ContextVar[str] = ContextVar("locale", default=DEFAULT_LOCALE)


def current_locale() -> str:
    """当前请求 locale（'en' | 'zh'；无请求上下文时为默认 'en'）。"""
    return _locale.get()


def set_locale(locale: str) -> None:
    _locale.set(locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE)


def tr(zh: str, en: str) -> str:
    """按当前 locale 返回文案：zh → 中文，其余（默认 en）→ 英文。"""
    return zh if _locale.get() == "zh" else en


def parse_accept_language(header: str | None) -> str:
    """解析 Accept-Language：首个条目以 zh 开头 → 'zh'，其余（含缺失）→ 'en'。"""
    if not header:
        return DEFAULT_LOCALE
    first = header.split(",")[0].strip().lower()
    return "zh" if first.startswith("zh") else DEFAULT_LOCALE


def run_with_locale(locale: str, fn: Callable, /, *args, **kwargs):
    """在当前线程恢复指定 locale 后执行 fn（线程池 worker 用，见模块 docstring）。"""
    token = _locale.set(locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE)
    try:
        return fn(*args, **kwargs)
    finally:
        _locale.reset(token)


class LocaleMiddleware:
    """纯 ASGI 中间件：解析请求 Accept-Language 写入 locale contextvar。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        # headers.get 默认值防 KeyError（无 Accept-Language 头 → en）
        set_locale(parse_accept_language(headers.get("accept-language")))
        await self.app(scope, receive, send)
