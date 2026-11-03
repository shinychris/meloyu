""" 开放 API β 单测（v0.8.2）：密钥生命周期 + 密钥鉴权生歌/查询/下载。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
FastAPI TestClient（httpx）+ 内存库 + 临时 audio 目录；生成执行 mock 调度。
"""
from __future__ import annotations

import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Plan, SETTING_ID, LLMSetting, User
from app.models.base import utc_now_iso
from app.services import api_keys as keys_svc
from tests.db import new_test_engine, reset_db, seed_plans


class _ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        # StaticPool：TestClient 工作线程与本线程共享同一内存连接（否则各自空库）
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：补齐夹具未自带的档位行（users.plan 外键）
        seed_plans(self.db, skip={'studio'})
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="api@test.local", password_hash="x",
                         nickname="dev", plan="studio", credit_balance=10000,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.add(Plan(code="studio", name="Studio", price_monthly=168,
                         price_yearly=134, daily_generations=None,
                         monthly_credits=10000, max_export="wav",
                         commercial_license=True, watermark=False, features=[],
                         switchable=True, sort_order=2, created_at=ts, updated_at=ts))
        # 歌词引擎守卫：开放 API 生歌需自动写词，须配置真实 LLM 通道
        self.db.add(LLMSetting(id=SETTING_ID, lyrics_backend="ollama",
                               ollama_model="qwen2.5:7b"))
        self.db.commit()

        # TestClient 注入测试库 session（override get_db）
        self._orig_override = app.dependency_overrides.get(get_db)

        def _test_db():
            session = sessionmaker(bind=self.engine)()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _test_db
        self.client = TestClient(app)

    def tearDown(self):
        if self._orig_override is not None:
            app.dependency_overrides[get_db] = self._orig_override
        else:
            app.dependency_overrides.pop(get_db, None)
        self.db.close()
        settings.data_dir = self._old
        self.tmp.cleanup()

    def _auth(self) -> dict:
        from app.core.security import create_access_token
        return {"Authorization": f"Bearer {create_access_token(self.user)}"}

class TestKeyLifecycle(_ApiTestCase):
    def test_issue_list_revoke(self):
        r = self.client.post("/api/v1/api-keys", json={"name": "prod"},
                             headers=self._auth())
        self.assertEqual(r.status_code, 201)
        data = r.json()["data"]
        self.assertTrue(data["key"].startswith("meloyu_sk_"))
        self.assertEqual(len(data["key"]), len("meloyu_sk_") + 40)
        # 列表只回前缀，不回完整 key
        r = self.client.get("/api/v1/api-keys", headers=self._auth())
        items = r.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertNotIn("key", items[0])
        self.assertTrue(items[0]["prefix"].startswith("meloyu_sk_"))
        # 吊销后列表清空、鉴权失效
        r = self.client.delete(f"/api/v1/api-keys/{items[0]['id']}",
                               headers=self._auth())
        self.assertTrue(r.json()["data"]["ok"])
        self.assertEqual(self.client.get("/api/v1/api-keys",
                                         headers=self._auth()).json()["data"]["total"], 0)
        response = self.client.get("/api/v1/public/works",
                                   headers={"X-API-Key": data["key"]})
        self.assertEqual(response.status_code, 401)

    def test_max_five_keys(self):
        for i in range(5):
            self.client.post("/api/v1/api-keys", json={"name": f"k{i}"},
                             headers=self._auth())
        r = self.client.post("/api/v1/api-keys", json={"name": "6th"},
                             headers=self._auth())
        self.assertEqual(r.status_code, 409)

class TestPublicApi(_ApiTestCase):
    def _key(self) -> str:
        return keys_svc.issue_key(self.db, self.user, "ci")["key"]

    def test_auth_variants_and_bad_key(self):
        key = self._key()
        r = self.client.get("/api/v1/public/works", headers={"X-API-Key": key})
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/v1/public/works",
                            headers={"Authorization": f"Bearer {key}"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/v1/public/works",
                            headers={"X-API-Key": "meloyu_sk_deadbeef"})
        self.assertEqual(r.status_code, 401)
        r = self.client.get("/api/v1/public/works")
        self.assertEqual(r.status_code, 401)

    def test_generate_task_flow_and_via_trace(self):
        key = self._key()
        with mock.patch("app.core.tasks.schedule_generation"):
            r = self.client.post("/api/v1/public/generations", headers={"X-API-Key": key},
                                 json={"mode": "custom",
                                       "style_prompt": "cyber synthwave",
                                       "params": {"duration_sec": 30,
                                                  "vocal": "instrumental"}})
        self.assertEqual(r.status_code, 201, r.text[:200])
        data = r.json()["data"]
        self.assertIn("/public/tasks/", data["poll"])
        # via 留痕
        from app.models import Task
        row = self.db.get(Task, data["task"]["id"])
        self.assertEqual(row.request_payload["via"]["source"], "api_key")
        self.assertEqual(row.request_payload["via"]["key_name"], "ci")
        self.assertEqual(row.cost_credits, 12)  # 按量计费=账号积分（v1_pro=12）
        # 任务查询
        r = self.client.get(f"/api/v1/public/tasks/{data['task']['id']}",
                            headers={"X-API-Key": key})
        self.assertEqual(r.status_code, 200)

    def test_task_of_other_user_denied(self):
        key = self._key()
        ts = utc_now_iso()
        other = User(id="z" * 32, email="other@test.local", password_hash="x",
                     nickname="o", plan="free", credit_balance=1000,
                     created_at=ts, updated_at=ts)
        self.db.add(other)
        self.db.commit()
        other_key = keys_svc.issue_key(self.db, other, "other")["key"]
        with mock.patch("app.core.tasks.schedule_generation"):
            r = self.client.post("/api/v1/public/generations",
                                 headers={"X-API-Key": other_key},
                                 json={"mode": "custom", "style_prompt": "x",
                                       "params": {"duration_sec": 30}})
        tid = r.json()["data"]["task"]["id"]
        # 我的 key 查他人的任务 → 40301（get_task_owned 对非属主拒绝）
        r = self.client.get(f"/api/v1/public/tasks/{tid}", headers={"X-API-Key": key})
        self.assertEqual(r.status_code, 403)

if __name__ == "__main__":
    unittest.main()
