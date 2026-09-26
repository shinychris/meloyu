"""应用内定时备份（v0.14.0 收尾补充，2026-09-26）。

背景：deploy 的备份包装脚本依赖 `docker exec`，但 GPU 容器
（nvidia-container-runtime + cap_drop ALL）在 Docker Desktop/Win11 下
exec 报 seccomp errno 524 不可用——备份必须有不依赖 exec 的通道。

方案：容器内应用自身起守护线程，每天 03:30（容器本地时区，TZ=Asia/
Shanghai）调用 scripts/backup.py 的既有实现（在线页级快照 + integrity
check + 音频增量镜像 + 轮换）。进程内多连接是 SQLite 正常用法（同一 OS
视图，非单写入方红线范畴）。上次执行日期落 data/ 目录标记文件，重启
不重跑当天已跑的备份。
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.core.logging import logger

_MARKER = "backup_last_run.txt"
_RUN_AT_HOUR, _RUN_AT_MINUTE = 3, 30
_CHECK_INTERVAL_SEC = 10 * 60


def _marker_path() -> Path:
    return settings.data_path / _MARKER


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _due_now() -> bool:
    now = datetime.now()
    if (now.hour, now.minute) < (_RUN_AT_HOUR, _RUN_AT_MINUTE):
        return False
    try:
        return _marker_path().read_text(encoding="utf-8").strip() != _today()
    except OSError:
        return True


def _mark_done() -> None:
    try:
        _marker_path().parent.mkdir(parents=True, exist_ok=True)
        _marker_path().write_text(_today(), encoding="utf-8")
    except OSError as e:  # noqa: BLE001 —— 标记失败下次会重试（备份本身幂等）
        logger.warning(f"backup marker write failed: {e}")


def run_backup_now() -> bool:
    """执行一次备份（复用 scripts/backup.py；返回是否成功）。"""
    import sys

    backend_dir = settings.data_path.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        from scripts.backup import main as backup_main
    except ImportError:
        logger.error("in-app backup: scripts.backup 不可导入，跳过")
        return False
    try:
        ok = backup_main(["--keep", "7"]) == 0
    except Exception as e:  # noqa: BLE001 —— 备份线程兜底
        logger.exception(f"in-app backup failed: {e}")
        return False
    if ok:
        _mark_done()
        logger.info("in-app daily backup done (snapshot + integrity + audio mirror)")
    return ok


def start_periodic_backup() -> None:
    def _loop() -> None:
        while True:
            try:
                if _due_now():
                    run_backup_now()
            except Exception as e:  # noqa: BLE001 —— 线程兜底
                logger.exception(f"periodic backup loop error: {e}")
            time.sleep(_CHECK_INTERVAL_SEC)

    threading.Thread(target=_loop, daemon=True, name="meloyu-backup").start()
    logger.info(f"periodic in-app backup armed (daily {_RUN_AT_HOUR:02d}:{_RUN_AT_MINUTE:02d})")
