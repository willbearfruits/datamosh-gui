# Datamosh GUI

Interactive timeline-based datamoshing for clip-level I-frame and P-frame manipulation.

## Support

If this project helps your workflow, support ongoing development and experiments:
https://www.patreon.com/Seriousshit

## What This App Does

Datamosh GUI is a PySide6 desktop editor built for experimental compression-art workflows.

- Build a sequence from multiple clips on a timeline
- Drag clips from bin to timeline, reorder segments, and cut at playhead
- Control keyframe behavior per clip or per timeline segment
- Toggle "Drop first I-frame" on individual cuts/segments
- Duplicate P-frames to push motion-smear and prediction artifacts
- Preview timeline output before final render
- Undo/redo timeline and settings changes

The app keeps AVI bitstream manipulation in `mosh.py` and uses the GUI as an editor/orchestrator.

## Project Layout

- `main.py`: GUI entrypoint
- `gui/`: active PySide6 application
- `mosh.py`: core AVI parser/rewriter + CLI
- `tests/`: pytest suite
- `legacy/`: old Tkinter-era code (reference only, not active)

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available on `PATH`

Install Python deps:

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

Or use:

```bash
./launch.sh
```

## Workflow (GUI)

1. Open one or more source clips.
2. Wait for normalization to complete.
3. Drag clips from bin to timeline and reorder as needed.
4. Use playhead + `Cut` (`Ctrl+K`) to split timeline segments.
5. Toggle `Drop I` (`I`) for selected segment when needed.
6. Adjust per-clip/segment settings:
   - Keep extra keyframes after first
   - Duplicate count
   - Duplicate gap
   - Keep/drop specific keyframe indices
7. Preview timeline output.
8. Render final AVI.

## Keyboard Shortcuts

- `Ctrl+O`: open clips
- `Ctrl+Shift+O`: add clips
- `Ctrl+R`: render
- `Ctrl+Z`: undo
- `Ctrl+Shift+Z` / `Ctrl+Y`: redo
- `Space`: play/pause preview
- `Left` / `Right`: frame step
- `Ctrl+K`: cut selected timeline segment at playhead
- `I`: toggle drop-first I-frame for selected segment
- `Delete`: remove selected timeline segment
- `F1`: shortcut help

## CLI (Core Engine)

`mosh.py` is usable directly for scripted workflows:

```bash
python3 mosh.py input.avi output.avi --keep-first 1 --duplicate-count 2 --duplicate-gap 3
```

Normalization example:

```bash
python3 mosh.py input.mp4 output.avi --normalize --normalize-preset balanced
```

## Testing

Headless-safe full suite:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

## Notes

- Current output target is AVI/Xvid.
- Non-AVI sources are normalized before processing.
- `legacy/` exists for historical reference; active code path is `main.py` + `gui/`.
