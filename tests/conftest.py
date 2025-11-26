"""Pytest configuration and shared fixtures."""
import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmpdir = Path(tempfile.mkdtemp(prefix="test-datamosh-"))
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_avi_path():
    """Path to sample AVI file (would need to be created for real tests)."""
    # In real tests, you'd either:
    # 1. Include a small sample video in tests/fixtures/
    # 2. Generate one programmatically with ffmpeg
    # 3. Skip tests that require video files if not available
    return Path("tests/fixtures/sample.avi")


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Mock ffmpeg subprocess calls for testing without ffmpeg."""
    import subprocess

    def mock_run(*args, **kwargs):
        """Mock subprocess.run for ffmpeg commands."""
        class MockResult:
            returncode = 0
            stdout = b""
            stderr = b""
        return MockResult()

    def mock_popen(*args, **kwargs):
        """Mock subprocess.Popen for ffmpeg commands."""
        class MockProcess:
            returncode = 0
            def __init__(self):
                self.stdout = None
                self.stderr = None
            def communicate(self):
                return b"", b""
            def poll(self):
                return 0
            def terminate(self):
                pass
            def wait(self, timeout=None):
                pass
        return MockProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
