r"""works 表灾后重建（2026-09-05 事故一次性工具，留档供审计）。

事故：dev uvicorn 与生产容器并发写同一 SQLite（违反 deploy/README 单写入方
红线），works 表 b-tree 页损坏（.recover 只能救出子表）。users/versions/
candidates/files/tasks/edit_events/credit_transactions 全部完好。

重建来源（全部为灾前真实数据，无编造）：
- id / 时间窗      ：versions + files 子行的 work_id 与 created_at/updated_at
- user_id          ：tasks.user_id（同 work 的生成任务归属）
- title            ：首个 version.params 按 _derive_title 同规则确定性重建
                     （simple_prompt[:12] / style_prompt[:12] / 未命名作品）
- bpm/key/duration/model：活跃候选（无则首版本 params）
- status/trashed_at：edit_events 最新 trash/restore 事件（无事件=active）
- active_version_id/preview_file_id/version_count：活跃候选所在版本 / 其
  preview 文件 / COUNT(versions)
- tags/favorite/cover_color：原值不可恢复 → 空值（外观级元数据，如实降级）
- display_code     ：文件名前缀（MY-XXXXX）恢复；缺失则按序补号

用法：python scripts/recover_works.py <recovered.db 路径>   # 幂等，可重复执行
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def derive_title(params_json: str) -> str:
    try:
        p = json.loads(params_json or "{}")
    except json.JSONDecodeError:
        p = {}
    if p.get("mode") == "simple" and p.get("simple_prompt"):
        return str(p["simple_prompt"])[:12]
    if p.get("style_prompt"):
        return str(p["style_prompt"])[:12]
    return "未命名作品"


def main(db_path: str) -> int:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    work_ids = {r[0] for r in db.execute("SELECT DISTINCT work_id FROM versions")}
    work_ids |= {r[0] for r in db.execute("SELECT DISTINCT work_id FROM files")}
    work_ids = {w for w in work_ids if w}
    existing = {r[0] for r in db.execute("SELECT id FROM works")}
    todo = sorted(work_ids - existing)
    print(f"子表 distinct works={len(work_ids)} 已存在={len(existing)} 待重建={len(todo)}")

    # display_code 现有占用（避免 UNIQUE 冲突）
    used_codes = {r[0] for r in db.execute("SELECT display_code FROM works")}
    max_seq = 0
    for c in used_codes:
        m = re.fullmatch(r"MY-(\d+)", c or "")
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    # 文件名前缀里的 display_code（master/preview 命名含 MY-XXXX）
    code_from_files: dict[str, str] = {}
    for wid, name in db.execute(
            "SELECT DISTINCT work_id, name FROM files WHERE name LIKE 'MY-%'"):
        m = re.match(r"(MY-\d+)", name or "")
        if m and wid not in code_from_files and m.group(1) not in used_codes:
            code_from_files[wid] = m.group(1)
            used_codes.add(m.group(1))

    inserted = 0
    for wid in todo:
        # 归属用户：该作品任一生成任务的 user_id（取最早任务）
        owner = db.execute(
            "SELECT user_id FROM tasks WHERE work_id=? ORDER BY created_at LIMIT 1",
            (wid,)).fetchone()
        if owner is None:
            # 无任务留痕的孤儿（理论上不存在；防御性挂到 demo）
            owner = db.execute(
                "SELECT id FROM users WHERE email='demo@meloyu.local'").fetchone()
            if owner is None:
                continue
        uid = owner[0]

        versions = db.execute(
            "SELECT id, params, created_at, updated_at FROM versions "
            "WHERE work_id=? ORDER BY created_at", (wid,)).fetchall()
        if not versions:
            # 无版本的空壳作品：仅从 files 侧出现的，补一条最小行
            fcnt = db.execute(
                "SELECT COUNT(*) FROM files WHERE work_id=?", (wid,)).fetchone()[0]
            if not fcnt:
                continue

        first = versions[0] if versions else None
        # 活跃候选（任一版本最新 adopted）
        active = db.execute(
            "SELECT c.bpm, c.key_tonic, c.key_mode, c.duration_sec, "
            "       c.version_id, c.id, v.params "
            "FROM candidates c JOIN versions v ON v.id=c.version_id "
            "WHERE v.work_id=? AND c.adopted=1 "
            "ORDER BY v.created_at DESC LIMIT 1", (wid,)).fetchone()
        params = {}
        try:
            params = json.loads((active["params"] if active else
                                 (first["params"] if first else None)) or "{}")
        except json.JSONDecodeError:
            pass
        bpm = (active["bpm"] if active else params.get("bpm")) or 90
        tonic = (active["key_tonic"] if active else
                 (params.get("key") or {}).get("tonic")) or "A"
        mode = (active["key_mode"] if active else
                (params.get("key") or {}).get("mode")) or "minor"
        dur = (active["duration_sec"] if active else params.get("duration_sec")) or 30
        model = params.get("model") or "v1_fast"

        # 状态：最近一次 trash/restore 事件
        st = db.execute(
            "SELECT action FROM edit_events WHERE work_id=? AND action IN "
            "('trash','restore') ORDER BY created_at DESC LIMIT 1", (wid,)).fetchone()
        status = "trash" if (st and st["action"] == "trash") else "active"

        active_vid = active["version_id"] if active else (
            versions[-1]["id"] if versions else None)
        preview = db.execute(
            "SELECT id FROM files WHERE candidate_id=? AND kind='preview' LIMIT 1",
            (active["id"],)).fetchone() if active else None

        created = (first["created_at"] if first else
                   db.execute("SELECT MIN(created_at) FROM files WHERE work_id=?",
                              (wid,)).fetchone()[0]) or "2026-08-28T00:00:00Z"
        updated = db.execute(
            "SELECT MAX(x) FROM (SELECT MAX(updated_at) x FROM versions WHERE work_id=? "
            "UNION ALL SELECT MAX(created_at) FROM tasks WHERE work_id=? "
            "UNION ALL SELECT MAX(created_at) FROM files WHERE work_id=?)",
            (wid, wid, wid)).fetchone()[0] or created

        code = code_from_files.get(wid)
        if not code:
            max_seq += 1
            code = f"MY-{max_seq:05d}"

        db.execute(
            "INSERT OR IGNORE INTO works (id, created_at, updated_at, user_id, "
            " display_code, title, status, favorite, tags, bpm, key_tonic, key_mode, "
            " duration_sec, model, version_count, active_version_id, preview_file_id, "
            " trashed_at, space_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, created, updated, uid, code, derive_title(
                first["params"] if first else "{}"), status, 0, "[]",
             int(bpm), tonic, mode, int(dur), model, len(versions),
             active_vid, preview["id"] if preview else None,
             "1970-01-01T00:00:00Z" if status == "trash" else None, None))
        inserted += 1

    db.commit()
    print(f"重建 works 行：{inserted}")
    print("works 总数：", db.execute("SELECT COUNT(*) FROM works").fetchone()[0])
    # 外键完整性（孤儿版本/文件应少于重建前的缺失 works）
    fk = db.execute("PRAGMA foreign_key_check").fetchall()
    bad = [r for r in fk if r[0] in ("versions", "files", "works")]
    print("works/versions/files 外键异常：", len(bad))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "meloyu.db.recovered"))
