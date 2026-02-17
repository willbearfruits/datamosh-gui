#!/usr/bin/env bash
# Launcher script for Datamosh GUI (PySide6)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUI_SCRIPT="$SCRIPT_DIR/main.py"

if [ ! -f "$GUI_SCRIPT" ]; then
    echo "Error: main.py not found in $SCRIPT_DIR" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found. Install Python 3.10+." >&2
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Warning: ffmpeg not found in PATH. Normalization/render may fail." >&2
fi

if ! command -v ffprobe >/dev/null 2>&1; then
    echo "Warning: ffprobe not found in PATH. Timeline frame analysis may fail." >&2
fi

if ! python3 -c "import PySide6" 2>/dev/null; then
    echo "Error: PySide6 is not installed. Run: pip install -r requirements.txt" >&2
    exit 1
fi

cd "$SCRIPT_DIR"
exec python3 "$GUI_SCRIPT" "$@"
