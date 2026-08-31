"""ACE-Step v1.5 通道真机 E2E 验证（V1.5 批）。

前置：ACE-Step venv 已部署、checkpoints 已下载、后端已启动。
用法：./.venv/Scripts/python scripts/acestep_e2e.py [--duration 30]
验收点：
  1. 目录项 ace-step local_status=ready 且含 acestep_local 通道
  2. 切 acestep_local 通道 + runtime 引擎标签
  3. 提交生成（带歌词+人声）→ provider=acestep_local → succeeded 双候选
  4. 候选 vocal 如实留痕、quality_score=null、48kHz wav 母带真实时长
  5. MP3 导出时长与母带一致（采样率修复回归）
  6. 环境还原（切回执行前引擎）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL, PASSWORD = "demo@meloyu.local", "Meloyu2026"


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
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail[:180]}")
        ok_all = ok_all and ok

    _, b = call("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    token = b["data"]["access_token"]
    check("登录", bool(token))

    _, b = call("GET", "/models/music-catalog", token)
    entry = next((m for m in b["data"]["models"] if m["id"] == "ace-step"), {})
    check("目录 ace-step 就绪 + acestep_local 通道",
          entry.get("local_status") == "ready"
          and "acestep_local" in entry.get("channels", [])
          and entry.get("benchmark", {}).get("score", 0) >= 9,
          f"status={entry.get('local_status')} channels={entry.get('channels')}")

    _, b = call("GET", "/models/settings", token)
    prev_backend = b["data"]["music_backend"]
    prev_model = b["data"]["music_model"]
    print(f"  原引擎：{prev_backend} · {prev_model}（验收后还原）")

    _, b = call("PUT", "/models/settings", token,
                {"music_backend": "acestep_local", "music_model": "ace-step"})
    check("切 acestep_local", b["data"]["music_backend"] == "acestep_local")
    _, b = call("GET", "/models/runtime", token)
    check("runtime 引擎标签", b["data"]["song_engine"].startswith("ACE-Step 本地"),
          b["data"]["song_engine"])

    lyrics = ("[Verse]\n夜风穿过旧街的灯\n我在人海数着星辰\n"
              "[Chorus]\n把心事唱给城市听\n让旋律替我说明\n")
    t0 = time.time()
    code, b = call("POST", "/generations", token, {
        "mode": "custom", "style_prompt": "华语流行抒情，钢琴与弦乐，城市夜色",
        "lyrics": lyrics, "model": "v1_pro", "seed": 20260901,
        "params": {"bpm": 88, "key": {"tonic": "A", "mode": "minor"},
                   "time_signature": "4/4", "duration_sec": args.duration,
                   "vocal": "female_air", "language": "zh", "instrument_density": 60},
    })
    task = b["data"]["task"]
    check("提交 201 + provider 留痕", code == 201 and task["provider"] == "acestep_local",
          json.dumps(task)[:120])
    tid = task["id"]
    while True:
        time.sleep(3)
        _, b = call("GET", f"/tasks/{tid}", token)
        t = b["data"]
        if t["status"] not in ("queued", "running"):
            break
        print(f"  … {t['status']} {t['progress']}% {t['stage_key']} {t['stage_label']}")
    elapsed = time.time() - t0
    cands = (t.get("result") or {}).get("candidates") or []
    check(f"终态 succeeded 双候选（{elapsed:.0f}s）",
          t["status"] == "succeeded" and len(cands) == 2, json.dumps(t.get("error") or cands)[:160])

    _, b = call("GET", f"/versions/{t['version_id']}/candidates", token)
    for c in b["data"]["items"]:
        check(f"候选 {c['label']} 元数据（vocal/时长/quality=null）",
              c["vocal"] == "female_air" and c["quality_score"] is None
              and c["duration_sec"] >= args.duration - 5,
              f"vocal={c['vocal']} dur={c['duration_sec']} q={c['quality_score']}")
        master = next((f for f in c["files"] if f["kind"] == "master"), None)
        if master:
            check(f"候选 {c['label']} 母带时长与登记一致",
                  abs((master["duration_sec"] or 0) - c["duration_sec"]) < 2,
                  f"wav={master['duration_sec']}s cand={c['duration_sec']}s")

    # MP3 导出时长一致（采样率修复回归）：先采纳候选 A 再导出
    if cands:
        call("POST", f"/candidates/{cands[0]['id']}/adopt", token)
        code, b = call("POST", "/exports", token,
                       {"version_id": t["version_id"],
                        "candidate_id": cands[0]["id"], "format": "mp3"})
        if code in (200, 201, 202):
            et = b["data"]["task"]
            for _ in range(60):
                time.sleep(1.5)
                _, b2 = call("GET", f"/tasks/{et['id']}", token)
                if b2["data"]["status"] not in ("queued", "running"):
                    break
            ex = b2["data"]
            files = (ex.get("result") or {}).get("files") or []
            f0 = files[0] if files else {}
            check("MP3 导出时长≈母带（采样率回归）",
                  ex["status"] == "succeeded"
                  and abs((f0.get("duration_sec") or 0) - cands[0]["duration_sec"]) <= 2,
                  f"mp3={f0.get('duration_sec')}s vs 候选={cands[0]['duration_sec']}s")

    # 还原
    call("PUT", "/models/settings", token,
         {"music_backend": prev_backend, "music_model": prev_model})
    print(f"环境已还原：{prev_backend} · {prev_model}")
    print("E2E 结论：" + ("🟢 全部通过" if ok_all else "🔴 存在失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
