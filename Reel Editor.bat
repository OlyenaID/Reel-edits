@echo off
rem Double-click to open the Reel Editor in your browser. Keep this window open while you edit.
title Reel Editor
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if not defined PY (
  echo First time here: setting things up. This takes a few minutes.
  call "%~dp0setup\setup-windows.bat"
  if errorlevel 1 goto failed
  set "PY=.venv\Scripts\python.exe"
)

"%PY%" reel.py app
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo Something went wrong. Copy the messages above and paste them to Claude for help.
pause
exit /b 1
