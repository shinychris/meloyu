"""OpenAI 兼容外部 API 客户端（chat/completions）。

一套协议覆盖主流厂商：OpenAI / 智谱 GLM / DeepSeek / Moonshot / 通义 等，
差异仅在 base_url + api_key + model 名。api_key 允许为空（兼容本地网关）。
"""
from __future__ import annotations

import httpx

from app.core.i18n import tr
from app.providers.llm.base import LLMError, strip_think

_PROBE_TIMEOUT = httpx.Timeout(20.0)


def _norm_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise LLMError("unavailable", tr("base_url 未配置", "base_url is not configured"))
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str = "", model: str = ""):
        self.base = _norm_base(base_url)
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()

    def _headers(self, api_key: str | None = None) -> dict:
        key = self.api_key if api_key is None else (api_key or "").strip()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def chat(self, system: str, prompt: str, timeout: float = 300.0,
             temperature: float = 0.8, max_tokens: int = 3000, model: str | None = None,
             base_url: str | None = None, api_key: str | None = None) -> str:
        """按 OpenAI 协议发起一次补全；model/base_url/api_key 可临时覆盖（测试连接用）。

        推理型模型（deepseek-r1 / o 系列等）思考进 reasoning_content、正文 content
        为空且 max_tokens 被思考耗尽 → 自动放大 max_tokens 重试一次。"""
        url = f"{_norm_base(base_url) if base_url else self.base}/chat/completions"
        m = (model or self.model).strip()
        if not m:
            raise LLMError("unavailable", tr("model 未配置", "model is not configured"))

        def once(token_budget: int) -> tuple[str, str]:
            payload = {
                "model": m,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": token_budget,
            }
            try:
                r = httpx.post(url, json=payload, headers=self._headers(api_key),
                               timeout=httpx.Timeout(timeout))
            except httpx.TimeoutException as e:
                raise LLMError(
                    "timeout",
                    tr(f"外部 API 超时（{timeout:.0f}s）",
                       f"External API timed out ({timeout:.0f}s)")) from e
            except httpx.HTTPError as e:
                raise LLMError("unavailable",
                               tr(f"外部 API 不可达（{url}）：{e.__class__.__name__}",
                                  f"External API unreachable ({url}): "
                                  f"{e.__class__.__name__}")) from e
            if r.status_code in (401, 403):
                raise LLMError(
                    "unavailable",
                    tr("鉴权失败：api_key 无效或无权限",
                       "Authentication failed: api_key invalid or unauthorized"))
            if r.status_code == 404:
                raise LLMError(
                    "protocol",
                    tr(f"端点或模型不存在（{url}，model={m}）",
                       f"Endpoint or model not found ({url}, model={m})"))
            if r.status_code == 429:
                raise LLMError(
                    "unavailable", tr("触发限流（429），请稍后重试",
                                      "Rate limited (429); please retry later"))
            if r.status_code != 200:
                raise LLMError(
                    "protocol",
                    tr(f"外部 API HTTP {r.status_code}：{r.text[:200]}",
                       f"External API HTTP {r.status_code}: {r.text[:200]}"))
            try:
                message = r.json()["choices"][0]["message"]
                # 思考链字段：OpenAI/deepseek 为 reasoning_content，Ollama /v1 为 reasoning
                reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
                return message.get("content") or "", reasoning
            except (ValueError, KeyError, IndexError, TypeError) as e:
                raise LLMError(
                    "protocol",
                    tr(f"响应结构不符合 OpenAI 协议：{e}",
                       f"Response structure does not follow the OpenAI protocol: {e}")) from e

        content, reasoning = once(max_tokens)
        if not content.strip() and reasoning.strip() and max_tokens < 8000:
            content, reasoning = once(min(max_tokens * 2, 8000))  # 思考耗尽预算，放大重试
        text = strip_think(content).strip()
        if not text:
            if reasoning.strip():
                raise LLMError("bad_output",
                               tr(f"模型 {m} 思考链过长超出输出预算/上下文（若端点为 Ollama"
                                  f" /v1，建议改用原生 Ollama 通道或非思考型模型）",
                                  f"Model {m}: thinking chain exceeded the output "
                                  f"budget/context (if the endpoint is Ollama /v1, use "
                                  f"the native Ollama channel or a non-thinking model)"))
            raise LLMError("bad_output", tr("外部 API 返回空内容",
                                            "External API returned empty content"))
        return text

    def test(self, base_url: str | None = None, api_key: str | None = None,
             model: str | None = None) -> str:
        """连通性测试：发一条小对话，返回模型回声样本。

        bad_output（推理型模型正文为空）不算连通失败——端点/鉴权/模型已验证。"""
        try:
            return self.chat(
                system="You are a connectivity probe. Reply with exactly: OK",
                prompt="ping", timeout=60.0, temperature=0.0, max_tokens=512,
                model=model, base_url=base_url, api_key=api_key)
        except LLMError as e:
            if e.kind == "bad_output":
                return tr(f"（已连通）{e.message}", f"(Connected) {e.message}")
            raise
