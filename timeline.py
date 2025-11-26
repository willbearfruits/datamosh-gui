#!/usr/bin/env python3
"""
Professional video timeline editor for Datamosh GUI

Provides Avidemux/Premiere-style timeline with:
- Frame-by-frame navigation
- Visual I-frame/P-frame markers
- Interactive P-frame duplication controls
- Scrubbing and preview integration
- In/out point markers for glitch effects
- Real-time editing capabilities
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Optional, Callable, List, Dict, Tuple

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class FrameMarker:
    """Represents a frame marker on the timeline"""
    frame_num: int
    frame_type: str  # 'I', 'P', 'B'
    is_keyframe: bool
    timestamp: float
    duplicate_count: int = 0  # For P-frame duplication
    glitch_marker: bool = False


@dataclass
class TimelineRegion:
    """Represents an in/out region for glitch effects"""
    start_frame: int
    end_frame: int
    effect_type: str = "mosh"  # 'mosh', 'duplicate', 'drop'
    color: str = "#ff4444"


class TimelineCanvas(tk.Canvas):
    """
    Professional timeline canvas with frame markers and scrubbing

    Features:
    - Horizontal scrollable timeline
    - Frame thumbnails at regular intervals
    - I-frame markers (vertical blue lines)
    - P-frame markers (vertical green lines)
    - Duplication markers (orange triangles)
    - Scrubber (red playhead line)
    - In/out region highlighting
    - Click to seek, drag to scrub
    """

    def __init__(self, parent, width: int = 800, height: int = 120, **kwargs):
        super().__init__(parent, width=width, height=height, bg="#2b2b2b",
                        highlightthickness=0, **kwargs)

        # Timeline dimensions
        self.timeline_height = height
        self.frame_width = 4  # Pixels per frame
        self.thumbnail_height = 60
        self.marker_area_height = 40

        # Frame data
        self.total_frames = 0
        self.current_frame = 0
        self.fps = 30.0
        self.duration = 0.0

        # Frame markers (I-frames, P-frames, etc)
        self.frame_markers: List[FrameMarker] = []
        self.regions: List[TimelineRegion] = []

        # Callbacks
        self.on_frame_seek: Optional[Callable[[int], None]] = None
        self.on_duplicate_add: Optional[Callable[[int, int], None]] = None
        self.on_region_select: Optional[Callable[[int, int], None]] = None

        # Interaction state
        self.is_scrubbing = False
        self.region_start: Optional[int] = None
        self.selected_marker: Optional[FrameMarker] = None

        # Visual elements
        self.playhead_line = None
        self.selection_rect = None

        # Bind mouse events
        self.bind("<Button-1>", self._on_mouse_down)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Double-Button-1>", self._on_double_click)

        # Scrollbar support
        self.config(scrollregion=(0, 0, 5000, height))

        # Draw initial ruler
        self._draw_ruler()

    def set_video_info(self, total_frames: int, fps: float, duration: float):
        """Set video information for timeline"""
        self.total_frames = total_frames
        self.fps = fps
        self.duration = duration

        # Update canvas size based on total frames
        total_width = max(self.total_frames * self.frame_width, 800)
        self.config(scrollregion=(0, 0, total_width, self.timeline_height))

        # Redraw
        self._redraw_timeline()

    def set_frame_markers(self, markers: List[FrameMarker]):
        """Set frame markers (I-frames, P-frames, etc)"""
        self.frame_markers = sorted(markers, key=lambda m: m.frame_num)
        self._redraw_timeline()

    def add_region(self, region: TimelineRegion):
        """Add an in/out region for effects"""
        self.regions.append(region)
        self._redraw_timeline()

    def clear_regions(self):
        """Clear all regions"""
        self.regions.clear()
        self._redraw_timeline()

    def seek_to_frame(self, frame_num: int):
        """Move playhead to specific frame"""
        self.current_frame = max(0, min(frame_num, self.total_frames - 1))
        self._update_playhead()

        # Auto-scroll to keep playhead visible
        x_pos = self.current_frame * self.frame_width
        self.xview_moveto(x_pos / (self.total_frames * self.frame_width))

    def _redraw_timeline(self):
        """Redraw entire timeline"""
        self.delete("all")

        # Draw ruler
        self._draw_ruler()

        # Draw regions first (background)
        self._draw_regions()

        # Draw frame markers
        self._draw_frame_markers()

        # Draw playhead last (foreground)
        self._update_playhead()

    def _draw_ruler(self):
        """Draw time ruler at top"""
        ruler_height = 20

        # Background
        self.create_rectangle(0, 0, self.winfo_width(), ruler_height,
                             fill="#1e1e1e", outline="")

        # Time markers
        if self.total_frames > 0 and self.fps > 0:
            # Draw markers every second
            frames_per_second = int(self.fps)
            for i in range(0, self.total_frames, frames_per_second):
                x = i * self.frame_width
                time_sec = i / self.fps

                # Major tick every second
                self.create_line(x, ruler_height - 10, x, ruler_height,
                               fill="#888888", width=1)

                # Time label
                time_str = f"{int(time_sec // 60):02d}:{int(time_sec % 60):02d}"
                self.create_text(x + 2, 5, text=time_str, anchor="nw",
                               fill="#cccccc", font=("monospace", 8))

    def _draw_regions(self):
        """Draw in/out regions for effects"""
        region_top = 20
        region_bottom = self.timeline_height - self.marker_area_height

        for region in self.regions:
            x1 = region.start_frame * self.frame_width
            x2 = region.end_frame * self.frame_width

            # Draw semi-transparent region
            self.create_rectangle(x1, region_top, x2, region_bottom,
                                fill=region.color, outline=region.color,
                                stipple="gray50", tags="region")

            # Draw boundary lines
            self.create_line(x1, region_top, x1, region_bottom,
                           fill=region.color, width=2)
            self.create_line(x2, region_top, x2, region_bottom,
                           fill=region.color, width=2)

            # Effect label
            mid_x = (x1 + x2) / 2
            self.create_text(mid_x, region_top + 15,
                           text=region.effect_type.upper(),
                           fill="#ffffff", font=("Arial", 10, "bold"),
                           tags="region")

    def _draw_frame_markers(self):
        """Draw I-frame and P-frame markers"""
        marker_top = self.timeline_height - self.marker_area_height
        marker_bottom = self.timeline_height

        # Draw background for marker area
        self.create_rectangle(0, marker_top, self.winfo_width(), marker_bottom,
                             fill="#1a1a1a", outline="")

        for marker in self.frame_markers:
            x = marker.frame_num * self.frame_width

            # Draw I-frame markers (keyframes)
            if marker.is_keyframe or marker.frame_type == 'I':
                # Blue vertical line for I-frames
                self.create_line(x, marker_top, x, marker_bottom,
                               fill="#4488ff", width=2, tags="i-frame")

                # Triangle at top
                self.create_polygon(x, marker_top,
                                  x - 4, marker_top + 8,
                                  x + 4, marker_top + 8,
                                  fill="#4488ff", outline="", tags="i-frame")

            # Draw P-frame markers
            elif marker.frame_type == 'P':
                # Green tick for P-frames
                self.create_line(x, marker_top + 5, x, marker_bottom - 5,
                               fill="#44ff44", width=1, tags="p-frame")

            # Draw duplication markers
            if marker.duplicate_count > 0:
                # Orange triangle for duplicated frames
                self.create_polygon(x, marker_bottom,
                                  x - 5, marker_bottom - 10,
                                  x + 5, marker_bottom - 10,
                                  fill="#ff8800", outline="", tags="duplicate")

                # Duplication count label
                if marker.duplicate_count > 1:
                    self.create_text(x, marker_bottom - 5,
                                   text=f"×{marker.duplicate_count}",
                                   fill="#ffffff", font=("Arial", 8, "bold"),
                                   tags="duplicate")

            # Draw glitch markers
            if marker.glitch_marker:
                # Red exclamation mark
                self.create_text(x, marker_top + 15, text="!",
                               fill="#ff0000", font=("Arial", 14, "bold"),
                               tags="glitch")

    def _update_playhead(self):
        """Update playhead position"""
        # Remove old playhead
        self.delete("playhead")

        # Draw new playhead
        x = self.current_frame * self.frame_width
        self.create_line(x, 0, x, self.timeline_height,
                       fill="#ff0000", width=2, tags="playhead")

        # Playhead triangle at top
        self.create_polygon(x, 0, x - 6, 12, x + 6, 12,
                          fill="#ff0000", outline="", tags="playhead")

        # Frame number
        self.create_text(x, 25, text=f"F{self.current_frame}",
                       fill="#ffffff", font=("Arial", 9, "bold"),
                       tags="playhead")

    def _frame_from_x(self, x: int) -> int:
        """Convert canvas x coordinate to frame number"""
        canvas_x = self.canvasx(x)
        frame = int(canvas_x / self.frame_width)
        return max(0, min(frame, self.total_frames - 1))

    def _on_mouse_down(self, event):
        """Handle mouse click - seek to frame"""
        frame = self._frame_from_x(event.x)
        self.current_frame = frame
        self.is_scrubbing = True
        self._update_playhead()

        if self.on_frame_seek:
            self.on_frame_seek(frame)

    def _on_mouse_drag(self, event):
        """Handle mouse drag - scrub through timeline"""
        if not self.is_scrubbing:
            return

        frame = self._frame_from_x(event.x)
        if frame != self.current_frame:
            self.current_frame = frame
            self._update_playhead()

            if self.on_frame_seek:
                self.on_frame_seek(frame)

    def _on_mouse_up(self, event):
        """Handle mouse release"""
        self.is_scrubbing = False

    def _on_right_click(self, event):
        """Handle right click - show context menu"""
        frame = self._frame_from_x(event.x)

        # Create context menu
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"Frame {frame}", state="disabled")
        menu.add_separator()
        menu.add_command(label="Set In Point",
                        command=lambda: self._set_in_point(frame))
        menu.add_command(label="Set Out Point",
                        command=lambda: self._set_out_point(frame))
        menu.add_separator()
        menu.add_command(label="Add P-frame Duplication (×5)",
                        command=lambda: self._add_duplication(frame, 5))
        menu.add_command(label="Add P-frame Duplication (×10)",
                        command=lambda: self._add_duplication(frame, 10))
        menu.add_command(label="Add P-frame Duplication (×20)",
                        command=lambda: self._add_duplication(frame, 20))
        menu.add_separator()
        menu.add_command(label="Add Glitch Marker",
                        command=lambda: self._add_glitch_marker(frame))
        menu.add_command(label="Clear All Markers",
                        command=self._clear_markers)

        menu.post(event.x_root, event.y_root)

    def _on_double_click(self, event):
        """Handle double click - find nearest keyframe"""
        frame = self._frame_from_x(event.x)

        # Find nearest I-frame
        nearest = None
        min_dist = float('inf')

        for marker in self.frame_markers:
            if marker.is_keyframe or marker.frame_type == 'I':
                dist = abs(marker.frame_num - frame)
                if dist < min_dist:
                    min_dist = dist
                    nearest = marker

        if nearest:
            self.seek_to_frame(nearest.frame_num)
            if self.on_frame_seek:
                self.on_frame_seek(nearest.frame_num)

    def _set_in_point(self, frame: int):
        """Set in point for region"""
        self.region_start = frame
        # Visual feedback
        self._update_playhead()

    def _set_out_point(self, frame: int):
        """Set out point for region"""
        if self.region_start is not None:
            region = TimelineRegion(
                start_frame=min(self.region_start, frame),
                end_frame=max(self.region_start, frame),
                effect_type="mosh",
                color="#ff4444"
            )
            self.add_region(region)

            if self.on_region_select:
                self.on_region_select(region.start_frame, region.end_frame)

            self.region_start = None

    def _add_duplication(self, frame: int, count: int):
        """Add P-frame duplication marker"""
        # Find or create marker at this frame
        marker = None
        for m in self.frame_markers:
            if m.frame_num == frame:
                marker = m
                break

        if marker is None:
            marker = FrameMarker(
                frame_num=frame,
                frame_type='P',
                is_keyframe=False,
                timestamp=frame / self.fps,
                duplicate_count=count
            )
            self.frame_markers.append(marker)
        else:
            marker.duplicate_count = count

        self._redraw_timeline()

        if self.on_duplicate_add:
            self.on_duplicate_add(frame, count)

    def _add_glitch_marker(self, frame: int):
        """Add glitch effect marker"""
        # Find or create marker at this frame
        marker = None
        for m in self.frame_markers:
            if m.frame_num == frame:
                marker = m
                break

        if marker is None:
            marker = FrameMarker(
                frame_num=frame,
                frame_type='P',
                is_keyframe=False,
                timestamp=frame / self.fps,
                glitch_marker=True
            )
            self.frame_markers.append(marker)
        else:
            marker.glitch_marker = True

        self._redraw_timeline()

    def _clear_markers(self):
        """Clear all user-added markers"""
        # Keep I-frame markers, clear duplications and glitches
        for marker in self.frame_markers:
            marker.duplicate_count = 0
            marker.glitch_marker = False

        self._redraw_timeline()


class TimelineWidget(ttk.Frame):
    """
    Complete timeline widget with controls

    Includes:
    - Timeline canvas
    - Playback controls
    - Frame counter
    - Zoom controls
    - Horizontal scrollbar
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Top control bar
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)

        # Frame counter
        self.frame_label = ttk.Label(control_frame, text="Frame: 0 / 0",
                                     font=("monospace", 10))
        self.frame_label.pack(side=tk.LEFT, padx=5)

        # Time counter
        self.time_label = ttk.Label(control_frame, text="00:00.000",
                                    font=("monospace", 10))
        self.time_label.pack(side=tk.LEFT, padx=5)

        # Playback controls
        ttk.Button(control_frame, text="◀◀", width=4,
                  command=self._prev_keyframe).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="◀", width=4,
                  command=self._prev_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="▶", width=4,
                  command=self._next_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="▶▶", width=4,
                  command=self._next_keyframe).pack(side=tk.LEFT, padx=2)

        # Zoom controls
        ttk.Label(control_frame, text="Zoom:").pack(side=tk.RIGHT, padx=(10, 2))
        self.zoom_scale = ttk.Scale(control_frame, from_=1, to=10,
                                    orient=tk.HORIZONTAL, length=100,
                                    command=self._on_zoom)
        self.zoom_scale.pack(side=tk.RIGHT, padx=2)

        # Timeline canvas with scrollbar
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=2)

        self.timeline = TimelineCanvas(canvas_frame, width=800, height=120)
        self.timeline.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL,
                                 command=self.timeline.xview)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.timeline.config(xscrollcommand=scrollbar.set)

        # Connect timeline callbacks
        self.timeline.on_frame_seek = self._on_frame_seek

        # Set initial zoom AFTER timeline is created
        self.zoom_scale.set(4)

        # Callbacks to parent
        self.on_frame_change: Optional[Callable[[int], None]] = None

    def load_video(self, video_path: Path):
        """Load video and extract frame information"""
        # Use ffprobe to get video info
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', str(video_path)
            ], capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                return

            data = json.loads(result.stdout)

            # Extract video stream info
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                return

            # Get FPS
            fps_str = video_stream.get('r_frame_rate', '30/1')
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den else 30.0

            # Get duration and frame count
            duration = float(video_stream.get('duration', 0))
            nb_frames = int(video_stream.get('nb_frames', 0))

            if nb_frames == 0 and duration > 0:
                nb_frames = int(duration * fps)

            # Set timeline info
            self.timeline.set_video_info(nb_frames, fps, duration)
            self._update_counters()

            # Extract keyframes in background
            threading.Thread(target=self._extract_keyframes,
                           args=(video_path,), daemon=True).start()

        except Exception as e:
            logger.error(f"Error loading video info: {e}", exc_info=True)

    def _extract_keyframes(self, video_path: Path):
        """Extract keyframe positions using ffprobe"""
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-select_streams', 'v:0',
                '-show_entries', 'packet=pts_time,flags',
                '-of', 'json', str(video_path)
            ], capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return

            data = json.loads(result.stdout)
            packets = data.get('packets', [])

            markers = []
            for i, packet in enumerate(packets):
                flags = packet.get('flags', '')
                is_keyframe = 'K' in flags

                if is_keyframe or i % 10 == 0:  # Sample every 10th frame
                    pts_time = float(packet.get('pts_time', 0))
                    frame_num = int(pts_time * self.timeline.fps)

                    marker = FrameMarker(
                        frame_num=frame_num,
                        frame_type='I' if is_keyframe else 'P',
                        is_keyframe=is_keyframe,
                        timestamp=pts_time
                    )
                    markers.append(marker)

            # Update timeline on main thread
            self.timeline.after(0, lambda: self.timeline.set_frame_markers(markers))

        except Exception as e:
            logger.error(f"Error extracting keyframes: {e}", exc_info=True)

    def _on_frame_seek(self, frame: int):
        """Handle frame seek from timeline"""
        self._update_counters()

        if self.on_frame_change:
            self.on_frame_change(frame)

    def _update_counters(self):
        """Update frame and time counters"""
        frame = self.timeline.current_frame
        total = self.timeline.total_frames
        fps = self.timeline.fps

        self.frame_label.config(text=f"Frame: {frame} / {total}")

        if fps > 0:
            time_sec = frame / fps
            minutes = int(time_sec // 60)
            seconds = time_sec % 60
            self.time_label.config(text=f"{minutes:02d}:{seconds:06.3f}")

    def _prev_frame(self):
        """Go to previous frame"""
        self.timeline.seek_to_frame(self.timeline.current_frame - 1)
        self._update_counters()

        if self.on_frame_change:
            self.on_frame_change(self.timeline.current_frame)

    def _next_frame(self):
        """Go to next frame"""
        self.timeline.seek_to_frame(self.timeline.current_frame + 1)
        self._update_counters()

        if self.on_frame_change:
            self.on_frame_change(self.timeline.current_frame)

    def _prev_keyframe(self):
        """Go to previous I-frame"""
        current = self.timeline.current_frame

        # Find previous keyframe
        prev_keyframe = None
        for marker in reversed(self.timeline.frame_markers):
            if (marker.is_keyframe or marker.frame_type == 'I') and marker.frame_num < current:
                prev_keyframe = marker
                break

        if prev_keyframe:
            self.timeline.seek_to_frame(prev_keyframe.frame_num)
            self._update_counters()

            if self.on_frame_change:
                self.on_frame_change(prev_keyframe.frame_num)

    def _next_keyframe(self):
        """Go to next I-frame"""
        current = self.timeline.current_frame

        # Find next keyframe
        next_keyframe = None
        for marker in self.timeline.frame_markers:
            if (marker.is_keyframe or marker.frame_type == 'I') and marker.frame_num > current:
                next_keyframe = marker
                break

        if next_keyframe:
            self.timeline.seek_to_frame(next_keyframe.frame_num)
            self._update_counters()

            if self.on_frame_change:
                self.on_frame_change(next_keyframe.frame_num)

    def _on_zoom(self, value):
        """Handle zoom change"""
        zoom = float(value)
        # Access the timeline canvas (which is self.timeline)
        canvas = self.timeline
        canvas.frame_width = int(zoom)

        # Update scroll region
        total_width = max(canvas.total_frames * canvas.frame_width, 800)
        canvas.config(scrollregion=(0, 0, total_width, canvas.timeline_height))

        canvas._redraw_timeline()


# Example usage
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Timeline Test")
    root.geometry("900x250")

    timeline = TimelineWidget(root)
    timeline.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Test with dummy data
    timeline.timeline.set_video_info(300, 30.0, 10.0)

    # Add some test markers
    markers = [
        FrameMarker(0, 'I', True, 0.0),
        FrameMarker(48, 'I', True, 1.6),
        FrameMarker(96, 'I', True, 3.2),
        FrameMarker(144, 'I', True, 4.8),
        FrameMarker(192, 'I', True, 6.4),
        FrameMarker(240, 'I', True, 8.0),
    ]
    timeline.timeline.set_frame_markers(markers)

    def on_frame_change(frame):
        print(f"Frame changed to: {frame}")

    timeline.on_frame_change = on_frame_change

    root.mainloop()
