"""应用内每日备份调度单测（v0.14.0 收尾补充）。

docker exec 在 GPU 容器上受 seccomp 限制不可用——备份改由应用内守护线程
执行（services/ops_backup.py）。覆盖：到期判定（时间窗 + 当日标记幂等）、
标记写入。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from app.config import settings
from app.services import ops_backup


def _freeze(when: datetime):
    """冻结 ops_backup.datetime.now（built-in 类不可 patch，替换模块级引用）"""
    fake = mock.MagicMock(wraps=datetime)
    fake.now.return_value = when
    return mock.patch("app.services.ops_backup.datetime", fake)

class TestBackupSchedule(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._patch = mock.patch.object(settings, "data_dir", self._tmp.name)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_not_due_before_window(self):
        early = datetime(2026, 9, 26, 2, 0)
        with _freeze(early):
            self.assertFalse(ops_backup._due_now())

    def test_due_first_time_of_day(self):
        at = datetime(2026, 9, 26, 3, 45)
        with _freeze(at):
            self.assertTrue(ops_backup._due_now())
            ops_backup._mark_done()
            self.assertFalse(ops_backup._due_now(), "当日标记后不再重跑")

    def test_marker_survives_restart_same_day(self):
        at = datetime(2026, 9, 26, 23, 0)
        with _freeze(at):
            ops_backup._mark_done()
            self.assertFalse(ops_backup._due_now())
        # 次日同一时刻重新到期
        nxt = at + timedelta(days=1)
        with _freeze(nxt):
            self.assertTrue(ops_backup._due_now())

    def test_scripts_path_points_at_backend_dir(self):
        """desktop 形态（数据目录在 ~/Meloyu）下 sys.path 必须注入代码根
        BACKEND_DIR 而非数据目录父目录——否则 scripts.backup 永不可导入，
        每日备份静默失效（2026-10-27 评审 F-BE-02）。"""
        from app.config import BACKEND_DIR
        with mock.patch.object(settings, "data_dir", self._tmp.name):
            ops_backup._scripts_on_path()
        self.assertIn(str(BACKEND_DIR), sys.path)
        import scripts.backup  # noqa: F401 —— 注入后必须可导入（旧实现走数据目录父目录必 ImportError）

if __name__ == "__main__":
    unittest.main()
