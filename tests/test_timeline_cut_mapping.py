"""Regression test: cut/inject at playhead must use a SOURCE frame index.

ClipRegion.duration_sec reflects the predicted OUTPUT length (source frames plus
duplicates). current_playhead_location() previously derived the cut frame from
fps * local_sec, i.e. an OUTPUT index, which project.split_timeline_item then
interpreted against the SOURCE frame count. With duplication active the output
count is inflated, so dropping the playhead at the visual midpoint produced a cut
clamped to the END of the source instead of its middle.
"""

import pytest

from gui.widgets.timeline_widget import TimelineCanvas, ClipRegion


@pytest.fixture
def canvas(qtbot):
    c = TimelineCanvas()
    qtbot.addWidget(c)
    return c


def _region(source_frames: int, output_frames: int, fps: float = 25.0) -> ClipRegion:
    return ClipRegion(
        timeline_index=0,
        clip_row=0,
        label="clip",
        frame_count=output_frames,
        source_frame_count=source_frames,
        fps=fps,
        duration_sec=output_frames / fps,
        loading=False,
    )


def test_playhead_midpoint_maps_to_source_midpoint_with_duplication(canvas):
    # 100 source frames doubled to 200 output frames via duplication.
    region = _region(source_frames=100, output_frames=200)
    canvas._regions = [region]
    canvas._total_duration = region.duration_sec
    canvas._playhead_sec = region.duration_sec / 2.0  # visual midpoint

    idx, local_frame = canvas.current_playhead_location()

    assert idx == 0
    # Must be ~the SOURCE midpoint (50), not the source end (99, the old bug) and
    # not the output midpoint (100).
    assert 45 <= local_frame <= 55
    assert local_frame < region.source_frame_count  # always a valid source index


def test_playhead_start_maps_to_frame_zero(canvas):
    region = _region(source_frames=80, output_frames=160)
    canvas._regions = [region]
    canvas._total_duration = region.duration_sec
    canvas._playhead_sec = 0.0

    idx, local_frame = canvas.current_playhead_location()
    assert idx == 0
    assert local_frame == 0


def test_playhead_snaps_to_frame(canvas):
    region = _region(source_frames=100, output_frames=100, fps=25.0)
    canvas._regions = [region]
    canvas._total_duration = region.duration_sec
    frame_dur = region.duration_sec / 100
    raw = 10 * frame_dur + frame_dur * 0.7  # 70% into frame 10
    snapped = canvas._snap_sec_to_frame(raw)
    # Snaps to ~1/3 into frame 10 (clearly inside the frame, left of centre).
    assert abs(snapped - (10 + 0.3) * frame_dur) < 1e-6


def test_playhead_without_duplication_still_maps_correctly(canvas):
    # No duplication: output == source, midpoint should be ~half.
    region = _region(source_frames=100, output_frames=100)
    canvas._regions = [region]
    canvas._total_duration = region.duration_sec
    canvas._playhead_sec = region.duration_sec / 2.0

    idx, local_frame = canvas.current_playhead_location()
    assert idx == 0
    assert 45 <= local_frame <= 55
