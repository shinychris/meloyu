#!/usr/bin/env bash
# Meloyu sidecar 打包（macOS/Linux）：backend venv + PyInstaller --onedir
# 产物：backend/dist-backend/meloyu-backend/desktop_runner（壳以 extraResources 携带）
set -euo pipefail
cd "$(dirname "$0")/../../backend"
PY=.venv/bin/python
[ -x "$PY" ] || { echo "[ERROR] backend/.venv not found"; exit 1; }
"$PY" -m pip install -q pyinstaller
# --specpath scripts 使相对路径以 scripts/ 为基准：app 包与导入根需回到上级
# acestep_runner.py 随包携带：providers/music_acestep.py 经子进程以 ACE-Step
# 独立 venv 解释器执行该脚本（BACKEND_DIR/scripts/，v0.16.3 前漏带——打包
# 形态下 ACE-Step 通道即使部署了组件也无法推理）
"$PY" -m PyInstaller --noconfirm --clean --onedir --name desktop_runner \
  --distpath dist-backend --workpath build-desktop --specpath scripts \
  --paths .. --add-data "../app:app" --add-data "../scripts/acestep_runner.py:scripts" \
  --exclude-module psycopg2 --exclude-module torch --exclude-module transformers \
  --exclude-module celery --exclude-module redis \
  scripts/desktop_runner.py
rm -rf dist-backend/meloyu-backend
mv dist-backend/desktop_runner dist-backend/meloyu-backend
echo "[OK] sidecar built: backend/dist-backend/meloyu-backend/"
