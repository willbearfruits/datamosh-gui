#!/usr/bin/env python3
"""
Modern hardware-accelerated video preview widget for datamosh GUI.

Provides an optimized video preview window with:
- Hardware-accelerated decoding (when available)
- Threaded frame extraction
- Efficient memory management
- Play/pause controls
- Frame seeking
- Fallback support for missing dependencies
"""

from __future__ import annotations

import logging
import queue
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

import tkinter as tk
from tkinter import messagebox, ttk, filedialog

# Configure module logger
logger = logging.getLogger(__name__)

# Optional dependencies with graceful fallback
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = ImageTk = None  # type: ignore

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    cv2 = None  # type: ignore


@dataclass
class FrameData:
    """Container for a decoded video frame."""
    width: int
    height: int
    data: bytes
    frame_number: int
    timestamp: float


class VideoPreviewWidget(tk.Toplevel):
    """
    Hardware-accelerated video preview widget with playback controls.

    Supports multiple backends:
    1. OpenCV (cv2) - Hardware-accelerated, best performance
    2. ffmpeg + PIL - Software decoding, good compatibility
    3. ffplay - External player fallback

    Features:
    - Threaded frame extraction for non-blocking UI
    - Play/pause/stop controls
    - Frame seeking
    - Configurable preview size
    - Automatic cleanup
    """

    def __init__(
        self,
        master: tk.Tk,
        video_path: Path,
        *,
        ffmpeg_bin: str = "ffmpeg",
        max_frames: int = 600,
        preview_width: int = 640,
        on_close: Optional[Callable[[], None]] = None,
        use_opencv: bool = True,
    ) -> None:
        """
        Initialize video preview widget.

        Args:
            master: Parent Tk window
            video_path: Path to video file
            ffmpeg_bin: Path to ffmpeg binary
            max_frames: Maximum frames to preview (0 = unlimited)
            preview_width: Width for preview display (0 = auto-detect from screen)
            on_close: Callback when window closes
            use_opencv: Prefer OpenCV over ffmpeg if available
        """
        super().__init__(master)

        self.video_path = video_path
        self.ffmpeg_bin = ffmpeg_bin
        self.max_frames = max_frames

        # Adaptive preview width based on screen size
        if preview_width == 0:
            try:
                screen_width = master.winfo_screenwidth()
                # Use half screen width, capped at 1280px for performance
                self.preview_width = min(screen_width // 2, 1280)
            except Exception:
                self.preview_width = 640  # Fallback
        else:
            self.preview_width = preview_width

        self._on_close = on_close
        self.use_opencv = use_opencv and HAS_CV2

        # Thread management
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start playing
        self._worker_thread: Optional[threading.Thread] = None

        # Frame queue and state
        self._frame_queue: queue.Queue[Optional[FrameData]] = queue.Queue(maxsize=30)
        self._current_photo: Optional[ImageTk.PhotoImage] = None
        self._current_image: Optional[Image.Image] = None  # Store raw PIL Image for export
        self._is_playing = True
        self._total_frames = 0
        self._current_frame = 0

        # Subprocess for ffmpeg method
        self._process: Optional[subprocess.Popen] = None

        # Configure window
        self.title(f"Preview - {video_path.name}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        # Build UI
        self._build_ui()

        # Check dependencies and start preview
        if not self._check_dependencies():
            self._fallback_to_ffplay()
        else:
            self._start_preview()

    def _build_ui(self) -> None:
        """Build the preview UI components."""
        # Main container
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Video display area
        self.canvas = tk.Canvas(
            main_frame,
            width=self.preview_width,
            height=int(self.preview_width * 9 / 16),  # 16:9 default
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack(pady=(0, 10))

        # Control bar
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X)

        # Play/pause button
        self.play_button = ttk.Button(
            control_frame,
            text="⏸ Pause",
            command=self._toggle_play_pause,
            width=10
        )
        self.play_button.pack(side=tk.LEFT, padx=(0, 5))

        # Stop button
        self.stop_button = ttk.Button(
            control_frame,
            text="⏹ Stop",
            command=self._handle_close,
            width=10
        )
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))

        # Export frame button
        self.export_button = ttk.Button(
            control_frame,
            text="📷 Export",
            command=self._export_current_frame,
            width=10
        )
        self.export_button.pack(side=tk.LEFT, padx=(0, 5))

        # Frame counter
        self.frame_label = ttk.Label(control_frame, text="Frame: 0/0")
        self.frame_label.pack(side=tk.LEFT, padx=(10, 0))

        # Status label
        self.status_label = ttk.Label(control_frame, text="Loading...")
        self.status_label.pack(side=tk.RIGHT)

    def _check_dependencies(self) -> bool:
        """Check if required dependencies are available."""
        if not HAS_PIL:
            messagebox.showwarning(
                "Missing Dependency",
                "PIL/Pillow is not installed. Falling back to ffplay.",
                parent=self
            )
            return False

        if self.use_opencv and not HAS_CV2:
            # Try ffmpeg method instead
            self.use_opencv = False

        return True

    def _start_preview(self) -> None:
        """Start the video preview worker thread."""
        if self.use_opencv:
            self._worker_thread = threading.Thread(
                target=self._opencv_worker,
                daemon=True
            )
            self.status_label.config(text="OpenCV mode")
        else:
            self._worker_thread = threading.Thread(
                target=self._ffmpeg_worker,
                daemon=True
            )
            self.status_label.config(text="FFmpeg mode")

        self._worker_thread.start()
        self._poll_frame_queue()

    def _opencv_worker(self) -> None:
        """Worker thread using OpenCV for hardware-accelerated decoding."""
        try:
            cap = cv2.VideoCapture(str(self.video_path))

            if not cap.isOpened():
                self._frame_queue.put(None)
                return

            # Get video properties
            self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_delay = 1.0 / fps

            frame_count = 0

            while not self._stop_event.is_set():
                # Handle pause
                if not self._pause_event.is_set():
                    time.sleep(0.1)
                    continue

                # Check frame limit
                if self.max_frames > 0 and frame_count >= self.max_frames:
                    break

                ret, frame = cap.read()

                if not ret:
                    break

                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Resize to preview width
                height, width = frame_rgb.shape[:2]
                aspect_ratio = height / width
                new_height = int(self.preview_width * aspect_ratio)

                if width != self.preview_width:
                    # Use INTER_AREA for better downscaling quality
                    frame_rgb = cv2.resize(
                        frame_rgb,
                        (self.preview_width, new_height),
                        interpolation=cv2.INTER_AREA
                    )

                # Create frame data
                frame_data = FrameData(
                    width=self.preview_width,
                    height=new_height,
                    data=frame_rgb.tobytes(),
                    frame_number=frame_count,
                    timestamp=frame_count / fps
                )

                # Put frame in queue (block if full)
                try:
                    self._frame_queue.put(frame_data, timeout=1.0)
                except queue.Full:
                    continue

                frame_count += 1

                # Maintain frame rate
                time.sleep(frame_delay)

            cap.release()

        except Exception as e:
            logger.error(f"OpenCV worker error: {e}", exc_info=True)
        finally:
            self._frame_queue.put(None)

    def _ffmpeg_worker(self) -> None:
        """Worker thread using ffmpeg for frame extraction."""
        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(self.video_path),
            "-vf", f"scale={self.preview_width}:trunc(ow/a/2)*2",
            "-f", "image2pipe",
            "-vcodec", "ppm",
            "-"
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            self._frame_queue.put(None)
            return

        if not self._process.stdout:
            self._frame_queue.put(None)
            return

        frame_count = 0
        stdout = self._process.stdout

        try:
            while not self._stop_event.is_set():
                # Handle pause
                if not self._pause_event.is_set():
                    time.sleep(0.1)
                    continue

                # Check frame limit
                if self.max_frames > 0 and frame_count >= self.max_frames:
                    break

                # Read PPM header
                magic = stdout.readline()
                if not magic or magic.strip() != b"P6":
                    break

                # Read dimensions
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

                # Read max value
                max_val_line = stdout.readline()
                if not max_val_line:
                    break

                # Read frame data
                frame_size = width * height * 3
                frame_data_bytes = stdout.read(frame_size)

                if len(frame_data_bytes) < frame_size:
                    break

                # Create frame data
                frame_data = FrameData(
                    width=width,
                    height=height,
                    data=frame_data_bytes,
                    frame_number=frame_count,
                    timestamp=0.0
                )

                # Put frame in queue
                try:
                    self._frame_queue.put(frame_data, timeout=1.0)
                except queue.Full:
                    continue

                frame_count += 1

                # Throttle frame rate
                time.sleep(0.033)  # ~30 fps

        except Exception as e:
            logger.error(f"FFmpeg worker error: {e}", exc_info=True)
        finally:
            self._frame_queue.put(None)
            stdout.close()

            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._process.kill()

    def _poll_frame_queue(self) -> None:
        """Poll the frame queue and update display."""
        if self._stop_event.is_set():
            return

        try:
            frame_data = self._frame_queue.get_nowait()
        except queue.Empty:
            self.after(15, self._poll_frame_queue)
            return

        # None signals end of stream
        if frame_data is None:
            self.status_label.config(text="Complete")
            self.play_button.config(state=tk.DISABLED)
            return

        # Update display
        self._display_frame(frame_data)

        # Update UI
        self._current_frame = frame_data.frame_number
        if self._total_frames > 0:
            self.frame_label.config(
                text=f"Frame: {self._current_frame + 1}/{self._total_frames}"
            )
        else:
            self.frame_label.config(text=f"Frame: {self._current_frame + 1}")

        # Continue polling
        self.after(15, self._poll_frame_queue)

    def _display_frame(self, frame_data: FrameData) -> None:
        """Display a frame on the canvas."""
        if not HAS_PIL:
            return

        # Create PIL image
        image = Image.frombytes(
            "RGB",
            (frame_data.width, frame_data.height),
            frame_data.data
        )

        # Store raw image for export functionality
        self._current_image = image

        # Convert to PhotoImage
        self._current_photo = ImageTk.PhotoImage(image)

        # Update canvas size if needed
        if self.canvas.winfo_width() != frame_data.width:
            self.canvas.config(
                width=frame_data.width,
                height=frame_data.height
            )

        # Display on canvas
        self.canvas.delete("all")
        self.canvas.create_image(
            0, 0,
            anchor=tk.NW,
            image=self._current_photo
        )

    def _toggle_play_pause(self) -> None:
        """Toggle play/pause state."""
        if self._is_playing:
            self._pause_event.clear()
            self.play_button.config(text="▶ Play")
            self.status_label.config(text="Paused")
        else:
            self._pause_event.set()
            self.play_button.config(text="⏸ Pause")
            self.status_label.config(text="Playing")

        self._is_playing = not self._is_playing

    def _export_current_frame(self) -> None:
        """Export current frame as PNG or JPEG."""
        if not self._current_image or not HAS_PIL:
            messagebox.showwarning(
                "Export Frame",
                "No frame currently displayed.",
                parent=self
            )
            return

        # Suggest filename based on video name and frame number
        video_stem = self.video_path.stem
        default_name = f"{video_stem}_frame_{self._current_frame:04d}.png"

        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Export Current Frame",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[
                ("PNG Image", "*.png"),
                ("JPEG Image", "*.jpg *.jpeg"),
                ("All Files", "*.*")
            ]
        )

        if not filename:
            return  # User cancelled

        try:
            # Save the raw PIL Image
            self._current_image.save(filename)

            messagebox.showinfo(
                "Export Success",
                f"Frame {self._current_frame} exported successfully!\n\n{filename}",
                parent=self
            )

        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Failed to export frame: {e}",
                parent=self
            )

    def _fallback_to_ffplay(self) -> None:
        """Fallback to external ffplay player."""
        messagebox.showinfo(
            "Preview",
            "Using external ffplay for preview.",
            parent=self
        )

        try:
            subprocess.run(
                [
                    "ffplay",
                    "-autoexit",
                    "-hide_banner",
                    "-loglevel", "error",
                    str(self.video_path)
                ],
                check=False
            )
        except FileNotFoundError:
            messagebox.showerror(
                "Preview Error",
                "Neither PIL/Pillow nor ffplay are available. Cannot preview video.",
                parent=self
            )
        finally:
            self.after(0, self._handle_close)

    def _handle_close(self) -> None:
        """Handle window close event."""
        if self._stop_event.is_set():
            return

        # Stop worker thread
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused

        # Terminate subprocess if exists
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

        # Wait for worker thread
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

        # Call cleanup callback
        if callable(self._on_close):
            try:
                self._on_close()
            except Exception as e:
                logger.error(f"Error in close callback: {e}", exc_info=True)
            finally:
                self._on_close = None

        # Destroy window
        self.destroy()


def create_preview_window(
    master: tk.Tk,
    video_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    on_close: Optional[Callable[[], None]] = None,
    **kwargs
) -> VideoPreviewWidget:
    """
    Convenience function to create a video preview window.

    Args:
        master: Parent Tk window
        video_path: Path to video file
        ffmpeg_bin: Path to ffmpeg binary
        on_close: Callback when window closes
        **kwargs: Additional arguments for VideoPreviewWidget

    Returns:
        VideoPreviewWidget instance
    """
    return VideoPreviewWidget(
        master,
        video_path,
        ffmpeg_bin=ffmpeg_bin,
        on_close=on_close,
        **kwargs
    )


# Compatibility layer for legacy PreviewWindow
class PreviewWindow(VideoPreviewWidget):
    """
    Legacy compatibility wrapper for VideoPreviewWidget.

    Maintains the same interface as the original PreviewWindow
    for backward compatibility.
    """

    def __init__(
        self,
        master: tk.Tk,
        video_path: Path,
        ffmpeg_bin: str,
        *,
        max_frames: int = 360,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(
            master,
            video_path,
            ffmpeg_bin=ffmpeg_bin,
            max_frames=max_frames,
            on_close=on_close,
            preview_width=480,
            use_opencv=True
        )
