"""自托管推理服务通道 Provider（V1.5.1 补充批，ADR-017）。

两个「本机/自托管」开源大模型通道——模型与推理服务不装进 Meloyu 后端
（依赖栈/官方推理路径均独立于本仓库），用户在任意环境启动推理服务后把
端点配进模型中心（llm_settings.local_service_hosts）：

  - mmax_local（MiniMax Music 3）：官方唯一推理路径 SGLang-Omni
    （Linux + 双 CUDA GPU），OpenAI 兼容 POST /v1/audio/speech，
    32kHz 16bit 立体声 wav 直返；
  - songgen_local（SongGeneration / LeVo）：社区 SongGeneration-Studio
    model server（Windows 可跑、低显存封装；v1 权重 base/full/large，
    v2 权重需 Linux/ComfyUI 路径自建），FastAPI /load + /generate，
    输出 flac（sample_rate 由模型 cfg 决定）。

显存/环境需求**不构成接入门槛**（用户测试时自行选择运行环境，ADR-017），
目录 local_note 仅如实标注。服务未运行时 fail-fast 给出启动指引，不阻断
其它通道；产物 master.wav（24bit PCM，模型原生采样率）+ preview.mp3，
无分轨/MIDI（与既有整曲通道同一导出规则；SongGeneration separate 分轨
能力未接入，留待后续）。
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import (
    AUDIOCPP_TASK_TIMEOUT_SEC,
    SELFHOSTED_DEFAULT_HOSTS,
    SELFHOSTED_PROBE_TIMEOUT_SEC,
)
from app.config import SELFHOSTED_TASK_TIMEOUT_SEC as _TIMEOUT
from app.core.i18n import tr
from app.core.logging import logger
from app.core.seed import candidate_seed
from app.providers.base import (
    CancelCheck,
    CandidateArtifact,
    GenerationOutput,
    ProgressCallback,
    SynthCancelled,
)
from app.providers.music_catalog import CATALOG_BY_ID
from app.synth.mp3_io import encode_mp3
from app.synth.wav_io import write_wav

# 声线预设 → 文本提示（模型经描述文本引导声线）
_VOCAL_DESC = {
    "female_air": "airy female vocals", "female_bright": "bright female vocals",
    "female_deep": "deep female vocals", "male_magnetic": "magnetic male vocals",
    "male_clear": "clear male vocals", "choir": "choir harmonies",
}

# SongGeneration-Studio 模型注册表（v1 权重，社区镜像 lglg666/SongGeneration-*），
# /load 时的优先级：时长完整版 → 更新版 → 基础版 → large
_SONGGEN_LOAD_ORDER = ("songgeneration_base_full", "songgeneration_base_new",
                       "songgeneration_base", "songgeneration_large")


class SelfHostedError(Exception):
    """自托管服务通道错误。kind ∈ service|runtime（service=服务不可达/未就绪）。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


_MMAX_HINT_ZH = ("MiniMax Music 3 推理服务未运行：官方路径为 SGLang-Omni（需 Linux + 双 CUDA "
                 "GPU），在服务机执行 `sgl-omni serve --model-path MiniMaxAI/MiniMax-Music3 "
                 "--port 8300` 后，在模型中心把端点配置到本通道（默认 http://127.0.0.1:8300）")
_MMAX_HINT_EN = ("MiniMax Music 3 inference service is not running: the official path is "
                 "SGLang-Omni (Linux + dual CUDA GPUs). On the service machine run "
                 "`sgl-omni serve --model-path MiniMaxAI/MiniMax-Music3 --port 8300`, then "
                 "configure the endpoint for this channel in the model center (default "
                 "http://127.0.0.1:8300)")
_SONGGEN_HINT_ZH = ("SongGeneration 推理服务未运行：在装有 SongGeneration-Studio 的环境启动其 "
                    "model server（端口默认 42100，Windows 可跑），或在模型中心把端点改为服务机"
                    "地址；权重经 Studio 界面下载（HF lglg666/SongGeneration-*）")
_SONGGEN_HINT_EN = ("SongGeneration inference service is not running: start its model server "
                    "in an environment with SongGeneration-Studio installed (default port "
                    "42100, runs on Windows), or point this channel's endpoint at the "
                    "service machine in the model center; weights download via the Studio "
                    "UI (HF lglg666/SongGeneration-*)")
_MMAX_LOCAL_HINT_ZH = ("MiniMax Music 3 本机推理未就绪：部署 audio.cpp（llama.cpp 音频分支，"
                       "Windows CUDA 预编译）与 GGUF 权重——backend/data/audiocpp/ 下放置 "
                       "audiocpp_cli.exe（GitHub 0xShug0/audio.cpp releases 的 windows-x64-"
                       "cuda12.4 包 + cudart 包解压）与 MiniMax-Music3-GGUF/（HF audio-cpp/"
                       "MiniMax-Music3-GGUF 默认 Q4/Q8/Q4 组件，约 8.4GB）")
_MMAX_LOCAL_HINT_EN = ("MiniMax Music 3 local inference is not ready: deploy audio.cpp (the "
                       "llama.cpp audio branch, Windows CUDA prebuilt) and the GGUF "
                       "weights - place audiocpp_cli.exe (from the windows-x64-cuda12.4 "
                       "plus cudart packages on GitHub 0xShug0/audio.cpp releases) and "
                       "MiniMax-Music3-GGUF/ (HF audio-cpp/MiniMax-Music3-GGUF, default "
                       "Q4/Q8/Q4 components, ~8.4GB) under backend/data/audiocpp/")


def mmax_hint() -> str:
    return tr(_MMAX_HINT_ZH, _MMAX_HINT_EN)


def songgen_hint() -> str:
    return tr(_SONGGEN_HINT_ZH, _SONGGEN_HINT_EN)


def mmax_local_hint() -> str:
    return tr(_MMAX_LOCAL_HINT_ZH, _MMAX_LOCAL_HINT_EN)


def _audiocpp_home() -> Path:
    from app.config import settings
    if settings.audiocpp_home:
        return Path(settings.audiocpp_home).resolve()
    return settings.data_path / "audiocpp"


# R-37：audio.cpp 通道级并发上限（生成线程池共 2 worker，慢通道独占 1）
_AUDIOCPP_SEMAPHORE = __import__("threading").BoundedSemaphore(1)


def _kill_process_tree(proc) -> None:
    """R-39：击杀整个进程树（子进程可能派生孙进程占显存，单 kill 泄漏）。

    Windows：taskkill /T /F；POSIX：进程组 SIGKILL 兜底单进程 kill。
    """
    import subprocess
    import sys
    try:
        if sys.platform == "win32" and proc.pid:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, check=False,
                           creationflags=0x08000000)
        else:
            import os
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
    except OSError:  # noqa: BLE001 —— 进程已退出的竞态
        pass


def _audiocpp_files() -> list:
    home = _audiocpp_home()
    gguf = home / "MiniMax-Music3-GGUF"
    need = ("language_model_q4_0.gguf", "rvq_depth_decoder_q8_0.gguf",
            "transformer_q4_0.gguf", "condition_encoder.gguf", "vocoder.gguf")
    return [home / "audiocpp_cli.exe"] + [gguf / n for n in need]


def audiocpp_verify() -> tuple[bool, str]:
    """P1-10 供应链校验：data/audiocpp/SHA256SUMS 存在时逐文件校验（进程内缓存一次）。

    部署方生成清单（在部署目录执行）：
      certutil -hashfile audiocpp_cli.exe SHA256  →  逐行 "<sha256>  <相对路径>" 写入
    清单不存在 = 宽松模式（仅存在性检查，兼容现状）；存在即严格模式。
    """
    global _AUDIOCPP_VERIFIED
    if _AUDIOCPP_VERIFIED is not None:
        return _AUDIOCPP_VERIFIED
    import hashlib
    home = _audiocpp_home()
    manifest = home / "SHA256SUMS"
    if not manifest.exists():
        _AUDIOCPP_VERIFIED = (True, "")
        return _AUDIOCPP_VERIFIED
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            expected[parts[1].strip().replace("\\", "/")] = parts[0].strip().lower()
    for f in _audiocpp_files():
        rel = f.relative_to(home).as_posix()
        want = expected.get(rel)
        if want is None:
            continue
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                h.update(chunk)
        if h.hexdigest() != want:
            msg = f"integrity check failed: {rel}"
            _AUDIOCPP_VERIFIED = (False, msg)
            return _AUDIOCPP_VERIFIED
    _AUDIOCPP_VERIFIED = (True, "")
    return _AUDIOCPP_VERIFIED


_AUDIOCPP_VERIFIED: tuple[bool, str] | None = None


def audiocpp_ready() -> bool:
    """本地 audio.cpp 形态就绪：CLI 与默认 GGUF 组件齐备 + 完整性清单（如提供）。"""
    if not all(f.exists() for f in _audiocpp_files()):
        return False
    ok, _ = audiocpp_verify()
    return ok


def service_host(channel: str, hosts: dict | None) -> str:
    """通道端点：配置覆盖 > 默认（mmax_local=SGLang / songgen_local=Studio）。

    容器内默认端点自动指向宿主机别名：127.0.0.1 在容器里是容器自身，
    host.docker.internal（Docker Desktop 内置域名）才可达宿主机服务——
    与模型中心 Ollama host 的容器回退同一逻辑（deploy/README 已知限制表）。
    """
    hosts = hosts or {}
    v = str(hosts.get(channel) or "").strip().rstrip("/")
    if v:
        return v
    default = SELFHOSTED_DEFAULT_HOSTS.get(channel, "")
    if default.startswith("http://127.0.0.1") and Path("/.dockerenv").exists():
        default = default.replace("http://127.0.0.1", "http://host.docker.internal")
    return default


def probe_service(channel: str, hosts: dict | None) -> dict:
    """探活（供目录 local_status 与通道校验）：{running, detail, hint}。

    mmax_local 双形态：本地 audio.cpp（CLI+GGUF 齐备即可用，优先）或 SGLang-Omni
    端点（用户自托管服务）——任一就绪即 running。
    """
    host = service_host(channel, hosts)
    if channel == "mmax_local":
        if audiocpp_ready():
            return {"running": True,
                    "detail": tr("本机 audio.cpp · MiniMax-Music3 GGUF Q4/Q8/Q4（已部署）",
                                 "Local audio.cpp · MiniMax-Music3 GGUF Q4/Q8/Q4 (deployed)"),
                    "hint": mmax_local_hint(), "host": "local"}
        hint = mmax_hint()
        try:
            with httpx.Client(timeout=SELFHOSTED_PROBE_TIMEOUT_SEC, trust_env=False) as c:
                r = c.get(f"{host}/v1/models")
            ok = r.status_code == 200
            return {"running": ok,
                    "detail": (f"{host} · SGLang-Omni "
                               + tr("在线" if ok else "异常", "online" if ok else "error")
                               + tr("（本机 audio.cpp 未部署）",
                                    " (local audio.cpp not deployed)")),
                    "hint": hint, "host": host}
        except Exception as e:  # noqa: BLE001 —— 探活失败=服务不在
            return {"running": False,
                    "detail": f"{host} · {type(e).__name__}"
                              + tr("；本机 audio.cpp 未部署",
                                   "; local audio.cpp not deployed"),
                    "hint": hint, "host": host}
    if channel == "songgen_local":
        hint = songgen_hint()
        try:
            # trust_env=False：TUN 系统代理会劫持 loopback 长连接（v0.6.1 修复漏网处）
            with httpx.Client(timeout=SELFHOSTED_PROBE_TIMEOUT_SEC, trust_env=False) as c:
                h = c.get(f"{host}/health")
                s = c.get(f"{host}/status").json() if h.status_code == 200 else {}
            ok = h.status_code == 200
            loaded = bool(s.get("loaded"))
            model = s.get("model_id") or ""
            return {"running": ok,
                    "detail": (f"{host} · Studio "
                               + tr("在线" if ok else "离线", "online" if ok else "offline")
                               + (tr(f"（已载入 {model}）", f" (loaded {model})")
                                  if loaded else tr("（未载入模型）",
                                                    " (no model loaded)"))),
                    "hint": hint, "host": host}
        except Exception as e:  # noqa: BLE001
            return {"running": False, "detail": f"{host} · {type(e).__name__}", "hint": hint,
                    "host": host}
    return {"running": False,
            "detail": tr(f"未知通道：{channel}", f"Unknown channel: {channel}"),
            "hint": "", "host": host}


def _stage(progress: ProgressCallback, should_cancel: CancelCheck, key: str, pct: int,
           label: str) -> None:
    if should_cancel():
        raise SynthCancelled()
    progress(key, pct, label)


def _caption(request) -> str:
    caption = (request.style_prompt or "pop music").strip()
    desc = _VOCAL_DESC.get(request.vocal, "")
    return f"{caption}, {desc}" if desc else caption


def _finalize_audio(raw: bytes | Path, dest: Path, label: str, sr_expected: int | None) -> dict:
    """模型原生音频（wav bytes / flac 路径）→ 24bit PCM master + 192k preview。

    返回 {relpath, duration_sec, sample_rate, preview_bytes...}；采样率以音频头
    实测为准（mmax 32kHz / sg2 由模型 cfg 决定），不做重采样（导出侧已按母带
    真实采样率编码，ADR：MP3 变速缺陷修复约定）。
    """
    import io

    import numpy as np
    import soundfile as sf

    if isinstance(raw, bytes):
        data, sr = sf.read(io.BytesIO(raw), dtype="float64", always_2d=True)
    else:
        data, sr = sf.read(str(raw), dtype="float64", always_2d=True)
    if sr_expected and sr != sr_expected:
        logger.info(f"selfhosted 采样率与预期不符（{sr} != {sr_expected}），以实测为准")
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    cand_dir = dest / "candidates" / label
    cand_dir.mkdir(parents=True, exist_ok=True)
    master = cand_dir / "master.wav"
    write_wav(master, [data[:, 0], data[:, 1]], bits=24, sample_rate=sr)
    preview = cand_dir / "preview.mp3"
    encode_mp3(preview, data[:, 0], data[:, 1], bitrate=192, sample_rate=sr)
    total = round(len(data) / sr, 2)
    from app.providers.music_musicgen import _sha256
    return {
        "relpath": f"candidates/{label}/master.wav",
        "preview_relpath": f"candidates/{label}/preview.mp3",
        "duration_sec": total, "sample_rate": sr,
        "master_bytes": master.stat().st_size, "preview_bytes": preview.stat().st_size,
        "master_sha": _sha256(master), "preview_sha": _sha256(preview),
    }


def _artifact(request, label: str, meta: dict, seed: int) -> CandidateArtifact:
    import re
    files = [
        dict(relpath=meta["preview_relpath"], kind="preview", stem_name=None,
             mime="audio/mpeg", bytes=meta["preview_bytes"],
             duration_sec=meta["duration_sec"], sample_rate=meta["sample_rate"],
             sha256=meta["preview_sha"]),
        dict(relpath=meta["relpath"], kind="master", stem_name=None, mime="audio/wav",
             bytes=meta["master_bytes"], duration_sec=meta["duration_sec"],
             sample_rate=meta["sample_rate"], sha256=meta["master_sha"]),
    ]
    return CandidateArtifact(
        label=label, seed=seed, quality_score=None, duration_sec=meta["duration_sec"],
        structure=[], style_tags=[t for t in re.split(r"[，,。;；\s]+", request.style_prompt or "")
                                  if t][:4],
        bpm=request.bpm, tonic=request.tonic, mode=request.mode,
        time_signature=request.time_signature, vocal=request.vocal,
        language=request.language, files=files,
    )


def _check_channel(model_id: str, channel: str) -> None:
    if channel not in CATALOG_BY_ID.get(model_id, {}).get("channels", []):
        raise SelfHostedError(
            "service",
            tr(f"模型不支持 {channel} 通道：{model_id}",
               f"Model does not support the {channel} channel: {model_id}"))


class MiniMaxSelfHostedProvider:
    """MusicProvider：MiniMax Music 3——本机 audio.cpp（GGUF 量化，优先）或
    SGLang-Omni 服务（OpenAI 兼容 speech API，官方路径）。"""

    name = "mmax_local"
    base_display = "MiniMax Music 3 · Self-hosted service"
    supports_vocals = True
    timeout_sec = _TIMEOUT
    vocals_downgraded = False

    def __init__(self, model_id: str, hosts: dict | None = None):
        _check_channel(model_id, self.name)
        self.display_name = "MiniMax Music 3 · " + CATALOG_BY_ID[model_id]['name']
        self.host = service_host(self.name, hosts)
        # 真实业务测试（2026-09-02）抓到的时序缺陷：任务层熔断在 generate() 调用前
        # 读取 timeout_sec，若 audio.cpp 的 4h 覆盖留在 _generate_local 内部才做，
        # 读到的仍是 1800s 默认值 → 本机形态任务被误熔断。构造期即按形态定型：
        self.timeout_sec = (AUDIOCPP_TASK_TIMEOUT_SEC if audiocpp_ready()
                            else _TIMEOUT)

    # ---------- 本地 audio.cpp 形态 ----------

    def _generate_local(self, request, progress, should_cancel, dest: Path):

        from app.config import AUDIOCPP_TASK_TIMEOUT_SEC
        # 本地 Q4 量化实测 RTF~94（双候选可能 1 小时+），放宽任务熔断
        self.timeout_sec = AUDIOCPP_TASK_TIMEOUT_SEC
        # R-37 容量治理：audio.cpp 单任务可占 GPU 数十分钟~4h，通道级并发上限 1，
        # 防止两个慢任务占满 2-worker 生成池拖瘫全站
        if not _AUDIOCPP_SEMAPHORE.acquire(blocking=False):
            _stage(progress, should_cancel, "model_load", 5,
                   tr("audio.cpp 通道忙碌（并发上限 1），排队等待…",
                      "audio.cpp channel busy (concurrency limit 1), waiting in queue…"))
            _AUDIOCPP_SEMAPHORE.acquire()
        try:
            return self._generate_local_inner(request, progress, should_cancel, dest)
        finally:
            _AUDIOCPP_SEMAPHORE.release()

    def _generate_local_inner(self, request, progress, should_cancel, dest: Path):
        import queue
        import subprocess
        import sys
        import threading

        from app.config import AUDIOCPP_TASK_TIMEOUT_SEC
        self.timeout_sec = AUDIOCPP_TASK_TIMEOUT_SEC
        home = _audiocpp_home()
        lyrics = (request.lyrics or "").strip() or "[Instrumental]"
        duration = max(10, min(int(request.duration_sec), 300))
        instructions = _caption(request)
        if request.vocal == "instrumental":
            instructions = f"{instructions}, instrumental, no vocals"
        candidates: list[CandidateArtifact] = []
        # RTF 实测 ~94（4060 Ti 8GB 跑 Q4 8B）：双候选如实双倍时长，
        # 目录 note 已标注速度，用户自行权衡时长
        for i in range(2):
            label = chr(ord("A") + i)
            est = duration * 94 // 60 + 1
            _stage(progress, should_cancel, "model_sample", 15 + i * 35,
                   tr(f"MiniMax Music 3（本机 audio.cpp Q4/Q8/Q4）生成候选 {label}"
                      f"（约 {est} 分钟/候选）…",
                      f"MiniMax Music 3 (local audio.cpp Q4/Q8/Q4) generating candidate "
                      f"{label} (~{est} min per candidate)…"))
            out_wav = dest / f"_mmax_{label}.wav"
            cmd = [str(home / "audiocpp_cli.exe"), "--task", "gen",
                   "--family", "minimax_music3", "--model", "MiniMax-Music3-GGUF",
                   "--backend", "cuda", "--threads", "8",
                   "--text", instructions[:500],
                   "--request-option", f"lyrics={lyrics[:2000]}",
                   "--request-option", f"duration_sec={duration}",
                   "--request-option", "num_inference_steps=30",
                   "--out", str(out_wav)]
            flags = 0x08000000 if sys.platform == "win32" else 0
            proc = subprocess.Popen(
                cmd, cwd=str(home), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=flags)
            # CLI 输出行稀疏（TIMING 间歇刷）：同步 readline 会数十秒~分钟级阻塞、
            # 取消标志无人查询（E2E 实测命中）——reader 线程 + 队列 1s 轮询取消
            lines: queue.Queue[str] = queue.Queue()

            def _pump(p=proc, q=lines):
                try:
                    for ln in p.stdout or []:
                        q.put(ln)
                finally:
                    q.put("")  # EOF 哨兵

            threading.Thread(target=_pump, daemon=True).start()

            def _kill(p=proc):  # 默认参绑定：防循环变量延迟绑定（B023）
                _kill_process_tree(p)

            watchdog = threading.Timer(self.timeout_sec, _kill)
            watchdog.daemon = True
            watchdog.start()
            tail = ""
            try:
                while True:
                    try:
                        line = lines.get(timeout=1.0)
                    except queue.Empty:
                        if should_cancel():
                            _kill()
                            raise SynthCancelled() from None
                        continue
                    if line == "":
                        break
                    tail = (tail + line)[-600:]
                proc.wait(timeout=60)
                if should_cancel():  # EOF 也可能由取消 kill 引起
                    raise SynthCancelled()
                if proc.returncode != 0 or not out_wav.exists():
                    raise SelfHostedError(
                        "runtime",
                        tr(f"audio.cpp 生成失败（码 {proc.returncode}）：{tail[-300:]}",
                           f"audio.cpp generation failed (code {proc.returncode}): "
                           f"{tail[-300:]}"))
            finally:
                watchdog.cancel()
                _kill()
            _stage(progress, should_cancel, "model_export", 80 + i * 8,
                       tr("导出音频…", "Exporting audio…"))
            meta = _finalize_audio(out_wav, dest, label, sr_expected=44100)
            out_wav.unlink(missing_ok=True)
            candidates.append(
                _artifact(request, label, meta, candidate_seed(request.seed, label)))
        self.vocals_downgraded = False
        return GenerationOutput(candidates, [], False)

    # ---------- SGLang-Omni 端点形态 ----------
    def generate(self, request, progress: ProgressCallback, should_cancel: CancelCheck,
                 dest_dir: str) -> GenerationOutput:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        st = probe_service(self.name, {self.name: self.host})
        if audiocpp_ready():
            return self._generate_local(request, progress, should_cancel, dest)
        if not st["running"]:
            raise SelfHostedError("service", st["hint"])

        lyrics = (request.lyrics or "").strip() or "[Instrumental]"
        duration = max(10, min(int(request.duration_sec), 300))  # 9000 帧 ≈ 5 分钟上限
        instructions = _caption(request)
        if request.vocal == "instrumental":
            instructions = f"{instructions}, instrumental, no vocals"
        candidates: list[CandidateArtifact] = []
        seeds = [request.seed, request.seed ^ 0x9E3779B9]
        with httpx.Client(timeout=self.timeout_sec, trust_env=False) as client:
            for i, seed in enumerate(seeds):
                label = chr(ord("A") + i)
                _stage(progress, should_cancel, "model_sample", 20 + i * 35,
                       tr(f"MiniMax Music 3 生成候选 {label}（SGLang 服务，约 1~5 分钟）…",
                          f"MiniMax Music 3 generating candidate {label} (SGLang service, "
                          f"~1-5 minutes)…"))
                r = client.post(f"{self.host}/v1/audio/speech", json={
                    "model": "minimax_ttm", "input": lyrics, "instructions": instructions,
                    "response_format": "wav", "seed": int(seed),
                    "max_new_tokens": min(9000, int(duration * 30)), "stream": False,
                })
                if r.status_code != 200:
                    raise SelfHostedError(
                        "runtime",
                        tr(f"SGLang 服务返回 {r.status_code}：{r.text[:200]}",
                           f"SGLang service returned {r.status_code}: {r.text[:200]}"))
                _stage(progress, should_cancel, "model_export", 80 + i * 8,
                       tr("导出音频…", "Exporting audio…"))
                meta = _finalize_audio(r.content, dest, label, sr_expected=32000)
                candidates.append(_artifact(request, label, meta, seed))
        self.vocals_downgraded = False
        return GenerationOutput(candidates, [], False)


class SongGenSelfHostedProvider:
    """MusicProvider：SongGeneration（LeVo）经 SongGeneration-Studio model server。"""

    name = "songgen_local"
    base_display = "SongGeneration · Self-hosted service"
    supports_vocals = True
    timeout_sec = _TIMEOUT
    vocals_downgraded = False

    def __init__(self, model_id: str, hosts: dict | None = None):
        _check_channel(model_id, self.name)
        self.display_name = ("SongGeneration · " + CATALOG_BY_ID[model_id]['name']
                             )
        self.host = service_host(self.name, hosts)

    def _ensure_model(self, client: httpx.Client) -> str:
        """确保 Studio 已载入模型（按注册表优先级自动 /load）；返回 model_id。"""
        s = client.get(f"{self.host}/status").json()
        if s.get("loaded") and s.get("model_id"):
            return str(s["model_id"])
        for mid in _SONGGEN_LOAD_ORDER:
            r = client.post(f"{self.host}/load", json={"model_id": mid}).json()
            if r.get("status") in ("loaded", "already_loaded"):
                return mid
            err = str(r.get("error") or "")
            if "not found" not in err.lower():
                raise SelfHostedError(
                    "runtime", tr(f"加载模型失败：{err[:200]}",
                                  f"Failed to load model: {err[:200]}"))
        raise SelfHostedError(
            "service",
            tr("Studio 已运行但未找到已下载的模型权重：请在 Studio 界面下载"
               "（HF lglg666/SongGeneration-*，约 11~21GB）后重试，或在其界面手动加载模型",
               "Studio is running but no downloaded model weights were found: download "
               "them in the Studio UI (HF lglg666/SongGeneration-*, ~11-21GB) and retry, "
               "or load a model manually in its UI"))

    def generate(self, request, progress: ProgressCallback, should_cancel: CancelCheck,
                 dest_dir: str) -> GenerationOutput:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        st = probe_service(self.name, {self.name: self.host})
        if not st["running"]:
            raise SelfHostedError("service", st["hint"])

        gen_type = "bgm" if request.vocal == "instrumental" else "mixed"
        description = _caption(request)
        if request.vocal == "instrumental":
            description = f"{description}, instrumental, no vocals"
        candidates: list[CandidateArtifact] = []
        work = dest / "_sg2_work"
        work.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(timeout=self.timeout_sec, trust_env=False) as client:
                _stage(progress, should_cancel, "model_load", 8,
                       tr("检查 Studio 模型载入…", "Checking Studio model load…"))
                loaded = self._ensure_model(client)
                for i in range(2):
                    label = chr(ord("A") + i)
                    _stage(progress, should_cancel, "model_sample", 20 + i * 35,
                           tr(f"SongGeneration（{loaded}）生成候选 {label}（自回归+扩散，"
                              f"视显存 2~20 分钟）…",
                              f"SongGeneration ({loaded}) generating candidate {label} "
                              f"(autoregressive + diffusion, 2-20 minutes depending on "
                              f"VRAM)…"))
                    input_path = work / f"input_{label}.jsonl"
                    input_path.write_text(json.dumps({
                        "gt_lyric": (request.lyrics or "").strip() or "[Instrumental]",
                        "descriptions": description, "idx": label,
                        "duration": max(10, min(int(request.duration_sec), 270)),
                        "temperature": 0.9, "cfg_coef": 1.5,
                    }, ensure_ascii=False), encoding="utf-8")
                    r = client.post(f"{self.host}/generate", json={
                        "input_jsonl": str(input_path), "save_dir": str(work / label),
                        "gen_type": gen_type,
                    }).json()
                    if r.get("status") == "cancelled":
                        raise SynthCancelled()
                    if r.get("error"):
                        raise SelfHostedError(
                            "runtime",
                            tr(f"Studio 生成失败：{str(r['error'])[:200]}",
                               f"Studio generation failed: {str(r['error'])[:200]}"))
                    out = r.get("output_file")
                    if not out or not Path(out).exists():
                        raise SelfHostedError(
                            "runtime",
                            tr(f"Studio 未返回音频：{str(r)[:200]}",
                               f"Studio returned no audio: {str(r)[:200]}"))
                    _stage(progress, should_cancel, "model_export", 80 + i * 8,
                       tr("导出音频…", "Exporting audio…"))
                    meta = _finalize_audio(Path(out), dest, label, sr_expected=None)
                    candidates.append(
                        _artifact(request, label, meta, candidate_seed(request.seed, label)))
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        self.vocals_downgraded = False
        return GenerationOutput(candidates, [], False)
