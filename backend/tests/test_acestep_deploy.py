"""v0.16.3 ACE-Step 组件应用内自动部署单测。

覆盖（app/services/acestep_deploy.py + model_center 部署操作编排）：
  1. 已部署快速路径（幂等秒回，不发任何网络/子进程）；
  2. uv 钉版表完整性（五平台 sha256 落表）与平台键推导；
  3. uv 获取优先级（系统 → 数据目录缓存，不触网）；
  4. 下载 sha256 校验失败清理（file:// 真实流，不依赖外网）；
  5. start_acestep_deploy：已就绪直接落 succeeded、冲突守卫；
     _execute_acestep_deploy/_execute_music_pull 编排（边界替身注入）；
  6. setup 脚本 CLI 薄壳退出码。

外部边界（网络下载 / uv sync 子进程）以测试替身隔离（仅测试内允许），
生产实现为真实链路（真实实现红线，AGENTS.md 2026-10-12）。

运行：.venv/Scripts/python.exe -m unittest tests.test_acestep_deploy -v
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.core.errors import BizError
from app.models import SETTING_ID, LLMSetting, ModelOp
from app.services import acestep_deploy as dep
from app.services import model_center as mc
from tests.db import new_test_engine, reset_db


def _db():
    """测试库会话 + 把 model_center.SessionLocal 一并指到该库（_write_op 通路）。"""
    engine = new_test_engine()
    reset_db(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    s.add(LLMSetting(id=SETTING_ID))
    s.commit()
    return s, factory


def _fake_win_venv(root: Path) -> None:
    """构造「已部署」目录形态：acestep 包目录 + Windows venv site-packages。"""
    (root / "acestep").mkdir(parents=True, exist_ok=True)
    sp = root / ".venv" / "Lib" / "site-packages" / "acestep"
    sp.mkdir(parents=True, exist_ok=True)
    py = root / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_bytes(b"")


class TestFastPath(unittest.TestCase):
    def test_deploy_ready_returns_immediately(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "acestep"
            _fake_win_venv(home)
            with mock.patch.object(settings, "acestep_home", str(home)):
                seen: list[tuple[int, str]] = []
                dep.deploy_acestep(lambda pct, msg: seen.append((pct, msg)))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], 100)
        self.assertTrue("就绪" in seen[0][1] or "ready" in seen[0][1].lower())


class TestUvPinning(unittest.TestCase):
    def test_all_platforms_pinned_with_sha256(self):
        self.assertEqual(
            set(dep._UV_ASSETS), {"win-x64", "linux-x64", "linux-arm64",
                                  "mac-x64", "mac-arm64"})
        for key, (asset, sha) in dep._UV_ASSETS.items():
            self.assertTrue(asset.startswith("uv-"), key)
            self.assertRegex(sha, r"^[0-9a-f]{64}$", key)

    def test_platform_key_on_this_machine(self):
        key = dep._uv_platform_key()
        if sys.platform == "win32":
            self.assertEqual(key, "win-x64")


class TestAcquireUv(unittest.TestCase):
    def test_prefers_system_uv(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch("shutil.which", return_value=str(Path(td) / "uv.exe")), \
                mock.patch.object(dep, "_uv_works", return_value=True):
            got = dep._acquire_uv(lambda p, m: None, 30, 6)
        self.assertEqual(got, str(Path(td) / "uv.exe"))

    def test_uses_cached_uv_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td)
            cached = data / "tools" / "uv" / dep._uv_exe_name()
            cached.parent.mkdir(parents=True)
            cached.write_bytes(b"")
            with mock.patch("shutil.which", return_value=None), \
                    mock.patch.object(dep, "_uv_works", return_value=True), \
                    mock.patch.object(settings, "data_dir", str(data)), \
                    mock.patch.object(dep, "_download_file",
                                      side_effect=AssertionError("不应触网")):
                got = dep._acquire_uv(lambda p, m: None, 30, 6)
            self.assertEqual(Path(got), cached)


class TestDownloadChecksum(unittest.TestCase):
    def test_sha_mismatch_cleans_up(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "payload.bin"
            src.write_bytes(b"meloyu" * 100)
            dest = Path(td) / "out" / "dl.bin"
            with self.assertRaises(dep.ACEStepDeployError) as ctx:
                dep._download_file(src.as_uri(), dest, "0" * 64,
                                   lambda p, m: None, 0, 10)
            self.assertEqual(ctx.exception.kind, "network")
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_suffix(dest.suffix + ".part").exists())

    def test_sha_match_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "payload.bin"
            src.write_bytes(b"meloyu" * 100)
            sha = hashlib.sha256(src.read_bytes()).hexdigest()
            dest = Path(td) / "out" / "dl.bin"
            dep._download_file(src.as_uri(), dest, sha, lambda p, m: None, 0, 10)
            self.assertEqual(dest.read_bytes(), src.read_bytes())


class TestOpsIntegration(unittest.TestCase):
    def test_start_deploy_ready_marks_succeeded_without_executor(self):
        db, _ = _db()
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(settings, "acestep_home",
                                  str(Path(td) / "acestep")) as _, \
                mock.patch.object(mc, "acestep_deps_installed", return_value=True), \
                mock.patch.object(mc, "_submit_op",
                                  side_effect=AssertionError("就绪态不应提交执行")):
            op = mc.start_acestep_deploy(db, "u1")
        self.assertEqual(op["status"], "succeeded")
        self.assertEqual(op["op_type"], "acestep_deploy")

    def test_start_deploy_conflict_guard(self):
        db, _ = _db()
        with mock.patch.object(mc, "acestep_deps_installed", return_value=False):
            db.add(ModelOp(id="op1", user_id="u1", op_type="music_pull",
                           target="musicgen-small", status="running", message=""))
            db.commit()
            with self.assertRaises(BizError):
                mc.start_acestep_deploy(db, "u1")
            # 已有 acestep 部署在跑 → 专属冲突文案（zh/en 任一）
            db.get(ModelOp, "op1").status = "succeeded"
            db.add(ModelOp(id="op2", user_id="u1", op_type="acestep_deploy",
                           target="acestep", status="running", message=""))
            db.commit()
            with self.assertRaises(BizError) as ctx:
                mc.start_acestep_deploy(db, "u1")
            msg = str(ctx.exception)
            self.assertTrue("正在部署" in msg or "already running" in msg)

    def test_execute_deploy_op_runs_service_and_succeeds(self):
        db, factory = _db()
        op = ModelOp(id="opd", user_id="u1", op_type="acestep_deploy",
                     target="acestep", status="queued", message="")
        db.add(op)
        db.commit()
        calls: list[int] = []

        def fake_deploy(on_progress) -> None:
            on_progress(10, "阶段一")
            calls.append(1)

        with mock.patch.object(mc, "SessionLocal", factory), \
                mock.patch.object(mc, "deploy_acestep", side_effect=fake_deploy):
            mc._execute_acestep_deploy("opd")
        db.expire_all()
        done = db.get(ModelOp, "opd")
        self.assertEqual(done.status, "succeeded")
        self.assertEqual(calls, [1])

    def test_music_pull_auto_deploys_deps_first(self):
        """未部署依赖时 music-pull 先走部署（进度 0~30），权重映射到 30~100。"""
        db, factory = _db()
        op = ModelOp(id="opp", user_id="u1", op_type="music_pull",
                     target="ace-step", status="queued", message="")
        db.add(op)
        db.commit()
        progresses: list[int] = []

        def fake_deploy(on_progress) -> None:
            on_progress(50, "部署中")   # → 全局 15
            progresses.append("deployed")

        def fake_pull(model_id, on_progress) -> None:
            on_progress(50, "权重 50%")  # → 全局 30 + 35 = 65
            progresses.append("pulled")

        with mock.patch.object(mc, "SessionLocal", factory), \
                mock.patch.object(mc, "acestep_deps_installed", return_value=False), \
                mock.patch.object(mc, "deploy_acestep", side_effect=fake_deploy), \
                mock.patch.object(mc, "acestep_pull_local", side_effect=fake_pull):
            mc._execute_music_pull("opp", "ace-step")
        db.expire_all()
        done = db.get(ModelOp, "opp")
        self.assertEqual(done.status, "succeeded")
        self.assertEqual(progresses, ["deployed", "pulled"])

    def test_music_pull_deploy_failure_keeps_fallback_hint(self):
        db, factory = _db()
        op = ModelOp(id="opf", user_id="u1", op_type="music_pull",
                     target="ace-step", status="queued", message="")
        db.add(op)
        db.commit()
        boom = dep.ACEStepDeployError("network", "下载失败（代理）")
        with mock.patch.object(mc, "SessionLocal", factory), \
                mock.patch.object(mc, "acestep_deps_installed", return_value=False), \
                mock.patch.object(mc, "deploy_acestep", side_effect=boom):
            mc._execute_music_pull("opf", "ace-step")
        db.expire_all()
        done = db.get(ModelOp, "opf")
        self.assertEqual(done.status, "failed")
        # 失败详情含手动兜底指引（dev 形态=脚本通道，保 smoke 15.8b 口径）
        self.assertIn("setup_acestep", done.error_message)


class TestCliWrapper(unittest.TestCase):
    def test_run_cli_ready_exit_zero(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(settings, "acestep_home",
                                  str(Path(td) / "acestep")):
            _fake_win_venv(Path(td) / "acestep")
            self.assertEqual(dep.run_cli(), 0)


if __name__ == "__main__":
    unittest.main()
