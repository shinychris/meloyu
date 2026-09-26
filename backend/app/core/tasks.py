"""任务执行基础设施：优先级工作线程 + 导出独立池 + 启动僵尸回收。

v0.14.0（2026-09-26 商业化审查 P0-4/P1-10）重构：
- 原单一 ThreadPoolExecutor(max_workers=2) 无优先级——studio 档「优先队列」
  承诺无从谈起。改为**双优先级堆队列**：plan 权重（studio/team=0、pro=1、
  free=2）为主序，提交先后为次序，2 个常驻 worker 线程消费。
- 生成与导出原共用 2 worker，两个慢导出即占满全站生成通道——导出改走
  **独立单 worker 池**（meloyu-export），与生成互不挤占；卡死导出最坏只
  影响后续导出排队。
- 队列取消：queued 任务被置 canceled 后，worker 取到时 execute_* 开头的
  状态检查直接跳过（与原 ThreadPoolExecutor 行为一致）。
"""
from __future__ import annotations

import heapq
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.core.i18n import current_locale, run_with_locale, tr
from app.core.logging import logger
from app.database import SessionLocal
from app.models import Task
from app.models.base import utc_now_iso

_heap: list[tuple[int, int, object, tuple]] = []
_wakeup = threading.Condition()
_seq = itertools.count()  # 同优先级内 FIFO 稳定序
_PLAN_PRIORITY = {"studio": 0, "team": 0, "pro": 1, "free": 2}
_WORKER_COUNT = 2
_workers_started = False
_export_executor: ThreadPoolExecutor | None = None


def _ensure_workers() -> None:
    global _workers_started
    if _workers_started:
        return
    for i in range(_WORKER_COUNT):
        threading.Thread(target=_worker_loop, daemon=True,
                         name=f"meloyu-task-{i}").start()
    _workers_started = True


def _worker_loop() -> None:
    while True:
        with _wakeup:
            while not _heap:
                _wakeup.wait()
            _priority, _seqno, fn, args = heapq.heappop(_heap)
        try:
            fn(*args)
        except Exception as e:  # noqa: BLE001 —— worker 线程兜底
            logger.exception(f"task crashed in worker: {e}")


def schedule_generation(task_id: str, plan: str = "free") -> None:
    from app.services.generation import execute_generation
    _ensure_workers()
    # 不复制 contextvar：捕获提交时 locale，worker 内恢复，保证任务进度/错误
    # 文案按提交请求语言生成（持久化语义，可接受）
    locale = current_locale()
    with _wakeup:
        heapq.heappush(_heap, (_PLAN_PRIORITY.get(plan, 2), next(_seq),
                               run_with_locale, (locale, _safe_run,
                                                 execute_generation, task_id)))
        _wakeup.notify()


def schedule_export(task_id: str) -> None:
    """导出走独立单 worker 池：慢/卡导出不再挤占生成通道（P1-10）。"""
    global _export_executor
    from app.services.export import execute_export
    if _export_executor is None:
        _export_executor = ThreadPoolExecutor(max_workers=1,
                                              thread_name_prefix="meloyu-export")
    locale = current_locale()
    _export_executor.submit(run_with_locale, locale, _safe_run, execute_export, task_id)


def queued_depth() -> int:
    """当前生成队列深度（监控/health 暴露用）。"""
    with _wakeup:
        return len(_heap)


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
            t.error_message = tr("任务被系统中断（服务重启），积分已退还",
                                 "Task interrupted by a system restart; credits refunded")
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
