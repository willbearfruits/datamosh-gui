# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the GUI application (PySide6)
python3 main.py

# Run the CLI engine directly
python3 mosh.py input.avi output.avi --keep-first 1

# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_clip_model.py

# Run a specific test
pytest tests/test_clip_model.py::TestClipListModel::test_add_clip

# Run with coverage
pytest --cov=. --cov-report=term-missing
```

Tests are in `tests/` and use markers `integration` (requires real video files), `gui` (requires display), and `slow`. The `mock_ffmpeg` fixture in `conftest.py` patches subprocess calls for unit tests. GUI tests use `pytest-qt`.

## Architecture

The application has two layers: a pure binary AVI manipulation engine (`mosh.py`, untouched) and a PySide6 GUI (`gui/`, `main.py`).

### Core engine (`mosh.py`)
Operates directly on the RIFF/AVI binary format — no video decoding. Pipeline:
1. `parse_avi_file()` → `AviStructure` (header, movi payload, idx1, suffix)
2. `process_chunks()` filters/duplicates `AviChunk` objects per `ClipOptions`
3. `build_movi_and_index()` reconstructs binary movi+idx1
4. `update_header_counts()` patches frame counts in AVI header

Multiple clips concatenated at chunk level, each tagged with `clip_id` for independent per-clip `ClipOptions`. Normalization (`normalize_to_xvid`) shells out to ffmpeg to convert any input to Xvid AVI. Presets in `NORMALIZE_PRESETS`.

### GUI layer (PySide6)

**Entry**: `main.py` → `gui/app.py` (QApplication + dark Fusion theme) → `gui/main_window.py`

**Layout**: QSplitter-based — horizontal splitter holds clip panel | centre | settings panel. Centre has a vertical splitter: preview widget on top, timeline on bottom. All panels are resizable.

**Data model** (`gui/models/`):
- `clip_model.py`: `ClipProfile` dataclass (per-clip state + mosh settings) and `ClipListModel` (QAbstractListModel with MIME drag-reorder)
- `project.py`: Central state container. Owns `ClipListModel`, tracks selection. Emits `clips_changed`, `clip_selected(int)`, `clip_updated(int)`, `status_message(str)`

**Widgets** (`gui/widgets/`):
- `clip_panel.py`: QListView with custom delegate, drag-reorder, auto-starts normalization + thumbnail extraction on import
- `preview_widget.py`: Inline video display with play/pause/step/scrub. Live re-mosh pipeline: setting change → 300ms debounce → MoshWorker → FrameExtractor → display. Toggle between "Selected" clip and "All Clips" combined preview
- `timeline_widget.py`: Premiere-style NLE timeline using QPainter. Time-based coordinates (`pixels_per_second`), clip blocks with gradient fills, adaptive frame visualization (density waveform at low zoom, individual bars at high zoom). Zoom with scroll wheel, pan with middle-mouse
- `settings_panel.py`: Per-clip controls (keep_first, duplicate_count, duplicate_gap, drop_first_keyframe, keep/drop keys). 300ms debounce before pushing changes
- `toolbar.py`: Open, Add Clip, Render, Help actions

**Workers** (`gui/workers/`): All QThread subclasses communicating via signals.
- `normalize_worker.py`: Runs `mosh.normalize_to_xvid()`
- `mosh_worker.py`: Runs `mosh.rewrite_avi()`. `build_clip_options()` converts ClipProfile → ClipOptions
- `frame_extractor.py`: Decodes frames via cv2 (ffmpeg fallback)
- `keyframe_analyzer.py`: Extracts keyframe positions via ffprobe

**Signal flow** (wired in `main_window._connect_signals()`):
- Clip selection → settings panel loads clip, preview refreshes (cache invalidated)
- Setting change → project emits clips_changed → preview debounce → re-mosh
- Timeline click → selects clip + sets playhead → preview seeks to frame
- Preview frame change ↔ timeline playhead (bidirectional)

**Legacy**: Old Tkinter GUI files are in `legacy/` (mosh_gui.py, shortcuts.py, timeline.py, video_preview.py).

## Key constraints

- Binary parser only handles **RIFF AVI** with flat (non-nested) movi sections. All non-AVI inputs must be normalized first.
- `ffmpeg` and `ffprobe` must be on PATH.
- `opencv-python-headless` is used for frame extraction; falls back to ffmpeg pipe if unavailable.
- Output format is always AVI (Xvid). MP4/WebM export not implemented.
- `mosh.py` must not be modified — the GUI wraps it via `MoshWorker`.
