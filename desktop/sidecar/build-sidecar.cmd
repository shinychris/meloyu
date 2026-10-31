@echo off
rem Meloyu sidecar build (Windows): backend venv + PyInstaller --onedir
rem Output: backend\dist-backend\meloyu-backend\desktop_runner.exe (carried as
rem extraResources by the Electron shell)
rem NOTE: keep this file ASCII-only -- cmd.exe parses batch files with the ANSI
rem code page (GBK on zh-CN systems), so UTF-8 Chinese comments break parsing.
setlocal
cd /d "%~dp0..\..\backend"
if not exist .venv\Scripts\python.exe (
  echo [ERROR] backend\.venv not found. Create it first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt pyinstaller
  exit /b 1
)
.venv\Scripts\pip install -q pyinstaller || exit /b 1
rem --specpath scripts: --add-data resolves against scripts\ (so ..pp points back
rem to the backend root), while --paths resolves against the CWD (backend\)
rem acestep_runner.py is carried in-package: providers/music_acestep.py runs it
rem via subprocess with the standalone ACE-Step venv interpreter
rem (BACKEND_DIR\scripts\; before v0.16.3 it was missing -- the ACE-Step channel
rem could not run in packaged form even with components deployed)
.venv\Scripts\pyinstaller --noconfirm --clean --onedir --name desktop_runner ^
  --distpath dist-backend --workpath build-desktop --specpath scripts ^
  --paths "%CD%" --add-data "..\app;app" --add-data "..\scripts\acestep_runner.py;scripts" ^
  --exclude-module psycopg2 --exclude-module torch --exclude-module transformers ^
  --exclude-module celery --exclude-module redis ^
  scripts\desktop_runner.py || exit /b 1
rem PyInstaller dir name follows --name: canonical name is meloyu-backend
rem (aligned with electron-builder.yml)
if exist dist-backend\meloyu-backend rmdir /s /q dist-backend\meloyu-backend
ren dist-backend\desktop_runner meloyu-backend
echo [OK] sidecar built: backend\dist-backend\meloyu-backend\
endlocal
