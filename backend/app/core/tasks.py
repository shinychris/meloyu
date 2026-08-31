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
    """启动自愈：① running/queued 僵尸任务置 failed(50003) 并退款（终态、退款与
    空版本电流向回滚同事务）；② 兜底扫描历史「已终态、已扣积分、无退款流水」的
    任务补退款（幂等，覆盖旧版本崩溃窗口遗留）。"""
    from app.models import CreditTransaction
    from app.services.credits import refund
    from app.services.generation import rollback_empty_current_version

    recovered = 0
    with SessionLocal() as db:
        rows = db.execute(select(Task).where(Task.status.in_(("queued", "running")))).scalars().all()
        now = utc_now_iso()
        for t in rows:
            t.status = "failed"
            t.error_code = 50003
            t.error_message = "任务被系统中断（服务重启），积分已退还"
            t.finished_at = now
            t.updated_at = now
            recovered += 1
            if t.cost_credits > 0:
                refund(db, t.user_id, t.cost_credits, t.id)
            rollback_empty_current_version(db, t.id)
        db.commit()

        compensated = 0
        terminal = db.execute(select(Task).where(Task.status.in_(("failed", "canceled")),
                                                 Task.cost_credits > 0)).scalars().all()
        for t in terminal:
            exists = db.execute(
                select(CreditTransaction.id).where(CreditTransaction.ref_task_id == t.id,
                                                   CreditTransaction.reason == "refund")
            ).fetchone()
            if not exists:
                refund(db, t.user_id, t.cost_credits, t.id)
                db.commit()
                compensated += 1
        if compensated:
            logger.warning(f"compensated {compensated} terminal tasks missing refund")
    if recovered:
        logger.info(f"recovered {recovered} zombie tasks (refunded)")
    return recovered
