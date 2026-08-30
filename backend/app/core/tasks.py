"""任务执行基础设施：线程池（max_workers=2）+ 启动僵尸回收。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.core.logging import logger
from app.database import SessionLocal
from app.models import Task
from app.models.base import utc_now_iso

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="meloyu-task")
    return _executor


def schedule_generation(task_id: str) -> None:
    from app.services.generation import execute_generation
    get_executor().submit(_safe_run, execute_generation, task_id)


def schedule_export(task_id: str) -> None:
    from app.services.export import execute_export
    get_executor().submit(_safe_run, execute_export, task_id)


def _safe_run(fn, task_id: str) -> None:
    try:
        fn(task_id)
    except Exception as e:  # noqa: BLE001 —— 线程池兜底
        logger.exception(f"task {task_id} crashed in executor: {e}")


def recover_zombie_tasks() -> int:
    """启动自愈：进程重启后，把 running/queued 僵尸任务置 failed(50003) 并退款。"""
    recovered = 0
    with SessionLocal() as db:
        rows = db.execute(select(Task).where(Task.status.in_(("queued", "running")))).scalars().all()
        if not rows:
            return 0
        now = utc_now_iso()
        for t in rows:
            t.status = "failed"
            t.error_code = 50003
            t.error_message = "任务被系统中断（服务重启），积分已退还"
            t.finished_at = now
            t.updated_at = now
            recovered += 1
        db.commit()
        for t in rows:
            if t.cost_credits > 0:
                from app.services.credits import refund
                refund(db, t.user_id, t.cost_credits, t.id)
                db.commit()
    if recovered:
        logger.info(f"recovered {recovered} zombie tasks (refunded)")
    return recovered
