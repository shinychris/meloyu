"""SongGeneration 自托管通道真机 E2E（V1.5.1 补充批）。

前置：SongGeneration-Studio 已部署（backend/data/sg2_studio：.venv + 权重 +
runtime），model server 在 127.0.0.1:42100 运行且已可加载模型。
用法：./.venv/Scripts/python scripts/sg2_e2e.py [--duration 30]
验收点：目录 ready → 切通道 → 提交 → succeeded 双候选 → 母带规格 → 还原。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
# 凭据可经环境变量覆盖（MELOYU_EMAIL/MELOYU_PASSWORD；默认=dev 种子演示账号）
EMAIL = os.environ.get("MELOYU_EMAIL", "demo@meloyu.local")
PASSWORD = os.environ.get("MELOYU_PASSWORD", "Meloyu2026")


def call(method: str, path: str, token: str = "", body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=30)
    args = ap.parse_args()
    ok_all = True

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal ok_all
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail[:160]}", flush=True)
        ok_all = ok_all and ok

    _, b = call("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    token = b["data"]["access_token"]

    _, b = call("GET", "/models/music-catalog", token)
    entry = next((m for m in b["data"]["models"] if m["id"] == "songgeneration-2"), {})
    check("目录 songgeneration-2 服务在线（ready）",
          entry.get("local_status") == "ready", entry.get("service_detail", ""))

    _, b = call("GET", "/models/settings", token)
    prev_backend, prev_model = b["data"]["music_backend"], b["data"]["music_model"]
    _, b = call("PUT", "/models/settings", token,
                {"music_backend": "songgen_local", "music_model": "songgeneration-2"})
    check("切 songgen_local", b["data"]["music_backend"] == "songgen_local")

    t0 = time.time()
    code, b = call("POST", "/generations", token, {
        "mode": "custom", "style_prompt": "华语流行抒情，钢琴与弦乐，城市夜色",
        "lyrics": "[Verse]\n夜风穿过旧街的灯\n[Chorus]\n把心事唱给城市听\n",
        "model": "v1_pro", "seed": 20260902,
        "params": {"bpm": 88, "key": {"tonic": "A", "mode": "minor"},
                   "time_signature": "4/4", "duration_sec": args.duration,
                   "vocal": "female_air", "language": "zh", "instrument_density": 60},
    })
    task = b["data"]["task"]
    check("提交 201 + provider 留痕", code == 201 and task["provider"] == "songgen_local")
    tid = task["id"]
    while True:
        time.sleep(5)
        _, b = call("GET", f"/tasks/{tid}", token)
        t = b["data"]
        if t["status"] not in ("queued", "running"):
            break
        print(f"  … {t['status']} {t['progress']}% {t['stage_key']} {t['stage_label']}", flush=True)
    elapsed = time.time() - t0
    cands = (t.get("result") or {}).get("candidates") or []
    check(f"终态 succeeded 双候选（{elapsed:.0f}s）",
          t["status"] == "succeeded" and len(cands) == 2,
          json.dumps(t.get("error") or cands)[:160])
    _, b = call("GET", f"/versions/{t['version_id']}/candidates", token)
    for c in b["data"]["items"]:
        master = next((f for f in c["files"] if f["kind"] == "master"), None)
        check(f"候选 {c['label']} 母带（vocal={c['vocal']} 时长={c['duration_sec']}s）",
              c["vocal"] == "female_air" and c["quality_score"] is None
              and master is not None and (master["duration_sec"] or 0) >= args.duration - 5,
              f"sr={master.get('sample_rate') if master else '?'}")

    call("PUT", "/models/settings", token,
         {"music_backend": prev_backend, "music_model": prev_model})
    print(f"环境已还原：{prev_backend} · {prev_model}")
    print("E2E 结论：" + ("🟢 全部通过" if ok_all else "🔴 存在失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
