@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM yt-dlp 更新スクリプト (Windows)
REM YouTubeの仕様変更時にダブルクリックで実行するだけでOK
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "VENV_PIP=%SCRIPT_DIR%..\backend\.venv\Scripts\pip.exe"
set "VENV_PYTHON=%SCRIPT_DIR%..\backend\.venv\Scripts\python.exe"

if not exist "%VENV_PIP%" (
    echo [ERROR] 仮想環境が見つかりません。先にインストーラーを実行してください。
    pause
    exit /b 1
)

echo.
echo === yt-dlp 更新 ===
echo.

echo 現在のバージョン:
"%VENV_PYTHON%" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo.
echo 最新版にアップデート中...
"%VENV_PIP%" install --upgrade yt-dlp -q

echo.
echo 更新後のバージョン:
"%VENV_PYTHON%" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo.
echo 完了! バックエンドサーバーを再起動してください。
echo.
pause
