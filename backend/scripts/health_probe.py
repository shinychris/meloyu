r"""Meloyu 健康拨测脚本（P1-7）。

检查项：
1. HTTP 拨测：GET {base}/api/v1/system/health
   （端点以 backend/app/api/v1/system.py 为准：system 路由 prefix=/system，
   挂载于 API_PREFIX=/api/v1 之下，即 GET /api/v1/system/health，无鉴权）。
   base 默认 http://127.0.0.1:8000，可用环境变量 MELOYU_BASE_URL 覆盖。
2. 任务失败率：只读打开 backend/data/meloyu.db，统计 tasks 表近 24h
   （created_at 为 UTC ISO 字符串，字典序=时间序）status='failed' 占比；
   样本 >= 10 且失败率 > 5% 时输出告警。库文件不存在则跳过本项。

实现约束：仅用标准库（urllib / sqlite3），不新增第三方依赖。

用法：
    backend/.venv/Scripts/python.exe backend/scripts/health_probe.py
    MELOYU_BASE_URL=http://10.0.0.5:8000 backend/.venv/Scripts/python.exe backend/scripts/health_probe.py

退出码：0 = 健康（或样本不足无法告警）；1 = 后端未起 / 拨测失败 / 失败率超阈值。
适配监控拉起（cron / 计划任务 / 容器 healthcheck 判断退出码即可）。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "data" / "meloyu.db"
DEFAULT_BASE = "http://127.0.0.1:8000"
HEALTH_PATH = "/api/v1/system/health"
TIMEOUT_SEC = 5
WINDOW_HOURS = 24
MIN_SAMPLE = 10
FAILURE_RATE_THRESHOLD = 0.05


def check_health(base: str) -> tuple[bool, str]:
    """GET {base}/api/v1/system/health，返回 (是否健康, 人类可读结果)。"""
    url = base.rstrip("/") + HEALTH_PATH
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"[health] FAIL {url} -> HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"[health] FAIL {url} -> 无法连接（{exc.__class__.__name__}: {exc}）"
    data = body.get("data") or {}
    if resp_status_ok(body) and data.get("status") == "ok":
        detail = (f"version={data.get('version')} uptime={data.get('uptime_sec')}s "
                  f"tasks_running={data.get('tasks_running')} audio_files={data.get('audio_files')}")
        return True, f"[health] OK   {url} -> {detail}"
    return False, f"[health] FAIL {url} -> 响应异常: {json.dumps(body, ensure_ascii=False)[:200]}"


def resp_status_ok(body: dict) -> bool:
    """统一响应包裹 {code,message,data}，code==0 视为业务成功。"""
    return body.get("code") == 0


def check_task_failure_rate() -> bool:
    """近 24h tasks 失败率统计，超阈值返回 False（视为拨测失败）。"""
    if not DB_PATH.is_file():
        print(f"[tasks] 数据库不存在，跳过失败率统计：{DB_PATH}")
        return True
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    cutoff = (datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        con = sqlite3.connect(uri, uri=True)
        try:
            total = con.execute(
                "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (cutoff,)
            ).fetchone()[0]
            failed = con.execute(
                "SELECT COUNT(*) FROM tasks WHERE created_at >= ? AND status = 'failed'",
                (cutoff,),
            ).fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as exc:
        print(f"[tasks] 数据库读取失败，跳过失败率统计（{exc.__class__.__name__}: {exc}）")
        return True
    if total == 0:
        print(f"[tasks] 近 {WINDOW_HOURS}h 无任务样本（total=0），无法计算失败率")
        return True
    rate = failed / total
    line = (f"[tasks] 近 {WINDOW_HOURS}h 任务 total={total} failed={failed} "
            f"失败率={rate:.1%}")
    if total >= MIN_SAMPLE and rate > FAILURE_RATE_THRESHOLD:
        print(f"{line} -> 告警：样本≥{MIN_SAMPLE} 且失败率超过 {FAILURE_RATE_THRESHOLD:.0%}")
        return False
    print(f"{line} -> 正常" + ("" if total >= MIN_SAMPLE else f"（样本<{MIN_SAMPLE}，不告警）"))
    return True


def main() -> int:
    base = os.environ.get("MELOYU_BASE_URL", DEFAULT_BASE)
    healthy, message = check_health(base)
    print(message)
    ok_rate = check_task_failure_rate()
    if not healthy:
        print("[probe] 结论：不健康（后端未启动或 health 接口不可用），退出码 1")
        return 1
    if not ok_rate:
        print("[probe] 结论：不健康（任务失败率超阈值），退出码 1")
        return 1
    print("[probe] 结论：健康，退出码 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
