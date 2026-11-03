"""用量统计服务单测（v0.17.0）：按天/按引擎聚合 + 歌词通道族判定。

配套：积分已转纯计量（B5），/usage/stats 面向用户自定义 API 的
调用做统计与分析——本文件验证聚合口径（calls 计提交、units 只计成功、
按天补零、远程/本地通道分类）与 current_lyrics_backend 回退判定。
"""
from __future__ import annotations

import unittest

from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.models import SETTING_ID, LLMSetting, Task, User
from app.models.base import utc_now_iso
from app.services import model_center
from app.services import usage as usage_svc
from tests.db import new_test_engine, reset_db


def _ts(days_ago: float) -> str:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class _UsageTestCase(unittest.TestCase):
    """每个用例独立内存库 + 一个用户。"""

    def setUp(self):
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        ts = utc_now_iso()
        self.user = User(id="u" + "x" * 31, email="u@t.dev", password_hash="x",
                         nickname="U", plan="studio",
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _task(self, *, status="succeeded", provider="acestep_local",
              lyrics_engine=None, cost=12, days_ago=0.5, model=None):
        ts = _ts(days_ago)
        self.db.add(Task(user_id=self.user.id, type="generation", status=status,
                         progress=100 if status == "succeeded" else 0,
                         stage_key="done", stage_label="q", provider=provider,
                         lyrics_engine=lyrics_engine, seed=1,
                         cost_credits=cost, request_payload={},
                         created_at=ts, updated_at=ts))


class TestUsageStatsAggregation(_UsageTestCase):

    def test_aggregates_by_engine_status_and_day(self):
        # 窗口内：api×2（1 成功 1 失败）、acestep×1 成功、无 provider 兜底 localsynth×1 取消
        self._task(status="succeeded", provider="api", lyrics_engine="openai_compat")
        self._task(status="failed", provider="api", cost=12)
        self._task(status="succeeded", provider="acestep_local", cost=6)
        self._task(status="canceled", provider=None, cost=12)
        # 窗口外（40 天前）：只进 all_time
        self._task(status="succeeded", provider="api", cost=12, days_ago=40)
        # export 任务不计入
        self.db.add(Task(user_id=self.user.id, type="export", status="succeeded",
                         progress=100, stage_key="done", stage_label="q",
                         provider=None, seed=None, cost_credits=0,
                         request_payload={}, created_at=_ts(0.5), updated_at=_ts(0.5)))
        self.db.commit()

        out = usage_svc.stats_dict(self.db, self.user, days=30)

        self.assertEqual(out["totals"]["window"],
                         {"calls": 4, "succeeded": 2, "failed": 1, "canceled": 1,
                          "units": 18})
        self.assertEqual(out["totals"]["all_time"]["calls"], 5)
        self.assertEqual(out["totals"]["all_time"]["units"], 30)

        engines = {e["engine"]: e for e in out["by_engine"]}
        self.assertEqual(engines["api"]["kind"], "remote_api")
        self.assertEqual(engines["api"]["calls"], 2)
        self.assertEqual(engines["api"]["succeeded"], 1)
        self.assertEqual(engines["api"]["units"], 12)  # 失败不计 units
        self.assertEqual(engines["acestep_local"]["kind"], "local")
        # provider 为空回退 localsynth 口径（与证书署名一致）
        self.assertEqual(engines["localsynth"]["calls"], 1)

        lyrics = {e["engine"]: e for e in out["lyrics_by_engine"]}
        self.assertEqual(lyrics["openai_compat"]["calls"], 1)
        self.assertEqual(lyrics["openai_compat"]["kind"], "remote_api")

        # 远程调用 = 歌曲通道 api(2) + 歌词通道 openai_compat(1)
        self.assertEqual(out["remote_api_calls"], 3)

    def test_by_day_zero_filled_and_local_day_bucket(self):
        # 时间稳健：任务时间取 min(1 小时, 本地今天已过时长的一半)。原
        # days_ago=0.2 固定 4.8 小时前，在本地 0:00~4:48 之间跑会跨过午夜
        # 落到昨天桶而必红——按当天已过多久动态取点，任何时刻运行都落今天桶
        _dt = __import__("datetime")
        now_local = _dt.datetime.now().astimezone()
        midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        since_midnight = (now_local - midnight).total_seconds()
        days_ago = min(3600.0, since_midnight / 2) / 86400
        self._task(days_ago=days_ago)
        self.db.commit()
        out = usage_svc.stats_dict(self.db, self.user, days=7)
        dates = [d["date"] for d in out["by_day"]]
        # 补零序列：7 天窗口按本机自然日，跨时区边界为 7~8 个桶
        self.assertIn(len(dates), (7, 8))
        self.assertEqual(dates[-1],
                         _dt.datetime.now().astimezone()
                         .strftime("%Y-%m-%d"))
        today = out["by_day"][-1]
        self.assertEqual(today["calls"], 1)
        self.assertEqual(today["units"], 12)
        # 其余天全部补零
        self.assertTrue(all(d["calls"] == 0 for d in out["by_day"][:-1]))

    def test_empty_user_returns_zero_series(self):
        out = usage_svc.stats_dict(self.db, self.user, days=30)
        self.assertEqual(out["totals"]["window"]["calls"], 0)
        self.assertEqual(out["by_engine"], [])
        self.assertEqual(out["lyrics_by_engine"], [])
        self.assertEqual(out["remote_api_calls"], 0)


class TestCurrentLyricsBackend(_UsageTestCase):
    """通道族判定与 get_lyrics_provider 的未配置口径一致（无兜底引擎）。"""

    def _set(self, **kw):
        row = LLMSetting(id=SETTING_ID, **kw)
        self.db.add(row)
        self.db.commit()

    def test_no_row_defaults_to_none(self):
        self.assertEqual(model_center.current_lyrics_backend(self.db), "none")

    def test_ollama_requires_model(self):
        self._set(lyrics_backend="ollama", ollama_model="")
        self.assertEqual(model_center.current_lyrics_backend(self.db), "none")

    def test_legacy_localsynth_reads_as_none(self):
        # 存量行历史值 localsynth（原离线规则引擎，已移除）读作未配置
        self._set(lyrics_backend="localsynth")
        self.assertEqual(model_center.current_lyrics_backend(self.db), "none")

    def test_ollama_with_model(self):
        self._set(lyrics_backend="ollama", ollama_model="qwen2.5:7b")
        self.assertEqual(model_center.current_lyrics_backend(self.db), "ollama")

    def test_openai_compat_requires_endpoint_and_model(self):
        self._set(lyrics_backend="openai_compat", external_base_url="",
                  external_model="")
        self.assertEqual(model_center.current_lyrics_backend(self.db), "none")

    def test_openai_compat_configured(self):
        self._set(lyrics_backend="openai_compat",
                  external_base_url="https://api.example.com/v1",
                  external_model="glm-4.7")
        self.assertEqual(model_center.current_lyrics_backend(self.db),
                         "openai_compat")


if __name__ == "__main__":
    unittest.main()
