"""Ollama 本地模型运行时客户端（REST：/api/version /tags /pull /delete /chat）。

同步阻塞式（与项目线程池模型一致）；pull 走 ndjson 流并回调进度。
"""
from __future__ import annotations

from collections.abc import Callable

import httpx

from app.core.i18n import tr
from app.providers.llm.base import LLMError, strip_think

# pull 阶段单层 blob 下载可能数分钟无完整响应，只限制连接建立
_PULL_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=30.0, pool=30.0)
_PROBE_TIMEOUT = httpx.Timeout(3.0)


def _norm_host(host: str) -> str:
    host = (host or "").strip().rstrip("/")
    if not host:
        host = "http://localhost:11434"
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    # 容错 OpenAI 兼容习惯：外部 API 通道的 base_url 带 /v1（如
    # http://host.docker.internal:11434/v1），Ollama 原生端点是 /api/*，剥掉尾缀
    if host.endswith("/v1"):
        host = host[: -len("/v1")].rstrip("/")
    return host


class OllamaClient:
    """轻封装：不做重试，错误统一转 LLMError(kind)。"""

    def __init__(self, host: str = "http://localhost:11434"):
        self.base = _norm_host(host)

    # ---- 运行时探测 ----
    def version(self) -> str:
        try:
            r = httpx.get(f"{self.base}/api/version", timeout=_PROBE_TIMEOUT)
            if r.status_code != 200:
                raise LLMError("unavailable",
                tr(f"Ollama 响应异常 HTTP {r.status_code}",
                   f"Ollama abnormal response HTTP {r.status_code}"))
            return str(r.json().get("version") or "")
        except LLMError:
            raise
        except httpx.HTTPError as e:
            raise LLMError("unavailable",
                    tr(f"Ollama 服务不可达（{self.base}）：{e.__class__.__name__}",
                       f"Ollama service unreachable ({self.base}): "
                       f"{e.__class__.__name__}")) from e

    def list_models(self) -> list[dict]:
        try:
            r = httpx.get(f"{self.base}/api/tags", timeout=_PROBE_TIMEOUT)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError("unavailable",
                    tr(f"Ollama 服务不可达（{self.base}）：{e.__class__.__name__}",
                       f"Ollama service unreachable ({self.base}): "
                       f"{e.__class__.__name__}")) from e
        out = []
        for m in r.json().get("models", []):
            details = m.get("details") or {}
            out.append({
                "name": m.get("name") or m.get("model") or "",
                "size_bytes": m.get("size") or 0,
                "modified_at": m.get("modified_at") or "",
                "family": details.get("family") or "",
                "parameter_size": details.get("parameter_size") or "",
                "quantization": details.get("quantization_level") or "",
                "capabilities": m.get("capabilities") or [],
            })
        out.sort(key=lambda x: x["name"])
        return out

    # ---- 模型管理 ----
    def pull(self, model: str, on_progress: Callable[[str, int], None]) -> None:
        """拉取模型；on_progress(status 文案, pct 0-100)，成功返回前回调 100。"""
        try:
            with httpx.Client(timeout=_PULL_TIMEOUT) as client:
                with client.stream("POST", f"{self.base}/api/pull",
                                   json={"model": model, "stream": True}) as resp:
                    if resp.status_code == 404:
                        resp.read()
                        raise LLMError("protocol",
                            tr(f"模型不存在：{model}（仓库无此 tag）",
                               f"Model not found: {model} (no such tag in the repo)"))
                    if resp.status_code != 200:
                        resp.read()
                        raise LLMError("protocol",
                            tr(f"pull 失败 HTTP {resp.status_code}",
                               f"pull failed with HTTP {resp.status_code}"))
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            import json
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        if ev.get("error"):
                            raise LLMError("protocol",
                                tr(f"pull 失败：{ev['error']}",
                                   f"pull failed: {ev['error']}"))
                        status = str(ev.get("status") or "")
                        total, completed = ev.get("total"), ev.get("completed")
                        if total and completed is not None and total > 0:
                            pct = min(99, int(completed * 100 / total))
                            on_progress(tr(f"下载中 {pct}%", f"Downloading {pct}%"), pct)
                        elif status:
                            on_progress(status, 0)
        except LLMError:
            raise
        except httpx.HTTPError as e:
            raise LLMError("unavailable",
                    tr(f"pull 连接中断：{e.__class__.__name__}",
                       f"pull connection interrupted: {e.__class__.__name__}")) from e
        on_progress(tr("完成", "Done"), 100)

    def delete(self, model: str) -> None:
        try:
            r = httpx.request("DELETE", f"{self.base}/api/delete",
                              json={"model": model}, timeout=_PROBE_TIMEOUT)
            if r.status_code == 404:
                raise LLMError("protocol", tr(f"模型不存在：{model}", f"Model not found: {model}"))
            if r.status_code != 200:
                raise LLMError("protocol",
                            tr(f"删除失败 HTTP {r.status_code}",
                               f"delete failed with HTTP {r.status_code}"))
        except LLMError:
            raise
        except httpx.HTTPError as e:
            raise LLMError("unavailable",
                            tr(f"Ollama 服务不可达：{e.__class__.__name__}",
                               f"Ollama service unreachable: {e.__class__.__name__}")) from e

    # ---- 推理 ----
    def chat(self, model: str, system: str, prompt: str, timeout: float = 300.0,
             temperature: float = 0.8, max_tokens: int = 3000) -> str:
        """非流式对话。max_tokens 默认给足：常开思考的模型卡（旧 qwen3 等，
        think:false 不被模板尊重）思考链会消耗大量预算，截断则正文永远为空。"""
        payload: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "stream": False,
            "think": False,  # 对带 thinking 能力的模型卡生效（qwen3.5 等）
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            r = httpx.post(f"{self.base}/api/chat", json=payload,
                           timeout=httpx.Timeout(timeout))
            if r.status_code == 400 and "think" in r.text:
                # 旧版本 / 不支持 thinking 参数的模型：去掉 think 重试一次
                payload.pop("think")
                r = httpx.post(f"{self.base}/api/chat", json=payload,
                               timeout=httpx.Timeout(timeout))
            if r.status_code == 404:
                raise LLMError("protocol", tr(f"模型未安装：{model}", f"Model not installed: {model}"))
            if r.status_code != 200:
                raise LLMError(
                    "protocol",
                    tr(f"Ollama chat HTTP {r.status_code}：{r.text[:200]}",
                       f"Ollama chat HTTP {r.status_code}: {r.text[:200]}"))
            body = r.json()
            message = body.get("message") or {}
            content = message.get("content") or ""
            if not content.strip():
                thinking = message.get("thinking") or ""
                if thinking and body.get("done_reason") == "length":
                    raise LLMError(
                        "bad_output",
                        tr(f"模型 {model} 思考链过长被截断（可调大 max_tokens 或改用"
                           f"支持关闭思考的模型，如 qwen3.5 系列）",
                           f"Model {model}: thinking chain truncated (raise max_tokens "
                           f"or switch to a model with toggleable thinking, e.g. the "
                           f"qwen3.5 series)"))
                if thinking:
                    raise LLMError(
                        "bad_output",
                        tr(f"模型 {model} 只输出了思考链没有正文，建议改用 qwen3.5 "
                           f"等可控思考的模型",
                           f"Model {model} returned only a thinking chain with no "
                           f"content; prefer a controllable-thinking model such as "
                           f"qwen3.5"))
        except LLMError:
            raise
        except httpx.TimeoutException as e:
            raise LLMError("timeout",
                    tr(f"模型推理超时（{timeout:.0f}s），可换更小模型重试",
                       f"Model inference timed out ({timeout:.0f}s); try a smaller "
                       f"model")) from e
        except httpx.HTTPError as e:
            raise LLMError(
                "unavailable",
                tr(f"Ollama 服务不可达：{e.__class__.__name__}",
                   f"Ollama service unreachable: {e.__class__.__name__}")) from e
        except ValueError as e:
            raise LLMError("protocol", tr(f"响应非 JSON：{e}", f"Response is not JSON: {e}")) from e
        text = strip_think(content).strip()
        if not text:
            raise LLMError("bad_output", tr("模型返回空内容", "Model returned empty content"))
        return text
