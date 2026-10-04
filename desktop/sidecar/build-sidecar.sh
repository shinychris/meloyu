#!/usr/bin/env bash
# Meloyu sidecar 打包（macOS/Linux）：backend venv + PyInstaller --onedir
# 产物：backend/dist-backend/meloyu-backend/desktop_runner（壳以 extraResources 携带）
set -euo pipefail
cd "$(dirname "$0")/../../backend"
PY=.venv/bin/python
[ -x "$PY" ] || { echo "[ERROR] backend/.venv not found"; exit 1; }
"$PY" -m pip install -q pyinstaller
"$PY" -m PyInstaller --noconfirm --clean --onedir --name desktop_runner \
  --distpath dist-backend --workpath build-desktop --specpath scripts \
  --add-data "app:app" \
  --exclude-module psycopg2 --exclude-module torch --exclude-module transformers \
  --exclude-module celery --exclude-module redis \
  scripts/desktop_runner.py
rm -rf dist-backend/meloyu-backend
mv dist-backend/desktop_runner dist-backend/meloyu-backend
echo "[OK] sidecar built: backend/dist-backend/meloyu-backend/"
