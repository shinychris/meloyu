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

from app.config import SELFHOSTED_DEFAULT_HOSTS, SELFHOSTED_PROBE_TIMEOUT_SEC
from app.config import SELFHOSTED_TASK_TIMEOUT_SEC as _TIMEOUT
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


MMAX_HINT = ("MiniMax Music 3 推理服务未运行：官方路径为 SGLang-Omni（需 Linux + 双 CUDA "
             "GPU），在服务机执行 `sgl-omni serve --model-path MiniMaxAI/MiniMax-Music3 "
             "--port 8300` 后，在模型中心把端点配置到本通道（默认 http://127.0.0.1:8300）")
SONGGEN_HINT = ("SongGeneration 推理服务未运行：在装有 SongGeneration-Studio 的环境启动其 "
                "model server（端口默认 42100，Windows 可跑），或在模型中心把端点改为服务机"
                "地址；权重经 Studio 界面下载（HF lglg666/SongGeneration-*）")


def service_host(channel: str, hosts: dict | None) -> str:
    """通道端点：配置覆盖 > 默认（mmax_local=SGLang / songgen_local=Studio）。"""
    hosts = hosts or {}
    v = str(hosts.get(channel) or "").strip().rstrip("/")
    return v or SELFHOSTED_DEFAULT_HOSTS.get(channel, "")


def probe_service(channel: str, hosts: dict | None) -> dict:
    """探活（供目录 local_status 与通道校验）：{running, detail, hint}。"""
    host = service_host(channel, hosts)
    if channel == "mmax_local":
        hint = MMAX_HINT
        try:
            with httpx.Client(timeout=SELFHOSTED_PROBE_TIMEOUT_SEC) as c:
                r = c.get(f"{host}/v1/models")
            ok = r.status_code == 200
            return {"running": ok, "detail": f"{host} · SGLang-Omni {'在线' if ok else '异常'}",
                    "hint": hint, "host": host}
        except Exception as e:  # noqa: BLE001 —— 探活失败=服务不在
            return {"running": False, "detail": f"{host} · {type(e).__name__}", "hint": hint,
                    "host": host}
    if channel == "songgen_local":
        hint = SONGGEN_HINT
        try:
            with httpx.Client(timeout=SELFHOSTED_PROBE_TIMEOUT_SEC) as c:
                h = c.get(f"{host}/health")
                s = c.get(f"{host}/status").json() if h.status_code == 200 else {}
            ok = h.status_code == 200
            loaded = bool(s.get("loaded"))
            model = s.get("model_id") or ""
            return {"running": ok,
                    "detail": f"{host} · Studio{'在线' if ok else '离线'}"
                              f"{'（已载入 ' + model + '）' if loaded else '（未载入模型）'}",
                    "hint": hint, "host": host}
        except Exception as e:  # noqa: BLE001
            return {"running": False, "detail": f"{host} · {type(e).__name__}", "hint": hint,
                    "host": host}
    return {"running": False, "detail": f"未知通道：{channel}", "hint": "", "host": host}


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
        raise SelfHostedError("service", f"模型不支持 {channel} 通道：{model_id}")


class MiniMaxSelfHostedProvider:
    """MusicProvider：MiniMax Music 3 经 SGLang-Omni（OpenAI 兼容 speech API）。"""

    name = "mmax_local"
    base_display = "MiniMax Music 3 · 自托管服务"
    supports_vocals = True
    timeout_sec = _TIMEOUT
    vocals_downgraded = False

    def __init__(self, model_id: str, hosts: dict | None = None):
        _check_channel(model_id, self.name)
        self.display_name = f"MiniMax Music 3 · {CATALOG_BY_ID[model_id]['name']}（自托管）"
        self.host = service_host(self.name, hosts)

    def generate(self, request, progress: ProgressCallback, should_cancel: CancelCheck,
                 dest_dir: str) -> GenerationOutput:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        st = probe_service(self.name, {self.name: self.host})
        if not st["running"]:
            raise SelfHostedError("service", st["hint"])

        lyrics = (request.lyrics or "").strip() or "[Instrumental]"
        duration = max(10, min(int(request.duration_sec), 300))  # 9000 帧 ≈ 5 分钟上限
        instructions = _caption(request)
        if request.vocal == "instrumental":
            instructions = f"{instructions}, instrumental, no vocals"
        candidates: list[CandidateArtifact] = []
        seeds = [request.seed, request.seed ^ 0x9E3779B9]
        with httpx.Client(timeout=self.timeout_sec) as client:
            for i, seed in enumerate(seeds):
                label = chr(ord("A") + i)
                _stage(progress, should_cancel, "model_sample", 20 + i * 35,
                       f"MiniMax Music 3 生成候选 {label}（SGLang 服务，约 1~5 分钟）…")
                r = client.post(f"{self.host}/v1/audio/speech", json={
                    "model": "minimax_ttm", "input": lyrics, "instructions": instructions,
                    "response_format": "wav", "seed": int(seed),
                    "max_new_tokens": min(9000, int(duration * 30)), "stream": False,
                })
                if r.status_code != 200:
                    raise SelfHostedError(
                        "runtime", f"SGLang 服务返回 {r.status_code}：{r.text[:200]}")
                _stage(progress, should_cancel, "model_export", 80 + i * 8, "导出音频…")
                meta = _finalize_audio(r.content, dest, label, sr_expected=32000)
                candidates.append(_artifact(request, label, meta, seed))
        self.vocals_downgraded = False
        return GenerationOutput(candidates, [], False)


class SongGenSelfHostedProvider:
    """MusicProvider：SongGeneration（LeVo）经 SongGeneration-Studio model server。"""

    name = "songgen_local"
    base_display = "SongGeneration · 自托管服务"
    supports_vocals = True
    timeout_sec = _TIMEOUT
    vocals_downgraded = False

    def __init__(self, model_id: str, hosts: dict | None = None):
        _check_channel(model_id, self.name)
        self.display_name = f"SongGeneration · {CATALOG_BY_ID[model_id]['name']}（自托管）"
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
                raise SelfHostedError("runtime", f"加载模型失败：{err[:200]}")
        raise SelfHostedError(
            "service", "Studio 已运行但未找到已下载的模型权重：请在 Studio 界面下载"
            "（HF lglg666/SongGeneration-*，约 11~21GB）后重试，或在其界面手动加载模型")

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
            with httpx.Client(timeout=self.timeout_sec) as client:
                _stage(progress, should_cancel, "model_load", 8, "检查 Studio 模型载入…")
                loaded = self._ensure_model(client)
                for i in range(2):
                    label = chr(ord("A") + i)
                    _stage(progress, should_cancel, "model_sample", 20 + i * 35,
                           f"SongGeneration（{loaded}）生成候选 {label}（自回归+扩散，"
                           "视显存 2~20 分钟）…")
                    input_path = work / f"input_{label}.jsonl"
                    input_path.write_text(json.dumps({
                        "gt_lyric": (request.lyrics or "").strip() or "[Instrumental]",
                        "descriptions": description, "idx": label,
                        "temperature": 0.9, "cfg_coef": 1.5,
                    }, ensure_ascii=False), encoding="utf-8")
                    r = client.post(f"{self.host}/generate", json={
                        "input_jsonl": str(input_path), "save_dir": str(work / label),
                        "gen_type": gen_type,
                    }).json()
                    if r.get("status") == "cancelled":
                        raise SynthCancelled()
                    if r.get("error"):
                        raise SelfHostedError("runtime", f"Studio 生成失败：{str(r['error'])[:200]}")
                    out = r.get("output_file")
                    if not out or not Path(out).exists():
                        raise SelfHostedError("runtime", f"Studio 未返回音频：{str(r)[:200]}")
                    _stage(progress, should_cancel, "model_export", 80 + i * 8, "导出音频…")
                    meta = _finalize_audio(Path(out), dest, label, sr_expected=None)
                    candidates.append(
                        _artifact(request, label, meta, candidate_seed(request.seed, label)))
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        self.vocals_downgraded = False
        return GenerationOutput(candidates, [], False)
