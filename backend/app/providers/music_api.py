"""外部歌曲生成 Provider：Suno 兼容协议（V1.3 真实模型通道，ADR-010）。

协议为社区通行事实标准（GoAPI / suno-api / 各类中转站兼容）：
  POST {base}/api/v1/generate    提交生成（custom 模式：prompt=歌词，tags=风格）
  GET  {base}/api/v1/get?ids=…   按 clip id 轮询状态，complete 后给 audio_url

base_url 允许填网关根（自动补 /api/v1）或完整 …/api/v1 前缀（不再重复追加）。

与本地引擎的能力差异（导出/编辑侧均有校验拦截，前端如实展示）：
  - 产物为整曲 mp3（preview 与 master 同源），无分轨、无 MIDI → 派生编辑与
    stems/MIDI/WAV 导出对外部候选不可用，MP3 导出直接复制母带；
  - 外部黑盒无确定性 seed 语义（seed 仅用于本系统派生/封面色）；
  - quality_score 置空——外部模型不返回质量分，不造假分（ADR-012）；
  - 整曲生成 1~5 分钟，任务超时阈值放大到 MUSIC_API_TASK_TIMEOUT_SEC。
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import MUSIC_API_TASK_TIMEOUT_SEC
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
from app.synth.ir import SongRequest
from app.synth.structure import parse_lyrics

_POLL_INTERVAL_SEC = 5.0
_SUBMIT_TIMEOUT = httpx.Timeout(60.0)
_POLL_TIMEOUT = httpx.Timeout(30.0)
_DOWNLOAD_TIMEOUT = httpx.Timeout(300.0)

# clip 状态 → 轮询期进度（提交 5% → 下载 80%）
_STATUS_PCT: dict[str, int] = {"submitted": 12, "queued": 18, "running": 25,
                               "streaming": 55, "complete": 80}


class MusicAPIError(Exception):
    """外部歌曲 API 通道错误。kind ∈ unavailable|auth|protocol|timeout|bad_output。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _norm_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise MusicAPIError("unavailable", tr("base_url 未配置", "base_url is not configured"))
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    if not base.endswith("/api/v1"):
        base = f"{base}/api/v1"
    return base


def _host_of(base_url: str) -> str:
    try:
        return urlparse((base_url or "").strip()).netloc or base_url
    except ValueError:
        return base_url


class SunoCompatClient:
    """Suno 兼容网关客户端（提交 / 轮询 / 探活）。"""

    def __init__(self, base_url: str, api_key: str = "", model: str = ""):
        self.base = _norm_base(base_url)
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _clips_of(data) -> list[dict]:
        """兼容三类返回：list[clip] / {"clips":[…]} / {"data":[…]}。"""
        if isinstance(data, list):
            return [c for c in data if isinstance(c, dict)]
        if isinstance(data, dict):
            for key in ("clips", "data"):
                v = data.get(key)
                if isinstance(v, list):
                    return [c for c in v if isinstance(c, dict)]
        return []

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None, timeout: httpx.Timeout) -> httpx.Response:
        url = f"{self.base}{path}"
        try:
            return httpx.request(method, url, params=params, json=json_body,
                                 headers=self._headers(), timeout=timeout)
        except httpx.TimeoutException as e:
            raise MusicAPIError(
                "timeout", tr(f"外部歌曲 API 超时（{url}）",
                              f"External song API timed out ({url})")) from e
        except httpx.HTTPError as e:
            raise MusicAPIError("unavailable",
                                tr(f"外部歌曲 API 不可达（{url}）：{e.__class__.__name__}",
                                   f"External song API unreachable ({url}): "
                                   f"{e.__class__.__name__}")) from e

    @staticmethod
    def _raise_status(r: httpx.Response, url: str) -> None:
        if r.status_code in (401, 403):
            raise MusicAPIError(
                "auth", tr("鉴权失败：api_key 无效或无权限",
                           "Authentication failed: api_key invalid or unauthorized"))
        if r.status_code == 404:
            raise MusicAPIError(
                "protocol",
                tr(f"端点不存在（{url}）：请确认 base_url 与协议",
                   f"Endpoint not found ({url}): check base_url and the protocol"))
        if r.status_code == 429:
            raise MusicAPIError(
                "unavailable", tr("触发限流（429），请稍后重试",
                                  "Rate limited (429); please retry later"))
        if r.status_code != 200:
            raise MusicAPIError(
                "protocol",
                tr(f"外部歌曲 API HTTP {r.status_code}：{r.text[:200]}",
                   f"External song API HTTP {r.status_code}: {r.text[:200]}"))

    def submit(self, prompt: str, tags: str, instrumental: bool) -> list[str]:
        """提交生成，返回 clip id 列表（通常 2 个，对应 A/B 候选）。"""
        payload: dict = {"prompt": prompt, "tags": tags,
                         "make_instrumental": bool(instrumental), "wait_audio": False}
        if self.model:
            payload["model"] = self.model
        url = f"{self.base}/generate"
        r = self._request("POST", "/generate", json_body=payload, timeout=_SUBMIT_TIMEOUT)
        self._raise_status(r, url)
        try:
            data = r.json()
        except ValueError as e:
            raise MusicAPIError(
                "protocol", tr(f"响应不是 JSON：{r.text[:200]}",
                               f"Response is not JSON: {r.text[:200]}")) from e
        ids = [str(c["id"]) for c in self._clips_of(data) if c.get("id")]
        if not ids:
            raise MusicAPIError(
                "protocol", tr(f"响应中无 clip id：{str(data)[:200]}",
                               f"No clip id in response: {str(data)[:200]}"))
        return ids

    def fetch(self, ids: list[str]) -> list[dict]:
        """按 id 拉取 clip 状态（GET；个别网关只收 POST，405 时自动改发）。"""
        params = {"ids": ",".join(ids)}
        url = f"{self.base}/get"
        r = self._request("GET", "/get", params=params, timeout=_POLL_TIMEOUT)
        if r.status_code == 405:
            r = self._request("POST", "/get", params=params, timeout=_POLL_TIMEOUT)
        self._raise_status(r, url)
        try:
            return self._clips_of(r.json())
        except ValueError as e:
            raise MusicAPIError(
                "protocol", tr(f"响应不是 JSON：{r.text[:200]}",
                               f"Response is not JSON: {r.text[:200]}")) from e

    def test(self) -> str:
        """探活：get 一个不存在的 clip id —— 端点与鉴权通过即返回 200（空结果）。"""
        url = f"{self.base}/get"
        r = self._request("GET", "/get", params={"ids": "__meloyu_probe__"},
                          timeout=_POLL_TIMEOUT)
        self._raise_status(r, url)
        return tr(f"端点可达（{self.base}），鉴权通过",
                  f"Endpoint reachable ({self.base}), authentication passed")


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


class APIMusicProvider:
    """MusicProvider 协议实现：提交→轮询→下载整曲 mp3，映射到既有任务状态机。"""

    name = "api"
    base_display = "外部歌曲生成 API（Suno 兼容）"
    supports_vocals = True
    timeout_sec = MUSIC_API_TASK_TIMEOUT_SEC

    def __init__(self, base_url: str, api_key: str = "", model: str = ""):
        self.client = SunoCompatClient(base_url, api_key, model)
        model_part = model or _host_of(base_url)
        self.display_name = tr("外部歌曲API · ", "External song API · ") + model_part

    def generate(
        self,
        request: SongRequest,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        dest = Path(dest_dir)
        _stage(progress, should_cancel, "api_submit", 5,
               tr("提交外部模型生成", "Submitting to external model"))
        lyrics = (request.lyrics or "").strip()
        instrumental = request.vocal == "instrumental"
        # custom 模式：有人声走歌词（段落标签 [Verse]/[Chorus] 为协议原生支持），
        # 器乐/无歌词时把风格描述作为 prompt
        prompt = lyrics if lyrics else request.style_prompt
        tags = request.style_prompt if lyrics else ""
        ids = self.client.submit(prompt=prompt, tags=tags, instrumental=instrumental)
        logger.info(f"music api submitted: clips={ids} base={self.client.base}")
        _stage(progress, should_cancel, "api_queue", 12,
               tr(f"外部模型已受理（{len(ids)} 个候选），排队中",
                  f"Accepted by external model ({len(ids)} candidates), queued"))

        clips = self._poll(ids, progress, should_cancel)

        candidates: list[CandidateArtifact] = []
        for idx, clip in enumerate(clips[:2]):
            label = chr(ord("A") + idx)
            _stage(progress, should_cancel, "api_download", 82 + idx * 5,
                   tr(f"下载候选 {label} 音频", f"Downloading candidate {label} audio"))
            candidates.append(self._download_candidate(clip, request, label, dest))
        return GenerationOutput(candidates, [], False)

    def _poll(self, ids: list[str], progress: ProgressCallback,
              should_cancel: CancelCheck) -> list[dict]:
        while True:
            if should_cancel():
                raise SynthCancelled()
            clips = self.client.fetch(ids)
            statuses = [str(c.get("status") or "").lower() for c in clips]
            if clips and all(s == "complete" for s in statuses):
                return clips
            for c, s in zip(clips, statuses, strict=False):
                if s in ("error", "failed"):
                    raise MusicAPIError(
                        "bad_output",
                        tr(f"外部模型生成失败：{str(c.get('error') or c.get('error_message') or s)[:200]}",
                           f"External model generation failed: "
                           f"{str(c.get('error') or c.get('error_message') or s)[:200]}"))
            pct = min(75, max(_STATUS_PCT.get(s, 20) for s in statuses)) if statuses else 15
            progress("api_render", pct,
                     tr("外部模型生成中（整曲约 1~5 分钟）",
                        "Generating on external model (whole song, ~1-5 minutes)"))
            time.sleep(_POLL_INTERVAL_SEC)

    def _download_candidate(self, clip: dict, request: SongRequest, label: str,
                            dest: Path) -> CandidateArtifact:
        url = str(clip.get("audio_url") or clip.get("audio_url_cdn") or "")
        if not url:
            raise MusicAPIError(
                "bad_output",
                tr(f"clip {clip.get('id')} 缺少 audio_url",
                   f"clip {clip.get('id')} has no audio_url"))
        cand_dir = dest / "candidates" / label
        cand_dir.mkdir(parents=True, exist_ok=True)
        path = cand_dir / "preview.mp3"
        try:
            with httpx.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as r:
                if r.status_code != 200:
                    raise MusicAPIError(
                        "protocol",
                        tr(f"音频下载失败 HTTP {r.status_code}",
                           f"Audio download failed with HTTP {r.status_code}"))
                with open(path, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
        except httpx.HTTPError as e:
            raise MusicAPIError(
                "unavailable",
                tr(f"音频下载失败：{e.__class__.__name__}",
                   f"Audio download failed: {e.__class__.__name__}")) from e

        meta = clip.get("metadata") if isinstance(clip.get("metadata"), dict) else {}
        duration = float(meta.get("duration") or clip.get("duration") or request.duration_sec)
        size = path.stat().st_size
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        relpath = path.relative_to(dest).as_posix()
        # preview 与 master 同源（整曲 mp3）：master 供导出/证书指纹使用
        files = [
            dict(relpath=relpath, kind="preview", stem_name=None, mime="audio/mpeg",
                 bytes=size, duration_sec=round(duration, 2), sample_rate=None,
                 sha256=digest.hexdigest()),
            dict(relpath=relpath, kind="master", stem_name=None, mime="audio/mpeg",
                 bytes=size, duration_sec=round(duration, 2), sample_rate=None,
                 sha256=digest.hexdigest()),
        ]
        return CandidateArtifact(
            label=label, seed=candidate_seed(request.seed, label), quality_score=None,
            duration_sec=round(duration, 2), structure=_structure_of(request.lyrics),
            style_tags=_style_tags(request.style_prompt), bpm=request.bpm,
            tonic=request.tonic, mode=request.mode, time_signature=request.time_signature,
            vocal=request.vocal, language=request.language, files=files,
        )
