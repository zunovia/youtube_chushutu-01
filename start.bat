@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM YouTube Chushutu - Backend Launcher for Windows
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Not installed yet. Run scripts\install.bat first.
    echo   %SCRIPT_DIR%scripts\install.bat
    pause
    exit /b 1
)

echo.
echo =========================================
echo   YouTube Chushutu Backend
echo =========================================
echo.

"%VENV_PYTHON%" -c "import yt_dlp, shutil; ffmpeg='OK' if shutil.which('ffmpeg') else 'NOT FOUND'; print(f'  yt-dlp:  {yt_dlp.version.__version__}'); print(f'  ffmpeg:  {ffmpeg}'); print(f'  URL:     http://localhost:9160'); print(f'  API Doc: http://localhost:9160/docs')"

echo.
echo Close this window or press Ctrl+C to stop.
echo =========================================
echo.

"%VENV_PYTHON%" "%BACKEND_DIR%\run.py"
pause
