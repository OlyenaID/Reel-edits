#!/bin/bash
# Double-click to open the Reel Editor in your browser. Keep this window open while you edit.
cd "$(dirname "$0")" || exit 1
PY=""
[ -x .venv/bin/python ] && PY=.venv/bin/python
[ -z "$PY" ] && [ -x ../.venv/bin/python ] && PY=../.venv/bin/python
if [ -z "$PY" ]; then
  echo "First time here: setting things up. This takes a few minutes."
  bash setup/setup-mac.sh || { echo; echo "Something went wrong. Copy the messages above and paste them to Claude."; read -r -p "Press Enter to close."; exit 1; }
  PY=.venv/bin/python
fi
"$PY" reel.py app || { echo; echo "Something went wrong. Copy the messages above and paste them to Claude."; read -r -p "Press Enter to close."; }
