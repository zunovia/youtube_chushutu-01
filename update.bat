@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM YouTube Chushutu - Updater for Windows
REM Double-click to bring this folder to the latest version.
REM Every line here is self-contained on purpose: this file is
REM also downloaded on its own, so it must work with LF or CRLF.
REM ============================================================
set "REMOTE=https://raw.githubusercontent.com/zunovia/youtube_chushutu-01/main/scripts/update.ps1"
set "PS1=%TEMP%\ytc-update.ps1"
echo Fetching the latest updater...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%REMOTE%' -OutFile '%PS1%'; exit 0 } catch { exit 1 }"
if errorlevel 1 echo Could not download the updater, using the local copy.
if errorlevel 1 set "PS1=%~dp0scripts\update.ps1"
if not exist "%PS1%" (echo [ERROR] No updater found. Check the internet connection and try again. & pause & exit /b 1)
REM "exit /b" on the same line: the updater may replace this file, and CMD
REM would otherwise keep reading the new file from the old byte offset.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -ProjectDir "%~dp0." || pause & exit /b
