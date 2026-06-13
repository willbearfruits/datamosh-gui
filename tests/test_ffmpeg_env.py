"""Tests for gui.ffmpeg_env (Windows ffmpeg discovery + console suppression)."""

import os
import subprocess
import sys

from gui import ffmpeg_env


def test_missing_ffmpeg_tools_reports_both_when_absent(monkeypatch):
    monkeypatch.setattr(ffmpeg_env.shutil, "which", lambda name: None)
    assert ffmpeg_env.missing_ffmpeg_tools() == ["ffmpeg", "ffprobe"]


def test_missing_ffmpeg_tools_empty_when_present(monkeypatch):
    monkeypatch.setattr(ffmpeg_env.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert ffmpeg_env.missing_ffmpeg_tools() == []


def test_missing_ffmpeg_tools_reports_only_absent(monkeypatch):
    monkeypatch.setattr(
        ffmpeg_env.shutil, "which",
        lambda name: None if name == "ffprobe" else "/usr/bin/ffmpeg",
    )
    assert ffmpeg_env.missing_ffmpeg_tools() == ["ffprobe"]


def test_ensure_ffmpeg_on_path_noop_when_not_frozen(monkeypatch):
    monkeypatch.setattr(ffmpeg_env.sys, "frozen", False, raising=False)
    before = os.environ.get("PATH")
    ffmpeg_env.ensure_ffmpeg_on_path()
    assert os.environ.get("PATH") == before


def test_suppress_subprocess_console_idempotent_and_platform_aware():
    original = subprocess.Popen
    try:
        ffmpeg_env.suppress_subprocess_console()
        first = subprocess.Popen
        ffmpeg_env.suppress_subprocess_console()
        # Second call must not re-wrap (no nesting / runaway subclassing).
        assert subprocess.Popen is first
        if sys.platform == "win32":
            assert first is not original
            assert getattr(first, "_datamosh_no_window", False) is True
        else:
            assert first is original  # no-op off Windows
    finally:
        subprocess.Popen = original
