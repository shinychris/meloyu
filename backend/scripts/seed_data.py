"""种子脚本 CLI 入口：python scripts/seed_data.py [--reset]

--reset：停止后端后执行；删除 data/meloyu.db 与 data/audio/ 整目录后重建灌库。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.models  # noqa: E402,F401
from app.database import engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed_data import run_seed  # noqa: E402

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    run_seed(reset="--reset" in sys.argv)
