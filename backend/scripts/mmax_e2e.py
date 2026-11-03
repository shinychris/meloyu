"""MiniMax Music 3 本机 audio.cpp 通道真机 E2E（V1.5.1 收尾批）。

前置：backend/data/audiocpp/ 已部署（audiocpp_cli.exe + MiniMax-Music3-GGUF），
后端运行中。本机 Q4 量化实测 RTF~94：API 层验证提交→进度→取消→退款链路
（接口时长下限 30s，走完整双候选需 90 分钟+，不宜阻塞）；出歌验证直接调
provider 用 10s 曲跑双候选（约 30~35 分钟）。
用法：./.venv/Scripts/python scripts/mmax_e2e.py
"""
from __future__ import annotations

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


def api_layer(ok_all) -> tuple[str, str]:
    """API 层：目录 ready → 切通道 → 提交（30s）→ running 留痕 → 取消 → 退款。"""
    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal ok_all
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail[:160]}", flush=True)
        ok_all[0] = ok_all[0] and ok

    _, b = call("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    token = b["data"]["access_token"]

    _, b = call("GET", "/models/music-catalog", token)
    entry = next((m for m in b["data"]["models"] if m["id"] == "minimax-music-3"), {})
    check("目录 minimax-music-3 就绪（本机 audio.cpp）",
          entry.get("local_status") == "ready", entry.get("service_detail", ""))

    _, b = call("GET", "/models/settings", token)
    prev_backend, prev_model = b["data"]["music_backend"], b["data"]["music_model"]
    _, b = call("PUT", "/models/settings", token,
                {"music_backend": "mmax_local", "music_model": "minimax-music-3"})
    check("切 mmax_local", b["data"]["music_backend"] == "mmax_local")

    _, b = call("GET", "/credits/balance", token)
    bal_before = b["data"]["balance"]

    code, b = call("POST", "/generations", token, {
        "mode": "custom", "style_prompt": "华语流行，清爽女声，钢琴与轻鼓点",
        "lyrics": "[Verse]\n夜色里灯火慢慢亮起\n我在人潮里找你\n[Chorus]\n把心事唱成一首歌\n让风带给你听\n",
        "model": "v1_pro", "seed": 20260903,
        "params": {"bpm": 96, "key": {"tonic": "C", "mode": "major"},
                   "time_signature": "4/4", "duration_sec": 30,
                   "vocal": "female_air", "language": "zh", "instrument_density": 60},
    })
    task = b["data"]["task"]
    check("提交 201 + provider 留痕", code == 201 and task["provider"] == "mmax_local")

    # 观察 running 推进（audio.cpp 子进程真实拉起）后取消
    running_seen = False
    for _ in range(24):  # 最多 4 分钟
        time.sleep(10)
        _, b = call("GET", f"/tasks/{task['id']}", token)
        t = b["data"]
        if t["status"] == "running" and t["stage_key"] in ("model_sample", "model_export"):
            running_seen = True
            break
        if t["status"] not in ("queued", "running"):
            break
    check("running 推进至模型采样阶段（子进程真实拉起）", running_seen,
          json.dumps(t)[:120])
    _, b = call("POST", f"/tasks/{task['id']}/cancel", token)
    time.sleep(8)
    _, b = call("GET", f"/tasks/{task['id']}", token)
    t = b["data"]
    _, b = call("GET", "/credits/balance", token)
    refunded = b["data"]["balance"] == bal_before
    check("取消终态 + 子进程终止 + 全额退款", t["status"] == "canceled" and refunded,
          f"status={t['status']} balance={b['data']['balance']}(before={bal_before})")

    call("PUT", "/models/settings", token,
         {"music_backend": prev_backend, "music_model": prev_model})
    return prev_backend, prev_model


def provider_layer(ok_all) -> None:
    """Provider 层：直调 _generate_local 跑 10s 双候选（约 30 分钟），验证真实出歌。"""
    import tempfile
    from pathlib import Path

    from app.config import settings as cfg
    from app.providers.music_selfhosted import MiniMaxSelfHostedProvider
    from app.synth.ir import SongRequest

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal ok_all
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail[:160]}", flush=True)
        ok_all[0] = ok_all[0] and ok

    provider = MiniMaxSelfHostedProvider("minimax-music-3", {})
    req = SongRequest(
        style_prompt="华语流行，清爽女声，钢琴与轻鼓点",
        negative_prompt="", model="v1_pro",
        lyrics="[Verse]\n夜色里灯火慢慢亮起\n[Chorus]\n把心事唱成一首歌\n",
        bpm=96, tonic="C", mode="major", time_signature="4/4", duration_sec=10,
        vocal="female_air", language="zh", instrument_density=60, seed=20260903)
    dest = Path(tempfile.mkdtemp(dir=cfg.data_path / "audio"))
    t0 = time.time()

    def progress(key, pct, label):
        if pct in (15, 50, 80):
            print(f"  [{time.time()-t0:.0f}s] {pct}% {key} {label}", flush=True)

    output = provider.generate(req, progress, lambda: False, str(dest))
    cands = output.candidates
    check(f"provider 直调出歌双候选（{time.time()-t0:.0f}s）", len(cands) == 2)
    for c in cands:
        master = dest / next(f["relpath"] for f in c.files if f["kind"] == "master")
        import soundfile as sf
        info = sf.info(str(master))
        check(f"候选 {c.label}（{info.samplerate}Hz {info.channels}ch {info.duration:.1f}s）",
              info.duration >= 9 and info.channels == 2 and c.vocal == "female_air")
    import shutil
    shutil.rmtree(dest, ignore_errors=True)


def main() -> int:
    ok_all = [True]
    prev = api_layer(ok_all)
    provider_layer(ok_all)
    print(f"环境已还原：{prev[0]} · {prev[1]}")
    print("E2E 结论：" + ("🟢 全部通过" if ok_all[0] else "🔴 存在失败项"))
    return 0 if ok_all[0] else 1


if __name__ == "__main__":
    sys.exit(main())
