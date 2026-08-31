"""Meloyu ↔ ACE-Step v1.5 子进程桥（在 ACE-Step 独立 venv 下运行）。

由 backend/app/providers/music_acestep.py 拉起——ACE-Step 钉死
torch==2.7.1+cu128 与后端 venv（torch 2.13+cu130，MusicGen 用）互斥，
故代码/依赖/checkpoints 全部隔离在 backend/data/acestep/（ADR-016）。

协议：stdout 每行一个 JSON 事件（stderr 原样透传，供排查）：
  {"event": "progress", "pct": 0~100, "message": "..."}
  {"event": "done", "candidates": [{"label", "relpath", "duration_sec",
                                    "sample_rate", "seed"}]}
  {"event": "error", "message": "..."}
退出码：0=成功；3=失败（已发 error 事件）；2=参数/环境错误。

用法：
  python acestep_runner.py download
  python acestep_runner.py generate --request req.json --outdir <dest>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
from pathlib import Path

# Windows 子进程 stdout 默认 GBK：强制 UTF-8，保证中文 message 不炸
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def progress(pct: float, message: str) -> None:
    emit({"event": "progress", "pct": max(0, min(99, int(pct))), "message": message[:200]})


def fail(message: str) -> None:
    emit({"event": "error", "message": str(message)[:400]})
    sys.exit(3)


# ---------- download 模式 ----------

_MAIN_REPO = "ACE-Step/Ace-Step1.5"
_LM_REPO = "ACE-Step/acestep-5Hz-lm-0.6B"


def _repo_total_bytes(repos: list[str]) -> int | None:
    """HF API 查询仓库总大小（失败返回 None，进度退化为字节数文案）。"""
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        total = 0
        for repo in repos:
            info = api.model_info(repo, files_metadata=True)
            total += sum((f.size or 0) for f in (info.siblings or []))
        return total or None
    except Exception:  # noqa: BLE001 —— 大小查询失败不阻断下载
        return None


def _dir_bytes(root: Path) -> int:
    n = 0
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                n += p.stat().st_size
        except OSError:  # noqa: BLE001 —— 下载中文件移动属正常
            pass
    return n


def _start_watcher(checkpoints: Path, total: int | None) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(2.0):
            got = _dir_bytes(checkpoints)
            if total:
                progress(1 + got * 98 / total, f"已下载 {got / 1e9:.1f} GB / 约 {total / 1e9:.1f} GB")
            else:
                progress(min(90, 5 + got / 6e8), f"已下载 {got / 1e9:.1f} GB")

    threading.Thread(target=loop, daemon=True).start()
    return stop


def run_download() -> None:
    from acestep.model_downloader import (
        check_main_model_exists,
        check_model_exists,
        download_main_model,
        download_submodel,
        get_checkpoints_dir,
    )

    checkpoints = get_checkpoints_dir()
    progress(1, "查询模型体积…")
    total = _repo_total_bytes([_MAIN_REPO, _LM_REPO])
    stop = _start_watcher(Path(checkpoints), total)
    try:
        if not check_main_model_exists(checkpoints):
            progress(2, "下载主模型（turbo DiT + VAE + 文本编码器 + 默认 LM）…")
            ok, msg = download_main_model(checkpoints)
            if not ok:
                fail(f"主模型下载失败：{msg}")
        if not check_model_exists("acestep-5Hz-lm-0.6B", checkpoints):
            progress(96, "下载 5Hz LM 0.6B（8GB 显存档）…")
            ok, msg = download_submodel("acestep-5Hz-lm-0.6B", checkpoints)
            if not ok:
                fail(f"LM 下载失败：{msg}")
    finally:
        stop.set()
    if not (check_main_model_exists(checkpoints)
            and check_model_exists("acestep-5Hz-lm-0.6B", checkpoints)):
        fail("下载结束但权重校验未通过，请重试")
    emit({"event": "done"})


# ---------- generate 模式 ----------

def run_generate(request_path: str, outdir: str) -> None:
    import torch

    req = json.loads(Path(request_path).read_text(encoding="utf-8"))
    dest = Path(outdir)

    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.model_downloader import get_checkpoints_dir

    device = "cuda" if torch.cuda.is_available() else "cpu"
    offload = bool(req.get("offload_to_cpu", device == "cuda"))
    # offload_dit_to_cpu=True：DiT 扩散完即腾显存——否则 DiT 常驻 ~4.5GB，
    # 解码时空闲显存 <0.5GB 触发 VAE 自动 CPU 解码（2×30s 实测 15 分钟+）
    offload_dit = bool(req.get("offload_dit_to_cpu", device == "cuda"))
    lm_model = req.get("lm_model_path", "acestep-5Hz-lm-0.6B")

    progress(4, f"加载 DiT 模型（{device.upper()}，offload={offload}/{offload_dit}）…")
    handler = AceStepHandler()
    project_root = str(Path(get_checkpoints_dir()).parent)
    status, ok = handler.initialize_service(
        project_root=project_root, config_path="acestep-v15-turbo",
        device=device, offload_to_cpu=offload, offload_dit_to_cpu=offload_dit,
    )
    if not ok:
        fail(f"DiT 初始化失败：{status}")

    progress(12, f"加载 5Hz LM（{lm_model}，pt 后端）…")
    llm = LLMHandler()
    status, ok = llm.initialize(
        checkpoint_dir=str(get_checkpoints_dir()), lm_model_path=lm_model,
        backend="pt", device=device, offload_to_cpu=offload,
    )
    if not ok:
        fail(f"LM 初始化失败：{status}")

    ts_map = {"4/4": "4", "3/4": "3", "6/8": "6", "2/4": "2"}
    params = GenerationParams(
        caption=(req.get("caption") or "")[:500],
        lyrics=(req.get("lyrics") or "")[:4000],
        instrumental=bool(req.get("instrumental")),
        vocal_language=req.get("vocal_language") or "unknown",
        duration=float(req.get("duration") or -1),
        bpm=req.get("bpm") or None,
        keyscale=(req.get("keyscale") or "").strip(),
        timesignature=ts_map.get(req.get("timesignature") or "", ""),
        seed=int(req.get("seed") or -1),
        thinking=bool(req.get("thinking", True)),
        use_cot_metas=False,   # bpm/调性/拍号由 Meloyu 请求显式给定，不让 LM 改写
        use_cot_language=False,
    )
    config = GenerationConfig(
        batch_size=int(req.get("batch_size") or 2),
        use_random_seed=False,
        seeds=[int(s) & 0xFFFFFFFF for s in (req.get("seeds") or [req.get("seed") or 0])],
        audio_format="wav",
    )

    def on_progress(value, desc=None, *args, **kwargs):  # noqa: ANN002, ANN003
        try:
            v = float(value)
            if v <= 1.0:
                v = 25 + v * 58  # 模型内进度映射到任务进度区间 25~83
            progress(v, str(desc) if desc else "模型采样中")
        except (TypeError, ValueError):  # noqa: BLE001 —— 进度解析失败静默
            pass

    progress(20, "LM 规划 + DiT 采样中…")
    result = generate_music(handler, llm, params, config,
                            save_dir=str(dest / "_raw"), progress=on_progress)
    if not result.success and req.get("thinking", True):
        # LM 思考链失败会整单失败：降级非思考模式重试一次（元数据直接用请求值）
        progress(50, "LM 规划失败，降级直出模式重试…")
        params.thinking = False
        result = generate_music(handler, llm, params, config,
                                save_dir=str(dest / "_raw"), progress=on_progress)
    if not result.success:
        fail(f"生成失败：{result.error or result.status_message}")

    progress(88, "导出音频…")
    import soundfile as sf
    candidates = []
    for idx, audio in enumerate(result.audios[:config.batch_size]):
        label = chr(ord("A") + idx)
        src = Path(audio["path"])
        cand_dir = dest / "candidates" / label
        cand_dir.mkdir(parents=True, exist_ok=True)
        master = cand_dir / "master.wav"
        # 管道默认写 32-bit FLOAT wav（格式标签 3，标准库 wave 不认）——
        # 统一重写为 PCM_24（Meloyu 母带规格），避免调用侧解码失败
        data, sr = sf.read(str(src), dtype="float64", always_2d=True)
        sf.write(str(master), data, sr, subtype="PCM_24")
        info = sf.info(str(master))
        candidates.append({
            "label": label,
            "relpath": f"candidates/{label}/master.wav",
            "duration_sec": round(info.frames / info.samplerate, 2),
            "sample_rate": info.samplerate,
            "seed": (audio.get("params") or {}).get("seed"),
        })
    if not candidates:
        fail(f"生成成功但无音频产出：{result.status_message}")
    shutil.rmtree(dest / "_raw", ignore_errors=True)
    emit({"event": "done", "candidates": candidates})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["download", "generate"])
    parser.add_argument("--request")
    parser.add_argument("--outdir")
    args = parser.parse_args()
    try:
        if args.mode == "download":
            run_download()
        else:
            if not (args.request and args.outdir):
                fail("--request 与 --outdir 必填")
            run_generate(args.request, args.outdir)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 —— 桥进程兜底：异常转 error 事件
        import traceback
        traceback.print_exc()
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
