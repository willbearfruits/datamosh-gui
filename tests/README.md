# Test Suite

Automated tests for the current PySide6 Datamosh GUI and core AVI engine.

## Install

```bash
pip install -r requirements.txt
```

## Run

Full suite (recommended in headless shells/CI):

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

Run all tests with default config:

```bash
pytest
```

Run a single file:

```bash
pytest tests/test_timeline_project.py
```

Run by keyword:

```bash
pytest -k "timeline"
```

## Markers

Defined in `pytest.ini`:

- `integration`: tests that may require real video assets
- `gui`: Qt/UI tests
- `slow`: longer-running tests

Examples:

```bash
pytest -m "not integration"
pytest -m gui
```

## Current Test Files

- `tests/test_clip_model.py`
- `tests/test_mosh.py`
- `tests/test_mosh_worker.py`
- `tests/test_project.py`
- `tests/test_timeline_duration.py`
- `tests/test_timeline_project.py`
- `tests/conftest.py`

## Notes

- `legacy/` tests are historical and are not part of default test discovery.
- If Qt crashes in headless environments, set `QT_QPA_PLATFORM=offscreen`.
