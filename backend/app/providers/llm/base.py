"""LLM 通道公共基础设施：异常、think 剥离、JSON 提取。

本包不依赖业务层；上层（lyrics_llm / model_center）注入具体客户端。
"""
from __future__ import annotations

import json
import re


class LLMError(Exception):
    """LLM 通道异常（kind：unavailable=服务不可达 / timeout=推理超时 /
    protocol=响应不符合预期 / bad_output=产出不可用）。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think>.*", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def strip_think(text: str) -> str:
    """剥离推理型模型（qwen3/deepseek-r1 等）混入输出的思考块。"""
    if "<think>" not in text:
        return text
    text = _THINK_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)  # 未闭合的尾部思考块
    return text.strip()


def extract_json(text: str) -> dict | list | None:
    """从模型输出提取 JSON 对象：优先剥 markdown 围栏，再按首尾花括号截取。"""
    text = strip_think(text).strip()
    for candidate in _FENCE_RE.findall(text):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                continue
    return None
