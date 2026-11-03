@echo off
rem One-time setup for Windows: ffmpeg, Python, and the engine's Python packages (in .venv).
cd /d "%~dp0.."
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo Installing ffmpeg...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
)

set "BASEPY="
where py >nul 2>nul && set "BASEPY=py -3"
if not defined BASEPY (
  where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "BASEPY=python"
)
if not defined BASEPY (
  echo Installing Python...
  winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
  set "BASEPY=py -3"
)

echo Creating the engine's Python folder...
%BASEPY% -m venv .venv
if errorlevel 1 (
  echo Could not create .venv. Close this window, open the Reel Editor again, and it will retry.
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install faster-whisper pillow
if errorlevel 1 (
  echo Could not download the Python packages. Check your internet connection, VPN or ad blocker.
  exit /b 1
)
".venv\Scripts\python.exe" reel.py check
exit /b 0
