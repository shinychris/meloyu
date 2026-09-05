"""一键部署 ACE-Step v1.5 到 backend/data/acestep（代码 + 独立 venv + uv sync）。

在 backend/ 下运行：./.venv/Scripts/python scripts/setup_acestep.py

Docker 部署（宿主机执行）：
    docker exec -it meloyu-backend python scripts/setup_acestep.py
    —— 容器内建 Linux venv（.venv-linux），与宿主机 Windows venv（.venv）
    同目录共存互不覆盖；checkpoints 权重经 bind 挂载直接共用，无需重下。
    前置：镜像已内置 uv；GPU 直通见 deploy/docker-compose.yml（无 GPU 时
    runner 自动回退 CPU，速度很慢但可用）。

为什么独立 venv：ACE-Step 钉死 torch==2.7.1+cu128，与后端 venv 的
torch 2.13+cu130（MusicGen 使用）互斥（ADR-016）。部署产物全部位于
backend/data/acestep/（gitignored）：源码、venv、checkpoints（约 11GB 权重，
首次在模型中心下载）。

前置：已安装 uv（https://docs.astral.sh/uv/）；Python 3.11/3.12 由 uv 自动解析。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEST = BACKEND_DIR / "data" / "acestep"
# venv 平台分目录：Windows 宿主与 Linux 容器共用同一 bind 挂载的 DEST，venv
# 二进制互不可执行且同名会互相覆盖（Exec format error，v0.11.1 实测坑位）。
IS_WINDOWS = sys.platform == "win32"
VENV_NAME = ".venv" if IS_WINDOWS else ".venv-linux"
VENV_PY = DEST / VENV_NAME / ("Scripts/python.exe" if IS_WINDOWS
                              else "bin/python")
# P1-10 供应链钉版：默认钉 commit（R-36——钉分支会被上游破坏性更新打断）；
# 升级时显式改此值（或 env ACE_STEP_REF 覆盖）并重新部署验证。
# 2026-09-02 核验：ca1e85f = upstream main HEAD（"fix(jetson): remove GPL video codecs…"）
ACE_STEP_REF = os.environ.get("ACE_STEP_REF", "ca1e85fe9430179831e6bc6be790c332190a3866")
REPO_ZIP = (f"https://codeload.github.com/ACE-Step/ACE-Step-1.5/zip/{ACE_STEP_REF}")


def main() -> int:
    print(f"目标目录：{DEST}")
    if not (DEST / "acestep").is_dir():
        print("下载源码…")
        with urllib.request.urlopen(REPO_ZIP, timeout=300) as r:
            data = r.read()
        tmp = DEST.parent / "_acestep_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        zipfile.ZipFile(BytesIO(data)).extractall(tmp)
        inner = tmp / next(iter(sorted(p.name for p in tmp.iterdir())))
        DEST.mkdir(parents=True, exist_ok=True)
        for item in inner.iterdir():
            shutil.move(str(item), DEST / item.name)
        shutil.rmtree(tmp)
        print("源码就绪")
    else:
        print("源码已存在，跳过下载")

    uv = shutil.which("uv")
    if not uv:
        print("未找到 uv：请先安装 https://docs.astral.sh/uv/ 后重试")
        return 2
    print("uv sync（下载 torch cu128 等依赖，约 4GB，可能 5~20 分钟）…")
    env = os.environ.copy()
    if not IS_WINDOWS:
        # Linux venv 固定名 .venv-linux（与宿主机 Windows .venv 隔离共存）
        env["UV_PROJECT_ENVIRONMENT"] = VENV_NAME
    rc = subprocess.call([uv, "sync"], cwd=str(DEST), env=env)
    if rc != 0:
        print("uv sync 失败，请检查网络（代理）后重试")
        return rc
    venv_py = VENV_PY
    ok = subprocess.call([str(venv_py), "-c", "import acestep"]) == 0
    print("部署完成" if ok else "部署异常：acestep 包不可导入")
    print("下一步：模型中心下载权重（约 11GB），或 API POST /models/music-pull")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
