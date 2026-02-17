# Repository Guidelines

## Project Structure & Module Organization
- `main.py` is the GUI entrypoint.
- `gui/` contains the active PySide6 app, split by concern:
  - `gui/widgets/`, `gui/dialogs/`, `gui/models/`, `gui/workers/`
- `mosh.py` is the core binary AVI datamosh engine and CLI path.
- `tests/` contains pytest coverage; shared fixtures live in `tests/conftest.py`.
- `legacy/` stores old Tkinter-era modules for reference only.

## Architecture & Processing Constraints
- Keep the two-layer design: GUI (`gui/`) orchestrates; core AVI processing lives in `mosh.py`.
- Treat `mosh.py` as stable core logic unless a change is explicitly required and reviewed.
- The parser supports RIFF AVI with flat `movi` sections; non-AVI inputs must be normalized first.
- External tools `ffmpeg` and `ffprobe` must be available on `PATH`.
- Current render pipeline outputs AVI/Xvid; MP4/WebM export is not implemented.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: create a local environment.
- `pip install -r requirements.txt`: install runtime and test dependencies.
- `python3 main.py`: run the GUI locally.
- `python3 mosh.py input.avi output.avi --keep-first 1`: run core processing from CLI.
- `QT_QPA_PLATFORM=offscreen pytest`: full test run in headless shells/CI.
- `pytest tests/test_clip_model.py`: run a single test module quickly.
- `pytest -m "not integration"`: skip video-dependent integration tests.
- `pytest --cov=. --cov-report=term-missing`: optional coverage summary.

## Coding Style & Naming Conventions
- Follow PEP 8 and use 4-space indentation.
- Keep new and modified code type-annotated (`Path`, `list[str]`, etc.), consistent with existing modules.
- Use `snake_case` for modules/functions/variables, `PascalCase` for Qt classes, and `UPPER_SNAKE_CASE` for constants.
- Keep UI handlers thin; move expensive work to `gui/workers/`.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-qt`, and `pytest-mock`.
- Naming: files as `tests/test_<area>.py`, tests as `test_<behavior>`.
- Reuse fixtures from `tests/conftest.py`; use `qtbot` for Qt signal/UI assertions.
- Available markers from `pytest.ini`: `integration`, `gui`, `slow`.

## Commit & Pull Request Guidelines
- Follow the existing commit style: short, imperative subjects (for example, `Add mosh worker error handling`).
- Keep commits scoped to one logical change.
- Include in every PR: change summary, rationale, and validation commands run.
- Include screenshots or short clips for UI changes.
- Link related issue(s) and note user-visible behavior changes in changelog/docs.
