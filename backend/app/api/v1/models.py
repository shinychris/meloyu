"""模型中心路由（契约 v1.4 §5.8，11 接口，登录即可用）。

本地开源模型（Ollama）下载/删除/列举/选用 + 外部 API（OpenAI 兼容）配置与连通性
测试 + 歌词引擎通道切换（V1.2）；外部歌曲生成 API（Suno 兼容）配置/探活/通道切换
（V1.3）。MVP 单机自用场景未做管理员角色收权（RAID 登记 P2）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.models import (
    ExternalTestRequest,
    LLMSettingsRequest,
    ModelDeleteRequest,
    ModelPullRequest,
    MusicTestRequest,
)
from app.services import model_center as svc

router = APIRouter(prefix="/models", tags=["models"])


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
                 user: User = Depends(get_current_user)):
    """切换引擎通道 / 更新连接配置（歌词 lyrics_backend + 歌曲 music_backend）。"""
    return ok(svc.update_settings(db, body.model_dump(exclude_unset=True)))


@router.post("/pull")
def pull(body: ModelPullRequest, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """发起模型下载（异步，轮询 GET /models/ops/{id} 看进度）。"""
    return ok(svc.start_pull(db, user.id, body.model), status_code=202)


@router.post("/delete")
def delete(body: ModelDeleteRequest, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
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
                  user: User = Depends(get_current_user)):
    """外部 API 连通性测试（发 2 token 最小对话，不落库）。"""
    return ok(svc.test_external(body.base_url, body.api_key, body.model))


@router.post("/test-music")
def test_music(body: MusicTestRequest,
               user: User = Depends(get_current_user)):
    """外部歌曲生成 API（Suno 兼容）端点探活（get 探针 id，不落库）。"""
    return ok(svc.test_music(body.base_url, body.api_key, body.model))


@router.get("/presets")
def presets(user: User = Depends(get_current_user)):
    """外部 API 厂商预设 + 推荐 pull 清单。"""
    return ok({"external_presets": svc.EXTERNAL_PRESETS,
               "music_api_presets": svc.MUSIC_API_PRESETS,
               "recommended_models": svc.RECOMMENDED_MODELS})
