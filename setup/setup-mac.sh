#!/bin/bash
# One-time setup for Mac: Homebrew, ffmpeg, Python, and the engine's Python packages (in .venv).
set -e
cd "$(dirname "$0")/.."
if ! command -v brew >/dev/null 2>&1; then
  echo "Installing Homebrew (it will ask for your Mac password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi
command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
command -v python3 >/dev/null 2>&1 || brew install python
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install faster-whisper pillow
.venv/bin/python reel.py check
