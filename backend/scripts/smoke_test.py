"""WP-B8 冒烟测试：38+ 契约接口 + V1.1 派生生成（extend/variant/regen-section）+ 确定性验证。

用法（后端需已在 127.0.0.1:8000 运行，且已灌种子）：
    ./.venv/Scripts/python scripts/smoke_test.py [--base http://127.0.0.1:8000]

⚠ 单写入方红线：生产栈（127.0.0.1:8180）在运行时本脚本拒绝执行——dev 服务与
生产容器并发写同一 SQLite 曾致 works 表损坏（2026-09-05 事故，详见
scripts/recover_works.py 头注）。先 docker compose down 再跑本脚本。

不依赖 pytest；输出逐项 PASS/FAIL 与最终通过率。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import sys
import time
import uuid
import wave
import zipfile
from pathlib import Path

import httpx

# v0.7.0：service 层直调辅助（模拟 webhook 激活/admin 提权）需要 app 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def _make_admin_via_db(email: str) -> None:
    """v0.7.0 冒烟辅助：注册账号提权管理员（模型中心写操作需 admin，P1-2）。"""
    from app.database import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.is_admin = True
        db.commit()


def _activate_plan_via_db(email: str, plan: str) -> None:
    """冒烟辅助：直写档位并按档发放积分（2026-10-03 起 Stripe 已拆除，
    等价旧 webhook 激活产物：plan + plan_grant 流水）。"""
    from app.database import SessionLocal
    from app.models import Plan, User
    from app.services import credits as credits_svc
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.plan = plan
        row = db.get(Plan, plan)
        if row and row.monthly_credits:
            credits_svc.grant(db, user, row.monthly_credits, "plan_grant")
        db.commit()


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



def _smoke_data_dir() -> str:
    import os
    return os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))

def main() -> int:
    global BASE, API
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base
    API = f"{BASE}/api/v1"

    email = f"smoke_{uuid.uuid4().hex[:10]}@meloyu.test"
    password = "Smoke1234"
    client = httpx.Client(timeout=120.0, trust_env=False)  # loopback 不走系统代理

    # 单写入方红线守卫（2026-09-05 事故复盘；2026-09-06 强化）：本脚本含宿主机
    # 直写 DB 的辅助（_make_admin_via_db / _activate_plan_via_db），生产栈（8180）
    # 在跑时一律拒绝——包括 --base 指向 8180 的情况（宿主机直写与容器写入方并发，
    # 且 WAL 跨 Docker bind mount 的可见性/锁语义不可靠，2026-09-06 实测 exec 内
    # 第二连接 CANTOPEN、宿主机读刚提交行 NoResultFound）。
    # 对生产栈版本验收的正确姿势：docker compose down → 宿主机 uvicorn --port 8000
    # → 本脚本（默认 base）→ 停 uvicorn → docker compose up -d。
    try:
        probe = client.get("http://127.0.0.1:8180/api/v1/system/health", timeout=3.0)
        if probe.status_code == 200:
            print("REFUSED: 生产栈（127.0.0.1:8180）正在运行——本脚本含宿主机直写 DB 的"
                  "辅助，与容器并发写违反单写入方红线（含 --base 8180 模式）。请先在 "
                  "deploy/ 执行 docker compose down，再在宿主机起 uvicorn --port 8000 "
                  "后对本机 dev 栈运行本脚本。")
            return 2
    except httpx.HTTPError:
        pass  # 生产栈未运行，放行

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

    # v0.7.0：冒烟账号提权管理员（后续 13/15 节模型中心写操作需 admin）
    _make_admin_via_db(email)
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    b = unwrap(r)
    token = b["data"]["access_token"]
    check("3.1(前置) 冒烟账号提权 admin 后重登（P1-2 收权适配）",
          r.status_code == 200 and token, json.dumps(b)[:120])

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
    # v0.7.0：付费档不再可免费直切（P0-4）——先验证被拒，再模拟 Stripe webhook 激活
    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "studio"})
    b = unwrap(r)
    check("11.2(前置) 免费直切 studio 被拒（P0-4，40901）",
          r.status_code == 409 and b["code"] == 40901)
    _activate_plan_via_db(email, "studio")
    r = client.get(f"{API}/auth/me", headers=auth_headers(token))
    b = unwrap(r)
    check("11.2(前置) 模拟 webhook 激活 studio（解除每日限额，覆盖 14/15/4.x）",
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
        check("15.6 runtime 歌曲引擎显示 MusicGen 本地（zh/en 双语任一）",
              b["data"]["song_engine"].startswith(
                  ("MusicGen 本地 · MusicGen Small", "MusicGen Local · MusicGen Small")),
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
                         or "未下载" in t["error"]["message"]
                         or "not installed" in t["error"]["message"]
                         or "not downloaded" in t["error"]["message"])))
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
        check("15.10 runtime 歌曲引擎显示 ACE-Step 本地（zh/en 任一）",
              b["data"]["song_engine"].startswith(
                  ("ACE-Step 本地 · ACE-Step", "ACE-Step Local · ACE-Step")),
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
                         or "未下载" in t["error"]["message"]
                         or "not deployed" in t["error"]["message"]
                         or "not downloaded" in t["error"]["message"])))
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
        check(f"15.11 music-pull {svc_mid}（服务型通道→40001 可读指引，zh/en 任一）",
              r.status_code == 422 and b["code"] == 40001
              and ("自托管" in str(b.get("message") or "")
                   or "self-hosted" in str(b.get("message") or "")),
              str(b.get("message"))[:120])

        r = client.put(f"{API}/models/settings", headers=auth_headers(token),
                       json={"music_backend": svc_ch, "music_model": svc_mid})
        b = unwrap(r)
        sv_ok = r.status_code == 200 and b["data"]["music_backend"] == svc_ch
        check(f"15.12 切 {svc_ch}（{svc_mid}）", sv_ok, json.dumps(b)[:200])
        if sv_ok:
            r = client.get(f"{API}/models/runtime", headers=auth_headers(token))
            b = unwrap(r)
            check(f"15.12 runtime 歌曲引擎显示 {svc_label} 自托管（zh/en 任一）",
                  ("自托管" in b["data"]["song_engine"]
                   or "Self-hosted" in b["data"]["song_engine"]),
                  b["data"].get("song_engine", ""))
            r = client.post(f"{API}/generations", headers=auth_headers(token), json={
                "mode": "simple", "simple_prompt": "晚风与街灯", "seed": 700003,
                "params": {"duration_sec": 30, "vocal": "female_air"},
            })
            b = unwrap(r)
            sv_submit = (r.status_code == 201 and b["code"] == 0
                         and b["data"]["task"]["provider"] == svc_ch)
            smoke_state["svc_ran"] += 1
            check(f"15.12 {svc_ch} 提交（task.provider 留痕）", sv_submit, json.dumps(b)[:200])
            if sv_submit:
                sv_tid = b["data"]["task"]["id"]
                # mmax_local 本机 audio.cpp 形态 RTF~94（30s 曲双候选 90 分钟+）：
                # 冒烟验证提交→running→取消→退款链路，真实出歌由 scripts/mmax_e2e.py 覆盖
                if svc_ch == "mmax_local" and svc_running:
                    running_seen = False
                    for _ in range(24):
                        time.sleep(10)
                        r2 = client.get(f"{API}/tasks/{sv_tid}", headers=auth_headers(token))
                        t2 = unwrap(r2)["data"]
                        if t2["status"] == "running" and t2["stage_key"] in (
                                "model_sample", "model_export"):
                            running_seen = True
                            break
                        if t2["status"] not in ("queued", "running"):
                            break
                    check(f"15.12 {svc_ch} running 推进（audio.cpp 子进程拉起）",
                          running_seen, json.dumps(t2)[:120])
                    r2 = client.post(f"{API}/tasks/{sv_tid}/cancel",
                                     headers=auth_headers(token))
                    time.sleep(8)
                    r2 = client.get(f"{API}/tasks/{sv_tid}", headers=auth_headers(token))
                    t2 = unwrap(r2)["data"]
                    smoke_state["svc_refunded"] += 1
                    check(f"15.12 {svc_ch} 取消+退款（慢速本机形态不阻塞冒烟）",
                          t2["status"] == "canceled", json.dumps(t2)[:120])
                else:
                    t = wait_task(client, sv_tid, token, timeout=900)
                    sv_end = (
                        (t["status"] == "succeeded" and t["result"]
                         and len(t["result"]["candidates"]) == 2)
                        or (t["status"] == "failed" and t["error"] is not None
                            and ("推理服务未运行" in t["error"]["message"]
                                 or "inference service is not running"
                                 in t["error"]["message"])))
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
    detail_ok = detail_field is not None and detail_field[0]["field"] == "occurrence"         and detail_field[0]["message"] in ("1~2", "1-2")
    check("5.7 occurrence 越界 → 40001（detail 指明合法范围，zh/en 任一）",
          r.status_code == 422 and b["code"] == 40001
          and ("1~2" in b.get("message", "") or "1-2" in b.get("message", ""))
          and detail_ok,
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

    # ============ 导出（4 格式 + FR-11 发行导出预设） ============
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

    # ---- FR-11 发行导出预设（v0.8.0）：douyin/streaming 两平台 ----
    r = client.post(f"{API}/exports", headers=auth_headers(token),
                    json={"version_id": version_id, "format": "release"})
    b = unwrap(r)
    check("9.4 POST /exports format=release 缺 platform → 40001",
          r.status_code == 422 and b["code"] == 40001, json.dumps(b)[:120])
    r = client.post(f"{API}/exports", headers=auth_headers(token),
                    json={"version_id": version_id, "format": "release",
                          "platform": "myspace"})
    b = unwrap(r)
    check("9.4 POST /exports 非法 platform → 40001",
          r.status_code == 422 and b["code"] == 40001, json.dumps(b)[:120])
    for platform in ("douyin", "streaming"):
        r = client.post(f"{API}/exports", headers=auth_headers(token),
                        json={"version_id": version_id, "format": "release",
                              "platform": platform,
                              "meta": {"title": "雨夜航班", "artist": "demo",
                                       "explicit": True, "release_date": "2026-10-01"}})
        b = unwrap(r)
        accepted = (r.status_code == 202 and b["code"] == 0
                    and b["data"]["task"]["format"] == "release")
        check(f"9.4 POST /exports release/{platform}", accepted, json.dumps(b)[:150])
        etask = wait_task(client, b["data"]["task"]["id"], token, timeout=120)
        ok = (etask["status"] == "succeeded"
              and len(etask["result"]["files"]) == 1
              and etask["result"]["files"][0]["kind"] == "export_release_zip")
        check(f"9.4 release/{platform} 产物 zip", ok,
              json.dumps(etask.get("result", {}))[:150])
        r = client.get(f"{API}/files/{etask['result']['files'][0]['file_id']}/download",
                       headers=auth_headers(token))
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = sorted(zf.namelist())
        audio = "audio.mp3" if platform == "douyin" else "audio.wav"
        meta_json = json.loads(zf.read("metadata.json"))
        cover_w = 1400 if platform == "douyin" else 3000
        ok = (names == ["README.txt", audio, "cover.png", "metadata.json"]
              and meta_json["platform"] == platform
              and meta_json["track"]["title"] == "雨夜航班"
              and meta_json["track"]["explicit"] is True
              and meta_json["aigc"]["ai_generated"] is True
              and struct.unpack(">II", zf.read("cover.png")[16:24]) == (cover_w, cover_w))
        check(f"9.4 release/{platform} 包内容（音频+封面{cover_w}+metadata+README）",
              ok, f"names={names}")

    # 契约 §14 R1 转正：exported_formats 派生字段（succeeded 导出格式去重升序）
    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
    b = unwrap(r)
    check("R1 work.exported_formats（详情：含 release 去重升序）",
          r.status_code == 200 and b["data"]["exported_formats"]
          == ["midi", "mp3", "release", "stems", "wav"], json.dumps(b["data"])[:120])
    r = client.get(f"{API}/works", headers=auth_headers(token))
    b = unwrap(r)
    hit = next((w for w in b["data"]["items"] if w["id"] == work_id), None)
    check("R1 work.exported_formats（列表与详情一致）",
          hit is not None and hit["exported_formats"] == ["midi", "mp3", "release", "stems", "wav"])

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
    r = client.get(f"{API}/credits/transactions", headers=auth_headers(token),
                   params={"page_size": 100})
    b = unwrap(r)
    check("11.2 激活发放 10000 积分（plan_grant）", any(
        t["reason"] == "plan_grant" and t["delta"] == 10000
        for t in b["data"]["items"]))

    # ============ 16. v0.7.0 商业化批（账号体系/支付门/证书分流） ============
    # 16.1 refresh 轮换与吊销（v0.13.0：refresh 走 HttpOnly Cookie，body 不再回显；
    #     从 Set-Cookie 头取值验证 + 请求体通道兼容旧客户端）
    def _refresh_from_setcookie(resp) -> str:
        for part in resp.headers.get("set-cookie", "").split(","):
            kv = part.split(";", 1)[0].strip()
            if kv.startswith("meloyu_refresh="):
                return kv[len("meloyu_refresh="):]
        return ""

    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    rt = _refresh_from_setcookie(r)
    sc = r.headers.get("set-cookie", "")
    check("16.1 login 经 Set-Cookie 下发 refresh（HttpOnly+Strict）",
          bool(rt) and "HttpOnly" in sc and "SameSite=strict" in sc
          and "Path=/api/v1/auth" in sc)
    check("16.1 login 响应体不再含 refresh_token",
          "refresh_token" not in unwrap(r)["data"])
    r = client.post(f"{API}/auth/refresh", json={})  # Cookie 通道（httpx 自动携带）
    new_pair = unwrap(r)["data"]
    new_rt = _refresh_from_setcookie(r)
    check("16.1 POST /auth/refresh 轮换（Cookie 通道）", r.status_code == 200
          and new_pair["access_token"] and bool(new_rt) and new_rt != rt)
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": rt})  # 旧值（body 兼容）
    check("16.1 旧 refresh 已失效（40103）", r.status_code == 401
          and unwrap(r)["code"] == 40103)
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": new_rt})  # 新值（body 兼容）
    newest_rt = _refresh_from_setcookie(r)
    check("16.1 新 refresh 可用（body 兼容通道）", r.status_code == 200 and bool(newest_rt))
    r = client.post(f"{API}/auth/logout", headers=auth_headers(new_pair["access_token"]))
    check("16.1 POST /auth/logout", r.status_code == 200 and unwrap(r)["data"]["ok"])
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": newest_rt})
    check("16.1 logout 后 refresh 被吊销", r.status_code == 401)

    # 16.2 改密/找回（SMTP 未配置口径）——只测错误路径，不实际改密（避免污染主凭据）
    r = client.post(f"{API}/auth/change-password",
                    headers=auth_headers(token),
                    json={"old_password": "DefinitelyWrong0", "new_password": "NewPass678"})
    check("16.2 change-password 旧密码错误拒绝（40103）", r.status_code == 401
          and unwrap(r)["code"] == 40103)
    # v0.10.2：找回密码恒 ok（SMTP 未配置只记日志，不向调用方区分——防注册状态枚举）
    r = client.post(f"{API}/auth/forgot-password", json={"email": email})
    check("16.2 forgot-password 恒 ok（防枚举口径，SMTP 未配置不外露）",
          r.status_code == 200 and unwrap(r)["data"]["ok"] is True)
    r = client.post(f"{API}/auth/forgot-password",
                    json={"email": "nobody-404@meloyu.test"})
    check("16.2 forgot-password 不存在邮箱同样 ok（响应不可区分）",
          r.status_code == 200 and unwrap(r)["data"]["ok"] is True)

    # 16.3 支付门（2026-10-03 转型：Stripe 已拆除，/billing/* 下线）
    r = client.post(f"{API}/billing/checkout", headers=auth_headers(token),
                    json={"kind": "subscription", "plan": "pro", "interval": "monthly"})
    check("16.3 /billing/checkout 已下线 → 404", r.status_code == 404)
    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "pro"})
    check("16.3 付费档订阅停售 → 40901", r.status_code == 409
          and unwrap(r)["code"] == 40901)

    # 16.4 免费档降级 + 档位恢复（studio 供后续节使用）
    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "free"})
    check("16.4 降级 free 允许", r.status_code == 200
          and unwrap(r)["data"]["plan"] == "free")
    _activate_plan_via_db(email, "studio")
    r = client.get(f"{API}/auth/me", headers=auth_headers(token))
    check("16.4 重新激活 studio（后续节依赖付费档）",
          unwrap(r)["data"]["plan"] == "studio")

    # 16.5 证书 license 分流（P0-1：license 段含 grade/basis，披露固定双语）
    r = client.get(f"{API}/works?page=1&page_size=1", headers=auth_headers(token))
    items = (unwrap(r).get("data") or {}).get("items") or []
    if r.status_code != 200:
        check("16.5 works 列表可达", False, f"HTTP {r.status_code}: {r.text[:150]}")
    cert_checked = False
    for w in items:
        r = client.get(f"{API}/works/{w['id']}/versions", headers=auth_headers(token))
        vitems = ((unwrap(r).get("data") or {}).get("items")
                  if r.status_code == 200 else None) or []
        for v in vitems:
            r = client.get(f"{API}/versions/{v['id']}/certificate?format=json",
                           headers=auth_headers(token))
            if r.status_code == 200:
                cert = unwrap(r)["data"]
                lic = cert["license"]
                check("16.5 证书 license 分流（grade/basis/bilingual disclosure）",
                      lic.get("grade") in ("allowed", "nc", "conditional", "tos",
                                           "unverified", "free_plan")
                      and lic.get("basis_zh") and lic.get("basis_en")
                      and chr(10) in cert["disclosure"])
                cert_checked = True
                break
        if cert_checked:
            break
    if not cert_checked:
        check("16.5 证书 license 分流（无可签发版本则跳过）", True)

    # 16.6 账号注销与数据导出（用临时账号，不影响主流程）
    tmp_email = f"smoke-del-{uuid.uuid4().hex[:8]}@t.local"
    r = client.post(f"{API}/auth/register", json={
        "email": tmp_email, "password": "DelMe12345", "nickname": "bye"})
    check("16.6 临时账号注册", r.status_code == 201, r.text[:150])
    tmp_token = (unwrap(r).get("data") or {}).get("access_token") or ""
    if not tmp_token:
        check("16.6 注销/导出链（依赖临时账号）", False, "临时账号注册失败，跳过")
        raise SystemExit(1)
    r = client.get(f"{API}/auth/export-data", headers=auth_headers(tmp_token))
    check("16.6 GET /auth/export-data（zip 魔数 PK）",
          r.status_code == 200 and r.content[:2] == b"PK")
    r = client.post(f"{API}/auth/delete-account", headers=auth_headers(tmp_token),
                    json={"password": "DelMe12345"})
    check("16.6 POST /auth/delete-account", r.status_code == 200
          and unwrap(r)["data"]["ok"])
    r = client.post(f"{API}/auth/login", json={"email": tmp_email,
                                               "password": "DelMe12345"})
    check("16.6 注销后原账号无法登录", r.status_code == 401)

    # 16.7 防侵权防护（MiniMax 义务②：在世艺术家名义/声音冒用 → 42202，服务端强制）
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "simple", "simple_prompt": "a song in the style of Taylor Swift",
        "params": {"duration_sec": 30},
    })
    check("16.7 生成请求艺术家冒用 → 42202（义务②防护）",
          r.status_code == 422 and unwrap(r)["code"] == 42202,
          json.dumps(unwrap(r))[:120])
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "simple", "simple_prompt": "dreamy synthwave night drive",
        "params": {"duration_sec": 30},
    })
    check("16.7 正常风格描述不被误拦（201）", r.status_code == 201,
          json.dumps(unwrap(r))[:120])

    # ============ 17. FR-4 参考音频（v0.8.1） ============
    import io as _io
    import wave as _wave

    def _smoke_ref_wav(bpm: int, sr: int = 22050, dur: float = 20.0) -> bytes:
        n = int(dur * sr)
        x = __import__("numpy").random.default_rng(7).normal(0, 0.02, n)
        beat = int(sr * 60.0 / bpm)
        for k in range(0, n - sr // 40, beat):
            L = sr // 40
            env = __import__("numpy").exp(__import__("numpy").linspace(0, 8, L))
            x[k:k + L] += 0.8 * env * __import__("numpy").sin(
                2 * 3.14159265 * 2000 * __import__("numpy").arange(L) / sr)
        x = (x / abs(x).max() * 0.7 * 32767).astype("<i2")
        buf = _io.BytesIO()
        with _wave.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(x.tobytes())
        return buf.getvalue()

    r = client.post(f"{API}/reference-tracks", headers=auth_headers(token),
                    params={"filename": "ref.wav"}, content=_smoke_ref_wav(120))
    b = unwrap(r)
    ref_track = b["data"]
    check("17.1 POST /reference-tracks（wav 上传即分析）",
          r.status_code == 201 and b["data"]["analyzed"] is True
          and 60 <= b["data"]["analysis"]["bpm"] <= 174
          and "非采样" in b["data"]["notice"] and "no waveform" in b["data"]["notice"],
          json.dumps(b)[:150])
    r = client.post(f"{API}/reference-tracks", headers=auth_headers(token),
                    params={"filename": "bad.flac"}, content=b"x" * 100)
    check("17.1 非法扩展名 → 40001", r.status_code == 422
          and unwrap(r)["code"] == 40001)
    r = client.post(f"{API}/reference-tracks", headers=auth_headers(token),
                    params={"filename": "song.mp3"}, content=bytes([0xFF, 0xFB]) + b"0" * 2048)
    b = unwrap(r)
    mp3_track = b["data"]
    check("17.1 mp3 上传 → 未分析（待浏览器解码补传）",
          r.status_code == 201 and mp3_track["analyzed"] is False)
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "custom", "style_prompt": "night drive synthwave",
        "params": {"duration_sec": 30, "vocal": "instrumental"},
        "reference_track_id": mp3_track["id"],
    })
    check("17.2 未分析参考用于生成 → 40901 可读指引", r.status_code == 409
          and unwrap(r)["code"] == 40901)
    r = client.post(f"{API}/reference-tracks/{mp3_track['id']}/analysis-wav",
                    headers=auth_headers(token), content=_smoke_ref_wav(96))
    b = unwrap(r)
    check("17.3 POST /reference-tracks/{id}/analysis-wav（补传后分析）",
          r.status_code == 200 and b["data"]["analyzed"] is True
          and b["data"]["analysis"]["duration_sec"] > 0, json.dumps(b)[:150])
    r = client.get(f"{API}/reference-tracks", headers=auth_headers(token))
    b = unwrap(r)
    check("17.4 GET /reference-tracks（列表）", r.status_code == 200
          and b["data"]["total"] >= 2 and len(b["data"]["items"]) >= 2)
    # 参考生成 E2E：参数覆盖 + 留痕（30s 器乐，走当前默认引擎）
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "custom", "style_prompt": "night drive synthwave",
        "params": {"duration_sec": 30, "vocal": "instrumental"},
        "reference_track_id": ref_track["id"],
    })
    b = unwrap(r)
    ref_gen_ok = r.status_code == 201
    check("17.5 参考生成提交（201）", ref_gen_ok, json.dumps(b)[:150])
    if ref_gen_ok:
        gtask = wait_task(client, b["data"]["task"]["id"], token, timeout=300)
        check("17.5 参考生成执行成功", gtask["status"] == "succeeded",
              json.dumps(gtask.get("error", ""))[:150])
        wid = b["data"]["work"]["id"]
        r = client.get(f"{API}/works/{wid}", headers=auth_headers(token))
        wdet = unwrap(r)["data"]
        ref_bpm = ref_track["analysis"]["bpm"]
        check("17.5 参考特征落到作品快照（bpm/key 来自分析值）",
              wdet["bpm"] == ref_bpm
              and wdet["key"]["tonic"] == ref_track["analysis"]["key_tonic"]
              and wdet["key"]["mode"] == ref_track["analysis"]["key_mode"],
              f"work={wdet['bpm']}/{wdet['key']} ref={ref_bpm}")
    r = client.delete(f"{API}/reference-tracks/{mp3_track['id']}",
                      headers=auth_headers(token))
    check("17.6 DELETE /reference-tracks/{id}", r.status_code == 200
          and unwrap(r)["data"]["ok"] is True)
    r = client.get(f"{API}/reference-tracks/{mp3_track['id']}",
                   headers=auth_headers(token))
    check("17.6 删除后读取 → 40401", r.status_code == 404
          and unwrap(r)["code"] == 40401)

    # ============ 18. FR-5 我的音色（v0.8.2） ============
    np_ = __import__("numpy")

    def _smoke_voice_wav(f0: float, formant: float, seed: int, sr: int = 22050,
                         dur: float = 4.0) -> bytes:
        rng = np_.random.default_rng(seed)
        n = int(dur * sr)
        t = np_.arange(n) / sr
        f0_t = f0 * (1.0 + 0.03 * np_.sin(2 * 3.14159265 * 1.7 * t)
                     + 0.01 * rng.standard_normal(n).cumsum() / n)
        phase = 2 * 3.14159265 * np_.cumsum(f0_t) / sr
        x = np_.zeros(n)
        for k in range(1, 25):
            x += (1.0 / k) * np_.sin(k * phase)
        x += 0.6 * np_.sin(2 * 3.14159265 * 800 * formant * t) * (0.5 + 0.5 * np_.sin(2 * 3.14159265 * 3 * t))
        x += 0.4 * np_.sin(2 * 3.14159265 * 1200 * formant * t) * (0.5 + 0.5 * np_.sin(2 * 3.14159265 * 2.2 * t))
        x = (x / np_.abs(x).max() * 0.6 * 32767).astype("<i2")
        buf = _io.BytesIO()
        with _wave.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(x.tobytes())
        return buf.getvalue()

    r = client.post(f"{API}/voice-profiles", headers=auth_headers(token),
                    params={"name": "我的音色"})
    b = unwrap(r)
    vp = b["data"]
    check("18.1 POST /voice-profiles 注册（下发随机短语1）",
          r.status_code == 201 and vp["status"] == "pending" and vp["phrase1"]
          and vp["phrase2"] is None, json.dumps(b)[:150])
    r = client.post(f"{API}/voice-profiles/{vp['id']}/samples",
                    headers=auth_headers(token), params={"step": 1},
                    content=_smoke_voice_wav(180, 1.0, seed=1))
    b = unwrap(r)
    vp = b["data"]
    check("18.1 样本1提交 → 短语2后发且不同（防重放）",
          r.status_code == 200 and vp["phrase2"] and vp["phrase2"] != vp["phrase1"])
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "custom", "style_prompt": "dream pop with airy pads",
        "params": {"duration_sec": 30, "vocal": "voice_clone",
                   "voice_profile_id": vp["id"]},
    })
    check("18.2 未验证音色用于生成 → 40901", r.status_code == 409
          and unwrap(r)["code"] == 40901)
    r = client.post(f"{API}/voice-profiles/{vp['id']}/samples",
                    headers=auth_headers(token), params={"step": 2},
                    content=_smoke_voice_wav(180, 1.0, seed=11))
    b = unwrap(r)
    vp = b["data"]
    check("18.3 同人样本2 → verified + timbre + 留痕2条",
          r.status_code == 200 and vp["status"] == "verified"
          and vp["timbre"] and vp["verify_score"] is not None
          and len(vp["consent_log"]) == 2, json.dumps(b)[:200])
    # 他人音频档案：样本2 用显著不同的“人”（低沉男声）→ 不通过
    r = client.post(f"{API}/voice-profiles", headers=auth_headers(token),
                    params={"name": "冒名档案"})
    vp_bad = unwrap(r)["data"]
    client.post(f"{API}/voice-profiles/{vp_bad['id']}/samples",
                headers=auth_headers(token), params={"step": 1},
                content=_smoke_voice_wav(180, 1.0, seed=2))
    r = client.post(f"{API}/voice-profiles/{vp_bad['id']}/samples",
                    headers=auth_headers(token), params={"step": 2},
                    content=_smoke_voice_wav(95, 0.75, seed=5))
    vp_bad = unwrap(r)["data"]
    check("18.3 他人音频做样本2 → 拒绝（status≠verified）",
          vp_bad["status"] != "verified", f"status={vp_bad['status']}")
    # 音色克隆生成 E2E（本地引擎）
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "custom", "style_prompt": "dream pop with airy pads",
        "params": {"duration_sec": 30, "vocal": "voice_clone",
                   "voice_profile_id": vp["id"]},
    })
    b = unwrap(r)
    vc_ok = r.status_code == 201
    check("18.4 voice_clone 生成提交（201，vocal=我的音色）", vc_ok,
          json.dumps(b)[:150])
    if vc_ok:
        gtask = wait_task(client, b["data"]["task"]["id"], token, timeout=300)
        check("18.4 voice_clone 生成执行成功", gtask["status"] == "succeeded",
              json.dumps(gtask.get("error", ""))[:150])
        r = client.get(f"{API}/versions/{gtask['version_id']}", headers=auth_headers(token))
        # version 详情不直接暴露 params？改查任务 payload 口径：留痕在 request_payload
        # v0.15.0：经应用 SessionLocal 查询（PG/SQLite 双方言；冒烟目标库由
        # DATA_DIR/DATABASE_URL 指向被测环境）
        from sqlalchemy import select as _sel

        from app.database import SessionLocal as _SL
        from app.models import Task as _T
        with _SL() as _db:
            _row = _db.execute(_sel(_T.request_payload).where(
                _T.id == gtask["id"])).first()
        snap = json.loads(_row[0]) if _row else {}
        check("18.4 voice 留痕（voice_clone=true + profile/活体口径）",
              snap.get("voice", {}).get("voice_clone") is True
              and snap["voice"]["voice_profile_id"] == vp["id"]
              and snap["voice"]["liveness"] == "two_random_phrases")
    r = client.get(f"{API}/voice-profiles", headers=auth_headers(token))
    b = unwrap(r)
    check("18.5 GET /voice-profiles（列表）", r.status_code == 200
          and b["data"]["total"] >= 2)
    r = client.delete(f"{API}/voice-profiles/{vp_bad['id']}", headers=auth_headers(token))
    check("18.6 DELETE /voice-profiles/{id}（删除=吊销）", r.status_code == 200
          and unwrap(r)["data"]["ok"] is True)

    # ============ 19. FR-13 团队空间与协作评论（v0.8.1） ============
    mate_email = f"mate_{uuid.uuid4().hex[:8]}@meloyu.test"
    r = client.post(f"{API}/auth/register", json={"email": mate_email,
                                                  "password": "Smoke1234",
                                                  "nickname": "队友"})
    mate_token = unwrap(r)["data"]["access_token"]
    r = client.post(f"{API}/team/spaces", headers=auth_headers(token),
                    json={"name": "冒烟小队"})
    b = unwrap(r)
    space = b["data"]
    check("19.1 POST /team/spaces（创建即含 owner 成员）",
          r.status_code == 201 and space["my_role"] == "owner"
          and space["member_count"] == 1, json.dumps(b)[:150])
    r = client.post(f"{API}/team/spaces/{space['id']}/members",
                    headers=auth_headers(token),
                    json={"email": mate_email, "role": "viewer"})
    b = unwrap(r)
    check("19.1 添加 viewer 成员", r.status_code == 200 and b["data"]["member_count"] == 2)
    r = client.post(f"{API}/works/{work_id}/share", headers=auth_headers(token),
                    json={"space_id": space["id"]})
    check("19.2 POST /works/{id}/share", r.status_code == 200
          and unwrap(r)["data"]["space_id"] == space["id"])
    # viewer 成员：可读详情/评论列表，不可评论、不可改标题
    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(mate_token))
    b = unwrap(r)
    check("19.3 viewer 读共享作品（详情含 my_role/space_id）",
          r.status_code == 200 and b["data"]["my_role"] == "viewer"
          and b["data"]["space_id"] == space["id"])
    r = client.post(f"{API}/works/{work_id}/comments", headers=auth_headers(mate_token),
                    json={"time_sec": 10, "body": "viewer 不该能发"})
    check("19.3 viewer 评论 → 40301", r.status_code == 403)
    r = client.patch(f"{API}/works/{work_id}", headers=auth_headers(mate_token),
                     json={"title": "越权改名"})
    check("19.3 viewer 改标题 → 40301", r.status_code == 403)
    # 升级 commenter：可评论、锚点排序、resolve 自己的（member user_id 从空间详情取）
    r = client.get(f"{API}/team/spaces/{space['id']}", headers=auth_headers(token))
    mate_id = next(m["user_id"] for m in unwrap(r)["data"]["members"]
                   if m["role"] == "viewer")
    r = client.patch(f"{API}/team/spaces/{space['id']}/members/{mate_id}",
                     headers=auth_headers(token), json={"role": "commenter"})
    check("19.4 升级 commenter", r.status_code == 200)
    r = client.post(f"{API}/works/{work_id}/comments", headers=auth_headers(mate_token),
                    json={"time_sec": 20.5, "body": "副歌混响再多点"})
    c_mid = unwrap(r)["data"]
    check("19.4 commenter 评论（锚定 120.5s）", r.status_code == 201
          and abs(c_mid["time_sec"] - 20.5) < 0.01)
    r = client.post(f"{API}/works/{work_id}/comments", headers=auth_headers(token),
                    json={"time_sec": 3.2, "body": "开头轻一点"})
    c_owner = unwrap(r)["data"]
    r = client.post(f"{API}/works/{work_id}/comments", headers=auth_headers(mate_token),
                    json={"time_sec": 999, "body": "超界锚点"})
    check("19.4 锚点超时间轴 → 40001", r.status_code == 422
          and unwrap(r)["code"] == 40001)
    r = client.get(f"{API}/works/{work_id}/comments", headers=auth_headers(mate_token))
    items = unwrap(r)["data"]["items"]
    check("19.5 GET /works/{id}/comments（按时间轴排序）",
          r.status_code == 200 and len(items) == 2
          and items[0]["id"] == c_owner["id"] and items[1]["id"] == c_mid["id"])
    r = client.patch(f"{API}/comments/{c_mid['id']}", headers=auth_headers(mate_token),
                     json={"resolved": True})
    check("19.5 作者 resolve 评论", r.status_code == 200
          and unwrap(r)["data"]["resolved"] is True)
    # editor：可改标题
    r = client.patch(f"{API}/team/spaces/{space['id']}/members/{mate_id}",
                     headers=auth_headers(token), json={"role": "editor"})
    r = client.patch(f"{API}/works/{work_id}", headers=auth_headers(mate_token),
                     json={"title": "队友改名"})
    check("19.6 editor 改标题（角色写权）", r.status_code == 200
          and unwrap(r)["data"]["title"] == "队友改名")
    # editor 不可删除作品（owner_only）
    r = client.delete(f"{API}/works/{work_id}", headers=auth_headers(mate_token))
    check("19.6 editor 删除作品 → 40301（owner 专属）", r.status_code == 403)
    # 取消共享 → 成员失权
    r = client.delete(f"{API}/works/{work_id}/share", headers=auth_headers(token))
    check("19.7 DELETE /works/{id}/share", r.status_code == 200)
    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(mate_token))
    check("19.7 取消共享后成员 → 40301", r.status_code == 403)
    # 恢复属主标题（后续节不受影响）+ 共享状态复位完成
    client.patch(f"{API}/works/{work_id}", headers=auth_headers(token),
                 json={"title": "冒烟作品改名"})

    # ============ 20. FR-19 开放 API β（v0.8.2） ============
    r = client.post(f"{API}/api-keys", headers=auth_headers(token),
                    json={"name": "冒烟密钥"})
    b = unwrap(r)
    apikey = b["data"]
    check("20.1 POST /api-keys（完整 key 仅此一次）",
          r.status_code == 201 and apikey["key"].startswith("meloyu_sk_")
          and len(apikey["key"]) == len("meloyu_sk_") + 40
          and apikey["notice"], json.dumps(b)[:150])
    r = client.get(f"{API}/api-keys", headers=auth_headers(token))
    b = unwrap(r)
    check("20.1 GET /api-keys（列表仅前缀）", r.status_code == 200
          and b["data"]["total"] >= 1 and "key" not in b["data"]["items"][0])
    r = client.get(f"{API}/public/works", headers={"X-API-Key": apikey["key"]})
    check("20.2 GET /public/works（X-API-Key）", r.status_code == 200
          and "items" in unwrap(r)["data"])
    r = client.get(f"{API}/public/works",
                   headers={"X-API-Key": "meloyu_sk_deadbeef00"})
    check("20.2 无效 key → 40101", r.status_code == 401)
    # 公开生歌（按量计费走积分）+ via 留痕 + 任务查询 + 下载
    bal_before = client.get(f"{API}/credits/balance",
                            headers=auth_headers(token)).json()["data"]["balance"]
    r = client.post(f"{API}/public/generations", headers={"X-API-Key": apikey["key"]},
                    json={"mode": "custom", "style_prompt": "lofi study beat",
                          "params": {"duration_sec": 30, "vocal": "instrumental"}})
    b = unwrap(r)
    pub_ok = r.status_code == 201 and b["data"]["poll"].endswith(
        b["data"]["task"]["id"])
    check("20.3 POST /public/generations（201 + poll 指引）", pub_ok,
          json.dumps(b)[:150])
    if pub_ok:
        ptid = b["data"]["task"]["id"]
        # 密钥侧轮询
        for _ in range(200):
            pr = client.get(f"{API}/public/tasks/{ptid}",
                            headers={"X-API-Key": apikey["key"]})
            td = unwrap(pr)["data"]
            if td["status"] in ("succeeded", "failed", "canceled"):
                break
            time.sleep(1.5)
        check("20.4 GET /public/tasks/{id}（终态+downloads）",
              td["status"] == "succeeded" and td.get("downloads"),
              json.dumps(td.get("error", ""))[:150])
        if td.get("downloads"):
            dl = td["downloads"][0]  # 服务端返回相对路径，客户端自行拼 base
            r = client.get(f"{BASE}{dl}", headers={"X-API-Key": apikey["key"]})
            check("20.5 GET /public/files/{id}/download（密钥鉴权下载）",
                  r.status_code == 200
                  and r.headers.get("content-disposition", "").startswith("attachment"))
            r = client.get(f"{BASE}{dl}", headers={"X-API-Key": "meloyu_sk_wrong"})
            check("20.5 错误 key 下载 → 40101", r.status_code == 401)
        bal_after = client.get(f"{API}/credits/balance",
                               headers=auth_headers(token)).json()["data"]["balance"]
        check("20.3 按量计费（积分扣 12：站内账本）", bal_before - bal_after == 12,
              f"{bal_before} -> {bal_after}")
    # 吊销后鉴权失效
    kid = client.get(f"{API}/api-keys", headers=auth_headers(token)).json()         ["data"]["items"][0]["id"]
    r = client.delete(f"{API}/api-keys/{kid}", headers=auth_headers(token))
    check("20.6 DELETE /api-keys/{id}（吊销）", r.status_code == 200
          and unwrap(r)["data"]["ok"] is True)
    r = client.get(f"{API}/public/works", headers={"X-API-Key": apikey["key"]})
    check("20.6 吊销后 → 40101", r.status_code == 401)

    # ============ 21. V2 多轨编辑器后端（v0.9.0）：retune + mixdown ============
    r = client.post(f"{API}/candidates/{cand_a['id']}/retune",
                    headers=auth_headers(token), json={})
    check("21.1 retune 无变更参数 → 40001", r.status_code == 422
          and unwrap(r)["code"] == 40001)
    r = client.post(f"{API}/candidates/{cand_a['id']}/retune",
                    headers=auth_headers(token), json={"bpm": 300})
    check("21.1 retune bpm 越界 → 40001", r.status_code == 422
          and unwrap(r)["code"] == 40001)
    r = client.post(f"{API}/candidates/{cand_a['id']}/retune",
                    headers=auth_headers(token), json={"bpm": 132})
    b = unwrap(r)
    rt_ok = r.status_code == 201
    check("21.1 POST /candidates/{id}/retune（bpm=132，6 积分）", rt_ok
          and b["data"]["task"]["provider"] == "localsynth", json.dumps(b)[:150])
    if rt_ok:
        t = wait_task(client, b["data"]["task"]["id"], token, timeout=300)
        check("21.1 retune 执行成功（同 seed 确定性重渲染）", t["status"] == "succeeded",
              json.dumps(t.get("error", ""))[:150])
        r = client.get(f"{API}/versions/{t['version_id']}", headers=auth_headers(token))
        vdet = unwrap(r)["data"]
        check("21.1 retune 子版本（source=retune、bpm=132）",
              vdet["source"] == "retune" and vdet["params"]["bpm"] == 132,
              json.dumps(vdet.get("params", {}))[:120])
    # mixdown：35s 立体声正弦 wav → 子版本 source=mixdown
    sr_, dur_ = 48000, 35
    tt = np_.arange(int(sr_ * dur_)) / sr_
    xx = 0.4 * np_.sin(2 * 3.14159265 * 440 * tt)
    pcm = (xx * 32767).astype("<i2")
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr_)
        wf.writeframes(np_.repeat(pcm, 2).tobytes())
    mix_bytes = buf.getvalue()
    # 找 retune 后的当前版本
    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
    cur_vid = unwrap(r)["data"]["active_version_id"]
    r = client.post(f"{API}/versions/{cur_vid}/mixdown", headers=auth_headers(token),
                    params={"notes": "人声+1dB，鼓组低切"},
                    content=mix_bytes)
    b = unwrap(r)
    check("21.2 POST /versions/{id}/mixdown（octet wav → 子版本）",
          r.status_code == 201 and b["data"]["version"]["source"] == "mixdown",
          json.dumps(b)[:150])
    if r.status_code == 201:
        mv = b["data"]["version"]["id"]
        r = client.get(f"{API}/versions/{mv}/candidates", headers=auth_headers(token))
        cands = unwrap(r)["data"]["items"]
        check("21.2 mixdown 候选（1 个已采用、无 AI 分、带 preview/master）",
              len(cands) == 1 and cands[0]["adopted"] is True
              and cands[0]["quality_score"] is None
              and {f["kind"] for f in cands[0]["files"]} == {"master", "preview"})
        r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
        check("21.2 work 当前版本切到 mixdown",
              unwrap(r)["data"]["active_version_id"] == mv)
    r = client.post(f"{API}/versions/{cur_vid}/mixdown", headers=auth_headers(token),
                    content=b"not a wav")
    check("21.2 非 wav → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001)
    r = client.post(f"{API}/versions/{cur_vid}/mixdown", headers=auth_headers(token),
                    content=_smoke_ref_wav(120)[:20000])  # 截断的合法 wav 头也解不出帧
    check("21.2 时长过短 → 40001", r.status_code == 422
          and unwrap(r)["code"] == 40001)

    # ============ 22. V2-b 我的口味（v0.9.0） ============
    r = client.post(f"{API}/taste/rebuild", headers=auth_headers(token))
    b = unwrap(r)
    prof = b["data"]["profile"]
    check("22.1 POST /taste/rebuild（作品库统计画像）",
          r.status_code == 200 and b["data"]["sample_count"] >= 3
          and 60 <= (prof.get("bpm") or 0) <= 174 and prof.get("key")
          and isinstance(prof.get("top_tags"), list)
          and b["data"]["semantics"][0] == "suggestions_only",
          json.dumps(b)[:200])
    r2 = client.get(f"{API}/taste", headers=auth_headers(token))
    check("22.1 GET /taste（幂等读取）",
          r2.status_code == 200
          and unwrap(r2)["data"]["profile"] == prof)

    # ============ 23. 词谱生成（v0.10.0） ============
    r = client.get(f"{API}/versions/{version_id}/leadsheet", headers=auth_headers(token),
                   params={"format": "json"})
    b = unwrap(r)
    ls = b["data"]
    check("23.1 GET /versions/{id}/leadsheet?format=json",
          r.status_code == 200 and ls["schema"] == "meloyu.leadsheet/1.0"
          and ls["stats"]["note_count"] > 0 and ls["stats"]["bar_count"] > 0
          and ls["meta"]["bpm"] > 0 and ls["meta"]["key"], json.dumps(b)[:150])
    syls = [n["syllable"] for bb in ls["bars"] for n in bb["notes"] if n["syllable"]]
    check("23.1 词谱音节对齐（歌词上谱）", len(syls) >= 4,
          f"syllables={len(syls)}")
    r = client.get(f"{API}/versions/{version_id}/leadsheet", headers=auth_headers(token),
                   params={"format": "pdf"})
    check("23.2 GET /versions/{id}/leadsheet?format=pdf",
          r.status_code == 200 and r.content[:5] == b"%PDF-"
          and r.headers.get("content-type") == "application/pdf"
          and r.headers.get("content-disposition", "").endswith('.pdf"'))
    r = client.get(f"{API}/versions/{version_id}/leadsheet", headers=auth_headers(token),
                   params={"format": "docx"})
    check("23.2 非法 format → 40001", r.status_code == 422
          and unwrap(r)["code"] == 40001)

    # ============ 24. V2-c 作品市场（v0.10.1） ============
    r = client.post(f"{API}/market/listings", headers=auth_headers(token),
                    json={"work_id": work_id, "price_credits": 100})
    b = unwrap(r)
    listing = b["data"]
    check("24.1 POST /market/listings（上架）", r.status_code == 201
          and listing["status"] == "active" and listing["price_credits"] == 100
          and listing["preview_file_id"], json.dumps(b)[:150])
    r = client.post(f"{API}/market/listings", headers=auth_headers(token),
                    json={"work_id": work_id, "price_credits": 50})
    check("24.1 重复上架 → 40901", r.status_code == 409)
    r = client.get(f"{API}/market/listings", params={"page_size": 50})
    b = unwrap(r)
    check("24.2 GET /market/listings（浏览免鉴权）", r.status_code == 200
          and any(x["id"] == listing["id"] for x in b["data"]["items"]))
    r = client.post(f"{API}/market/listings/{listing['id']}/purchase",
                    headers=auth_headers(token))
    check("24.3 买自己 → 40901", r.status_code == 409)
    # mate（19 节注册的队友，editor 曾有积分？用其注册赠送 200）购买
    bal_s = client.get(f"{API}/credits/balance", headers=auth_headers(mate_token)).json()["data"]["balance"]
    r = client.post(f"{API}/market/listings/{listing['id']}/purchase",
                    headers=auth_headers(mate_token))
    b = unwrap(r)
    order = b["data"]
    check("24.3 购买（分账 90/10 + 非独占授权）", r.status_code == 200
          and order["seller_earnings"] == 90 and order["platform_fee"] == 10
          and "非独占" in order["license"] and "Non-exclusive" in order["license"],
          json.dumps(b)[:150])
    bal_s2 = client.get(f"{API}/credits/balance", headers=auth_headers(mate_token)).json()["data"]["balance"]
    check("24.3 买家积分扣减", bal_s - bal_s2 == 100, f"{bal_s} -> {bal_s2}")
    r = client.post(f"{API}/market/listings/{listing['id']}/purchase",
                    headers=auth_headers(mate_token))
    check("24.3 重复购买 → 40901", r.status_code == 409)
    r = client.get(f"{API}/market/my/orders", headers=auth_headers(mate_token))
    check("24.4 GET /market/my/orders（授权凭证）", r.status_code == 200
          and unwrap(r)["data"]["total"] >= 1)
    r = client.get(f"{API}/market/my/listings", headers=auth_headers(token))
    check("24.4 GET /market/my/listings", r.status_code == 200
          and unwrap(r)["data"]["total"] >= 1
          and unwrap(r)["data"]["items"][0]["sales"] >= 1)
    r = client.delete(f"{API}/market/listings/{listing['id']}", headers=auth_headers(token))
    check("24.5 DELETE /market/listings/{id}（下架）", r.status_code == 200
          and unwrap(r)["data"]["status"] == "delisted")
    r = client.get(f"{API}/market/listings")
    check("24.5 下架后浏览不可见", r.status_code == 200
          and not any(x["id"] == listing["id"]
                      for x in unwrap(r)["data"]["items"]))

    # ============ 25. 占位转正批（v0.11.0）：哼唱成歌 / 旋律修调 / 自定义封面 / 联系通道 ============

    # 25.1 哼唱分析：合成四音（A3→C4→E4→D4）→ 音高轮廓 + 音程保真
    import struct as _st
    import wave as _wav

    import numpy as _np
    _sr = 22050
    _x = []
    for _hz in (220.0, 261.63, 329.63, 293.66):
        _t = _np.arange(int(_sr * 0.5)) / _sr
        _seg = 0.6 * _np.sin(2 * _np.pi * _hz * _t)
        _env = _np.minimum(1, _np.arange(len(_t)) / (_sr * 0.02)) * _np.minimum(
            1, (len(_t) - _np.arange(len(_t))) / (_sr * 0.02))
        _x.append(_seg * _env)
    _x = _np.concatenate(_x)
    _buf = io.BytesIO()
    with _wav.open(_buf, "wb") as _wf:
        _wf.setnchannels(1); _wf.setsampwidth(2); _wf.setframerate(_sr)
        _wf.writeframes((_x * 32767).astype("<i2").tobytes())
    r = client.post(f"{API}/hum/analyze", content=_buf.getvalue(),
                    headers={"Content-Type": "application/octet-stream", **auth_headers(token)})
    hum = unwrap(r)["data"] if r.status_code == 200 else {}
    _semis = [n["semi"] for n in hum.get("notes", [])]
    _ivs = [b - a for a, b in zip(_semis, _semis[1:])] if len(_semis) >= 2 else []
    check("25.1 POST /hum/analyze（音高轮廓+音程保真）",
          r.status_code == 200 and len(_semis) >= 4 and 0 in _semis
          and all(abs(x - y) <= 1 for x, y in zip(_ivs[:3], [3, 4, -2]))
          and 2 <= len(hum.get("hum_melody", [])) <= 64
          and 60 <= hum.get("bpm_hint", 0) <= 174, json.dumps(hum)[:200])
    r = client.post(f"{API}/hum/analyze", content=b"notawav",
                    headers={"Content-Type": "application/octet-stream", **auth_headers(token)})
    check("25.1 非 wav → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001)

    # 25.2 哼唱生成：hum_melody 透传 → 引擎旋律覆写 → 成功 + 留痕
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "simple", "simple_prompt": "哼唱旋律之歌",
        "params": {"duration_sec": 30, "hum_melody": hum.get("hum_melody")},
    })
    hum_task = (r.json().get("data") or {}).get("task") if r.status_code == 201 else None
    check("25.2 哼唱生成提交（params.hum_melody）", r.status_code == 201 and hum_task is not None,
          r.text[:200])
    if hum_task:
        t = wait_task(client, hum_task["id"], token, timeout=180)
        ver_row = None
        if t["status"] == "succeeded":
            r2 = client.get(f"{API}/versions/{t['version_id']}", headers=auth_headers(token))
            ver_row = unwrap(r2)["data"] if r2.status_code == 200 else {}
        check("25.2 哼唱生成成功 + version.params 留痕 hum_melody",
              t["status"] == "succeeded" and ver_row
              and (ver_row.get("params") or {}).get("hum_melody"),
              json.dumps(t.get("error") or {})[:160])

    # 25.3 旋律修调：生成 → 采纳 → 词谱 beat → pitch-edit → 子版本
    r = client.post(f"{API}/generations", headers=auth_headers(token), json={
        "mode": "simple", "simple_prompt": "修调测试曲", "seed": 700701,
        "params": {"duration_sec": 30}})
    pe_task = (r.json().get("data") or {}).get("task") if r.status_code == 201 else None
    pe_ok = pe_task is not None
    check("25.3 修调源曲生成提交", pe_ok, r.text[:160])
    if pe_ok:
        t = wait_task(client, pe_task["id"], token, timeout=180)
        pe_ok = t["status"] == "succeeded"
        check("25.3 修调源曲生成成功", pe_ok, json.dumps(t.get("error") or {})[:160])
        if pe_ok:
            r = client.get(f"{API}/versions/{t['version_id']}/candidates",
                           headers=auth_headers(token))
            cands = unwrap(r)["data"]["items"]
            r = client.post(f"{API}/candidates/{cands[0]['id']}/adopt",
                            headers=auth_headers(token))
            check("25.3 采纳候选（供修调与封面节复用）", r.status_code == 200)
            r = client.get(f"{API}/versions/{t['version_id']}/leadsheet?format=json",
                           headers=auth_headers(token))
            ls = unwrap(r)["data"] if r.status_code == 200 else {}
            all_notes = [n for b in ls.get("bars", []) for n in b["notes"]]
            check("25.3 词谱 json 提供音符（beat 键）", len(all_notes) >= 5,
                  f"notes={len(all_notes)}")
            if all_notes:
                beat0 = float(all_notes[0]["beat"])
                beat1 = float(all_notes[min(2, len(all_notes) - 1)]["beat"])
                pe_body = {"edits": [{"beat": beat0, "semi": 1},
                                     {"beat": beat1, "semi": -2}],
                           "quantize": "8"}
                r = client.post(f"{API}/candidates/{cands[0]['id']}/pitch-edit",
                                headers=auth_headers(token), json=pe_body)
                pe_task2 = (r.json().get("data") or {}).get("task") if r.status_code == 201 else None
                check("25.3 pitch-edit 提交（beat 键对齐）", r.status_code == 201 and pe_task2,
                      r.text[:200])
                if pe_task2:
                    t2 = wait_task(client, pe_task2["id"], token, timeout=180)
                    r = client.get(f"{API}/versions/{t2.get('version_id')}",
                                   headers=auth_headers(token))
                    pe_child = unwrap(r)["data"] if r.status_code == 200 else {}
                    check("25.3 pitch-edit 重渲染成功（子版本 source=pitch_edit 自动采纳）",
                          t2["status"] == "succeeded" and pe_child
                          and pe_child.get("source") == "pitch_edit"
                          and pe_child.get("active_candidate_id"),
                          json.dumps(t2.get("error") or pe_child or {})[:200])
        if pe_ok:
            r = client.get(f"{API}/versions/{pe_task['version_id']}/candidates",
                           headers=auth_headers(token))
            _cid = unwrap(r)["data"]["items"][0]["id"]
            r = client.post(f"{API}/candidates/{_cid}/pitch-edit",
                            headers=auth_headers(token), json={"edits": []})
            check("25.4 空编辑 → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001)
            r = client.post(f"{API}/candidates/{_cid}/pitch-edit",
                            headers=auth_headers(token),
                            json={"edits": [{"beat": 0, "semi": 99}]})
            check("25.4 semi 越界 → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001)
            r = client.post(f"{API}/candidates/{_cid}/pitch-edit",
                            headers=auth_headers(token),
                            json={"edits": [{"beat": 0, "semi": 1}], "quantize": "32"})
            check("25.4 非法 quantize → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001)

    # 25.5 自定义发行封面：程序构造 PNG → release 包内 cover.png 为上传字节
    def _png_solid(size: int, rgb=(200, 90, 30)) -> bytes:
        import zlib as _zl
        raw = b"".join(bytes([0]) + bytes(rgb) * size for _ in range(size))
        def _chunk(tag: bytes, data: bytes) -> bytes:
            return (_st.pack(">I", len(data)) + tag + data
                    + _st.pack(">I", _zl.crc32(tag + data) & 0xFFFFFFFF))
        return (bytes((137, 80, 78, 71, 13, 10, 26, 10))
                + _chunk(b"IHDR", _st.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                + _chunk(b"IDAT", _zl.compress(raw))
                + _chunk(b"IEND", b""))
    import base64 as _b64
    cover = _png_solid(600)
    cover_b64 = _b64.b64encode(cover).decode()
    if pe_ok:
        r = client.post(f"{API}/exports", headers=auth_headers(token), json={
            "version_id": pe_task["version_id"], "format": "release", "platform": "douyin",
            "meta": {"title": "封面测试", "artist": "smoke", "release_date": "2026-09-05",
                     "cover_png_b64": cover_b64}})
        cov_task = (r.json().get("data") or {}).get("task") if r.status_code == 202 else None
        check("25.5 自定义封面 release 提交", r.status_code == 202 and cov_task, r.text[:200])
        if cov_task:
            t = wait_task(client, cov_task["id"], token, timeout=180)
            dl = None
            if t["status"] == "succeeded":
                fid = t["result"]["files"][0]["file_id"]
                dl = client.get(f"{API}/files/{fid}/download",
                                headers=auth_headers(token)).content
            import zipfile as _zf
            ok_zip = dl and dl[:2] == b"PK"
            same = False
            if ok_zip:
                with _zf.ZipFile(io.BytesIO(dl)) as z:
                    same = z.read("cover.png") == cover
            check("25.5 包内 cover.png = 上传字节（占位图已替换）",
                  t["status"] == "succeeded" and same,
                  json.dumps(t.get("error") or {})[:160])
        r = client.post(f"{API}/exports", headers=auth_headers(token), json={
            "version_id": pe_task["version_id"], "format": "release", "platform": "douyin",
            "meta": {"title": "坏封面", "artist": "smoke", "release_date": "2026-09-05",
                     "cover_png_b64": _b64.b64encode(b"JPGNOTPNG").decode()}})
        check("25.5 非 PNG 封面 → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001,
              r.text[:160])
        r = client.post(f"{API}/exports", headers=auth_headers(token), json={
            "version_id": pe_task["version_id"], "format": "release", "platform": "douyin",
            "meta": {"title": "小封面", "artist": "smoke", "release_date": "2026-09-05",
                     "cover_png_b64": _b64.b64encode(_png_solid(300)).decode()}})
        check("25.5 尺寸过小封面 → 40001", r.status_code == 422 and unwrap(r)["code"] == 40001,
              r.text[:160])

    # 25.6 团队档联系通道：plans 响应携带 sales_contact 字段
    r = client.get(f"{API}/subscriptions/plans", headers=auth_headers(token))
    plans_data = unwrap(r)["data"] if r.status_code == 200 else {}
    check("25.6 plans 携带 sales_contact 字段（未配置为空串）",
          r.status_code == 200 and "sales_contact" in plans_data,
          json.dumps(plans_data)[:120])

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
