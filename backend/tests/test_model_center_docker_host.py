"""模型中心生产部署寻址单测：容器内 loopback 自动改用 host.docker.internal。

覆盖（deploy/docker-compose.yml 生产形态，backend 跑容器、Ollama/自托管服务在宿主机）：
  1. OllamaClient._norm_host 剥 OpenAI 兼容习惯的 /v1 尾缀；
  2. _ollama_client 容器内把 DB 默认 localhost 持久化替换为 host.docker.internal，
     自定义地址不动、非容器环境不动；
  3. external_presets 的 Ollama 本地网关预设容器内自动给宿主机地址；
  4. music_selfhosted.service_host 未配置时容器内默认端点指向宿主机别名。

运行：.venv/Scripts/python.exe -m unittest tests.test_model_center_docker_host -v
"""
from __future__ import annotations

import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.models import SETTING_ID, Base, LLMSetting
from app.providers.llm.ollama_client import OllamaClient, _norm_host
from app.services import model_center as mc


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _FakeDockerPath:
    """music_selfhosted 模块内的 Path 替身：仅 /.dockerenv 报存在。"""

    def __init__(self, p):
        self._p = str(p)

    def exists(self) -> bool:
        return self._p == "/.dockerenv"


class TestNormHost(unittest.TestCase):
    def test_v1_suffix_stripped(self):
        self.assertEqual(_norm_host("http://host.docker.internal:11434/v1"),
                         "http://host.docker.internal:11434")
        self.assertEqual(_norm_host("http://localhost:11434/v1/"),
                         "http://localhost:11434")

    def test_plain_host_kept(self):
        self.assertEqual(_norm_host("http://10.0.0.5:11434"), "http://10.0.0.5:11434")
        self.assertEqual(_norm_host("ollama-svc:11434"), "http://ollama-svc:11434")
        self.assertEqual(_norm_host(""), "http://localhost:11434")
        self.assertEqual(OllamaClient("http://h:11434/v1").base, "http://h:11434")


class TestOllamaClientDockerFallback(unittest.TestCase):
    def test_loopback_replaced_and_persisted_in_docker(self):
        db = _db()
        db.add(LLMSetting(id=SETTING_ID))
        db.commit()
        s = db.get(LLMSetting, SETTING_ID)
        self.assertEqual(s.ollama_host, "http://localhost:11434")  # 出厂默认
        with mock.patch.object(mc, "_in_docker", return_value=True):
            client = mc._ollama_client(db, s)
        self.assertEqual(client.base, "http://host.docker.internal:11434")
        self.assertEqual(s.ollama_host, "http://host.docker.internal:11434")  # 已持久化
        # 二次解析：DB 已是宿主机别名，不再改写
        with mock.patch.object(mc, "_in_docker", return_value=True):
            self.assertEqual(mc._ollama_client(db, s).base,
                             "http://host.docker.internal:11434")

    def test_custom_host_untouched_in_docker(self):
        db = _db()
        db.add(LLMSetting(id=SETTING_ID, ollama_host="http://ollama-svc:11434"))
        db.commit()
        s = db.get(LLMSetting, SETTING_ID)
        with mock.patch.object(mc, "_in_docker", return_value=True):
            self.assertEqual(mc._ollama_client(db, s).base, "http://ollama-svc:11434")

    def test_no_rewrite_outside_docker(self):
        db = _db()
        db.add(LLMSetting(id=SETTING_ID))
        db.commit()
        s = db.get(LLMSetting, SETTING_ID)
        with mock.patch.object(mc, "_in_docker", return_value=False):
            self.assertEqual(mc._ollama_client(db, s).base, "http://localhost:11434")

    def test_runtime_status_reports_docker_flag_and_effective_host(self):
        db = _db()
        db.add(LLMSetting(id=SETTING_ID))
        db.commit()
        with mock.patch.object(mc, "_in_docker", return_value=True), \
                mock.patch.object(OllamaClient, "version",
                                  side_effect=mc.LLMError("unavailable", "down")):
            rt = mc.runtime_status(db)
        self.assertTrue(rt["docker"])
        self.assertEqual(rt["ollama"]["host"], "http://host.docker.internal:11434")
        self.assertFalse(rt["ollama"]["running"])
        self.assertIn("OLLAMA_HOST=0.0.0.0", rt["ollama"]["install_hint"])


class TestPresetsAndSelfhosted(unittest.TestCase):
    def test_ollama_gateway_preset_env_aware(self):
        with mock.patch.object(mc, "_in_docker", return_value=True):
            presets = {p["base_url"] for p in mc.external_presets()}
        self.assertIn("http://host.docker.internal:11434/v1", presets)
        with mock.patch.object(mc, "_in_docker", return_value=False):
            presets = {p["base_url"] for p in mc.external_presets()}
        self.assertIn("http://localhost:11434/v1", presets)

    def test_selfhosted_default_host_env_aware(self):
        from app.providers import music_selfhosted as sh
        with mock.patch.object(sh, "Path", _FakeDockerPath):
            self.assertEqual(sh.service_host("mmax_local", None),
                             "http://host.docker.internal:8300")
            self.assertEqual(sh.service_host("songgen_local", {}),
                             "http://host.docker.internal:42100")
            # 显式配置优先，不做替换
            self.assertEqual(sh.service_host("mmax_local", {"mmax_local": "http://x:1"}),
                             "http://x:1")
        # 非容器环境保持 127.0.0.1 默认
        self.assertEqual(sh.service_host("mmax_local", None), "http://127.0.0.1:8300")


if __name__ == "__main__":
    unittest.main()
