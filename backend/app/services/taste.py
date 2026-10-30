"""我的口味服务（V2-b，v0.9.1）：作品库统计画像 + 参数预填建议。"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.i18n import tr
from app.models import Candidate, TasteProfile, User, Work
from app.models.base import utc_now_iso


def _median(vals: list[int]) -> int | None:
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else round((s[m - 1] + s[m]) / 2)


def rebuild(db: Session, user: User) -> dict:
    """扫描本人作品（active，含采用的候选参数）重建画像。幂等覆盖。"""
    works = db.execute(select(Work).where(
        Work.user_id == user.id, Work.status == "active")).scalars().all()
    bpms: list[int] = []
    keys: list[str] = []
    densities: list[int] = []
    vocals: Counter = Counter()
    languages: Counter = Counter()
    tags: Counter = Counter()
    sample = 0
    for w in works:
        if w.trashed_at:
            continue
        bpms.append(w.bpm)
        keys.append(f"{w.key_tonic} {w.key_mode}")
        sample += 1
        # 候选层参数（密度/人声/语言/风格标签来自最新版本的采用候选）
        if w.active_version_id:
            from app.models import Version
            v = db.get(Version, w.active_version_id)
            cand = (db.get(Candidate, v.active_candidate_id)
                    if v and v.active_candidate_id else None)
            if cand:
                p = (v.params or {}) if v else {}
                # 密度缺省 65（与生成参数默认 instrument_density 一致；
                # 画像只做统计建议值预填，不训练模型）
                densities.append(int(p.get("instrument_density", 65)))
                if cand.vocal and cand.vocal != "instrumental":
                    vocals[cand.vocal] += 1
                languages[cand.language] += 1
                for tg in (cand.style_tags or [])[:6]:
                    tags[tg] += 1
    profile: dict = {
        "bpm": _median(bpms),
        "key": Counter(keys).most_common(1)[0][0] if keys else None,
        "density": _median(densities),
        "vocal": vocals.most_common(1)[0][0] if vocals else None,
        "language": languages.most_common(1)[0][0] if languages else None,
        "top_tags": [t for t, _ in tags.most_common(6)],
    }
    row = db.execute(select(TasteProfile).where(
        TasteProfile.user_id == user.id)).scalars().first()
    if row is None:
        row = TasteProfile(user_id=user.id, profile=profile, sample_count=sample)
        db.add(row)
    else:
        row.profile = profile
        row.sample_count = sample
        row.updated_at = utc_now_iso()
    db.commit()
    return taste_to_dict(row)


def taste_to_dict(row: TasteProfile) -> dict:
    p = row.profile or {}
    return {
        "profile": p,
        "sample_count": row.sample_count,
        "updated_at": row.updated_at,
        # 语义说明（建议值预填，用户可改；不训练模型、不做隐式改写）
        "semantics": ("suggestions_only",
                      tr("画像为作品库统计建议值，一键预填后可自由修改；不训练模型",
                         "Profile is statistical suggestions from your library; "
                         "prefill freely editable; no model training")),
    }


def get(db: Session, user: User) -> dict:
    row = db.execute(select(TasteProfile).where(
        TasteProfile.user_id == user.id)).scalars().first()
    if row is None:
        return rebuild(db, user)  # 首次访问即懒构建
    return taste_to_dict(row)
