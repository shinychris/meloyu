@echo off
rem Meloyu sidecar 打包（Windows）：backend venv + PyInstaller --onedir
rem 产物：backend\dist-backend\meloyu-backend\desktop_runner.exe（壳以 extraResources 携带）
setlocal
cd /d "%~dp0..\..\backend"
if not exist .venv\Scripts\python.exe (
  echo [ERROR] backend\.venv not found. Create it first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt pyinstaller
  exit /b 1
)
.venv\Scripts\pip install -q pyinstaller || exit /b 1
rem --specpath scripts 使相对路径以 scripts\ 为基准：app 包与导入根需回到上级
rem acestep_runner.py 随包携带：providers/music_acestep.py 经子进程以 ACE-Step
rem 独立 venv 解释器执行该脚本（BACKEND_DIR\scripts\，v0.16.3 前漏带——打包
rem 形态下 ACE-Step 通道即使部署了组件也无法推理）
.venv\Scripts\pyinstaller --noconfirm --clean --onedir --name desktop_runner ^
  --distpath dist-backend --workpath build-desktop --specpath scripts ^
  --paths .. --add-data "..\app;app" --add-data "..\scripts\acestep_runner.py;scripts" ^
  --exclude-module psycopg2 --exclude-module torch --exclude-module transformers ^
  --exclude-module celery --exclude-module redis ^
  scripts\desktop_runner.py || exit /b 1
rem PyInstaller 目录名取 --name：规范为 meloyu-backend（与 electron-builder.yml 对齐）
if exist dist-backend\meloyu-backend rmdir /s /q dist-backend\meloyu-backend
ren dist-backend\desktop_runner meloyu-backend
echo [OK] sidecar built: backend\dist-backend\meloyu-backend\
endlocal
