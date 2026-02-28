# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the GUI application (PySide6)
python3 main.py

# Run the CLI engine directly
python3 mosh.py input.avi output.avi --keep-first 1

# Install dependencies (use a venv)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run all tests (headless — required in CI and non-display shells)
QT_QPA_PLATFORM=offscreen pytest

# Skip integration tests that require real video files
pytest -m "not integration"

# Run a single test file
pytest tests/test_clip_model.py

# Run a specific test
pytest tests/test_clip_model.py::TestClipListModel::test_add_clip

# Run with coverage
pytest --cov=. --cov-report=term-missing
```

Tests are in `tests/` with markers `integration` (requires real video files), `gui` (requires display), and `slow`. The `mock_ffmpeg` fixture in `conftest.py` patches `subprocess.run()` and `subprocess.Popen()` globally. GUI tests use `pytest-qt`; use `qtbot.waitSignal()` for Qt signal assertions.

## Architecture

The application has two layers: a pure binary AVI manipulation engine (`mosh.py`, treat as stable/untouched) and a PySide6 GUI (`gui/`, `main.py`).

### Core engine (`mosh.py`)
Operates directly on the RIFF/AVI binary format — no video decoding. Pipeline:
1. `parse_avi_file()` → `AviStructure` (header, movi payload, idx1, suffix)
2. `process_chunks()` filters/duplicates `AviChunk` objects per `ClipOptions`
3. `build_movi_and_index()` reconstructs binary movi+idx1
4. `update_header_counts()` patches frame counts in AVI header

Multiple clips concatenated at chunk level, each tagged with `clip_id` for independent per-clip `ClipOptions`. Normalization (`normalize_to_xvid`) shells out to ffmpeg to convert any input to Xvid AVI. Presets in `NORMALIZE_PRESETS`.

### GUI layer (PySide6)

**Entry**: `main.py` → `gui/app.py` (QApplication + dark Fusion theme, plus `sanitize_qt_plugin_env()` to strip OpenCV's bundled Qt plugins before startup) → `gui/main_window.py`

**Layout**: QSplitter-based — horizontal splitter holds clip panel | centre | settings panel. Centre has a vertical splitter: preview widget on top, timeline on bottom. All panels are resizable.

**Data model** (`gui/models/`):
- `clip_model.py`: `ClipProfile` dataclass (per-clip state + mosh settings) and `ClipListModel` (QAbstractListModel with MIME drag-reorder)
- `project.py`: Central state container. Owns `ClipListModel`, tracks selection, and maintains undo/redo history (`_undo_stack`/`_redo_stack`, 200-snapshot limit via `ProjectSnapshot`). Emits `clips_changed`, `clip_selected(int)`, `clip_updated(int)`, `timeline_changed`, `history_changed(can_undo, can_redo)`, `status_message(str)`

**Widgets** (`gui/widgets/`):
- `clip_panel.py`: QListView with custom delegate, drag-reorder, auto-starts normalization + thumbnail extraction on import
- `preview_widget.py`: Inline video display with play/pause/step/scrub. Live re-mosh pipeline: setting change → 300ms debounce → MoshWorker → FrameExtractor → display. Toggle between "Selected" clip and "All Clips" combined preview
- `timeline_widget.py`: Premiere-style NLE timeline using QPainter. Time-based coordinates (`pixels_per_second`), clip blocks with gradient fills, adaptive frame visualization (density waveform at low zoom, individual bars at high zoom). Zoom with scroll wheel, pan with middle-mouse (~51 KB, largest file)
- `settings_panel.py`: Per-clip controls (keep_first, duplicate_count, duplicate_gap, drop_first_keyframe, keep/drop keys). 300ms debounce before pushing changes
- `toolbar.py`: Open, Add Clip, Render, Help actions

**Dialogs** (`gui/dialogs/`): `normalize_dialog.py` (import settings), `render_dialog.py` (output filename), `shortcuts_dialog.py` (keyboard shortcut reference).

**Workers** (`gui/workers/`): All QThread subclasses communicating via signals.
- `normalize_worker.py`: Runs `mosh.normalize_to_xvid()`, creates temp dir with prefix `datamosh-norm-`
- `mosh_worker.py`: Runs `mosh.rewrite_avi()`. `build_clip_options()` converts ClipProfile → ClipOptions. Also handles trim-aware rewrite (`_rewrite_with_trims()`) which slices binary video chunks by frame range
- `frame_extractor.py`: Decodes frames via cv2, falls back to ffmpeg pipe; respects `_abort` flag. Emits `frame_ready(int, QImage)`
- `keyframe_analyzer.py`: Runs `ffprobe -show_entries packet=pts_time,flags -of json`; emits `finished_ok(list[FrameInfo])`
- `iframe_inject_worker.py`: Creates single-frame I-frame clips, temp dir prefix `datamosh-inject-`
- `update_worker.py`: Checks GitHub releases for newer versions

**Signal flow** (wired in `main_window._connect_signals()`):
- Clip selection → settings panel loads clip, preview refreshes (cache invalidated)
- Setting change → project emits clips_changed → preview debounce → re-mosh
- Timeline click → selects clip + sets playhead → preview seeks to frame
- Preview frame change ↔ timeline playhead (bidirectional)

**Debounce pattern**: Both `settings_panel.py` and `preview_widget.py` use `QTimer.setSingleShot(True)` with a 300ms timeout before triggering expensive operations.

**Temp files**: Workers create directories under `/tmp` (e.g. `datamosh-preview-*`, `datamosh-norm-*`). The preview widget cleans up its own dir via destructor; normalize/inject workers do not — their paths live in `ClipProfile.normalized_path` for the session lifetime. `.gitignore` excludes `mosh-*/` and `moshprep-*/`.

**Legacy**: Old Tkinter GUI files are in `legacy/` (mosh_gui.py, shortcuts.py, timeline.py, video_preview.py).

## Coding conventions

- PEP 8, 4-space indentation. Type-annotate new/modified code (`Path`, `list[str]`, etc.)
- `snake_case` for modules/functions/variables, `PascalCase` for Qt classes, `UPPER_SNAKE_CASE` for constants
- UI handlers stay thin — move expensive work to `gui/workers/`

## Key constraints

- Binary parser only handles **RIFF AVI** with flat (non-nested) movi sections. All non-AVI inputs must be normalized first.
- `ffmpeg` and `ffprobe` must be on PATH.
- `opencv-python-headless` is used for frame extraction; falls back to ffmpeg pipe if unavailable.
- Output format is always AVI (Xvid). MP4/WebM export not implemented.
- `mosh.py` must not be modified — the GUI wraps it via `MoshWorker`.
