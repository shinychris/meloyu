"""生成编排：扣积分→建任务→线程池执行→进度回写→候选落库→失败退款。

任务状态机与线程池见 core/tasks.py；本模块只做业务编排。
"""
from __future__ import annotations

import shutil
import time
from datetime import UTC
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import GENERATION_TASK_TIMEOUT_SEC, MODEL_CREDIT_COST, settings
from app.core.errors import (
    err_conflict,
    err_forbidden,
    err_not_found,
    err_payment_required,
    err_sensitive,
    err_validation,
)
from app.core.i18n import current_locale, tr
from app.core.logging import logger
from app.core.seed import cover_color_for_seed, derive_seed
from app.database import SessionLocal
from app.models import Candidate, File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.providers.base import SynthCancelled, stage_label
from app.providers.lyrics_local import check_sensitive
from app.services import model_center
from app.services import works as works_svc
from app.services.serializers import candidate_to_dict, task_to_dict
from app.synth.ir import SongRequest

# ---------- 提交 ----------

def expand_simple_prompt(simple_prompt: str) -> str:
    """simple 模式：一句话扩写为 style_prompt（规则引擎，LLM 不可用时的兜底）。"""
    base = (simple_prompt or "").strip().rstrip("。，,.")
    if current_locale() != "zh":
        return f"{base}, pop arrangement, piano with string pads, clear lead vocal, natural emotional flow"
    return f"{base}，流行编曲，钢琴与弦乐铺底，人声旋律清晰，情绪自然流动"


_STYLE_EXPAND_SYSTEM = (
    "你是音乐制作总监。把用户的一句话创意扩写成 30~60 字的中文风格描述，"
    "涵盖编曲思路、乐器、情绪与节奏；只输出风格描述本身，不要解释或引号。"
)
_STYLE_EXPAND_SYSTEM_EN = (
    "You are a music production director. Expand the user's one-line idea into an "
    "English style description of roughly 30-60 words, covering arrangement, "
    "instruments, mood, and tempo. Output only the style description itself - no "
    "explanations, no quotes."
)


def expand_style_by_llm(chat, simple_prompt: str) -> str:
    """simple 模式风格扩写（走歌词引擎同一 LLM 配置）；失败/坏输出返回空串由规则兜底。

    按提交请求的 locale 要求对应语言的风格描述（en 用户不产出中文风格文案）；
    长度校验/截断阈值随语言分别设定（zh 按字符、en 按词折算的字符量）。
    """
    try:
        en = current_locale() != "zh"
        system = _STYLE_EXPAND_SYSTEM_EN if en else _STYLE_EXPAND_SYSTEM
        user = (f"One-line idea: {simple_prompt}" if en
                else f"一句话创意：{simple_prompt}")
        text = chat(system, user).strip()
        text = text.strip('"“”‘’').strip()
        if en:
            return text[:240] if 20 <= len(text) <= 400 else ""
        return text[:120] if 8 <= len(text) <= 200 else ""
    except Exception as e:  # noqa: BLE001 —— 扩写失败回退规则拼接，不阻断生成
        logger.warning(f"LLM 风格扩写失败，回退规则引擎: {e}")
        return ""


def resolve_generation_request(payload: dict) -> dict:
    """规范化请求：simplified 减半、seed 派生，标记延迟任务。

    V1.3 起（ADR-011）：simple 扩写与歌词自动生成延迟到执行线程完成
    （统一走模型中心配置的真实 LLM，本地规则仅作回退），提交接口保持快速返回；
    seed 以提交时的规范化参数派生，确定性语义不变。
    """
    mode = payload.get("mode", "simple")
    simplified = bool(payload.get("simplified", False))
    params = dict(payload.get("params") or {})

    if mode == "simple":
        # 未扩写原文：仅用于 seed 派生与标题；真实扩写在执行线程完成
        style_prompt = (payload.get("simple_prompt") or "").strip()
    else:
        style_prompt = payload.get("style_prompt") or ""
    if simplified and style_prompt:
        parts = [p for p in style_prompt.replace("，", ",").split(",") if p.strip()]
        style_prompt = "，".join(p.strip() for p in parts[: max(1, len(parts) // 2)])

    lyrics = payload.get("lyrics") or ""
    vocal = params.get("vocal", "female_air")
    auto_lyrics = (not lyrics) and vocal != "instrumental"

    full_params = {
        "mode": mode, "style_prompt": style_prompt,
        "negative_prompt": payload.get("negative_prompt") or "",
        "model": payload.get("model") or "v1_pro",
        "bpm": params.get("bpm", 90),
        "key": params.get("key", {"tonic": "A", "mode": "minor"}),
        "time_signature": params.get("time_signature", "4/4"),
        "duration_sec": params.get("duration_sec", 210),
        "vocal": vocal, "language": params.get("language", "zh"),
        "instrument_density": params.get("instrument_density", 65),
        "voice_profile_id": params.get("voice_profile_id"),
        "hum_melody": params.get("hum_melody") or None,
    }
    seed = payload.get("seed")
    if seed is None:
        seed = derive_seed(full_params, settings.server_nonce)
    return {"style_prompt": style_prompt, "lyrics": lyrics, "params": full_params,
            "seed": int(seed) & 0xFFFFFFFF,
            "auto_lyrics": auto_lyrics,
            "expand_prompt": mode == "simple" and bool(style_prompt)}


def check_generation_content(payload: dict) -> None:
    text = " ".join(filter(None, [
        payload.get("style_prompt") or "", payload.get("simple_prompt") or "",
        payload.get("lyrics") or "", payload.get("negative_prompt") or "",
    ]))
    if check_sensitive(text):
        raise err_sensitive()
    # 义务②（MiniMax 社区许可）：在世艺术家名义/声音冒用防护（服务端强制）
    from app.services.ip_protection import check_ip_protection
    check_ip_protection(text)


def check_free_daily_limit(db: Session, user: User) -> None:
    """免费档每日生成限额（含 extend/variant/regen-section 派生任务）。"""
    if user.plan != "free":
        return
    from datetime import datetime, timedelta

    from app.models import Plan
    # 自然日按 UTC+8：当日 00:00 (UTC+8) = 前一日 16:00 UTC
    now_cn = datetime.now(UTC) + timedelta(hours=8)
    day_start_utc = (now_cn.replace(hour=0, minute=0, second=0, microsecond=0)
                     - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = db.execute(
        select(func.count()).select_from(Task).where(
            Task.user_id == user.id, Task.type == "generation",
            Task.created_at >= day_start_utc)
    ).scalar_one()
    # P1-14：限额读 Plan 表（运营调表即时生效，不再硬编码 5）
    plan = db.get(Plan, "free")
    limit = plan.daily_generations if plan and plan.daily_generations else 5
    if count >= limit:
        raise err_payment_required(
            tr("今日免费生成次数已用完", "Today's free generations are used up"))


def check_account_hourly_limit(db: Session, user: User) -> None:
    """账号维度每小时生成上限（P1-7：叠加在 IP 限流之上，全部档位生效）。"""
    from datetime import datetime, timedelta
    cutoff = (datetime.now(UTC) - timedelta(hours=1)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = db.execute(
        select(func.count()).select_from(Task).where(
            Task.user_id == user.id, Task.type == "generation",
            Task.created_at >= cutoff)
    ).scalar_one()
    if count >= settings.account_generation_hourly_limit:
        raise err_payment_required(
            tr("生成请求过于频繁（每小时上限 "
               f"{settings.account_generation_hourly_limit} 次），请稍后再试",
               "Too many generation requests (hourly limit "
               f"{settings.account_generation_hourly_limit}); please try again later"))


# 档位默认配额（Plan 表 NULL 时回退；运营可在表内覆盖）
_DEFAULT_CONCURRENT = {"free": 1, "pro": 3, "studio": 5, "team": 5}
_DEFAULT_STORAGE_MB = {"free": 2 * 1024, "pro": 20 * 1024,
                       "studio": 100 * 1024, "team": 200 * 1024}


def check_inflight_limit(db: Session, user: User) -> None:
    """P1-8：每用户在途（queued/running）生成任务上限，防单用户堆满队列。"""
    from app.models import Plan
    plan_row = db.get(Plan, user.plan)
    limit = (plan_row.max_concurrent_tasks if plan_row and plan_row.max_concurrent_tasks
             else _DEFAULT_CONCURRENT.get(user.plan, 2))
    inflight = db.execute(
        select(func.count()).select_from(Task).where(
            Task.user_id == user.id, Task.type == "generation",
            Task.status.in_(("queued", "running")))
    ).scalar_one()
    if inflight >= limit:
        raise err_conflict(
            tr(f"在途生成任务已达上限（{limit} 个），请等待完成后再提交",
               f"You already have {limit} generation task(s) running; "
               "wait for them to finish first"))


def check_storage_quota(db: Session, user: User) -> None:
    """P1-8：每用户已登记文件总量 vs 档位存储配额（提交生成/导出前校验）。

    只统计 files 表登记字节（未登记的临时文件由孤儿清扫兜底）；命中配额
    引导清理回收站（30 天后自动物理删除）。
    """
    from app.models import File, Plan, Work
    plan_row = db.get(Plan, user.plan)
    quota_mb = (plan_row.storage_quota_mb if plan_row and plan_row.storage_quota_mb
                else _DEFAULT_STORAGE_MB.get(user.plan, 2 * 1024))
    used = db.execute(
        select(func.coalesce(func.sum(File.bytes), 0)).join(
            Work, Work.id == File.work_id).where(Work.user_id == user.id)
    ).scalar_one()
    if used >= quota_mb * 1024 * 1024:
        raise err_conflict(
            tr(f"存储空间已满（配额 {quota_mb // 1024}GB）：请删除不需要的作品"
               f"（回收站 30 天后自动清除）或升级档位",
               f"Storage quota reached ({quota_mb // 1024}GB): delete unneeded works "
               "(trash auto-purges after 30 days) or upgrade your plan"))


def _check_maintenance() -> None:
    """P1-13：维护模式（发布窗口）拒绝新任务提交，防进队列即被重启杀掉。"""
    if settings.maintenance_mode:
        raise err_conflict(
            tr("系统维护中，请稍后再试（通常几分钟内恢复）",
               "The system is under maintenance; please try again shortly"))


def submit_generation(db: Session, user: User, payload: dict) -> dict:
    _check_maintenance()
    check_generation_content(payload)
    check_free_daily_limit(db, user)
    check_account_hourly_limit(db, user)
    check_inflight_limit(db, user)
    check_storage_quota(db, user)
    from app.core.disk_guard import ensure_disk_available
    ensure_disk_available()

    resolved = resolve_generation_request(payload)
    params = resolved["params"]

    # FR-4 参考音频（v0.8.1）：特征级参考——分析值覆盖 bpm/调性/器乐密度
    reference_info = None
    reference_track_id = (payload.get("reference_track_id") or "").lower()
    if reference_track_id:
        from app.services import reference as reference_svc
        track = reference_svc.resolve_for_generation(db, user, reference_track_id)
        params = reference_svc.apply_to_params(params, track.analysis)
        resolved["params"] = params
        reference_info = {
            "reference_track_id": track.id, "name": track.name,
            "analysis": {
                "bpm": track.analysis["bpm"],
                "key_tonic": track.analysis["key_tonic"],
                "key_mode": track.analysis["key_mode"],
                "energy": track.analysis["energy"],
                "brightness": track.analysis["brightness"],
            },
            # 合规留痕：参考非采样（特征级），上传时已确认权利
            "feature_level": True, "ack_rights": True,
        }

    # FR-5 人声克隆（v0.8.2）：vocal=voice_clone 需已验证档案，仅本地引擎通道
    voice_info = None
    if params.get("vocal") == "voice_clone":
        from app.models.enums import VOCALS  # noqa: F401 —— 校验已在 schema 完成
        from app.services import model_center as _mc
        backend = _mc.current_music_backend(db)
        if backend != "localsynth":
            raise err_conflict(
                tr("人声克隆仅支持本地合成引擎通道（当前歌曲引擎需在模型中心切回本地）",
                   "Voice cloning is only supported on the local synth engine channel "
                   "(switch the song engine back to local in the model center)"))
        from app.services import voice as voice_svc
        profile_id = (params.get("voice_profile_id") or "").lower()
        if not profile_id:
            raise err_validation(
                tr("vocal=voice_clone 时 params.voice_profile_id 必填",
                   "params.voice_profile_id is required when vocal=voice_clone"))
        profile = voice_svc.get_verified_owned(db, user, profile_id)
        params["voice_timbre"] = profile.timbre
        resolved["params"] = params
        voice_info = {
            "voice_profile_id": profile.id, "name": profile.name,
            "verify_score": profile.verify_score,
            "liveness": "two_random_phrases",
            # 合规留痕：克隆音轨标记（导出 AIGC 标识 + 事件水印口径）
            "voice_clone": True,
        }
    # 哼唱成歌（v0.11.0）：hum_melody 仅本地引擎（外部通道无旋律覆写能力）
    if params.get("hum_melody"):
        from app.services import model_center as _mc
        if _mc.current_music_backend(db) != "localsynth":
            raise err_conflict(
                tr("哼唱旋律仅支持本地合成引擎通道（当前歌曲引擎需在模型中心切回本地）",
                   "Hummed melody is only supported on the local synth engine channel "
                   "(switch the song engine back to local in the model center)"))
        voice_info = voice_info or {"hum_melody": True}

    cost = MODEL_CREDIT_COST.get(params["model"], 12)

    # work / version
    work_id = payload.get("work_id")
    parent_version_id = payload.get("parent_version_id")
    now = utc_now_iso()
    if work_id:
        work = works_svc.get_work_row(db, work_id, user)
        # 指向「全空壳被自动清理」的作品重新提交（如重试）：先恢复，避免成果落入回收站
        if work.trashed_at is not None:
            work.trashed_at = None
            work.updated_at = now
    else:
        title = _derive_title(payload, params)
        work = Work(user_id=user.id, display_code=works_svc.new_display_code(db),
                    title=title, status="active", favorite=False, tags=[],
                    bpm=params["bpm"],
                    key_tonic=params["key"]["tonic"], key_mode=params["key"]["mode"],
                    duration_sec=params["duration_sec"], model=params["model"],
                    cover_color=cover_color_for_seed(resolved["seed"]),
                    created_at=now, updated_at=now)
        db.add(work)
        db.flush()
    version_no = f"v{work.version_count + 1}"
    if parent_version_id:
        parent = db.get(Version, parent_version_id)
        if not parent or parent.work_id != work.id:
            raise err_not_found(tr("父版本不存在", "Parent version not found"))
    else:
        latest = db.execute(select(Version).where(Version.work_id == work.id)
                            .order_by(Version.created_at.desc(), Version.id.desc())
                            .limit(1)).scalars().first()
        parent_version_id = latest.id if latest else None
    version = Version(work_id=work.id, parent_version_id=parent_version_id,
                      version_no=version_no, source="generate", candidate_count=0,
                      params=params, lyrics=resolved["lyrics"], created_at=now,
                      updated_at=now)
    db.add(version)
    db.flush()
    work.version_count += 1
    work.updated_at = now

    request_snapshot = {
        "mode": payload.get("mode"), "simple_prompt": payload.get("simple_prompt"),
        "style_prompt": payload.get("style_prompt"), "lyrics": payload.get("lyrics"),
        "negative_prompt": payload.get("negative_prompt"),
        "model": payload.get("model"), "work_id": work_id,
        "parent_version_id": parent_version_id,
        "simplified": bool(payload.get("simplified", False)),
        "seed": payload.get("seed"), "params": payload.get("params"),
        "reference": reference_info,
        "voice": voice_info,
        "_resolved": resolved,
    }
    task = Task(user_id=user.id, type="generation", status="queued", progress=0,
                stage_key="queued", stage_label=tr("排队中", "Queued"), work_id=work.id,
                version_id=version.id,
                provider=model_center.current_music_backend(db), seed=resolved["seed"],
                cost_credits=cost, request_payload=request_snapshot,
                created_at=now, updated_at=now)
    db.add(task)
    db.flush()

    from app.services.credits import atomic_deduct
    atomic_deduct(db, user.id, cost, "generation", task.id)

    db.commit()
    db.refresh(task)
    db.refresh(work)

    from app.core.tasks import schedule_generation
    schedule_generation(task.id, plan=user.plan)

    return {
        "task": task_to_dict(task),
        "work": {"id": work.id, "display_code": work.display_code,
                 "title": work.title, "cover_color": work.cover_color},
        "cost_credits": cost,
    }


def _derive_title(payload: dict, params: dict) -> str:
    if payload.get("mode") == "simple" and payload.get("simple_prompt"):
        return payload["simple_prompt"][:12]
    if params.get("style_prompt"):
        return params["style_prompt"][:12]
    return tr("未命名作品", "Untitled work")


# ---------- 执行（线程池内）----------

def _prepare_generation_inputs(db, task_id: str, payload_row: dict, resolved: dict) -> None:
    """执行前准备模型输入：simple 扩写 + 自动写词（V1.3 起走模型中心配置的真实引擎）。

    LLM 失败时 provider 内部自动回退本地规则（响应带 fallback 留痕）；
    引擎与回退信息写入任务快照 _resolved、歌词回填 version.lyrics，供审计与前端展示。
    """
    params = resolved["params"]
    changed = False
    if payload_row.get("mode") == "simple" and payload_row.get("simple_prompt"):
        _write_progress(task_id, "writing", 2,
                        tr("AI 扩写风格描述…", "Expanding style description with AI…"))
        simple = str(payload_row["simple_prompt"]).strip()
        style = expand_simple_prompt(simple)
        chat = model_center.get_lyrics_chat(db)
        if chat is not None:
            style = expand_style_by_llm(chat, simple) or style
        params["style_prompt"] = style
        resolved["style_prompt"] = style
        resolved["style_expanded"] = True
        changed = True
    if resolved.get("auto_lyrics") and not resolved.get("lyrics"):
        _write_progress(task_id, "writing", 4,
                        tr("AI 创作歌词…", "Writing lyrics with AI…"))
        theme = payload_row.get("simple_prompt") or (params.get("style_prompt") or "")[:60]
        gen = model_center.get_lyrics_provider(db).generate(
            theme=theme, style_hint=(params.get("style_prompt") or "")[:80],
            mood=None, language=params.get("language", "zh"))
        resolved["lyrics"] = gen.get("lyrics") or ""
        resolved["lyrics_engine"] = gen.get("engine", "")
        resolved["lyrics_fallback"] = bool(gen.get("fallback"))
        changed = True
    if not changed:
        return
    task = db.get(Task, task_id)
    if task is None:
        return
    task.request_payload = {**(task.request_payload or {}), "_resolved": resolved}
    version = db.get(Version, task.version_id)
    if version is not None:
        version.lyrics = resolved.get("lyrics") or ""
        version.params = params
    db.commit()


def execute_generation(task_id: str) -> None:
    t_start = time.monotonic()
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "running"
        task.started_at = utc_now_iso()
        task.updated_at = utc_now_iso()
        db.commit()
        user_id = task.user_id

    try:
        payload_row = task.request_payload or {}
        derived_spec = payload_row.get("_derived") if isinstance(payload_row, dict) else None
        resolved = dict(payload_row.get("_resolved") or {})
        params = resolved["params"]

        # 引擎选择（V1.3，ADR-010）：普通生成走模型中心配置（localsynth/api 双通道）；
        # 派生编辑固定本地引擎（波形手术依赖本地渲染产物，外部候选已被产物校验拦截）
        with SessionLocal() as db:
            if derived_spec:
                from app.providers.music_local import LocalSynthProvider
                provider = LocalSynthProvider()
            else:
                provider = model_center.get_music_provider(db)
                _prepare_generation_inputs(db, task_id, payload_row, resolved)
        # 写词/扩写在真实模型上可能耗时数分钟（CPU 本地模型），不计入渲染超时
        t_start = time.monotonic()
        timeout_sec = getattr(provider, "timeout_sec", GENERATION_TASK_TIMEOUT_SEC)

        req = SongRequest(
            style_prompt=params["style_prompt"], negative_prompt=params["negative_prompt"],
            model=params["model"], lyrics=resolved.get("lyrics") or "",
            bpm=params["bpm"], tonic=params["key"]["tonic"], mode=params["key"]["mode"],
            time_signature=params["time_signature"], duration_sec=params["duration_sec"],
            vocal=params["vocal"], language=params["language"],
            instrument_density=params["instrument_density"], seed=resolved["seed"],
            voice_timbre=params.get("voice_timbre"),
            hum_melody=params.get("hum_melody") or None,
        )
        dest = settings.audio_path / task.work_id / task.version_id

        progress = _progress_reporter(task_id, t_start, timeout_sec)

        def should_cancel() -> bool:
            return _cancel_requested(task_id)

        if derived_spec:
            base_dir = str(settings.audio_path / derived_spec["base_dir"])
            output = provider.generate_derived(req, derived_spec, base_dir,
                                               progress, should_cancel, str(dest))
        else:
            output = provider.generate(req, progress, should_cancel, str(dest))

        with SessionLocal() as db:
            _persist_success(db, task_id, user_id, output, provider)
        logger.info(f"generation {task_id} done in {time.monotonic() - t_start:.1f}s "
                    f"provider={provider.name}")
    except SynthCancelled:
        with SessionLocal() as db:
            _finish_task(db, task_id, "canceled", None, None)
            _refund(db, task_id)
            rollback_empty_current_version(db, task_id)
            db.commit()
        _cleanup_failed_audio(task_id)
    except TimeoutError as e:
        with SessionLocal() as db:
            _finish_task(db, task_id, "failed", 50002,
                         tr("生成失败：渲染超时 ", "Generation failed: render timeout ") + str(e))
            _refund(db, task_id)
            rollback_empty_current_version(db, task_id)
            db.commit()
        _cleanup_failed_audio(task_id)
    except Exception as e:  # noqa: BLE001 —— 任务级兜底，退款 + 50002
        logger.exception(f"generation {task_id} failed: {e}")
        with SessionLocal() as db:
            _finish_task(db, task_id, "failed", 50002,
                         tr("生成失败：", "Generation failed: ")
                         + f"{type(e).__name__} {e}")
            _refund(db, task_id)
            rollback_empty_current_version(db, task_id)
            db.commit()
        _cleanup_failed_audio(task_id)


def _progress_reporter(task_id: str, t_start: float, timeout_sec: int):
    """provider 进度回调：超时熔断 + 进度落库（瞬时库错误跳过该次）。"""
    def progress(stage_key: str, pct: int, label: str) -> None:
        if time.monotonic() - t_start > timeout_sec:
            raise TimeoutError(
                tr(f"超过 {timeout_sec}s 熔断", f"exceeded {timeout_sec}s circuit limit"))
        try:
            _write_progress(task_id, stage_key, pct, label)
        except OperationalError as e:
            _skip_transient_db(task_id, "progress", e)
    return progress


def _skip_transient_db(task_id: str, what: str, e: Exception) -> None:
    """进度/取消轮询遇瞬时库错误（unable to open database file 等）跳过该次。

    坑位：Docker bind 挂载（9p）下 WAL 共享内存偶发瞬时打开失败——v0.11.1
    容器实测：采样到 70% 时 cancel 轮询新开连接报 OperationalError，5 分钟
    推理被连带判失败。轮询性操作 fail-open，只告警不打断；持续失败仍会在
    落库/收尾处正常抛出。"""
    logger.warning(f"generation {task_id} {what} poll skipped (transient db): {e}")


def _cleanup_failed_audio(task_id: str) -> None:
    """P1-11：任务终态失败/取消后清扫版本目录的孤儿音频。

    失败路径 provider 可能已落盘部分候选文件（如候选 A 成功 B 失败），
    rollback 只回滚 DB 引用不删盘——长期运行缓慢吃满磁盘。版本已有登记
    文件（异常发生在 _persist_success 之后的极少场景）则不清理。
    """
    try:
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t is None or t.work_id is None or t.version_id is None:
                return
            registered = db.execute(select(func.count()).select_from(File).where(
                File.version_id == t.version_id)).scalar_one()
            if registered:
                return
            dest = settings.audio_path / t.work_id / t.version_id
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 —— 清扫失败不影响任务终态
        logger.warning(f"generation {task_id} orphan audio cleanup failed: {e}")


def _cancel_requested(task_id: str) -> bool:
    try:
        with SessionLocal() as db2:
            t = db2.get(Task, task_id)
            return bool(t and t.cancel_requested)
    except OperationalError as e:
        # fail-open：取消检查是轮询性的，跳过一次最多延迟取消感知，
        # 不该因它把进行中的长时推理连带废掉
        _skip_transient_db(task_id, "cancel", e)
        return False


def _write_progress(task_id: str, stage_key: str, pct: int, label: str) -> None:
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        if t is None or t.status != "running":
            return
        if abs(pct - t.progress) < 2 and stage_key == t.stage_key:
            return
        t.progress = max(0, min(100, pct))
        t.stage_key = stage_key
        t.stage_label = label
        t.updated_at = utc_now_iso()
        db.commit()


def _persist_success(db: Session, task_id: str, user_id: str, output, provider) -> None:
    task = db.get(Task, task_id)
    if task is None or task.status not in ("running", "queued"):
        return
    task.provider = provider.name  # 执行时实际引擎（提交与执行间配置可能已切换）
    work = db.get(Work, task.work_id)
    version = db.get(Version, task.version_id)
    # 目录模型留痕（真实业务测试 2026-09-02 抓到的传导断点）：params.model 是本地
    # 引擎档位（v1_pro/v1_fast），通道实际使用的目录模型此前未随版本落库——证书
    # 许可分流拿不到真实模型。此处快照执行时刻 provider 的目录模型（无则不写）。
    catalog_model = getattr(provider, "model_id", None)
    if catalog_model and version.params.get("catalog_model") != catalog_model:
        import copy as _copy
        merged = _copy.deepcopy(version.params) if version.params else {}
        merged["catalog_model"] = catalog_model
        version.params = merged
    now = utc_now_iso()
    result_candidates = []
    first_cand = None
    for art in output.candidates:
        cand = Candidate(
            version_id=version.id, label=art.label, adopted=False, seed=art.seed,
            quality_score=art.quality_score, duration_sec=int(round(art.duration_sec)),
            bpm=art.bpm, key_tonic=art.tonic, key_mode=art.mode,
            time_signature=art.time_signature, vocal=art.vocal, language=art.language,
            style_tags=art.style_tags, structure=art.structure,
            applied_negative=output.applied_negative, created_at=now, updated_at=now,
        )
        db.add(cand)
        db.flush()
        if first_cand is None:
            first_cand = cand
        preview_relpath: str | None = None
        seen_paths: set[str] = set()
        for fmeta in art.files:
            rel = fmeta["relpath"]
            full = f"{work.id}/{version.id}/{rel}"
            if full in seen_paths:
                # 同源产物注册多种 kind（外部通道 preview/master 同源整曲）：复制一份
                # 独立物理文件再登记，避免 files.path UNIQUE 冲突——2026-09-26 商业化
                # 审查 P0-7：该冲突曾使外部 API 通道每个任务在最后落库步必败并退款
                new_rel = (f"{Path(rel).parent.as_posix()}/{Path(rel).stem}"
                           f"_{fmeta['kind']}{Path(rel).suffix}")
                src = settings.audio_path / full
                dst = settings.audio_path / work.id / version.id / new_rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                rel, full = new_rel, f"{work.id}/{version.id}/{new_rel}"
            seen_paths.add(full)
            if fmeta["kind"] == "preview":
                preview_relpath = rel
            db.add(File(
                work_id=work.id, version_id=version.id, candidate_id=cand.id,
                kind=fmeta["kind"], stem_name=fmeta.get("stem_name"),
                name=_display_filename(work.display_code, version.version_no, art.label,
                                       fmeta["kind"], fmeta.get("stem_name"),
                                       Path(rel).suffix),
                path=full,
                mime=fmeta["mime"], bytes=fmeta["bytes"],
                duration_sec=fmeta.get("duration_sec"), sample_rate=fmeta.get("sample_rate"),
                sha256=fmeta["sha256"], created_at=now, updated_at=now,
            ))
        result_candidates.append({
            "id": cand.id, "label": art.label, "quality_score": art.quality_score,
            "duration_sec": int(round(art.duration_sec)),
            "preview_file_id": None,  # 占位，flush 后回填
            "_preview_relpath": preview_relpath,
        })
    # 回填 preview_file_id（autoflush=False：须先 flush 才能在查询中看到本轮 File 行，
    # 否则末轮加入的候选——如 B——的 preview 永远查不到，本机 MusicGen 真机生成实测命中）
    db.flush()
    for rc, _art in zip(result_candidates, output.candidates, strict=False):
        if rc["_preview_relpath"]:
            row = db.execute(select(File).where(
                File.work_id == work.id, File.version_id == version.id,
                File.path == f"{work.id}/{version.id}/{rc['_preview_relpath']}")
            ).scalars().first()
            if row:
                rc["preview_file_id"] = row.id
        rc.pop("_preview_relpath", None)

    version.candidate_count = len(output.candidates)
    version.inferred_structure = bool(output.inferred_structure)
    if version.active_candidate_id is None and result_candidates:
        pass  # 不自动采用，等待用户 adopt（契约语义）
    # V1.1 派生任务（extend/variant/regen-section）：子版本自动 adopt 首个候选，
    # 避免出现「无活跃候选的空壳子版本」（不写 human adopt 事件，不计入人工参与统计）
    derived_spec = (task.request_payload or {}).get("_derived") if task.request_payload else None
    if derived_spec and first_cand is not None:
        first_cand.adopted = True
        version.active_candidate_id = first_cand.id
        work.bpm = first_cand.bpm
        work.key_tonic = first_cand.key_tonic
        work.key_mode = first_cand.key_mode
        work.duration_sec = first_cand.duration_sec
        work.model = version.params.get("model", work.model)
        work.active_version_id = version.id
        if result_candidates and result_candidates[0].get("preview_file_id"):
            work.preview_file_id = result_candidates[0]["preview_file_id"]
    resolved_snapshot = (task.request_payload or {}).get("_resolved") or {}
    works_svc.add_event(db, user_id=user_id, action="generate", actor="ai",
                        detail={"task_id": task.id, "provider": provider.name,
                                "provider_display": provider.display_name,
                                "lyrics_engine": resolved_snapshot.get("lyrics_engine"),
                                "lyrics_fallback": resolved_snapshot.get("lyrics_fallback"),
                                # 器乐模型承接人声请求时的如实降级留痕（MusicGen）
                                "vocals_downgraded": bool(getattr(provider, "vocals_downgraded", False)),
                                "derived_op": derived_spec.get("op") if derived_spec else None,
                                "auto_adopted": bool(derived_spec),
                                "candidates": [rc["label"] for rc in result_candidates]},
                        work_id=work.id, version_id=version.id)
    task.status = "succeeded"
    task.progress = 100
    task.stage_key = "done"
    task.stage_label = stage_label("done")
    task.result = {"candidates": result_candidates}
    task.finished_at = now
    task.updated_at = now
    work.updated_at = now
    db.commit()


def _display_filename(display_code: str, version_no: str, label: str, kind: str,
                      stem_name: str | None, ext: str) -> str:
    ext = ext.lstrip(".")
    if kind == "stem":
        return f"{display_code}_{version_no}_{label}_{kind}_{stem_name}.{ext}"
    if kind in ("preview", "master"):
        return f"{display_code}_{version_no}_{label}_{kind}.{ext}"
    return f"{display_code}_{version_no}_{kind}.{ext}"


def _finish_task(db: Session, task_id: str, status: str, error_code: int | None,
                 error_message: str | None) -> None:
    t = db.get(Task, task_id)
    if t is None or t.status in ("succeeded", "failed", "canceled"):
        return
    t.status = status
    t.error_code = error_code
    t.error_message = error_message
    t.finished_at = utc_now_iso()
    t.updated_at = utc_now_iso()
    db.flush()  # 不单独 commit：终态与退款由调用方在同一事务内一次提交


def _refund(db: Session, task_id: str) -> None:
    t = db.get(Task, task_id)
    if t is None or t.cost_credits <= 0:
        return
    user = db.get(User, t.user_id)
    if user is None:
        return
    from app.services.credits import refund
    refund(db, user.id, t.cost_credits, t.id)


def _fallback_current_version(db: Session, work_id: str, exclude_id: str) -> str | None:
    """最近的非空版本（候选数 > 0）；无则 None。"""
    row = db.execute(
        select(Version).where(Version.work_id == work_id, Version.id != exclude_id,
                              Version.candidate_count > 0)
        .order_by(Version.created_at.desc(), Version.id.desc()).limit(1)
    ).scalars().first()
    return row.id if row else None


def rollback_empty_current_version(db: Session, task_id: str) -> None:
    """任务终态（canceled/failed）后回滚空版本电流向（模拟用户测试发现 #4）。

    任务在提交时已建版本；失败/取消后该版本 candidate_count=0，
    若 work.current 正指向它，则回滚到最近的非空版本（通常为 parent）。
    不删除版本行（任务/事件外键仍引用），版本树 current 解析另跳过空版本。

    若作品所有版本均为空（首次生成即失败，无任何候选/文件产出），
    则将作品移入回收站（trashed_at），避免「全部作品」列表残留同名空壳
    与后续成功作品混淆（真实业务测试发现 #7）；带显式 work_id 重提交会自动恢复。
    """
    t = db.get(Task, task_id)
    if t is None or t.version_id is None:
        return
    version = db.get(Version, t.version_id)
    if version is None or version.candidate_count > 0:
        return
    work = db.get(Work, version.work_id)
    if work is None:
        return
    if work.active_version_id == version.id:
        work.active_version_id = _fallback_current_version(db, work.id, version.id)
        work.updated_at = utc_now_iso()
    if _fallback_current_version(db, work.id, version.id) is None and work.trashed_at is None:
        work.trashed_at = utc_now_iso()
        work.updated_at = utc_now_iso()


# ---------- 查询 / 取消 ----------

def get_task_owned(db: Session, task_id: str, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise err_not_found(tr("任务不存在", "Task not found"))
    if task.user_id != user.id:
        raise err_forbidden()
    return task


def list_tasks(db: Session, user: User, *, type_: str | None, status: str | None,
               work_id: str | None, page: int, page_size: int) -> dict:
    conds = [Task.user_id == user.id]
    if type_:
        conds.append(Task.type == type_)
    if status:
        conds.append(Task.status == status)
    if work_id:
        conds.append(Task.work_id == work_id)
    base = select(Task).where(*conds)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(Task.created_at.desc(), Task.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    from app.services.credits import paginate_meta
    return paginate_meta([task_to_dict(t) for t in rows], total, page, page_size)


def cancel_task(db: Session, user: User, task_id: str) -> dict:
    task = get_task_owned(db, task_id, user)
    if task.status in ("succeeded", "failed", "canceled"):
        raise err_conflict(tr("任务已结束，无法取消", "Task already finished; cannot cancel"))
    if task.type == "export" and task.status == "running":
        # P1-10：排队中的导出可取消（worker 取到时按状态检查跳过）；
        # 执行中的导出无阶段取消钩子（转码不可中断），只能等其自然终态/软超时
        raise err_conflict(tr("导出正在执行，暂不支持中断（最多 10 分钟自动结束）",
                              "Export is running and cannot be interrupted "
                              "(auto-finishes within 10 minutes)"))
    if task.status == "queued":
        task.status = "canceled"
        task.finished_at = utc_now_iso()
        task.updated_at = utc_now_iso()
        _refund(db, task.id)
        rollback_empty_current_version(db, task.id)
        db.commit()  # 终态、退款与电流向回滚同事务提交
        db.refresh(task)
        return task_to_dict(task)
    # running：置取消标志，渲染循环在阶段边界到达
    task.cancel_requested = True
    task.stage_label = tr("正在取消…", "Canceling…")
    task.updated_at = utc_now_iso()
    db.commit()
    db.refresh(task)
    return task_to_dict(task)


# ---------- 候选 ----------

def list_candidates(db: Session, version_id: str, user: User) -> dict:
    version = works_svc.get_version_owned(db, version_id, user, min_role="viewer")
    rows = db.execute(select(Candidate).where(Candidate.version_id == version.id)
                      .order_by(Candidate.label.asc())).scalars().all()
    items = [candidate_to_dict(c) for c in rows]
    # 义务①（MiniMax 社区许可）：生成结果页（作品详情候选卡）展示生成引擎署名——
    # 取该版本最近一次生成任务的 provider 留痕，随候选列表下发
    from app.models import Task
    from app.services.certificate import provider_attribution
    gen_task = db.execute(
        select(Task.provider).where(Task.version_id == version.id,
                                    Task.type == "generation")
        .order_by(Task.created_at.desc(), Task.id.desc()).limit(1)
    ).first()
    provider = (gen_task[0] if gen_task else None) or "localsynth"
    return {"items": items, "inferred_structure": bool(version.inferred_structure),
            "provider": provider, "provider_display": provider_attribution(provider)}


def get_candidate_owned(db: Session, candidate_id: str, user: User) -> Candidate:
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise err_not_found(tr("候选不存在", "Candidate not found"))
    works_svc.get_version_owned(db, cand.version_id, user)  # 归属校验
    return cand


def adopt_candidate(db: Session, candidate_id: str, user: User) -> dict:
    from app.services.serializers import version_to_dict
    cand = get_candidate_owned(db, candidate_id, user)
    version = db.get(Version, cand.version_id)
    if version.active_candidate_id == cand.id:
        raise err_conflict(tr("该候选已是活跃候选", "This candidate is already active"))
    # 同版本其他候选置 false
    others = db.execute(select(Candidate).where(Candidate.version_id == version.id)).scalars()
    for c in others:
        c.adopted = (c.id == cand.id)
    version.active_candidate_id = cand.id
    work = db.get(Work, version.work_id)
    work.bpm = cand.bpm
    work.key_tonic = cand.key_tonic
    work.key_mode = cand.key_mode
    work.duration_sec = cand.duration_sec
    work.model = version.params.get("model", work.model)
    work.active_version_id = version.id
    # 回写 preview_file_id：该候选的 preview 文件
    preview = db.execute(select(File).where(File.candidate_id == cand.id,
                                            File.kind == "preview")).scalars().first()
    if preview:
        work.preview_file_id = preview.id
    work.updated_at = utc_now_iso()
    works_svc.add_event(db, user_id=user.id, action="adopt", actor="human",
                        detail={"candidate_id": cand.id, "label": cand.label},
                        work_id=work.id, version_id=version.id)
    db.commit()
    db.refresh(version)
    return version_to_dict(version)
