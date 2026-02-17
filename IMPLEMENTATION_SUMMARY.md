# Implementation Summary

This repository currently ships a PySide6 desktop editor for timeline-based datamoshing.

## Current Architecture

- `main.py` launches the GUI.
- `gui/` contains the active application:
  - `widgets/` timeline, clip bin, preview, toolbar, settings
  - `models/` project state and clip/timeline data
  - `workers/` background normalization, frame extraction, keyframe analysis, render
- `mosh.py` remains the core AVI binary parser/rewriter and CLI.
- `legacy/` stores old Tkinter-era code for reference only.

## Core Workflow

1. Import clips.
2. Normalize to Xvid AVI in background workers.
3. Arrange timeline segments (drag/drop + reorder).
4. Cut segments at playhead.
5. Apply per-clip/per-segment keyframe and P-frame controls.
6. Preview timeline output.
7. Render final AVI.

## Timeline Editing Features

- Drag from bin to timeline
- Reorder timeline segments
- Cut at playhead (`Ctrl+K`)
- Toggle per-segment drop-first-I-frame (`I`)
- Delete segment (`Delete`)
- Undo/redo history

## Security/Privacy Snapshot (2026-02-17)

Repository scan found no embedded secrets, API keys, private key material, or hardcoded personal paths in tracked files.

Operational security notes:
- External tools (`ffmpeg`, `ffprobe`) are required at runtime.
- Subprocess usage in active code paths does not use `shell=True`.

## Validation Baseline

Headless-safe test command:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

Current baseline: full suite passing with one intentional skip.
