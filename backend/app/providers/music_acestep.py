"""ACE-Step v1.5 本地开源模型 Provider（V1.5「本地开源音乐大模型」批，ADR-016）。

ACE-Step v1.5（MIT，5Hz LM + DiT 混合架构，2B turbo + 0.6B LM）：歌词→完整
歌曲（真人声演唱），8GB 显存档可用（pt 后端 + CPU offload），是本机 4060 Ti
唯一可跑的开源「人声成曲」SOTA 模型。

依赖隔离：ACE-Step 钉死 torch==2.7.1+cu128，与后端 venv（torch 2.13+cu130，
MusicGen 使用）互斥——代码/独立 venv/checkpoints 部署在 backend/data/acestep/
（gitignored，scripts/setup_acestep.py 一键部署）。推理经子进程调用
scripts/acestep_runner.py（acestep venv 下运行），stdout JSON Lines 回传
进度/结果；取消=terminate 子进程（GPU 显存随进程退出释放，与 MusicGen
进程内推理互不挤占）。产物 master.wav（48kHz，模型原生）+ preview.mp3，
无分轨/MIDI（导出侧按「有无分轨」拦截，与外部通道同一规则）。
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from app.config import ACESTEP_TASK_TIMEOUT_SEC, BACKEND_DIR, settings
from app.core.i18n import tr
from app.core.logging import logger
from app.providers.base import (
    CancelCheck,
    CandidateArtifact,
    GenerationOutput,
    ProgressCallback,
    SynthCancelled,
)
from app.providers.music_catalog import CATALOG_BY_ID
from app.synth.ir import SongRequest
from app.synth.mp3_io import encode_mp3
from app.synth.wav_io import read_wav

_INSTALL_HINT_ZH = ("ACE-Step 未部署：在 backend/ 下执行 "
                    "python scripts/setup_acestep.py（自动下载代码并 uv sync 独立 venv，"
                    "约 4GB 依赖；需已安装 uv 与 Python 3.11/3.12）")
_INSTALL_HINT_EN = ("ACE-Step is not deployed: from backend/ run "
                    "python scripts/setup_acestep.py (downloads the code and uv-syncs an "
                    "isolated venv, ~4GB of dependencies; requires uv and Python 3.11/3.12)")
_INSTALL_HINT_DOCKER_ZH = ("Docker 部署请在宿主机执行：docker exec -it meloyu-backend "
                           "python scripts/setup_acestep.py（容器内建 Linux venv "
                           ".venv-linux，与宿主机 Windows venv 互不干扰，权重经 "
                           "bind 挂载共用）")
_INSTALL_HINT_DOCKER_EN = ("In the Docker deployment run from the host: docker exec -it "
                           "meloyu-backend python scripts/setup_acestep.py (creates a "
                           "Linux venv .venv-linux inside the container, independent of "
                           "the host's Windows venv; weights are shared via the bind mount)")

# 单卡 GPU 互斥（generate 内持有，子进程退出即释放；见 generate 处注释）
_ACESTEP_SEMAPHORE = threading.BoundedSemaphore(1)

# 主模型 4 组件 + 8GB 档 LM（checkpoints 目录下的子目录名，与 acestep 包一致）
_COMPONENTS = ("acestep-v15-turbo", "vae", "Qwen3-Embedding-0.6B",
               "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-0.6B")
_WEIGHT_NAMES = (
    "model.safetensors", "model.safetensors.index.json",
    "pytorch_model.bin", "pytorch_model.bin.index.json",
    "diffusion_pytorch_model.safetensors", "diffusion_pytorch_model.safetensors.index.json",
    "diffusion_pytorch_model.bin", "diffusion_pytorch_model.bin.index.json",
)

# 声线预设 → caption 附加描述（模型无显式声线参数，经文本提示引导）
_VOCAL_DESC = {
    "female_air": "airy female vocals", "female_bright": "bright female vocals",
    "female_deep": "deep female vocals", "male_magnetic": "magnetic male vocals",
    "male_clear": "clear male vocals", "choir": "choir harmonies",
}

_LANG_MAP = {"zh": "zh", "yue": "yue", "en": "en", "ja": "ja"}


class ACEStepLocalError(Exception):
    """ACE-Step 本地通道错误。kind ∈ deps|download|runtime。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def acestep_root() -> Path:
    return settings.acestep_path


def _in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _venv_dir() -> Path:
    # Windows 宿主与 Linux 容器共用同一份 bind 挂载的 acestep 目录（data/ 不入
    # 镜像），而 venv 内是平台二进制且互不可执行——同名 .venv 还会互相覆盖。
    # Linux 固定用 .venv-linux 隔离，避免容器内把宿主机 Windows venv 的
    # python.exe 当解释器执行（OSError Exec format error，v0.11.1 实测坑位）。
    return acestep_root() / (".venv" if sys.platform == "win32" else ".venv-linux")


def _venv_python() -> Path:
    if sys.platform == "win32":
        return _venv_dir() / "Scripts" / "python.exe"
    return _venv_dir() / "bin" / "python"


def _venv_site_packages() -> Path | None:
    if sys.platform == "win32":
        return _venv_dir() / "Lib" / "site-packages"
    lib = _venv_dir() / "lib"
    for child in sorted(lib.glob("python*"), reverse=True):
        sp = child / "site-packages"
        if sp.is_dir():
            return sp
    return None


def _runner_path() -> Path:
    return BACKEND_DIR / "scripts" / "acestep_runner.py"


def checkpoints_dir() -> Path:
    return acestep_root() / "checkpoints"


def acestep_install_hint() -> str:
    hint = tr(_INSTALL_HINT_ZH, _INSTALL_HINT_EN)
    if _in_docker():
        hint += "；" + tr(_INSTALL_HINT_DOCKER_ZH, _INSTALL_HINT_DOCKER_EN)
    return hint


def acestep_deps_installed() -> bool:
    """独立 venv 存在且 acestep 包已安装（site-packages 校验，秒回；
    只查 venv python 会在 uv sync 半途误报就绪）。平台感知：Linux 容器
    只认 .venv-linux，宿主机 Windows venv 挂载进来不算数。"""
    if not ((acestep_root() / "acestep").is_dir()):
        return False
    sp = _venv_site_packages()
    return (_venv_python().exists()
            and sp is not None
            and ((sp / "acestep").is_dir() or any(sp.glob("ace_step*.dist-info"))))


def _has_weights(model_dir: Path) -> bool:
    return any((model_dir / name).exists() for name in _WEIGHT_NAMES)


def _is_acestep_model(model_id: str) -> bool:
    return "acestep_local" in CATALOG_BY_ID.get(model_id, {}).get("channels", [])


def is_downloaded(model_id: str) -> bool:
    if not _is_acestep_model(model_id):
        return False
    ck = checkpoints_dir()
    return all(_has_weights(ck / c) for c in _COMPONENTS)


def local_downloaded_ids() -> list[str]:
    return [m["id"] for m in CATALOG_BY_ID.values()
            if _is_acestep_model(m["id"]) and is_downloaded(m["id"])]


def delete_local(model_id: str) -> None:
    if not _is_acestep_model(model_id):
        raise ACEStepLocalError(
            "download", tr(f"模型不支持本地删除：{model_id}",
                           f"Model does not support local deletion: {model_id}"))
    ck = checkpoints_dir()
    if ck.exists():
        import shutil
        shutil.rmtree(ck)


def _subprocess_env() -> dict:
    import os
    env = os.environ.copy()
    env.update({
        "ACESTEP_PROJECT_ROOT": str(acestep_root()),
        "ACESTEP_CHECKPOINTS_DIR": str(checkpoints_dir()),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        # hf-xet 过代理易挂起（v0.5.1 坑位），普通 HTTPS 断点续传
        "HF_HUB_DISABLE_XET": "1",
    })
    if settings.hf_endpoint:
        env.setdefault("HF_ENDPOINT", settings.hf_endpoint)
    return env


def _spawn(args: list[str]) -> subprocess.Popen:
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    return subprocess.Popen(
        [_venv_python(), str(_runner_path()), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=_subprocess_env(), cwd=str(acestep_root()),
        text=True, encoding="utf-8", errors="replace",
        creationflags=flags,
    )


class _StderrTail:
    """并发消费子进程 stderr（torch 告警量大，不消费会塞满管道缓冲区拖死子进程），
    只保留尾部用于错误信息。"""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.thread: threading.Thread | None = None

    def start(self, proc: subprocess.Popen) -> None:
        def loop() -> None:
            try:
                for line in proc.stderr or []:
                    self.lines.append(line)
                    if len(self.lines) > 40:
                        del self.lines[:-40]
            except Exception:  # noqa: BLE001 —— 消费线程不允许影响主流程
                pass

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def tail(self) -> str:
        return "".join(self.lines).strip()[-600:]


def _stream_events(proc: subprocess.Popen, lines: queue.Queue[str]) -> None:
    try:
        for line in proc.stdout or []:
            lines.put(line)
    finally:
        lines.put("")  # EOF 哨兵


def _run_runner(args: list[str], on_event, *, timeout_sec: int,
                should_cancel: CancelCheck | None = None) -> dict:
    """拉起 runner 并逐行消费 JSON 事件；返回 done 事件 dict。

    取消/超时都会 kill 子进程后抛错；事件循环经队列 1s 轮询，保证
    cancel 秒级响应（读 stdout 是阻塞的，不能直接在 readline 里查标志）。
    """
    proc = _spawn(args)
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=_stream_events, args=(proc, lines), daemon=True).start()
    stderr_tail = _StderrTail()
    stderr_tail.start(proc)
    killed = {"timeout": False}

    def _kill(timeout: bool = False) -> None:
        killed["timeout"] = killed["timeout"] or timeout
        try:
            proc.kill()
        except OSError:  # noqa: BLE001 —— 进程可能已退出
            pass

    watchdog = threading.Timer(timeout_sec, lambda: _kill(timeout=True))
    watchdog.daemon = True
    watchdog.start()
    try:
        while True:
            try:
                line = lines.get(timeout=1.0)
            except queue.Empty:
                if should_cancel and should_cancel():
                    _kill()
                    raise SynthCancelled() from None
                continue
            if line == "":  # EOF
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                logger.debug(f"acestep_runner 非 JSON 输出: {line[:160]}")
                continue
            if event.get("event") == "error":
                _kill()
                raise ACEStepLocalError(
                    "runtime",
                    str(event.get("message") or tr("未知错误", "Unknown error")))
            if event.get("event") == "done":
                return event
            if event.get("event") == "progress" and on_event:
                on_event(int(event.get("pct") or 0), str(event.get("message") or ""))
        proc.wait(timeout=30)
        if killed["timeout"]:
            raise TimeoutError(
                tr(f"ACE-Step 推理超过 {timeout_sec}s 熔断",
                   f"ACE-Step inference exceeded {timeout_sec}s circuit limit"))
        rc = proc.returncode
        if rc == 0:
            # 正常退出但没发 done（不应发生）
            raise ACEStepLocalError(
                "runtime", tr("runner 未返回结果即退出",
                              "runner exited without returning a result"))
        raise ACEStepLocalError(
            "runtime",
            tr(f"runner 异常退出（码 {rc}）：{stderr_tail.tail()[-300:]}",
               f"runner crashed (exit code {rc}): {stderr_tail.tail()[-300:]}"))
    finally:
        watchdog.cancel()
        _kill()
        for stream in (proc.stdout, proc.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:  # noqa: BLE001
                    pass


def pull_local(model_id: str, on_progress) -> None:
    """下载模型权重（主模型 4 组件 + 0.6B LM，约 11GB），进度经 on_progress 上报。"""
    if not _is_acestep_model(model_id):
        raise ACEStepLocalError(
            "download", tr(f"模型不支持本地下载：{model_id}",
                           f"Model does not support local download: {model_id}"))
    if not acestep_deps_installed():
        raise ACEStepLocalError("deps", acestep_install_hint())
    checkpoints_dir().mkdir(parents=True, exist_ok=True)

    def on_event(pct: int, message: str) -> None:
        on_progress(max(1, min(99, pct)), message)

    _run_runner(["download"], on_event, timeout_sec=24 * 3600)


def _stage_key(pct: int) -> str:
    if pct < 20:
        return "model_load"
    if pct < 88:
        return "model_sample"
    return "model_export"


class ACEStepLocalProvider:
    """MusicProvider 协议实现：本机 ACE-Step v1.5 推理（人声+器乐）。"""

    name = "acestep_local"
    base_display = "Local ACE-Step v1.5 (open source)"
    supports_vocals = True
    timeout_sec = ACESTEP_TASK_TIMEOUT_SEC
    vocals_downgraded = False

    def __init__(self, model_id: str):
        if not _is_acestep_model(model_id):
            raise ACEStepLocalError(
                "download",
                tr(f"模型不支持本机 ACE-Step 通道：{model_id}",
                   f"Model does not support the local ACE-Step channel: {model_id}"))
        self.model_id = model_id
        self.display_name = (tr("ACE-Step 本地 · ", "ACE-Step Local · ")
                             + CATALOG_BY_ID[model_id]['name'])

    def generate(
        self,
        request: SongRequest,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        if not acestep_deps_installed():
            raise ACEStepLocalError("deps", acestep_install_hint())
        if not is_downloaded(self.model_id):
            raise ACEStepLocalError(
                "download",
                tr("模型权重未下载（请先在模型中心下载，约 11GB）",
                   "Model weights not downloaded (download them in the model center "
                   "first, ~11GB)"))

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        vocal_desc = _VOCAL_DESC.get(request.vocal, "")
        caption = (request.style_prompt or "pop music").strip()
        if vocal_desc:
            caption = f"{caption}, {vocal_desc}"
        req = {
            "caption": caption,
            "lyrics": (request.lyrics or "").strip(),
            "instrumental": request.vocal == "instrumental",
            "vocal_language": _LANG_MAP.get(request.language, "unknown"),
            "duration": max(10, min(int(request.duration_sec), 600)),
            "bpm": int(request.bpm),
            "keyscale": f"{request.tonic}{'' if request.mode == 'major' else 'm'}",
            "timesignature": request.time_signature,
            "seed": request.seed,
            "seeds": [request.seed, request.seed ^ 0x9E3779B9],
            "batch_size": 2,
        }
        req_file = dest / "_request.json"
        req_file.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")

        def on_event(pct: int, message: str) -> None:
            # 阶段边界查取消（采样中由队列轮询秒级响应）
            if should_cancel():
                raise SynthCancelled()
            progress(_stage_key(pct), max(1, min(99, pct)),
                     message or tr("ACE-Step 生成中", "Generating with ACE-Step"))

        # GPU 单卡互斥（2026-09-26 商业化审查 P1-17）：8GB 显存跑不下两个 ACE-Step
        # 子进程（batch 2 各自拉 torch），并发必双双 OOM 失败退款——与 musicgen
        # _GEN_LOCK / selfhosted _AUDIOCPP_SEMAPHORE 同款串行化。等待期间持续上报
        # 进度与查取消：排队等待计入任务超时预算，防止排到队首时已被超时熔断误杀。
        while not _ACESTEP_SEMAPHORE.acquire(timeout=5):
            if should_cancel():
                raise SynthCancelled()
            progress("gpu_wait", 1,
                     tr("等待 GPU 空闲（前一任务生成中）…",
                        "Waiting for GPU (previous task generating)…"))

        try:
            done = _run_runner(
                ["generate", "--request", str(req_file), "--outdir", str(dest)],
                on_event, timeout_sec=self.timeout_sec, should_cancel=should_cancel)
        finally:
            _ACESTEP_SEMAPHORE.release()
            req_file.unlink(missing_ok=True)

        candidates: list[CandidateArtifact] = []
        for meta in done.get("candidates") or []:
            label = str(meta.get("label") or chr(ord("A") + len(candidates)))
            master_rel = str(meta.get("relpath"))
            master = dest / master_rel
            if not master.exists():
                raise ACEStepLocalError(
                    "runtime",
                    tr(f"候选 {label} 母带缺失：{master_rel}",
                       f"Candidate {label} master missing: {master_rel}"))
            sr = int(meta.get("sample_rate") or 48000)
            total_sec = float(meta.get("duration_sec") or 0)
            channels = read_wav(master)
            left = channels[0]
            right = channels[1] if len(channels) > 1 else channels[0]
            preview = master.parent / "preview.mp3"
            encode_mp3(preview, left, right, bitrate=192, sample_rate=sr)
            files = [
                dict(relpath=preview.relative_to(dest).as_posix(), kind="preview",
                     stem_name=None, mime="audio/mpeg", bytes=preview.stat().st_size,
                     duration_sec=total_sec, sample_rate=sr, sha256=None),
                dict(relpath=master_rel, kind="master",
                     stem_name=None, mime="audio/wav", bytes=master.stat().st_size,
                     duration_sec=total_sec, sample_rate=sr, sha256=None),
            ]
            # sha256 后补（生成侧不阻塞导出）：与 MusicGen 一致登记
            from app.providers.music_musicgen import _sha256
            for f in files:
                f["sha256"] = _sha256(dest / f["relpath"])
            candidates.append(CandidateArtifact(
                label=label, seed=int(meta.get("seed") or request.seed),
                quality_score=None, duration_sec=total_sec,
                structure=[], style_tags=_style_tags(request.style_prompt),
                bpm=request.bpm, tonic=request.tonic, mode=request.mode,
                time_signature=request.time_signature,
                vocal=request.vocal, language=request.language, files=files,
            ))
        self.vocals_downgraded = False
        return GenerationOutput(candidates, [], False)


def _style_tags(style_prompt: str) -> list[str]:
    import re
    return [t for t in re.split(r"[，,。;；\s]+", style_prompt or "") if t][:4]
