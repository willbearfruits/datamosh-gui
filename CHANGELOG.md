# Changelog

All notable changes to this project are documented here.

## [Unreleased] - 2026-02-17

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
