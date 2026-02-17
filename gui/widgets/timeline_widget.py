"""Editable NLE timeline: drag/drop, reordering, cut-at-playhead, and frame-level viz."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QRectF, Qt, Signal, QPointF
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QKeySequence,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

import mosh
from gui.models.clip_model import ClipListModel
from gui.models.project import Project, TimelineItem
from gui.theme import TEXT_DIM
from gui.workers.keyframe_analyzer import FrameInfo, KeyframeAnalyzer

# -- Clip colours (cycle for different clips) --
CLIP_COLORS = [
    (QColor(55, 100, 180), QColor(40, 75, 140)),      # blue
    (QColor(150, 65, 150), QColor(110, 45, 110)),     # purple
    (QColor(50, 140, 110), QColor(35, 105, 80)),      # teal
    (QColor(170, 110, 45), QColor(130, 80, 30)),      # amber
    (QColor(65, 140, 65), QColor(45, 105, 45)),       # green
    (QColor(140, 55, 85), QColor(105, 40, 65)),       # wine
]

SELECTED_BORDER = QColor(0, 160, 255)
SELECTED_GLOW = QColor(0, 140, 255, 40)
CLIP_TEXT = QColor(230, 230, 230)
CLIP_TEXT_DIM = QColor(180, 180, 180)

KEPT_KEY = QColor(80, 165, 255)
DROPPED_KEY = QColor(210, 55, 55)
P_FRAME = QColor(75, 195, 75)
DUP_MARK = QColor(255, 170, 35)

PLAYHEAD_COLOR = QColor(255, 55, 55)
PLAYHEAD_HEAD = QColor(255, 80, 80)
RULER_BG = QColor(32, 32, 36)
RULER_TICK = QColor(80, 80, 80)
RULER_TEXT = QColor(130, 130, 130)
TRACK_BG = QColor(18, 18, 20)

RULER_H = 28
TRACK_TOP = RULER_H
PLAYHEAD_HEAD_W = 12
PLAYHEAD_HEAD_H = 10


def _effective_keep_limit(keep_first: int, drop_first: bool) -> int:
    """First keyframe is controlled by drop_first; slider controls extra keys."""
    return max(0, keep_first) + (0 if drop_first else 1)


@dataclass
class ClipRegion:
    """Layout info for one timeline segment."""

    timeline_index: int
    clip_row: int
    label: str
    frames: list[FrameInfo] = field(default_factory=list)
    frame_count: int = 1
    keep_first: int = 0
    dup_count: int = 0
    dup_gap: int = 1
    drop_first: bool = False
    fps: float = 30.0
    duration_sec: float = 0.0
    loading: bool = True
    color_top: QColor = field(default_factory=lambda: CLIP_COLORS[0][0])
    color_bot: QColor = field(default_factory=lambda: CLIP_COLORS[0][1])


class TimelineCanvas(QWidget):
    """Interactive timeline canvas with zoom/pan/drag/drop/edit primitives."""

    frame_clicked = Signal(int)
    clip_clicked = Signal(int)
    timeline_item_clicked = Signal(int)
    timeline_item_moved = Signal(int, int)
    timeline_clip_dropped = Signal(int, int)
    viewport_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.setAcceptDrops(True)

        self._regions: list[ClipRegion] = []
        self._selected_item: int = -1
        self._playhead_sec: float = 0.0
        self._total_duration: float = 0.0

        self._dragging_playhead = False
        self._panning = False
        self._pan_start_x: float = 0
        self._pan_start_offset: float = 0

        # Timeline item drag/reorder state
        self._drag_candidate_item: int = -1
        self._drag_start_pos = QPointF()
        self._dragging_item = False
        self._drop_index: int = -1
        self._external_drop_index: int = -1

        # View: pixels_per_second and scroll offset in seconds
        self._pps: float = 100.0
        self._scroll_sec: float = 0.0

        self._font = QFont("Sans", 9)
        self._font_small = QFont("Sans", 7)
        self._font_bold = QFont("Sans", 9, QFont.Weight.Bold)

    # -- Public API --------------------------------------------------------

    def set_regions(self, regions: list[ClipRegion]) -> None:
        self._regions = regions
        self._recompute_duration()
        self._clamp_scroll()
        self.update()
        self.viewport_changed.emit()

    def set_selected_item(self, index: int) -> None:
        self._selected_item = index
        self.update()

    def set_playhead(self, frame: int) -> None:
        if not self._regions:
            self._playhead_sec = 0.0
            self.update()
            return

        remaining = max(0, frame)
        t_offset = 0.0
        for region in self._regions:
            n = max(1, region.frame_count)
            if remaining < n:
                if region.fps > 0:
                    local_sec = remaining / region.fps
                else:
                    local_sec = (remaining / n) * region.duration_sec
                self._playhead_sec = t_offset + min(max(0.0, local_sec), region.duration_sec)
                self.update()
                return
            remaining -= n
            t_offset += region.duration_sec

        self._playhead_sec = self._total_duration
        self.update()

    def clear(self) -> None:
        self._regions.clear()
        self._playhead_sec = 0.0
        self._total_duration = 0.0
        self._scroll_sec = 0.0
        self._selected_item = -1
        self.update()
        self.viewport_changed.emit()

    def get_scroll_fraction(self) -> float:
        visible = self.width() / self._pps
        scrollable = max(0.001, self._total_duration - visible)
        if scrollable <= 0:
            return 0.0
        return self._scroll_sec / scrollable

    def set_scroll_fraction(self, frac: float) -> None:
        visible = self.width() / self._pps
        scrollable = max(0.0, self._total_duration - visible)
        self._scroll_sec = max(0.0, min(frac * scrollable, scrollable))
        self.update()

    def get_visible_fraction(self) -> float:
        if self._total_duration <= 0:
            return 1.0
        return min(1.0, (self.width() / self._pps) / self._total_duration)

    def current_playhead_location(self) -> tuple[int, int]:
        """Return (timeline_index, local_frame) for the current playhead."""
        if not self._regions:
            return -1, 0

        t_offset = 0.0
        for idx, region in enumerate(self._regions):
            right = t_offset + region.duration_sec
            if self._playhead_sec < right or idx == len(self._regions) - 1:
                local_sec = max(0.0, min(self._playhead_sec - t_offset, region.duration_sec))
                if region.fps > 0:
                    local_frame = int(local_sec * region.fps)
                else:
                    local_frame = int((local_sec / max(region.duration_sec, 1e-6)) * region.frame_count)
                local_frame = max(0, min(local_frame, max(0, region.frame_count - 1)))
                return region.timeline_index, local_frame
            t_offset = right

        return -1, 0

    def timeline_item_at_pos(self, pos: QPointF) -> int:
        """Return timeline index for a canvas coordinate, or -1."""
        if pos.y() < RULER_H or pos.y() > self.height():
            return -1
        sec = self._x_to_sec(pos.x())
        idx, _ = self._clip_at_sec(sec)
        return idx

    # -- Internals ---------------------------------------------------------

    def _recompute_duration(self) -> None:
        self._total_duration = sum(r.duration_sec for r in self._regions)

    def _sec_to_x(self, sec: float) -> float:
        return (sec - self._scroll_sec) * self._pps

    def _x_to_sec(self, x: float) -> float:
        return x / self._pps + self._scroll_sec

    def _track_height(self) -> float:
        return max(30, self.height() - RULER_H - 4)

    def _clamp_scroll(self) -> None:
        visible_sec = self.width() / self._pps
        max_scroll = max(0.0, self._total_duration - visible_sec)
        self._scroll_sec = max(0.0, min(self._scroll_sec, max_scroll))

    def _clip_at_sec(self, sec: float) -> tuple[int, ClipRegion | None]:
        t = 0.0
        for r in self._regions:
            if t <= sec < t + r.duration_sec:
                return r.timeline_index, r
            t += r.duration_sec
        return -1, None

    def _insert_index_for_sec(self, sec: float) -> int:
        if not self._regions:
            return 0
        if sec <= 0:
            return 0

        t = 0.0
        for i, r in enumerate(self._regions):
            mid = t + (r.duration_sec / 2.0)
            if sec < mid:
                return i
            t += r.duration_sec
        return len(self._regions)

    def _emit_frame_for_sec(self, sec: float) -> None:
        if not self._regions:
            self.frame_clicked.emit(0)
            return

        frame_offset = 0
        t_offset = 0.0
        for idx, region in enumerate(self._regions):
            right = t_offset + region.duration_sec
            if sec < right or idx == len(self._regions) - 1:
                local_sec = max(0.0, min(sec - t_offset, region.duration_sec))
                if region.fps > 0:
                    local = int(local_sec * region.fps)
                else:
                    local = int((local_sec / max(region.duration_sec, 1e-6)) * region.frame_count)
                local = max(0, min(local, max(0, region.frame_count - 1)))
                self.frame_clicked.emit(frame_offset + local)
                return
            frame_offset += max(1, region.frame_count)
            t_offset = right

        self.frame_clicked.emit(max(0, frame_offset - 1))

    # -- Painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, TRACK_BG)

        if not self._regions or self._total_duration <= 0:
            p.setFont(self._font)
            p.setPen(TEXT_DIM)
            p.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "Drag clips from bin to timeline",
            )
            p.end()
            return

        self._draw_ruler(p, w)
        self._draw_clips(p, w, h)
        self._draw_insert_marker(p, w, h)
        self._draw_playhead(p, w, h)

        p.end()

    def _draw_ruler(self, p: QPainter, w: int) -> None:
        p.fillRect(0, 0, w, RULER_H, RULER_BG)

        target_px = 100
        sec_per_tick = target_px / self._pps
        nice = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
        for n in nice:
            if n >= sec_per_tick:
                sec_per_tick = n
                break
        else:
            sec_per_tick = nice[-1]

        p.setFont(self._font_small)
        fm = QFontMetrics(self._font_small)

        start = int(self._scroll_sec / sec_per_tick) * sec_per_tick
        t = start
        while True:
            x = self._sec_to_x(t)
            if x > w + 10:
                break
            if x >= -10:
                p.setPen(QPen(RULER_TICK, 1))
                p.drawLine(int(x), RULER_H - 8, int(x), RULER_H)

                if t >= 60:
                    label = f"{int(t // 60)}:{int(t % 60):02d}"
                elif sec_per_tick >= 1:
                    label = f"{t:.0f}s"
                else:
                    label = f"{t:.2f}s"
                tw = fm.horizontalAdvance(label)
                p.setPen(RULER_TEXT)
                p.drawText(int(x - tw / 2), RULER_H - 10, label)

                for sub in range(1, 4):
                    sx = self._sec_to_x(t + sub * sec_per_tick / 4)
                    if 0 <= sx <= w:
                        p.setPen(QPen(QColor(55, 55, 55), 1))
                        p.drawLine(int(sx), RULER_H - 3, int(sx), RULER_H)

            t += sec_per_tick

        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.drawLine(0, RULER_H - 1, w, RULER_H - 1)

    def _draw_clips(self, p: QPainter, w: int, h: int) -> None:
        track_h = self._track_height()
        t_offset = 0.0

        for r in self._regions:
            x_start = self._sec_to_x(t_offset)
            x_end = self._sec_to_x(t_offset + r.duration_sec)
            clip_w = x_end - x_start
            t_offset += r.duration_sec

            if x_end < 0 or x_start > w:
                continue

            rect = QRectF(x_start + 1, TRACK_TOP + 2, clip_w - 2, track_h - 4)
            self._draw_clip_block(p, r, rect)

    def _draw_clip_block(self, p: QPainter, r: ClipRegion, rect: QRectF) -> None:
        is_selected = r.timeline_index == self._selected_item

        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        top_c = QColor(r.color_top)
        bot_c = QColor(r.color_bot)
        if is_selected:
            top_c = top_c.lighter(130)
            bot_c = bot_c.lighter(130)
        grad.setColorAt(0, top_c)
        grad.setColorAt(1, bot_c)

        path = QPainterPath()
        path.addRoundedRect(rect, 5, 5)
        p.fillPath(path, grad)

        if is_selected:
            p.setPen(QPen(SELECTED_BORDER, 2))
            p.drawPath(path)
            glow_rect = rect.adjusted(2, 2, -2, -2)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, 4, 4)
            p.fillPath(glow_path, SELECTED_GLOW)
        else:
            p.setPen(QPen(QColor(60, 60, 65), 1))
            p.drawPath(path)

        p.save()
        p.setClipPath(path)

        # Header
        header_h = 20
        header_rect = QRectF(rect.left(), rect.top(), rect.width(), header_h)
        header_grad = QLinearGradient(0, rect.top(), 0, rect.top() + header_h)
        header_grad.setColorAt(0, QColor(255, 255, 255, 25))
        header_grad.setColorAt(1, QColor(0, 0, 0, 20))
        p.fillRect(header_rect, header_grad)

        p.setFont(self._font_bold)
        fm = QFontMetrics(self._font_bold)
        label = r.label + (" ..." if r.loading else "")
        avail = rect.width() - 12
        if fm.horizontalAdvance(label) > avail:
            label = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(avail))
        p.setPen(CLIP_TEXT)
        p.drawText(int(rect.left() + 6), int(rect.top() + fm.ascent() + 3), label)

        p.setFont(self._font_small)
        fm_s = QFontMetrics(self._font_small)
        dur_str = self._format_duration(r.duration_sec)
        dur_str += f"  ({r.frame_count}f)"
        dur_w = fm_s.horizontalAdvance(dur_str)
        if dur_w < rect.width() - 12:
            p.setPen(CLIP_TEXT_DIM)
            p.drawText(int(rect.right() - dur_w - 6), int(rect.top() + fm_s.ascent() + 3), dur_str)

        # Cut boundary indicator: drop first I-frame at segment start
        if r.drop_first:
            p.setPen(QPen(DROPPED_KEY, 2))
            p.drawLine(int(rect.left() + 2), int(rect.top() + 2), int(rect.left() + 2), int(rect.bottom() - 2))
            if rect.width() > 92:
                p.setPen(QColor(255, 205, 205))
                p.drawText(int(rect.left() + 8), int(rect.top() + fm_s.ascent() + 14), "drop I")

        body_top = rect.top() + header_h + 2
        body_h = rect.height() - header_h - 4
        if body_h > 10 and r.frames:
            self._draw_frame_viz(p, r, rect.left(), rect.width(), body_top, body_h)

        p.restore()

    def _draw_frame_viz(
        self,
        p: QPainter,
        r: ClipRegion,
        x_offset: float,
        clip_w: float,
        y_top: float,
        height: float,
    ) -> None:
        n = len(r.frames)
        if n <= 0:
            return

        px_per_frame = clip_w / n

        if px_per_frame >= 3:
            key_count = 0
            p_count = 0
            keep_limit = _effective_keep_limit(r.keep_first, r.drop_first)
            for i, frame in enumerate(r.frames):
                fx = x_offset + i * px_per_frame
                if fx > x_offset + clip_w:
                    break

                if frame.is_keyframe:
                    keep_key = key_count < keep_limit
                    if r.drop_first and key_count == 0:
                        keep_key = False
                    color = KEPT_KEY if keep_key else DROPPED_KEY
                    bar_h = height
                    key_count += 1
                else:
                    color = P_FRAME
                    bar_h = height * 0.45
                    p_count += 1

                fy = y_top + (height - bar_h)
                bar_w = max(px_per_frame - 1, 1.5)

                if px_per_frame >= 5:
                    bp = QPainterPath()
                    bp.addRoundedRect(QRectF(fx, fy, bar_w, bar_h), 1.5, 1.5)
                    p.fillPath(bp, color)
                else:
                    p.fillRect(QRectF(fx, fy, bar_w, bar_h), color)

                if (
                    not frame.is_keyframe
                    and r.dup_count > 0
                    and r.dup_gap > 0
                    and p_count % r.dup_gap == 0
                ):
                    p.fillRect(QRectF(fx, y_top, max(bar_w, 2), 3), DUP_MARK)
        else:
            buckets = max(1, int(clip_w / 2))
            frames_per_bucket = max(1, n / buckets)
            for b in range(buckets):
                bx = x_offset + b * (clip_w / buckets)
                f_start = int(b * frames_per_bucket)
                f_end = min(n, int((b + 1) * frames_per_bucket))
                if f_start >= f_end:
                    continue

                chunk = r.frames[f_start:f_end]
                n_keys = sum(1 for f in chunk if f.is_keyframe)
                n_p = len(chunk) - n_keys
                total = len(chunk)

                bw = max(clip_w / buckets - 0.5, 1)
                p_frac = n_p / total if total > 0 else 0
                p_h = height * 0.4 * p_frac
                if p_h > 1:
                    p.fillRect(
                        QRectF(bx, y_top + height - p_h, bw, p_h),
                        QColor(P_FRAME.red(), P_FRAME.green(), P_FRAME.blue(), 120),
                    )

                if n_keys > 0:
                    k_h = height * 0.8 * (n_keys / total)
                    key_color = QColor(KEPT_KEY.red(), KEPT_KEY.green(), KEPT_KEY.blue(), 160)
                    p.fillRect(QRectF(bx, y_top + height - p_h - k_h, bw, k_h), key_color)

    def _draw_insert_marker(self, p: QPainter, w: int, h: int) -> None:
        marker = self._external_drop_index
        if self._dragging_item:
            marker = self._drop_index
        if marker < 0:
            return

        t = 0.0
        for i, region in enumerate(self._regions):
            if i >= marker:
                break
            t += region.duration_sec
        x = self._sec_to_x(t)

        p.setPen(QPen(QColor(255, 190, 60), 2, Qt.PenStyle.DashLine))
        p.drawLine(int(x), TRACK_TOP + 1, int(x), h - 2)

    def _draw_playhead(self, p: QPainter, w: int, h: int) -> None:
        if self._total_duration <= 0:
            return

        px = self._sec_to_x(self._playhead_sec)
        if px < -20 or px > w + 20:
            return

        p.setPen(QPen(PLAYHEAD_COLOR, 2))
        p.drawLine(int(px), 0, int(px), h)

        tri = QPainterPath()
        tri.moveTo(px - PLAYHEAD_HEAD_W / 2, 0)
        tri.lineTo(px + PLAYHEAD_HEAD_W / 2, 0)
        tri.lineTo(px, PLAYHEAD_HEAD_H)
        tri.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(PLAYHEAD_HEAD)
        p.drawPath(tri)

        p.setFont(self._font_small)
        fm = QFontMetrics(self._font_small)
        t_label = self._format_duration(self._playhead_sec)
        tw = fm.horizontalAdvance(t_label)
        tx = px + 8
        if tx + tw > w:
            tx = px - tw - 8
        p.setPen(QColor(220, 220, 220))
        p.drawText(int(tx), PLAYHEAD_HEAD_H + 2 + fm.ascent(), t_label)

    @staticmethod
    def _format_duration(sec: float) -> str:
        if sec >= 60:
            return f"{int(sec // 60)}:{sec % 60:05.2f}"
        return f"{sec:.2f}s"

    # -- Mouse interaction -------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            sec = self._x_to_sec(event.position().x())
            y = event.position().y()

            if y < RULER_H:
                self._dragging_playhead = True
                self._playhead_sec = max(0.0, min(sec, self._total_duration))
                self._emit_frame_for_sec(self._playhead_sec)
                self.update()
                return

            if sec < 0 or sec > self._total_duration:
                return

            item_idx, region = self._clip_at_sec(sec)
            self._playhead_sec = max(0.0, min(sec, self._total_duration))
            self._emit_frame_for_sec(self._playhead_sec)

            if item_idx >= 0 and region is not None:
                self._selected_item = item_idx
                self.timeline_item_clicked.emit(item_idx)
                if region.clip_row >= 0:
                    self.clip_clicked.emit(region.clip_row)
                self._drag_candidate_item = item_idx
                self._drag_start_pos = event.position()
                self._drop_index = item_idx
            else:
                self._dragging_playhead = True

            self.update()
            return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start_x = event.position().x()
            self._pan_start_offset = self._scroll_sec
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_candidate_item >= 0 and not self._dragging_item:
            dx = abs(event.position().x() - self._drag_start_pos.x())
            dy = abs(event.position().y() - self._drag_start_pos.y())
            if dx + dy >= 6:
                self._dragging_item = True

        if self._dragging_item:
            sec = self._x_to_sec(event.position().x())
            self._drop_index = self._insert_index_for_sec(sec)
            self.update()
            return

        if self._dragging_playhead:
            sec = self._x_to_sec(event.position().x())
            self._playhead_sec = max(0.0, min(sec, self._total_duration))
            self._emit_frame_for_sec(self._playhead_sec)
            self.update()
            return

        if self._panning:
            dx = event.position().x() - self._pan_start_x
            self._scroll_sec = self._pan_start_offset - dx / self._pps
            self._clamp_scroll()
            self.update()
            self.viewport_changed.emit()
            return

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_item:
            if self._drag_candidate_item >= 0 and self._drop_index >= 0:
                self.timeline_item_moved.emit(self._drag_candidate_item, self._drop_index)

        self._dragging_playhead = False
        self._drag_candidate_item = -1
        self._dragging_item = False
        self._drop_index = -1

        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        mouse_x = event.position().x()
        sec_at_mouse = self._x_to_sec(mouse_x)

        factor = 1.25 if delta > 0 else 1.0 / 1.25
        self._pps = max(5.0, min(self._pps * factor, 5000.0))

        self._scroll_sec = sec_at_mouse - mouse_x / self._pps
        self._clamp_scroll()

        self.update()
        self.viewport_changed.emit()

    # -- Drag/drop from bin -----------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(ClipListModel.MIME_TYPE):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if not event.mimeData().hasFormat(ClipListModel.MIME_TYPE):
            event.ignore()
            return
        sec = self._x_to_sec(event.position().x())
        self._external_drop_index = self._insert_index_for_sec(sec)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.update()

    def dragLeaveEvent(self, event) -> None:
        self._external_drop_index = -1
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._external_drop_index = -1

        raw = event.mimeData().data(ClipListModel.MIME_TYPE)
        if raw.isEmpty():
            event.ignore()
            self.update()
            return

        try:
            rows = [int(x) for x in bytes(raw).decode().split(",") if x.strip()]
        except ValueError:
            event.ignore()
            self.update()
            return

        insert = self._insert_index_for_sec(self._x_to_sec(event.position().x()))
        for off, row in enumerate(rows):
            self.timeline_clip_dropped.emit(row, insert + off)

        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.update()


class TimelineWidget(QWidget):
    """Timeline panel: editable sequence + keyframe analysis + transport mapping."""

    frame_changed = Signal(int)
    clip_clicked = Signal(int)

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._analyzers: list[KeyframeAnalyzer] = []
        self._frame_cache: dict[int, list[FrameInfo]] = {}
        self._cache_source: dict[int, str] = {}
        self._analysis_inflight: set[int] = set()

        self._build_ui()

        self._project.clip_updated.connect(self.refresh)
        self._project.timeline_changed.connect(self.refresh)
        self._project.timeline_item_selected.connect(self._canvas.set_selected_item)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(8, 3, 8, 3)
        self._info_label = QLabel("Timeline")
        self._info_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #aaa;")
        info_row.addWidget(self._info_label)
        info_row.addStretch()

        self._btn_cut = QPushButton("Cut")
        self._btn_cut.setFixedHeight(22)
        self._btn_cut.setToolTip("Cut at playhead (Ctrl+K)")
        self._btn_cut.clicked.connect(self._cut_at_playhead)
        info_row.addWidget(self._btn_cut)

        self._btn_drop = QPushButton("Drop I")
        self._btn_drop.setFixedHeight(22)
        self._btn_drop.setToolTip("Toggle drop first I-frame (I)")
        self._btn_drop.clicked.connect(self._toggle_drop_first_selected)
        info_row.addWidget(self._btn_drop)

        self._btn_del = QPushButton("Delete")
        self._btn_del.setFixedHeight(22)
        self._btn_del.setToolTip("Delete selected timeline segment")
        self._btn_del.clicked.connect(self._delete_selected)
        info_row.addWidget(self._btn_del)

        self._hint_label = QLabel("Drag from bin | Drag clip to reorder | Ctrl+K cut | I toggle cut I-frame")
        self._hint_label.setStyleSheet("font-size: 10px; color: #555;")
        info_row.addWidget(self._hint_label)
        layout.addLayout(info_row)

        self._canvas = TimelineCanvas()
        self._canvas.frame_clicked.connect(self._on_frame_clicked)
        self._canvas.clip_clicked.connect(self._on_clip_clicked)
        self._canvas.timeline_item_clicked.connect(self._project.select_timeline_item)
        self._canvas.timeline_item_moved.connect(self._project.move_timeline_item)
        self._canvas.timeline_clip_dropped.connect(self._project.insert_timeline_from_row)
        self._canvas.viewport_changed.connect(self._sync_scrollbar)
        self._canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._canvas.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._canvas, 1)

        self._scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._scrollbar.setStyleSheet(
            """
            QScrollBar:horizontal {
                background: #191919;
                height: 12px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: #555;
                border-radius: 4px;
                min-width: 30px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover { background: #777; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            """
        )
        self._scrollbar.setRange(0, 1000)
        self._scrollbar.valueChanged.connect(self._on_scrollbar)
        layout.addWidget(self._scrollbar)

        self._cut_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._cut_shortcut.activated.connect(self._cut_at_playhead)

        self._toggle_drop_shortcut = QShortcut(QKeySequence("I"), self)
        self._toggle_drop_shortcut.activated.connect(self._toggle_drop_first_selected)

        self._delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        self._delete_shortcut.activated.connect(self._delete_selected)

    def _sync_scrollbar(self) -> None:
        frac = self._canvas.get_scroll_fraction()
        vis = self._canvas.get_visible_fraction()
        self._scrollbar.blockSignals(True)
        self._scrollbar.setPageStep(max(1, int(vis * 1000)))
        self._scrollbar.setValue(int(frac * 1000))
        self._scrollbar.blockSignals(False)

    def _on_scrollbar(self, value: int) -> None:
        self._canvas.set_scroll_fraction(value / 1000.0)

    # -- Public slots ------------------------------------------------------

    def refresh(self) -> None:
        items = self._project.timeline_items
        if not items:
            self._canvas.clear()
            self._info_label.setText("Timeline")
            return

        regions: list[ClipRegion] = []
        for idx, item in enumerate(items):
            clip = item.clip
            clip_row = self._project.row_for_clip(clip)
            colors = CLIP_COLORS[idx % len(CLIP_COLORS)]

            key = id(clip)
            norm = str(clip.normalized_path) if clip.normalized_path else ""
            if self._cache_source.get(key) != norm:
                self._frame_cache.pop(key, None)
                self._analysis_inflight.discard(key)
                self._cache_source[key] = norm

            start, end, frame_count = self._frame_bounds(item)
            source_frame_count = frame_count
            frames: list[FrameInfo] = []
            loading = not clip.is_ready()
            drop_first = (
                item.drop_first_keyframe_override
                if item.drop_first_keyframe_override is not None
                else clip.drop_first_keyframe
            )

            full = self._frame_cache.get(key)
            if full is not None:
                end = min(end, len(full))
                if end <= start:
                    end = min(len(full), start + 1)
                frames = full[start:end]
                source_frame_count = max(1, len(frames))
                frame_count = self._predict_output_frame_count(
                    frames,
                    keep_first=clip.keep_first,
                    drop_first=drop_first,
                    dup_count=clip.duplicate_count,
                    dup_gap=clip.duplicate_gap,
                    keep_keys_spec=clip.keep_keys_spec,
                    drop_keys_spec=clip.drop_keys_spec,
                )
                loading = False
            else:
                frame_count = self._estimate_output_frames_without_analysis(
                    source_frame_count,
                    dup_count=clip.duplicate_count,
                    dup_gap=clip.duplicate_gap,
                )

            fps = clip.fps if clip.fps > 0 else 30.0
            duration = frame_count / fps if fps > 0 else frame_count / 30.0

            r = ClipRegion(
                timeline_index=idx,
                clip_row=clip_row,
                label=clip.label(),
                frames=frames,
                frame_count=frame_count,
                keep_first=clip.keep_first,
                dup_count=clip.duplicate_count,
                dup_gap=clip.duplicate_gap,
                drop_first=drop_first,
                fps=fps,
                duration_sec=max(0.01, duration),
                loading=loading,
                color_top=colors[0],
                color_bot=colors[1],
            )
            regions.append(r)

            if clip.is_ready() and full is None and key not in self._analysis_inflight:
                self._analyze_clip(key, clip.normalized_path)

        self._canvas.set_regions(regions)
        self._canvas.set_selected_item(self._project.selected_timeline_index)
        self._sync_scrollbar()
        self._update_info_label(items)

    def set_playhead(self, frame: int) -> None:
        self._canvas.set_playhead(frame)

    # -- Analysis ----------------------------------------------------------

    def _analyze_clip(self, key: int, path) -> None:
        analyzer = KeyframeAnalyzer(path, self)
        analyzer.finished_ok.connect(lambda frames, k=key: self._on_frames_ready(k, frames))
        analyzer.error.connect(lambda msg, k=key: self._on_analysis_error(k, msg))
        analyzer.finished.connect(analyzer.deleteLater)
        self._analyzers.append(analyzer)
        self._analysis_inflight.add(key)
        analyzer.start()

    def _on_frames_ready(self, key: int, frames: list[FrameInfo]) -> None:
        self._analysis_inflight.discard(key)
        self._frame_cache[key] = frames
        self.refresh()

    def _on_analysis_error(self, key: int, msg: str) -> None:
        self._analysis_inflight.discard(key)
        self._info_label.setText(f"Analysis error: {msg}")

    # -- Actions -----------------------------------------------------------

    def _on_frame_clicked(self, frame: int) -> None:
        self.frame_changed.emit(frame)

    def _on_clip_clicked(self, row: int) -> None:
        if row >= 0:
            self.clip_clicked.emit(row)

    def _cut_at_playhead(self) -> None:
        item_idx, local_frame = self._canvas.current_playhead_location()
        if item_idx < 0:
            item_idx = self._project.selected_timeline_index

        if item_idx < 0:
            return

        if self._project.split_timeline_item(item_idx, local_frame):
            self._project.status_message.emit("Cut created")
        else:
            self._project.status_message.emit("Unable to cut at this position")

    def _toggle_drop_first_selected(self) -> None:
        idx = self._project.selected_timeline_index
        if idx < 0:
            return
        val = self._project.toggle_timeline_item_drop_first(idx)
        if val is None:
            return
        state = "ON" if val else "OFF"
        self._project.status_message.emit(f"Drop first I-frame: {state}")

    def _delete_selected(self) -> None:
        idx = self._project.selected_timeline_index
        if idx < 0:
            return
        if self._project.remove_timeline_item(idx):
            self._project.status_message.emit("Timeline item removed")

    def _show_context_menu(self, pos) -> None:
        item_idx = self._canvas.timeline_item_at_pos(pos)
        if item_idx >= 0:
            self._project.select_timeline_item(item_idx)
            if item_idx < len(self._project.timeline_items):
                clip_row = self._project.row_for_clip(self._project.timeline_items[item_idx].clip)
                if clip_row >= 0:
                    self._project.select_clip(clip_row)

        menu = QMenu(self)

        act_cut = menu.addAction("Cut At Playhead")
        act_cut.triggered.connect(self._cut_at_playhead)

        act_drop = menu.addAction("Toggle Drop First I-Frame")
        act_drop.triggered.connect(self._toggle_drop_first_selected)

        act_delete = menu.addAction("Delete Segment")
        act_delete.triggered.connect(self._delete_selected)

        menu.addSeparator()
        act_add_selected = menu.addAction("Add Selected Bin Clip")
        act_add_selected.triggered.connect(self._add_selected_bin_clip)

        if self._project.selected_timeline_index < 0:
            act_drop.setEnabled(False)
            act_delete.setEnabled(False)
        if self._project.selected_row < 0:
            act_add_selected.setEnabled(False)

        menu.exec(self._canvas.mapToGlobal(pos))

    def _add_selected_bin_clip(self) -> None:
        row = self._project.selected_row
        if row < 0:
            return
        idx, _ = self._canvas.current_playhead_location()
        insert_at = idx + 1 if idx >= 0 else len(self._project.timeline_items)
        if self._project.insert_timeline_from_row(row, insert_at):
            self._project.status_message.emit("Clip inserted on timeline")

    # -- Helpers -----------------------------------------------------------

    def _update_info_label(self, items: list[TimelineItem]) -> None:
        total_frames = sum(r.frame_count for r in self._canvas._regions)
        n_keys = sum(sum(1 for f in r.frames if f.is_keyframe) for r in self._canvas._regions)
        total_sec = sum(r.duration_sec for r in self._canvas._regions)
        n_ready = sum(1 for i in items if i.clip.is_ready())
        self._info_label.setText(
            f"{total_frames} frames  |  {total_sec:.2f}s  |  {n_keys} I-frames  |  {len(items)} items ({n_ready} ready)"
        )

    @staticmethod
    def _estimate_output_frames_without_analysis(
        source_frames: int,
        dup_count: int,
        dup_gap: int,
    ) -> int:
        base = max(1, source_frames)
        if dup_count <= 0 or dup_gap <= 0:
            return base
        return base + (base // dup_gap) * dup_count

    @staticmethod
    def _predict_output_frame_count(
        frames: list[FrameInfo],
        *,
        keep_first: int,
        drop_first: bool,
        dup_count: int,
        dup_gap: int,
        keep_keys_spec: str,
        drop_keys_spec: str,
    ) -> int:
        if not frames:
            return 1

        keep_set: Optional[set[int]] = None
        drop_set: Optional[set[int]] = None
        try:
            if keep_keys_spec:
                keep_set = mosh.parse_keyframe_spec(keep_keys_spec) or None
            if drop_keys_spec:
                drop_set = mosh.parse_keyframe_spec(drop_keys_spec) or None
        except ValueError:
            keep_set = None
            drop_set = None

        keep_limit = _effective_keep_limit(keep_first, drop_first)
        keys_kept = 0
        key_index = 0
        p_counter = 0
        out = 0

        for frame in frames:
            if frame.is_keyframe:
                keep = True
                if drop_first and key_index == 0:
                    keep = False
                elif drop_set is not None and key_index in drop_set:
                    keep = False
                elif keep_set is not None and key_index in keep_set:
                    keep = True
                elif keys_kept >= keep_limit:
                    keep = False

                if keep:
                    out += 1
                    keys_kept += 1
                key_index += 1
                continue

            out += 1
            p_counter += 1
            if dup_count > 0 and dup_gap > 0 and (p_counter % dup_gap == 0):
                out += dup_count

        return max(1, out)

    @staticmethod
    def _frame_bounds(item: TimelineItem) -> tuple[int, int, int]:
        clip = item.clip
        fps = clip.fps if clip.fps > 0 else 30.0
        estimated_total = clip.total_frames if clip.total_frames > 0 else max(1, int(5 * fps))

        start = max(0, item.in_frame)
        end = item.out_frame if item.out_frame > 0 else estimated_total
        end = max(start + 1, min(end, estimated_total))
        return start, end, max(1, end - start)
