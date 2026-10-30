"""外部 API 通道 Ollama 关思考单测（v0.12.2）。

覆盖（openai_compat 走 Ollama /v1 网关的场景）：
  1. looks_like_ollama 识别默认端口 11434 / 主机名含 ollama 的端点；
  2. 命中 Ollama 端点时 chat 附带 reasoning_effort:"none"（v0.11+ 关思考），
     非 Ollama 端点不附带（避免严格网关 400）；
  3. 旧版 Ollama 对 reasoning_effort:"none" 报 400 时自动去掉该字段重试一次。

运行：.venv/Scripts/python.exe -m unittest tests.test_openai_compat_reasoning -v
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from app.providers.llm.openai_compat import OpenAICompatClient, looks_like_ollama


def _ok_response(content: str = "hello") -> mock.MagicMock:
    r = mock.MagicMock()
    r.status_code = 200
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r

def _bad_response(text: str) -> mock.MagicMock:
    r = mock.MagicMock()
    r.status_code = 400
    r.text = text
    return r

class TestLooksLikeOllama(unittest.TestCase):
    def test_default_port_and_hostname(self):
        self.assertTrue(looks_like_ollama("http://localhost:11434/v1/chat/completions"))
        self.assertTrue(looks_like_ollama("http://ollama-svc:8000/v1/chat/completions"))
        self.assertFalse(looks_like_ollama("https://api.openai.com/v1/chat/completions"))
        self.assertFalse(looks_like_ollama("https://api.deepseek.com/chat/completions"))
        self.assertFalse(looks_like_ollama(""))

class TestChatReasoningEffort(unittest.TestCase):
    def test_ollama_endpoint_sends_none(self):
        client = OpenAICompatClient("http://localhost:11434/v1", model="qwen3:8b")
        with mock.patch("app.providers.llm.openai_compat.httpx.post",
                        return_value=_ok_response()) as post:
            client.chat(system="s", prompt="p")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload.get("reasoning_effort"), "none")

    def test_other_endpoint_omits_field(self):
        client = OpenAICompatClient("https://api.openai.com/v1", model="gpt-4o-mini")
        with mock.patch("app.providers.llm.openai_compat.httpx.post",
                        return_value=_ok_response()) as post:
            client.chat(system="s", prompt="p")
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("reasoning_effort", payload)

    def test_legacy_ollama_400_retries_without_field(self):
        client = OpenAICompatClient("http://localhost:11434/v1", model="llama3")
        bad = _bad_response(json.dumps({"error": {"message":
            "invalid value for reasoning_effort"}}))
        with mock.patch("app.providers.llm.openai_compat.httpx.post",
                        side_effect=[bad, _ok_response()]) as post:
            text = client.chat(system="s", prompt="p")
        self.assertEqual(text, "hello")
        self.assertEqual(post.call_count, 2)
        self.assertIn("reasoning_effort", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("reasoning_effort", post.call_args_list[1].kwargs["json"])

    def test_unrelated_400_not_retried(self):
        client = OpenAICompatClient("http://localhost:11434/v1", model="llama3")
        with mock.patch("app.providers.llm.openai_compat.httpx.post",
                        return_value=_bad_response("model not found")):
            from app.providers.llm.base import LLMError
            with self.assertRaises(LLMError):
                client.chat(system="s", prompt="p")

if __name__ == "__main__":
    unittest.main()
