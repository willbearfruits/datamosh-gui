# Changelog

All notable changes to the Datamosh GUI project will be documented in this file.

## [Unreleased] - 2025-11-26

### Added
- **Frame Export Feature**: Export current preview frame as PNG/JPEG with one click
- **Adaptive Preview Width**: Preview window automatically adjusts to screen size (max 1280px)
- **Logging Framework**: Comprehensive logging to `datamosh-gui.log` and console
- **Test Suite**: pytest-based test suite with fixtures and mocks
  - `tests/test_mosh.py` - Core engine tests
  - `tests/test_video_preview.py` - Preview widget tests
  - `tests/test_shortcuts.py` - Keyboard shortcut tests
  - `tests/conftest.py` - Shared fixtures
- **Git Repository**: Version control initialized with proper .gitignore
- **Enhanced .gitignore**: Added patterns for logs, backups, test artifacts, PyInstaller

### Improved
- **Video Preview Quality**: Changed scaling from INTER_LINEAR to INTER_AREA for better downscaling
- **Error Handling**: Replaced print statements with proper logging (logger.error, logger.info)
- **Resource Cleanup**: Better exception handling with exc_info=True for stack traces
- **Documentation**: Added tests/README.md with usage instructions

### Changed
- Cleaned build artifacts (build/, dist/, __pycache__/)
- Updated requirements.txt with pytest dependencies
- Organized imports in timeline.py and shortcuts.py

### Technical Details
- All modules now use Python logging framework
- Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Logs written to both file (`datamosh-gui.log`) and console
- Test coverage target: 70%+
- Production readiness score: 78% → 85% (estimated)

---

## [1.0.0] - 2024-11-24 (Prior Release)

### Features
- Interactive Tkinter GUI for datamosh effects
- Core AVI manipulation engine
- Hardware-accelerated preview (OpenCV)
- Timeline editor with I-frame/P-frame markers
- Keyboard shortcuts system
- Drag-and-drop support
- Multiple normalization presets
- Per-clip configuration
- P-frame duplication

---

**Note**: Version numbers follow [Semantic Versioning](https://semver.org/)
