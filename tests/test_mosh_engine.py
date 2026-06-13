"""Engine tests for the mosh.py robustness fixes (idx1 tolerance, precedence, ffmpeg)."""

import struct
import pytest

import mosh
from mosh import AVIIF_KEYFRAME


# -- Minimal in-memory AVI builder --------------------------------------------

# frames: list of (is_keyframe, data_bytes). idx_mode controls how idx1 is written.
FRAMES = [(True, b"AAAA"), (False, b"BBBBBB"), (False, b"CC"), (True, b"DDDD")]


def _build_avi(frames, idx_mode="relative"):
    chunks = bytearray()
    entries = []  # (chunk_id, flags, movi_relative_offset, size)
    rel = 4  # first chunk offset within the movi payload (spec convention)
    for is_kf, data in frames:
        cid = b"00dc"
        size = len(data)
        entries.append((cid, AVIIF_KEYFRAME if is_kf else 0, rel, size))
        chunks += cid + struct.pack("<I", size) + data
        pad = size % 2
        if pad:
            chunks += b"\x00"
        rel += 8 + size + pad

    movi = b"LIST" + struct.pack("<I", 4 + len(chunks)) + b"movi" + bytes(chunks)
    movi_data_off = 12 + 8  # file offset of the 'movi' tag (RIFF header is 12 bytes)

    use = list(entries)
    if idx_mode == "short" and use:
        use = use[:-1]
    elif idx_mode == "extra":
        use = use + [(b"00dc", 0, 4, 1)]

    idx_payload = bytearray()
    for cid, flags, rel_off, size in use:
        if idx_mode == "absolute":
            off = movi_data_off + rel_off       # file-relative offsets (common muxer style)
        elif idx_mode == "garbage":
            off = 0xDEADBEEF
        else:
            off = rel_off
        idx_payload += cid + struct.pack("<I", flags) + struct.pack("<I", off) + struct.pack("<I", size)
    idx1 = b"idx1" + struct.pack("<I", len(idx_payload)) + bytes(idx_payload)

    body = movi + (b"" if idx_mode == "none" else idx1)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"AVI " + bytes(body)


def _parse(tmp_path, data, name="t.avi"):
    p = tmp_path / name
    p.write_bytes(data)
    return mosh.parse_avi_file(p, clip_id=0)


# -- idx1 tolerance -----------------------------------------------------------

def test_parse_relative_offsets(tmp_path):
    st = _parse(tmp_path, _build_avi(FRAMES, "relative"))
    assert len(st.chunks) == 4
    assert [c.is_keyframe for c in st.chunks] == [True, False, False, True]


def test_parse_absolute_offsets_no_longer_raises(tmp_path):
    # Previously raised AviParseError("Chunk offset mismatch ..."); now tolerated.
    st = _parse(tmp_path, _build_avi(FRAMES, "absolute"))
    assert [c.is_keyframe for c in st.chunks] == [True, False, False, True]


def test_parse_garbage_offsets_tolerated(tmp_path):
    st = _parse(tmp_path, _build_avi(FRAMES, "garbage"))
    assert [c.is_keyframe for c in st.chunks] == [True, False, False, True]


def test_parse_without_idx1(tmp_path):
    st = _parse(tmp_path, _build_avi(FRAMES, "none"))
    assert len(st.chunks) == 4
    assert all(not c.is_keyframe for c in st.chunks)  # no idx1 -> no keyframe info


def test_parse_short_idx1(tmp_path):
    st = _parse(tmp_path, _build_avi(FRAMES, "short"))
    assert len(st.chunks) == 4  # last chunk just lacks a flag; no crash


def test_parse_extra_idx1(tmp_path):
    st = _parse(tmp_path, _build_avi(FRAMES, "extra"))
    assert len(st.chunks) == 4  # surplus index entry ignored


def test_roundtrip_preserves_chunks_and_keyframes(tmp_path):
    src = tmp_path / "in.avi"
    src.write_bytes(_build_avi(FRAMES, "relative"))
    out = tmp_path / "out.avi"
    mosh.rewrite_avi(src, out, keep_initial_keyframes=99, duplicate_count=0, duplicate_gap=1)
    st = mosh.parse_avi_file(out, clip_id=0)
    assert len(st.chunks) == 4
    assert [c.is_keyframe for c in st.chunks] == [True, False, False, True]


# -- keep/drop precedence -----------------------------------------------------

def _kf(clip_id=0):
    return mosh.AviChunk(b"00dc", AVIIF_KEYFRAME, b"x", True, True, 0, clip_id)


def test_explicit_keep_survives_drop_first():
    chunks = [_kf(), _kf()]  # keyframe ordinals 0 and 1
    opts = {0: mosh.ClipOptions(
        keep_initial_keyframes=0, duplicate_count=0, duplicate_gap=1,
        drop_first_keyframe=True, keep_specific_keys={0},
    )}
    out = mosh.process_chunks(chunks, 0, 0, 1, clip_options=opts)
    # ordinal 0 explicitly kept despite drop_first; ordinal 1 dropped (limit 0).
    assert len(out) == 1


def test_explicit_drop_beats_explicit_keep():
    chunks = [_kf()]
    opts = {0: mosh.ClipOptions(
        keep_initial_keyframes=5, duplicate_count=0, duplicate_gap=1,
        keep_specific_keys={0}, drop_specific_keys={0},
    )}
    out = mosh.process_chunks(chunks, 0, 0, 1, clip_options=opts)
    assert len(out) == 0  # explicit drop wins over explicit keep


def test_process_chunks_aborts_cooperatively():
    chunks = [_kf() for _ in range(10)]
    with pytest.raises(mosh.MoshAborted):
        mosh.process_chunks(chunks, 5, 0, 1, should_abort=lambda: True)


def test_process_chunks_runs_when_abort_false():
    chunks = [_kf(), _kf()]
    out = mosh.process_chunks(chunks, 5, 0, 1, should_abort=lambda: False)
    assert len(out) == 2


def test_default_drop_first_unchanged_without_explicit_sets():
    chunks = [_kf(), _kf()]
    opts = {0: mosh.ClipOptions(
        keep_initial_keyframes=5, duplicate_count=0, duplicate_gap=1,
        drop_first_keyframe=True,
    )}
    out = mosh.process_chunks(chunks, 0, 0, 1, clip_options=opts)
    assert len(out) == 1  # ordinal 0 dropped by drop_first, ordinal 1 kept


# -- normalize_to_xvid error surfacing ----------------------------------------

class _Result:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


def test_normalize_surfaces_ffmpeg_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mosh.subprocess, "run",
        lambda *a, **k: _Result(1, "frame 1\nError: something broke\n"),
    )
    with pytest.raises(RuntimeError) as ei:
        mosh.normalize_to_xvid(tmp_path / "in.mp4", tmp_path / "out.avi")
    assert "something broke" in str(ei.value)


def test_normalize_detects_missing_libxvid(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mosh.subprocess, "run",
        lambda *a, **k: _Result(1, "Unknown encoder 'libxvid'\n"),
    )
    with pytest.raises(RuntimeError) as ei:
        mosh.normalize_to_xvid(tmp_path / "in.mp4", tmp_path / "out.avi")
    assert "libxvid" in str(ei.value).lower()


def test_normalize_missing_binary(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(mosh.subprocess, "run", boom)
    with pytest.raises(RuntimeError) as ei:
        mosh.normalize_to_xvid(tmp_path / "in.mp4", tmp_path / "out.avi")
    assert "not found" in str(ei.value).lower()
