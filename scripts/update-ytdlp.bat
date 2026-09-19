@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM yt-dlp Updater for Windows
REM ============================================================

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "PROJECT_DIR=%CD%"
popd
set "VENV_PIP=%PROJECT_DIR%\backend\.venv\Scripts\pip.exe"
set "VENV_PYTHON=%PROJECT_DIR%\backend\.venv\Scripts\python.exe"

if not exist "%VENV_PIP%" (
    echo [ERROR] Not installed yet. Run scripts\install.bat first.
    pause
    exit /b 1
)

echo.
echo === yt-dlp Update ===
echo.

echo Current version:
"%VENV_PYTHON%" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo.
echo Updating to latest...
REM [default] carries yt-dlp-ejs, the solver script that must match yt-dlp.
"%VENV_PIP%" install --upgrade "yt-dlp[default]" -q
REM The JS runtime that runs it. Best effort: 64-bit only.
"%VENV_PIP%" install --upgrade deno -q

echo.
echo Updated version:
"%VENV_PYTHON%" -c "import yt_dlp; print(f'  {yt_dlp.version.__version__}')"

echo.
echo Done! Please restart the backend server.
echo (For a full update including the extension, run update.bat instead.)
echo.
pause
