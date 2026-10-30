"""MusicGen 本地开源模型 Provider（V1.4「多类开源模型接入」，ADR-014）。

本机 transformers 直跑 Meta 开源 MusicGen（facebook/musicgen-small|medium）：
  - 模型权重经 huggingface_hub snapshot_download 真实下载（进度回调写 model_ops，
    与 Ollama pull 同一体验），缓存于 backend/data/hf_cache/；
  - 推理 torch CPU（small：30s 器乐约 2~6 分钟；medium 更慢，目录 note 已标注）；
  - 仅支持器乐（无歌词/人声输入）：vocal!=instrumental 的请求自动降级为器乐，
    候选 vocal 如实记 instrumental，事件留痕 vocals_downgraded；
  - 产物 master.wav（原始采样率 24bit）+ preview.mp3，无分轨/MIDI（导出侧拦截）。

依赖为可选安装（torch/transformers 体积大，不进主 requirements）：
    ./.venv/Scripts/python -m pip install -r requirements-musicgen.txt
未安装时：通道构造/下载/生成给出明确 install_hint（与 Ollama 未安装的处理一致）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import threading
from pathlib import Path

from app.config import MUSICGEN_TASK_TIMEOUT_SEC, settings
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
from app.synth.ir import SongRequest
from app.synth.mp3_io import encode_mp3
from app.synth.wav_io import write_wav

_INSTALL_HINT_ZH = ("本机 MusicGen 依赖未安装（torch/transformers 较大，未随主依赖安装）："
                    "backend/ 下执行 ./.venv/Scripts/python -m pip install -r "
                    "requirements-musicgen.txt 后重启服务")
_INSTALL_HINT_EN = ("Local MusicGen dependencies are not installed (torch/transformers are "
                    "large and not in the main requirements): from backend/ run ./.venv/"
                    "Scripts/python -m pip install -r requirements-musicgen.txt, then "
                    "restart the server")


def _install_hint() -> str:
    return tr(_INSTALL_HINT_ZH, _INSTALL_HINT_EN)


def musicgen_install_hint() -> str:
    return _install_hint()


def _apply_hf_endpoint() -> None:
    """HF_ENDPOINT 覆盖（.env 配 hf_endpoint=https://hf-mirror.com 走国内镜像）。

    同时禁用 hf-xet 传输协议：xet 走独立 CDN 端点，过代理/镜像时常挂起
    （本机部署实测 72% 停滞）；普通 HTTPS 支持断点续传，代理友好。
    """
    import os
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    if settings.hf_endpoint:
        os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)


# 进程级标记：CUDA 设备断言毒化上下文后置 True，本进程后续生成一律走 CPU
# （重启服务后自动恢复尝试 GPU）
_CUDA_POISONED = {"flag": False}

# P1-9 模型常驻缓存：同一模型在进程生命周期内只 from_pretrained 一次
# （原实现每次生成都冷加载权重，small 也要分钟级）。GPU 采样全程持锁串行
# （transformers generate 非线程安全，且单卡显存本就只能串行）。
_MODEL_CACHE: dict[str, tuple] = {}
_GEN_LOCK = threading.Lock()


def _load_or_get(hf_id: str, device: str):
    """加载或复用常驻模型；返回 (model, processor, sampling_rate)。"""
    if f"{hf_id}@{device}" not in _MODEL_CACHE:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        model = MusicgenForConditionalGeneration.from_pretrained(
            hf_id, cache_dir=str(hf_cache_dir())).to(device)
        processor = AutoProcessor.from_pretrained(hf_id, cache_dir=str(hf_cache_dir()))
        _MODEL_CACHE[f"{hf_id}@{device}"] = (model, processor,
                                             model.config.audio_encoder.sampling_rate)
    return _MODEL_CACHE[f"{hf_id}@{device}"]


def _evict_model_cache(hf_id: str | None = None) -> None:
    """清缓存（模型删除后/毒化降级时调用，防引用已删权重）。"""
    for k in [k for k in _MODEL_CACHE if hf_id is None or k.startswith(f"{hf_id}@")]:
        _MODEL_CACHE.pop(k, None)


class MusicGenLocalError(Exception):
    """MusicGen 本地通道错误。kind ∈ deps|download|runtime。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def musicgen_deps_installed() -> bool:
    return all(importlib.util.find_spec(m) for m in ("torch", "transformers"))


def hf_cache_dir() -> Path:
    return settings.data_path / "hf_cache"


def _snapshot_prefix(hf_id: str) -> str:
    return hf_id.replace("/", "--")


def is_downloaded(model_id: str) -> bool:
    entry = CATALOG_BY_ID.get(model_id)
    if not entry or not entry.get("local_hf_id"):
        return False
    pattern = f"models--{_snapshot_prefix(entry['local_hf_id'])}/snapshots/*/config.json"
    return bool(next(hf_cache_dir().glob(pattern), None))


def local_downloaded_ids() -> list[str]:
    return [m["id"] for m in CATALOG_BY_ID.values()
            if "musicgen_local" in m["channels"] and is_downloaded(m["id"])]


def delete_local(model_id: str) -> None:
    _evict_model_cache()  # 删除权重后弃用常驻实例（防引用已删文件）
    entry = CATALOG_BY_ID.get(model_id)
    if not entry or not entry.get("local_hf_id"):
        raise MusicGenLocalError(
            "download", tr(f"模型不支持本地删除：{model_id}",
                           f"Model does not support local deletion: {model_id}"))
    target = hf_cache_dir() / f"models--{_snapshot_prefix(entry['local_hf_id'])}"
    if target.exists():
        shutil.rmtree(target)


def pull_local(model_id: str, on_progress) -> None:
    """真实下载模型权重（huggingface_hub），进度经 on_progress(pct, message) 上报。"""
    entry = CATALOG_BY_ID.get(model_id)
    if not entry or "musicgen_local" not in entry.get("channels", []):
        raise MusicGenLocalError(
            "download", tr(f"模型不支持本地下载：{model_id}",
                           f"Model does not support local download: {model_id}"))
    if not musicgen_deps_installed():
        raise MusicGenLocalError("deps", _install_hint())
    from huggingface_hub import snapshot_download
    from tqdm import tqdm

    _apply_hf_endpoint()

    class _OpTqdm(tqdm):
        """把 HF 的下载进度条回调映射到 model_ops 进度（以主权重文件为准）。"""

        def update(self, n=1):
            super().update(n)
            try:
                if self.total:
                    pct = max(1, min(99, int(self.n * 100 / self.total)))
                    on_progress(pct, tr(f"{self.desc or '下载'} {pct}%",
                                        f"{self.desc or 'Downloading'} {pct}%"))
            except Exception:  # noqa: BLE001 —— 进度回调不允许影响下载
                pass

    on_progress(1, tr("连接 Hugging Face…", "Connecting to Hugging Face…"))
    snapshot_download(entry["local_hf_id"], cache_dir=str(hf_cache_dir()),
                      tqdm_class=_OpTqdm)
    on_progress(100, tr(f"已下载 {entry['name']}", f"Downloaded {entry['name']}"))


def _stage(progress: ProgressCallback, should_cancel: CancelCheck, key: str, pct: int,
           label: str) -> None:
    if should_cancel():
        raise SynthCancelled()
    progress(key, pct, label)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _style_tags(style_prompt: str) -> list[str]:
    return [t for t in re.split(r"[，,。;；\s]+", style_prompt or "") if t][:4]


class MusicGenLocalProvider:
    """MusicProvider 协议实现：本机 MusicGen 推理（器乐）。"""

    name = "musicgen_local"
    base_display = "Local MusicGen (open source)"
    supports_vocals = False
    timeout_sec = MUSICGEN_TASK_TIMEOUT_SEC
    vocals_downgraded = False

    def __init__(self, model_id: str):
        entry = CATALOG_BY_ID.get(model_id)
        if entry is None or "musicgen_local" not in entry.get("channels", []):
            raise MusicGenLocalError("download",
                                     tr(f"模型不支持本机运行：{model_id}（需 GPU 档请走 Replicate）",
                                        f"Model does not support local execution: {model_id} "
                                        f"(GPU-only tiers should use Replicate)"))
        self.model_id = model_id
        self.hf_id = entry["local_hf_id"]
        self.max_duration = int(entry["capabilities"]["max_duration_sec"])
        self.display_name = tr("MusicGen 本地 · ", "MusicGen Local · ") + entry['name']

    def generate(
        self,
        request: SongRequest,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        if not musicgen_deps_installed():
            raise MusicGenLocalError("deps", _install_hint())
        if not is_downloaded(self.model_id):
            raise MusicGenLocalError(
                "download",
                tr(f"模型权重未下载：{self.hf_id}（请先在模型中心下载）",
                   f"Model weights not downloaded: {self.hf_id} (download them in the "
                   f"model center first)"))


        _apply_hf_endpoint()
        with _GEN_LOCK:  # GPU 采样串行（generate 非线程安全 + 单卡显存互斥）
            return self._generate_locked(request, progress, should_cancel, dest_dir)

    def _generate_locked(self, request, progress, should_cancel, dest_dir: str
                         ) -> GenerationOutput:
        import torch

        # GPU 优先；进程内曾触发 CUDA 设备断言后禁用（断言会毒化上下文并拖死进程）
        device = "cpu" if _CUDA_POISONED["flag"] else (
            "cuda" if torch.cuda.is_available() else "cpu")
        duration = min(request.duration_sec, self.max_duration)
        first_load = f"{self.hf_id}@{device}" not in _MODEL_CACHE
        _stage(progress, should_cancel, "model_load", 4,
               tr(f"加载本地模型 {self.hf_id}（{device.upper()}，"
                  + ("首次加载较慢" if first_load else "常驻已就绪") + "）",
                  f"Loading local model {self.hf_id} ({device.upper()}; "
                  + ("first load is slow" if first_load else "resident ready") + ")"))
        model, processor, sr = _load_or_get(self.hf_id, device)

        desc = (f"{request.style_prompt or 'instrumental music'}. "
                f"{request.bpm} BPM, {request.mode} key, instrumental.")
        inputs = processor(text=[desc, desc], padding=True, return_tensors="pt").to(device)

        if device == "cuda":
            # 实测 RTX 4060 Ti：300M 自回归逐 token 生成，30s×2 约 2~3 分钟（kernel 开销为主）
            est = tr(f"GPU 约 {max(30, duration * 3)}~{duration * 6}s",
                     f"GPU ~{max(30, duration * 3)}-{duration * 6}s")
        else:
            est_min = max(1, round(duration / 10))
            est = tr(f"CPU 约 {est_min}~{est_min * 3} 分钟",
                     f"CPU ~{est_min}-{est_min * 3} min")
        _stage(progress, should_cancel, "model_sample", 25,
               tr(f"模型采样中（{duration}s 器乐 ×2 候选，{est}）",
                  f"Sampling ({duration}s instrumental x2 candidates, {est})"))

        # guidance_scale=1.0：关闭 classifier-free guidance 分支——该分支在 CUDA 上存在
        # flaky 设备端索引断言（srcIndex < srcSelectDimSize，真机中文风格+人声请求实测
        # 两次命中并拖死进程），关掉后损失少量文本贴合度换取稳定；采样路径不受影响。
        from transformers import StoppingCriteria, StoppingCriteriaList

        class _CancelStopping(StoppingCriteria):
            """逐解码步检查取消标志：采样阶段（占绝大部分耗时）也能秒级响应取消，
            而不必等到下一阶段边界。提前停止的部分音频不会落盘（下一 _stage 即抛取消）。"""

            def __call__(self, input_ids, scores, **kwargs) -> bool:  # noqa: ARG002
                return bool(should_cancel())

        def _sample(dev_inputs, dev_model, dev: str):
            torch.manual_seed(request.seed)
            if dev == "cuda":
                torch.cuda.manual_seed_all(request.seed)
            with torch.no_grad():
                return dev_model.generate(
                    **dev_inputs, do_sample=True, guidance_scale=1.0,
                    max_new_tokens=int(duration * 50),
                    stopping_criteria=StoppingCriteriaList([_CancelStopping()])).cpu()

        try:
            audio = _sample(inputs, model, device)
        except RuntimeError as e:
            if device != "cuda":
                raise
            # CUDA 设备断言：上下文已毒化——本进程后续禁用 CUDA，换 CPU 重载重试
            _CUDA_POISONED["flag"] = True
            logger.warning(f"musicgen CUDA 采样失败（设备断言类），本进程降级 CPU 重试: {e}")
            _evict_model_cache(self.hf_id)  # 弃用已加载实例（含毒化的 GPU 实例）
            try:
                torch.cuda.empty_cache()
            except RuntimeError:  # noqa: BLE001 —— 清理失败不影响 CPU 重试
                pass
            _stage(progress, should_cancel, "model_sample", 30,
                   tr("GPU 采样异常，已切换 CPU 重试（本进程内不再使用 GPU）",
                      "GPU sampling error; retrying on CPU (GPU disabled for this "
                      "process)"))
            device = "cpu"
            model, processor, sr = _load_or_get(self.hf_id, device)
            inputs = processor(text=[desc, desc], padding=True, return_tensors="pt")
            audio = _sample(inputs, model, device)
        _stage(progress, should_cancel, "model_export", 88, tr("导出音频…", "Exporting audio…"))

        dest = Path(dest_dir)
        candidates: list[CandidateArtifact] = []
        for idx in range(audio.shape[0]):
            label = chr(ord("A") + idx)
            wav = audio[idx, 0].detach().float().numpy()
            if wav.ndim != 1:
                wav = wav.reshape(-1)
            cand_dir = dest / "candidates" / label
            cand_dir.mkdir(parents=True, exist_ok=True)
            master = cand_dir / "master.wav"
            write_wav(master, [wav], bits=24, sample_rate=sr)
            preview = cand_dir / "preview.mp3"
            encode_mp3(preview, wav, wav, bitrate=192, sample_rate=sr)
            total_sec = round(len(wav) / sr, 2)
            files = [
                dict(relpath=preview.relative_to(dest).as_posix(), kind="preview",
                     stem_name=None, mime="audio/mpeg", bytes=preview.stat().st_size,
                     duration_sec=total_sec, sample_rate=sr, sha256=_sha256(preview)),
                dict(relpath=master.relative_to(dest).as_posix(), kind="master",
                     stem_name=None, mime="audio/wav", bytes=master.stat().st_size,
                     duration_sec=total_sec, sample_rate=sr, sha256=_sha256(master)),
            ]
            candidates.append(CandidateArtifact(
                label=label, seed=candidate_seed(request.seed, label),
                quality_score=None, duration_sec=total_sec,
                structure=[], style_tags=_style_tags(request.style_prompt),
                bpm=request.bpm, tonic=request.tonic, mode=request.mode,
                time_signature=request.time_signature,
                vocal="instrumental", language=request.language, files=files,
            ))
        self.vocals_downgraded = request.vocal != "instrumental"
        if self.vocals_downgraded:
            logger.info("musicgen_local: 请求含人声但模型仅器乐，已降级为器乐生成并留痕")
        return GenerationOutput(candidates, [], False)
