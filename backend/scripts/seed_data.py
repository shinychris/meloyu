"""种子脚本 CLI 入口（薄包装）：python scripts/seed_data.py [--reset]

唯一事实源为 app/init_db.py（2026-10-27 归并：本文件原先各自复刻
create_all + run_seed 且缺幂等迁移步骤），此处仅透传参数并注明出处。
--reset：停止后端后执行；清空数据库与 data/audio/ 后重建灌库。
目标库由 DATABASE_URL / .env 决定。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.init_db import main  # noqa: E402

if __name__ == "__main__":
    main()
