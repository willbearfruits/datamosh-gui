"""Tests for mosh.py core datamosh engine."""
import pytest
from pathlib import Path
import mosh


class TestKeyframeSpecParsing:
    """Test keyframe specification parsing."""

    def test_parse_single_index(self):
        """Test parsing a single keyframe index."""
        result = mosh.parse_keyframe_spec("5")
        assert result == {5}

    def test_parse_multiple_indices(self):
        """Test parsing multiple keyframe indices."""
        result = mosh.parse_keyframe_spec("1,3,5")
        assert result == {1, 3, 5}

    def test_parse_range(self):
        """Test parsing a range of keyframes."""
        result = mosh.parse_keyframe_spec("2-5")
        assert result == {2, 3, 4, 5}

    def test_parse_mixed(self):
        """Test parsing mixed indices and ranges."""
        result = mosh.parse_keyframe_spec("1,3-5,7")
        assert result == {1, 3, 4, 5, 7}

    def test_parse_empty(self):
        """Test parsing empty specification."""
        result = mosh.parse_keyframe_spec("")
        assert result == set()

    def test_parse_invalid(self):
        """Test parsing invalid specification."""
        with pytest.raises(ValueError):
            mosh.parse_keyframe_spec("invalid")


class TestAviChunk:
    """Test AviChunk dataclass."""

    def test_chunk_creation(self):
        """Test creating an AVI chunk."""
        chunk = mosh.AviChunk(
            chunk_id=b"00dc",
            flags=0x10,
            data=b"test_data",
            is_video=True,
            is_keyframe=True,
            stream_id=0,
            clip_id=0
        )
        assert chunk.chunk_id == b"00dc"
        assert chunk.is_video is True
        assert chunk.is_keyframe is True

    def test_chunk_clone(self):
        """Test cloning an AVI chunk."""
        chunk = mosh.AviChunk(
            chunk_id=b"00dc",
            flags=0x10,
            data=b"test_data",
            is_video=True,
            is_keyframe=True,
            stream_id=0,
            clip_id=0
        )
        clone = chunk.clone()
        assert clone.chunk_id == chunk.chunk_id
        assert clone.data == chunk.data
        assert clone is not chunk  # Different object


class TestClipOptions:
    """Test ClipOptions dataclass."""

    def test_default_options(self):
        """Test default clip options."""
        opts = mosh.ClipOptions(
            keep_initial_keyframes=1,
            duplicate_count=0,
            duplicate_gap=1
        )
        assert opts.keep_initial_keyframes == 1
        assert opts.duplicate_count == 0
        assert opts.drop_first_keyframe is False
        assert opts.keep_specific_keys is None


class TestNormalizePresets:
    """Test normalization presets."""

    def test_presets_exist(self):
        """Test that standard presets exist."""
        assert "fast" in mosh.NORMALIZE_PRESETS
        assert "balanced" in mosh.NORMALIZE_PRESETS
        assert "sharp" in mosh.NORMALIZE_PRESETS

    def test_preset_structure(self):
        """Test preset structure."""
        preset = mosh.NORMALIZE_PRESETS["balanced"]
        assert "width" in preset
        assert "qscale" in preset
        assert "gop" in preset
        assert "keep_audio" in preset


# Integration tests (require actual AVI files)
@pytest.mark.integration
class TestAviProcessing:
    """Integration tests for AVI processing (requires video files)."""

    @pytest.mark.skip(reason="Requires sample AVI file")
    def test_rewrite_avi_basic(self, temp_dir, sample_avi_path):
        """Test basic AVI rewriting."""
        if not sample_avi_path.exists():
            pytest.skip("Sample AVI file not available")

        output_path = temp_dir / "output.avi"
        mosh.rewrite_avi(
            sample_avi_path,
            output_path,
            keep_initial_keyframes=1,
            duplicate_count=0,
            duplicate_gap=1
        )
        assert output_path.exists()
