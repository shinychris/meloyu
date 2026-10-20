"""模型中心服务：本地开源模型（Ollama）下载/删除/列举 + 外部 API 配置
+ 歌词引擎工厂（V1.2）+ 外部歌曲生成 API 通道（V1.3）
+ 开源歌曲模型目录/Replicate 托管/本机 MusicGen（V1.4）
+ 本机 ACE-Step v1.5 人声成曲通道（V1.5，ADR-016）。

进度写库节流（≥2% 或 ≥1s 才落一次），拉取线程与生成任务线程池隔离（各 1 worker）。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.i18n import current_locale, run_with_locale, tr
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
)
from app.providers.music_acestep import (
    delete_local as acestep_delete_local,
)
from app.providers.music_acestep import (
    local_downloaded_ids as acestep_downloaded_ids,
)
from app.providers.music_acestep import (
    pull_local as acestep_pull_local,
)
from app.providers.music_api import APIMusicProvider, MusicAPIError, SunoCompatClient
from app.providers.music_catalog import (
    ACESTEP_RUNNABLE_IDS as _ACESTEP_IDS,
)
from app.providers.music_catalog import (
    CATALOG_BY_ID,
    LOCAL_RUNNABLE_IDS,
    catalog_disclaimer,
    catalog_sorted,
    localized_entry,
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
from app.providers.music_selfhosted import (
    MiniMaxSelfHostedProvider,
    SongGenSelfHostedProvider,
    probe_service,
)
from app.services.acestep_deploy import ACEStepDeployError, deploy_acestep

_op_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meloyu-model-op")

# ---------- 运行环境感知（Ollama/自托管端点的容器内寻址） ----------

# Docker Desktop（Windows/macOS）内置域名，容器内经它访问宿主机端口；
# Linux 原生 docker 需在 compose 给服务加 extra_hosts: ["host.docker.internal:host-gateway"]
_DOCKER_HOST_ALIAS = "http://host.docker.internal:11434"
_LOOPBACK_OLLAMA_HOSTS = frozenset({
    "http://localhost:11434", "http://127.0.0.1:11434"})


def _in_docker() -> bool:
    """backend 是否跑在容器里（deploy/docker-compose.yml 生产形态）。"""
    return Path("/.dockerenv").exists()

# 推荐 pull 的本地模型（tag 须与 Ollama 仓库一致；大小为约值）。
# 注：qwen3.5 系列支持关闭思考链直出；旧 qwen3 系列常开思考，CPU 混合推理下一首
# 歌词可能数分钟——无独显机器优先选小模型。
RECOMMENDED_MODELS: list[dict] = [  # note 为 (zh, en) 双语
    {"tag": "qwen3.5:1.7b", "name": "Qwen3.5 1.7B", "size_mb": 1147,
     "note": ("推荐：思考可关、直出快，中文歌词质量性价比档",
              "Recommended: thinking can be disabled for fast direct output; best "
              "value for Chinese lyric quality")},
    {"tag": "qwen3.5:4b", "name": "Qwen3.5 4B", "size_mb": 3390,
     "note": ("质量档（本机预装）：4B 级中文写作最佳，无独显约 1~3 分钟/首",
              "Quality tier (pre-installed locally): best 4B-class Chinese writing; "
              "about 1-3 minutes per song without a discrete GPU")},
    {"tag": "qwen3:0.6b", "name": "Qwen3 0.6B", "size_mb": 522,
     "note": ("最轻档：CPU 可用，常开思考但量小，链路验证/低配首选",
              "Lightest tier: runs on CPU; always-on thinking but a small "
              "footprint - top pick for pipeline validation or low-end machines")},
    {"tag": "qwen3:1.7b", "name": "Qwen3 1.7B", "size_mb": 1060,
     "note": ("轻量档：常开思考，速度与质量折中",
              "Lightweight tier: always-on thinking; a speed/quality compromise")},
    {"tag": "deepseek-r1:1.5b", "name": "DeepSeek-R1 1.5B", "size_mb": 1053,
     "note": ("推理型小模型：韵脚推敲认真，思考链较长",
              "Small reasoning model: careful rhyme crafting, but longer thinking "
              "chains")},
    {"tag": "gemma3:270m", "name": "Gemma3 270M", "size_mb": 311,
     "note": ("极限小体积冒烟档，仅用于链路验证",
              "Ultra-compact smoke-test tier, for pipeline validation only")},
]


def recommended_models() -> list[dict]:
    return [{**m, "note": tr(m["note"][0], m["note"][1])} for m in RECOMMENDED_MODELS]

EXTERNAL_PRESETS: list[dict] = [  # vendor/model_hint 为 (zh, en) 双语
    {"vendor": ("智谱 GLM", "Zhipu GLM"),
     "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model_hint": ("glm-4-flash（免费档）/ glm-4-air", "glm-4-flash (free tier) / glm-4-air")},
    {"vendor": ("DeepSeek", "DeepSeek"), "base_url": "https://api.deepseek.com/v1",
     "model_hint": ("deepseek-chat", "deepseek-chat")},
    {"vendor": ("OpenAI", "OpenAI"), "base_url": "https://api.openai.com/v1",
     "model_hint": ("gpt-4o-mini", "gpt-4o-mini")},
    {"vendor": ("Moonshot", "Moonshot"), "base_url": "https://api.moonshot.cn/v1",
     "model_hint": ("moonshot-v1-8k", "moonshot-v1-8k")},
    {"vendor": ("Ollama 本地网关", "Ollama local gateway"),
     "base_url": "http://localhost:11434/v1",
     "model_hint": ("qwen3.5:4b（需先 ollama pull；Key 任意填）",
                    "qwen3.5:4b (requires ollama pull first; any key value works)")},
]


def external_presets() -> list[dict]:
    out = []
    for p in EXTERNAL_PRESETS:
        base_url = p["base_url"]
        # Ollama 本地网关预设按运行环境给地址：容器内 localhost 指向容器自身，
        # 须走 host.docker.internal 才能到宿主机 Ollama
        if base_url == "http://localhost:11434/v1" and _in_docker():
            base_url = "http://host.docker.internal:11434/v1"
        out.append({"vendor": tr(*p["vendor"]), "base_url": base_url,
                    "model_hint": tr(*p["model_hint"])})
    return out

# 外部歌曲生成 API 预设（Suno 兼容协议，ADR-010）：base 填网关根，自动补 /api/v1
MUSIC_API_PRESETS: list[dict] = [  # vendor 为 (zh, en) 双语
    {"vendor": ("GoAPI（Suno 中转）", "GoAPI (Suno relay)"),
     "base_url": "https://api.goapi.ai/suno", "model_hint": ""},
    {"vendor": ("自建 suno-api 网关", "Self-hosted suno-api gateway"),
     "base_url": "http://localhost:3000", "model_hint": ""},
]


def music_api_presets() -> list[dict]:
    return [{"vendor": tr(*p["vendor"]), "base_url": p["base_url"],
             "model_hint": p["model_hint"]} for p in MUSIC_API_PRESETS]


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
        "local_service_hosts": s.local_service_hosts or {},
    }


_MUSIC_BACKENDS = ("localsynth", "api", "replicate", "musicgen_local", "acestep_local",
                   "mmax_local", "songgen_local")
# 自托管推理服务通道（V1.5.1，ADR-017）：模型装在用户环境，端点可配置
_SELFHOSTED_BACKENDS = ("mmax_local", "songgen_local")


def update_settings(db: Session, patch: dict) -> dict:
    s = _setting_row(db)
    backend = patch.get("lyrics_backend", s.lyrics_backend)
    if backend not in ("localsynth", "ollama", "openai_compat"):
        raise err_validation(tr("lyrics_backend 必须为 localsynth/ollama/openai_compat",
                                "lyrics_backend must be localsynth/ollama/openai_compat"))
    if backend == "ollama" and not (patch.get("ollama_model") or s.ollama_model):
        raise err_validation(tr("ollama 通道需要先选择本地模型",
                                "The Ollama channel needs a local model selected first"))
    if backend == "openai_compat":
        base = patch.get("external_base_url", s.external_base_url)
        model = patch.get("external_model", s.external_model)
        if not base or not model:
            raise err_validation(tr("外部 API 通道需要 base_url 与 model",
                                    "The external API channel needs base_url and model"))

    music_backend = patch.get("music_backend")
    music_model = str(patch.get("music_model") or "").strip()
    if not music_model and "music_model" not in patch:
        music_model = s.music_model
    if music_backend is None:
        music_backend = s.music_backend
        # 仅选模型未显式给通道：按模型可用通道自动切换（显式 music_backend 优先；
        # 有 Replicate Token 优先托管，否则本机/自托管通道 ACE-Step > MiniMax > SongGen > MusicGen）
        if music_model and music_model != s.music_model:
            entry = CATALOG_BY_ID.get(music_model)
            if entry:
                channels = entry.get("channels", [])
                if "replicate" in channels and (
                        patch.get("replicate_api_token") or s.replicate_api_token):
                    music_backend = "replicate"
                elif "acestep_local" in channels:
                    music_backend = "acestep_local"
                elif "mmax_local" in channels:
                    music_backend = "mmax_local"
                elif "songgen_local" in channels:
                    music_backend = "songgen_local"
                elif "musicgen_local" in channels:
                    music_backend = "musicgen_local"
    if music_backend not in _MUSIC_BACKENDS:
        raise err_validation(
            tr("music_backend 必须为 localsynth/api/replicate/musicgen_local/"
               "acestep_local/mmax_local/songgen_local",
               "music_backend must be localsynth/api/replicate/musicgen_local/"
               "acestep_local/mmax_local/songgen_local"))
    if music_backend == "api" and not (patch.get("music_api_base_url") or s.music_api_base_url):
        raise err_validation(tr("外部歌曲 API 通道需要先配置 base_url",
                                "The external song API channel needs base_url configured"))
    if music_backend not in ("localsynth", "api"):
        entry = CATALOG_BY_ID.get(music_model)
        if entry is None:
            raise err_validation(
                tr(f"开源模型目录中不存在：{music_model or '（未选择模型）'}",
                   f"Not in the open-source model catalog: "
                   f"{music_model or '(no model selected)'}"))
        if music_backend not in entry.get("channels", []):
            raise err_validation(
                tr(f"模型 {music_model} 不支持 {music_backend} 通道"
                   f"（可用：{'/'.join(entry['channels'])}）",
                   f"Model {music_model} does not support the {music_backend} channel "
                   f"(available: {'/'.join(entry['channels'])})"))
        if music_backend == "replicate" and not (
                patch.get("replicate_api_token") or s.replicate_api_token):
            raise err_validation(tr("Replicate 通道需要先配置 API Token",
                                    "The Replicate channel needs an API token configured"))
        if music_backend == "musicgen_local" and music_model not in LOCAL_RUNNABLE_IDS:
            raise err_validation(
                tr(f"模型 {music_model} 不支持本机运行（需 GPU 档请走 Replicate）",
                   f"Model {music_model} does not support local execution "
                   f"(GPU-only tiers should use Replicate)"))
        if music_backend == "acestep_local" and music_model not in _ACESTEP_IDS:
            raise err_validation(
                tr(f"模型 {music_model} 不支持本机 ACE-Step 通道",
                   f"Model {music_model} does not support the local ACE-Step channel"))

    for field in ("ollama_host", "ollama_model", "external_base_url", "external_model",
                  "music_api_base_url", "music_api_model", "music_model"):
        if field in patch and patch[field] is not None:
            v = str(patch[field]).strip()
            if len(v) > 300:
                raise err_validation(tr(f"{field} 过长", f"{field} is too long"))
            setattr(s, field, v)
    # P1-2：key/token 落库一律 Fernet 加密（KEY_ENCRYPTION_SECRET 未配置时明文直通）
    if patch.get("external_api_key"):  # 空串=保持不变（脱敏读回无法回显）
        s.external_api_key = encrypt_secret(str(patch["external_api_key"]).strip())
    if patch.get("music_api_key"):
        s.music_api_key = encrypt_secret(str(patch["music_api_key"]).strip())
    if "replicate_api_token" in patch:  # V1.4：显式空串=清除（前端仅在输入时携带该字段）
        s.replicate_api_token = encrypt_secret(
            str(patch.get("replicate_api_token") or "").strip())
    if isinstance(patch.get("replicate_slugs"), dict):
        slugs = {}
        for mid, slug in patch["replicate_slugs"].items():
            if mid not in CATALOG_BY_ID:
                raise err_validation(tr(f"replicate_slugs 含未知模型：{mid}",
                                        f"replicate_slugs contains an unknown model: {mid}"))
            v = str(slug or "").strip()
            if len(v) > 120 or any(c in v for c in " ?#") or v.count("/") > 1:
                raise err_validation(
                    tr(f"slug 不合法（应为 owner/name）：{mid}={v[:60]}",
                       f"Invalid slug (expected owner/name): {mid}={v[:60]}"))
            if v:
                slugs[mid] = v
        s.replicate_slugs = slugs
    if isinstance(patch.get("local_service_hosts"), dict):
        hosts = {}
        for ch, host in patch["local_service_hosts"].items():
            if ch not in _SELFHOSTED_BACKENDS:
                raise err_validation(tr(f"local_service_hosts 含未知通道：{ch}",
                                        f"local_service_hosts contains an unknown channel: {ch}"))
            v = str(host or "").strip().rstrip("/")
            if v and not v.startswith(("http://", "https://")):
                raise err_validation(
                    tr(f"端点须为 http(s)://…：{ch}={v[:60]}",
                       f"Endpoint must be http(s)://...: {ch}={v[:60]}"))
            if len(v) > 300:
                raise err_validation(tr(f"{ch} 端点过长", f"{ch} endpoint is too long"))
            hosts[ch] = v  # 空串=回退默认端点
        merged = dict(s.local_service_hosts or {})
        merged.update(hosts)
        s.local_service_hosts = merged
    s.lyrics_backend = backend
    s.music_backend = music_backend
    db.commit()
    db.refresh(s)
    return get_settings(db)


# ---------- 运行时状态 / 本地模型 ----------

def _ollama_client(db: Session, s: LLMSetting) -> OllamaClient:
    """按配置构造 OllamaClient；容器内 loopback 自动改用宿主机别名并持久化。

    生产部署（docker-compose）下 DB 默认值 http://localhost:11434 在容器内指向
    容器自身而非宿主机 Ollama——统一替换为 host.docker.internal（Docker Desktop
    内置域名）并写回 DB：状态检测/下载/删除/推理直接用正确地址，模型中心回显
    一致。宿主机 Ollama 须监听 0.0.0.0（OLLAMA_HOST=0.0.0.0）方可从容器可达，
    未安装时的引导见 runtime_status 的 install_hint。用户显式配置非 loopback
    地址（如自建 ollama 容器服务名）不受影响。dev（宿主机 uvicorn）完全不变。
    """
    client = OllamaClient(s.ollama_host)
    if _in_docker() and client.base in _LOOPBACK_OLLAMA_HOSTS:
        logger.info("ollama_host 容器内自动回退: {} → {}", client.base, _DOCKER_HOST_ALIAS)
        client = OllamaClient(_DOCKER_HOST_ALIAS)
        s.ollama_host = _DOCKER_HOST_ALIAS
        db.commit()
    return client


def _ollama_install_hint() -> str:
    if _in_docker():
        return tr(
            "容器内未检测到 Ollama（host.docker.internal:11434）：宿主机需安装 "
            "Ollama（https://ollama.com/download）并监听 0.0.0.0——设置环境变量 "
            "OLLAMA_HOST=0.0.0.0 后重启 Ollama，容器才能经内置域名访问 11434 端口",
            "No Ollama detected inside the container (host.docker.internal:11434): "
            "install Ollama on the host (https://ollama.com/download) and make it "
            "listen on 0.0.0.0 — set OLLAMA_HOST=0.0.0.0 and restart Ollama so the "
            "container can reach port 11434 via the built-in domain")
    return tr("本机未检测到 Ollama 服务：https://ollama.com/download 安装后"
              "运行 `ollama serve`（Windows 安装包常驻自启）",
              "No local Ollama service detected: install from "
              "https://ollama.com/download, then run `ollama serve` "
              "(the Windows installer stays resident and auto-starts)")


def runtime_status(db: Session) -> dict:
    s = _setting_row(db)
    client = _ollama_client(db, s)
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
            "install_hint": _ollama_install_hint(),
        },
        "docker": _in_docker(),
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
        return tr("外部API · ", "External API · ") + s.external_model
    return tr("离线规则引擎（兜底·非 AI 模型）", "Offline rules engine (fallback, non-AI)")


def song_engine_label(db: Session) -> str:
    s = _setting_row(db)
    if s.music_backend == "api" and s.music_api_base_url:
        try:
            provider = APIMusicProvider(s.music_api_base_url,
                                    decrypt_secret(s.music_api_key),
                                        s.music_api_model)
            return provider.display_name
        except Exception as e:  # noqa: BLE001 —— 展示用标签，构造失败不阻断
            logger.warning(f"song engine label 构造失败: {e}")
            return tr("外部歌曲API（配置异常）", "External song API (misconfigured)")
    entry = CATALOG_BY_ID.get(s.music_model) if s.music_model else None
    if s.music_backend == "replicate" and entry:
        return f"Replicate · {entry['name']}"
    if s.music_backend == "musicgen_local" and entry:
        return tr("MusicGen 本地 · ", "MusicGen Local · ") + entry['name']
    if s.music_backend == "acestep_local" and entry:
        return tr("ACE-Step 本地 · ", "ACE-Step Local · ") + entry['name']
    if s.music_backend in _SELFHOSTED_BACKENDS and entry:
        tail = (tr("SGLang 服务", "SGLang service") if s.music_backend == "mmax_local"
                else tr("Studio 服务", "Studio service"))
        zh = f"{entry['name']} · 自托管（{tail}）"
        en = f"{entry['name']} · Self-hosted ({tail})"
        return tr(zh, en)
    if (s.music_backend in ("replicate", "musicgen_local", "acestep_local")
            or s.music_backend in _SELFHOSTED_BACKENDS):
        return tr("开源模型（未选择模型）", "Open-source model (none selected)")
    return tr("离线合成引擎（兜底·非 AI 模型）", "Offline synth engine (fallback, non-AI)")


def list_local_models(db: Session) -> dict:
    s = _setting_row(db)
    client = _ollama_client(db, s)
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
            "pulling": pulling, "error": err, "recommended": recommended_models()}


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
    _write_op(op_id, status="running", message=tr("连接 Ollama…", "Connecting to Ollama…"))
    last = {"t": 0.0, "pct": -1}

    def on_progress(status: str, pct: int) -> None:
        now = time.monotonic()
        if pct < 100 and pct - last["pct"] < 2 and now - last["t"] < 1.0:
            return
        last.update(t=now, pct=pct)
        _write_op(op_id, progress=max(pct, 0), message=status)

    try:
        OllamaClient(host).pull(model, on_progress)
        _write_op(op_id, status="succeeded", progress=100,
                  message=tr(f"已下载 {model}", f"Downloaded {model}"))
    except LLMError as e:
        _write_op(op_id, status="failed", message=tr("下载失败", "Download failed"),
                  error_message=e.message[:280])
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"model pull {model} crashed: {e}")
        _write_op(op_id, status="failed", message=tr("下载失败", "Download failed"),
                  error_message=str(e)[:280])


def start_pull(db: Session, user_id: str, model: str) -> dict:
    model = model.strip()
    if not valid_model_tag(model):
        raise err_validation(
            tr("模型 tag 格式不合法（允许字母数字与 . _ : @ / + -）",
               "Invalid model tag (allowed: alphanumerics and . _ : @ / + -)"))
    running = db.execute(select(ModelOp).where(
        ModelOp.status.in_(("queued", "running")))).scalars().all()
    if any(op.target == model for op in running):
        raise err_conflict(tr(f"模型 {model} 正在下载中", f"Model {model} is already downloading"))
    if any(op.target != model for op in running):
        raise err_conflict(tr("已有模型下载任务进行中，请等待完成后再发起",
                              "Another model download is in progress; wait for it to "
                              "finish before starting a new one"))
    s = _setting_row(db)
    host = _ollama_client(db, s).base  # 容器内 loopback 已在此修正并持久化
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="pull", target=model,
                 status="queued", message=tr("排队中", "Queued"))
    db.add(op)
    db.commit()
    db.refresh(op)
    _submit_op(_execute_pull, op.id, model, host)
    return op.to_dict()


def run_delete(db: Session, user_id: str, model: str) -> dict:
    """同步删除（本地文件删除耗时可观但不需进度流；失败如实落 error_message）。"""
    model = model.strip()
    if not valid_model_tag(model):
        raise err_validation(tr("模型 tag 格式不合法", "Invalid model tag"))
    s = _setting_row(db)
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="delete", target=model,
                 status="running", message=tr("删除中", "Deleting"))
    db.add(op)
    db.commit()
    db.refresh(op)
    try:
        _ollama_client(db, s).delete(model)
    except LLMError as e:
        op.status, op.message = "failed", tr("删除失败", "Delete failed")
        op.error_message = e.message[:280]
        db.commit()
        db.refresh(op)
        return op.to_dict()
    if s.ollama_model == model:  # 删掉当前选用模型 → 引擎回退本地规则
        s.lyrics_backend, s.ollama_model = "localsynth", ""
        db.commit()
    op.status, op.progress, op.message = "succeeded", 100, \
        tr(f"已删除 {model}", f"Deleted {model}")
    db.commit()
    db.refresh(op)
    return op.to_dict()


def _safe_op(fn, *args) -> None:
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"model op crashed: {e}")


def _submit_op(fn, *args) -> None:
    """提交模型操作到单 worker 线程池；捕获提交时 locale，worker 内恢复。"""
    _op_executor.submit(run_with_locale, current_locale(), _safe_op, fn, *args)


def list_ops(db: Session, limit: int = 10) -> list[dict]:
    rows = db.execute(select(ModelOp).order_by(ModelOp.created_at.desc())
                      .limit(min(limit, 50))).scalars().all()
    return [r.to_dict() for r in rows]


def get_op(db: Session, op_id: str) -> dict:
    op = db.get(ModelOp, op_id)
    if op is None:
        raise err_not_found(tr("操作任务不存在", "Operation not found"))
    return op.to_dict()


def recover_stale_ops() -> int:
    """启动自愈：服务重启时把遗留 queued/running 的模型操作置 failed。"""
    with SessionLocal() as db:
        rows = db.execute(select(ModelOp).where(
            ModelOp.status.in_(("queued", "running")))).scalars().all()
        now = utc_now_iso()
        for op in rows:
            op.status, op.message = "failed", tr("任务被系统中断（服务重启）",
                                                 "Interrupted by a system restart")
            op.updated_at = now
        db.commit()
        return len(rows)


# ---------- 外部 API 连通性 ----------

def test_external(base_url: str, api_key: str, model: str) -> dict:
    if not base_url.strip() or not model.strip():
        raise err_validation(tr("base_url 与 model 必填", "base_url and model are required"))
    try:
        sample = OpenAICompatClient(base_url, api_key, model).test(
            base_url=base_url, api_key=api_key, model=model)
        return {"ok": True, "sample": sample[:80],
                "message": tr("连接成功，模型可用", "Connected; the model is available")}
    except LLMError as e:
        return {"ok": False, "sample": "", "message": e.message}


# ---------- 外部歌曲 API 连通性 ----------

def test_music(base_url: str, api_key: str, model: str = "") -> dict:
    if not base_url.strip():
        raise err_validation(tr("base_url 必填", "base_url is required"))
    try:
        sample = SunoCompatClient(base_url, api_key, model).test()
        return {"ok": True, "sample": sample[:80],
                "message": tr("连接成功，端点可用", "Connected; the endpoint is available")}
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
            client = _ollama_client(db, s)
            return LLMLyricsProvider(
                chat=lambda sys, p: client.chat(s.ollama_model, sys, p),
                engine=f"ollama:{s.ollama_model}",
                display_name=f"Ollama · {s.ollama_model}")
        if s.lyrics_backend == "openai_compat":
            if not (s.external_base_url and s.external_model):
                return LocalLyricsProvider()
            client = OpenAICompatClient(s.external_base_url,
                                       decrypt_secret(s.external_api_key),
                                        s.external_model)
            return LLMLyricsProvider(
                chat=lambda sys, p: client.chat(sys, p),
                engine=f"openai-compat:{s.external_model}",
                display_name=tr("外部API · ", "External API · ") + s.external_model)
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


def current_lyrics_backend(db: Session) -> str:
    """留痕/用量统计用：当前生效的歌词引擎通道族（配置不完整按回退本地计）。

    与 get_lyrics_provider 的回退口径一致（ollama 缺模型 / openai_compat 缺
    端点+模型 → localsynth）；完整引擎串（含模型名）见任务快照 _resolved.lyrics_engine。
    """
    s = db.get(LLMSetting, SETTING_ID)
    if s is None:
        return "localsynth"
    if s.lyrics_backend == "ollama" and s.ollama_model:
        return "ollama"
    if (s.lyrics_backend == "openai_compat"
            and s.external_base_url and s.external_model):
        return "openai_compat"
    return "localsynth"


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
    if s.music_backend in _SELFHOSTED_BACKENDS and s.music_model:
        return s.music_backend
    return "localsynth"


def get_music_provider(db: Session):
    """按全局配置返回歌曲 provider；配置异常一律回退本地合成引擎。"""
    s = db.get(LLMSetting, SETTING_ID)
    if s is not None:
        entry = CATALOG_BY_ID.get(s.music_model) if s.music_model else None
        try:
            if s.music_backend == "api" and s.music_api_base_url:
                return APIMusicProvider(s.music_api_base_url,
                                         decrypt_secret(s.music_api_key),
                                        s.music_api_model)
            if s.music_backend == "replicate" and s.replicate_api_token and entry:
                slug = (s.replicate_slugs or {}).get(s.music_model) \
                    or entry.get("replicate_slug") or ""
                return ReplicateMusicProvider(decrypt_secret(s.replicate_api_token),
                                               s.music_model, slug)
            if s.music_backend == "musicgen_local" and entry:
                return MusicGenLocalProvider(s.music_model)
            if s.music_backend == "acestep_local" and entry:
                return ACEStepLocalProvider(s.music_model)
            if s.music_backend == "mmax_local" and entry:
                return MiniMaxSelfHostedProvider(s.music_model, s.local_service_hosts)
            if s.music_backend == "songgen_local" and entry:
                return SongGenSelfHostedProvider(s.music_model, s.local_service_hosts)
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
    ace_deploy_op = db.execute(
        select(ModelOp).where(ModelOp.op_type == "acestep_deploy")
        .order_by(ModelOp.created_at.desc()).limit(1)).scalars().first()
    probes = {ch: probe_service(ch, s.local_service_hosts) for ch in _SELFHOSTED_BACKENDS}
    slugs: dict = s.replicate_slugs or {}
    models = []
    for rank, m in enumerate(catalog_sorted(), start=1):
        entry = localized_entry(m)  # 展示字段按 locale 展开（zh 原样 / en 英文）
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
        elif any(ch in m["channels"] for ch in _SELFHOSTED_BACKENDS):
            ch = next(ch for ch in _SELFHOSTED_BACKENDS if ch in m["channels"])
            # 服务型通道：ready=服务在线（不要求此刻已载入模型，生成时会自动 load）
            entry["local_status"] = "ready" if probes[ch]["running"] else "not_running"
            entry["service_detail"] = probes[ch]["detail"]
        else:
            entry["local_status"] = "not_applicable"
        entry["selected"] = bool(
            s.music_backend in _MUSIC_BACKENDS and s.music_backend != "localsynth"
            and s.music_backend != "api"
            and s.music_model == m["id"])
        models.append(entry)
    return {
        "models": models,
        "machine": {"musicgen_deps_installed": deps,
                    "install_hint": "" if deps else musicgen_install_hint(),
                    "downloaded_ids": sorted(downloaded | ace_downloaded),
                    "acestep_deps_installed": ace_deps,
                    "acestep_install_hint": "" if ace_deps else acestep_install_hint(),
                    # v0.16.3 组件自动部署：最近一次部署操作（首启自动/手动共用）
                    # 供组件中心展示进度；desktop 形态默认首启自动部署
                    "acestep_deploy_op": ace_deploy_op.to_dict() if ace_deploy_op else None,
                    "acestep_auto_deploy": (settings.app_mode == "desktop"
                                            and settings.acestep_auto_deploy),
                    "services": probes},
        "selected": {"music_backend": s.music_backend,
                     "music_model": s.music_model or None},
        "replicate": {"token_saved": bool(s.replicate_api_token)},
        "disclaimer": catalog_disclaimer(),
    }


def _execute_music_pull(op_id: str, model_id: str) -> None:
    _write_op(op_id, status="running",
              message=tr("准备下载模型权重…", "Preparing model weight download…"))
    on_progress = _throttled_progress(op_id)
    entry = CATALOG_BY_ID.get(model_id) or {}
    is_acestep = "acestep_local" in entry.get("channels", [])
    err_cls = ACEStepLocalError if is_acestep else MusicGenLocalError
    pull_fn = acestep_pull_local if is_acestep else pull_local
    try:
        # v0.16.3：acestep 依赖未部署时先应用内自动部署（源码+uv 引导+venv，
        # 约 4GB，进度占 0~30%），再下权重（30~100%）——桌面用户单按钮走完
        # 全链路，不再要求跑脚本（方案 §3.2 组件中心 + 默认安装即部署）
        if is_acestep and not acestep_deps_installed():
            deploy_acestep(lambda pct, msg: on_progress(int(pct * 0.3), msg))

            def weights_progress(pct: int, message: str) -> None:
                on_progress(30 + int(pct * 0.7), message)

            pull_fn(model_id, weights_progress)
        else:
            pull_fn(model_id, on_progress)
        _write_op(op_id, status="succeeded", progress=100,
                  message=tr(f"已下载 {model_id}", f"Downloaded {model_id}"))
    except (ACEStepDeployError, err_cls) as e:  # type: ignore[misc] —— 动态 err_cls
        detail = e.message
        if isinstance(e, ACEStepDeployError):
            # 自动部署失败时附手动兜底指引（dev=脚本 / desktop=组件中心重试）
            detail = f"{detail}；{acestep_install_hint()}"
        _write_op(op_id, status="failed", message=tr("下载失败", "Download failed"),
                  error_message=detail[:280])
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"music pull {model_id} crashed: {e}")
        _write_op(op_id, status="failed", message=tr("下载失败", "Download failed"),
                  error_message=str(e)[:280])


def _throttled_progress(op_id: str):
    """操作进度落库节流（≥2% 或 ≥1s 才写一次）。"""
    last = {"t": 0.0, "pct": -1}

    def on_progress(pct: int, message: str) -> None:
        now = time.monotonic()
        if pct < 100 and pct - last["pct"] < 2 and now - last["t"] < 1.0:
            return
        last.update(t=now, pct=pct)
        _write_op(op_id, progress=max(pct, 0), message=message[:280])

    return on_progress


def _execute_acestep_deploy(op_id: str) -> None:
    on_progress = _throttled_progress(op_id)
    _write_op(op_id, status="running",
              message=tr("准备部署 ACE-Step 组件…", "Preparing ACE-Step deployment…"))
    try:
        deploy_acestep(on_progress)
        _write_op(op_id, status="succeeded", progress=100,
                  message=tr("ACE-Step 组件部署完成（权重请在下方下载）",
                             "ACE-Step component deployed "
                             "(download weights below)"))
    except ACEStepDeployError as e:
        _write_op(op_id, status="failed",
                  message=tr("组件部署失败", "Component deployment failed"),
                  error_message=f"{e.message}；{acestep_install_hint()}"[:280])
    except Exception as e:  # noqa: BLE001 —— 线程兜底
        logger.exception(f"acestep deploy crashed: {e}")
        _write_op(op_id, status="failed",
                  message=tr("组件部署失败", "Component deployment failed"),
                  error_message=str(e)[:280])


def start_acestep_deploy(db: Session, user_id: str, *, auto: bool = False) -> dict | None:
    """发起 ACE-Step 组件部署（异步，轮询 GET /models/ops/{id} 看进度）。

    auto=True 为 desktop 首启自动部署（v0.16.3：默认安装即部署完成）——
    已就绪时静默跳过（返回 None，不落 ops 防每次启动刷记录）；有其他操作
    进行中则冲突，由调用方（main.py）捕获静默跳过，下次启动自愈。
    手动调用（auto=False）已就绪时幂等落 succeeded 秒回。
    """
    if acestep_deps_installed():
        if auto:
            return None
        op = ModelOp(id=new_uuid(), user_id=user_id, op_type="acestep_deploy",
                     target="acestep", status="succeeded", progress=100,
                     message=tr("ACE-Step 组件已就绪", "ACE-Step component ready"))
        db.add(op)
        db.commit()
        db.refresh(op)
        return op.to_dict()
    running = db.execute(select(ModelOp).where(
        ModelOp.status.in_(("queued", "running")))).scalars().all()
    if any(op.target == "acestep" for op in running):
        raise err_conflict(tr("ACE-Step 组件正在部署中",
                              "ACE-Step component deployment is already running"))
    if running:
        raise err_conflict(tr("已有模型下载任务进行中，请等待完成后再发起",
                              "Another model download is in progress; wait for it "
                              "to finish before starting a new one"))
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="acestep_deploy",
                 target="acestep", status="queued",
                 message=tr("排队中（首启自动）" if auto else "排队中",
                            "Queued (auto)" if auto else "Queued"))
    db.add(op)
    db.commit()
    db.refresh(op)
    _submit_op(_execute_acestep_deploy, op.id)
    return op.to_dict()


_DOWNLOADABLE_CHANNELS = {"musicgen_local", "acestep_local"}  # 下载型本机通道（V1.5.1 区分）


def start_music_pull(db: Session, user_id: str, model_id: str) -> dict:
    model_id = model_id.strip()
    entry = CATALOG_BY_ID.get(model_id)
    if entry is None:
        raise err_validation(tr(f"模型不支持本地下载：{model_id}",
                                f"Model does not support local download: {model_id}"))
    if not (_DOWNLOADABLE_CHANNELS & set(entry.get("channels", []))):
        raise err_validation(
            tr(f"模型 {model_id} 走自托管推理服务通道：权重由服务侧（SGLang-Omni / "
               "SongGeneration-Studio）管理，无需在此下载",
               f"Model {model_id} uses the self-hosted inference service channel: "
               "weights are managed by the service side (SGLang-Omni / "
               "SongGeneration-Studio); no download needed here"))
    running = db.execute(select(ModelOp).where(
        ModelOp.status.in_(("queued", "running")))).scalars().all()
    if any(op.target == model_id for op in running):
        raise err_conflict(tr(f"模型 {model_id} 正在下载中",
                              f"Model {model_id} is already downloading"))
    if running:
        raise err_conflict(tr("已有模型下载任务进行中，请等待完成后再发起",
                              "Another model download is in progress; wait for it to "
                              "finish before starting a new one"))
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="music_pull", target=model_id,
                 status="queued", message=tr("排队中", "Queued"))
    db.add(op)
    db.commit()
    db.refresh(op)
    _submit_op(_execute_music_pull, op.id, model_id)
    return op.to_dict()


def run_music_delete(db: Session, user_id: str, model_id: str) -> dict:
    model_id = model_id.strip()
    entry = CATALOG_BY_ID.get(model_id)
    if entry is None or not entry.get("local_hf_id"):
        raise err_validation(tr(f"模型不支持本地删除：{model_id}",
                                f"Model does not support local deletion: {model_id}"))
    if not (_DOWNLOADABLE_CHANNELS & set(entry.get("channels", []))):
        raise err_validation(
            tr(f"模型 {model_id} 走自托管推理服务通道：权重在服务侧环境，请到服务机删除",
               f"Model {model_id} uses the self-hosted inference service channel: "
               f"weights live in the service environment; delete them on the service "
               f"machine"))
    is_acestep = "acestep_local" in entry.get("channels", [])
    op = ModelOp(id=new_uuid(), user_id=user_id, op_type="music_delete", target=model_id,
                 status="running", message=tr("删除中", "Deleting"))
    db.add(op)
    db.commit()
    db.refresh(op)
    try:
        (acestep_delete_local if is_acestep else delete_local)(model_id)
    except (ACEStepLocalError, MusicGenLocalError) as e:
        op.status, op.message = "failed", tr("删除失败", "Delete failed")
        op.error_message = e.message[:280]
        db.commit()
        db.refresh(op)
        return op.to_dict()
    s = _setting_row(db)
    if s.music_model == model_id and s.music_backend in ("musicgen_local", "acestep_local"):
        s.music_backend, s.music_model = "localsynth", ""  # 删掉选用模型 → 回退本地合成
        db.commit()
    op.status, op.progress, op.message = "succeeded", 100, \
        tr(f"已删除 {model_id}", f"Deleted {model_id}")
    db.commit()
    db.refresh(op)
    return op.to_dict()


def test_replicate(api_token: str, base_url: str = "", model: str = "") -> dict:
    if not (api_token or "").strip():
        raise err_validation(tr("API Token 必填", "API token is required"))
    try:
        client = ReplicateClient(api_token, base_url or "")
        acct = client.account()
        username = acct.get("username") or acct.get("type") or "ok"
        message = tr(f"Token 有效（账号 {username}）", f"Token valid (account {username})")
        sample = ""
        slug = (model or "").strip()
        if slug:
            m = client.get_model(slug)
            sample = f"{m.get('owner')}/{m.get('name')}"
            message += tr(f"；模型 {sample} 存在", f"; model {sample} exists")
        return {"ok": True, "sample": sample[:80] or str(username)[:80], "message": message}
    except ReplicateError as e:
        return {"ok": False, "sample": "", "message": e.message}
