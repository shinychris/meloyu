"""授权证书：JSON 签发（契约 §8.4）+ certificates/files/edit_events 落库。"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import API_PREFIX
from app.core.errors import err_conflict
from app.models import Candidate, Certificate, EditEvent, File, User, Version, Work
from app.models.base import utc_now_iso
from app.repositories import counters
from app.services import works as works_svc

DISCLOSURE = ("本作品由 AI 辅助生成（Meloyu 本地合成引擎 {model}），"
              "人类创作参与记录见 human_participation。")

_ACTION_LABELS = [
    ("update", "歌词人工撰写/编辑"),
    ("adopt", "采用候选"),
    ("export", "导出"),
    ("certificate", "证书下载"),
    ("trash", "移入回收站"),
    ("restore", "恢复作品"),
]


def issue_certificate(db: Session, user: User, version: Version) -> tuple[dict, str]:
    """签发证书：返回 (cert_dict, 下载文件名)。每次下载 = 一次签发。"""
    if not version.active_candidate_id:
        raise err_conflict("该版本尚未采用候选")
    work = db.get(Work, version.work_id)
    cand = db.get(Candidate, version.active_candidate_id)
    master = db.execute(select(File).where(File.candidate_id == cand.id,
                                           File.kind == "master")).scalars().first()
    preview = db.execute(select(File).where(File.candidate_id == cand.id,
                                            File.kind == "preview")).scalars().first()

    now = utc_now_iso()
    today = datetime.now(UTC).strftime("%Y%m%d")
    cert_no = counters.next_counter(db, f"cert_{today}")
    cert_code = f"MY-CERT-{today}-{cert_no:06d}"

    events_count = db.execute(select(func.count()).select_from(EditEvent)
                              .where(EditEvent.work_id == work.id)).scalar_one()
    human_summary = _human_summary(db, work.id)

    license_type = "non_commercial" if user.plan == "free" else "commercial"
    cert_dict = {
        "certificate_id": cert_code,
        "work": {"id": work.id, "display_code": work.display_code, "title": work.title},
        "version": {"id": version.id, "version_no": version.version_no,
                    "active_candidate_id": version.active_candidate_id},
        "model": {"provider": "localsynth", "provider_display": "Meloyu 本地引擎",
                  "model": version.params.get("model", "v1_pro"), "seed": cand.seed},
        "generated_at": version.created_at,
        "license": {"type": license_type, "plan": user.plan, "valid": True},
        "human_participation": {
            "edit_events_count": events_count,
            "summary": human_summary,
            "events_ref": f"{API_PREFIX}/works/{work.id}/events",
        },
        "fingerprint": {
            "algorithm": "sha256",
            "master_wav_sha256": master.sha256 if master else "",
            "preview_mp3_sha256": preview.sha256 if preview else "",
        },
        "disclosure": DISCLOSURE.format(model=version.params.get("model", "v1_pro")),
        "issued_at": now,
    }

    # 落盘证书 JSON 文件并登记
    import hashlib

    from app.config import settings
    cert_dir = settings.audio_path / work.id / version.id / "certificates"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / f"{cert_code}.json"
    content = json.dumps(cert_dict, ensure_ascii=False, indent=2)
    cert_path.write_bytes(content.encode("utf-8"))  # 二进制写：避免 Windows 换行翻译破坏 sha256
    relpath = f"{work.id}/{version.id}/certificates/{cert_code}.json"
    frow = File(work_id=work.id, version_id=version.id, candidate_id=None,
                kind="certificate", stem_name=None,
                name=f"{work.display_code}_{version.version_no}_certificate.json",
                path=relpath, mime="application/json", bytes=cert_path.stat().st_size,
                duration_sec=None, sample_rate=None,
                sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                created_at=now, updated_at=now)
    db.add(frow)
    db.flush()

    db.add(Certificate(certificate_code=cert_code, work_id=work.id, version_id=version.id,
                       provider="localsynth", provider_display="Meloyu 本地引擎",
                       model=version.params.get("model", "v1_pro"), seed=cand.seed,
                       generated_at=version.created_at, license_type=license_type,
                       plan_at_issuance=user.plan, license_valid=True,
                       edit_events_count=events_count, human_summary=human_summary,
                       master_sha256=master.sha256 if master else "",
                       preview_sha256=preview.sha256 if preview else "",
                       disclosure=cert_dict["disclosure"], issued_at=now, file_id=frow.id,
                       created_at=now, updated_at=now))
    works_svc.add_event(db, user_id=user.id, action="certificate", actor="human",
                        detail={"certificate_code": cert_code}, work_id=work.id,
                        version_id=version.id)
    db.commit()
    filename = f"{work.display_code}_{version.version_no}_certificate.json"
    return cert_dict, filename


def _human_summary(db: Session, work_id: str) -> list[str]:
    rows = db.execute(select(EditEvent.action, EditEvent.actor, func.count())
                      .where(EditEvent.work_id == work_id)
                      .group_by(EditEvent.action, EditEvent.actor)).all()
    counts = {(a, actor): n for a, actor, n in rows}
    summary = []
    for action, label in _ACTION_LABELS:
        n = counts.get((action, "human"), 0)
        if n:
            summary.append(f"{label} {n} 次")
    return summary
