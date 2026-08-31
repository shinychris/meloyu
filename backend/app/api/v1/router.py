"""v1 路由汇总 → /api/v1。"""
from fastapi import APIRouter

from app.api.v1 import (
    auth,
    candidates,
    credits,
    exports,
    files,
    generations,
    lyrics,
    models,
    subscriptions,
    system,
    tasks,
    versions,
    works,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(generations.router)
api_router.include_router(tasks.router)
api_router.include_router(candidates.router)
api_router.include_router(lyrics.router)
api_router.include_router(models.router)
api_router.include_router(works.router)
api_router.include_router(versions.router)
api_router.include_router(exports.router)
api_router.include_router(files.router)
api_router.include_router(credits.router)
api_router.include_router(subscriptions.router)
api_router.include_router(system.router)
