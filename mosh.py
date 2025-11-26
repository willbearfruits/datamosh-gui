#!/usr/bin/env python3
"""
Datamosh helper that removes I-frames and optionally duplicates P-frames
inside classic MPEG4-in-AVI bitstreams. The tool works directly on the
compressed payload, so the resulting glitches come from broken prediction
rather than from a post effect.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set


class AviParseError(Exception):
    """Raised when the source AVI does not match expectations."""


@dataclass
class AviChunk:
    """Single chunk inside the LIST movi section."""

    chunk_id: bytes
    flags: int
    data: bytes
    is_video: bool
    is_keyframe: bool
    stream_id: Optional[int]
    clip_id: int

    def clone(self) -> "AviChunk":
        # Data are immutable bytes, so shallow copy is fine.
        return AviChunk(
            chunk_id=self.chunk_id,
            flags=self.flags,
            data=self.data,
            is_video=self.is_video,
            is_keyframe=self.is_keyframe,
            stream_id=self.stream_id,
            clip_id=self.clip_id,
        )


@dataclass
class AviHeaderOffsets:
    total_frames: Optional[int]
    video_stream_length: Optional[int]
    odml_total_frames: List[int]


@dataclass
class AviStructure:
    """Breakdown of an AVI file ready to be rebuilt."""

    prefix: bytearray
    between: bytes
    suffix: bytes
    chunks: List[AviChunk]


@dataclass
class ClipOptions:
    keep_initial_keyframes: int
    duplicate_count: int
    duplicate_gap: int
    drop_first_keyframe: bool = False
    keep_specific_keys: Optional[Set[int]] = None
    drop_specific_keys: Optional[Set[int]] = None


# AVI index flag for keyframes.
AVIIF_KEYFRAME = 0x00000010

# Normalisation presets tuned for datamoshing.
NORMALIZE_PRESETS = {
    "fast": {"width": 960, "qscale": 4, "gop": 60, "keep_audio": True},
    "balanced": {"width": 1280, "qscale": 3, "gop": 48, "keep_audio": True},
    "sharp": {"width": 1920, "qscale": 2, "gop": 36, "keep_audio": True},
}


def read_le_uint(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def pack_le_uint(buffer: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", buffer, offset, value)


def locate_chunks(data: bytes) -> tuple[int, int, int, int]:
    """
    Locate the LIST movi and idx1 chunks.

    Returns:
        (movi_pos, movi_size, idx1_pos, idx1_size)
    """
    pos = 12  # Skip RIFF header.
    movi_pos = movi_size = idx1_pos = idx1_size = None  # type: ignore
    length = len(data)

    while pos + 8 <= length:
        chunk_id = data[pos : pos + 4]
        chunk_size = read_le_uint(data, pos + 4)
        chunk_end = pos + 8 + chunk_size
        if chunk_size % 2 == 1:
            chunk_end += 1

        if chunk_id == b"LIST":
            if pos + 12 > length:
                raise AviParseError("Corrupted LIST chunk header")
            list_type = data[pos + 8 : pos + 12]
            if list_type == b"movi":
                movi_pos, movi_size = pos, chunk_size
        elif chunk_id == b"idx1":
            idx1_pos, idx1_size = pos, chunk_size

        if movi_pos is not None and idx1_pos is not None:
            break

        pos = chunk_end

    if movi_pos is None:
        raise AviParseError("LIST movi chunk not found")
    if idx1_pos is None:
        raise AviParseError("idx1 chunk not found")

    return movi_pos, movi_size, idx1_pos, idx1_size


def parse_idx1(data: bytes, idx1_pos: int, idx1_size: int) -> List[tuple[bytes, int, int, int]]:
    entries: List[tuple[bytes, int, int, int]] = []
    pos = idx1_pos + 8
    end = pos + idx1_size
    while pos + 16 <= end:
        chunk_id = data[pos : pos + 4]
        flags = read_le_uint(data, pos + 4)
        offset = read_le_uint(data, pos + 8)
        size = read_le_uint(data, pos + 12)
        entries.append((chunk_id, flags, offset, size))
        pos += 16
    if pos != end:
        raise AviParseError("idx1 chunk has trailing bytes")
    return entries


def _parse_stream_id(chunk_id: bytes) -> Optional[int]:
    try:
        prefix = chunk_id[:2].decode("ascii")
    except UnicodeDecodeError:
        return None
    return int(prefix) if prefix.isdigit() else None


def parse_movi_chunks(
    movi_payload: bytes,
    idx_entries: Sequence[tuple[bytes, int, int, int]],
    clip_id: int,
) -> List[AviChunk]:
    chunks: List[AviChunk] = []
    pos = 0
    entry_idx = 0
    payload_len = len(movi_payload)
    while pos + 8 <= payload_len:
        chunk_id = movi_payload[pos : pos + 4]
        if chunk_id == b"LIST":
            list_type = movi_payload[pos + 8 : pos + 12] if pos + 12 <= payload_len else b""
            raise AviParseError(
                f"Nested LIST chunk ({list_type.decode('ascii', 'ignore')}) "
                "inside movi is not supported by this tool."
            )
        chunk_size = read_le_uint(movi_payload, pos + 4)
        chunk_data_start = pos + 8
        chunk_data_end = chunk_data_start + chunk_size

        if chunk_data_end > payload_len:
            raise AviParseError("Chunk exceeds movi payload size")
        if entry_idx >= len(idx_entries):
            raise AviParseError("idx1 has fewer entries than movi chunks")

        idx_chunk_id, flags, offset, size_from_idx = idx_entries[entry_idx]
        # Validate metadata matches the index.
        if idx_chunk_id != chunk_id:
            raise AviParseError("movi chunk order does not match idx1")
        if size_from_idx != chunk_size:
            raise AviParseError("Chunk size mismatch between movi and idx1")
        # idx1 offsets are measured from the start of the LIST movi chunk header
        # plus four bytes for the 'movi' tag. Given pos is measured from the start
        # of the movi payload, the expected offset is pos + 4.
        expected_offset = pos + 4
        if offset != expected_offset:
            raise AviParseError("Chunk offset mismatch between movi and idx1")

        chunk_data = movi_payload[chunk_data_start:chunk_data_end]
        stream_id = _parse_stream_id(chunk_id)
        suffix = chunk_id[2:]
        is_video = suffix in (b"dc", b"db") and stream_id is not None
        is_keyframe = bool(flags & AVIIF_KEYFRAME) and is_video

        chunks.append(
            AviChunk(
                chunk_id=chunk_id,
                flags=flags,
                data=bytes(chunk_data),
                is_video=is_video,
                is_keyframe=is_keyframe,
                stream_id=stream_id,
                clip_id=clip_id,
            )
        )

        entry_idx += 1
        pos = chunk_data_end
        if chunk_size % 2 == 1:
            pos += 1  # Skip padding byte.

    if entry_idx != len(idx_entries):
        raise AviParseError("idx1 contains extra entries after parsing movi")

    return chunks


def parse_avi_file(path: Path, clip_id: int) -> AviStructure:
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"AVI ":
        raise AviParseError(f"{path} is not a RIFF AVI file")

    movi_pos, movi_size, idx1_pos, idx1_size = locate_chunks(data)
    movi_payload = data[movi_pos + 12 : movi_pos + 8 + movi_size]
    idx_entries = parse_idx1(data, idx1_pos, idx1_size)
    chunks = parse_movi_chunks(movi_payload, idx_entries, clip_id=clip_id)

    prefix = bytearray(data[:movi_pos])
    between = data[movi_pos + 8 + movi_size : idx1_pos]
    suffix = data[idx1_pos + 8 + idx1_size :]
    return AviStructure(prefix=prefix, between=between, suffix=suffix, chunks=chunks)


def find_header_offsets(prefix: bytes) -> AviHeaderOffsets:
    total_frames_offset: Optional[int] = None
    video_stream_length_offset: Optional[int] = None
    odml_offsets: List[int] = []

    pos = 12  # Skip RIFF header.
    prefix_len = len(prefix)
    while pos + 8 <= prefix_len:
        chunk_id = prefix[pos : pos + 4]
        chunk_size = read_le_uint(prefix, pos + 4)
        chunk_end = pos + 8 + chunk_size
        if chunk_size % 2 == 1:
            chunk_end += 1

        if chunk_id == b"LIST":
            if pos + 12 > prefix_len:
                break
            list_type = prefix[pos + 8 : pos + 12]
            if list_type == b"hdrl":
                total_frames_offset, video_stream_length_offset = _parse_hdrl_for_offsets(
                    prefix,
                    pos + 12,
                    pos + 8 + chunk_size,
                    total_frames_offset,
                    video_stream_length_offset,
                    odml_offsets,
                )
        pos = chunk_end

    return AviHeaderOffsets(
        total_frames=total_frames_offset,
        video_stream_length=video_stream_length_offset,
        odml_total_frames=odml_offsets,
    )


def _parse_hdrl_for_offsets(
    data: bytes,
    start: int,
    end: int,
    total_frames_offset: Optional[int],
    video_stream_length_offset: Optional[int],
    odml_offsets: List[int],
) -> tuple[Optional[int], Optional[int]]:
    pos = start
    while pos + 8 <= end:
        chunk_id = data[pos : pos + 4]
        chunk_size = read_le_uint(data, pos + 4)
        chunk_end = pos + 8 + chunk_size
        if chunk_size % 2 == 1:
            chunk_end += 1

        if chunk_id == b"avih" and total_frames_offset is None:
            total_frames_offset = pos + 8 + 16  # dwTotalFrames inside MainAVIHeader.
        elif chunk_id == b"LIST":
            sub_type = data[pos + 8 : pos + 12]
            if sub_type == b"strl" and video_stream_length_offset is None:
                video_stream_length_offset = _find_video_stream_length(data, pos + 12, pos + 8 + chunk_size)
            elif sub_type == b"odml":
                _collect_odml_offsets(data, pos + 12, pos + 8 + chunk_size, odml_offsets)

        pos = chunk_end

    return total_frames_offset, video_stream_length_offset


def _find_video_stream_length(data: bytes, start: int, end: int) -> Optional[int]:
    pos = start
    while pos + 8 <= end:
        chunk_id = data[pos : pos + 4]
        chunk_size = read_le_uint(data, pos + 4)
        chunk_end = pos + 8 + chunk_size
        if chunk_size % 2 == 1:
            chunk_end += 1

        if chunk_id == b"strh":
            fcc_type = data[pos + 8 : pos + 12]
            if fcc_type == b"vids":
                return pos + 8 + 32  # dwLength field inside AVIStreamHeader.

        pos = chunk_end

    return None


def _collect_odml_offsets(data: bytes, start: int, end: int, collector: List[int]) -> None:
    pos = start
    while pos + 8 <= end:
        chunk_id = data[pos : pos + 4]
        chunk_size = read_le_uint(data, pos + 4)
        chunk_end = pos + 8 + chunk_size
        if chunk_size % 2 == 1:
            chunk_end += 1

        if chunk_id == b"dmlh":
            collector.append(pos + 8)  # dwTotalFrames in the dmlh header.

        pos = chunk_end


def process_chunks(
    chunks: Sequence[AviChunk],
    keep_initial_keyframes: int,
    duplicate_count: int,
    duplicate_gap: int,
    keep_key_indices: Optional[Set[int]] = None,
    drop_key_indices: Optional[Set[int]] = None,
    clip_options: Optional[Dict[int, ClipOptions]] = None,
    drop_appended_first: bool = True,
) -> List[AviChunk]:
    if duplicate_count < 0:
        raise ValueError("duplicate_count must be >= 0")
    if duplicate_gap <= 0:
        raise ValueError("duplicate_gap must be >= 1")

    processed: List[AviChunk] = []
    global_key_index = 0
    per_clip_key_index = defaultdict(int)
    per_clip_keys_kept = defaultdict(int)
    per_clip_p_counter = defaultdict(int)

    for chunk in chunks:
        if not chunk.is_video:
            processed.append(chunk.clone())
            continue

        clip_id = chunk.clip_id
        options = clip_options.get(clip_id) if clip_options else None
        clip_keep_limit = options.keep_initial_keyframes if options else keep_initial_keyframes
        clip_dup_count = options.duplicate_count if options else duplicate_count
        clip_dup_gap = options.duplicate_gap if options else duplicate_gap
        clip_drop_first = options.drop_first_keyframe if options else (drop_appended_first and clip_id != 0)
        clip_keep_set = options.keep_specific_keys if options else None
        clip_drop_set = options.drop_specific_keys if options else None

        if clip_dup_count < 0:
            raise ValueError("duplicate_count must be >= 0")
        if clip_dup_gap <= 0:
            raise ValueError("duplicate_gap must be >= 1")

        if chunk.is_keyframe:
            clip_key_index = per_clip_key_index[clip_id]
            keep = True

            if clip_drop_first and clip_key_index == 0:
                keep = False
            elif clip_drop_set is not None and clip_key_index in clip_drop_set:
                keep = False
            elif drop_key_indices is not None and global_key_index in drop_key_indices:
                keep = False
            elif clip_keep_set is not None and clip_key_index in clip_keep_set:
                keep = True
            elif keep_key_indices is not None and global_key_index in keep_key_indices:
                keep = True
            elif per_clip_keys_kept[clip_id] >= clip_keep_limit:
                keep = False

            if keep:
                processed.append(chunk.clone())
                per_clip_keys_kept[clip_id] += 1

            per_clip_key_index[clip_id] += 1
            global_key_index += 1
            # Drop subsequent keyframes outright.
            continue

        per_clip_p_counter[clip_id] += 1
        processed.append(chunk.clone())

        if clip_dup_count > 0 and (per_clip_p_counter[clip_id] % clip_dup_gap == 0):
            for _ in range(clip_dup_count):
                clone = chunk.clone()
                # Enforce non-keyframe flag for safety.
                clone.flags &= ~AVIIF_KEYFRAME
                clone.is_keyframe = False
                processed.append(clone)

    return processed


def build_movi_and_index(
    chunks: Sequence[AviChunk],
) -> tuple[bytes, bytes, int]:
    movi_payload = bytearray()
    idx_payload = bytearray()
    offset = 4  # Account for the 'movi' fourcc preceding the payload.
    video_frames = 0

    for chunk in chunks:
        data = chunk.data
        size = len(data)
        movi_payload += chunk.chunk_id
        movi_payload += struct.pack("<I", size)
        movi_payload += data
        if size % 2 == 1:
            movi_payload += b"\x00"

        idx_payload += chunk.chunk_id
        idx_payload += struct.pack("<I", chunk.flags)
        idx_payload += struct.pack("<I", offset)
        idx_payload += struct.pack("<I", size)

        offset += 8 + size + (size % 2)
        if chunk.is_video:
            video_frames += 1

    movi_chunk = (
        b"LIST"
        + struct.pack("<I", 4 + len(movi_payload))
        + b"movi"
        + bytes(movi_payload)
    )
    idx_chunk = b"idx1" + struct.pack("<I", len(idx_payload)) + bytes(idx_payload)
    return movi_chunk, idx_chunk, video_frames


def update_header_counts(prefix: bytearray, offsets: AviHeaderOffsets, total_frames: int) -> None:
    if offsets.total_frames is not None:
        pack_le_uint(prefix, offsets.total_frames, total_frames)
    if offsets.video_stream_length is not None:
        pack_le_uint(prefix, offsets.video_stream_length, total_frames)
    for off in offsets.odml_total_frames:
        pack_le_uint(prefix, off, total_frames)


def normalize_to_xvid(
    src: Path,
    dst: Path,
    ffmpeg_bin: str = "ffmpeg",
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    qscale: int = 3,
    gop: int = 48,
    keep_audio: bool = True,
) -> None:
    """
    Convert arbitrary footage into a datamosh-friendly Xvid AVI.
    """
    if qscale < 1:
        raise ValueError("qscale must be >= 1")
    if gop < 1:
        raise ValueError("gop must be >= 1")

    def _even(value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        return max(2, (value // 2) * 2)

    width = _even(width)
    height = _even(height)

    scale_filter: Optional[str] = None
    if width and height:
        # keep aspect ratio inside requested box, pad with black if needed
        scale_filter = (
            f"scale={width}:{height}:flags=lanczos:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )
    elif width:
        scale_filter = f"scale={width}:-2:flags=lanczos"
    elif height:
        scale_filter = f"scale=-2:{height}:flags=lanczos"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(src),
        "-c:v",
        "libxvid",
        "-qscale:v",
        str(qscale),
        "-g",
        str(gop),
        "-bf",
        "0",
        "-pix_fmt",
        "yuv420p",
    ]
    if scale_filter:
        cmd.extend(["-vf", scale_filter])
    if keep_audio:
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.append("-an")
    cmd.append(str(dst))

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:  # pragma: no cover - CLI error path.
        raise RuntimeError("ffmpeg binary not found on PATH") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover - CLI error path.
        raise RuntimeError(f"ffmpeg failed with exit code {exc.returncode}") from exc


def rewrite_avi(
    source_path: Path,
    output_path: Path,
    keep_initial_keyframes: int,
    duplicate_count: int,
    duplicate_gap: int,
    extra_inputs: Sequence[Path] = (),
    keep_key_indices: Optional[Set[int]] = None,
    drop_key_indices: Optional[Set[int]] = None,
    clip_options: Optional[Dict[int, ClipOptions]] = None,
    drop_appended_first: bool = True,
) -> None:
    base = parse_avi_file(source_path, clip_id=0)

    all_chunks: List[AviChunk] = list(base.chunks)
    for clip_index, extra_path in enumerate(extra_inputs, start=1):
        extra = parse_avi_file(extra_path, clip_id=clip_index)
        all_chunks.extend(extra.chunks)

    processed_chunks = process_chunks(
        all_chunks,
        keep_initial_keyframes,
        duplicate_count,
        duplicate_gap,
        keep_key_indices=keep_key_indices,
        drop_key_indices=drop_key_indices,
        clip_options=clip_options,
        drop_appended_first=drop_appended_first,
    )
    movi_chunk, idx_chunk, video_frames = build_movi_and_index(processed_chunks)

    header_offsets = find_header_offsets(base.prefix)
    update_header_counts(base.prefix, header_offsets, video_frames)

    rebuilt = bytearray()
    rebuilt += base.prefix
    rebuilt += movi_chunk
    rebuilt += base.between
    rebuilt += idx_chunk
    rebuilt += base.suffix

    pack_le_uint(rebuilt, 4, len(rebuilt) - 8)  # Update RIFF size.

    output_path.write_bytes(bytes(rebuilt))


def ensure_xvid_avi(src: Path, dst: Path, ffmpeg_bin: str = "ffmpeg") -> None:
    """
    Convert arbitrary input into an Xvid AVI ready for moshing.
    """
    normalize_to_xvid(src, dst, ffmpeg_bin=ffmpeg_bin)


def parse_keyframe_spec(spec: str) -> Set[int]:
    """
    Parse comma-separated keyframe indices or ranges (e.g. '0,5,10-12').
    """
    result: Set[int] = set()
    if not spec:
        return result
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            try:
                start = int(start_str, 10)
                end = int(end_str, 10)
            except ValueError as exc:
                raise ValueError(f"Invalid keyframe range '{part}'") from exc
            if end < start:
                raise ValueError(f"Range end before start in '{part}'")
            result.update(range(start, end + 1))
        else:
            try:
                result.add(int(part, 10))
            except ValueError as exc:
                raise ValueError(f"Invalid keyframe index '{part}'") from exc
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create datamoshed AVI clips by removing I-frames and multiplying P-frames.",
    )
    parser.add_argument("input", type=Path, help="Source AVI file (preferably Xvid/DivX encoded).")
    parser.add_argument("output", type=Path, help="Destination AVI file.")
    parser.add_argument(
        "--keep-first",
        type=int,
        default=1,
        help="Number of leading video keyframes to keep (default: 1).",
    )
    parser.add_argument(
        "--duplicate-count",
        type=int,
        default=0,
        help="How many extra copies to insert for selected P-frames (default: 0).",
    )
    parser.add_argument(
        "--duplicate-gap",
        type=int,
        default=1,
        help="Duplicate every Nth P-frame (default: 1 = duplicate all).",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Automatically convert non-AVI sources into a temporary Xvid AVI via ffmpeg.",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help="Path to ffmpeg binary used during --prepare (default: ffmpeg).",
    )
    parser.add_argument(
        "--append",
        action="append",
        type=Path,
        default=[],
        help="Additional AVI clips to append after the main input (can be repeated).",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Transcode all inputs to datamosh-friendly Xvid using optional scaling parameters.",
    )
    parser.add_argument(
        "--normalize-preset",
        choices=sorted(NORMALIZE_PRESETS.keys()),
        default="balanced",
        help="Preset used when --normalize is enabled (default: balanced).",
    )
    parser.add_argument(
        "--norm-width",
        type=int,
        default=None,
        help="Target width when using --normalize (maintains aspect ratio).",
    )
    parser.add_argument(
        "--norm-height",
        type=int,
        default=None,
        help="Target height when using --normalize (maintains aspect ratio).",
    )
    parser.add_argument(
        "--norm-qscale",
        type=int,
        default=0,
        help="Xvid quality factor when using --normalize (0 = preset default).",
    )
    parser.add_argument(
        "--norm-gop",
        type=int,
        default=0,
        help="GOP length when using --normalize (0 = preset default).",
    )
    parser.add_argument(
        "--normalize-drop-audio",
        action="store_true",
        help="Strip audio tracks during normalization for pure video glitches.",
    )
    parser.add_argument(
        "--keep-keys",
        default="",
        help="Comma-separated list or ranges of keyframe indices to force-keep (e.g. '0,15,20-22').",
    )
    parser.add_argument(
        "--drop-keys",
        default="",
        help="Comma-separated list or ranges of keyframe indices to force-drop.",
    )
    parser.add_argument(
        "--keep-appended-first",
        action="store_true",
        help="Preserve the first keyframe for appended clips instead of dropping it automatically.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    cleanup_files: List[Path] = []
    cleanup_dirs: List[Path] = []

    if args.norm_width is not None:
        if args.norm_width <= 0 or args.norm_width % 2 != 0:
            print("Error: --norm-width must be a positive, even integer.", file=sys.stderr)
            return 1
    if args.norm_height is not None:
        if args.norm_height <= 0 or args.norm_height % 2 != 0:
            print("Error: --norm-height must be a positive, even integer.", file=sys.stderr)
            return 1
    if args.norm_qscale < 0:
        print("Error: --norm-qscale must be >= 0.", file=sys.stderr)
        return 1
    if args.norm_gop < 0:
        print("Error: --norm-gop must be >= 0.", file=sys.stderr)
        return 1

    def prepare_path(path: Path, role: str) -> Path:
        suffix = path.suffix.lower()
        need_normalize = args.normalize
        need_prepare = args.prepare and suffix != ".avi"

        if not need_normalize and not need_prepare:
            if suffix != ".avi":
                print(
                    f"Warning: '{path}' is not an AVI. Convert to Xvid AVI first or pass --prepare/--normalize.",
                    file=sys.stderr,
                )
            return path

        tmp_dir = Path(tempfile.mkdtemp(prefix=f"moshprep-{role}-"))
        cleanup_dirs.append(tmp_dir)
        temp_path = tmp_dir / f"{path.stem}_{role}_mosh.avi"

        try:
            if need_normalize:
                preset = NORMALIZE_PRESETS[args.normalize_preset]
                norm_width = args.norm_width if args.norm_width is not None else preset["width"]
                norm_height = args.norm_height
                norm_qscale = args.norm_qscale if args.norm_qscale else preset["qscale"]
                norm_gop = args.norm_gop if args.norm_gop else preset["gop"]
                keep_audio = False if args.normalize_drop_audio else preset["keep_audio"]

                normalize_to_xvid(
                    path,
                    temp_path,
                    ffmpeg_bin=args.ffmpeg_bin,
                    width=norm_width,
                    height=norm_height,
                    qscale=norm_qscale,
                    gop=norm_gop,
                    keep_audio=keep_audio,
                )
            else:
                ensure_xvid_avi(path, temp_path, ffmpeg_bin=args.ffmpeg_bin)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise

        cleanup_files.append(temp_path)
        return temp_path

    try:
        source_path = prepare_path(args.input, role="base")
        append_paths = [prepare_path(extra, role=f"append{idx}") for idx, extra in enumerate(args.append, start=1)]
    except RuntimeError:
        return 1

    try:
        keep_keys = parse_keyframe_spec(args.keep_keys) if args.keep_keys else set()
        drop_keys = parse_keyframe_spec(args.drop_keys) if args.drop_keys else set()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    keep_keys_opt: Optional[Set[int]] = keep_keys or None
    drop_keys_opt: Optional[Set[int]] = drop_keys or None
    drop_appended_first = not args.keep_appended_first

    try:
        rewrite_avi(
            source_path,
            args.output,
            keep_initial_keyframes=args.keep_first,
            duplicate_count=args.duplicate_count,
            duplicate_gap=args.duplicate_gap,
            extra_inputs=append_paths,
            keep_key_indices=keep_keys_opt,
            drop_key_indices=drop_keys_opt,
            clip_options=None,
            drop_appended_first=drop_appended_first,
        )
    finally:
        for temp in cleanup_files:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        for directory in reversed(cleanup_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
