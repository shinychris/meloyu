"""v0.11.1 ACE-Step venv 平台感知单测（Docker Exec format error 事故回归）。

事故：compose 把宿主机 backend/data bind 挂进 Linux 容器，容器内把挂载进来的
Windows venv（.venv/Scripts/python.exe，PE 二进制）当解释器执行 → OSError
[Errno 8] Exec format error；且旧 deps 检测只看该文件存在与否，挂载后误报就绪。

修复后契约：Windows 用 .venv/Scripts/python.exe，Linux 用 .venv-linux/bin/python，
两侧 venv 同目录共存互不干扰；deps 检测平台感知，异构 venv 不算数。

运行：.venv/Scripts/python.exe -m unittest tests.test_acestep_venv_platform -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.config import settings
from app.providers import music_acestep as mas

def _mk(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")

def _make_win_venv(root: Path) -> None:
    _mk(root / ".venv" / "Scripts" / "python.exe")
    (root / ".venv" / "Lib" / "site-packages" / "acestep").mkdir(parents=True,
                                                                 exist_ok=True)

def _make_linux_venv(root: Path) -> None:
    _mk(root / ".venv-linux" / "bin" / "python")
    (root / ".venv-linux" / "lib" / "python3.12" / "site-packages"
     / "acestep").mkdir(parents=True, exist_ok=True)

class _PlatformCase(unittest.TestCase):
    """把 acestep_home 指到临时目录并把 sys.platform 切到指定平台。"""

    def patched(self, tmp: Path, platform: str) -> None:
        p1 = mock.patch.object(settings, "acestep_home", str(tmp))
        p2 = mock.patch("sys.platform", platform)
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

class TestVenvPlatformPaths(_PlatformCase):
    def test_windows_layout(self):
        with tempfile.TemporaryDirectory() as td:
            self.patched(Path(td), "win32")
            self.assertEqual(mas._venv_dir(), Path(td) / ".venv")
            self.assertEqual(mas._venv_python(),
                             Path(td) / ".venv" / "Scripts" / "python.exe")

    def test_linux_layout(self):
        with tempfile.TemporaryDirectory() as td:
            self.patched(Path(td), "linux")
            self.assertEqual(mas._venv_dir(), Path(td) / ".venv-linux")
            self.assertEqual(mas._venv_python(),
                             Path(td) / ".venv-linux" / "bin" / "python")

class TestDepsInstalledPlatformAware(_PlatformCase):
    def test_linux_sees_only_windows_venv_not_installed(self):
        # 事故场景回归：容器内只有挂载进来的 Windows venv → 必须判定未部署
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "acestep").mkdir()
            _make_win_venv(tmp)
            self.patched(tmp, "linux")
            self.assertFalse(mas.acestep_deps_installed())

    def test_linux_venv_installed(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "acestep").mkdir()
            _make_linux_venv(tmp)
            self.patched(tmp, "linux")
            self.assertTrue(mas.acestep_deps_installed())

    def test_windows_venv_installed(self):
        # 宿主机既有行为不回归
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "acestep").mkdir()
            _make_win_venv(tmp)
            self.patched(tmp, "win32")
            self.assertTrue(mas.acestep_deps_installed())

    def test_missing_source_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _make_linux_venv(tmp)
            self.patched(tmp, "linux")
            self.assertFalse(mas.acestep_deps_installed())

class TestInstallHintInDocker(unittest.TestCase):
    def test_hint_appends_docker_line(self):
        with mock.patch.object(mas, "_in_docker", return_value=True):
            self.assertIn("docker exec -it meloyu-backend",
                          mas.acestep_install_hint())
        with mock.patch.object(mas, "_in_docker", return_value=False):
            self.assertNotIn("docker exec", mas.acestep_install_hint())

if __name__ == "__main__":
    unittest.main()
