"""桌面 sidecar 启动入口（PyInstaller 打包目标）。

壳进程通过环境变量注入运行参数：
    MELOYU_PORT            监听端口（壳选取的空闲端口）
    DATA_DIR               用户数据目录（壳的 userData/data）
    DESKTOP_STATIC_DIR     前端静态目录（resources/web）
    LICENSE_PUBLIC_KEY     License 验签公钥（构建时注入）

桌面专属收敛（仅本入口生效；云端形态走 uvicorn app.main:app，不经过此文件）：
- Host 头校验中间件（评审 F-DT-09）：Host 必须为 127.0.0.1/localhost + 本端口，
  其余 403——防 DNS rebinding 把浏览器页面的请求打到本地全部 API；
- POST /_sidecar/shutdown（评审 F-DT-07）：壳退出流程先走 HTTP 优雅关停
  （置 uvicorn should_exit，完成在途请求再退出，防 SQLite 写入中途被杀），
  失败才由壳 kill/taskkill 兜底。仅 MELOYU_PORT 存在（桌面壳拉起）时注册；
  dev 下 npm 脚本直启 uvicorn 不经过 desktop_runner，无此路由也不强制 Host
  校验（评审 F-DT-09 dev 说明）；
- 成品 dev 语义收敛（评审 F-DT-17）：桌面档仍以 ENV=dev 运行（无强随机密钥
  与 PG，生产启动断言不适用），但移除 /api/docs、/api/openapi.json、/redoc
  交互文档路由并摘除 CORS 中间件（SPA 与接口同源，CORS 无意义；窗口外来源
  已被 Host 校验拦截）。

打包：desktop/sidecar/build-sidecar.{cmd,sh}（PyInstaller --onedir）。
"""
from __future__ import annotations

import os
import sys

# 打包形态 stdout/stderr 经壳管道输出，Windows 默认 GBK 编码无法表示 loguru
# 等库的 Unicode 字符（ℹ/⚠ 图标，实测打包后每条日志 UnicodeEncodeError）——
# 先行重配为 UTF-8 再导入应用（reconfigure 原地改编码，既有 sink 同样生效）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from fastapi.responses import JSONResponse

# dev 手动运行（python scripts/desktop_runner.py）时 sys.path[0] 为 scripts/，
# 补注 backend 根以导入 app 包；PyInstaller 形态由 --paths .. 在分析期解析
# （frozen 后此目录不存在于运行环境，插入无害）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.main import app

# 桌面壳拉起标记：MELOYU_PORT 由壳注入（desktop/src/main.js spawn env）
_IS_DESKTOP_SHELL = bool(os.environ.get("MELOYU_PORT"))
_PORT = os.environ.get("MELOYU_PORT", "8765")


def _install_desktop_guardians() -> None:
    """桌面专属中间件与路由（须在 uvicorn 启动前注册；Starlette 的中间件栈
    延迟到首个请求才构建，此时尚可增删）。"""
    port = _PORT

    @app.middleware("http")
    async def loopback_host_guard(request, call_next):  # noqa: ANN001, ANN201
        """评审 F-DT-09：Host 头白名单。绑定 127.0.0.1 已挡住直接远程访问，
        但 DNS rebinding 可让恶意页面把域名解析到 127.0.0.1 绕过——按 Host
        头二次校验（app_mode 无关，仅 desktop_runner 入口生效）。"""
        host = (request.headers.get("host") or "").strip().lower()
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return JSONResponse(
                status_code=403,
                content={"code": 40303, "message": "invalid host header",
                         "data": None, "request_id": ""},
            )
        return await call_next(request)

    # 评审 F-DT-17：摘除 CORS 中间件——桌面 SPA 与接口同源，CORS 无意义；
    # 放开只会留一个更宽的 dev CORS 面
    from fastapi.middleware.cors import CORSMiddleware
    app.user_middleware = [m for m in app.user_middleware
                           if m.cls is not CORSMiddleware]

    # 评审 F-DT-17：下线交互文档路由（成品桌面应用无需 /api/docs 面）。
    # docs_url 在 FastAPI 构造期已注册为路由，这里直接摘除
    docs_paths = {"/api/docs", "/api/openapi.json", "/redoc"}
    app.router.routes[:] = [r for r in app.router.routes
                            if getattr(r, "path", None) not in docs_paths]


def main() -> None:
    if _IS_DESKTOP_SHELL:
        _install_desktop_guardians()

        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=int(_PORT),
            log_level="info", access_log=False,
        ))

        @app.post("/_sidecar/shutdown", include_in_schema=False)
        async def sidecar_shutdown() -> dict:
            """评审 F-DT-07：壳退出流程第一步。置 should_exit → uvicorn 完成
            在途请求后优雅退出（避免 SQLite 写入中途被强杀）；仅桌面壳拉起
            （MELOYU_PORT 存在）时注册，云端形态绝不注册此路由。"""
            server.should_exit = True
            return {"ok": True}

        server.run()
        return

    # 非壳环境手动运行（本地排查用）：默认端口，无桌面专属收敛
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(_PORT),
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
