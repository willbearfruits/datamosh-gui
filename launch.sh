#!/usr/bin/env bash
# Launcher script for Datamosh GUI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUI_SCRIPT="$SCRIPT_DIR/mosh_gui.py"

# Check if GUI script exists
if [ ! -f "$GUI_SCRIPT" ]; then
    echo "Error: mosh_gui.py not found in $SCRIPT_DIR" >&2
    exit 1
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.10 or higher." >&2
    exit 1
fi

# Check if ffmpeg is available
if ! command -v ffmpeg &> /dev/null; then
    echo "Warning: ffmpeg not found in PATH. Video processing may fail." >&2
    echo "Install ffmpeg: sudo apt install ffmpeg" >&2
fi

# Check for Pillow
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "Warning: Pillow not installed. Preview will use external ffplay." >&2
    echo "Install Pillow: pip3 install Pillow" >&2
fi

# Launch the GUI
cd "$SCRIPT_DIR"
python3 "$GUI_SCRIPT" "$@"
