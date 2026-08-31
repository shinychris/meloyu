"""导出编排：格式路由（wav/mp3/midi/stems zip），复用候选产物转码打包。"""
from __future__ import annotations

import wave as wav_mod
import zipfile
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_conflict, err_not_found
from app.core.logging import logger
from app.database import SessionLocal
from app.models import Candidate, File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.services import works as works_svc
from app.services.serializers import file_ref, task_to_dict
from app.synth.mp3_io import encode_mp3


def create_export(db: Session, user: User, version_id: str, fmt: str) -> dict:
    version = works_svc.get_version_owned(db, version_id, user)
    if not version.active_candidate_id:
        raise err_conflict("该版本尚未采用候选")
    now = utc_now_iso()
    task = Task(user_id=user.id, type="export", status="queued", progress=0,
                stage_key="queued", stage_label="排队中",
                work_id=version.work_id, version_id=version.id,
                format=fmt, cost_credits=0,
                request_payload={"version_id": version_id, "format": fmt},
                created_at=now, updated_at=now)
    db.add(task)
    db.commit()
    db.refresh(task)
    from app.core.tasks import schedule_export
    schedule_export(task.id)
    return {"task": task_to_dict(task)}


def execute_export(task_id: str) -> None:
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "running"
        task.started_at = utc_now_iso()
        task.updated_at = utc_now_iso()
        task.stage_key = "serialize"
        task.stage_label = "文件导出"
        task.progress = 30
        db.commit()
        fmt = task.format
        version_id = task.version_id

    try:
        with SessionLocal() as db:
            version = db.get(Version, version_id)
            work = db.get(Work, version.work_id)
            cand = db.get(Candidate, version.active_candidate_id)
            files = _export_artifacts(db, work, version, cand, fmt)
            now = utc_now_iso()
            task_row = db.get(Task, task_id)
            task_row.status = "succeeded"
            task_row.progress = 100
            task_row.stage_key = "done"
            task_row.stage_label = "完成"
            task_row.result = {"files": files}
            task_row.finished_at = now
            task_row.updated_at = now
            works_svc.add_event(db, user_id=task_row.user_id, action="export", actor="human",
                                detail={"task_id": task_id, "format": fmt,
                                        "file_ids": [f["file_id"] for f in files]},
                                work_id=work.id, version_id=version.id)
            db.commit()
        logger.info(f"export {task_id} ({fmt}) done")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"export {task_id} failed: {e}")
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t and t.status not in ("succeeded", "canceled"):
                t.status = "failed"
                t.error_code = 50002
                t.error_message = f"导出失败：{e}"
                t.finished_at = utc_now_iso()
                t.updated_at = utc_now_iso()
                db.commit()


def _candidate_file(db: Session, candidate_id: str, kind: str,
                    stem_name: str | None = None) -> File:
    from sqlalchemy import select
    q = select(File).where(File.candidate_id == candidate_id, File.kind == kind)
    if stem_name:
        q = q.where(File.stem_name == stem_name)
    f = db.execute(q).scalars().first()
    if not f:
        raise err_not_found(f"候选文件缺失：{kind}")
    return f


def _abs(path: str) -> Path:
    return (settings.audio_path / path).resolve()


def _register(db: Session, work: Work, version: Version, *, kind: str, relpath: str,
              mime: str, path: Path, duration_sec: float | None, name: str,
              stem_name: str | None = None) -> File:
    import hashlib

    from sqlalchemy import select
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    # 同路径已有登记且内容一致（导出对 version+candidate+format 确定）→ 复用，避免 UNIQUE(path) 冲突
    existing = db.execute(select(File).where(File.path == relpath)).scalars().first()
    if existing is not None:
        if existing.sha256 == digest:
            return existing
        # 内容不一致（理论上仅换候选后发生，路径已含候选标签则不会走到这里）：换唯一路径兜底
        suffix = utc_now_iso().replace("-", "").replace(":", "").replace("T", "").replace("Z", "")
        relpath = f"{relpath.rsplit('/', 1)[0]}/{path.stem}_{suffix}{path.suffix}"
    now = utc_now_iso()
    f = File(work_id=work.id, version_id=version.id, candidate_id=None, kind=kind,
             stem_name=stem_name, name=name, path=relpath, mime=mime,
             bytes=path.stat().st_size, duration_sec=duration_sec,
             sample_rate=48000 if path.suffix == ".wav" else None,
             sha256=digest, created_at=now, updated_at=now)
    db.add(f)
    db.flush()
    return f


def _export_artifacts(db: Session, work: Work, version: Version, cand: Candidate,
                      fmt: str) -> list[dict]:
    # 路径含候选标签：换候选重导出不会撞路径；同候选重导出由 _register 复用记录
    base = f"{work.id}/{version.id}/exports/{cand.label}"
    exports_dir = _abs(base)
    exports_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []

    # 外部模型候选（Suno 兼容通道）产物为整曲 mp3，无 WAV 母带/分轨/MIDI（ADR-010）
    master = _candidate_file(db, cand.id, "master")
    external_candidate = (master.mime or "").startswith("audio/mpeg")
    if external_candidate and fmt in ("wav", "midi", "stems"):
        raise err_conflict("该候选由外部歌曲模型生成（整曲 mp3），仅支持 MP3 导出；"
                           "WAV 母带/分轨/MIDI 为本地引擎产物")

    if fmt == "mp3":
        if external_candidate:
            # 母带即 mp3：直接复制（无 WAV 可解码，不做有损→有损二压）
            p = exports_dir / "export.mp3"
            p.write_bytes(_abs(master.path).read_bytes())
        else:
            with wav_mod.open(str(_abs(master.path)), "rb") as wf:
                n = wf.getnframes()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                raw = wf.readframes(n)
            data = _wav_bytes_to_float(raw, sw)
            if ch == 1:
                left = right = data
            else:
                left, right = data[0::2], data[1::2]
            p = exports_dir / "export.mp3"
            encode_mp3(p, left, right, bitrate=320)
        row = _register(db, work, version, kind="export_mp3", relpath=f"{base}/export.mp3",
                        mime="audio/mpeg", path=p, duration_sec=master.duration_sec,
                        name=f"{work.display_code}_{version.version_no}_export_mp3.mp3")
        out.append(file_ref(row))

    elif fmt == "wav":
        p = exports_dir / "master.wav"
        p.write_bytes(_abs(master.path).read_bytes())
        row = _register(db, work, version, kind="export_wav", relpath=f"{base}/master.wav",
                        mime="audio/wav", path=p, duration_sec=master.duration_sec,
                        name=f"{work.display_code}_{version.version_no}_export_wav.wav")
        out.append(file_ref(row))

    elif fmt == "midi":
        # 引擎在生成时已落盘 midi/（不登记 files），导出时复制登记
        cand_midi_dir = _abs(f"{work.id}/{version.id}/candidates/{cand.label}/midi")
        for stem in ("melody", "chords", "bass", "drums"):
            src = cand_midi_dir / f"{stem}.mid"
            if not src.exists():
                raise err_not_found(f"MIDI 文件缺失：{stem}")
            p = exports_dir / f"midi_{stem}.mid"
            p.write_bytes(src.read_bytes())
            row = _register(db, work, version, kind="export_midi",
                            relpath=f"{base}/midi_{stem}.mid", mime="audio/midi", path=p,
                            duration_sec=None,
                            name=f"{work.display_code}_{version.version_no}_export_midi_{stem}.mid")
            out.append(file_ref(row))

    elif fmt == "stems":
        zip_path = exports_dir / "stems.zip"
        stem_paths = []
        for stem in ("vocals", "drums", "bass", "other"):
            src_row = _candidate_file(db, cand.id, "stem", stem)
            src = _abs(src_row.path)
            stem_paths.append((f"{stem}.wav", src))
        write_zip(zip_path, stem_paths)
        row = _register(db, work, version, kind="export_stems_zip",
                        relpath=f"{base}/stems.zip", mime="application/zip", path=zip_path,
                        duration_sec=None,
                        name=f"{work.display_code}_{version.version_no}_export_stems.zip")
        out.append(file_ref(row))
        for stem in ("vocals", "drums", "bass", "other"):
            src_row = _candidate_file(db, cand.id, "stem", stem)
            src = _abs(src_row.path)
            p = exports_dir / f"stems_{stem}.wav"
            p.write_bytes(src.read_bytes())
            srow = _register(db, work, version, kind="stem", stem_name=stem,
                             relpath=f"{base}/stems_{stem}.wav", mime="audio/wav", path=p,
                             duration_sec=src_row.duration_sec,
                             name=f"{work.display_code}_{version.version_no}_stem_{stem}.wav")
            out.append(file_ref(srow))
    else:
        raise err_not_found(f"未知导出格式：{fmt}")
    return out


def _wav_bytes_to_float(raw: bytes, sampwidth: int) -> np.ndarray:
    if sampwidth == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        return v.astype(np.float64) / float(1 << 23)
    dt = "<i2" if sampwidth == 2 else "<i4"
    v = np.frombuffer(raw, dtype=dt).astype(np.float64)
    return v / float(1 << (8 * sampwidth - 1))


def write_zip(zip_path: Path, entries: list[tuple[str, Path]]) -> None:
    """确定性 zip：固定条目时间戳，保证同内容同 sha256。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, src in entries:
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, src.read_bytes())
