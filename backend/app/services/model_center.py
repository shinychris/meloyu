"""模型中心服务：本地开源模型（Ollama）下载/删除/列举 + 外部 API 配置
+ 歌词引擎工厂（V1.2）+ 外部歌曲生成 API 通道（V1.3）
+ 开源歌曲模型目录/Replicate 托管/本机 MusicGen（V1.4）
+ 本机 ACE-Step v1.5 人声成曲通道（V1.5，ADR-016）。

进度写库节流（≥2% 或 ≥1s 才落一次），拉取线程与生成任务线程池隔离（各 1 worker）。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.logging import logger
from app.database import SessionLocal
from app.models import SETTING_ID, LLMSetting, ModelOp
from app.models.base import new_uuid, utc_now_iso
from app.providers.llm import LLMError, OllamaClient, OpenAICompatClient
from app.providers.lyrics_llm import LLMLyricsProvider, valid_model_tag
from app.providers.lyrics_local import LocalLyricsProvider
from app.providers.music_acestep import (
    ACEStepLocalError,
    ACEStepLocalProvider,
    acestep_deps_installed,
    acestep_install_hint,
    delete_local as acestep_delete_local,
    local_downloaded_ids as acestep_downloaded_ids,
    pull_local as acestep_pull_local,
)
from app.providers.music_api import APIMusicProvider, MusicAPIError, SunoCompatClient
from app.providers.music_catalog import (
    ACESTEP_RUNNABLE_IDS as _ACESTEP_IDS,
    CATALOG_BY_ID,
    CATALOG_DISCLAIMER,
    LOCAL_RUNNABLE_IDS,
    catalog_sorted,
)
from app.providers.music_musicgen import (
    MusicGenLocalError,
    MusicGenLocalProvider,
    delete_local,
    local_downloaded_ids,
    musicgen_deps_installed,
    musicgen_install_hint,
    pull_local,
)
from app.providers.music_replicate import ReplicateClient, ReplicateError, ReplicateMusicProvider

_op_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meloyu-model-op")

# 推荐 pull 的本地模型（tag 须与 Ollama 仓库一致；大小为约值）。
# 注：qwen3.5 系列支持关闭思考链直出；旧 qwen3 系列常开思考，CPU 混合推理下一首
# 歌词可能数分钟——无独显机器优先选小模型。
RECOMMENDED_MODELS: list[dict] = [
    {"tag": "qwen3.5:1.7b", "name": "Qwen3.5 1.7B", "size_mb": 1147,
     "note": "推荐：思考可关、直出快，中文歌词质量性价比档"},
    {"tag": "qwen3.5:4b", "name": "Qwen3.5 4B", "size_mb": 3390,
     "note": "质量档（本机预装）：4B 级中文写作最佳，无独显约 1~3 分钟/首"},
    {"tag": "qwen3:0.6b", "name": "Qwen3 0.6B", "size_mb": 522,
     "note": "最轻档：CPU 可用，常开思考但量小，链路验证/低配首选"},
    {"tag": "qwen3:1.7b", "name": "Qwen3 1.7B", "size_mb": 1060,
     "note": "轻量档：常开思考，速度与质量折中"},
    {"tag": "deepseek-r1:1.5b", "name": "DeepSeek-R1 1.5B", "size_mb": 1053,
     "note": "推理型小模型：韵脚推敲认真，思考链较长"},
    {"tag": "gemma3:270m", "name": "Gemma3 270M", "size_mb": 311,
     "note": "极限小体积冒烟档，仅用于链路验证"},
]

EXTERNAL_PRESETS: list[dict] = [
    {"vendor": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model_hint": "glm-4-flash（免费档）/ glm-4-air"},
    {"vendor": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
     "model_hint": "deepseek-chat"},
    {"vendor": "OpenAI", "base_url": "https://api.openai.com/v1",
     "model_hint": "gpt-4o-mini"},
    {"vendor": "Moonshot", "base_url": "https://api.moonshot.cn/v1",
     "model_hint": "moonshot-v1-8k"},
]

# 外部歌曲生成 API 预设（Suno 兼容协议，ADR-010）：base 填网关根，自动补 /api/v1
MUSIC_API_PRESETS: list[dict] = [
    {"vendor": "GoAPI（Suno 中转）", "base_url": "https://api.goapi.ai/suno",
     "model_hint": "" },
    {"vendor": "自建 suno-api 网关", "base_url": "http://localhost:3000",
     "model_hint": ""},
]


# ---------- 配置 ----------

def _setting_row(db: Session) -> LLMSetting:
    row = db.get(LLMSetting, SETTING_ID)
    if row is None:
        row = LLMSetting(id=SETTING_ID)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _mask_key(key: str) -> dict:
    key = key or ""
    return {"has_key": bool(key), "key_tail": key[-4:] if len(key) > 4 else ""}


def get_settings(db: Session) -> dict:
    s = _setting_row(db)
    return {
        "lyrics_backend": s.lyrics_backend,
        "ollama_host": s.ollama_host,
        "ollama_model": s.ollama_model,
        "external_base_url": s.external_base_url,
        "external_model": s.external_model,
        "external_api_key": _mask_key(s.external_api_key),
        "music_backend": s.music_backend,
        "music_api_base_url": s.music_api_base_url,
        "music_api_model": s.music_api_model,
        "music_api_key": _mask_key(s.music_api_key),
        "music_model": s.music_model,
        "replicate_api_token": _mask_key(s.replicate_api_token),
        "replicate_slugs": s.replicate_slugs or {},
    }


_MUSIC_BACKENDS = ("localsynth", "api", "replicate", "musicgen_local", "acestep_local")


def update_settings(db: Session, patch: dict) -> dict:
    s = _setting_row(db)
    backend = patch.get("lyrics_backend", s.lyrics_backend)
    if backend not in ("localsynth", "ollama", "openai_compat"):
        raise err_validation("lyrics_backend 必须为 localsynth/ollama/openai_compat")
    if backend == "ollama" and not (patch.get("ollama_model") or s.ollama_model):
        raise err_validation("ollama 通道需要先选择本地模型")
    if backend == "openai_compat":
        base = patch.get("external_base_url", s.external_base_url)
        model = patch.get("external_model", s.external_model)
        if not base or not model:
            raise err_validation("外部 API 通道需要 base_url 与 model")

    music_backend = patch.get("music_backend")
    music_model = str(patch.get("music_model") or "").strip()
    if not music_model and "music_model" not in patch:
        music_model = s.music_model
    if music_backend is None:
        music_backend = s.music_backend
        # 仅选模型未显式给通道：按模型可用通道自动切换（显式 music_backend 优先；
        # 有 Replicate Token 优先托管，否则本机通道 ACE-Step（人声）> MusicGen（器乐））
        if music_model and music_model != s.music_model:
            entry = CATALOG_BY_ID.get(music_model)
            if entry:
                channels = entry.get("channels", [])
                if "replicate" in channels and (
                        patch.get("replicate_api_token") or s.replicate_api_token):
                    music_backend = "replicate"
                elif "acestep_local" in channels:
                    music_backend = "acestep_local"
                elif "musicgen_local" in channels:
                    music_backend = "musicgen_local"
    if music_backend not in _MUSIC_BACKENDS:
        raise err_validation("music_backend 必须为 localsynth/api/replicate/musicgen_local/acestep_local")
    if music_backend == "api" and not (patch.get("music_api_base_url") or s.music_api_base_url):
        raise err_validation("外部歌曲 API 通道需要先配置 base_url")
    if music_backend in ("replicate", "musicgen_local", "acestep_local"):
        entry = CATALOG_BY_ID.get(music_model)
        if entry is None:
            raise err_validation(f"开源模型目录中不存在：{music_model or '（未选择模型）'}")
        if music_backend not in entry.get("channels", []):
            raise err_validation(f"模型 {music_model} 不支持 {music_backend} 通道"
                                 f"（可用：{'/'.join(entry['channels'])}）")
        if music_backend == "replicate" and not (
                patch.get("replicate_api_token") or s.replicate_api_token):
            raise err_validation("Replicate 通道需要先配置 API Token")
        if music_backend == "musicgen_local" and music_model not in LOCAL_RUNNABLE_IDS:
            raise err_validation(f"模型 {music_model} 不支持本机运行（需 GPU 档请走 Replicate）")
        if music_backend == "acestep_local" and music_model not in _ACESTEP_IDS:
            raise err_validation(f"模型 {music_model} 不支持本机 ACE-Step 通道")

    for field in ("ollama_host", "ollama_model", "external_base_url", "external_model",
                  "music_api_base_url", "music_api_model", "music_model"):
        if field in patch and patch[field] is not None:
            v = str(patch[field]).strip()
            if len(v) > 300:
                raise err_validation(f"{field} 过长")
            setattr(s, field, v)
    if patch.get("external_api_key"):  # 空串=保持不变（脱敏读回无法回显）
        s.external_api_key = str(patch["external_api_key"]).strip()
    if patch.get("music_api_key"):
        s.music_api_key = str(patch["music_api_key"]).strip()
    if "replicate_api_token" in patch:  # V1.4：显式空串=清除（前端仅在输入时携带该字段）
        s.replicate_api_token = str(patch.get("replicate_api_token") or "").strip()
    if isinstance(patch.get("replicate_slugs"), dict):
        slugs = {}
        for mid, slug in patch["replicate_slugs"].items():
            if mid not in CATALOG_BY_ID:
                raise err_validation(f"replicate_slugs 含未知模型：{mid}")
            v = str(slug or "").strip()
            if len(v) > 120 or any(c in v for c in " ?#") or v.count("/") > 1:
                raise err_validation(f"slug 不合法（应为 owner/name）：{mid}={v[:60]}")
            if v:
                slugs[mid] = v
        s.replicate_slugs = slugs
    s.lyrics_backend = backend
    s.music_backend = music_backend
    db.commit()
    db.refresh(s)
    return get_settings(db)


# ---------- 运行时状态 / 本地模型 ----------

def runtime_status(db: Session) -> dict:
    s = _setting_row(db)
    client = OllamaClient(s.ollama_host)
    running, version, err = False, "", ""
    try:
        version = client.version()
        running = True
    except LLMError as e:
        err = e.message
    models: list[dict] = client.list_models() if running else []
    return {
        "ollama": {
            "host": client.base,
            "running": running,
            "version": version,
            "models_count": len(models),
            "error": err,
            "install_hint": "本机未检测到 Ollama 服务：https://ollama.com/download 安装后"
                            "运行 `ollama serve`（Windows 安装包常驻自启）",
        },
        "active_backend": s.lyrics_backend,
        "engine": engine_label(db),
        "music_backend": s.music_backend,
        "song_engine": song_engine_label(db),
        "replicate": {"token_saved": bool(s.replicate_api_token)},
    }


def engine_label(db: Session) -> str:
    s = _setting_row(db)
    if s.lyrics_backend == "ollama" and s.ollama_model:
        return f"Ollama · {s.ollama_model}"
    if s.lyrics_backend == "openai_compat" and s.external_model:
        return f"外部API · {s.external_model}"
    return "本地规则引擎（离线可用）"


def song_engine_label(db: Session) -> str:
    s = _setting_row(db)
    if s.music_backend == "api" and s.music_api_base_url:
        try:
            provider = APIMusicProvider(s.music_api_base_url, s.music_api_key,
                                        s.music_api_model)
            return provider.display_name
        except Exception as e:  # noqa: BLE001 —— 展示用标签，构造失败不阻断
            logger.warning(f"song engine label 构造失败: {e}")
            return "外部歌曲API（配置异常）"
    entry = CATALOG_BY_ID.get(s.music_model) if s.music_model else None
    if s.music_backend == "replicate" and entry:
        return f"Replicate · {entry['name']}"
    if s.music_backend == "musicgen_local" and entry:
        return f"MusicGen 本地 · {entry['name']}"
    if s.music_backend == "acestep_local" and entry:
        return f"ACE-Step 本地 · {entry['name']}"
    if s.music_backend in ("replicate", "musicgen_local", "acestep_local"):
        return "开源模型（未选择模型）"
    return "本地合成引擎（离线可用）"


def list_local_models(db: Session) -> dict:
    s = _setting_row(db)
    client = OllamaClient(s.ollama_host)
    try:
        models = client.list_models()
        err = ""
    except LLMError as e:
        models, err = [], e.message
    pulling = [
        op.to_dict() for op in db.execute(select(ModelOp).where(
            ModelOp.op_type == "pull", ModelOp.status.in_(("queued", "running")))).scalars()
    ]
    return {"host": client.base, "models": models, "selected": s.ollama_model,
            "pulling": pulling, "error": err, "recommended": RECOMMENDED_MODELS}


# ---------- 下载 / 删除（操作任务） ----------

def _write_op(op_id: str, **fields) -> None:
    with SessionLocal() as db:
        op = db.get(ModelOp, op_id)
        if op is None:
            return
        for k, v in fields.items():
            setattr(op, k, v)
        op.updated_at = utc_now_iso()
        db.commit()


def _execute_pull(op_id: str, model: str, host: str) -> None:
    _write_op(op_id, status="running", message="连接 Ollama…")
    last = {"t": 0.0, "pct": -1}

    def on_progress(status: str, pct: int) -> None:
        now = time.monotonic()
        if pct < 100 and pct - last["pct"] < 2 and now - last["t"] < 1.0:
            return
        last.update(t=now, pct=pct)
        _write_op(op_id, progress=max(pct, 0), message=status)

    try:
        OllamaClient(host).pull(model, on_progress)
        _write_op(op_id, status="succeeded", progress=100, message=f"已下载 {model}")
    except LLMError as e:
        _write_op(op_id, status="failed", message="下载失败",
                  error_message=e.message[:280])
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"model pull {model} crashed: {e}")
        _write_op(op_id, status="failed", message="下载失败",
                  error_message=str(e)[:280])


def start_pull(db: Session, user_id: str, model: str) -> dict:
    model = model.strip()
    if not valid_model_tag(model):
        raise err_validation("模型 tag 格式不合法（允许字母数字与 . _ : @ / + -）")
    running = db.execute(select(ModelOp).where(
        ModelOp.status.in_(("queued", "running")))).scalars().all()
    if any(op.target == model for op in running):
        raise err_conflict(f"模型 {model} 正在下载中")
    if any(op.target != model for op in running):
        raise err_conflict("已有模型下载任务进行中，请等待完成后再发起")
    s = _setting_row(db)
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="pull", target=model,
                 status="queued", message="排队中")
    db.add(op)
    db.commit()
    db.refresh(op)
    _op_executor.submit(_safe_op, _execute_pull, op.id, model, s.ollama_host)
    return op.to_dict()


def run_delete(db: Session, user_id: str, model: str) -> dict:
    """同步删除（本地文件删除耗时可观但不需进度流；失败如实落 error_message）。"""
    model = model.strip()
    if not valid_model_tag(model):
        raise err_validation("模型 tag 格式不合法")
    s = _setting_row(db)
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="delete", target=model,
                 status="running", message="删除中")
    db.add(op)
    db.commit()
    db.refresh(op)
    try:
        OllamaClient(s.ollama_host).delete(model)
    except LLMError as e:
        op.status, op.message = "failed", "删除失败"
        op.error_message = e.message[:280]
        db.commit()
        db.refresh(op)
        return op.to_dict()
    if s.ollama_model == model:  # 删掉当前选用模型 → 引擎回退本地规则
        s.lyrics_backend, s.ollama_model = "localsynth", ""
        db.commit()
    op.status, op.progress, op.message = "succeeded", 100, f"已删除 {model}"
    db.commit()
    db.refresh(op)
    return op.to_dict()


def _safe_op(fn, *args) -> None:
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"model op crashed: {e}")


def list_ops(db: Session, limit: int = 10) -> list[dict]:
    rows = db.execute(select(ModelOp).order_by(ModelOp.created_at.desc())
                      .limit(min(limit, 50))).scalars().all()
    return [r.to_dict() for r in rows]


def get_op(db: Session, op_id: str) -> dict:
    op = db.get(ModelOp, op_id)
    if op is None:
        raise err_not_found("操作任务不存在")
    return op.to_dict()


def recover_stale_ops() -> int:
    """启动自愈：服务重启时把遗留 queued/running 的模型操作置 failed。"""
    with SessionLocal() as db:
        rows = db.execute(select(ModelOp).where(
            ModelOp.status.in_(("queued", "running")))).scalars().all()
        now = utc_now_iso()
        for op in rows:
            op.status, op.message = "failed", "任务被系统中断（服务重启）"
            op.updated_at = now
        db.commit()
        return len(rows)


# ---------- 外部 API 连通性 ----------

def test_external(base_url: str, api_key: str, model: str) -> dict:
    if not base_url.strip() or not model.strip():
        raise err_validation("base_url 与 model 必填")
    try:
        sample = OpenAICompatClient(base_url, api_key, model).test(
            base_url=base_url, api_key=api_key, model=model)
        return {"ok": True, "sample": sample[:80], "message": "连接成功，模型可用"}
    except LLMError as e:
        return {"ok": False, "sample": "", "message": e.message}


# ---------- 外部歌曲 API 连通性 ----------

def test_music(base_url: str, api_key: str, model: str = "") -> dict:
    if not base_url.strip():
        raise err_validation("base_url 必填")
    try:
        sample = SunoCompatClient(base_url, api_key, model).test()
        return {"ok": True, "sample": sample[:80], "message": "连接成功，端点可用"}
    except MusicAPIError as e:
        return {"ok": False, "sample": "", "message": e.message}


# ---------- 歌词引擎工厂（services/lyrics 与 generation 消费） ----------

def get_lyrics_provider(db: Session):
    """按全局配置返回歌词 provider；配置异常一律回退本地规则引擎。"""
    s = db.get(LLMSetting, SETTING_ID)
    if s is None or s.lyrics_backend == "localsynth":
        return LocalLyricsProvider()
    try:
        if s.lyrics_backend == "ollama":
            if not s.ollama_model:
                return LocalLyricsProvider()
            client = OllamaClient(s.ollama_host)
            return LLMLyricsProvider(
                chat=lambda sys, p: client.chat(s.ollama_model, sys, p),
                engine=f"ollama:{s.ollama_model}",
                display_name=f"Ollama · {s.ollama_model}")
        if s.lyrics_backend == "openai_compat":
            if not (s.external_base_url and s.external_model):
                return LocalLyricsProvider()
            client = OpenAICompatClient(s.external_base_url, s.external_api_key,
                                        s.external_model)
            return LLMLyricsProvider(
                chat=lambda sys, p: client.chat(sys, p),
                engine=f"openai-compat:{s.external_model}",
                display_name=f"外部API · {s.external_model}")
    except Exception as e:  # noqa: BLE001 —— 配置构造失败不阻断歌词功能
        logger.warning(f"lyrics provider 构造失败，回退本地引擎: {e}")
    return LocalLyricsProvider()


def get_lyrics_chat(db: Session):
    """当前歌词引擎的底层 chat 函数（LLM 通道）；localsynth 返回 None。

    供生成管线做 simple 模式风格扩写等轻量文本任务复用同一模型配置。
    """
    provider = get_lyrics_provider(db)
    chat = getattr(provider, "chat", None)
    return chat if callable(chat) else None


# ---------- 歌曲引擎工厂（services/generation 消费） ----------

def current_music_backend(db: Session) -> str:
    """提交时留痕用：只读配置不构造客户端。"""
    s = db.get(LLMSetting, SETTING_ID)
    if s is None:
        return "localsynth"
    if s.music_backend == "api" and s.music_api_base_url:
        return "api"
    if s.music_backend == "replicate" and s.replicate_api_token and s.music_model:
        return "replicate"
    if s.music_backend == "musicgen_local" and s.music_model:
        return "musicgen_local"
    if s.music_backend == "acestep_local" and s.music_model:
        return "acestep_local"
    return "localsynth"


def get_music_provider(db: Session):
    """按全局配置返回歌曲 provider；配置异常一律回退本地合成引擎。"""
    s = db.get(LLMSetting, SETTING_ID)
    if s is not None:
        entry = CATALOG_BY_ID.get(s.music_model) if s.music_model else None
        try:
            if s.music_backend == "api" and s.music_api_base_url:
                return APIMusicProvider(s.music_api_base_url, s.music_api_key,
                                        s.music_api_model)
            if s.music_backend == "replicate" and s.replicate_api_token and entry:
                slug = (s.replicate_slugs or {}).get(s.music_model) \
                    or entry.get("replicate_slug") or ""
                return ReplicateMusicProvider(s.replicate_api_token, s.music_model, slug)
            if s.music_backend == "musicgen_local" and entry:
                return MusicGenLocalProvider(s.music_model)
            if s.music_backend == "acestep_local" and entry:
                return ACEStepLocalProvider(s.music_model)
        except Exception as e:  # noqa: BLE001 —— 配置构造失败回退本地引擎，创作不中断
            logger.warning(f"music provider 构造失败，回退本地引擎: {e}")
    from app.providers.music_local import LocalSynthProvider
    return LocalSynthProvider()


# ---------- 开源歌曲模型目录（V1.4） ----------

def get_music_catalog(db: Session) -> dict:
    """目录（按外部测评参考分降序）+ 本机状态 + 当前选用 + 免责声明。"""
    s = _setting_row(db)
    deps = musicgen_deps_installed()
    downloaded = set(local_downloaded_ids())
    ace_deps = acestep_deps_installed()
    ace_downloaded = set(acestep_downloaded_ids()) if ace_deps else set()
    slugs: dict = s.replicate_slugs or {}
    models = []
    for rank, m in enumerate(catalog_sorted(), start=1):
        entry = dict(m)
        entry["rank"] = rank
        slug_default = m.get("replicate_slug") or ""
        override = str(slugs.get(m["id"]) or "").strip()
        entry["replicate_slug"] = override or slug_default
        entry["replicate_slug_default"] = slug_default
        entry["replicate_slug_overridden"] = bool(override)
        if "musicgen_local" in m["channels"]:
            if not deps:
                entry["local_status"] = "deps_missing"
            elif m["id"] in downloaded:
                entry["local_status"] = "ready"
            else:
                entry["local_status"] = "not_downloaded"
        elif "acestep_local" in m["channels"]:
            if not ace_deps:
                entry["local_status"] = "deps_missing"
            elif m["id"] in ace_downloaded:
                entry["local_status"] = "ready"
            else:
                entry["local_status"] = "not_downloaded"
        else:
            entry["local_status"] = "not_applicable"
        entry["selected"] = bool(
            s.music_backend in ("replicate", "musicgen_local", "acestep_local")
            and s.music_model == m["id"])
        models.append(entry)
    return {
        "models": models,
        "machine": {"musicgen_deps_installed": deps,
                    "install_hint": "" if deps else musicgen_install_hint(),
                    "downloaded_ids": sorted(downloaded | ace_downloaded),
                    "acestep_deps_installed": ace_deps,
                    "acestep_install_hint": "" if ace_deps else acestep_install_hint()},
        "selected": {"music_backend": s.music_backend,
                     "music_model": s.music_model or None},
        "replicate": {"token_saved": bool(s.replicate_api_token)},
        "disclaimer": CATALOG_DISCLAIMER,
    }


def _execute_music_pull(op_id: str, model_id: str) -> None:
    _write_op(op_id, status="running", message="准备下载模型权重…")
    last = {"t": 0.0, "pct": -1}

    def on_progress(pct: int, message: str) -> None:
        now = time.monotonic()
        if pct < 100 and pct - last["pct"] < 2 and now - last["t"] < 1.0:
            return
        last.update(t=now, pct=pct)
        _write_op(op_id, progress=max(pct, 0), message=message[:280])

    entry = CATALOG_BY_ID.get(model_id) or {}
    is_acestep = "acestep_local" in entry.get("channels", [])
    err_cls = ACEStepLocalError if is_acestep else MusicGenLocalError
    pull_fn = acestep_pull_local if is_acestep else pull_local
    try:
        pull_fn(model_id, on_progress)
        _write_op(op_id, status="succeeded", progress=100, message=f"已下载 {model_id}")
    except err_cls as e:
        _write_op(op_id, status="failed", message="下载失败", error_message=e.message[:280])
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"music pull {model_id} crashed: {e}")
        _write_op(op_id, status="failed", message="下载失败", error_message=str(e)[:280])


def start_music_pull(db: Session, user_id: str, model_id: str) -> dict:
    model_id = model_id.strip()
    entry = CATALOG_BY_ID.get(model_id)
    if entry is None or not ({"musicgen_local", "acestep_local"} & set(entry.get("channels", []))):
        raise err_validation(f"模型不支持本地下载：{model_id}")
    running = db.execute(select(ModelOp).where(
        ModelOp.status.in_(("queued", "running")))).scalars().all()
    if any(op.target == model_id for op in running):
        raise err_conflict(f"模型 {model_id} 正在下载中")
    if running:
        raise err_conflict("已有模型下载任务进行中，请等待完成后再发起")
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="music_pull", target=model_id,
                 status="queued", message="排队中")
    db.add(op)
    db.commit()
    db.refresh(op)
    _op_executor.submit(_safe_op, _execute_music_pull, op.id, model_id)
    return op.to_dict()


def run_music_delete(db: Session, user_id: str, model_id: str) -> dict:
    model_id = model_id.strip()
    entry = CATALOG_BY_ID.get(model_id)
    if entry is None or not entry.get("local_hf_id") or not (
            {"musicgen_local", "acestep_local"} & set(entry.get("channels", []))):
        raise err_validation(f"模型不支持本地删除：{model_id}")
    is_acestep = "acestep_local" in entry.get("channels", [])
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="music_delete", target=model_id,
                 status="running", message="删除中")
    db.add(op)
    db.commit()
    db.refresh(op)
    try:
        (acestep_delete_local if is_acestep else delete_local)(model_id)
    except (ACEStepLocalError, MusicGenLocalError) as e:
        op.status, op.message = "failed", "删除失败"
        op.error_message = e.message[:280]
        db.commit()
        db.refresh(op)
        return op.to_dict()
    s = _setting_row(db)
    if s.music_model == model_id and s.music_backend in ("musicgen_local", "acestep_local"):
        s.music_backend, s.music_model = "localsynth", ""  # 删掉选用模型 → 回退本地合成
        db.commit()
    op.status, op.progress, op.message = "succeeded", 100, f"已删除 {model_id}"
    db.commit()
    db.refresh(op)
    return op.to_dict()


def test_replicate(api_token: str, base_url: str = "", model: str = "") -> dict:
    if not (api_token or "").strip():
        raise err_validation("API Token 必填")
    try:
        client = ReplicateClient(api_token, base_url or "")
        acct = client.account()
        username = acct.get("username") or acct.get("type") or "ok"
        message = f"Token 有效（账号 {username}）"
        sample = ""
        slug = (model or "").strip()
        if slug:
            m = client.get_model(slug)
            sample = f"{m.get('owner')}/{m.get('name')}"
            message += f"；模型 {sample} 存在"
        return {"ok": True, "sample": sample[:80] or str(username)[:80], "message": message}
    except ReplicateError as e:
        return {"ok": False, "sample": "", "message": e.message}
