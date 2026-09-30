r"""Meloyu 健康拨测脚本（P1-7）。

检查项：
1. HTTP 拨测：GET {base}/api/v1/system/health
   （端点以 backend/app/api/v1/system.py 为准：system 路由 prefix=/system，
   挂载于 API_PREFIX=/api/v1 之下，即 GET /api/v1/system/health，无鉴权）。
   base 默认 http://127.0.0.1:8000，可用环境变量 MELOYU_BASE_URL 覆盖。
2. 任务失败率：统计 tasks 表近 24h（created_at 为 UTC ISO 字符串，字典序=
   时间序）status='failed' 占比；样本 >= 10 且失败率 > 5% 时输出告警。
   v0.15.0 起：配置 DATABASE_URL（PostgreSQL）时经 psycopg2 查询（容器网络
   主机名 postgres 自动换算为宿主机侧 127.0.0.1:5433；可用 MELOYU_DATABASE_URL
   覆盖）；未配置时只读打开 backend/data/meloyu.db（SQLite 回退）。库不可用
   则跳过本项。

实现约束：标准库 + venv 已装的 psycopg2（PG 模式），不新增额外依赖。

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
from urllib.parse import urlsplit, urlunsplit

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
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
        # v0.13.0：health 不再回显 version/uptime/统计（无鉴权端点信息收敛）
        return True, f"[health] OK   {url} -> status=ok db={data.get('db')}"
    return False, f"[health] FAIL {url} -> 响应异常: {json.dumps(body, ensure_ascii=False)[:200]}"


def resp_status_ok(body: dict) -> bool:
    """统一响应包裹 {code,message,data}，code==0 视为业务成功。"""
    return body.get("code") == 0


def _pg_probe_url() -> str | None:
    """PG 拨测连接串：未配置 DATABASE_URL 返回 None（走 SQLite 回退）。

    容器网络主机名 postgres 在宿主机不可解析——compose 已将 PG 发布到
    127.0.0.1:5433，这里自动换算；MELOYU_DATABASE_URL 可整体覆盖。
    SQLAlchemy 方言后缀（postgresql+psycopg2）剥成 psycopg2 可用的 dsn。
    """
    import re as _re

    from app.config import settings
    url = os.environ.get("MELOYU_DATABASE_URL") or settings.database_url
    if not url:
        return None
    parts = urlsplit(url)
    if parts.hostname == "postgres":
        netloc = parts.netloc.replace("@postgres:", "@127.0.0.1:5433", 1)
        url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
    return _re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def check_task_failure_rate() -> bool:
    """近 24h tasks 失败率统计，超阈值返回 False（视为拨测失败）。"""
    cutoff = (datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pg_url = _pg_probe_url()
    if pg_url:
        return _check_rate_pg(pg_url, cutoff)
    if not DB_PATH.is_file():
        print(f"[tasks] 数据库不存在，跳过失败率统计：{DB_PATH}")
        return True
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
        try:
            total, failed = _rate_query(
                lambda q: con.execute(q, (cutoff,)).fetchone(), "?")
        finally:
            con.close()
    except sqlite3.Error as exc:
        print(f"[tasks] 数据库读取失败，跳过失败率统计（{exc.__class__.__name__}: {exc}）")
        return True
    return _report_rate(total, failed)


def _check_rate_pg(url: str, cutoff: str) -> bool:
    try:
        import psycopg2
        con = psycopg2.connect(url)
        try:
            cur = con.cursor()

            def run(q):
                cur.execute(q, (cutoff,))
                return cur.fetchone()

            total, failed = _rate_query(run, "%s")
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 —— 拨测只读，库不可达不判死
        print(f"[tasks] PG 读取失败，跳过失败率统计（{exc.__class__.__name__}: {exc}）")
        return True
    return _report_rate(total, failed)


def _rate_query(run, ph: str) -> tuple[int, int]:
    total = run(f"SELECT COUNT(*) FROM tasks WHERE created_at >= {ph}")[0]
    failed = run(f"SELECT COUNT(*) FROM tasks WHERE created_at >= {ph} "
                 "AND status = 'failed'")[0]
    return int(total), int(failed)


def _report_rate(total: int, failed: int) -> bool:
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
