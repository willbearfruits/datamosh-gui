# Changelog

All notable changes to this project are documented here.

## [Unreleased] - 2026-02-17

### Added
- In-app update checker wired to GitHub Releases (`Update` toolbar action).
- Version file and runtime version helpers (`VERSION`, `gui/version.py`).
- Release docs (`RELEASES.md`).
- Update checker tests (`tests/test_update_checker.py`).

### Release Engineering
- Added automated cross-platform release workflow:
  - `.github/workflows/release.yml`
- Added Linux `.deb` packager script:
  - `packaging/linux/build_deb.sh`
- Added Windows installer script (Inno Setup):
  - `packaging/windows/datamosh.iss`
- Release artifacts now target portable + installer outputs for Linux/Windows/macOS.

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
