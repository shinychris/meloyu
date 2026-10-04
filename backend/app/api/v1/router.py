"""v1 路由汇总 → /api/v1。"""
from fastapi import APIRouter

from app.api.v1 import (
    auth,
    candidates,
    credits,
    exports,
    files,
    generations,
    hum,
    licenses,
    lyrics,
    market,
    models,
    public,
    reference,
    subscriptions,
    system,
    tasks,
    taste,
    team,
    versions,
    voice,
    works,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(licenses.router)
api_router.include_router(generations.router)
api_router.include_router(tasks.router)
api_router.include_router(candidates.router)
api_router.include_router(lyrics.router)
api_router.include_router(models.router)
api_router.include_router(reference.router)
api_router.include_router(team.router)
api_router.include_router(taste.router)
api_router.include_router(market.router)
api_router.include_router(works.router)
api_router.include_router(versions.router)
api_router.include_router(exports.router)
api_router.include_router(files.router)
api_router.include_router(credits.router)
api_router.include_router(subscriptions.router)
api_router.include_router(voice.router)
api_router.include_router(hum.router)
api_router.include_router(public.router)
api_router.include_router(public.keys_router)
api_router.include_router(system.router)
