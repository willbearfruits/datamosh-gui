#!/usr/bin/env python3
"""
Interactive Tk GUI for the datamosh helper.

It normalises each clip into a datamosh-friendly Xvid AVI, lets you customise
per-clip keyframe handling, and provides an inline preview window that streams
frames directly out of ffmpeg so you can audition glitches before exporting.
"""

from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# Configure module logger
logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageTk  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    Image = ImageTk = None  # type: ignore

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
    HAS_DND = True
except ImportError:  # pragma: no cover - optional dependency
    TkinterDnD = tk.Tk  # type: ignore
    DND_FILES = None  # type: ignore
    HAS_DND = False

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore

import mosh
import shortcuts
from video_preview import VideoPreviewWidget
from timeline import TimelineWidget


@dataclass
class ClipProfile:
    role: str  # "base" or "append{n}"
    source_path: Path
    normalized_path: Path
    temp_dir: Optional[Path]
    keep_first: int = 1
    duplicate_count: int = 0
    duplicate_gap: int = 1
    drop_first_keyframe: bool = False
    keep_keys_spec: str = ""
    drop_keys_spec: str = ""
    norm_width: Optional[int] = None
    norm_height: Optional[int] = None
    norm_qscale: int = 3
    norm_gop: int = 48
    keep_audio: bool = True
    transcode: bool = True
    preset_name: str = "Balanced"
    preset_key: Optional[str] = "balanced"

    def label(self) -> str:
        return self.source_path.name

    def resolution_hint(self) -> str:
        if not self.transcode:
            return "original"
        if self.norm_width and self.norm_height:
            return f"{self.norm_width}x{self.norm_height}"
        if self.norm_width:
            return f"{self.norm_width}xauto"
        if self.norm_height:
            return f"auto x{self.norm_height}"
        return "preset"


GUI_PRESETS = {
    "Fast": {"width": 960, "qscale": 4, "gop": 60, "keep_audio": True, "key": "fast"},
    "Balanced": {"width": 1280, "qscale": 3, "gop": 48, "keep_audio": True, "key": "balanced"},
    "Sharp": {"width": 1920, "qscale": 2, "gop": 36, "keep_audio": True, "key": "sharp"},
    "Custom": None,
    "Original": None,
}


class NormalizationDialog(simpledialog.Dialog):
    """Small dialog that asks how to normalise a clip for moshing."""

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        initial_settings: Dict[str, object],
    ) -> None:
        self._initial = initial_settings
        self.result: Optional[Dict[str, object]] = None
        super().__init__(parent, title)

    def body(self, master: tk.Widget) -> tk.Widget:
        tk.Label(master, text="Preset:").grid(row=0, column=0, sticky="w")
        self.preset_choice = tk.StringVar(value=self._initial.get("preset", "Balanced"))
        preset_menu = ttk.Combobox(master, textvariable=self.preset_choice, values=list(GUI_PRESETS.keys()), state="readonly", width=12)
        preset_menu.grid(row=0, column=1, columnspan=2, sticky="w")
        preset_menu.bind("<<ComboboxSelected>>", self._on_preset_change)

        tk.Label(master, text="Target width:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.width_var = tk.StringVar(value=str(self._initial.get("width", "")) if self._initial.get("width") else "")
        self.width_entry = ttk.Entry(master, textvariable=self.width_var, width=10)
        self.width_entry.grid(row=1, column=1, sticky="w", pady=(6, 0))

        tk.Label(master, text="Quality (qscale):").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.qscale_var = tk.IntVar(value=int(self._initial.get("qscale", 3)))
        self.qscale_spin = ttk.Spinbox(master, from_=1, to=10, textvariable=self.qscale_var, width=6)
        self.qscale_spin.grid(row=2, column=1, sticky="w", pady=(6, 0))

        tk.Label(master, text="GOP length:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.gop_var = tk.IntVar(value=int(self._initial.get("gop", 48)))
        self.gop_spin = ttk.Spinbox(master, from_=12, to=240, increment=6, textvariable=self.gop_var, width=6)
        self.gop_spin.grid(row=3, column=1, sticky="w", pady=(6, 0))

        self.keep_audio_var = tk.BooleanVar(value=bool(self._initial.get("keep_audio", True)))
        self.keep_audio_check = ttk.Checkbutton(master, text="Keep original audio", variable=self.keep_audio_var)
        self.keep_audio_check.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        master.grid_columnconfigure(2, weight=1)
        self._apply_preset_defaults()
        return preset_menu

    def _on_preset_change(self, _event: object) -> None:
        self._apply_preset_defaults()

    def _apply_preset_defaults(self) -> None:
        preset_name = self.preset_choice.get()
        preset = GUI_PRESETS.get(preset_name)
        if preset is None:
            if preset_name == "Original":
                self.width_var.set("")
                self.width_entry.configure(state=tk.DISABLED)
                self.qscale_spin.configure(state=tk.DISABLED)
                self.gop_spin.configure(state=tk.DISABLED)
                self.keep_audio_check.configure(state=tk.DISABLED)
                self.keep_audio_var.set(True)
            else:
                self.width_entry.configure(state=tk.NORMAL)
                self.qscale_spin.configure(state=tk.NORMAL)
                self.gop_spin.configure(state=tk.NORMAL)
                self.keep_audio_check.configure(state=tk.NORMAL)
        else:
            self.width_var.set(str(preset["width"]))
            self.qscale_var.set(preset["qscale"])
            self.gop_var.set(preset["gop"])
            self.keep_audio_var.set(preset["keep_audio"])
            self.width_entry.configure(state=tk.DISABLED)
            self.qscale_spin.configure(state=tk.NORMAL)
            self.gop_spin.configure(state=tk.NORMAL)
            self.keep_audio_check.configure(state=tk.NORMAL)
        if preset_name not in ("Custom", "Original"):
            self.width_entry.configure(state=tk.DISABLED)
        elif preset_name == "Custom":
            self.width_entry.configure(state=tk.NORMAL)
            self.qscale_spin.configure(state=tk.NORMAL)
            self.gop_spin.configure(state=tk.NORMAL)
            self.keep_audio_check.configure(state=tk.NORMAL)

    def validate(self) -> bool:
        preset_name = self.preset_choice.get()
        if preset_name == "Original":
            return True
        if preset_name == "Custom":
            value = self.width_var.get().strip()
            if not value:
                messagebox.showerror("Normalise Clip", "Enter a target width for the custom option.", parent=self)
                return False
            try:
                width = int(value)
            except ValueError:
                messagebox.showerror("Normalise Clip", "Custom width must be numeric.", parent=self)
                return False
            if width <= 0 or width % 2 != 0:
                messagebox.showerror("Normalise Clip", "Custom width must be a positive, even integer.", parent=self)
                return False
        if self.qscale_var.get() < 1:
            messagebox.showerror("Normalise Clip", "Quality must be at least 1.", parent=self)
            return False
        if self.gop_var.get() < 1:
            messagebox.showerror("Normalise Clip", "GOP length must be at least 1.", parent=self)
            return False
        return True

    def apply(self) -> None:
        preset_name = self.preset_choice.get()
        if preset_name == "Original":
            self.result = {"transcode": False, "preset": preset_name, "preset_key": None}
            return

        width_value = self.width_var.get().strip()
        preset = GUI_PRESETS.get(preset_name)
        if isinstance(preset, dict) and preset_name != "Custom":
            width = preset["width"]
        else:
            width = int(width_value) if width_value else None
        preset_key = preset["key"] if preset and "key" in preset else None
        self.result = {
            "transcode": True,
            "width": width,
            "height": None,
            "qscale": self.qscale_var.get(),
            "gop": self.gop_var.get(),
            "keep_audio": self.keep_audio_var.get(),
            "preset": preset_name,
            "preset_key": preset_key,
        }


class PreviewWindow(tk.Toplevel):
    """Inline video preview using ffmpeg image piping (falls back to ffplay)."""

    def __init__(
        self,
        master: tk.Tk,
        video_path: Path,
        ffmpeg_bin: str,
        *,
        max_frames: int = 360,
        on_close: Optional[callable] = None,
    ) -> None:
        super().__init__(master)
        self.title(f"Preview – {video_path.name}")
        self.resizable(False, False)
        self._queue: "queue.Queue[Optional[tuple[int, int, bytes]]]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._on_close = on_close
        self._photo: Optional[ImageTk.PhotoImage] = None  # type: ignore

        self.label = tk.Label(self)
        self.label.pack(padx=12, pady=12)

        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        if ImageTk is None:  # Pillow missing -> fallback to ffplay
            messagebox.showinfo(
                "Preview",
                "Pillow is not installed, launching ffplay for preview instead.",
                parent=self,
            )
            subprocess.run(
                [
                    "ffplay",
                    "-autoexit",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    str(video_path),
                ],
                check=False,
            )
            self.after(0, self._handle_close)
            return

        self._thread = threading.Thread(
            target=self._stream_frames,
            args=(video_path, ffmpeg_bin, max_frames),
            daemon=True,
        )
        self._thread.start()
        self._poll_queue()

    def _stream_frames(self, video_path: Path, ffmpeg_bin: str, max_frames: int) -> None:
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vf",
            "scale=480:trunc(ow/a/2)*2",
            "-f",
            "image2pipe",
            "-vcodec",
            "ppm",
            "-",
        ]
        try:
            self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            self._queue.put(None)
            return
        assert self._process.stdout is not None

        frame_count = 0
        stdout = self._process.stdout
        try:
            while not self._stop.is_set():
                magic = stdout.readline()
                if not magic:
                    break
                if magic.strip() != b"P6":
                    continue  # Skip unexpected headers
                dims_line = stdout.readline()
                while dims_line.startswith(b"#"):
                    dims_line = stdout.readline()
                if not dims_line:
                    break
                try:
                    width_str, height_str = dims_line.strip().split()
                    width = int(width_str)
                    height = int(height_str)
                except ValueError:
                    break
                max_val_line = stdout.readline()
                if not max_val_line:
                    break
                frame_size = width * height * 3
                frame_data = stdout.read(frame_size)
                if len(frame_data) < frame_size:
                    break
                self._queue.put((width, height, frame_data))
                frame_count += 1
                if frame_count >= max_frames:
                    break
        finally:
            self._queue.put(None)
            stdout.close()
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=2)

    def _poll_queue(self) -> None:
        if self._stop.is_set():
            return
        try:
            item = self._queue.get_nowait()
        except queue.Empty:
            self.after(15, self._poll_queue)
            return

        if item is None:
            self._handle_close()
            return

        width, height, data = item
        assert Image is not None and ImageTk is not None  # for type checker
        image = Image.frombytes("RGB", (width, height), data)
        self._photo = ImageTk.PhotoImage(image)  # type: ignore
        self.label.configure(image=self._photo)
        self.after(15, self._poll_queue)

    def _handle_close(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        if callable(self._on_close):
            try:
                self._on_close()
            finally:
                self._on_close = None
        self.destroy()


class MoshApp(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Datamosh Helper")
        self.resizable(False, False)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.ffmpeg_bin = tk.StringVar(value="ffmpeg")
        self.status = tk.StringVar(value="Load a clip to begin.")
        self.auto_normalize = tk.BooleanVar(value=True)
        self.normalize_preset = tk.StringVar(value="Balanced")

        self.default_keep_first = tk.IntVar(value=1)
        self.default_dup_count = tk.IntVar(value=0)
        self.default_dup_gap = tk.IntVar(value=1)

        self.detail_keep_first = tk.IntVar(value=1)
        self.detail_dup_count = tk.IntVar(value=0)
        self.detail_dup_gap = tk.IntVar(value=1)
        self.detail_drop_first = tk.BooleanVar(value=False)
        self.detail_keep_keys = tk.StringVar()
        self.detail_drop_keys = tk.StringVar()

        self.clip_profiles: List[ClipProfile] = []
        self.selected_clip_index: Optional[int] = None
        self._worker: Optional[threading.Thread] = None
        self.progress_bar: Optional[ttk.Progressbar] = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

        # Initialize keyboard shortcuts
        self.shortcut_manager = shortcuts.ShortcutManager(self)
        shortcuts.register_datamosh_shortcuts(self.shortcut_manager, self)

        # Initialize drag-and-drop support
        self._setup_drag_and_drop()

    def _setup_drag_and_drop(self) -> None:
        """Setup drag-and-drop support for video files."""
        if not HAS_DND:
            return  # tkinterdnd2 not available

        # Register the main window as a drop target
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self._on_file_drop)

    def _on_file_drop(self, event) -> None:
        """Handle dropped files."""
        if not HAS_DND:
            return

        # Parse dropped files from event data
        files = self._parse_drop_files(event.data)

        # Filter valid video files
        VALID_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
        video_files = [
            f for f in files
            if Path(f).suffix.lower() in VALID_EXTENSIONS and Path(f).exists()
        ]

        if not video_files:
            messagebox.showwarning(
                "Drag & Drop",
                "No valid video files found.\nSupported: MP4, AVI, MOV, MKV, WebM, FLV, WMV",
                parent=self
            )
            return

        # Load first file as base clip
        base_path = Path(video_files[0])
        profile = self._prepare_clip(base_path, role="base", drop_first=False, defaults=True)
        if profile is None:
            return

        if self.clip_profiles:
            self._release_profile(self.clip_profiles[0])
            self.clip_profiles[0] = profile
        else:
            self.clip_profiles.insert(0, profile)

        self.input_path.set(str(profile.source_path))
        default_output = profile.source_path.with_suffix("").name + "_moshed.avi"
        if not self.output_path.get():
            self.output_path.set(str(profile.source_path.with_name(default_output)))

        # Load additional files as appends
        for path_str in video_files[1:]:
            path = Path(path_str)
            offset = len(self.clip_profiles)
            profile = self._prepare_clip(path, role=f"append{offset}", drop_first=True, defaults=False)
            if profile is not None:
                self.clip_profiles.append(profile)

        self._refresh_clip_tree()
        self._select_clip(0)

        if len(video_files) == 1:
            self._set_status(f"Loaded: {base_path.name}")
        else:
            self._set_status(f"Loaded {len(video_files)} clips (1 base + {len(video_files)-1} appends)")

    def _parse_drop_files(self, data: str) -> list[str]:
        """Parse dropped file paths from tkinterdnd2 data string."""
        # Handle both single and multiple files
        # tkinterdnd2 wraps paths with spaces in braces: {/path/to/file.mp4}
        files = []
        current = ""
        in_braces = False

        for char in data:
            if char == '{':
                in_braces = True
            elif char == '}':
                in_braces = False
                if current:
                    files.append(current.strip())
                    current = ""
            elif char == ' ' and not in_braces:
                if current:
                    files.append(current.strip())
                    current = ""
            else:
                current += char

        if current:
            files.append(current.strip())

        return files

    # UI construction -----------------------------------------------------

    def _build_ui(self) -> None:
        padding = {"padx": 8, "pady": 4}

        input_frame = tk.Frame(self)
        input_frame.grid(row=0, column=0, sticky="ew", **padding)
        tk.Label(input_frame, text="Input clip:").grid(row=0, column=0, sticky="w")
        tk.Entry(input_frame, textvariable=self.input_path, width=48).grid(row=0, column=1, sticky="w")
        tk.Button(input_frame, text="Browse…", command=self._select_input).grid(row=0, column=2, padx=(6, 0))

        output_frame = tk.Frame(self)
        output_frame.grid(row=1, column=0, sticky="ew", **padding)
        tk.Label(output_frame, text="Output file:").grid(row=0, column=0, sticky="w")
        tk.Entry(output_frame, textvariable=self.output_path, width=48).grid(row=0, column=1, sticky="w")
        tk.Button(output_frame, text="Browse…", command=self._select_output).grid(row=0, column=2, padx=(6, 0))

        clip_frame = ttk.LabelFrame(self, text="Clip Stack")
        clip_frame.grid(row=2, column=0, sticky="ew", **padding)

        columns = ("clip", "keep", "drop", "dup", "gap", "res")
        self.clip_tree = ttk.Treeview(clip_frame, columns=columns, show="headings", height=6, selectmode="browse")
        self.clip_tree.heading("clip", text="Clip")
        self.clip_tree.heading("keep", text="Keep")
        self.clip_tree.heading("drop", text="Drop 1st")
        self.clip_tree.heading("dup", text="Dup")
        self.clip_tree.heading("gap", text="Gap")
        self.clip_tree.heading("res", text="Normalised")
        self.clip_tree.column("clip", width=180, anchor="w")
        self.clip_tree.column("keep", width=60, anchor="center")
        self.clip_tree.column("drop", width=70, anchor="center")
        self.clip_tree.column("dup", width=60, anchor="center")
        self.clip_tree.column("gap", width=60, anchor="center")
        self.clip_tree.column("res", width=120, anchor="w")
        self.clip_tree.grid(row=0, column=0, columnspan=7, sticky="ew")
        self.clip_tree.bind("<<TreeviewSelect>>", self._on_clip_select)
        clip_frame.grid_columnconfigure(0, weight=1)

        tk.Button(clip_frame, text="Add append…", command=self._add_append).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Button(clip_frame, text="Remove", command=self._remove_selected_clip).grid(row=1, column=1, sticky="w", pady=(6, 0))
        tk.Button(clip_frame, text="Clear appended", command=self._clear_appended).grid(row=1, column=2, sticky="w", pady=(6, 0))
        tk.Button(clip_frame, text="Re-normalize", command=self._renormalize_selected).grid(row=1, column=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(clip_frame, text="Auto-normalize", variable=self.auto_normalize).grid(row=1, column=4, sticky="w", pady=(6, 0))
        ttk.Label(clip_frame, text="Preset:").grid(row=1, column=5, sticky="e", padx=(12, 0), pady=(6, 0))
        preset_combo = ttk.Combobox(clip_frame, textvariable=self.normalize_preset, values=["Fast", "Balanced", "Sharp", "Original"], state="readonly", width=12)
        preset_combo.grid(row=1, column=6, sticky="e", pady=(6, 0))

        # Timeline editor
        timeline_frame = ttk.LabelFrame(self, text="Timeline Editor (Frame-by-frame)")
        timeline_frame.grid(row=3, column=0, sticky="ew", **padding)
        self.timeline_widget = TimelineWidget(timeline_frame)
        self.timeline_widget.pack(fill=tk.BOTH, expand=True)
        self.timeline_widget.on_frame_change = self._on_timeline_frame_change
        self.timeline_widget.timeline.on_duplicate_add = self._on_timeline_duplicate_add
        self.timeline_widget.timeline.on_region_select = self._on_timeline_region_select

        detail_frame = ttk.LabelFrame(self, text="Clip Settings")
        detail_frame.grid(row=4, column=0, sticky="ew", **padding)

        tk.Label(detail_frame, text="Keep first I-frames:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(detail_frame, from_=0, to=999, textvariable=self.detail_keep_first, width=6).grid(row=0, column=1, sticky="w", padx=(4, 12))

        tk.Label(detail_frame, text="Duplicate count:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(detail_frame, from_=0, to=99, textvariable=self.detail_dup_count, width=6).grid(row=0, column=3, sticky="w", padx=(4, 12))

        tk.Label(detail_frame, text="Duplicate gap:").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(detail_frame, from_=1, to=99, textvariable=self.detail_dup_gap, width=6).grid(row=0, column=5, sticky="w")

        ttk.Checkbutton(detail_frame, text="Drop first keyframe", variable=self.detail_drop_first).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        tk.Label(detail_frame, text="Keep key indices:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(detail_frame, textvariable=self.detail_keep_keys, width=24).grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))
        tk.Label(detail_frame, text="Drop key indices:").grid(row=2, column=3, sticky="w", pady=(6, 0))
        ttk.Entry(detail_frame, textvariable=self.detail_drop_keys, width=24).grid(row=2, column=4, columnspan=2, sticky="w", pady=(6, 0))

        tk.Button(detail_frame, text="Apply to selected", command=self._apply_clip_settings).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        prep_frame = ttk.LabelFrame(self, text="ffmpeg")
        prep_frame.grid(row=5, column=0, sticky="ew", **padding)
        tk.Label(prep_frame, text="ffmpeg binary:").grid(row=0, column=0, sticky="w")
        ttk.Entry(prep_frame, textvariable=self.ffmpeg_bin, width=20).grid(row=0, column=1, sticky="w")

        status_frame = tk.Frame(self)
        status_frame.grid(row=6, column=0, sticky="ew", padx=8, pady=(4, 0))
        tk.Label(status_frame, textvariable=self.status, anchor="w").grid(row=0, column=0, sticky="w")

        # Progress bar frame
        progress_frame = tk.Frame(self)
        progress_frame.grid(row=7, column=0, sticky="ew", padx=8, pady=(2, 0))
        self.progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate", length=400)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_remove()  # Hide by default
        self.progress_frame = progress_frame  # Store reference for showing/hiding

        button_frame = tk.Frame(self)
        button_frame.grid(row=8, column=0, sticky="e", padx=8, pady=8)
        self.run_button = tk.Button(button_frame, text="Render", command=lambda: self._start_worker("render"))
        self.run_button.grid(row=0, column=0, padx=(0, 6))
        self.preview_button = tk.Button(button_frame, text="Preview", command=lambda: self._start_worker("preview"))
        self.preview_button.grid(row=0, column=1, padx=(0, 6))
        tk.Button(button_frame, text="Quit", command=self._on_exit).grid(row=0, column=2)

    # File selection ------------------------------------------------------

    def _select_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select base clip",
            filetypes=(("Video files", "*.avi *.mp4 *.mov *.mkv *.*"), ("All files", "*.*")),
        )
        if not path:
            return
        profile = self._prepare_clip(Path(path), role="base", drop_first=False, defaults=True)
        if profile is None:
            return
        if self.clip_profiles:
            self._release_profile(self.clip_profiles[0])
            self.clip_profiles[0] = profile
        else:
            self.clip_profiles.insert(0, profile)
        self.input_path.set(str(profile.source_path))
        default_output = profile.source_path.with_suffix("").name + "_moshed.avi"
        if not self.output_path.get():
            self.output_path.set(str(profile.source_path.with_name(default_output)))
        self._refresh_clip_tree()
        self._select_clip(0)
        self._set_status("Base clip ready. Add more clips or tweak settings.")

    def _select_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Select output file",
            defaultextension=".avi",
            filetypes=(("AVI files", "*.avi"), ("All files", "*.*")),
        )
        if path:
            self.output_path.set(path)

    # Clip management -----------------------------------------------------

    def _prepare_clip(self, source: Path, *, role: str, drop_first: bool, defaults: bool) -> Optional[ClipProfile]:
        if not source.exists():
            messagebox.showerror("Load Clip", f"{source} does not exist.", parent=self)
            return None

        normalized_path = source
        temp_dir: Optional[Path] = None

        preset_name = self.normalize_preset.get()
        preset = GUI_PRESETS.get(preset_name)

        # Default settings derived from the selected preset.
        default_settings = {
            "preset": preset_name if preset_name in GUI_PRESETS else "Balanced",
            "width": preset["width"] if isinstance(preset, dict) else None,
            "qscale": preset["qscale"] if isinstance(preset, dict) else 3,
            "gop": preset["gop"] if isinstance(preset, dict) else 48,
            "keep_audio": preset.get("keep_audio", True) if isinstance(preset, dict) else True,
        }

        options = {
            "transcode": False,
            "preset": preset_name if preset_name in GUI_PRESETS else "Balanced",
            "preset_key": preset["key"] if isinstance(preset, dict) else None,
            "width": default_settings["width"],
            "height": None,
            "qscale": default_settings["qscale"],
            "gop": default_settings["gop"],
            "keep_audio": default_settings["keep_audio"],
        }

        if self.auto_normalize.get():
            dialog = NormalizationDialog(
                self,
                f"Normalise {source.name}",
                initial_settings=default_settings,
            )
            if dialog.result is None:
                return None
            options.update(dialog.result)
        else:
            options["preset"] = "Original"
            options["preset_key"] = None
            options["transcode"] = False

        transcode = bool(options.get("transcode"))
        preset_name = options.get("preset", preset_name)
        preset_key = options.get("preset_key")
        norm_width = options.get("width")
        norm_height = options.get("height")
        norm_qscale = options.get("qscale", 3)
        norm_gop = options.get("gop", 48)
        keep_audio = options.get("keep_audio", True)

        if transcode:
            self._set_status(f"Normalising {source.name} ({preset_name})…")
            normalized_path, temp_dir = self._normalize_clip(
                source,
                width=norm_width,
                height=norm_height,
                qscale=norm_qscale,
                gop=norm_gop,
                keep_audio=keep_audio,
            )
            if normalized_path is None:
                self._set_status("Normalisation cancelled.")
                return None
        else:
            preset_key = None if preset_name == "Original" else preset_key

        if transcode:
            self._set_status(f"Clip normalised ({preset_name}).")
        else:
            self._set_status("Clip ready (original stream).")

        profile = ClipProfile(
            role=role,
            source_path=source,
            normalized_path=normalized_path,
            temp_dir=temp_dir,
            keep_first=self.default_keep_first.get() if defaults else 0,
            duplicate_count=self.default_dup_count.get(),
            duplicate_gap=max(self.default_dup_gap.get(), 1),
            drop_first_keyframe=drop_first,
            norm_width=norm_width,
            norm_height=norm_height,
            norm_qscale=norm_qscale,
            norm_gop=norm_gop,
            keep_audio=keep_audio,
            transcode=transcode,
            preset_name=preset_name,
            preset_key=preset_key,
        )
        return profile

    def _normalize_clip(
        self,
        source: Path,
        *,
        width: Optional[int],
        height: Optional[int],
        qscale: int,
        gop: int,
        keep_audio: bool,
    ) -> tuple[Optional[Path], Optional[Path]]:
        temp_dir = Path(tempfile.mkdtemp(prefix="mosh-clip-"))
        target = temp_dir / f"{source.stem}_normalized.avi"

        def _even(value: Optional[int]) -> Optional[int]:
            if value is None:
                return None
            return max(2, (value // 2) * 2)

        width = _even(width)
        height = _even(height)

        cmd = [
            self.ffmpeg_bin.get() or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
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
        if width and height:
            cmd.extend(
                [
                    "-vf",
                    f"scale={width}:{height}:flags=lanczos:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                ]
            )
        elif width:
            cmd.extend(["-vf", f"scale={width}:-2:flags=lanczos"])
        elif height:
            cmd.extend(["-vf", f"scale=-2:{height}:flags=lanczos"])
        if keep_audio:
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.append("-an")
        cmd.append(str(target))

        progress = tk.Toplevel(self)
        progress.title("Normalising clip")
        progress.geometry("360x140")
        progress.resizable(False, False)
        tk.Label(progress, text=f"Preparing Xvid stream…\n{source.name}", wraplength=320).pack(padx=12, pady=(12, 4))
        status_var = tk.StringVar(value="Encoding…")
        tk.Label(progress, textvariable=status_var).pack()
        button_frame = tk.Frame(progress)
        button_frame.pack(pady=(8, 12))

        cancelled = threading.Event()
        done_event = threading.Event()
        process_holder: Dict[str, Optional[subprocess.Popen]] = {"proc": None}
        result: Dict[str, Optional[object]] = {"code": None, "stderr": ""}

        def worker() -> None:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError:
                result["code"] = -1
                result["stderr"] = "ffmpeg not found on PATH."
                done_event.set()
                return
            except Exception as exc:  # pragma: no cover - unexpected
                result["code"] = -1
                result["stderr"] = str(exc)
                done_event.set()
                return

            process_holder["proc"] = proc

            try:
                _, stderr = proc.communicate()
            except Exception as exc:  # pragma: no cover - communicate failure
                result["code"] = -1
                result["stderr"] = str(exc)
                done_event.set()
                return

            result["code"] = proc.returncode
            result["stderr"] = (stderr or b"").decode("utf-8", errors="ignore")
            done_event.set()

        def cancel() -> None:
            if cancelled.is_set():
                return
            cancelled.set()
            status_var.set("Stopping…")
            cancel_button.configure(state=tk.DISABLED)
            proc = process_holder.get("proc")
            if proc and proc.poll() is None:
                proc.terminate()

        cancel_button = ttk.Button(button_frame, text="Cancel", command=cancel)
        cancel_button.pack()
        progress.protocol("WM_DELETE_WINDOW", cancel)
        progress.transient(self)
        progress.grab_set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll() -> None:
            if done_event.is_set():
                progress.destroy()
            else:
                progress.after(100, poll)

        poll()
        self.wait_window(progress)
        done_event.wait()
        thread.join(timeout=0.1)

        proc = process_holder.get("proc")
        if cancelled.is_set():
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, None

        code = result.get("code")
        stderr_output = result.get("stderr", "") or ""
        if code is None:
            shutil.rmtree(temp_dir, ignore_errors=True)
            messagebox.showerror("Normalise Clip", stderr_output or "Normalisation failed.", parent=self)
            return None, None
        if code != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            messagebox.showerror(
                "Normalise Clip",
                stderr_output or f"ffmpeg exited with status {code}.",
                parent=self,
            )
            return None, None

        return target, temp_dir

    def _add_append(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select clip(s) to append",
            filetypes=(("Video files", "*.avi *.mp4 *.mov *.mkv *.*"), ("All files", "*.*")),
        )
        if not paths:
            return
        for offset, path in enumerate(paths, start=len(self.clip_profiles)):
            profile = self._prepare_clip(Path(path), role=f"append{offset}", drop_first=True, defaults=False)
            if profile is None:
                continue
            self.clip_profiles.append(profile)
        self._refresh_clip_tree()
        if self.clip_profiles:
            self._select_clip(len(self.clip_profiles) - 1)
        self._set_status("Appended clip(s) loaded. Adjust per-clip settings as needed.")

    def _remove_selected_clip(self) -> None:
        index = self.selected_clip_index
        if index is None or index == 0:
            self._set_status("Select an appended clip to remove.")
            return
        profile = self.clip_profiles.pop(index)
        self._release_profile(profile)
        self._refresh_clip_tree()
        new_index = min(index - 1, len(self.clip_profiles) - 1)
        if new_index >= 0:
            self._select_clip(new_index)
        else:
            self.selected_clip_index = None
        self._set_status("Clip removed.")

    def _clear_appended(self) -> None:
        if len(self.clip_profiles) <= 1:
            return
        for profile in self.clip_profiles[1:]:
            self._release_profile(profile)
        del self.clip_profiles[1:]
        self._refresh_clip_tree()
        self._select_clip(0)
        self._set_status("Cleared appended clips.")

    def _renormalize_selected(self) -> None:
        index = self.selected_clip_index
        if index is None:
            self._set_status("Select a clip to normalise.")
            return
        profile = self.clip_profiles[index]
        initial_settings = {
            "preset": profile.preset_name,
            "width": profile.norm_width,
            "qscale": profile.norm_qscale,
            "gop": profile.norm_gop,
            "keep_audio": profile.keep_audio,
        }
        dialog = NormalizationDialog(
            self,
            f"Re-normalize {profile.source_path.name}",
            initial_settings=initial_settings,
        )
        if dialog.result is None:
            return
        result = dialog.result
        self._release_profile(profile)

        if not result.get("transcode", True):
            profile.normalized_path = profile.source_path
            profile.temp_dir = None
            profile.norm_width = None
            profile.norm_height = None
            profile.norm_qscale = 3
            profile.norm_gop = 48
            profile.keep_audio = True
            profile.transcode = False
            profile.preset_name = result.get("preset", "Original")
            profile.preset_key = result.get("preset_key")
        else:
            normalized_path, temp_dir = self._normalize_clip(
                profile.source_path,
                width=result.get("width"),
                height=result.get("height"),
                qscale=result.get("qscale", 3),
                gop=result.get("gop", 48),
                keep_audio=result.get("keep_audio", True),
            )
            if normalized_path is None:
                return
            profile.normalized_path = normalized_path
            profile.temp_dir = temp_dir
            profile.norm_width = result.get("width")
            profile.norm_height = result.get("height")
            profile.norm_qscale = result.get("qscale", 3)
            profile.norm_gop = result.get("gop", 48)
            profile.keep_audio = result.get("keep_audio", True)
            profile.transcode = True
            profile.preset_name = result.get("preset", "Custom")
            profile.preset_key = result.get("preset_key")

        self._refresh_clip_tree()
        self._select_clip(index)
        self._set_status("Clip normalised.")

    def _release_profile(self, profile: ClipProfile) -> None:
        if profile.temp_dir and profile.temp_dir.exists():
            shutil.rmtree(profile.temp_dir, ignore_errors=True)
        profile.temp_dir = None

    # Tree + details ------------------------------------------------------

    def _refresh_clip_tree(self) -> None:
        for item in self.clip_tree.get_children():
            self.clip_tree.delete(item)
        for idx, profile in enumerate(self.clip_profiles):
            keep = profile.keep_first
            drop = "Yes" if (profile.drop_first_keyframe and idx != 0) else "No"
            dup = profile.duplicate_count
            gap = profile.duplicate_gap
            res = profile.resolution_hint()
            self.clip_tree.insert(
                "",
                "end",
                iid=f"clip{idx}",
                values=(profile.label(), keep, drop, dup, gap, res),
            )
        if self.selected_clip_index is not None and self.selected_clip_index < len(self.clip_profiles):
            desired = f"clip{self.selected_clip_index}"
            current = self.clip_tree.selection()
            if not current or current[0] != desired:
                self.clip_tree.selection_set(desired)
        elif self.clip_profiles:
            self._select_clip(0)

    def _select_clip(self, index: int) -> None:
        if index < 0 or index >= len(self.clip_profiles):
            return
        self.selected_clip_index = index
        profile = self.clip_profiles[index]
        desired = f"clip{index}"
        current = self.clip_tree.selection()
        if not current or current[0] != desired:
            self.clip_tree.selection_set(desired)
        self.detail_keep_first.set(profile.keep_first)
        self.detail_dup_count.set(profile.duplicate_count)
        self.detail_dup_gap.set(profile.duplicate_gap)
        self.detail_drop_first.set(profile.drop_first_keyframe)
        self.detail_keep_keys.set(profile.keep_keys_spec)
        self.detail_drop_keys.set(profile.drop_keys_spec)

        # Load video into timeline editor
        if profile.normalized_path.exists():
            self.timeline_widget.load_video(profile.normalized_path)

    def _on_clip_select(self, _event: object) -> None:
        selection = self.clip_tree.selection()
        if not selection:
            return
        item = selection[0]
        if item.startswith("clip"):
            index = int(item[4:])
            self._select_clip(index)

    def _select_previous_clip(self) -> None:
        """Navigate to previous clip (keyboard shortcut helper)."""
        if not self.clip_profiles:
            return
        if self.selected_clip_index is None:
            self._select_clip(0)
        elif self.selected_clip_index > 0:
            self._select_clip(self.selected_clip_index - 1)

    def _select_next_clip(self) -> None:
        """Navigate to next clip (keyboard shortcut helper)."""
        if not self.clip_profiles:
            return
        if self.selected_clip_index is None:
            self._select_clip(0)
        elif self.selected_clip_index < len(self.clip_profiles) - 1:
            self._select_clip(self.selected_clip_index + 1)

    def _on_timeline_frame_change(self, frame: int) -> None:
        """Handle frame change from timeline scrubbing."""
        # Status update
        self._set_status(f"Timeline: Frame {frame} selected")

    def _on_timeline_duplicate_add(self, frame: int, count: int) -> None:
        """Handle P-frame duplication added from timeline."""
        if self.selected_clip_index is not None and self.clip_profiles:
            profile = self.clip_profiles[self.selected_clip_index]

            # Update the duplicate count in the current profile
            # Note: This is a simplified version that applies to all frames
            # In a more advanced version, you'd track per-frame duplications
            profile.duplicate_count = count

            # Update the detail panel to reflect the change
            self.detail_dup_count.set(count)

            # Refresh the tree view
            self._refresh_clip_tree()

            self._set_status(f"P-frame duplication (×{count}) added at frame {frame}")

    def _on_timeline_region_select(self, start_frame: int, end_frame: int) -> None:
        """Handle in/out region selection from timeline."""
        self._set_status(f"Region selected: frames {start_frame} to {end_frame}")

    def _apply_clip_settings(self) -> None:
        index = self.selected_clip_index
        if index is None:
            self._set_status("Select a clip to adjust.",)
            return
        profile = self.clip_profiles[index]
        profile.keep_first = max(0, self.detail_keep_first.get())
        profile.duplicate_count = max(0, self.detail_dup_count.get())
        profile.duplicate_gap = max(1, self.detail_dup_gap.get())
        profile.drop_first_keyframe = bool(self.detail_drop_first.get())
        profile.keep_keys_spec = self.detail_keep_keys.get().strip()
        profile.drop_keys_spec = self.detail_drop_keys.get().strip()
        self._refresh_clip_tree()
        self._set_status("Clip settings updated.")

    # Worker orchestration ------------------------------------------------

    def _start_worker(self, mode: str) -> None:
        if self._worker and self._worker.is_alive():
            return
        try:
            options = self._collect_options()
        except ValueError as exc:
            messagebox.showerror("Datamosh Helper", str(exc), parent=self)
            return

        self._set_status("Rendering…" if mode == "render" else "Preparing preview…")
        self._set_buttons_state(tk.DISABLED)
        self._start_progress()  # Start progress bar animation
        self._worker = threading.Thread(target=self._run_mosh, args=(options, mode), daemon=True)
        self._worker.start()

    def _collect_options(self) -> Dict[str, object]:
        if not self.clip_profiles:
            raise ValueError("Load at least one clip.")
        output = self.output_path.get().strip()
        if not output:
            raise ValueError("Choose an output filename.")
        output_path = Path(output).expanduser()
        if not output_path.parent.exists():
            raise ValueError("Output directory does not exist.")
        for profile in self.clip_profiles:
            if not profile.normalized_path.exists():
                raise ValueError(f"Normalised file missing for {profile.source_path.name}.")
        return {
            "clips": list(self.clip_profiles),
            "output": output_path,
            "ffmpeg_bin": self.ffmpeg_bin.get() or "ffmpeg",
        }

    def _run_mosh(self, options: Dict[str, object], mode: str) -> None:
        try:
            if mode == "render":
                self._perform_mosh(options)
            else:
                self._perform_preview(options)
        except Exception as exc:  # pragma: no cover - UI surface
            self._notify_error(exc)
        else:
            if mode == "render":
                self._notify_success()

    def _build_clip_options(self, clips: List[ClipProfile]) -> Dict[int, mosh.ClipOptions]:
        clip_opts: Dict[int, mosh.ClipOptions] = {}
        for idx, profile in enumerate(clips):
            try:
                keep_keys = mosh.parse_keyframe_spec(profile.keep_keys_spec) if profile.keep_keys_spec else set()
                drop_keys = mosh.parse_keyframe_spec(profile.drop_keys_spec) if profile.drop_keys_spec else set()
            except ValueError as exc:
                raise ValueError(f"{profile.label()}: {exc}") from exc
            clip_opts[idx] = mosh.ClipOptions(
                keep_initial_keyframes=max(0, profile.keep_first),
                duplicate_count=max(0, profile.duplicate_count),
                duplicate_gap=max(1, profile.duplicate_gap),
                drop_first_keyframe=profile.drop_first_keyframe if idx != 0 else profile.drop_first_keyframe,
                keep_specific_keys=keep_keys or None,
                drop_specific_keys=drop_keys or None,
            )
        return clip_opts

    def _perform_mosh(self, options: Dict[str, object]) -> None:
        clips: List[ClipProfile] = options["clips"]  # type: ignore[assignment]
        base = clips[0]
        append = clips[1:]
        clip_opts = self._build_clip_options(clips)

        mosh.rewrite_avi(
            base.normalized_path,
            options["output"],  # type: ignore[arg-type]
            keep_initial_keyframes=clip_opts[0].keep_initial_keyframes,
            duplicate_count=clip_opts[0].duplicate_count,
            duplicate_gap=clip_opts[0].duplicate_gap,
            extra_inputs=[profile.normalized_path for profile in append],
            keep_key_indices=None,
            drop_key_indices=None,
            clip_options=clip_opts,
            drop_appended_first=False,
        )

    def _perform_preview(self, options: Dict[str, object]) -> None:
        clips: List[ClipProfile] = options["clips"]  # type: ignore[assignment]
        clip_opts = self._build_clip_options(clips)
        base = clips[0]
        append = clips[1:]

        preview_dir = Path(tempfile.mkdtemp(prefix="mosh-preview-"))
        preview_path = preview_dir / "preview.avi"

        try:
            mosh.rewrite_avi(
                base.normalized_path,
                preview_path,
                keep_initial_keyframes=clip_opts[0].keep_initial_keyframes,
                duplicate_count=clip_opts[0].duplicate_count,
                duplicate_gap=clip_opts[0].duplicate_gap,
                extra_inputs=[profile.normalized_path for profile in append],
                keep_key_indices=None,
                drop_key_indices=None,
                clip_options=clip_opts,
                drop_appended_first=False,
            )
        except Exception:
            shutil.rmtree(preview_dir, ignore_errors=True)
            raise

        def launch_preview() -> None:
            def cleanup() -> None:
                shutil.rmtree(preview_dir, ignore_errors=True)
                self._stop_progress()  # Stop progress bar
                self._set_buttons_state(tk.NORMAL)
                self._set_status("Preview closed.")

            self._stop_progress()  # Stop progress bar when preview launches

            # Use the new VideoPreviewWidget with hardware acceleration
            VideoPreviewWidget(
                self,
                preview_path,
                ffmpeg_bin=options["ffmpeg_bin"],  # type: ignore[arg-type]
                max_frames=600,  # Preview up to 600 frames (~20 seconds at 30fps)
                preview_width=640,
                use_opencv=True,  # Enable OpenCV hardware acceleration if available
                on_close=cleanup
            )
            self._set_buttons_state(tk.NORMAL)
            self._set_status("Preview ready – close the window when finished.")

        self.after(0, launch_preview)

    # Notifications -------------------------------------------------------

    def _notify_error(self, exc: Exception) -> None:
        def _show() -> None:
            self._stop_progress()  # Stop progress bar
            self._set_status("Operation failed.")
            self._set_buttons_state(tk.NORMAL)
            messagebox.showerror("Datamosh Helper", str(exc), parent=self)

        self.after(0, _show)

    def _notify_success(self) -> None:
        def _show() -> None:
            self._stop_progress()  # Stop progress bar
            self._set_status("All done! Open the output clip to view the glitch.")
            self._set_buttons_state(tk.NORMAL)

        self.after(0, _show)

    # Helpers -------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status.set(text)

    def _set_buttons_state(self, state: str) -> None:
        self.run_button.configure(state=state)
        self.preview_button.configure(state=state)

    def _start_progress(self) -> None:
        """Show and start the progress bar animation."""
        if self.progress_bar and self.progress_frame:
            self.progress_frame.grid()  # Show the progress bar frame
            self.progress_bar.start(10)  # Start indeterminate animation

    def _stop_progress(self) -> None:
        """Stop and hide the progress bar."""
        if self.progress_bar and self.progress_frame:
            self.progress_bar.stop()
            self.progress_frame.grid_remove()  # Hide the progress bar frame

    def _on_exit(self) -> None:
        for profile in self.clip_profiles:
            self._release_profile(profile)
        self.destroy()


def main() -> int:
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('datamosh-gui.log'),
            logging.StreamHandler()
        ]
    )
    logger.info("Starting Datamosh GUI application")

    try:
        app = MoshApp()
        app.mainloop()
        logger.info("Application closed normally")
        return 0
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
