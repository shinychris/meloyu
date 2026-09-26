"""导出编排：格式路由（wav/mp3/midi/stems zip），复用候选产物转码打包。"""
from __future__ import annotations

import wave as wav_mod
import zipfile
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EXPORT_TASK_TIMEOUT_SEC, settings
from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.i18n import tr
from app.core.logging import logger
from app.database import SessionLocal
from app.models import Candidate, File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.services import works as works_svc
from app.services.serializers import file_ref, task_to_dict
from app.synth.mp3_io import encode_mp3


def create_export(db: Session, user: User, version_id: str, fmt: str,
                  platform: str | None = None, meta: dict | None = None) -> dict:
    from app.services.generation import _check_maintenance
    _check_maintenance()
    from app.core.disk_guard import ensure_disk_available
    ensure_disk_available()
    # P0-4（2026-09-26 商业化审查）：付费档核心权益后端强制——Plan.max_export
    # 此前无任何消费点，free 用户可直导 WAV/MIDI/Stems/发行包，付费档价值被架空。
    # 口径：max_export=="mp3"（free）仅允许 mp3；"wav"（pro/studio）放开全部格式。
    # 通道物理限制（外部通道候选无分轨/母带为 mp3 等）仍由执行期校验兜底。
    from app.models import Plan
    plan_row = db.get(Plan, user.plan)
    allowed = plan_row.max_export if plan_row else "mp3"
    if allowed == "mp3" and fmt != "mp3":
        from app.core.errors import err_payment_required
        raise err_payment_required(
            tr(f"{fmt.upper()} 导出为 Pro/Studio 档权益；免费档仅支持 MP3 导出",
               f"{fmt.upper()} export is a Pro/Studio benefit; "
               "the free plan exports MP3 only"))
    # P1-8：存储配额（导出产物同样计入占用）+ 每用户在途导出上限
    # （导出 0 积分，无上限可刷满导出池拖慢所有人）
    from sqlalchemy import func as _func
    from sqlalchemy import select as _select
    inflight = db.execute(
        _select(_func.count()).select_from(Task).where(
            Task.user_id == user.id, Task.type == "export",
            Task.status.in_(("queued", "running")))
    ).scalar_one()
    if inflight >= 3:
        raise err_conflict(
            tr("在途导出任务已达上限（3 个），请等待完成后再提交",
               "You already have 3 export task(s) running; wait for them to finish first"))
    from app.services.generation import check_storage_quota
    check_storage_quota(db, user)
    version = works_svc.get_version_owned(db, version_id, user)
    if not version.active_candidate_id:
        raise err_conflict(tr("该版本尚未采用候选", "No candidate adopted for this version yet"))
    payload = {"version_id": version_id, "format": fmt}
    if fmt == "release":
        # FR-11 发行导出预设：platform 已由 schema 校验（douyin/streaming）
        payload["platform"] = platform
        payload["meta"] = meta or {}
        payload["meta"].setdefault("title", work_title_of(db, version))
        payload["meta"].setdefault("artist", user_email_prefix(user))
        # v0.11.0：封面校验前移到提交期（40001 快速失败，不建任务不占队列）
        if (payload["meta"].get("cover_png_b64")):
            from app.services.release_export import preset_of as _preset_of
            validate_cover_png(payload["meta"]["cover_png_b64"],
                               _preset_of(platform)["cover_size"])
    now = utc_now_iso()
    task = Task(user_id=user.id, type="export", status="queued", progress=0,
                stage_key="queued", stage_label=tr("排队中", "Queued"),
                work_id=version.work_id, version_id=version.id,
                format=fmt, cost_credits=0,
                request_payload=payload,
                created_at=now, updated_at=now)
    db.add(task)
    db.commit()
    db.refresh(task)
    from app.core.tasks import schedule_export
    schedule_export(task.id)
    return {"task": task_to_dict(task)}


def validate_cover_png(b64: str, preset_size: tuple[int, int] = (3000, 3000)) -> bytes:
    """自定义封面校验（v0.11.0）：base64/PNG 魔数/≤4MB/≥600x600 → 返回字节。

    在 create_export（提交期，扣积分前 40001 快速失败）与 execute_export
    （执行期防御副本）两处调用，口径一致。
    """
    import base64 as _b64
    import struct as _st
    try:
        data = _b64.b64decode(str(b64), validate=True)
    except Exception as e:
        raise err_validation(tr("cover_png_b64 不是合法 base64",
                             "cover_png_b64 is not valid base64")) from e
    if not data.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))):
        raise err_validation(tr("自定义封面须为 PNG 图片",
                             "Custom cover must be a PNG image"))
    if len(data) > 4 * 1024 * 1024:
        raise err_validation(tr("自定义封面超过 4MB 上限",
                             "Custom cover exceeds the 4MB limit"))
    w = h = 0
    if len(data) > 24:
        w, h = _st.unpack(">II", data[16:24])
    if w < 600 or h < 600:
        raise err_validation(tr(
            f"自定义封面尺寸 {w}x{h} 过小（≥600x600，建议 {preset_size[0]}x{preset_size[1]}）",
            f"Custom cover {w}x{h} is too small (>=600x600; "
            f"{preset_size[0]}x{preset_size[1]} recommended)"))
    return data


def work_title_of(db: Session, version: Version) -> str:
    work = db.get(Work, version.work_id)
    return work.title if work else ""


def user_email_prefix(user: User) -> str:
    return (user.email or "").split("@", 1)[0] or "artist"


def execute_export(task_id: str) -> None:
    import time as _time
    deadline = _time.monotonic() + EXPORT_TASK_TIMEOUT_SEC
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "running"
        task.started_at = utc_now_iso()
        task.updated_at = utc_now_iso()
        task.stage_key = "serialize"
        task.stage_label = tr("文件导出", "Exporting files")
        task.progress = 30
        db.commit()
        fmt = task.format
        version_id = task.version_id
        payload = task.request_payload or {}

    try:
        with SessionLocal() as db:
            version = db.get(Version, version_id)
            work = db.get(Work, version.work_id)
            cand = db.get(Candidate, version.active_candidate_id)
            files = _export_artifacts(db, work, version, cand, fmt, payload,
                                      deadline=deadline)
            now = utc_now_iso()
            task_row = db.get(Task, task_id)
            task_row.status = "succeeded"
            task_row.progress = 100
            task_row.stage_key = "done"
            task_row.stage_label = tr("完成", "Done")
            task_row.result = {"files": files}
            task_row.finished_at = now
            task_row.updated_at = now
            works_svc.add_event(db, user_id=task_row.user_id, action="export", actor="human",
                                detail={"task_id": task_id, "format": fmt,
                                        "platform": payload.get("platform"),
                                        "file_ids": [f["file_id"] for f in files]},
                                work_id=work.id, version_id=version.id)
            db.commit()
        logger.info(f"export {task_id} ({fmt}) done")
    except TimeoutError as e:
        logger.error(f"export {task_id} timed out after {EXPORT_TASK_TIMEOUT_SEC}s")
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t and t.status not in ("succeeded", "canceled"):
                t.status = "failed"
                t.error_code = 50002
                t.error_message = tr("导出失败：超时 ", "Export failed: timeout ") + str(e)
                t.finished_at = utc_now_iso()
                t.updated_at = utc_now_iso()
                db.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception(f"export {task_id} failed: {e}")
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t and t.status not in ("succeeded", "canceled"):
                t.status = "failed"
                t.error_code = 50002
                t.error_message = tr("导出失败：", "Export failed: ") + str(e)
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
        raise err_not_found(tr(f"候选文件缺失：{kind}", f"Candidate file missing: {kind}"))
    return f


def _abs(path: str) -> Path:
    return (settings.audio_path / path).resolve()


def _register(db: Session, work: Work, version: Version, *, kind: str, relpath: str,
              mime: str, path: Path, duration_sec: float | None, name: str,
              stem_name: str | None = None, sample_rate: int | None = None) -> File:
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
             sample_rate=sample_rate,
             sha256=digest, created_at=now, updated_at=now)
    db.add(f)
    db.flush()
    return f


def _wav_sample_rate(path: Path) -> int | None:
    """读 wav 头取真实采样率（外部模型母带可能是 32kHz 等，非本地引擎 48kHz）。"""
    try:
        with wav_mod.open(str(path), "rb") as wf:
            return wf.getframerate()
    except Exception:  # noqa: BLE001 —— 头解析失败不阻断导出，登记留空
        return None


def _mark_aigc(path: Path, fmt: str, attribution: str | None = None) -> None:
    """P0-3/义务③：导出产物写入 AIGC 显式标识（mp3=ID3v2 / wav=RIFF LIST）。

    attribution 为引擎署名（如 "MiniMax-Music3 (self-hosted)"）——AUP 第 11 条
    机器生成内容披露含生成来源。标识写入失败不阻断导出（记日志）。
    """
    from app.synth.id3 import mark_mp3, mark_wav
    try:
        data = path.read_bytes()
        marked = (mark_mp3(data, attribution) if fmt == "mp3"
                  else mark_wav(data, attribution))
        if marked != data:
            path.write_bytes(marked)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"AIGC marking failed for {path.name}: {e}")


def _make_export_mp3(exports_dir: Path, master: File) -> tuple[Path, int | None]:
    """母带 → export.mp3（mp3 母带直接复制防二压；wav 按真实采样率 320k 编码）。"""
    if (master.mime or "").startswith("audio/mpeg"):
        p = exports_dir / "export.mp3"
        p.write_bytes(_abs(master.path).read_bytes())
        return p, None
    with wav_mod.open(str(_abs(master.path)), "rb") as wf:
        n = wf.getnframes()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        src_rate = wf.getframerate()
        raw = wf.readframes(n)
    data = _wav_bytes_to_float(raw, sw)
    if ch == 1:
        left = right = data
    else:
        left, right = data[0::2], data[1::2]
    p = exports_dir / "export.mp3"
    # 按母带真实采样率编码：外部模型母带可能非 48kHz（如 MusicGen 32kHz），
    # 若按默认 48k 编码会把全部样本时间轴压缩（时长缩水、变速变调）
    encode_mp3(p, left, right, bitrate=320, sample_rate=src_rate)
    return p, src_rate


def _make_export_wav(exports_dir: Path, master: File) -> Path:
    """母带 wav 复制（导出登记与 AIGC 标识由调用方处理）。"""
    p = exports_dir / "master.wav"
    p.write_bytes(_abs(master.path).read_bytes())
    return p


def _check_deadline(deadline: float | None) -> None:
    """导出软超时（P1-10）：阶段边界检查，超时抛 TimeoutError 判失败。"""
    import time as _time
    if deadline is not None and _time.monotonic() > deadline:
        raise TimeoutError(f"exceeded {EXPORT_TASK_TIMEOUT_SEC}s export budget")


def _export_artifacts(db: Session, work: Work, version: Version, cand: Candidate,
                      fmt: str, payload: dict | None = None,
                      deadline: float | None = None) -> list[dict]:
    # 路径含候选标签：换候选重导出不会撞路径；同候选重导出由 _register 复用记录
    base = f"{work.id}/{version.id}/exports/{cand.label}"
    exports_dir = _abs(base)
    exports_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    _check_deadline(deadline)

    # 模型整曲候选（Suno 兼容 API / Replicate / 本机 MusicGen）无分轨与 MIDI；
    # wav 母带是否可导出取决于产物格式（Replicate/MusicGen 有 wav，Suno 网关仅 mp3）
    master = _candidate_file(db, cand.id, "master")
    # 义务①③：导出标识带生成引擎署名（固定英文，不随请求 locale 漂移）
    from app.services.certificate import _version_provider, provider_attribution
    _, provider_name = _version_provider(db, version)
    attribution = provider_attribution(provider_name)
    has_stems = db.execute(
        select(File.id).where(File.candidate_id == cand.id, File.kind == "stem")
    ).first() is not None
    mp3_master = (master.mime or "").startswith("audio/mpeg")
    if fmt in ("midi", "stems") and not has_stems:
        raise err_conflict(
            tr("该候选为模型整曲产物（无分轨/MIDI）；分轨与 MIDI 为本地引擎产物",
               "This candidate is a whole-song model output (no stems/MIDI); "
               "stems and MIDI come from the local engine only"))
    if fmt == "wav" and mp3_master:
        raise err_conflict(
            tr("该候选母带为 mp3（外部歌曲 API 通道），仅支持 MP3 导出",
               "This candidate's master is mp3 (external song API channel); "
               "only MP3 export is supported"))

    if fmt == "mp3":
        _check_deadline(deadline)
        p, src_rate = _make_export_mp3(exports_dir, master)
        _mark_aigc(p, "mp3", attribution)
        row = _register(db, work, version, kind="export_mp3", relpath=f"{base}/export.mp3",
                        mime="audio/mpeg", path=p, duration_sec=master.duration_sec,
                        name=f"{work.display_code}_{version.version_no}_export_mp3.mp3",
                        sample_rate=src_rate)
        out.append(file_ref(row))

    elif fmt == "wav":
        _check_deadline(deadline)
        p = _make_export_wav(exports_dir, master)
        _mark_aigc(p, "wav", attribution)
        row = _register(db, work, version, kind="export_wav", relpath=f"{base}/master.wav",
                        mime="audio/wav", path=p, duration_sec=master.duration_sec,
                        name=f"{work.display_code}_{version.version_no}_export_wav.wav",
                        sample_rate=_wav_sample_rate(p))
        out.append(file_ref(row))

    elif fmt == "midi":
        # 引擎在生成时已落盘 midi/（不登记 files），导出时复制登记
        cand_midi_dir = _abs(f"{work.id}/{version.id}/candidates/{cand.label}/midi")
        for stem in ("melody", "chords", "bass", "drums"):
            src = cand_midi_dir / f"{stem}.mid"
            if not src.exists():
                raise err_not_found(tr(f"MIDI 文件缺失：{stem}", f"MIDI file missing: {stem}"))
            _check_deadline(deadline)
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
            _check_deadline(deadline)
            src_row = _candidate_file(db, cand.id, "stem", stem)
            src = _abs(src_row.path)
            p = exports_dir / f"stems_{stem}.wav"
            p.write_bytes(src.read_bytes())
            _mark_aigc(p, "wav", attribution)
            srow = _register(db, work, version, kind="stem", stem_name=stem,
                             relpath=f"{base}/stems_{stem}.wav", mime="audio/wav", path=p,
                             duration_sec=src_row.duration_sec,
                             name=f"{work.display_code}_{version.version_no}_stem_{stem}.wav")
            out.append(file_ref(srow))
    elif fmt == "release":
        # FR-11 发行导出预设（v0.8.0）：平台模板打包（音频+封面占位+metadata+README）
        _check_deadline(deadline)
        from app.services.release_export import (
            build_metadata,
            build_readme,
            preset_of,
            write_release_zip,
        )
        platform = (payload or {}).get("platform") or "douyin"
        preset = preset_of(platform)
        meta = (payload or {}).get("meta") or {}
        # v0.11.0 自定义封面：base64 PNG 优先于程序占位图（校验见 validate_cover_png）
        cover_png_bytes: bytes | None = None
        if meta.get("cover_png_b64"):
            cover_png_bytes = validate_cover_png(meta["cover_png_b64"],
                                                 preset["cover_size"])
        if preset["audio"] == "wav" and mp3_master:
            raise err_conflict(
                tr("流媒体发行预设需 WAV 母带；该候选母带为 mp3（外部歌曲 API 通道），请改用抖音预设",
                   "Streaming preset requires a WAV master; this candidate's master is mp3 "
                   "(external song API channel) — use the Douyin preset instead"))
        if preset["audio"] == "mp3":
            audio, src_rate = _make_export_mp3(exports_dir, master)
            arcname = "audio.mp3"
        else:
            audio = _make_export_wav(exports_dir, master)
            src_rate = _wav_sample_rate(audio)
            arcname = "audio.wav"
        _mark_aigc(audio, preset["audio"], attribution)
        work_snap = {
            "work_id": work.id, "display_code": work.display_code,
            "version_id": version.id, "version_no": version.version_no,
            "title": work.title, "bpm": work.bpm,
            "key": f"{work.key_tonic} {work.key_mode}",
            "duration_sec": work.duration_sec, "model": work.model,
        }
        aigc = {
            "engine_attribution": attribution,
            "ai_generated": True,
            # FR-16 披露协助：双语披露语与证书同口径（不随下载者 locale 漂移）
            "disclosure": (f"本作品由 AI 辅助生成（{attribution}），人类创作参与记录见授权证书。"
                           f"This work was created with AI assistance ({attribution}); "
                           f"see the license certificate for human participation records."),
            # v0.10.2 修正：证书路由实际为 /versions/{id}/certificate（旧 works 前缀路径 404）；
            # 外部平台无法携带 JWT 访问该端点，凭 display_code+版本在站内「合规与权利中心」可验
            "certificate_endpoint": f"/api/v1/versions/{version.id}/certificate",
            "certificate_ref": f"{work.display_code} / {version.version_no}",
        }
        metadata_json = build_metadata(platform=platform, preset=preset, meta=meta,
                                       work=work_snap, aigc=aigc)
        readme_txt = build_readme(platform=platform, preset=preset,
                                  entries=[arcname, "cover.png", "metadata.json", "README.txt"])
        zip_path = exports_dir / f"release_{platform}.zip"
        write_release_zip(zip_path, platform=platform, audio_arcname=arcname,
                          audio_path=audio, cover_size=preset["cover_size"],
                          cover_color=work.cover_color,
                          metadata_json=metadata_json, readme_txt=readme_txt,
                          cover_png_bytes=cover_png_bytes)
        row = _register(db, work, version, kind="export_release_zip",
                        relpath=f"{base}/release_{platform}.zip", mime="application/zip",
                        path=zip_path, duration_sec=master.duration_sec,
                        name=f"{work.display_code}_{version.version_no}_release_{platform}.zip",
                        sample_rate=src_rate)
        out.append(file_ref(row))
    else:
        raise err_not_found(tr(f"未知导出格式：{fmt}", f"Unknown export format: {fmt}"))
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
