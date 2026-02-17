"""Tests for shortcuts.py keyboard shortcut system."""
import pytest
import tkinter as tk
from shortcuts import ShortcutManager, Shortcut, Modifier


# Skip GUI tests if running in headless environment
try:
    root = tk.Tk()
    root.destroy()
    HAS_DISPLAY = True
except tk.TclError:
    HAS_DISPLAY = False


@pytest.mark.skipif(not HAS_DISPLAY, reason="No display available")
class TestShortcutManager:
    """Tests for ShortcutManager."""

    def test_manager_creation(self):
        """Test creating a shortcut manager."""
        root = tk.Tk()
        manager = ShortcutManager(root)

        assert manager.enabled is True
        assert len(manager.shortcuts) == 0
        root.destroy()

    def test_register_shortcut(self):
        """Test registering a shortcut."""
        root = tk.Tk()
        manager = ShortcutManager(root)

        callback = lambda: None
        shortcut = Shortcut(
            key='o',
            modifiers=(Modifier.CTRL,),
            callback=callback,
            description="Open file"
        )

        manager.register(shortcut)
        assert len(manager.shortcuts) == 1
        root.destroy()

    def test_shortcut_conflict(self):
        """Test shortcut conflict detection."""
        root = tk.Tk()
        manager = ShortcutManager(root)

        callback1 = lambda: None
        callback2 = lambda: None

        shortcut1 = Shortcut('o', (Modifier.CTRL,), callback1, "Open")
        shortcut2 = Shortcut('o', (Modifier.CTRL,), callback2, "Override")

        manager.register(shortcut1)

        # Should raise ValueError for conflict
        with pytest.raises(ValueError, match="conflict"):
            manager.register(shortcut2)

        root.destroy()

    def test_shortcut_override(self):
        """Test overriding a shortcut."""
        root = tk.Tk()
        manager = ShortcutManager(root)

        callback1 = lambda: None
        callback2 = lambda: None

        shortcut1 = Shortcut('o', (Modifier.CTRL,), callback1, "Open")
        shortcut2 = Shortcut('o', (Modifier.CTRL,), callback2, "Override")

        manager.register(shortcut1)
        manager.register(shortcut2, override=True)

        assert len(manager.shortcuts) == 1
        root.destroy()


class TestShortcut:
    """Tests for Shortcut dataclass."""

    def test_shortcut_creation(self):
        """Test creating a shortcut."""
        callback = lambda: print("test")

        shortcut = Shortcut(
            key='s',
            modifiers=(Modifier.CTRL, Modifier.SHIFT),
            callback=callback,
            description="Save as",
            category="File"
        )

        assert shortcut.key == 's'
        assert len(shortcut.modifiers) == 2
        assert shortcut.description == "Save as"
        assert shortcut.category == "File"
