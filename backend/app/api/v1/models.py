"""模型中心路由（15 接口）。

本地开源模型（Ollama）下载/删除/列举/选用 + 外部 API（OpenAI 兼容）配置与连通性
测试 + 歌词引擎通道切换（V1.2）；外部歌曲生成 API（Suno 兼容）配置/探活/通道切换
（V1.3）；开源歌曲模型目录/Replicate 托管/本机 MusicGen 下载/删除/探活（V1.4）。

v0.7.0：全局配置写操作收权管理员（users.is_admin：settings.admin_emails
注册自动授予 + demo 种子账号）；读/探活/目录仍登录即可用。API key 落库经
core/crypto.py Fernet 加密（KEY_ENCRYPTION_SECRET 配置后生效）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_forbidden
from app.core.i18n import tr
from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.models import (
    CatalogModelRequest,
    ExternalTestRequest,
    LLMSettingsRequest,
    ModelDeleteRequest,
    ModelPullRequest,
    MusicTestRequest,
    ReplicateTestRequest,
)
from app.services import model_center as svc

router = APIRouter(prefix="/models", tags=["models"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    """模型中心写操作需管理员（全局配置影响所有用户的通道与费用）。

    B7（2026-10-16 补全）：desktop 形态配置即当前用户自己的配置——
    get_current_user 已短路为本地档案，不再叠加 admin 判定；
    cloud/enterprise 维持 admin 闸（全局配置影响所有用户）。
    """
    if settings.app_mode == "desktop":
        return user
    if not user.is_admin:
        raise err_forbidden(tr(
            "模型中心写操作需管理员权限（平台级全局配置）",
            "Model center write operations require administrator rights "
            "(platform-level global configuration)"))
    return user


def require_admin_probe(user: User = Depends(get_current_user)) -> User:
    """连通性测试端点同样需管理员（2026-09-09）。

    test-external/test-music 接受调用方任意 base_url 并由服务端发起请求——
    若登录即可用，构成内网探测/云元数据读取原语（SSRF）；与 PUT /settings
    同级收权 admin（管理员本就可信配置任意通道地址，含本机推理端点）。
    desktop 形态放开为当前用户（B7，2026-10-16：单机实例探测目标是
    用户自己配置的本机/自托管端点，信任边界即本地档案）。
    """
    if settings.app_mode == "desktop":
        return user
    if not user.is_admin:
        raise err_forbidden(tr(
            "模型中心连通性测试需管理员权限（测试将用您填写的地址发起服务端请求）",
            "Model center connectivity tests require administrator rights "
            "(tests make server-side requests to the URL you provide)"))
    return user


@router.get("/runtime")
def runtime(db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """运行时状态：Ollama 安装/版本/模型数 + 当前生效引擎。"""
    return ok(svc.runtime_status(db))


@router.get("/local")
def local_models(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """本地已装模型列表 + 正在进行的下载 + 推荐 pull 清单。"""
    return ok(svc.list_local_models(db))


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """引擎通道配置（歌词 + 歌曲；api_key 脱敏）。"""
    return ok(svc.get_settings(db))


@router.put("/settings")
def put_settings(body: LLMSettingsRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    """切换引擎通道 / 更新连接配置（歌词 lyrics_backend + 歌曲 music_backend）。"""
    return ok(svc.update_settings(db, body.model_dump(exclude_unset=True)))


@router.post("/pull")
def pull(body: ModelPullRequest, db: Session = Depends(get_db),
         user: User = Depends(require_admin)):
    """发起模型下载（异步，轮询 GET /models/ops/{id} 看进度）。"""
    return ok(svc.start_pull(db, user.id, body.model), status_code=202)


@router.post("/delete")
def delete(body: ModelDeleteRequest, db: Session = Depends(get_db),
           user: User = Depends(require_admin)):
    """删除本地模型（同步返回结果）。"""
    return ok(svc.run_delete(db, user.id, body.model))


@router.get("/ops")
def ops(db: Session = Depends(get_db), limit: int = Query(default=10, ge=1, le=50),
        user: User = Depends(get_current_user)):
    """最近的模型操作记录。"""
    return ok(svc.list_ops(db, limit))


@router.get("/ops/{op_id}")
def op(op_id: str, db: Session = Depends(get_db),
       user: User = Depends(get_current_user)):
    """模型操作进度轮询（1~2s 间隔）。"""
    return ok(svc.get_op(db, op_id))


@router.post("/test-external")
def test_external(body: ExternalTestRequest,
                  user: User = Depends(require_admin_probe)):
    """外部 API 连通性测试（发 2 token 最小对话，不落库）。"""
    return ok(svc.test_external(body.base_url, body.api_key, body.model))


@router.post("/test-music")
def test_music(body: MusicTestRequest,
               user: User = Depends(require_admin_probe)):
    """外部歌曲生成 API（Suno 兼容）端点探活（get 探针 id，不落库）。"""
    return ok(svc.test_music(body.base_url, body.api_key, body.model))


@router.post("/test-replicate")
def test_replicate(body: ReplicateTestRequest,
                   user: User = Depends(require_admin_probe)):
    """Replicate Token 校验（GET /v1/account）+ 可选模型存在性（不落库）。"""
    return ok(svc.test_replicate(body.api_token, body.base_url, body.model))


@router.get("/music-catalog")
def music_catalog(db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """开源歌曲模型目录：按外部测评参考分降序 + 能力矩阵 + 本机状态 + 推荐。"""
    return ok(svc.get_music_catalog(db))


@router.post("/music-pull")
def music_pull(body: CatalogModelRequest, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    """下载本机开源歌曲模型（MusicGen，HF 真实下载，异步轮询 ops/{id} 看进度）。"""
    return ok(svc.start_music_pull(db, user.id, body.model), status_code=202)


@router.post("/acestep-deploy")
def acestep_deploy(db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    """部署 ACE-Step 组件（v0.16.3：源码+uv 引导+独立 venv 约 4GB，异步轮询
    ops/{id} 看进度；desktop 首启自动走同一链路，此端点供组件中心手动触发/重试）。"""
    return ok(svc.start_acestep_deploy(db, user.id), status_code=202)


@router.post("/music-delete")
def music_delete(body: CatalogModelRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    """删除本机开源歌曲模型（同步返回结果；删选用中模型自动回退本地合成）。"""
    return ok(svc.run_music_delete(db, user.id, body.model))


@router.get("/presets")
def presets(user: User = Depends(get_current_user)):
    """外部 API 厂商预设 + 推荐 pull 清单（文案按请求 locale 输出）。"""
    return ok({"external_presets": svc.external_presets(),
               "music_api_presets": svc.music_api_presets(),
               "recommended_models": svc.recommended_models()})
