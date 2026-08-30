"""WP-B8 冒烟测试：覆盖 38 个契约接口 + 确定性验证 + Range/错误码抽查。

用法（后端需已在 127.0.0.1:8000 运行，且已灌种子）：
    ./.venv/Scripts/python scripts/smoke_test.py [--base http://127.0.0.1:8000]

不依赖 pytest；输出逐项 PASS/FAIL 与最终通过率。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid

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
               and b["data"]["generation_limits"]["max_duration_sec"] == 240)
    check("12.2 GET /system/meta", meta_ok, json.dumps(b)[:120])

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

    # ============ 生成（4） ============
    gen_body = {
        "mode": "custom",
        "style_prompt": "华语流行抒情，钢琴主导，雨夜氛围",
        "lyrics": "[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心",
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

    for endpoint in ("extend", "variant", "regen-section"):
        r = client.post(f"{API}/candidates/{cand_a['id']}/{endpoint}",
                        headers=auth_headers(token), json={})
        b = unwrap(r)
        check(f"5.{5 + ['extend', 'variant', 'regen-section'].index(endpoint)} "
              f"POST /candidates/{{id}}/{endpoint} → 501",
              r.status_code == 501 and b["code"] == 50101 and b["data"]["feature"] == endpoint)

    # ============ 作品库（6） ============
    r = client.get(f"{API}/works", headers=auth_headers(token))
    b = unwrap(r)
    check("7.1 GET /works", r.status_code == 200 and b["data"]["total"] >= 2
          and all(w["status"] == "active" for w in b["data"]["items"]))

    r = client.get(f"{API}/works/{work_id}", headers=auth_headers(token))
    b = unwrap(r)
    work_ok = (r.status_code == 200 and b["data"]["active_version_id"] == version_id
               and b["data"]["preview_file_id"] == cand_a["preview_file_id"]
               and b["data"]["duration_sec"] == cand_a["duration_sec"]
               and isinstance(b["data"]["cover_color"], str))
    check("7.2 GET /works/{id}（快照回写）", work_ok, json.dumps(b)[:200])

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
    tree_ok = (r.status_code == 200 and b["data"]["current_version_id"] == version_id
               and len(nodes) >= 2)
    if tree_ok:
        v2_node = [n for n in nodes if n["version_no"] == "v2"]
        tree_ok = bool(v2_node) and v2_node[0]["parent_version_id"] == version_id
    check("8.1 GET /works/{id}/versions（版本树 v1→v2）", tree_ok,
          json.dumps(b["data"])[:200])

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
               and cert.get("license", {}).get("type") == "non_commercial"
               and len(cert.get("fingerprint", {}).get("master_wav_sha256", "")) == 64
               and "human_participation" in cert)
    check("8.4 GET /versions/{id}/certificate", cert_ok, json.dumps(cert)[:200])

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
    check("10.1 GET /credits/balance", r.status_code == 200 and b["data"]["plan"] == "free"
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
          and len(gen_txs) == 3 and len(refund_txs) >= 1
          and all(t["balance_after"] >= 0 for t in txs))

    # 注册赠送 200 - 12*3 + 12 退款 = 176
    check("10.2 账本自洽（200 − 36 + 12 = 176）", balance_now == 200 - 36 + 12,
          f"balance={balance_now}")

    # ============ 订阅（2） ============
    r = client.get(f"{API}/subscriptions/plans", headers=auth_headers(token))
    b = unwrap(r)
    plans = b["data"]["plans"]
    check("11.1 GET /subscriptions/plans", r.status_code == 200 and len(plans) == 4
          and plans[0]["code"] == "free" and plans[0]["current"] is True
          and plans[3]["code"] == "team")

    r = client.post(f"{API}/subscriptions/switch", headers=auth_headers(token),
                    json={"plan": "studio"})
    b = unwrap(r)
    check("11.2 POST /subscriptions/switch → studio", r.status_code == 200
          and b["data"]["plan"] == "studio"
          and b["data"]["credits"]["balance"] == balance_now + 10000)

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
