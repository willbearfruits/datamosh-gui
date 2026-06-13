# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [1.2.0] - 2026-06-13

### Added
- Save/open projects as `.dmosh` files (clip sources, per-clip settings, timeline, selection).
- Per-segment glitch settings: each timeline segment can override the clip's keep/duplicate/keyframe settings.
- Export to MP4/MOV (H.264) in addition to native AVI, via an ffmpeg transcode of the moshed output.

### Fixed
- Cut/inject at playhead now maps to a *source* frame (was misplaced when duplicates were active); the playhead snaps to frames.
- Audio survives moshing/export — normalization re-encodes to MP3 (AVI can't carry AAC/Opus via stream-copy).
- macOS: tooltips show native shortcuts (⌘) and the timeline delete also binds Backspace.
- Windows: no console-window flashes; bundled-ffmpeg detection with a clear startup message.
- Live preview no longer mixes stale frames; cooperative cancellation (no unsafe `terminate()`).
- Core engine: tolerant idx1 parsing (absolute offsets / missing index), clearer keep/drop precedence, real ffmpeg error messages, and a clear >4 GB output guard.

### Engineering
- CI now runs the pytest suite on push/PR (ubuntu + windows); repaired the broken download-portal links.

## [1.1.5] - 2026-02-28

### Fixed
- Temp directories from normalization and I-frame injection are now cleaned up when a clip is removed, preventing `/tmp` accumulation over long sessions.
- Video info probing (fps, frame count, dimensions) moved off the Qt main thread — no more UI freeze after importing clips.
- Timeline scroll wheel now pans; `Ctrl+wheel` zooms (was inverted vs. shortcut docs).
- Clip list view now highlights the correct row when a timeline clip is clicked.
- Settings panel controls are now disabled when no clip is selected (prevented silent no-op slider interactions).
- "Cut At Playhead" context menu item disabled on empty timeline.
- `UpdateWorker` exceptions no longer permanently block future update checks.
- OpenCV video capture handle always released via `finally` (prevents file lock on Windows).
- `RenderDialog` stops its render worker when the dialog is closed mid-render.
- Drag-reorder MIME data parse is now validated; malformed drops return `False` cleanly.
- Undo/redo stacks use `deque(maxlen=200)` for O(1) eviction.
- Timeline hint text contrast raised to meet WCAG AA minimum.

## [1.1.4] - 2026-02-18

### Changed
- Linux release build runner pinned to `ubuntu-22.04` to improve AppImage runtime compatibility on older glibc systems.

## [1.1.3] - 2026-02-18

### Added
- Linux AppImage packaging script (`packaging/linux/build_appimage.sh`).
- Linux release artifact now includes `Datamosh-<version>-linux-x86_64.AppImage`.

### Changed
- GitHub release workflow now builds and publishes Linux AppImage artifacts.
- Website and release docs updated to include AppImage downloads.

## [1.1.2] - 2026-02-18

### Fixed
- Windows installer build path for Inno Setup license file (`packaging/windows/datamosh.iss`).

### Changed
- Refreshed download website layout with top visual showcase and bottom platform downloads.
- Added Windows download links in website release section.

## [1.1.1] - 2026-02-18

### Added
- In-app update checker wired to GitHub Releases (`Update` toolbar action).
- Version file and runtime version helpers (`VERSION`, `gui/version.py`).
- Release docs (`RELEASES.md`).
- Update checker tests (`tests/test_update_checker.py`).
- Import options flow for clip ingest with saved defaults:
  - normalize-all vs direct-AVI-prefer mode
  - preset/custom normalization controls (width/height/GOP/qscale/audio)
  - persistent import profile via Qt settings
- Timeline I-frame injection from media files (video or image):
  - creates a single-frame Xvid AVI inject clip
  - inserts clip at playhead position
  - available from timeline button, context menu, and `Ctrl+Shift+I`
- GitHub Pages download site with release links and media preview:
  - `docs/index.html`
  - `.github/workflows/pages.yml`

### Release Engineering
- Added automated cross-platform release workflow:
  - `.github/workflows/release.yml`
- Added Linux `.deb` packager script:
  - `packaging/linux/build_deb.sh`
- Added Windows installer script (Inno Setup):
  - `packaging/windows/datamosh.iss`
- Release artifacts now target portable + installer outputs for Linux/Windows/macOS.
- Added polished release body template with showcase media:
  - `RELEASE_BODY.md`
- Publish job now runs with partial artifacts when one platform build fails.
- Fixed release publish job to checkout repository before applying `RELEASE_BODY.md`.
- Added workflow to promote `v1.1.0-beta.5` as current non-prerelease release metadata.

### Documentation
- Rewrote `README.md` for the current PySide6 timeline workflow.
- Updated `BUILD_INSTRUCTIONS.md` to package from `main.py` (removed legacy Tkinter build paths).
- Updated `tests/README.md` to match the active test suite.
- Added `CONTRIBUTING.md` and `SECURITY.md`.
- Added GitHub templates:
  - `.github/pull_request_template.md`
  - `.github/ISSUE_TEMPLATE/bug_report.yml`
  - `.github/ISSUE_TEMPLATE/feature_request.yml`

### Maintenance
- Updated `launch.sh` to run the active entrypoint (`main.py`) and validate runtime dependencies.

## [0.2.0]

### Features
- Timeline-focused PySide6 GUI with:
  - drag/drop from clip bin to timeline
  - segment reorder
  - cut at playhead
  - per-segment first-I-frame toggle
  - undo/redo support
- Timeline playback and preview pipeline aligned with timeline sequence behavior.

## [0.1.0]

### Initial
- Core AVI datamosh engine (`mosh.py`).
- Early GUI foundation and normalization pipeline.
