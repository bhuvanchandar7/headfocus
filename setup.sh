#!/bin/zsh
# One-time setup: Python environment, face model, and HeadFocus.app.
# Safe to run again (e.g. after moving this folder).
set -e
DIR="${0:A:h}"
cd "$DIR"
APP="$HOME/Applications/HeadFocus.app"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

[[ "$(uname)" == Darwin ]] || { echo "HeadFocus only runs on macOS."; exit 1; }

echo "==> Python environment"
if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null; then
    uv venv -q -p 3.12 .venv
  else
    PY=""
    for c in python3.12 python3.11 python3.10 python3; do
      if command -v $c >/dev/null && $c -c 'import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,12))'; then
        PY=$c; break
      fi
    done
    [[ -n "$PY" ]] || { echo "Need Python 3.10-3.12 (MediaPipe requirement). Install with: brew install python@3.12"; exit 1; }
    $PY -m venv .venv
  fi
fi
if command -v uv >/dev/null; then
  uv pip install -q --python .venv/bin/python -r requirements.txt
else
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
fi

echo "==> Face model"
mkdir -p models
[[ -s models/face_landmarker.task ]] || curl -fsSL -o models/face_landmarker.task "$MODEL_URL"

echo "==> HeadFocus.app"
command -v clang >/dev/null || { echo "Need Xcode Command Line Tools. Install with: xcode-select --install"; exit 1; }
mkdir -p "$APP/Contents/MacOS" .build
clang -O2 -DHEADFOCUS_DIR="\"$DIR\"" -o .build/HeadFocus.new launcher/main.c
# Only replace the app when the launcher changed: re-signing resets macOS permissions.
# (Compare unsigned builds, since signing modifies the installed binary.)
if [[ -x "$APP/Contents/MacOS/HeadFocus" ]] && cmp -s .build/HeadFocus.new .build/HeadFocus.last \
   && cmp -s launcher/Info.plist "$APP/Contents/Info.plist"; then
  echo "   up to date"
else
  cp .build/HeadFocus.new "$APP/Contents/MacOS/HeadFocus"
  cp launcher/Info.plist "$APP/Contents/Info.plist"
  codesign --force -s - "$APP" >/dev/null 2>&1
  cp .build/HeadFocus.new .build/HeadFocus.last
  echo "   built $APP"
fi
rm -f .build/HeadFocus.new

chmod +x headfocus Calibrate.command
echo
echo "Done. Next:"
echo "  1. ./headfocus calibrate     (or double-click Calibrate.command)"
echo "  2. ./headfocus run --preview (try it; Ctrl+C to stop)"
echo "  3. ./headfocus install       (run in the background at every login)"
