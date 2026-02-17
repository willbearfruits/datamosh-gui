"""Tests for gui.models.project."""

import pytest
from pathlib import Path

from gui.models.clip_model import ClipProfile
from gui.models.project import Project


@pytest.fixture
def project(qtbot):
    p = Project()
    return p


@pytest.fixture
def clip_a():
    return ClipProfile(source_path=Path("/tmp/a.mp4"))


@pytest.fixture
def clip_b():
    return ClipProfile(source_path=Path("/tmp/b.mp4"))


def test_add_clip(project, clip_a, qtbot):
    with qtbot.waitSignal(project.clips_changed):
        project.add_clip(clip_a)
    assert project.has_clips()
    assert len(project.clips) == 1


def test_first_clip_auto_selects(project, clip_a, qtbot):
    with qtbot.waitSignal(project.clip_selected):
        project.add_clip(clip_a)
    assert project.selected_row == 0
    assert project.selected_clip is clip_a


def test_remove_clip(project, clip_a, clip_b, qtbot):
    project.add_clip(clip_a)
    project.add_clip(clip_b)
    project.select_clip(1)
    project.remove_clip(0)
    assert len(project.clips) == 1
    assert project.clips[0] is clip_b


def test_select_clip(project, clip_a, clip_b, qtbot):
    project.add_clip(clip_a)
    project.add_clip(clip_b)

    with qtbot.waitSignal(project.clip_selected):
        project.select_clip(1)
    assert project.selected_row == 1
    assert project.selected_clip is clip_b


def test_all_ready(project, clip_a, clip_b):
    clip_a.normalized_path = Path("/tmp/norm_a.avi")
    clip_b.normalized_path = Path("/tmp/norm_b.avi")
    project.add_clip(clip_a)
    project.add_clip(clip_b)
    assert project.all_ready()


def test_not_all_ready(project, clip_a, clip_b):
    clip_a.normalized_path = Path("/tmp/norm_a.avi")
    project.add_clip(clip_a)
    project.add_clip(clip_b)
    assert not project.all_ready()


def test_notify_clip_updated(project, clip_a, qtbot):
    project.add_clip(clip_a)
    with qtbot.waitSignal(project.clip_updated):
        project.notify_clip_updated(0)
