"""LLM 通道客户端包：Ollama（本地开源模型）+ OpenAI 兼容（外部 API）。"""
from app.providers.llm.base import LLMError, extract_json, strip_think
from app.providers.llm.ollama_client import OllamaClient
from app.providers.llm.openai_compat import OpenAICompatClient

__all__ = ["LLMError", "extract_json", "strip_think", "OllamaClient", "OpenAICompatClient"]
