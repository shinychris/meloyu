"""loguru JSON 日志配置（request 级 / task 级）。"""
from __future__ import annotations

import sys

from loguru import logger

_configured = False


def setup_logging(debug: bool = False) -> None:
    global _configured
    if _configured:
        return
    _configured = True
    logger.remove()
    logger.add(
        sys.stdout,
        serialize=True,
        level="DEBUG" if debug else "INFO",
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )
