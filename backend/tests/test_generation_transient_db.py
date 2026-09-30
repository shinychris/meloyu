"""v0.11.1 生成轮询瞬时库错误防抖单测（Docker bind 挂载 WAL 坑位回归）。

坑位：容器内采样到 70% 时，取消检查新开 SQLite 连接报
OperationalError: unable to open database file（9p 挂载下 WAL 共享内存偶发
瞬时失败），5 分钟推理被连带判失败。修复后契约：进度/取消轮询 fail-open——
瞬时库错误跳过该次（告警不打断），超时熔断逻辑不受影响。

运行：.venv/Scripts/python.exe -m unittest tests.test_generation_transient_db -v
"""
from __future__ import annotations

import time
import unittest
from unittest import mock

from sqlalchemy.exc import OperationalError

from app.services import generation as gen

def _op_err() -> OperationalError:
    return OperationalError("PRAGMA journal_mode=WAL", {},
                            Exception("unable to open database file"))

class _RaisingSessionCtx:
    """替身 SessionLocal：进 with 即抛瞬时库错误。"""

    def __enter__(self):
        raise _op_err()

    def __exit__(self, *exc):
        return False

class _FakeTask:
    def __init__(self, cancel_requested: bool) -> None:
        self.cancel_requested = cancel_requested

class _FakeSessionCtx:
    def __init__(self, task) -> None:
        self._task = task

    def __enter__(self):
        return mock.Mock(get=lambda _m, _id: self._task)

    def __exit__(self, *exc):
        return False

class TestCancelRequestedFailOpen(unittest.TestCase):
    def test_transient_db_error_returns_false(self):
        # 回归主场景：库打不开 ≠ 取消，不得把进行中的推理连带废掉
        with mock.patch.object(gen, "SessionLocal", _RaisingSessionCtx):
            self.assertFalse(gen._cancel_requested("t1"))

    def test_normal_path_reads_flag(self):
        with mock.patch.object(gen, "SessionLocal", lambda: _FakeSessionCtx(_FakeTask(True))):
            self.assertTrue(gen._cancel_requested("t1"))
        with mock.patch.object(gen, "SessionLocal", lambda: _FakeSessionCtx(_FakeTask(False))):
            self.assertFalse(gen._cancel_requested("t1"))
        with mock.patch.object(gen, "SessionLocal", lambda: _FakeSessionCtx(None)):
            self.assertFalse(gen._cancel_requested("t1"))

class TestProgressReporterFailOpen(unittest.TestCase):
    def test_transient_db_error_swallowed(self):
        progress = gen._progress_reporter("t1", time.monotonic(), 60)
        with mock.patch.object(gen, "_write_progress", side_effect=_op_err()):
            progress("model_sample", 70, "Generating music...")  # 不得抛出

    def test_timeout_still_fires(self):
        progress = gen._progress_reporter("t1", time.monotonic() - 10, 1)
        with self.assertRaises(TimeoutError):
            progress("model_sample", 70, "Generating music...")

    def test_other_errors_not_swallowed(self):
        # 只放行瞬时库错误：其他异常照常抛出（真缺陷不能被静默）
        progress = gen._progress_reporter("t1", time.monotonic(), 60)
        with mock.patch.object(gen, "_write_progress",
                               side_effect=ValueError("real bug")):
            with self.assertRaises(ValueError):
                progress("model_sample", 70, "Generating music...")

if __name__ == "__main__":
    unittest.main()
