"""参考音轨服务（v0.8.1）：上传、特征分析、列表、删除与生成参数应用。

上传协议（octet-stream，零新依赖——不引入 python-multipart）：
- POST /reference-tracks?filename=xx.mp3&ack_rights=true   body=原始音频字节
- POST /reference-tracks/{id}/analysis-wav                  body=浏览器解码的 PCM wav
  （mp3/m4a 服务端不解码；前端 AudioContext 渲染 mono wav 后补传，服务端才可分析）

合规：参考=特征级（BPM/调性/能量/亮度），生成不使用参考波形（非采样）；
上传须 ack_rights=true（确认拥有音频权利），落库留痕。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.i18n import tr
from app.core.logging import logger
from app.models import ReferenceTrack, User
from app.models.base import utc_now_iso
from app.services import reference_analysis

# 上传约束（≤8min；大小上限防滥用）
ALLOWED_EXTS = (".mp3", ".wav", ".m4a")
MIME_BY_EXT = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
MAX_BYTES = 50 * 1024 * 1024
MAX_DURATION_SEC = 480  # 8 分钟

# 前端固定展示的合规提示（双语，不随 locale 漂移——上传确认文案）
REFERENCE_NOTICE = ("参考仅提取节奏/调性/能量等特征用于参数化生成，不使用原音频波形（非采样）；"
                    "上传即确认你拥有该音频的相关权利。"
                    "Reference extraction only (tempo/key/energy features) — no waveform "
                    "sampling; by uploading you confirm you hold the rights to this audio.")


def _track_dir(user_id: str) -> Path:
    d = settings.audio_path / "reference" / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def track_to_dict(t: ReferenceTrack) -> dict:
    return {
        "id": t.id, "name": t.name, "mime": t.mime, "bytes": t.bytes,
        "duration_sec": t.duration_sec, "sha256": t.sha256,
        "ack_rights": t.ack_rights,
        "analysis": t.analysis,
        "analyzed": t.analysis is not None,
        "notice": REFERENCE_NOTICE,
        "created_at": t.created_at,
    }


def create_track(db: Session, user: User, *, filename: str, content: bytes) -> dict:
    #（2026-09-09）：文件名入库前消毒——去路径分量（../、盘符、
    # 目录分隔符）与控制字符（CRLF 等），防元数据污染；落盘名本就是服务端
    # UUID，此处仅影响展示与后续 Content-Disposition 回显
    name = Path((filename or "").replace("\\", "/")).name.strip()
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTS or not name or len(name) > 120:
        raise err_validation(
            tr(f"filename 须为 {'/'.join(ALLOWED_EXTS)} 且 1~120 字符",
               f"filename must be one of {'/'.join(ALLOWED_EXTS)}, 1-120 chars"))
    if len(content) > MAX_BYTES:
        raise err_validation(tr("参考音频超过 50MB 上限", "Reference audio exceeds the 50MB limit"))
    if not content:
        raise err_validation(tr("上传内容为空", "Upload body is empty"))
    from app.core.disk_guard import ensure_disk_available
    ensure_disk_available(extra_bytes=len(content))

    now = utc_now_iso()
    track = ReferenceTrack(user_id=user.id, name=name,
                           path="", mime=MIME_BY_EXT[ext], bytes=len(content),
                           sha256=_sha256(content), ack_rights=True,
                           created_at=now, updated_at=now)
    db.add(track)
    db.flush()
    p = _track_dir(user.id) / f"{track.id}{ext}"
    p.write_bytes(content)
    track.path = str(p.relative_to(settings.audio_path)).replace("\\", "/")
    if ext == ".wav":
        # wav 原件可直接分析（同步，秒级）；时长超限拒绝登记
        try:
            analysis = reference_analysis.analyze_wav(p)
        except Exception as e:  # noqa: BLE001 —— 损坏 wav 不阻断登记，标记未分析
            logger.warning(f"reference analysis failed for {track.id}: {e}")
        else:
            if analysis["duration_sec"] > MAX_DURATION_SEC:
                p.unlink(missing_ok=True)
                db.rollback()
                raise err_validation(
                    tr(f"参考音频时长 {analysis['duration_sec']:.0f}s 超过 8 分钟上限",
                       f"Reference audio is {analysis['duration_sec']:.0f}s, "
                       "exceeding the 8-minute limit"))
            track.analysis = analysis
            track.duration_sec = analysis["duration_sec"]
    db.commit()
    db.refresh(track)
    return track_to_dict(track)


def attach_analysis_wav(db: Session, user: User, track_id: str, content: bytes) -> dict:
    """mp3/m4a 的浏览器解码渲染补传（mono wav）→ 服务端分析。幂等：覆盖旧分析。"""
    track = get_owned(db, user, track_id)
    if len(content) > MAX_BYTES:
        raise err_validation(tr("分析音频超过 50MB 上限", "Analysis wav exceeds the 50MB limit"))
    p = _track_dir(user.id) / f"{track.id}_analysis.wav"
    p.write_bytes(content)
    try:
        analysis = reference_analysis.analyze_wav(p)
    except Exception as e:  # noqa: BLE001
        # 解析失败不留残盘（2026-10-27 对齐 voice.py 同场景行为）
        p.unlink(missing_ok=True)
        raise err_validation(
            tr(f"分析失败：wav 无法解析（{e}）",
               f"Analysis failed: cannot parse wav ({e})")) from e
    if analysis["duration_sec"] > MAX_DURATION_SEC:
        p.unlink(missing_ok=True)
        raise err_validation(
            tr(f"参考音频时长 {analysis['duration_sec']:.0f}s 超过 8 分钟上限",
               f"Reference audio is {analysis['duration_sec']:.0f}s, exceeding the 8-minute limit"))
    track.analysis = analysis
    track.duration_sec = analysis["duration_sec"]
    track.updated_at = utc_now_iso()
    db.commit()
    db.refresh(track)
    return track_to_dict(track)


def get_owned(db: Session, user: User, track_id: str) -> ReferenceTrack:
    track = db.get(ReferenceTrack, track_id)
    if track is None:
        raise err_not_found(tr("参考音频不存在", "Reference track not found"))
    if track.user_id != user.id:
        raise err_not_found(tr("参考音频不存在", "Reference track not found"))
    return track


def list_tracks(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
    q = (select(ReferenceTrack).where(ReferenceTrack.user_id == user.id)
         .order_by(ReferenceTrack.created_at.desc(), ReferenceTrack.id.desc()))
    total = len(db.execute(select(ReferenceTrack.id)
                           .where(ReferenceTrack.user_id == user.id)).all())
    rows = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"items": [track_to_dict(t) for t in rows], "total": total,
            "page": page, "page_size": page_size}


def delete_track(db: Session, user: User, track_id: str) -> dict:
    track = get_owned(db, user, track_id)
    for rel in (track.path,):
        p = settings.audio_path / rel
        p.unlink(missing_ok=True)
    (settings.audio_path / "reference" / user.id / f"{track.id}_analysis.wav").unlink(missing_ok=True)
    db.delete(track)
    db.commit()
    return {"ok": True}


def apply_to_params(params: dict, analysis: dict) -> dict:
    """参考特征 → 生成参数（覆盖 bpm/调性/器乐密度；时长与人生参数保持用户选择）。

    返回应用后的新 params dict（不改入参）。BPM 折进 [60,174]、能量线性映射密度。
    """
    out = dict(params)
    out["bpm"] = int(max(60, min(174, analysis["bpm"])))
    out["key"] = {"tonic": analysis["key_tonic"], "mode": analysis["key_mode"]}
    out["instrument_density"] = int(round(max(0, min(100, analysis["energy"] * 100))))
    return out


def resolve_for_generation(db: Session, user: User, track_id: str) -> ReferenceTrack:
    track = get_owned(db, user, track_id)
    if track.analysis is None:
        raise err_conflict(
            tr("参考音频尚未完成特征分析（mp3/m4a 需浏览器解码后补传分析音频）",
               "Reference track has no feature analysis yet (mp3/m4a needs the "
               "browser-decoded wav attached first)"))
    return track
