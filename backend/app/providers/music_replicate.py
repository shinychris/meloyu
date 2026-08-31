"""Replicate 托管开源歌曲模型 Provider（V1.4「多类开源模型接入」，ADR-014）。

统一走 Replicate HTTP API（一个 API Token 接全部目录模型）：
  POST {base}/v1/models/{owner}/{name}/predictions   创建推理（官方/社区模型均可，
                                                     走 latest version，无需 version hash）
  GET  {base}/v1/predictions/{id}                    轮询：starting/processing/succeeded/
                                                     failed/canceled → output 为音频 URL
  GET  {base}/v1/account | /v1/models/{slug}         探活 / 模型校验

多模型输入适配：目录中每类模型的 input schema 不同（MusicGen 吃 prompt、ACE-Step/YuE
吃歌词+风格、DiffRhythm 吃歌词+风格+时长），_INPUT_BUILDERS 白名单构造，未收录字段
不盲传（多余字段会被 Replicate 422 拒绝）。schema 若与平台版本漂移，422 的
detail 会透出字段名，便于修正适配器或自建映射。

产物：一次生成并行提交 2 个 prediction → A/B 候选。输出 wav → master.wav 原样落盘 +
本地解码转 preview.mp3；输出 mp3 → preview/master 同源（与 music_api 一致）。
"""
from __future__ import annotations

import hashlib
import re
import time
import wave
from pathlib import Path

import httpx

from app.config import REPLICATE_API_BASE
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
from app.synth.structure import parse_lyrics
from app.synth.wav_io import read_wav

_POLL_INTERVAL_SEC = 5.0
_TIMEOUTS = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=60.0)

# 声线枚举 → 英文风格描述（拼入 tags/prompt，供模型控制人声色彩）
VOCAL_TAG_EN = {
    "female_air": "female airy vocal", "female_bright": "female bright vocal",
    "female_deep": "female deep vocal", "male_magnetic": "male magnetic vocal",
    "male_clear": "male clear vocal", "choir": "choir vocals",
}


class ReplicateError(Exception):
    """Replicate 通道错误。kind ∈ unavailable|auth|protocol|timeout|bad_output。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


# ---------- 输入适配（白名单字段，见模块 docstring） ----------

def _input_musicgen(req: SongRequest, model_id: str) -> dict:
    prompt = f"{req.style_prompt or 'instrumental music'}. {req.bpm} BPM, {req.mode} key."
    return {"prompt": prompt,
            "duration": min(req.duration_sec, 120),
            "model_version": model_id.removeprefix("musicgen-"),
            "output_format": "wav"}


def _input_lyrics_song(req: SongRequest, model_id: str) -> dict:
    instrumental = req.vocal == "instrumental"
    tags = req.style_prompt or ""
    if not instrumental:
        tags = f"{tags}, {VOCAL_TAG_EN.get(req.vocal, 'vocal')}".strip(", ")
    lyrics = (req.lyrics or "").strip() or req.style_prompt
    return {"prompt": lyrics, "tags": tags, "instrumental": instrumental,
            "duration": min(req.duration_sec, 240)}


def _input_yue(req: SongRequest, model_id: str) -> dict:
    instrumental = req.vocal == "instrumental"
    genre = req.style_prompt or "pop"
    if not instrumental:
        genre = f"{genre}, {VOCAL_TAG_EN.get(req.vocal, 'vocal')}"
    return {"lyrics": (req.lyrics or "").strip() or req.style_prompt,
            "genre": genre, "duration": min(req.duration_sec, 240),
            "instrumental": instrumental}


def _input_diffrhythm(req: SongRequest, model_id: str) -> dict:
    return {"lyrics": (req.lyrics or "").strip() or req.style_prompt,
            "style_prompt": req.style_prompt or "pop",
            "song_length": min(req.duration_sec, 240)}


def _input_stable_audio(req: SongRequest, model_id: str) -> dict:
    prompt = f"{req.style_prompt or 'ambient music'}. {req.bpm} BPM."
    return {"prompt": prompt, "duration": min(req.duration_sec, 47),
            "output_format": "wav"}


_INPUT_BUILDERS = {
    "musicgen-small": _input_musicgen,
    "musicgen-medium": _input_musicgen,
    "musicgen-large": _input_musicgen,
    "ace-step": _input_lyrics_song,
    "yue": _input_yue,
    "diffrhythm": _input_diffrhythm,
    "stable-audio-open": _input_stable_audio,
}


def build_replicate_input(req: SongRequest, model_id: str) -> dict:
    builder = _INPUT_BUILDERS.get(model_id)
    if builder is None:  # 目录新增模型未写适配器 → 保守通用形态
        return {"prompt": f"{req.style_prompt}. {req.bpm} BPM."}
    return builder(req, model_id)


# ---------- 客户端 ----------

class ReplicateClient:
    def __init__(self, api_token: str, base: str = REPLICATE_API_BASE):
        if not (api_token or "").strip():
            raise ReplicateError("auth", "Replicate API Token 未配置")
        self.token = api_token.strip()
        self.base = (base or REPLICATE_API_BASE).strip().rstrip("/")

    def _request(self, method: str, path: str, json_body: dict | None = None) -> httpx.Response:
        url = f"{self.base}{path}"
        headers = {"Authorization": f"Bearer {self.token}",
                   "Content-Type": "application/json"}
        try:
            return httpx.request(method, url, json=json_body, headers=headers,
                                 timeout=_TIMEOUTS)
        except httpx.TimeoutException as e:
            raise ReplicateError("timeout", f"Replicate API 超时（{url}）") from e
        except httpx.HTTPError as e:
            raise ReplicateError("unavailable",
                                 f"Replicate API 不可达（{url}）：{e.__class__.__name__}") from e

    @staticmethod
    def _raise_status(r: httpx.Response, url: str) -> None:
        if r.status_code in (401, 403):
            raise ReplicateError("auth", "鉴权失败：API Token 无效或无权限")
        if r.status_code == 404:
            raise ReplicateError("protocol",
                                 f"模型不存在（{url}）：请在模型中心核对/更新该模型的 slug")
        if r.status_code == 422:
            raise ReplicateError("protocol",
                                 f"模型 input 参数不合法（{r.text[:200]}）——平台版本与适配器"
                                 "漂移时请在目录中调整该模型 slug 或反馈适配器修正")
        if r.status_code != 200:
            raise ReplicateError("protocol", f"Replicate HTTP {r.status_code}：{r.text[:200]}")

    def account(self) -> dict:
        r = self._request("GET", "/v1/account")
        self._raise_status(r, f"{self.base}/v1/account")
        return r.json()

    def get_model(self, slug: str) -> dict:
        r = self._request("GET", f"/v1/models/{slug.strip().strip('/')}")
        self._raise_status(r, f"{self.base}/v1/models/{slug}")
        return r.json()

    def create(self, slug: str, input: dict) -> str:
        r = self._request("POST", f"/v1/models/{slug.strip().strip('/')}/predictions",
                          json_body={"input": input})
        self._raise_status(r, f"{self.base}/v1/models/{slug}/predictions")
        pred_id = (r.json() or {}).get("id")
        if not pred_id:
            raise ReplicateError("protocol", f"响应中无 prediction id：{r.text[:200]}")
        return str(pred_id)

    def fetch(self, prediction_id: str) -> dict:
        r = self._request("GET", f"/v1/predictions/{prediction_id}")
        self._raise_status(r, f"{self.base}/v1/predictions/{prediction_id}")
        return r.json()


def _audio_url(output) -> str:
    """兼容常见输出形态：单 URL 字符串 / URL 列表 / {url:…} 列表。"""
    if isinstance(output, str) and output.startswith("http"):
        return output
    if isinstance(output, list):
        for item in output:  # 优先带音频扩展名的条目
            if isinstance(item, str) and item.startswith("http"):
                if item.lower().split("?")[0].endswith(
                        (".wav", ".mp3", ".flac", ".ogg", ".m4a")):
                    return item
        for item in output:  # 无扩展名兜底
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict) and str(item.get("url") or "").startswith("http"):
                return str(item["url"])
    if isinstance(output, dict) and str(output.get("url") or "").startswith("http"):
        return str(output["url"])
    raise ReplicateError("bad_output", f"模型输出中无音频 URL：{str(output)[:200]}")


def _stage(progress: ProgressCallback, should_cancel: CancelCheck, key: str, pct: int,
           label: str) -> None:
    if should_cancel():
        raise SynthCancelled()
    progress(key, pct, label)


def _structure_of(lyrics: str) -> list[dict]:
    parsed, _ = parse_lyrics(lyrics or "")
    return [{"section": sec, "line_count": len(lines)} for sec, lines in parsed]


def _style_tags(style_prompt: str) -> list[str]:
    return [t for t in re.split(r"[，,。;；\s]+", style_prompt or "") if t][:4]


# ---------- Provider ----------

class ReplicateMusicProvider:
    """MusicProvider 协议实现：目录模型经 Replicate 托管推理。"""

    name = "replicate"
    base_display = "Replicate 开源模型托管"
    supports_vocals = True  # 以所选目录模型能力为准（capabilities.vocals）
    timeout_sec = 900

    def __init__(self, api_token: str, model_id: str, slug: str):
        entry = CATALOG_BY_ID.get(model_id)
        if entry is None:
            raise ReplicateError("bad_output", f"目录中不存在模型：{model_id}")
        slug = (slug or entry.get("replicate_slug") or "").strip()
        if not slug:
            raise ReplicateError("protocol",
                                 f"模型 {model_id} 未配置 Replicate slug（社区托管 slug "
                                 "请在模型中心填写）")
        self.client = ReplicateClient(api_token)
        self.model_id = model_id
        self.slug = slug
        self.display_name = f"Replicate · {entry['name']}"
        self.vocals_supported = bool(entry["capabilities"]["vocals"])

    def generate(
        self,
        request: SongRequest,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        dest = Path(dest_dir)
        input = build_replicate_input(request, self.model_id)
        _stage(progress, should_cancel, "api_submit", 5,
               f"提交 Replicate 生成（{self.slug}，2 个候选并行）")
        ids = [self.client.create(self.slug, input) for _ in range(2)]
        logger.info(f"replicate submitted: model={self.slug} predictions={ids}")

        outputs = self._poll(ids, progress, should_cancel)

        candidates = []
        for idx, url in enumerate(outputs[:2]):
            label = chr(ord("A") + idx)
            _stage(progress, should_cancel, "api_download", 82 + idx * 5,
                   f"下载候选 {label} 音频")
            candidates.append(self._materialize(url, request, label, dest))
        return GenerationOutput(candidates, [], False)

    def _poll(self, ids: list[str], progress: ProgressCallback,
              should_cancel: CancelCheck) -> list[str]:
        pending = list(ids)
        done: dict[str, str] = {}
        while pending:
            if should_cancel():
                raise SynthCancelled()
            for pid in list(pending):
                data = self.client.fetch(pid)
                status = str(data.get("status") or "").lower()
                if status == "succeeded":
                    done[pid] = _audio_url(data.get("output"))
                    pending.remove(pid)
                elif status in ("failed", "canceled"):
                    raise ReplicateError(
                        "bad_output",
                        f"模型推理失败：{str(data.get('error') or status)[:200]}")
            if pending:
                pct = 55 if done else 20
                progress("api_render", pct, "Replicate 推理中（云端开源模型）")
                time.sleep(_POLL_INTERVAL_SEC)
        return [done[pid] for pid in ids if pid in done]

    def _materialize(self, url: str, request: SongRequest, label: str,
                     dest: Path) -> CandidateArtifact:
        cand_dir = dest / "candidates" / label
        cand_dir.mkdir(parents=True, exist_ok=True)
        is_wav = ".wav" in url.lower().split("?")[0][-6:]
        raw = cand_dir / ("master.wav" if is_wav else "preview.mp3")
        try:
            with httpx.stream("GET", url, timeout=300.0, follow_redirects=True) as r:
                if r.status_code != 200:
                    raise ReplicateError("protocol", f"音频下载失败 HTTP {r.status_code}")
                with open(raw, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
        except httpx.HTTPError as e:
            raise ReplicateError("unavailable", f"音频下载失败：{e.__class__.__name__}") from e

        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        size = raw.stat().st_size
        if is_wav:
            with wave.open(str(raw), "rb") as wf:
                sr, ch = wf.getframerate(), wf.getnchannels()
            channels = read_wav(raw)
            left = channels[0]
            right = channels[1] if ch > 1 and len(channels) > 1 else channels[0]
            preview = cand_dir / "preview.mp3"
            encode_mp3(preview, left, right, bitrate=192, sample_rate=sr)
            duration = size / (sr * ch * 2)  # 16bit 近似：按采样率与声道数估长
            files = [
                dict(relpath=preview.relative_to(dest).as_posix(), kind="preview",
                     stem_name=None, mime="audio/mpeg",
                     bytes=preview.stat().st_size, duration_sec=round(duration, 2),
                     sample_rate=sr, sha256=hashlib.sha256(preview.read_bytes()).hexdigest()),
                dict(relpath=raw.relative_to(dest).as_posix(), kind="master",
                     stem_name=None, mime="audio/wav", bytes=size,
                     duration_sec=round(duration, 2), sample_rate=sr, sha256=digest),
            ]
        else:
            preview = raw
            duration = request.duration_sec
            files = [
                dict(relpath=preview.relative_to(dest).as_posix(), kind="preview",
                     stem_name=None, mime="audio/mpeg", bytes=size,
                     duration_sec=round(duration, 2), sample_rate=None, sha256=digest),
                dict(relpath=preview.relative_to(dest).as_posix(), kind="master",
                     stem_name=None, mime="audio/mpeg", bytes=size,
                     duration_sec=round(duration, 2), sample_rate=None, sha256=digest),
            ]
        vocal = request.vocal if self.vocals_supported else "instrumental"
        return CandidateArtifact(
            label=label, seed=candidate_seed(request.seed, label), quality_score=None,
            duration_sec=round(duration, 2),
            structure=_structure_of(request.lyrics if self.vocals_supported else ""),
            style_tags=_style_tags(request.style_prompt), bpm=request.bpm,
            tonic=request.tonic, mode=request.mode,
            time_signature=request.time_signature, vocal=vocal,
            language=request.language, files=files,
        )
