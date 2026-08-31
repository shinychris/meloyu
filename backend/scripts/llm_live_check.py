"""LLM 通道真实验证（分阶段，避免整体超时）：
stage1 = Ollama 通道 generate+polish；stage2 = 外部通道 test+generate；restore = 还原默认。
用法：.venv/Scripts/python scripts/llm_live_check.py [stage1|stage2|restore|pull]
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API = "http://localhost:8000/api/v1"
MODEL = "qwen3.5:4b"  # 本地通道：think 可关、直出快
EXTERNAL_MODEL = "qwen2.5:1.5b"  # 外部通道验证：非思考型（/v1 上无法关思考）


def call(method: str, path: str, token: str | None = None, body: dict | None = None,
         timeout: float = 320.0) -> tuple[int, dict]:
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def login() -> str:
    _, b = call("POST", "/auth/login",
                body={"email": "demo@meloyu.local", "password": "Meloyu2026"})
    return b["data"]["access_token"]


def stage1(token: str) -> None:
    st, b = call("PUT", "/models/settings", token,
                 {"lyrics_backend": "ollama", "ollama_model": MODEL})
    print(f"== settings → {st} {b['data']['lyrics_backend']} {b['data']['ollama_model']}")
    t0 = time.time()
    st, b = call("POST", "/lyrics/generate", token,
                 {"theme": "夏夜海边便利店", "style_hint": "华语流行 治愈",
                  "mood": "治愈", "language": "zh"}, timeout=320)
    d = b["data"]
    print(f"== generate HTTP {st} {time.time()-t0:.0f}s engine={d.get('engine')} "
          f"fallback={d.get('fallback')} alts={len(d.get('alternatives', []))}")
    print(d["lyrics"][:300])
    print("structure:", json.dumps(d.get("structure"), ensure_ascii=False)[:140])
    if d.get("fallback_reason"):
        print("!! fallback_reason:", d["fallback_reason"])
        return
    assert d.get("engine") == f"ollama:{MODEL}" and not d.get("fallback")

    t0 = time.time()
    st, b = call("POST", "/lyrics/polish", token,
                 {"lyrics": d["lyrics"], "style_hint": "更诗意的意象",
                  "locked_lines": [1]}, timeout=320)
    p = b["data"]
    print(f"== polish HTTP {st} {time.time()-t0:.0f}s engine={p.get('engine')} "
          f"fallback={p.get('fallback')} changes={len(p.get('changes', []))} "
          f"sections={p.get('polished_sections')}")
    if p.get("fallback_reason"):
        print("!! fallback_reason:", p["fallback_reason"])


def stage2(token: str) -> None:
    st, b = call("POST", "/models/test-external", token,
                 {"base_url": "http://localhost:11434/v1", "api_key": "ollama",
                  "model": EXTERNAL_MODEL})
    print("== test-external →", st, json.dumps(b["data"], ensure_ascii=False)[:200])
    assert b["data"]["ok"] is True

    st, b = call("PUT", "/models/settings", token,
                 {"lyrics_backend": "openai_compat",
                  "external_base_url": "http://localhost:11434/v1",
                  "external_api_key": "ollama", "external_model": EXTERNAL_MODEL})
    print(f"== settings → openai_compat {st}")
    t0 = time.time()
    st, b = call("POST", "/lyrics/generate", token,
                 {"theme": "末班地铁的窗", "style_hint": "城市民谣", "mood": "忧郁",
                  "language": "zh"}, timeout=320)
    d = b["data"]
    print(f"== generate(external) HTTP {st} {time.time()-t0:.0f}s "
          f"engine={d.get('engine')} fallback={d.get('fallback')}")
    print(d["lyrics"][:200])
    if d.get("fallback_reason"):
        print("!! fallback_reason:", d["fallback_reason"])
    else:
        assert d.get("engine") == f"openai-compat:{EXTERNAL_MODEL}"


def pull_stage(token: str) -> None:
    """下载 qwen3:0.6b（进度轮询）→ 出现在列表 → 幂等重拉秒完成。"""
    st, b = call("POST", "/models/pull", token, {"model": "qwen3:0.6b"})
    assert st == 202, b
    op = b["data"]
    print(f"== pull submitted op={op['id'][:8]}…")
    seen: set[int] = set()
    while op["status"] in ("queued", "running"):
        time.sleep(3)
        _, b = call("GET", f"/models/ops/{op['id']}", token)
        op = b["data"]
        seen.add(op["progress"])
        print(f"   progress={op['progress']}% {op['message']}")
    print(f"== pull final status={op['status']} err={op['error_message']} "
          f"progress_samples={sorted(seen)[:8]}")
    assert op["status"] == "succeeded"
    _, b = call("GET", "/models/local", token)
    names = [m["name"] for m in b["data"]["models"]]
    print("== local models:", names)
    assert "qwen3:0.6b" in names
    # 幂等：已存在时重拉应快速成功
    st, b = call("POST", "/models/pull", token, {"model": "qwen3:0.6b"})
    assert st == 202
    op2 = b["data"]
    while op2["status"] in ("queued", "running"):
        time.sleep(1)
        _, b = call("GET", f"/models/ops/{op2['id']}", token)
        op2 = b["data"]
    print(f"== re-pull(已存在) status={op2['status']} progress={op2['progress']}")
    assert op2["status"] == "succeeded"


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "stage1"
    token = login()
    print("== login ok, stage =", stage)
    if stage == "stage1":
        stage1(token)
    elif stage == "stage2":
        stage2(token)
    elif stage == "pull":
        pull_stage(token)
    else:
        st, _ = call("PUT", "/models/settings", token, {"lyrics_backend": "localsynth"})
        print("== restored localsynth", st)
    print("STAGE DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
