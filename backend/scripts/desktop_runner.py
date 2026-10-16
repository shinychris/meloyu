"""桌面 sidecar 启动入口（PyInstaller 打包目标）。

壳进程通过环境变量注入运行参数：
    MELOYU_PORT            监听端口（壳选取的空闲端口）
    DATA_DIR               用户数据目录（壳的 userData/data）
    DESKTOP_STATIC_DIR     前端静态目录（resources/web）
    LICENSE_PUBLIC_KEY     License 验签公钥（构建时注入）

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

from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("MELOYU_PORT", "8765")),
        log_level="info",
        access_log=False,
    )
