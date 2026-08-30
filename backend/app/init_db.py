"""建库 + 幂等灌种子：python -m app.init_db [--reset]"""
from __future__ import annotations

import sys

from app import models  # noqa: F401 —— 注册全部表
from app.database import engine
from app.models import Base
from app.seed_data import run_seed

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    reset = "--reset" in sys.argv
    run_seed(reset=reset)
