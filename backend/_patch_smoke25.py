# -*- coding: utf-8 -*-
"""向 smoke_test.py 插入第 25 节（占位转正批）。一次性脚本。"""
import ast
import io

P = "scripts/smoke_test.py"
s = io.open(P, encoding="utf-8").read()

BS = chr(92)  # backslash



PLAIN = """    # ============ 25. 占位转正批（v0.11.0）：哼唱成歌 / 旋律修调 / 自定义封面 / 联系通道 ============

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
        raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
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

    # ============ 汇总 ============"""

anchor = "    # ============ 汇总 ============"
assert anchor in s and "25. 占位转正批" not in s
s = s.replace(anchor, PLAIN, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
ast.parse(io.open(P, encoding="utf-8").read())
print("smoke section 25 inserted, syntax ok")
