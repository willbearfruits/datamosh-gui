"""Tests for gui.workers.mosh_worker."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gui.models.clip_model import ClipProfile
from gui.workers.mosh_worker import build_clip_options, MoshWorker

import mosh


def test_build_clip_options_defaults():
    clips = [
        ClipProfile(source_path=Path("/tmp/a.mp4")),
        ClipProfile(source_path=Path("/tmp/b.mp4")),
    ]
    opts = build_clip_options(clips)
    assert len(opts) == 2
    assert opts[0].keep_initial_keyframes == 1
    assert opts[0].duplicate_count == 0
    assert opts[0].duplicate_gap == 1
    assert opts[0].drop_first_keyframe is False


def test_build_clip_options_custom():
    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        keep_first=3,
        duplicate_count=5,
        duplicate_gap=2,
        drop_first_keyframe=True,
        keep_keys_spec="0,5",
        drop_keys_spec="3",
    )
    opts = build_clip_options([clip])
    assert opts[0].keep_initial_keyframes == 3
    assert opts[0].duplicate_count == 5
    assert opts[0].duplicate_gap == 2
    assert opts[0].drop_first_keyframe is True
    assert opts[0].keep_specific_keys == {0, 5}
    assert opts[0].drop_specific_keys == {3}


def test_build_clip_options_empty_specs():
    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        keep_keys_spec="",
        drop_keys_spec="",
    )
    opts = build_clip_options([clip])
    assert opts[0].keep_specific_keys is None
    assert opts[0].drop_specific_keys is None


def test_build_clip_options_clamps_negatives():
    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        keep_first=-5,
        duplicate_count=-1,
        duplicate_gap=0,
    )
    opts = build_clip_options([clip])
    assert opts[0].keep_initial_keyframes == 1
    assert opts[0].duplicate_count == 0
    assert opts[0].duplicate_gap == 1


def test_build_clip_options_drop_first_only():
    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        keep_first=0,
        drop_first_keyframe=True,
    )
    opts = build_clip_options([clip])
    assert opts[0].keep_initial_keyframes == 0
    assert opts[0].drop_first_keyframe is True


def test_mosh_worker_no_ready_clips(qtbot):
    clips = [ClipProfile(source_path=Path("/tmp/a.mp4"))]  # not normalized
    worker = MoshWorker(clips, Path("/tmp/out.avi"))
    errors = []
    worker.error.connect(errors.append)

    with qtbot.waitSignal(worker.error, timeout=5000):
        worker.start()

    assert len(errors) == 1
    assert "No clips" in errors[0]


def test_mosh_worker_success(qtbot, temp_dir):
    """Test MoshWorker calls rewrite_avi correctly with a mock."""
    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        normalized_path=temp_dir / "norm.avi",
    )
    out = temp_dir / "out.avi"

    with patch.object(mosh, "rewrite_avi") as mock_rewrite:
        worker = MoshWorker([clip], out)
        results = []
        worker.finished_ok.connect(results.append)

        with qtbot.waitSignal(worker.finished_ok, timeout=5000):
            worker.start()

        assert len(results) == 1
        assert results[0] == str(out)
        mock_rewrite.assert_called_once()


def test_mosh_worker_exception(qtbot, temp_dir):
    """Test MoshWorker emits error on exception."""
    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        normalized_path=temp_dir / "norm.avi",
    )
    out = temp_dir / "out.avi"

    with patch.object(mosh, "rewrite_avi", side_effect=RuntimeError("boom")):
        worker = MoshWorker([clip], out)
        errors = []
        worker.error.connect(errors.append)

        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        assert "boom" in errors[0]


def test_mosh_worker_size_overflow_message(qtbot, temp_dir):
    """A struct.error from the 32-bit AVI size fields becomes an actionable message."""
    import struct as _struct

    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        normalized_path=temp_dir / "norm.avi",
    )
    out = temp_dir / "out.avi"
    overflow = _struct.error("'I' format requires 0 <= number <= 4294967295")

    with patch.object(mosh, "rewrite_avi", side_effect=overflow):
        worker = MoshWorker([clip], out)
        errors = []
        worker.error.connect(errors.append)

        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        assert errors
        assert "4 GB" in errors[0] or "too large" in errors[0]
        # The cryptic raw struct message must not leak to the user.
        assert "format requires" not in errors[0]


def test_mosh_worker_non_overflow_struct_error_not_mislabeled(qtbot, temp_dir):
    """A struct.error from corrupt/truncated parsing must NOT claim the 4 GB limit."""
    import struct as _struct

    clip = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        normalized_path=temp_dir / "norm.avi",
    )
    out = temp_dir / "out.avi"
    parse_err = _struct.error("unpack_from requires a buffer of at least 4 bytes")

    with patch.object(mosh, "rewrite_avi", side_effect=parse_err):
        worker = MoshWorker([clip], out)
        errors = []
        worker.error.connect(errors.append)

        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        assert errors
        assert "4 GB" not in errors[0] and "too large" not in errors[0]
        assert "video data" in errors[0]
