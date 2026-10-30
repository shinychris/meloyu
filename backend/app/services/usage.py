"""用量统计服务（2026-10-17）：面向用户自定义 API 的调用统计与分析。

定位转型后积分已转纯计量（B5，license 模式不扣减不拒绝），本模块从 tasks
表聚合真实用量：按天 / 按歌曲引擎通道 / 按歌词引擎通道。远程通道
（api / replicate / openai_compat）消耗的是用户自有 API Key 配额，本表
只做统计分析口径；units 为计量单位（历史积分口径的等价量）。

口径说明：
- calls 按提交计（含失败/取消）；units 仅统计成功任务（与流水净额一致——
  license 模式失败/取消任务会记等额退款流水，净消耗为 0）；
- by_day 按后端本机时区的自然日分桶（桌面形态即用户自己机器的时区）；
- export 任务不计入（无引擎调用）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User

# 远程通道 = 用户自定义 API（自有 Key 计费）；其余（含 ollama 本地推理）视为本地
REMOTE_API_ENGINES = {"api", "replicate", "openai_compat"}

_STATUS_KEYS = ("succeeded", "failed", "canceled")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _totals(db: Session, user_id: str, from_iso: str | None) -> dict:
    sql = ("SELECT status, COUNT(*), COALESCE(SUM(CASE WHEN status = 'succeeded' "
           "THEN cost_credits ELSE 0 END), 0) FROM tasks "
           "WHERE user_id = :uid AND type = 'generation'")
    params: dict = {"uid": user_id}
    if from_iso:
        sql += " AND created_at >= :from"
        params["from"] = from_iso
    sql += " GROUP BY status"
    out = {"calls": 0, "succeeded": 0, "failed": 0, "canceled": 0, "units": 0}
    for status, count, units in db.execute(text(sql), params):
        out["calls"] += count
        if status in _STATUS_KEYS:
            out[status] += count
        if status == "succeeded":
            out["units"] += units
    return out


def stats_dict(db: Session, user: User, days: int) -> dict:
    """聚合统计：总量（全部/窗口）+ 按天序列 + 按引擎通道分组。"""
    now_local = datetime.now().astimezone()
    from_dt = now_local - timedelta(days=days)
    from_iso = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = db.execute(
        text("SELECT created_at, status, cost_credits, provider, lyrics_engine "
             "FROM tasks WHERE user_id = :uid AND type = 'generation' "
             "AND created_at >= :from"),
        {"uid": user.id, "from": from_iso},
    ).fetchall()

    by_day: dict[str, dict] = {}
    by_engine: dict[str, dict] = {}
    lyrics_by_engine: dict[str, dict] = {}
    for created_at, status, cost, provider, lyrics_engine in rows:
        day = _parse_iso(created_at).astimezone().strftime("%Y-%m-%d")
        d = by_day.setdefault(day, {"calls": 0, "units": 0})
        d["calls"] += 1
        if status == "succeeded":
            d["units"] += cost
        engine = provider or "localsynth"
        e = by_engine.setdefault(
            engine, {"engine": engine, "kind": ("remote_api" if engine in REMOTE_API_ENGINES else "local"),
                     "calls": 0, "succeeded": 0, "units": 0})
        e["calls"] += 1
        if status == "succeeded":
            e["succeeded"] += 1
            e["units"] += cost
        if lyrics_engine:
            le = lyrics_by_engine.setdefault(
                lyrics_engine,
                {"engine": lyrics_engine,
                 "kind": ("remote_api" if lyrics_engine in REMOTE_API_ENGINES else "local"),
                 "calls": 0})
            le["calls"] += 1

    # 按天补零：从窗口首日到本机今日，序列完整便于前端画趋势
    day_list = []
    cursor = from_dt.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor <= today:
        key = cursor.strftime("%Y-%m-%d")
        day_list.append({"date": key, **by_day.get(key, {"calls": 0, "units": 0})})
        cursor += timedelta(days=1)

    engine_list = sorted(by_engine.values(), key=lambda x: -x["calls"])
    lyrics_list = sorted(lyrics_by_engine.values(), key=lambda x: -x["calls"])
    return {
        "mode": settings.billing_mode,
        "window": {"days": days, "from": from_iso,
                   "to": now_local.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "totals": {
            "all_time": _totals(db, user.id, None),
            "window": _totals(db, user.id, from_iso),
        },
        "by_day": day_list,
        "by_engine": engine_list,
        "lyrics_by_engine": lyrics_list,
        "remote_api_calls": sum(e["calls"] for e in engine_list + lyrics_list
                                if e["kind"] == "remote_api"),
    }
