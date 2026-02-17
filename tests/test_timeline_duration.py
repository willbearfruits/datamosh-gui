"""Duration math tests for timeline output frame prediction."""

from gui.workers.keyframe_analyzer import FrameInfo
from gui.widgets.timeline_widget import TimelineWidget


def test_estimate_output_frames_accounts_for_duplicates():
    out = TimelineWidget._estimate_output_frames_without_analysis(
        source_frames=100,
        dup_count=2,
        dup_gap=5,
    )
    assert out == 140


def test_predict_output_frames_keeps_first_when_keep_zero_and_no_drop():
    frames = [
        FrameInfo(index=0, is_keyframe=True, pts_time=0.0),
        FrameInfo(index=1, is_keyframe=False, pts_time=0.04),
        FrameInfo(index=2, is_keyframe=True, pts_time=0.08),
    ]

    out = TimelineWidget._predict_output_frame_count(
        frames,
        keep_first=0,
        drop_first=False,
        dup_count=0,
        dup_gap=1,
        keep_keys_spec="",
        drop_keys_spec="",
    )
    # First keyframe remains, second keyframe drops.
    assert out == 2
