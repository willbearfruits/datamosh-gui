"""Background worker that runs mosh.rewrite_avi()."""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Set

# Containers we export by re-encoding the moshed AVI (engine output is always AVI).
TRANSCODE_SUFFIXES = (".mp4", ".mov")

from PySide6.QtCore import QThread, Signal

import mosh
from gui.models.clip_model import ClipProfile


def build_clip_options(clips: list[ClipProfile]) -> Dict[int, mosh.ClipOptions]:
    """Build a ClipOptions dict from a list of ClipProfile."""
    opts: Dict[int, mosh.ClipOptions] = {}
    for idx, clip in enumerate(clips):
        keep_keys: Optional[Set[int]] = None
        drop_keys: Optional[Set[int]] = None
        if clip.keep_keys_spec:
            keep_keys = mosh.parse_keyframe_spec(clip.keep_keys_spec) or None
        if clip.drop_keys_spec:
            drop_keys = mosh.parse_keyframe_spec(clip.drop_keys_spec) or None

        # First keyframe behavior is controlled by drop_first_keyframe.
        # keep_first controls *additional* keyframes after the first boundary keyframe.
        drop_first = clip.effective_drop_first_keyframe()
        keep_extra = max(0, clip.keep_first)
        keep_limit = keep_extra + (0 if drop_first else 1)

        opts[idx] = mosh.ClipOptions(
            keep_initial_keyframes=keep_limit,
            duplicate_count=max(0, clip.duplicate_count),
            duplicate_gap=max(1, clip.duplicate_gap),
            drop_first_keyframe=drop_first,
            keep_specific_keys=keep_keys,
            drop_specific_keys=drop_keys,
        )
    return opts


def _clip_has_trim(clip: ClipProfile) -> bool:
    return clip.trim_start_frame > 0 or clip.trim_end_frame > 0


def _count_video_frames(chunks: list[mosh.AviChunk]) -> int:
    return sum(1 for c in chunks if c.is_video)


def _slice_video_chunks(
    chunks: list[mosh.AviChunk],
    start_frame: int,
    end_frame: int,
    clip_id: int,
) -> list[mosh.AviChunk]:
    """Extract [start_frame, end_frame) video chunks and retag clip_id."""
    out: list[mosh.AviChunk] = []
    video_idx = 0
    for chunk in chunks:
        if not chunk.is_video:
            continue
        if start_frame <= video_idx < end_frame:
            clone = chunk.clone()
            clone.clip_id = clip_id
            out.append(clone)
        video_idx += 1
    return out


class MoshWorker(QThread):
    """Run rewrite_avi in a background thread."""

    finished_ok = Signal(str)   # output_path
    error = Signal(str)         # error message

    def __init__(
        self,
        clips: list[ClipProfile],
        output_path: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._clips = clips
        self._output = output_path
        self._abort = False

    def abort(self) -> None:
        """Request cooperative cancellation; rewrite stops at the next chunk check."""
        self._abort = True

    def run(self) -> None:
        try:
            if not self._clips:
                self.error.emit("No clips are ready for moshing.")
                return

            ready = [c for c in self._clips if c.is_ready()]
            if not ready:
                self.error.emit("No clips are ready for moshing.")
                return
            if len(ready) != len(self._clips):
                self.error.emit("Some clips are not ready for moshing yet.")
                return

            base = ready[0]
            extras = ready[1:]
            clip_opts = build_clip_options(ready)

            # The engine only writes AVI; for MP4/MOV we mosh to a temp AVI then
            # transcode (re-encoding the glitched frames into a clean shareable file).
            transcode = self._output.suffix.lower() in TRANSCODE_SUFFIXES
            tmp_dir: Optional[Path] = None
            avi_target = self._output
            if transcode:
                tmp_dir = Path(tempfile.mkdtemp(prefix="datamosh-export-"))
                avi_target = tmp_dir / "moshed.avi"

            try:
                if any(_clip_has_trim(c) for c in ready):
                    self._rewrite_with_trims(ready, clip_opts, avi_target)
                else:
                    mosh.rewrite_avi(
                        base.normalized_path,
                        avi_target,
                        keep_initial_keyframes=clip_opts[0].keep_initial_keyframes,
                        duplicate_count=clip_opts[0].duplicate_count,
                        duplicate_gap=clip_opts[0].duplicate_gap,
                        extra_inputs=[c.normalized_path for c in extras],
                        keep_key_indices=None,
                        drop_key_indices=None,
                        clip_options=clip_opts,
                        drop_appended_first=False,
                        should_abort=lambda: self._abort,
                    )
                if self._abort:
                    return
                if transcode:
                    self._transcode(avi_target, self._output)
            finally:
                if tmp_dir is not None:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            self.finished_ok.emit(str(self._output))

        except mosh.MoshAborted:
            return  # superseded/cancelled — emit nothing
        except struct.error as exc:
            # mosh.py packs the movi/RIFF sizes as unsigned 32-bit; a very large
            # mosh (high duplicate count or long clips) overflows that and raises a
            # cryptic struct.error ("'I' format requires 0 <= number <= ..."). The
            # engine is treated as untouched, so translate that case here. A
            # struct.error can also come from parsing a truncated/corrupt AVI
            # (unpack_from), so only the integer-overflow signature maps to the
            # size-limit message; anything else is reported as-is.
            msg = str(exc).lower()
            if "format requires" in msg or "argument out of range" in msg or "requires 0 <=" in msg:
                self.error.emit(
                    "Output is too large for the AVI format (~4 GB limit). Reduce the "
                    "duplicate count, increase the duplicate gap, or shorten the clips."
                )
            else:
                self.error.emit(f"Failed to read or write video data: {exc}")
        except Exception as exc:
            self.error.emit(str(exc))

    def _rewrite_with_trims(
        self,
        clips: list[ClipProfile],
        clip_opts: Dict[int, mosh.ClipOptions],
        output: Path,
    ) -> None:
        """Rewrite using timeline segment trims without re-encoding."""
        parsed_cache: dict[Path, mosh.AviStructure] = {}
        all_chunks: list[mosh.AviChunk] = []
        base_struct: Optional[mosh.AviStructure] = None

        for clip_idx, clip in enumerate(clips):
            if not clip.normalized_path:
                raise RuntimeError("Clip has no normalized path")

            src = clip.normalized_path
            if src not in parsed_cache:
                parsed_cache[src] = mosh.parse_avi_file(src, clip_id=0)
            parsed = parsed_cache[src]
            if base_struct is None:
                base_struct = parsed

            total = _count_video_frames(parsed.chunks)
            if total <= 0:
                raise RuntimeError(f"No video frames found in {src}")

            start = max(0, clip.trim_start_frame)
            end = clip.trim_end_frame if clip.trim_end_frame > 0 else total
            end = max(start + 1, min(end, total))

            segment = _slice_video_chunks(parsed.chunks, start, end, clip_idx)
            if not segment:
                raise RuntimeError(f"Trim produced an empty segment for {src}")
            all_chunks.extend(segment)

        if base_struct is None:
            raise RuntimeError("No base clip available for output header")

        first = clip_opts[0]
        processed = mosh.process_chunks(
            all_chunks,
            keep_initial_keyframes=first.keep_initial_keyframes,
            duplicate_count=first.duplicate_count,
            duplicate_gap=first.duplicate_gap,
            keep_key_indices=None,
            drop_key_indices=None,
            clip_options=clip_opts,
            drop_appended_first=False,
            should_abort=lambda: self._abort,
        )
        movi_chunk, idx_chunk, video_frames = mosh.build_movi_and_index(processed)

        prefix = bytearray(base_struct.prefix)
        header_offsets = mosh.find_header_offsets(prefix)
        mosh.update_header_counts(prefix, header_offsets, video_frames)

        rebuilt = bytearray()
        rebuilt += prefix
        rebuilt += movi_chunk
        rebuilt += base_struct.between
        rebuilt += idx_chunk
        rebuilt += base_struct.suffix
        mosh.pack_le_uint(rebuilt, 4, len(rebuilt) - 8)

        output.write_bytes(bytes(rebuilt))

    def _transcode(self, src_avi: Path, dst: Path) -> None:
        """Re-encode the moshed AVI into the container implied by dst's suffix.

        Decoding the broken-prediction AVI yields the glitched frames, which we
        re-encode cleanly to H.264 so the export plays anywhere.
        """
        cmd = [
            "ffmpeg", "-y", "-i", str(src_avi),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
            str(dst),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg not found on PATH; cannot export to this format.") from exc
        if result.returncode != 0:
            tail = "\n".join((result.stderr or "").strip().splitlines()[-6:])
            raise RuntimeError(
                f"Export transcode failed (ffmpeg exit {result.returncode})."
                + (f"\n\n{tail}" if tail else "")
            )
