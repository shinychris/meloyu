"""一键部署 ACE-Step v1.5 到本地组件目录（代码 + 独立 venv + uv sync）。

在 backend/ 下运行：./.venv/Scripts/python scripts/setup_acestep.py

Docker 部署（宿主机执行）：
    docker exec -it meloyu-backend python scripts/setup_acestep.py
    —— 容器内建 Linux venv（.venv-linux），与宿主机 Windows venv（.venv）
    同目录共存互不覆盖；checkpoints 权重经 bind 挂载直接共用，无需重下。
    前置：镜像已内置 uv；GPU 直通见 deploy/docker-compose.yml（无 GPU 时
    runner 自动回退 CPU，速度很慢但可用）。

v0.16.3 起本脚本为薄壳：部署链路（源码钉版下载 → uv 引导 → sync → 校验）
统一实现在 app/services/acestep_deploy.py，与模型中心「组件部署」操作、
desktop 首启自动部署共用同一入口（幂等，重复执行只补缺口）。干净机器
无 uv/Python 时由服务自动钉版下载 uv 并托管 Python 3.12。

为什么独立 venv：ACE-Step 钉死 torch==2.7.1+cu128，与后端 venv 的
torch 2.13+cu130（MusicGen 使用）互斥（ADR-016）。部署产物全部位于
数据目录 acestep/（gitignored）：源码、venv、checkpoints（约 11GB 权重，
首次在模型中心下载）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.acestep_deploy import run_cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_cli())
