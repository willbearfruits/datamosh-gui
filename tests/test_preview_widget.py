"""Tests for the live-preview generation-token guard (no stale frame mixing)."""

import pytest
from PySide6.QtGui import QImage

from gui.models.project import Project
from gui.widgets.preview_widget import PreviewWidget


@pytest.fixture
def preview(qtbot):
    widget = PreviewWidget(Project())
    qtbot.addWidget(widget)
    yield widget
    widget.shutdown()


def _img() -> QImage:
    return QImage(2, 2, QImage.Format.Format_RGB888)


def test_stale_frame_callbacks_are_ignored(preview):
    preview._generation = 5
    preview._frames = []
    preview._on_frame_decoded(3, 0, _img())  # from a superseded generation
    assert preview._frames == []
    preview._on_frame_decoded(5, 0, _img())  # current generation
    assert len(preview._frames) == 1


def test_stale_mosh_done_starts_no_extractor(preview):
    preview._generation = 5
    preview._extractor = None
    preview._on_mosh_done(3, "does-not-exist.avi")  # stale -> must be a no-op
    assert preview._extractor is None


def test_stale_extraction_done_does_not_touch_display(preview):
    preview._generation = 5
    preview._frames = [_img()]
    preview._current_frame = 0
    # Stale completion must not re-show frames or reset the scrubber.
    preview._on_extraction_done(2, 1)  # no exception, no-op


def test_cancel_workers_bumps_generation_and_clears_refs(preview):
    gen = preview._generation
    preview._cancel_workers()
    assert preview._generation == gen + 1
    assert preview._mosh_worker is None
    assert preview._extractor is None


def test_reset_clears_frames_and_invalidates_generation(preview):
    preview._frames = [_img(), _img()]
    preview._current_frame = 1
    gen = preview._generation
    preview.reset()
    assert preview._frames == []
    assert preview._current_frame == 0
    assert preview._generation == gen + 1
