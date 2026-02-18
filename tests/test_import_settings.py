"""Tests for import profile normalization helpers."""

from gui.widgets.clip_panel import (
    IMPORT_MODE_NORMALIZE,
    IMPORT_MODE_PREFER_SOURCE,
    default_import_settings,
    normalize_import_settings,
)


def test_default_import_settings_values() -> None:
    out = default_import_settings()
    assert out["mode"] == IMPORT_MODE_NORMALIZE
    assert out["preset"] == "balanced"
    assert out["keep_audio"] is True


def test_normalize_import_settings_sanitizes_values() -> None:
    out = normalize_import_settings(
        {
            "mode": "bad-mode",
            "preset": "BAD",
            "width": "0",
            "height": "720",
            "qscale": "0",
            "gop": "48",
            "keep_audio": "false",
            "remember_defaults": "yes",
        }
    )
    assert out["mode"] == IMPORT_MODE_NORMALIZE
    assert out["preset"] == "balanced"
    assert out["width"] is None
    assert out["height"] == 720
    assert out["qscale"] is None
    assert out["gop"] == 48
    assert out["keep_audio"] is False
    assert out["remember_defaults"] is True


def test_normalize_import_settings_accepts_prefer_source_mode() -> None:
    out = normalize_import_settings({"mode": IMPORT_MODE_PREFER_SOURCE, "preset": "fast"})
    assert out["mode"] == IMPORT_MODE_PREFER_SOURCE
    assert out["preset"] == "fast"
