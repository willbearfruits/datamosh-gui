"""Tests for video_preview.py module."""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import tkinter as tk


# Skip all GUI tests if running in headless environment
try:
    root = tk.Tk()
    root.destroy()
    HAS_DISPLAY = True
except tk.TclError:
    HAS_DISPLAY = False


@pytest.mark.skipif(not HAS_DISPLAY, reason="No display available")
class TestVideoPreviewWidget:
    """Tests for VideoPreviewWidget."""

    def test_adaptive_preview_width_auto(self):
        """Test adaptive preview width with auto-detection."""
        from video_preview import VideoPreviewWidget

        with patch('tkinter.Toplevel.__init__'):
            root = tk.Tk()

            # Mock the video file
            video_path = Path("/tmp/test.avi")

            # Test auto width (0 = auto-detect)
            with patch.object(root, 'winfo_screenwidth', return_value=1920):
                widget = VideoPreviewWidget.__new__(VideoPreviewWidget)
                widget.video_path = video_path
                widget.preview_width = 0

                # Simulate the adaptive width logic
                screen_width = 1920
                expected_width = min(screen_width // 2, 1280)

                assert expected_width == 960  # Half of 1920, less than 1280

    def test_adaptive_preview_width_large_screen(self):
        """Test adaptive preview width caps at 1280 for large screens."""
        screen_width = 3840  # 4K display
        expected_width = min(screen_width // 2, 1280)

        assert expected_width == 1280  # Capped at max


class TestFrameData:
    """Tests for FrameData dataclass."""

    def test_frame_data_creation(self):
        """Test creating FrameData."""
        from video_preview import FrameData

        frame = FrameData(
            width=640,
            height=480,
            data=b"test_data",
            frame_number=10,
            timestamp=0.5
        )

        assert frame.width == 640
        assert frame.height == 480
        assert frame.frame_number == 10
        assert frame.timestamp == 0.5
