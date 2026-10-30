"""磁盘水位防护（2026-09-26 商业化审查 P0-9）。

数据盘写满的失效模式比想象的隐蔽：SQLite 写事务全数报错（database or disk
is full）、上传写半截损坏、任务成批失败退款，而容器 health 依旧 "healthy"
地拒绝一切写。写入密集入口（生成/派生/导出/上传）前置检查，低于阈值直接
业务错误拒绝；/system/health 回报真实水位供探针告警。
"""
from __future__ import annotations

import shutil

from app.config import settings
from app.core.errors import err_conflict
from app.core.i18n import tr
from app.core.logging import logger


def disk_free_gb() -> float:
    """数据盘剩余空间（GB）。data_path 必存（库文件所在），audio_path 首次可能未建。

    2026-10-27：data 目录可能尚不存在（如数据盘新挂载/首次启动竞态），此时
    shutil.disk_usage 抛 FileNotFoundError 使生成提交 500——入口先建目录
    （幂等），保证水位检查总有可探测目标。
    """
    settings.data_path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(settings.data_path).free / (1 << 30)


def ensure_disk_available(extra_bytes: int | None = None) -> None:
    """写入入口前置水位检查；不足时抛 40901（携带当前水位与阈值）。

    extra_bytes：本次写入的预估增量（如 mixdown 上传 200MB），按需抬高本次阈值。
    """
    threshold = settings.disk_min_free_gb + ((extra_bytes or 0) / (1 << 30))
    free = disk_free_gb()
    if free < threshold:
        logger.warning(f"disk watermark tripped: free={free:.1f}GB "
                       f"threshold={threshold:.1f}GB")
        raise err_conflict(
            tr(f"服务器存储空间不足（剩余 {free:.0f}GB），请稍后再试或联系运维",
               f"Server storage is running low ({free:.0f}GB free); "
               "please try again later or contact the operator"))
