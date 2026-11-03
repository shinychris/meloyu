"""ACE-Step 组件应用内自动部署（v0.16.3）。

桌面买断制口径：Meloyu 是完整应用，默认安装即应部署 ACE-Step 组件——
终端用户没有「到 backend/ 跑脚本」的开发环境，本服务把
scripts/setup_acestep.py 的部署链路搬进应用内，并补齐干净机器引导：

  ① 源码：GitHub codeload 钉 commit 下载（供应链钉版）
  ② uv：系统 PATH → 随包（backend/tools/uv）→ 数据目录缓存 → 钉版下载
     （版本 + sha256 双钉；干净机器零前置，uv 自带 Python 托管下载）
  ③ venv：uv sync 独立 venv（torch cu128 与后端 venv 互斥）
  ④ 校验：venv python -c "import acestep"

消费方：模型中心部署操作（POST /models/acestep-deploy）、music-pull 对
acestep 模型的依赖自动前置部署、desktop 首启自动部署（main.py）、
scripts/setup_acestep.py（CLI 薄壳，保持开发者/Docker 手动通道）。

权重（约 11GB）仍走模型中心 music-pull（acestep_runner download），
与本部署（代码+依赖约 4GB）分层：部署完成 ≠ 权重就绪。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from app.config import BACKEND_DIR, settings
from app.core.i18n import tr
from app.core.logging import logger
from app.providers.music_acestep import (
    _venv_dir,
    _venv_python,
    acestep_deps_installed,
    acestep_root,
)

ProgressFn = Callable[[int, str], None]

# 供应链钉版：默认钉 commit（与 scripts/setup_acestep.py 原逻辑一致）；
# 升级显式改此值（或 env ACE_STEP_REF 覆盖）并重新部署验证。
# 2026-09-02 核验：ca1e85f = upstream main HEAD（"fix(jetson): remove GPL video codecs…"）
ACE_STEP_REF = os.environ.get("ACE_STEP_REF", "ca1e85fe9430179831e6bc6be790c332190a3866")
REPO_ZIP = f"https://codeload.github.com/ACE-Step/ACE-Step-1.5/zip/{ACE_STEP_REF}"

# uv 引导工具钉版（同上：版本 + 逐平台 sha256 双钉；env ACESTEP_UV_VERSION
# 覆盖版本时哈希校验自动让位为仅 HTTPS——升级需重新核验落表）。
# 0.9.28 = 2026-01-29 发布，与本机 dev 环境一致（部署链路已实测）。
# sha256 取自官方 Release 资产逐一下载核验（2026-10-17，win-x64/linux-x64/
# linux-arm64/mac-x64/mac-arm64 五平台）。
UV_VERSION = os.environ.get("ACESTEP_UV_VERSION", "0.9.28")
UV_RELEASE_BASE = "https://github.com/astral-sh/uv/releases/download"
# 平台键 → (release 资产名, sha256)；覆盖桌面全部目标（win-x64 / mac 双架构）
# 与部署运行环境（linux 容器双架构）。
_UV_ASSETS: dict[str, tuple[str, str]] = {
    "win-x64": ("uv-x86_64-pc-windows-msvc.zip",
                "9cb567fcd92f31431220ce620787043b946c30b9bb46ca213780e5ef471453be"),
    "linux-x64": ("uv-x86_64-unknown-linux-gnu.tar.gz",
                  "66ad1822dd9cf96694b95c24f25bc05cff417a65351464da01682a91796d1f2b"),
    "linux-arm64": ("uv-aarch64-unknown-linux-gnu.tar.gz",
                    "382c342735ff29f8ba4574d88e39bca798bcbac50bff6742710ca9cd8143e7d2"),
    "mac-x64": ("uv-x86_64-apple-darwin.tar.gz",
                "2116af95fc003173bfdf5a5768a44bdb3c34fccf56b7a81b570ac7c722a96e2d"),
    "mac-arm64": ("uv-aarch64-apple-darwin.tar.gz",
                  "12163fe09eb292d3ad1ea0f132a84485c902e2ff360d57562bf676e6615fcba0"),
}

_DOWNLOAD_TIMEOUT_SEC = 300   # 单次阻塞读超时（镜像脚本 urlopen 同值）
_CHUNK_BYTES = 1024 * 1024
# uv sync 进度爬行：20 分钟爬满 37→92（无真实总量可依，心跳式推进）
_SYNC_FULL_SEC = 20 * 60


class ACEStepDeployError(Exception):
    """部署链路错误。kind ∈ network|tool|verify。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _uv_platform_key() -> str:
    if sys.platform == "win32":
        return "win-x64"  # Windows 安装包仅 x64（electron-builder.yml）
    machine = (os.environ.get("PROCESSOR_ARCHITEW6432")
               or os.environ.get("PROCESSOR_ARCHITECTURE") or "").lower()
    import platform
    arch = platform.machine().lower() or machine
    arm = arch in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "mac-arm64" if arm else "mac-x64"
    return "linux-arm64" if arm else "linux-x64"


def _download_file(url: str, dest: Path, expected_sha256: str,
                   on_progress: ProgressFn, pct_base: int, pct_span: int) -> None:
    """流式下载 + sha256 校验 + 原子落盘（tmp→rename，中断不留半成品）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    hasher = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SEC) as r, \
                open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(_CHUNK_BYTES)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                got += len(chunk)
                if total:
                    pct = pct_base + int(pct_span * got / total)
                    msg = tr(f"下载中 {got / 1e6:.0f}MB / {total / 1e6:.0f}MB",
                             f"Downloading {got / 1e6:.0f}MB / {total / 1e6:.0f}MB")
                    on_progress(min(pct_base + pct_span - 1, pct), msg)
    except Exception as e:  # noqa: BLE001 —— 网络错误统一转部署错误
        tmp.unlink(missing_ok=True)
        raise ACEStepDeployError(
            "network", tr(f"下载失败（{url}）：{e}",
                          f"Download failed ({url}): {e}")) from e
    if expected_sha256 and hasher.hexdigest() != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise ACEStepDeployError(
            "network", tr(f"下载校验失败（sha256 不符，钉版 {UV_VERSION}）",
                          "Download checksum mismatch "
                          f"(sha256, pinned {UV_VERSION})"))
    tmp.replace(dest)


def _ensure_source(on_progress: ProgressFn, pct_base: int, pct_span: int) -> None:
    """源码就位：已存在即跳过；否则钉版 zip 下载解包（逻辑承自 setup 脚本）。"""
    dest = acestep_root()
    if (dest / "acestep").is_dir():
        on_progress(pct_base + pct_span - 1, tr("源码已就绪", "Source ready"))
        return
    on_progress(pct_base, tr("下载 ACE-Step 源码…", "Downloading ACE-Step source…"))
    archive = dest.parent / "_acestep_src.zip"
    _download_file(REPO_ZIP, archive, "", on_progress, pct_base, pct_span - 4)
    on_progress(pct_base + pct_span - 4, tr("解包源码…", "Extracting source…"))
    tmp = dest.parent / "_acestep_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        inner = tmp / next(iter(sorted(p.name for p in tmp.iterdir())))
        dest.mkdir(parents=True, exist_ok=True)
        for item in inner.iterdir():
            shutil.move(str(item), dest / item.name)
    except Exception as e:  # noqa: BLE001 —— 解包/搬移失败清理后转部署错误
        raise ACEStepDeployError(
            "tool", tr(f"源码解包失败：{e}", f"Source extraction failed: {e}")) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        archive.unlink(missing_ok=True)
    if not (dest / "acestep").is_dir():
        raise ACEStepDeployError(
            "tool", tr("源码解包结果异常（缺 acestep 包目录）",
                         "Source extraction result invalid (acestep package missing)"))


def _uv_tool_dir() -> Path:
    return settings.data_path / "tools" / "uv"


def _uv_exe_name() -> str:
    return "uv.exe" if sys.platform == "win32" else "uv"


def _uv_works(path: Path) -> bool:
    try:
        return subprocess.call([str(path), "--version"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               timeout=60) == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _acquire_uv(on_progress: ProgressFn, pct_base: int, pct_span: int) -> str:
    """uv 可执行文件：系统 → 随包/数据目录缓存 → 钉版下载（双钉校验）。"""
    found = shutil.which("uv")
    if found:
        on_progress(pct_base + pct_span - 1, tr("uv 就绪（系统）", "uv ready (system)"))
        return found
    for cand in (BACKEND_DIR / "tools" / "uv" / _uv_exe_name(),
                 _uv_tool_dir() / _uv_exe_name()):
        if cand.is_file() and _uv_works(cand):
            on_progress(pct_base + pct_span - 1,
                        tr("uv 就绪（本地缓存）", "uv ready (local cache)"))
            return str(cand)
    key = _uv_platform_key()
    asset, sha = _UV_ASSETS.get(key) or (None, "")
    # 哈希表与钉版 0.9.28 绑定：env 覆盖版本时自动让位为仅 HTTPS 传输
    if os.environ.get("ACESTEP_UV_VERSION"):
        sha = ""
    if asset is None:
        raise ACEStepDeployError(
            "tool", tr(f"当前平台（{key}）无钉版 uv 资产，请安装 uv："
                       "https://docs.astral.sh/uv/",
                       f"No pinned uv asset for this platform ({key}); "
                       "install uv: https://docs.astral.sh/uv/"))
    on_progress(pct_base,
                tr(f"下载部署工具 uv {UV_VERSION}…",
                   f"Downloading deploy tool uv {UV_VERSION}…"))
    archive = _uv_tool_dir() / asset
    _download_file(f"{UV_RELEASE_BASE}/{UV_VERSION}/{asset}", archive, sha,
                   on_progress, pct_base, pct_span - 2)
    extract = _uv_tool_dir() / "_extract"
    shutil.rmtree(extract, ignore_errors=True)
    try:
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(extract)
    except Exception as e:  # noqa: BLE001
        raise ACEStepDeployError(
            "tool", tr(f"uv 解包失败：{e}", f"uv extraction failed: {e}")) from e
    binaries = [p for p in extract.rglob(_uv_exe_name()) if p.is_file()]
    if not binaries:
        raise ACEStepDeployError(
            "tool", tr("uv 压缩包内未找到可执行文件", "uv binary not found in archive"))
    target = _uv_tool_dir() / _uv_exe_name()
    shutil.copy2(binaries[0], target)
    shutil.rmtree(extract, ignore_errors=True)
    archive.unlink(missing_ok=True)
    if not _uv_works(target):
        raise ACEStepDeployError(
            "tool", tr("下载的 uv 无法执行", "Downloaded uv failed to run"))
    on_progress(pct_base + pct_span - 1, tr("uv 就绪", "uv ready"))
    return str(target)


def _uv_sync(uv: str, on_progress: ProgressFn, pct_base: int, pct_span: int) -> None:
    """uv sync 拉齐独立 venv（约 4GB；Linux 容器固定 .venv-linux 与宿主隔离）。

    无总量可依（解析器+下载混合），按耗时心跳爬行推进，stdout/stderr 尾行
    作为进度文案（uv 解析/下载状态行对用户可见）。uv 托管 Python
    （requires-python >=3.11,<3.13）缺失时自动下载，干净机器零前置。
    """
    env = os.environ.copy()
    env.update({
        "UV_PYTHON": "3.12",
        "UV_PYTHON_DOWNLOADS": "automatic",
        "PYTHONUNBUFFERED": "1",
    })
    if sys.platform != "win32":
        # Linux venv 固定名 .venv-linux（与宿主机 Windows .venv 隔离共存，
        # v0.11.1 Exec format error 坑位）
        env["UV_PROJECT_ENVIRONMENT"] = _venv_dir().name
    on_progress(pct_base, tr("安装依赖（uv sync，约 4GB，5~20 分钟）…",
                             "Installing dependencies (uv sync, ~4GB, 5-20 min)…"))
    proc = subprocess.Popen(
        [uv, "sync"], cwd=str(acestep_root()), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )
    tail: list[str] = []
    started = time.monotonic()

    def _pump() -> None:
        try:
            for line in proc.stdout or []:
                line = line.strip()
                if line:
                    tail.append(line)
                    del tail[:-8]
        except Exception:  # noqa: BLE001 —— 消费线程不允许影响主流程
            pass

    threading.Thread(target=_pump, daemon=True).start()
    while proc.poll() is None:
        elapsed = time.monotonic() - started
        pct = pct_base + int(pct_span * min(1.0, elapsed / _SYNC_FULL_SEC))
        on_progress(min(pct_base + pct_span - 2, pct),
                    (tail[-1] if tail else tr("安装依赖中…", "Installing dependencies…"))[:200])
        time.sleep(2.0)
    if proc.returncode != 0:
        detail = " | ".join(tail[-3:])[:280]
        raise ACEStepDeployError(
            "tool", tr(f"uv sync 失败（码 {proc.returncode}）：{detail}",
                       f"uv sync failed (code {proc.returncode}): {detail}"))


def deploy_acestep(on_progress: ProgressFn) -> None:
    """完整部署链：源码 → uv → venv sync → import 校验。全部就绪则秒回。

    幂等：源码/uv/依赖任一已就绪即跳过对应阶段，重复调用只补缺口
    （desktop 每次启动检查、失败重启自愈复用同一入口）。
    """
    if acestep_deps_installed():
        on_progress(100, tr("ACE-Step 组件已就绪", "ACE-Step component ready"))
        return
    _ensure_source(on_progress, 1, 27)
    uv = _acquire_uv(on_progress, 28, 8)
    _uv_sync(uv, on_progress, 36, 57)
    on_progress(94, tr("校验部署…", "Verifying deployment…"))
    try:
        rc = subprocess.call([str(_venv_python()), "-c", "import acestep"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ACEStepDeployError(
            "verify", tr(f"校验执行失败：{e}", f"Verification failed: {e}")) from e
    if rc != 0 or not acestep_deps_installed():
        raise ACEStepDeployError(
            "verify", tr("部署异常：acestep 包不可导入",
                         "Deployment invalid: acestep package not importable"))
    on_progress(99, tr("ACE-Step 组件部署完成（权重请在模型中心下载）",
                       "ACE-Step component deployed "
                       "(download weights in the model center)"))
    logger.info(f"acestep deployed at {acestep_root()} (uv {UV_VERSION}, "
                f"ref {ACE_STEP_REF[:12]})")


def run_cli() -> int:
    """CLI 入口（scripts/setup_acestep.py 薄壳复用）：打印进度，返回退出码。"""
    def _print(pct: int, message: str) -> None:
        print(f"[{pct:3d}%] {message}", flush=True)
    try:
        deploy_acestep(_print)
    except ACEStepDeployError as e:
        print(f"部署失败（{e.kind}）：{e.message}", file=sys.stderr)
        return 2
    print("下一步：模型中心下载权重（约 11GB），或 API POST /models/music-pull")
    return 0
