@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM YouTube Chushutu - バックエンド起動スクリプト (Windows)
REM ダブルクリックで起動OK
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

REM 仮想環境チェック
if not exist "%VENV_PYTHON%" (
    echo [ERROR] 仮想環境が見つかりません。先にインストーラーを実行してください:
    echo   %SCRIPT_DIR%scripts\install.bat
    pause
    exit /b 1
)

echo.
echo =========================================
echo   YouTube Chushutu バックエンド
echo =========================================
echo.

"%VENV_PYTHON%" -c "import yt_dlp, shutil; ffmpeg='OK' if shutil.which('ffmpeg') else 'NOT FOUND'; print(f'  yt-dlp:  {yt_dlp.version.__version__}'); print(f'  ffmpeg:  {ffmpeg}'); print(f'  URL:     http://localhost:9160'); print(f'  API Doc: http://localhost:9160/docs')"

echo.
echo 停止するにはこのウィンドウを閉じるか Ctrl+C を押してください
echo =========================================
echo.

"%VENV_PYTHON%" "%BACKEND_DIR%\run.py"
pause
