"""M5 联调补充核对：导出全链路 + F-6 正向 + 新作品作品库闭环
用法: python -X utf8 scripts/integration_check.py
"""
import json
import os
import sys
import time
import urllib.request

BASE = "http://localhost:5173/api/v1"  # 经 Vite 代理，等价于前端真实链路
TOKEN_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "meloyu_tok.txt")


def call(method, path, body=None, token=None, raw=False):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = r.read()
            return r.status, payload if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, payload if raw else json.loads(payload)
        except Exception:
            return e.code, payload


def main():
    tok = open(TOKEN_FILE, encoding="utf-8").read().strip()
    ok = []

    # 1. 找最近一次 generation 任务（联调刚生成的）
    st, d = call("GET", "/tasks?type=generation&page=1&page_size=5", token=tok)
    items = d["data"] if isinstance(d["data"], list) else d["data"].get("items", [])
    gen = [t for t in items if t["status"] == "succeeded"][0]
    print(f"[1] 最近生成任务 {gen['id'][:12]}… status={gen['status']}")
    rid = gen["result"]["work_id"] if "work_id" in (gen.get("result") or {}) else None
    if not rid:
        # 兜底：作品库第一页里找最新作品
        st, d = call("GET", "/works?page=1&page_size=10", token=tok)
        items = d["data"] if isinstance(d["data"], list) else d["data"].get("items", [])
        rid = items[0]["id"]
    st, d = call("GET", f"/works/{rid}", token=tok)
    w = d["data"]
    print(f"[2] 新作品 {w['display_code']} «{w.get('title')}» bpm={w.get('bpm')} key={w.get('key')}")
    ok.append(("作品详情", st == 200 and w["id"] == rid))

    st, d = call("GET", f"/works/{rid}/versions", token=tok)
    vid = d["data"]["current_version_id"]
    print(f"[3] 当前版本 {vid[:12]}…")
    st, d = call("GET", f"/versions/{vid}/candidates", token=tok)
    cands = d["data"] if isinstance(d["data"], list) else d["data"].get("items", [])
    print(f"[4] 候选 {len(cands)} 个: {[(c['label'], c['quality_score'], c['duration_sec']) for c in cands]}")
    ok.append(("候选2条", len(cands) >= 2))

    # 5. adopt 候选 B（版本树操作 + 留痕）；重复 adopt 返回 409 属正确幂等语义
    st, d = call("POST", f"/candidates/{cands[1]['id']}/adopt", token=tok)
    print(f"[5] adopt 候选B: HTTP {st} code={d.get('code')}")
    ok.append(("adopt", st in (200, 409)))

    # 6. 四种导出格式
    for fmt in ["mp3", "wav", "midi", "stems"]:
        st, d = call("POST", "/exports", {"version_id": vid, "format": fmt}, token=tok)
        if st not in (200, 201, 202):
            print(f"[6.{fmt}] 提交失败 HTTP {st}: {json.dumps(d, ensure_ascii=False)[:200]}")
            ok.append((f"导出{fmt}", False))
            continue
        etid = d["data"]["task"]["id"]
        for _ in range(60):
            st2, d2 = call("GET", f"/tasks/{etid}", token=tok)
            if d2["data"]["status"] in ("succeeded", "failed"):
                break
            time.sleep(1)
        t = d2["data"]
        files = (t.get("result") or {}).get("files", [])
        names = [(f["name"], f["bytes"]) for f in files]
        print(f"[6.{fmt}] {t['status']} -> {names}")
        ok.append((f"导出{fmt}", t["status"] == "succeeded" and len(files) >= 1))
        # 下载校验（取首个文件，走 Bearer 下载）
        st3, raw = call("GET", f"/files/{files[0]['file_id']}/download", token=tok, raw=True)
        magic = raw[:4]
        good = st3 == 200 and len(raw) == files[0]["bytes"] and (
            (fmt == "mp3" and (magic[:3] == b"ID3" or magic[0] == 0xFF))
            or (fmt == "wav" and magic == b"RIFF")
            or (fmt == "midi" and magic[:4] == b"MThd")
            or (fmt == "stems" and magic[:2] == b"PK")
        )
        print(f"      下载: HTTP {st3} {len(raw)}B magic={magic!r} -> {'OK' if good else 'FAIL'}")
        ok.append((f"下载{fmt}", good))

    # 7. F-6 正向：该作品导出任务过滤
    st, d = call("GET", f"/tasks?type=export&work_id={rid}", token=tok)
    items = d["data"] if isinstance(d["data"], list) else d["data"].get("items", [])
    print(f"[7] F-6 导出任务过滤: 该作品 {len(items)} 条 {[t['format'] for t in items]}")
    ok.append(("F-6过滤", len(items) >= 4))

    # 8. 编辑留痕事件
    st, d = call("GET", f"/works/{rid}/events", token=tok)
    evs = d["data"] if isinstance(d["data"], list) else d["data"].get("items", [])
    print(f"[8] 留痕事件: {len(evs)} 条 -> {[e.get('action') for e in evs][:8]}")
    ok.append(("留痕", any(e.get("action") == "adopt" for e in evs)))

    # 9. 收藏/标签 PATCH
    st, d = call("PATCH", f"/works/{rid}", {"favorite": True, "tags": ["联调", "国风"]}, token=tok)
    print(f"[9] PATCH favorite/tags: HTTP {st}")
    ok.append(("PATCH作品", st == 200))

    print("\n===== 结果 =====")
    for name, passed in ok:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    print(f"通过 {sum(1 for _, p in ok if p)}/{len(ok)}")
    sys.exit(0 if all(p for _, p in ok) else 1)


if __name__ == "__main__":
    main()
