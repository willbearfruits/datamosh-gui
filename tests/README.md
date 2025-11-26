# Datamosh GUI Test Suite

Automated test suite for the Datamosh GUI application.

## Setup

Install test dependencies:

```bash
pip install pytest pytest-cov pytest-mock
```

## Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=. --cov-report=html
```

Run specific test file:
```bash
pytest tests/test_mosh.py
```

Run tests matching a pattern:
```bash
pytest -k "test_parse"
```

Run with verbose output:
```bash
pytest -v
```

## Test Markers

Tests are organized with markers:

- `@pytest.mark.integration` - Integration tests requiring video files
- `@pytest.mark.gui` - GUI tests requiring a display
- `@pytest.mark.slow` - Slow tests (>1 second)

Run only unit tests (skip integration):
```bash
pytest -m "not integration"
```

Run only integration tests:
```bash
pytest -m integration
```

## Test Structure

```
tests/
├── __init__.py           # Test package init
├── conftest.py           # Shared fixtures and configuration
├── test_mosh.py          # Core engine tests
├── test_video_preview.py # Video preview widget tests
├── test_shortcuts.py     # Keyboard shortcut tests
└── README.md            # This file
```

## Adding Tests

When adding new features:

1. Create test file: `tests/test_<module>.py`
2. Add test class: `class Test<Feature>:`
3. Add test methods: `def test_<specific_behavior>:`
4. Use fixtures from `conftest.py` for common setup

Example:
```python
def test_new_feature(temp_dir, mock_ffmpeg):
    """Test description."""
    # Arrange
    setup_code()

    # Act
    result = function_under_test()

    # Assert
    assert result == expected
```

## Coverage

Target: 70%+ code coverage

View coverage report:
```bash
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

## CI/CD Integration

To integrate with CI/CD:

```yaml
# .github/workflows/test.yml (example)
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest --cov=. --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Notes

- GUI tests may be skipped in headless environments
- Integration tests require sample video files in `tests/fixtures/`
- Mock ffmpeg for unit tests to avoid external dependencies
