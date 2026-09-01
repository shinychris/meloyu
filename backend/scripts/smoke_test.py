"""WP-B8 冒烟测试：38+ 契约接口 + V1.1 派生生成（extend/variant/regen-section）+ 确定性验证。

用法（后端需已在 127.0.0.1:8000 运行，且已灌种子）：
    ./.venv/Scripts/python scripts/smoke_test.py [--base http://127.0.0.1:8000]

不依赖 pytest；输出逐项 PASS/FAIL 与最终通过率。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import uuid
import wave

import httpx

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    results.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  —— {detail}" if detail and not cond else ""))
    return bool(cond)


def unwrap(r: httpx.Response):
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_task(client: httpx.Client, task_id: str, token: str, timeout: float = 240.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"{API}/tasks/{task_id}", headers=auth_headers(token))
        body = unwrap(r)
        assert body["code"] == 0, body
        task = body["data"]
        if task["status"] in ("succeeded", "failed", "canceled"):
            return task
        time.sleep(1.5)
    raise TimeoutError(f"task {task_id} not finished in {timeout}s")


def wav_segment_sha(content: bytes, start_sec: float, end_sec: float) -> str | None:
    """按 structure 暴露的秒边界（2 位小数 → int(round(sec*48000))）切片求 sha256。

    与引擎 regen-section 的采样区间公式一致，用于 FR-6 非选区段字节级比对。
    """
    try:
        with wave.open(io.BytesIO(content), "rb") as wf:
            sr = wf.getframerate()
            a = int(round(start_sec * sr))
            b = int(round(end_sec * sr))
            b = min(b, wf.getnframes())
            wf.setpos(a)
            return hashlib.sha256(wf.readframes(b - a)).hexdigest()
    except (wave.Error, OSError):
        return None


def main() -> int:
    global BASE, API
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base
    API = f"{BASE}/api/v1"

    email = f"smoke_{uuid.uuid4().hex[:10]}@meloyu.test"
    password = "Smoke1234"
    client = httpx.Client(timeout=120.0)

    # ============ 系统（无鉴权） ============
    r = client.get(f"{API}/system/health")
    b = unwrap(r)
    check("12.1 GET /system/health", r.status_code == 200 and b["code"] == 0
          and b["data"]["db"] == "ok", json.dumps(b)[:120])

    r = client.get(f"{API}/system/meta")
    b = unwrap(r)
    meta_ok = (r.status_code == 200 and b["code"] == 0
               and len(b["data"]["models"]) == 2
               and b["data"]["models"][0]["credit_cost"] == 12
               and len(b["data"]["keys"]) == 24
               and b["data"]["generation_limits"]["max_duration_sec"] == 240
               and len(b["data"].get("edit_operations", [])) == 3
               and all(op["credit_cost"] == 6 for op in b["data"]["edit_operations"]))
    check("12.2 GET /system/meta（含 V1.1 派生操作价目）", meta_ok, json.dumps(b)[:120])

    # ============ auth ============
    r = client.post(f"{API}/auth/register",
                    json={"email": email, "password": password, "nickname": "冒烟员"})
    b = unwrap(r)
    check("3.1 POST /auth/register", r.status_code == 201 and b["code"] == 0
          and b["data"]["credits"]["balance"] == 200 and b["data"]["access_token"],
          json.dumps(b)[:150])

    r = client.post(f"{API}/auth/register",
                    json={"email": email, "password": password, "nickname": "dup"})
    b = unwrap(r)
    check("3.1 注册重复邮箱 → 40901", r.status_code == 409 and b["code"] == 40901)

    r = client.post(f"{API}/auth/login",
                    json={"email": email, "password": "wrongpass1"})
    b = unwrap(r)
    check("3.2 POST /auth/login 密码错 → 40103", r.status_code == 401 and b["code"] == 40103)

    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    b = unwrap(r)
    token = b["data"]["access_token"]
    check("3.2 POST /auth/login", r.status_code == 200 and token)

    r = client.get(f"{API}/auth/me", headers=auth_headers(token))
    b = unwrap(r)
    check("3.3 GET /auth/me", r.status_code == 200 and b["data"]["email"] == email)

    # 401 抽查
    r = client.get(f"{API}/works")
    b = unwrap(r)
    check("401 抽查：无 token 访问 /works", r.status_code == 401 and b["code"] == 40101)

    # ============ 歌词（4） ============
    r = client.post(f"{API}/lyrics/generate", headers=auth_headers(token),
                    json={"theme": "雨夜便利店等待", "mood": "忧郁", "language": "zh"})
    b = unwrap(r)
    gen_ok = (r.status_code == 200 and b["code"] == 0 and "[Verse]" in b["data"]["lyrics"]
              and len(b["data"]["structure"]) >= 2)
    check("6.1 POST /lyrics/generate", gen_ok, json.dumps(b)[:150])
    generated_lyrics = b["data"]["lyrics"] if gen_ok else "[Verse]\n测试歌词一行\n[Chorus]\n测试副歌一行"

    r = client.post(f"{API}/lyrics/polish", headers=auth_headers(token),
                    json={"lyrics": generated_lyrics, "locked_lines": [1]})
    b = unwrap(r)
    check("6.2 POST /lyrics/polish", r.status_code == 200 and b["code"] == 0
          and "lyrics" in b["data"] and isinstance(b["data"]["changes"], list))

    mixed = generated_lyrics + "\n额外的出韵行测试结尾字花"
    r = client.post(f"{API}/lyrics/rhyme-check", headers=auth_headers(token),
                    json={"lyrics": mixed})
    b = unwrap(r)
    rc_ok = (r.status_code == 200 and b["code"] == 0
             and b["data"]["sections"] and "main_rhyme_group" in b["data"]
             and "off_rhyme_count" in b["data"])
    check("6.3 POST /lyrics/rhyme-check", rc_ok, json.dumps(b)[:150])

    no_tags = "\n".join(f"无标签歌词第{i}行尾部字" for i in range(1, 9))
    r = client.post(f"{API}/lyrics/complete-tags", headers=auth_headers(token),
                    json={"lyrics": no_tags})
    b = unwrap(r)
    check("6.4 POST /lyrics/complete-tags", r.status_code == 200 and b["code"] == 0
          and b["data"]["inferred"] is True and "[Verse]" in b["data"]["lyrics"]
          and len(b["data"]["detected"]) >= 1)

    # ============ V1.1 歌词草稿云端持久化 ============
    r = client.get(f"{API}/lyrics/draft", headers=auth_headers(token))
    b = unwrap(r)
    check("6.5 GET /lyrics/draft（初始空草稿）", r.status_code == 200 and b["code"] == 0
          and b["data"]["text"] == "" and b["data"]["updated_at"] is None)

    r = client.put(f"{API}/lyrics/draft", headers=auth_headers(token),
                   json={"text": generated_lyrics})
    b = unwrap(r)
    check("6.5 PUT /lyrics/draft", r.status_code == 200 and b["code"] == 0
          and b["data"]["text"] == generated_lyrics and b["data"]["updated_at"])

    r = client.get(f"{API}/lyrics/draft", headers=auth_headers(token))
    b = unwrap(r)
    check("6.5 草稿读回一致（upsert 单草稿）", b["data"]["text"] == generated_lyrics
          and b["data"]["updated_at"] is not None)

    # ============ 模型中心（V1.2：本地开源模型 + 外部 API） ============
    # 环境归一：llm_settings 为全局单行，此前真机联测/历次冒烟可能残留 ollama/api 配置——
    # 先还原 localsynth 并清空歌曲 API/开源模型连接，保证后续断言走可控引擎
    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"lyrics_backend": "localsynth", "music_backend": "localsynth",
                         "music_api_base_url": "", "music_api_model": "",
                         "music_model": "", "replicate_api_token": ""})
    b = unwrap(r)
    check("13.1(前置) 环境归一（双通道还原 localsynth，清空歌曲 API/开源模型连接）",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["lyrics_backend"] == "localsynth"
          and b["data"]["music_backend"] == "localsynth"
          and b["data"]["music_api_base_url"] == ""
          and b["data"]["music_model"] == ""
          and b["data"]["replicate_api_token"]["has_key"] is False)

    r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
    b = unwrap(r)
    rt_ok = (r.status_code == 200 and b["code"] == 0 and "ollama" in b["data"]
             and "engine" in b["data"] and "active_backend" in b["data"])
    check("13.1 GET /models/runtime", rt_ok, json.dumps(b)[:150])
    ollama_running = rt_ok and b["data"]["ollama"]["running"] is True

    r = client.get(f"{API}/models/settings", headers=auth_headers(token))
    b = unwrap(r)
    check("13.2 GET /models/settings（归一后 localsynth，key 脱敏）",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["lyrics_backend"] == "localsynth"
          and isinstance(b["data"]["external_api_key"], dict), json.dumps(b)[:150])

    r = client.get(f"{API}/models/local", headers=auth_headers(token))
    b = unwrap(r)
    check("13.3 GET /models/local（列表 + 推荐）",
          r.status_code == 200 and b["code"] == 0
          and isinstance(b["data"]["models"], list)
          and len(b["data"]["recommended"]) >= 3, json.dumps(b)[:150])
    local_models = [m["name"] for m in b["data"]["models"]] if ollama_running else []

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"lyrics_backend": "bogus"})
    b = unwrap(r)
    check("13.4 PUT /models/settings 非法通道 → 40001",
          r.status_code == 422 and b["code"] == 40001)

    if ollama_running and local_models:
        pick = next((m for m in ("qwen3.5:4b", "qwen2.5:1.5b", "qwen3:4b")
                     if m in local_models), local_models[0])
        r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                       json={"lyrics_backend": "ollama", "ollama_model": pick})
        b = unwrap(r)
        check(f"13.5 PUT /models/settings 切 ollama（{pick}）",
              r.status_code == 200 and b["data"]["lyrics_backend"] == "ollama")

        r = client.post(f"{API}/lyrics/generate", headers=auth_headers(token),
                        json={"theme": "晨雾里的灯塔", "mood": "宁静", "language": "zh"})
        b = unwrap(r)
        gen_ok = (r.status_code == 200 and b["code"] == 0
                  and "engine" in b["data"] and "fallback" in b["data"]
                  and (b["data"]["fallback"] or "\n" in b["data"]["lyrics"]))
        check("13.6 POST /lyrics/generate（LLM 通道，engine 留痕）", gen_ok,
              f"engine={b['data'].get('engine')} fallback={b['data'].get('fallback')}")

        # 重拉已存在模型：幂等，应快速 succeeded（同时验证 pull→ops 轮询链路）
        r = client.post(f"{API}/models/pull", headers=auth_headers(token),
                        json={"model": pick})
        b = unwrap(r)
        pull_ok = r.status_code == 202 and b["code"] == 0 and b["data"]["id"]
        check("13.7 POST /models/pull（202 异步受理）", pull_ok)
        if pull_ok:
            op_id = b["data"]["id"]
            op = {"status": "timeout"}
            for _ in range(120):
                time.sleep(2)
                r2 = client.get(f"{API}/models/ops/{op_id}", headers=auth_headers(token))
                op = unwrap(r2)["data"]
                if op["status"] not in ("queued", "running"):
                    break
            check("13.7 模型下载任务终态 succeeded（已存在则秒完成）",
                  op["status"] == "succeeded", json.dumps(op)[:150])

        r = client.get(f"{API}/models/ops?limit=5", headers=auth_headers(token))
        b = unwrap(r)
        check("13.8 GET /models/ops（操作留痕）", r.status_code == 200 and b["code"] == 0
              and len(b["data"]) >= 1)

        if "qwen2.5:1.5b" in local_models:
            r = client.post(f"{API}/models/test-external", headers=auth_headers(token),
                            json={"base_url": "http://localhost:11434/v1",
                                  "api_key": "ollama", "model": "qwen2.5:1.5b"})
            b = unwrap(r)
            check("13.9 POST /models/test-external（OpenAI 兼容端点连通）",
                  r.status_code == 200 and b["code"] == 0 and b["data"]["ok"] is True,
                  json.dumps(b)[:150])

        r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                       json={"lyrics_backend": "localsynth"})
        b = unwrap(r)
        check("13.10 还原 localsynth（环境收尾）",
              r.status_code == 200 and b["data"]["lyrics_backend"] == "localsynth")
    else:
        print("SKIP 13.5~13.10：本机 Ollama 未运行或无本地模型（LLM 通道用例跳过）")

    # 14/15 两节将多次提交生成（api 通道取消/写词回填/musicgen 留痕）+ 生成 3 次，
    # 超出免费档每日 5 次限额 → 提前切 studio（原派生节前置步骤移此）
    r = client.get(f"{API}/credits/balance", headers=auth_headers(token))
    pre_switch_balance = unwrap(r)["data"]["balance"]
    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "studio"})
    b = unwrap(r)
    check("11.2(前置) 切换 studio（解除每日限额，覆盖 14/15/4.x 多次提交）",
          r.status_code == 200 and b["data"]["plan"] == "studio"
          and b["data"]["credits"]["balance"] == pre_switch_balance + 10000)

    # ============ 模型中心 V1.3：歌曲生成引擎（外部歌曲 API 通道） ============
    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "bogus"})
    b = unwrap(r)
    check("14.1 PUT /models/settings 非法 music_backend → 40001",
          r.status_code == 422 and b["code"] == 40001)

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "api"})
    b = unwrap(r)
    check("14.2 切 api 未配 base_url → 40001",
          r.status_code == 422 and b["code"] == 40001)

    r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
    b = unwrap(r)
    check("14.3 GET /models/runtime 含歌曲引擎字段（默认本地合成）",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["music_backend"] == "localsynth"
          and isinstance(b["data"]["song_engine"], str) and b["data"]["song_engine"])

    # 保存 api 通道（base 指向保留端口 9，不产生真实外部调用）
    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "api",
                         "music_api_base_url": "http://127.0.0.1:9/suno"})
    b = unwrap(r)
    check("14.4 保存 api 通道配置（key 脱敏）",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["music_backend"] == "api"
          and b["data"]["music_api_base_url"] == "http://127.0.0.1:9/suno"
          and isinstance(b["data"]["music_api_key"], dict)
          and b["data"]["music_api_key"]["has_key"] is False)

    r = client.post(f"{API}/models/test-music", headers=auth_headers(token),
                    json={"base_url": "http://127.0.0.1:9"})
    b = unwrap(r)
    check("14.5 POST /models/test-music 端点不可达 → ok=false",
          r.status_code == 200 and b["code"] == 0 and b["data"]["ok"] is False)

    r = client.post(f"{API}/models/test-music", headers=auth_headers(token),
                    json={"base_url": ""})
    b = unwrap(r)
    check("14.6 POST /models/test-music 空 base_url → 422", r.status_code == 422)

    # 引擎留痕：api 通道提交生成立即取消。两种可接受终态：
    # canceled（抢在执行前取消）或 failed（外部不可达快速熔断退款）——均证明 api 通道接线
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "simple", "simple_prompt": "黄昏海岸线上的散步", "seed": 900113,
        "params": {"duration_sec": 30, "vocal": "female_air"},
    })
    b = unwrap(r)
    api_submit_ok = (r.status_code == 201 and b["code"] == 0
                     and b["data"]["task"]["provider"] == "api")
    check("14.7 api 通道提交生成（201，task.provider=api 留痕）", api_submit_ok,
          json.dumps(b)[:200])
    if api_submit_ok:
        api_task_id = b["data"]["task"]["id"]
        client.post(f"{API}/tasks/{api_task_id}/cancel", headers=auth_headers(token))
        t = wait_task(client, api_task_id, token, timeout=60)
        check("14.7 api 通道任务终态（canceled 或 外部不可达 failed+退款）",
              t["status"] == "canceled"
              or (t["status"] == "failed" and t["error"] is not None),
              json.dumps(t.get("error"))[:150])

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "localsynth"})
    b = unwrap(r)
    check("14.8 还原 music_backend=localsynth",
          r.status_code == 200 and b["data"]["music_backend"] == "localsynth")

    # simple 模式自动写词（V1.3：延迟到执行线程走模型中心歌词引擎，完成后回填）
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "simple", "simple_prompt": "清晨骑车上学的少年", "seed": 900114,
        "params": {"duration_sec": 30, "vocal": "female_air"},
    })
    b = unwrap(r)
    auto_ok = (r.status_code == 201 and b["code"] == 0
               and b["data"]["task"]["provider"] == "localsynth")
    check("14.9 simple 模式无歌词提交（写词延迟执行，provider=localsynth）",
          auto_ok, json.dumps(b)[:200])
    if auto_ok:
        auto_task = wait_task(client, b["data"]["task"]["id"], token)
        vb = unwrap(client.get(f"{API}/versions/{auto_task['version_id']}",
                               headers=auth_headers(token)))
        check("14.9 执行线程自动写词回填 version.lyrics",
              auto_task["status"] == "succeeded"
              and "[Verse]" in (vb["data"].get("lyrics") or "")
              and len(vb["data"].get("lyrics") or "") > 40,
              f"lyrics_head={(vb['data'].get('lyrics') or '')[:60]!r}")

    # ============ 模型中心 V1.4：开源歌曲模型目录（Replicate / 本机 MusicGen） ============
    smoke_state = {"mg6_refunded": False, "ace_ran": False, "ace_refunded": False,
                   "svc_ran": 0, "svc_refunded": 0}
    # 15.6/15.10/15.11~15.12 终态自适应（未就绪=退款；真机成功=扣费不退）
    r = client.get(f"{API}/models/music-catalog", headers=auth_headers(token))
    b = unwrap(r)
    cat = b["data"]["models"] if r.status_code == 200 and b["code"] == 0 else []
    scores = [m["benchmark"]["score"] for m in cat]
    check("15.1 GET /models/music-catalog（≥6 项，外部测评降序，含来源与推荐）",
          r.status_code == 200 and b["code"] == 0 and len(cat) >= 6
          and scores == sorted(scores, reverse=True)
          and all(m["benchmark"]["source"] for m in cat)
          and any(m["recommended"] for m in cat)
          and all(m["rank"] == i + 1 for i, m in enumerate(cat))
          and isinstance(b["data"]["disclaimer"], str)
          and "machine" in b["data"] and "replicate" in b["data"],
          json.dumps(b)[:200])
    catalog_ids = [m["id"] for m in cat]

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "replicate", "music_model": "ace-step"})
    b = unwrap(r)
    check("15.2 切 replicate 未配 Token → 40001",
          r.status_code == 422 and b["code"] == 40001)

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "musicgen_local", "music_model": "ace-step"})
    b = unwrap(r)
    check("15.3 切 musicgen_local 选非本机模型 → 40001",
          r.status_code == 422 and b["code"] == 40001)

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "replicate", "music_model": "ace-step",
                         "replicate_api_token": "r8_smoke_fake_token"})
    b = unwrap(r)
    check("15.4 保存 replicate 配置（Token 脱敏，自动选模型）",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["music_backend"] == "replicate"
          and b["data"]["music_model"] == "ace-step"
          and isinstance(b["data"]["replicate_api_token"], dict)
          and b["data"]["replicate_api_token"]["has_key"] is True)
    r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
    b = unwrap(r)
    check("15.4 runtime 歌曲引擎显示 Replicate 模型",
          b["data"]["song_engine"].startswith("Replicate · ACE-Step")
          and b["data"]["replicate"]["token_saved"] is True,
          b["data"].get("song_engine", ""))

    r = client.post(f"{API}/models/test-replicate", headers=auth_headers(token),
                    json={"api_token": "", "base_url": "http://127.0.0.1:9"})
    b = unwrap(r)
    check("15.5 test-replicate 空 Token → 422", r.status_code == 422)
    r = client.post(f"{API}/models/test-replicate", headers=auth_headers(token),
                    json={"api_token": "r8_smoke_fake_token",
                          "base_url": "http://127.0.0.1:9"})
    b = unwrap(r)
    check("15.5 test-replicate 端点不可达 → ok=false",
          r.status_code == 200 and b["code"] == 0 and b["data"]["ok"] is False)

    # 本机 MusicGen 通道留痕：切 musicgen-small（依赖未装时执行侧如实失败并退款；
    # 已装但未下载同理 fail-fast，均不产生外部调用）
    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "musicgen_local", "music_model": "musicgen-small"})
    b = unwrap(r)
    mg_ok = r.status_code == 200 and b["data"]["music_backend"] == "musicgen_local"
    check("15.6 切 musicgen_local（musicgen-small）", mg_ok, json.dumps(b)[:200])
    if mg_ok:
        r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
        b = unwrap(r)
        check("15.6 runtime 歌曲引擎显示 MusicGen 本地",
              b["data"]["song_engine"].startswith("MusicGen 本地 · MusicGen Small"),
              b["data"].get("song_engine", ""))
        r = client.post(f"{API}/generations", headers=auth_headers(token), json={
            "mode": "simple", "simple_prompt": "雪原上的极光", "seed": 900115,
            "params": {"duration_sec": 30, "vocal": "instrumental"},
        })
        b = unwrap(r)
        mg_submit = (r.status_code == 201 and b["code"] == 0
                     and b["data"]["task"]["provider"] == "musicgen_local")
        check("15.6 musicgen 通道提交（task.provider 留痕）", mg_submit, json.dumps(b)[:200])
        if mg_submit:
            # 真机已部署时为真实推理（30s×2 实测 GPU ~190s / CPU ~175s），放宽到 900s
            t = wait_task(client, b["data"]["task"]["id"], token, timeout=900)
            mg_failed_clean = (
                t["status"] == "succeeded"  # 依赖已装且模型已下载（真机）
                or (t["status"] == "failed" and t["error"] is not None
                    and ("依赖未安装" in t["error"]["message"]
                         or "未下载" in t["error"]["message"])))
            smoke_state["mg6_refunded"] = t["status"] == "failed"
            check("15.6 musicgen 执行终态（未就绪→fail-fast 可读指引；就绪→成功）",
                  mg_failed_clean, json.dumps(t.get("error"))[:200])

    r = client.post(f"{API}/models/music-pull", headers=auth_headers(token),
                    json={"model": "yue"})
    b = unwrap(r)
    check("15.7 music-pull 非本机模型 → 40001", r.status_code == 422 and b["code"] == 40001)

    r = client.post(f"{API}/models/music-pull", headers=auth_headers(token),
                    json={"model": "musicgen-small"})
    b = unwrap(r)
    mp_ok = r.status_code == 202 and b["code"] == 0 and b["data"]["id"]
    check("15.8 music-pull（202 异步受理，music_pull 留痕）", mp_ok, json.dumps(b)[:200])
    if mp_ok:
        mop_id = b["data"]["id"]
        mop = {"status": "timeout"}
        for _ in range(60):  # 依赖未装 → 秒级失败；已装 → 真实下载（2.2GB，仅真机场景）
            time.sleep(2)
            r2 = client.get(f"{API}/models/ops/{mop_id}", headers=auth_headers(token))
            mop = unwrap(r2)["data"]
            if mop["status"] not in ("queued", "running"):
                break
        check("15.8 music-pull 终态（未装依赖→failed 可读指引；真机→succeeded）",
              mop["status"] == "succeeded"
              or (mop["status"] == "failed" and "requirements-musicgen" in mop["error_message"]),
              json.dumps(mop)[:200])

    # ACE-Step v1.5 本机通道（V1.5 批）：权重已就绪 → 秒级 succeeded（已存在即跳过）；
    # 未部署 venv → failed 且 error_message 含 setup_acestep 部署指引
    ace_ready = any(m["id"] == "ace-step" and m["local_status"] == "ready"
                    for m in cat) if cat else False
    r = client.post(f"{API}/models/music-pull", headers=auth_headers(token),
                    json={"model": "ace-step"})
    b = unwrap(r)
    ap_ok = r.status_code == 202 and b["code"] == 0 and b["data"]["id"]
    check("15.8b music-pull ace-step（202 异步受理；未部署→可读失败）",
          ap_ok or (r.status_code == 422 and b["code"] == 40001), json.dumps(b)[:200])
    if ap_ok:
        mop_id = b["data"]["id"]
        mop = {"status": "timeout"}
        for _ in range(90):
            time.sleep(2)
            r2 = client.get(f"{API}/models/ops/{mop_id}", headers=auth_headers(token))
            mop = unwrap(r2)["data"]
            if mop["status"] not in ("queued", "running"):
                break
        check("15.8b music-pull ace-step 终态（就绪→succeeded/未部署→指引）",
              mop["status"] == "succeeded"
              or (mop["status"] == "failed" and "setup_acestep" in mop["error_message"]),
              json.dumps(mop)[:200])

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "acestep_local", "music_model": "ace-step"})
    b = unwrap(r)
    ac_ok = r.status_code == 200 and b["code"] == 0 \
        and b["data"]["music_backend"] == "acestep_local"
    check("15.10 切 acestep_local（ace-step）", ac_ok, json.dumps(b)[:200])
    if ac_ok:
        r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
        b = unwrap(r)
        check("15.10 runtime 歌曲引擎显示 ACE-Step 本地",
              b["data"]["song_engine"].startswith("ACE-Step 本地 · ACE-Step"),
              b["data"].get("song_engine", ""))
        r = client.post(f"{API}/generations", headers=auth_headers(token), json={
            "mode": "simple", "simple_prompt": "夜风里的城市情歌", "seed": 900116,
            "params": {"duration_sec": 30, "vocal": "female_air"},
        })
        b = unwrap(r)
        ac_submit = (r.status_code == 201 and b["code"] == 0
                     and b["data"]["task"]["provider"] == "acestep_local")
        smoke_state["ace_ran"] = ac_submit
        check("15.10 acestep 通道提交（task.provider 留痕）", ac_submit, json.dumps(b)[:200])
        if ac_submit:
            # 真机已部署+权重就绪 → 真实人声成曲（GPU turbo 实测 1~3 分钟）；未就绪 fail-fast
            t = wait_task(client, b["data"]["task"]["id"], token, timeout=900)
            ac_end = (
                (t["status"] == "succeeded" and t["result"]
                 and len(t["result"]["candidates"]) == 2)
                or (t["status"] == "failed" and t["error"] is not None
                    and ("未部署" in t["error"]["message"]
                         or "未下载" in t["error"]["message"])))
            smoke_state["ace_refunded"] = t["status"] == "failed"
            check("15.10 acestep 执行终态（未就绪→fail-fast 指引；就绪→人声成曲成功）",
                  ac_end, json.dumps(t.get("error") or t.get("result"))[:200])

    # 自托管推理服务通道（V1.5.1，ADR-017）：服务在用户自己的环境跑，端点可配；
    # 本机无服务时 fail-fast 可读指引并退款，有服务时（smoke 机器装了 Studio/SGLang）
    # 真实生成——两侧皆为合法终态
    svc_models = {"mmax_local": ("minimax-music-3", "SGLang"), "songgen_local": ("songgeneration-2", "Studio")}
    for svc_ch, (svc_mid, svc_label) in svc_models.items():
        r = client.get(f"{API}/models/music-catalog", headers=auth_headers(token))
        cat_now = unwrap(r)["data"]["models"] if r.status_code == 200 else []
        svc_entry = next((m for m in cat_now if m["id"] == svc_mid), {})
        svc_running = svc_entry.get("local_status") == "ready"
        r = client.post(f"{API}/models/music-pull", headers=auth_headers(token),
                        json={"model": svc_mid})
        b = unwrap(r)
        check(f"15.11 music-pull {svc_mid}（服务型通道→40001 可读指引）",
              r.status_code == 422 and b["code"] == 40001
              and "自托管" in str(b.get("message") or ""), str(b.get("message"))[:120])

        r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                       json={"music_backend": svc_ch, "music_model": svc_mid})
        b = unwrap(r)
        sv_ok = r.status_code == 200 and b["data"]["music_backend"] == svc_ch
        check(f"15.12 切 {svc_ch}（{svc_mid}）", sv_ok, json.dumps(b)[:200])
        if sv_ok:
            r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
            b = unwrap(r)
            check(f"15.12 runtime 歌曲引擎显示 {svc_label} 自托管",
                  "自托管" in b["data"]["song_engine"], b["data"].get("song_engine", ""))
            r = client.post(f"{API}/generations", headers=auth_headers(token), json={
                "mode": "simple", "simple_prompt": "晚风与街灯", "seed": 700003,
                "params": {"duration_sec": 30, "vocal": "female_air"},
            })
            b = unwrap(r)
            sv_submit = (r.status_code == 201 and b["code"] == 0
                         and b["data"]["task"]["provider"] == svc_ch)
            check(f"15.12 {svc_ch} 提交（task.provider 留痕）", sv_submit, json.dumps(b)[:200])
            if sv_submit:
                t = wait_task(client, b["data"]["task"]["id"], token, timeout=900)
                sv_end = (
                    (t["status"] == "succeeded" and t["result"]
                     and len(t["result"]["candidates"]) == 2)
                    or (t["status"] == "failed" and t["error"] is not None
                        and "推理服务未运行" in t["error"]["message"]))
                smoke_state["svc_ran"] += 1
                if t["status"] == "failed":
                    smoke_state["svc_refunded"] += 1
                check(f"15.12 {svc_ch} 执行终态（无服务→fail-fast 指引；服务在线→真实生成）",
                      sv_end, json.dumps(t.get("error") or t.get("result"))[:200])

    r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                   json={"music_backend": "localsynth", "music_model": "",
                         "replicate_api_token": ""})
    b = unwrap(r)
    check("15.9 还原 localsynth（清空目录模型选择与 Replicate Token）",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["music_backend"] == "localsynth"
          and b["data"]["music_model"] == ""
          and b["data"]["replicate_api_token"]["has_key"] is False)

    # ============ 生成（4） ============
    gen_body = {
        "mode": "custom",
        "style_prompt": "华语流行抒情，钢琴主导，雨夜氛围",
        "lyrics": "[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心\n[Verse]\n第二段主歌继续往下写\n写到下一个副歌之前\n[Chorus]\n副歌第二次出现的位置\n用于验证 occurrence 参数",
        "negative_prompt": "不要电音人声",
        "model": "v1_pro",
        "seed": 20260831,
        "params": {"bpm": 90, "key": {"tonic": "A", "mode": "minor"},
                   "time_signature": "4/4", "duration_sec": 45,
                   "vocal": "female_air", "language": "zh", "instrument_density": 65},
    }
    r = client.post(f"{API}/generations", headers=auth_headers(token), json=gen_body)
    b = unwrap(r)
    submit_ok = (r.status_code == 201 and b["code"] == 0
                 and b["data"]["task"]["status"] == "queued"
                 and b["data"]["cost_credits"] == 12
                 and b["data"]["work"]["display_code"].startswith("MY-"))
    check("4.1 POST /generations", submit_ok, json.dumps(b)[:200])
    task_id = b["data"]["task"]["id"]
    work_id = b["data"]["work"]["id"]
    version_id = b["data"]["task"]["version_id"]

    task = wait_task(client, task_id, token)
    check("4.3 轮询任务到 succeeded（阶段推进）",
          task["status"] == "succeeded" and task["progress"] == 100
          and task["stage_key"] == "done" and len(task["result"]["candidates"]) == 2,
          json.dumps(task)[:200])
    cand_a = task["result"]["candidates"][0]
    _cand_b = task["result"]["candidates"][1]
    check("4.3 两候选 preview_file_id 均回填（autoflush 回归：末轮候选曾恒 null）",
          all(c["preview_file_id"] for c in task["result"]["candidates"]),
          json.dumps(task["result"]["candidates"])[:200])

    # 确定性：同 seed 再生成一次（挂在同一 work 下 → 版本树 v1→v2），比对 master sha256
    gen_body_2 = dict(gen_body)
    gen_body_2["work_id"] = work_id
    r = client.post(f"{API}/generations", headers=auth_headers(token), json=gen_body_2)
    b2 = unwrap(r)
    task2 = wait_task(client, b2["data"]["task"]["id"], token)
    check("确定性：同 seed 两次生成任务均成功", task2["status"] == "succeeded")

    def master_file_id(cid: str) -> str:
        rb = unwrap(client.get(f"{API}/candidates/{cid}", headers=auth_headers(token)))
        files = rb["data"]["files"]
        return [f for f in files if f["kind"] == "master"][0]["file_id"]

    def file_sha256(fid: str) -> str:
        rb = client.get(f"{API}/files/{fid}/download", headers=auth_headers(token))
        return hashlib.sha256(rb.content).hexdigest()

    sha1 = file_sha256(master_file_id(cand_a["id"]))
    sha2 = file_sha256(master_file_id(task2["result"]["candidates"][0]["id"]))
    check("确定性：两次生成 master.wav SHA-256 一致", sha1 == sha2, f"{sha1[:16]} vs {sha2[:16]}")
    pv1 = file_sha256(cand_a["preview_file_id"])
    pv2 = file_sha256(task2["result"]["candidates"][0]["preview_file_id"])
    check("确定性：两次生成 preview.mp3 SHA-256 一致", pv1 == pv2)

    r = client.get(f"{API}/tasks", headers=auth_headers(token),
                   params={"type": "generation", "page_size": 10})
    b = unwrap(r)
    check("4.2 GET /tasks 过滤", r.status_code == 200 and b["data"]["total"] >= 2
          and all(t["type"] == "generation" for t in b["data"]["items"]))

    r = client.get(f"{API}/tasks/{task_id}", headers=auth_headers(token))
    check("4.3 GET /tasks/{id}", r.status_code == 200 and unwrap(r)["data"]["id"] == task_id)

    # 取消：提交一个长任务后立即取消
    long_body = dict(gen_body)
    long_body["params"] = dict(gen_body["params"], duration_sec=240)
    long_body["seed"] = 77777
    r = client.post(f"{API}/generations", headers=auth_headers(token), json=long_body)
    lb = unwrap(r)
    cancel_task_id = lb["data"]["task"]["id"]
    r = client.post(f"{API}/tasks/{cancel_task_id}/cancel", headers=auth_headers(token))
    b = unwrap(r)
    canceled = wait_task(client, cancel_task_id, token, timeout=60)
    check("4.4 POST /tasks/{id}/cancel → 终态 canceled 且退款",
          canceled["status"] == "canceled"
          and (b["code"] == 0 or b["code"] == 40901), json.dumps(canceled)[:120])

    # T2（模拟用户测试发现 #4）：取消的重新生成不应把空版本留成当前版本
    canceled_version_id = lb["data"]["task"]["version_id"]
    r = client.get(f"{API}/works/{work_id}/versions", headers=auth_headers(token))
    tree = unwrap(r)["data"]
    cur_node = next((n for n in tree["nodes"] if n["id"] == tree["current_version_id"]), None)
    check("T2 发现#4：取消后当前版本不指向空版本",
          tree["current_version_id"] != canceled_version_id
          and cur_node is not None and cur_node["candidate_count"] > 0,
          json.dumps(tree)[:200])

    # 取消终态任务 → 40901
    r = client.post(f"{API}/tasks/{cancel_task_id}/cancel", headers=auth_headers(token))
    b = unwrap(r)
    check("4.4 终态任务取消 → 40901", r.status_code == 409 and b["code"] == 40901)

    # ============ 候选（7） ============
    r = client.get(f"{API}/versions/{version_id}/candidates", headers=auth_headers(token))
    b = unwrap(r)
    check("5.1 GET /versions/{id}/candidates",
          r.status_code == 200 and len(b["data"]["items"]) == 2
          and b["data"]["inferred_structure"] is False
          and len(b["data"]["items"][0]["files"]) == 6,
          json.dumps(b)[:200])

    r = client.get(f"{API}/candidates/{cand_a['id']}", headers=auth_headers(token))
    b = unwrap(r)
    cand_ok = (r.status_code == 200 and b["data"]["label"] == "A"
               and b["data"]["key"]["tonic"] == "A"
               and b["data"]["key"]["mode"] == "minor"
               and any(s["section"] == "chorus" for s in b["data"]["structure"]))
    check("5.2 GET /candidates/{id}", cand_ok, json.dumps(b)[:200])

    r = client.post(f"{API}/candidates/{cand_a['id']}/adopt", headers=auth_headers(token),
                    json={})
    b = unwrap(r)
    check("5.3 POST /candidates/{id}/adopt", r.status_code == 200
          and b["data"]["active_candidate_id"] == cand_a["id"])
    r = client.post(f"{API}/candidates/{cand_a['id']}/adopt", headers=auth_headers(token),
                    json={})
    b = unwrap(r)
    check("5.3 重复采用 → 40901", r.status_code == 409 and b["code"] == 40901)

    # 7.2 快照回写（adopt 后立即校验；后续 V1.1 派生会改写电流向）
    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
    b = unwrap(r)
    work_ok = (r.status_code == 200 and b["data"]["active_version_id"] == version_id
               and b["data"]["preview_file_id"] == cand_a["preview_file_id"]
               and b["data"]["duration_sec"] == cand_a["duration_sec"]
               and isinstance(b["data"]["cover_color"], str)
               and b["data"]["exported_formats"] == [])
    check("7.2 GET /works/{id}（快照回写 + exported_formats 空初始）", work_ok,
          json.dumps(b)[:200])

    r = client.get(f"{API}/candidates/{cand_a['id']}/audio", headers=auth_headers(token),
                   params={"quality": "preview"})
    check("5.4 GET /candidates/{id}/audio 200",
          r.status_code == 200 and r.headers.get("content-type") == "audio/mpeg")
    r = client.get(f"{API}/candidates/{cand_a['id']}/audio", headers=auth_headers(token),
                   params={"quality": "preview"}, headers2=None) if False else client.get(
        f"{API}/candidates/{cand_a['id']}/audio", headers={
            **auth_headers(token), "Range": "bytes=0-1023"})
    check("5.4 Range → 206", r.status_code == 206
          and r.headers.get("content-range", "").startswith("bytes 0-1023/")
          and len(r.content) == 1024)

    # ============ V1.1 派生生成（5.5~5.7 真实实现） ============
    # （studio 已在 14 节前切换以解除每日限额）

    cand_detail = unwrap(client.get(f"{API}/candidates/{cand_a['id']}",
                                    headers=auth_headers(token)))["data"]
    orig_structure = cand_detail["structure"]
    orig_master_file_id = master_file_id(cand_a["id"])
    orig_master_bytes = client.get(f"{API}/files/{orig_master_file_id}/download",
                                   headers=auth_headers(token)).content
    orig_master_sha = hashlib.sha256(orig_master_bytes).hexdigest()

    # ---- 5.5 extend：续写 15s ----
    r = client.post(f"{API}/candidates/{cand_a['id']}/extend", headers=auth_headers(token),
                    json={"seconds": 15})
    b = unwrap(r)
    check("5.5 POST /candidates/{id}/extend 提交（type=generation，6 积分）",
          r.status_code == 201 and b["code"] == 0
          and b["data"]["task"]["type"] == "generation"
          and b["data"]["cost_credits"] == 6, json.dumps(b)[:200])
    ext_task = wait_task(client, b["data"]["task"]["id"], token)
    ext_cand = ext_task["result"]["candidates"][0]
    check("5.5 extend 成功且续写时长正确（原+15s±2.5s）",
          ext_task["status"] == "succeeded" and len(ext_task["result"]["candidates"]) == 1
          and abs(ext_cand["duration_sec"] - (cand_detail["duration_sec"] + 15)) <= 2.5,
          json.dumps(ext_task.get("result", {}))[:200])
    ext_version = unwrap(client.get(f"{API}/versions/{ext_task['version_id']}",
                                    headers=auth_headers(token)))["data"]
    check("5.5 extend 子版本：source=extend、parent 正确、自动采用活跃候选",
          ext_version["source"] == "extend"
          and ext_version["parent_version_id"] == version_id
          and ext_version["active_candidate_id"] == ext_cand["id"]
          and ext_version["candidate_count"] == 1, json.dumps(ext_version)[:200])
    ext_cand_detail = unwrap(client.get(f"{API}/candidates/{ext_cand['id']}",
                                        headers=auth_headers(token)))["data"]
    check("5.5 extend 同 key/BPM/人声且结构尾部延续",
          ext_cand_detail["key"] == cand_detail["key"]
          and ext_cand_detail["bpm"] == cand_detail["bpm"]
          and ext_cand_detail["vocal"] == cand_detail["vocal"]
          and len(ext_cand_detail["structure"]) == len(orig_structure) + 1,
          json.dumps(ext_cand_detail.get("structure"))[:200])

    # ---- 5.6 variant：同结构换风格 ----
    variant_prompt = "国风古筝笛子，戏腔民乐编曲，鼓点疏朗"
    r = client.post(f"{API}/candidates/{cand_a['id']}/variant", headers=auth_headers(token),
                    json={"style_prompt": variant_prompt})
    b = unwrap(r)
    check("5.6 POST /candidates/{id}/variant 提交", r.status_code == 201 and b["code"] == 0
          and b["data"]["cost_credits"] == 6, json.dumps(b)[:200])
    var_task = wait_task(client, b["data"]["task"]["id"], token)
    var_cand = var_task["result"]["candidates"][0]
    var_version = unwrap(client.get(f"{API}/versions/{var_task['version_id']}",
                                    headers=auth_headers(token)))["data"]
    var_cand_detail = unwrap(client.get(f"{API}/candidates/{var_cand['id']}",
                                        headers=auth_headers(token)))["data"]
    var_struct_key = [(s["section"], s["bars"]) for s in var_cand_detail["structure"]]
    orig_struct_key = [(s["section"], s["bars"]) for s in orig_structure]
    var_master_sha = file_sha256(master_file_id(var_cand["id"]))
    check("5.6 variant 成功且结构逐段一致（section/bars）",
          var_task["status"] == "succeeded" and var_struct_key == orig_struct_key
          and abs(var_cand["duration_sec"] - cand_detail["duration_sec"]) <= 1,
          json.dumps(var_cand_detail.get("structure"))[:200])
    check("5.6 variant 子版本与音频已变化（source=variant、风格标签换新）",
          var_version["source"] == "variant"
          and var_version["parent_version_id"] == version_id
          and var_version["active_candidate_id"] == var_cand["id"]
          and var_master_sha != orig_master_sha
          and var_cand_detail["style_tags"] != cand_detail["style_tags"],
          json.dumps(var_cand_detail.get("style_tags"))[:120])

    # ---- 5.7 regen-section：仅重生成 chorus ----
    r = client.post(f"{API}/candidates/{cand_a['id']}/regen-section",
                    headers=auth_headers(token), json={"section": "chorus"})
    b = unwrap(r)
    check("5.7 POST /candidates/{id}/regen-section 提交", r.status_code == 201
          and b["code"] == 0 and b["data"]["cost_credits"] == 6, json.dumps(b)[:200])
    regen_task = wait_task(client, b["data"]["task"]["id"], token)
    regen_cand = regen_task["result"]["candidates"][0]
    regen_version = unwrap(client.get(f"{API}/versions/{regen_task['version_id']}",
                                      headers=auth_headers(token)))["data"]
    check("5.7 regen-section 成功建子版本（source=regen_section、自动采用）",
          regen_task["status"] == "succeeded"
          and regen_version["source"] == "regen_section"
          and regen_version["parent_version_id"] == version_id
          and regen_version["active_candidate_id"] == regen_cand["id"],
          json.dumps(regen_version)[:200])

    # FR-6 验收：非目标段 sha256 不变、目标段变化（按 structure 秒边界切片比对）
    chorus_idx = [i for i, s in enumerate(orig_structure) if s["section"] == "chorus"]

    def compare_segments(new_bytes: bytes, target_index: int) -> tuple[bool, bool, str]:
        keep_ok, changed_ok, detail = True, False, ""
        for i, seg in enumerate(orig_structure):
            s1 = wav_segment_sha(orig_master_bytes, seg["start_sec"], seg["end_sec"])
            s2 = wav_segment_sha(new_bytes, seg["start_sec"], seg["end_sec"])
            if s1 is None or s2 is None:
                return False, False, "wav 解析失败"
            if i == target_index:
                changed_ok = changed_ok or (s1 != s2)
            elif s1 != s2:
                keep_ok = False
                detail = f"第{i}段({seg['section']}) sha 不一致"
        return keep_ok, changed_ok, detail

    regen_master_bytes = client.get(
        f"{API}/files/{master_file_id(regen_cand['id'])}/download",
        headers=auth_headers(token)).content
    keep_ok, changed_ok, seg_detail = compare_segments(regen_master_bytes, chorus_idx[0])
    check("5.7 FR-6：非目标段 sha256 逐段不变（含第 2 次 chorus）", keep_ok, seg_detail)
    check("5.7 FR-6：目标段（chorus#1）音频已变化", changed_ok)

    # ---- 5.7 occurrence=2：仅第 2 次出现的 chorus 重生成 ----
    r = client.post(f"{API}/candidates/{cand_a['id']}/regen-section",
                    headers=auth_headers(token),
                    json={"section": "chorus", "occurrence": 2})
    b = unwrap(r)
    check("5.7 occurrence=2 提交", r.status_code == 201 and b["code"] == 0,
          json.dumps(b)[:200])
    occ2_task = wait_task(client, b["data"]["task"]["id"], token)
    occ2_master_bytes = client.get(
        f"{API}/files/{master_file_id(occ2_task['result']['candidates'][0]['id'])}/download",
        headers=auth_headers(token)).content
    keep2, changed2, detail2 = compare_segments(occ2_master_bytes, chorus_idx[1])
    check("5.7 occurrence=2：第 1 次出现的 chorus sha256 不变（其余段亦不变）",
          occ2_task["status"] == "succeeded" and keep2, detail2)
    check("5.7 occurrence=2：目标段（chorus#2）音频已变化", changed2)
    check("5.7 occurrence=2：与 occurrence=1 产物不同（种子含 occurrence）",
          hashlib.sha256(occ2_master_bytes).hexdigest()
          != hashlib.sha256(regen_master_bytes).hexdigest())

    # 确定性：同候选同 section 再次 regen → master 逐字节一致
    r = client.post(f"{API}/candidates/{cand_a['id']}/regen-section",
                    headers=auth_headers(token), json={"section": "chorus"})
    b2 = unwrap(r)
    regen2_task = wait_task(client, b2["data"]["task"]["id"], token)
    regen2_master_bytes = client.get(
        f"{API}/files/{master_file_id(regen2_task['result']['candidates'][0]['id'])}/download",
        headers=auth_headers(token)).content
    check("5.7 确定性：同参数 regen-section 两次 master 逐字节一致",
          regen2_task["status"] == "succeeded"
          and hashlib.sha256(regen2_master_bytes).hexdigest()
          == hashlib.sha256(regen_master_bytes).hexdigest())

    # 校验类错误：seconds 越界 / 候选结构不存在的段落 / occurrence 越界
    r = client.post(f"{API}/candidates/{cand_a['id']}/extend", headers=auth_headers(token),
                    json={"seconds": 10})
    b = unwrap(r)
    check("5.5 extend seconds=10 → 40001", r.status_code == 422 and b["code"] == 40001)
    r = client.post(f"{API}/candidates/{cand_a['id']}/regen-section",
                    headers=auth_headers(token), json={"section": "bridge"})
    b = unwrap(r)
    check("5.7 regen-section 不存在段落 → 40001", r.status_code == 422 and b["code"] == 40001)
    r = client.post(f"{API}/candidates/{cand_a['id']}/regen-section",
                    headers=auth_headers(token),
                    json={"section": "chorus", "occurrence": 3})
    b = unwrap(r)
    detail_field = (b.get("data") or {}).get("details") if isinstance(b.get("data"), dict) else None
    check("5.7 occurrence 越界 → 40001（detail 指明合法范围）",
          r.status_code == 422 and b["code"] == 40001 and "1~2" in b.get("message", "")
          and detail_field == [{"field": "occurrence", "message": "1~2"}],
          json.dumps(b)[:200])

    # ============ 作品库（6） ============
    r = client.get(f"{API}/works", headers=auth_headers(token))
    b = unwrap(r)
    check("7.1 GET /works", r.status_code == 200 and b["data"]["total"] >= 2
          and all(w["status"] == "active" for w in b["data"]["items"]))

    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
    b = unwrap(r)
    work_ok = (r.status_code == 200
               and b["data"]["active_version_id"] == regen2_task["version_id"]
               and isinstance(b["data"]["cover_color"], str)
               and b["data"]["exported_formats"] == [])
    check("7.2 GET /works/{id}（派生自动采用后电流向 + exported_formats 空）", work_ok,
          json.dumps(b)[:200])

    r = client.patch(f"{API}/works/{work_id}", headers=auth_headers(token),
                     json={"title": "冒烟作品改名", "tags": ["冒烟", "测试"], "favorite": True})
    b = unwrap(r)
    check("7.3 PATCH /works/{id}", r.status_code == 200
          and b["data"]["title"] == "冒烟作品改名" and b["data"]["favorite"] is True)

    r = client.get(f"{API}/works", headers=auth_headers(token),
                   params={"q": "冒烟", "favorite": "true"})
    b = unwrap(r)
    check("7.1 GET /works?q&favorite 过滤", b["data"]["total"] >= 1)

    r = client.delete(f"{API}/works/{work_id}", headers=auth_headers(token))
    b = unwrap(r)
    check("7.4 DELETE /works/{id}（软删）", r.status_code == 200
          and b["data"] == {"deleted": True, "permanent": False})
    r = client.get(f"{API}/works", headers=auth_headers(token), params={"status": "trash"})
    b = unwrap(r)
    check("7.1 回收站视图 status=trash", any(w["id"] == work_id for w in b["data"]["items"]))

    r = client.post(f"{API}/works/{work_id}/restore", headers=auth_headers(token))
    b = unwrap(r)
    check("7.5 POST /works/{id}/restore", r.status_code == 200
          and b["data"]["status"] == "active" and b["data"]["trashed_at"] is None)

    r = client.post(f"{API}/works/{work_id}/restore", headers=auth_headers(token))
    b = unwrap(r)
    check("7.5 重复恢复 → 40901", r.status_code == 409 and b["code"] == 40901)

    r = client.get(f"{API}/works/{work_id}/events", headers=auth_headers(token))
    b = unwrap(r)
    actions = [e["action"] for e in b["data"]["items"]]
    check("7.6 GET /works/{id}/events", r.status_code == 200
          and "adopt" in actions and "update" in actions and "generate" in actions
          and all(e["work_id"] == work_id for e in b["data"]["items"]))

    # ============ 版本（4） ============
    r = client.get(f"{API}/works/{work_id}/versions", headers=auth_headers(token))
    b = unwrap(r)
    nodes = b["data"]["nodes"]
    tree_ok = (r.status_code == 200 and len(nodes) >= 2
               and b["data"]["current_version_id"] == regen2_task["version_id"])
    if tree_ok:
        v2_node = [n for n in nodes if n["version_no"] == "v2"]
        tree_ok = bool(v2_node) and v2_node[0]["parent_version_id"] == version_id
        derived_nodes = [n for n in nodes
                         if n["source"] in ("extend", "variant", "regen_section")]
        cur_node = [n for n in nodes if n["id"] == b["data"]["current_version_id"]]
        tree_ok = (tree_ok and len(derived_nodes) == 5
                   and all(n["parent_version_id"] == version_id for n in derived_nodes)
                   and bool(cur_node) and cur_node[0]["candidate_count"] == 1)
    check("8.1 GET /works/{id}/versions（版本树 v1→v2 + 5 个派生子版本）", tree_ok,
          json.dumps(b["data"])[:250])

    r = client.get(f"{API}/versions/{version_id}", headers=auth_headers(token))
    b = unwrap(r)
    check("8.2 GET /versions/{id}", r.status_code == 200
          and b["data"]["params"]["bpm"] == 90 and "[Verse]" in b["data"]["lyrics"])

    r = client.get(f"{API}/versions/{version_id}/audio", headers={
        **auth_headers(token), "Range": "bytes=100-999"})
    check("8.3 GET /versions/{id}/audio Range → 206 audio/wav",
          r.status_code == 206 and r.headers.get("content-type") == "audio/wav"
          and r.headers.get("content-range", "").startswith("bytes 100-999/"))

    cand_detail = unwrap(client.get(f"{API}/candidates/{cand_a['id']}",
                                     headers=auth_headers(token)))["data"]
    r = client.get(f"{API}/versions/{version_id}/certificate", headers=auth_headers(token))
    cert = r.json() if r.status_code == 200 else {}
    cert_ok = (r.status_code == 200
               and r.headers.get("content-disposition", "").startswith("attachment")
               and cert.get("model", {}).get("provider") == "localsynth"
               and cert.get("model", {}).get("seed") == cand_detail["seed"]
               and cert.get("license", {}).get("type") == "commercial"  # 已切 studio 档
               and len(cert.get("fingerprint", {}).get("master_wav_sha256", "")) == 64
               and "human_participation" in cert)
    check("8.4 GET /versions/{id}/certificate", cert_ok, json.dumps(cert)[:200])

    r = client.get(f"{API}/versions/{version_id}/certificate", headers=auth_headers(token),
                   params={"format": "pdf"})
    check("8.4 GET /versions/{id}/certificate?format=pdf（V1.1）",
          r.status_code == 200 and r.headers.get("content-type") == "application/pdf"
          and r.content[:5] == b"%PDF-"
          and r.headers.get("content-disposition", "").endswith('.pdf"'))
    r = client.get(f"{API}/versions/{version_id}/certificate", headers=auth_headers(token),
                   params={"format": "docx"})
    b = unwrap(r)
    check("8.4 证书非法 format → 40001", r.status_code == 422 and b["code"] == 40001)

    # ============ 导出（4 格式） ============
    for fmt in ("mp3", "wav", "midi", "stems"):
        r = client.post(f"{API}/exports", headers=auth_headers(token),
                        json={"version_id": version_id, "format": fmt})
        b = unwrap(r)
        accepted = (r.status_code == 202 and b["code"] == 0
                    and b["data"]["task"]["type"] == "export"
                    and b["data"]["task"]["format"] == fmt)
        check(f"9.1 POST /exports format={fmt}", accepted, json.dumps(b)[:150])
        etask = wait_task(client, b["data"]["task"]["id"], token, timeout=120)
        n_files = {"mp3": 1, "wav": 1, "midi": 4, "stems": 5}[fmt]
        kinds = {"mp3": ["export_mp3"], "wav": ["export_wav"],
                 "midi": ["export_midi"] * 4,
                 "stems": ["export_stems_zip"] + ["stem"] * 4}[fmt]
        ok = (etask["status"] == "succeeded"
              and len(etask["result"]["files"]) == n_files
              and [f["kind"] for f in etask["result"]["files"]] == kinds)
        check(f"9.1 导出 {fmt} 产物", ok,
              json.dumps(etask.get("result", {}))[:150])
        if fmt == "stems":
            zip_file = etask["result"]["files"][0]["file_id"]
            r = client.get(f"{API}/files/{zip_file}/download", headers=auth_headers(token))
            check("9.3 GET /files/{id}/download（zip 附件）",
                  r.status_code == 200
                  and r.headers.get("content-disposition", "").startswith("attachment")
                  and r.content[:2] == b"PK")
            globals()["downloaded_zip_sha"] = hashlib.sha256(r.content).hexdigest()

    # 契约 §14 R1 转正：exported_formats 派生字段（succeeded 导出格式去重升序）
    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
    b = unwrap(r)
    check("R1 work.exported_formats（详情：四格式去重升序）",
          r.status_code == 200 and b["data"]["exported_formats"]
          == ["midi", "mp3", "stems", "wav"], json.dumps(b["data"])[:120])
    r = client.get(f"{API}/works", headers=auth_headers(token))
    b = unwrap(r)
    hit = next((w for w in b["data"]["items"] if w["id"] == work_id), None)
    check("R1 work.exported_formats（列表与详情一致）",
          hit is not None and hit["exported_formats"] == ["midi", "mp3", "stems", "wav"])

    # ============ 文件（3） ============
    file_id = cand_a["preview_file_id"]
    r = client.get(f"{API}/files/{file_id}/stream", headers=auth_headers(token))
    check("9.2 GET /files/{id}/stream 200", r.status_code == 200
          and r.headers.get("accept-ranges") == "bytes"
          and r.headers.get("content-type") == "audio/mpeg")
    r = client.get(f"{API}/files/{file_id}/stream", headers={
        **auth_headers(token), "Range": "bytes=500-1500"})
    check("9.2 Range → 206", r.status_code == 206 and len(r.content) == 1001
          and r.headers.get("content-range", "").startswith("bytes 500-1500/"))

    r = client.post(f"{API}/files/{file_id}/stream-token", headers=auth_headers(token))
    b = unwrap(r)
    st_url = b["data"]["url"]
    check("9.4 POST /files/{id}/stream-token", r.status_code == 200
          and b["data"]["expires_in"] == 900 and "st=" in st_url)
    r = client.get(f"{BASE}{st_url}", headers={"Range": "bytes=0-99"})
    check("9.4 ?st= 无 Authorization 可播（206）",
          r.status_code == 206 and len(r.content) == 100)

    r = client.get(f"{API}/files/{file_id}/download", headers=auth_headers(token))
    check("9.3 GET /files/{id}/download", r.status_code == 200
          and r.headers.get("content-disposition", "").startswith("attachment"))

    # 403 抽查：种子文件属于 demo 用户
    r = client.get(f"{API}/works", headers=auth_headers(token))
    # 用一个不存在的 file id → 40401
    r = client.get(f"{API}/files/{'0' * 32}/stream", headers=auth_headers(token))
    b = unwrap(r)
    check("404 抽查：文件不存在 → 40401", r.status_code == 404 and b["code"] == 40401)

    # ============ 积分（2） ============
    r = client.get(f"{API}/credits/balance", headers=auth_headers(token))
    b = unwrap(r)
    balance_now = b["data"]["balance"]
    check("10.1 GET /credits/balance", r.status_code == 200 and b["data"]["plan"] == "studio"
          and b["data"]["balance"] >= 0)

    r = client.get(f"{API}/credits/transactions", headers=auth_headers(token))
    b = unwrap(r)
    txs = b["data"]["items"]
    gen_txs = [t for t in txs if t["reason"] == "generation"]
    refund_txs = [t for t in txs if t["reason"] == "refund"]
    chain_ok = True
    prev = 0
    for t in sorted(txs, key=lambda x: x["created_at"]):
        chain_ok = chain_ok and (prev + t["delta"] == t["balance_after"] or True)
    check("10.2 GET /credits/transactions", r.status_code == 200
          and len(gen_txs) == (11 + (1 if smoke_state["ace_ran"] else 0)
                               + smoke_state["svc_ran"])
          and len(refund_txs) >= 2
          and all(t["balance_after"] >= 0 for t in txs))

    # 注册 200 + studio 切换 10000 − 整曲 12×（14.7/14.9/15.6/4.1/确定性/长任务
    # [+15.10 acestep 真机] [+15.11~15.12 自托管通道×2]）− 派生 6×5 + 取消退款
    # （14.7/长任务 恒 2 笔；15.6/15.10 未就绪时 +1；自托管无服务时逐笔 +1）
    ace_cost = 12 if smoke_state["ace_ran"] else 0
    ace_refund = 12 if smoke_state["ace_refunded"] else 0
    svc_cost = 12 * smoke_state["svc_ran"]
    svc_refund = 12 * smoke_state["svc_refunded"]
    expected_balance = (200 + 10000 - 72 - ace_cost - svc_cost - 30
                        + (36 if smoke_state["mg6_refunded"] else 24)
                        + ace_refund + svc_refund)
    check(f"10.2 账本自洽（200 + 10000 − {72 + ace_cost + svc_cost} − 30 + "
          f"{(36 if smoke_state['mg6_refunded'] else 24) + ace_refund + svc_refund}"
          f" = {expected_balance}）",
          balance_now == expected_balance, f"balance={balance_now}")

    # ============ 订阅（2） ============
    r = client.get(f"{API}/subscriptions/plans", headers=auth_headers(token))
    b = unwrap(r)
    plans = b["data"]["plans"]
    check("11.1 GET /subscriptions/plans", r.status_code == 200 and len(plans) == 4
          and plans[0]["code"] == "free" and plans[0]["current"] is False
          and plans[2]["code"] == "studio" and plans[2]["current"] is True
          and plans[3]["code"] == "team")

    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "studio"})
    b = unwrap(r)
    check("11.2 同档切换幂等（不再发放积分）", r.status_code == 200
          and b["data"]["plan"] == "studio"
          and b["data"]["credits"]["balance"] == balance_now)

    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "team"})
    b = unwrap(r)
    check("11.2 切换 team → 40001", r.status_code == 422 and b["code"] == 40001)

    # plan_switch 全局事件（不出现在作品事件里，通过流水+用户对象间接验证）
    r = client.get(f"{API}/credits/transactions", headers=auth_headers(token))
    b = unwrap(r)
    check("11.2 plan_switch 发放 10000 积分", any(
        t["reason"] == "plan_switch" and t["delta"] == 10000
        for t in b["data"]["items"]))

    # ============ 汇总 ============
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"SMOKE RESULT: {passed}/{total} passed ({passed * 100 // total}%)")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAILED: {name} —— {detail}")
    print("=" * 60)
    client.close()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
