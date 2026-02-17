"""Tests for gui.models.clip_model."""

import pytest
from pathlib import Path

from gui.models.clip_model import ClipProfile, ClipListModel


@pytest.fixture
def model():
    return ClipListModel()


@pytest.fixture
def sample_clip():
    return ClipProfile(source_path=Path("/tmp/test.mp4"))


def test_add_clip(model, sample_clip):
    row = model.add_clip(sample_clip)
    assert row == 0
    assert model.rowCount() == 1
    assert model.clip_at(0) is sample_clip


def test_add_multiple_clips(model):
    c1 = ClipProfile(source_path=Path("/tmp/a.mp4"))
    c2 = ClipProfile(source_path=Path("/tmp/b.mp4"))
    model.add_clip(c1)
    model.add_clip(c2)
    assert model.rowCount() == 2
    assert model.clip_at(0) is c1
    assert model.clip_at(1) is c2


def test_remove_clip(model, sample_clip):
    model.add_clip(sample_clip)
    model.remove_clip(0)
    assert model.rowCount() == 0


def test_remove_invalid_row(model):
    model.remove_clip(5)  # should not raise
    assert model.rowCount() == 0


def test_move_clip(model):
    clips = [
        ClipProfile(source_path=Path(f"/tmp/{i}.mp4"))
        for i in range(3)
    ]
    for c in clips:
        model.add_clip(c)

    model.move_clip(0, 2)
    assert model.clip_at(0) is clips[1]
    assert model.clip_at(1) is clips[2]
    assert model.clip_at(2) is clips[0]


def test_move_clip_same_row(model, sample_clip):
    model.add_clip(sample_clip)
    model.move_clip(0, 0)
    assert model.clip_at(0) is sample_clip


def test_clip_at_out_of_range(model):
    assert model.clip_at(-1) is None
    assert model.clip_at(0) is None


def test_display_role(model, sample_clip):
    from PySide6.QtCore import Qt
    model.add_clip(sample_clip)
    idx = model.index(0, 0)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "test"


def test_display_role_normalizing(model):
    from PySide6.QtCore import Qt
    clip = ClipProfile(source_path=Path("/tmp/vid.mp4"), normalizing=True)
    model.add_clip(clip)
    idx = model.index(0, 0)
    text = model.data(idx, Qt.ItemDataRole.DisplayRole)
    assert "normalizing" in text


def test_clip_profile_label():
    clip = ClipProfile(source_path=Path("/home/user/my_video.avi"))
    assert clip.label() == "my_video"


def test_clip_profile_is_ready():
    clip = ClipProfile(source_path=Path("/tmp/test.mp4"))
    assert not clip.is_ready()
    clip.normalized_path = Path("/tmp/test_normalized.avi")
    assert clip.is_ready()
    clip.normalizing = True
    assert not clip.is_ready()


def test_update_clip(model, sample_clip):
    from PySide6.QtCore import Qt
    model.add_clip(sample_clip)
    sample_clip.normalizing = True
    model.update_clip(0)
    idx = model.index(0, 0)
    text = model.data(idx, Qt.ItemDataRole.DisplayRole)
    assert "normalizing" in text
