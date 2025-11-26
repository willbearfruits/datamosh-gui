#!/usr/bin/env python3
"""
Keyboard shortcut system for Datamosh GUI

Provides centralized keyboard shortcut management with:
- Platform-aware modifiers (Ctrl/Cmd)
- Help dialog
- Easy registration
- Conflict detection
"""

from __future__ import annotations

import logging
import platform
import tkinter as tk
from dataclasses import dataclass
from enum import Enum
from tkinter import ttk
from typing import Callable, Dict, Optional, Tuple

# Configure module logger
logger = logging.getLogger(__name__)


class Modifier(Enum):
    """Keyboard modifiers"""
    CTRL = 'Control'
    SHIFT = 'Shift'
    ALT = 'Alt'
    CMD = 'Command'  # macOS


@dataclass
class Shortcut:
    """Keyboard shortcut definition"""
    key: str
    modifiers: Tuple[Modifier, ...] = ()
    callback: Optional[Callable] = None
    description: str = ""
    category: str = "General"


class ShortcutManager:
    """
    Central keyboard shortcut manager.

    Usage:
        manager = ShortcutManager(root_window)
        manager.register(Shortcut('o', (Modifier.CTRL,), open_file, "Open file", "File"))
        manager.show_help_dialog()  # Show all shortcuts
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.shortcuts: Dict[str, Shortcut] = {}
        self.enabled = True

        # Platform detection
        self.is_mac = platform.system() == 'Darwin'
        self.primary_mod = Modifier.CMD if self.is_mac else Modifier.CTRL

    def register(self, shortcut: Shortcut, override: bool = False):
        """Register a keyboard shortcut"""
        key_string = self._make_key_string(shortcut)

        if key_string in self.shortcuts and not override:
            existing = self.shortcuts[key_string]
            raise ValueError(
                f"Shortcut conflict: {key_string} already bound to "
                f"'{existing.description}'"
            )

        self.shortcuts[key_string] = shortcut
        self._bind_shortcut(shortcut)

    def register_many(self, shortcuts: list[Shortcut]):
        """Register multiple shortcuts"""
        for shortcut in shortcuts:
            self.register(shortcut)

    def unregister(self, key: str, modifiers: Tuple[Modifier, ...] = ()):
        """Unregister a shortcut"""
        key_string = self._make_key_string_from_parts(key, modifiers)
        if key_string in self.shortcuts:
            self._unbind_shortcut(self.shortcuts[key_string])
            del self.shortcuts[key_string]

    def enable(self):
        """Enable all shortcuts"""
        self.enabled = True

    def disable(self):
        """Disable all shortcuts (useful during text entry)"""
        self.enabled = False

    def show_help_dialog(self):
        """Display shortcut help dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Keyboard Shortcuts")
        dialog.geometry("650x500")
        dialog.transient(self.root)

        # Header
        header = ttk.Frame(dialog)
        header.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(header, text="Keyboard Shortcuts",
                 font=('Arial', 14, 'bold')).pack(anchor='w')

        # Create notebook for categories
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Group shortcuts by category
        categories = {}
        for shortcut in self.shortcuts.values():
            cat = shortcut.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(shortcut)

        # Create tab for each category
        for category, shortcuts in sorted(categories.items()):
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=category)

            # Create treeview
            columns = ('key', 'description')
            tree = ttk.Treeview(frame, columns=columns, show='headings',
                               height=15, selectmode='none')
            tree.heading('key', text='Shortcut')
            tree.heading('description', text='Action')
            tree.column('key', width=150)
            tree.column('description', width=450)

            # Scrollbar
            scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL,
                                     command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)

            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Populate shortcuts
            for shortcut in sorted(shortcuts, key=lambda s: s.description):
                key_display = self._format_key_display(shortcut)
                tree.insert('', tk.END, values=(key_display, shortcut.description))

        # Close button
        ttk.Button(dialog, text="Close",
                  command=dialog.destroy).pack(pady=(0, 10))

        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def _make_key_string(self, shortcut: Shortcut) -> str:
        """Create unique key string from shortcut"""
        return self._make_key_string_from_parts(shortcut.key, shortcut.modifiers)

    def _make_key_string_from_parts(self, key: str,
                                    modifiers: Tuple[Modifier, ...]) -> str:
        """Create key string from parts"""
        mod_str = '-'.join(sorted(m.value for m in modifiers))
        return f"<{mod_str}-{key}>" if mod_str else f"<{key}>"

    def _bind_shortcut(self, shortcut: Shortcut):
        """Bind shortcut to root window"""
        key_string = self._make_key_string(shortcut)

        def handler(event):
            if self.enabled and shortcut.callback:
                try:
                    shortcut.callback()
                except Exception as e:
                    logger.error(f"Error in shortcut {key_string}: {e}", exc_info=True)
                return 'break'  # Prevent default behavior

        self.root.bind(key_string, handler)

    def _unbind_shortcut(self, shortcut: Shortcut):
        """Unbind shortcut from root window"""
        key_string = self._make_key_string(shortcut)
        self.root.unbind(key_string)

    def _format_key_display(self, shortcut: Shortcut) -> str:
        """Format shortcut for display"""
        parts = []

        # Sort modifiers for consistent display
        mod_order = {
            Modifier.CTRL: 0,
            Modifier.CMD: 0,
            Modifier.ALT: 1,
            Modifier.SHIFT: 2
        }
        sorted_mods = sorted(shortcut.modifiers,
                           key=lambda m: mod_order.get(m, 99))

        for mod in sorted_mods:
            if mod == Modifier.CTRL:
                parts.append('Ctrl')
            elif mod == Modifier.CMD:
                parts.append('Cmd')
            elif mod == Modifier.ALT:
                parts.append('Alt')
            elif mod == Modifier.SHIFT:
                parts.append('Shift')

        # Format key name
        key_name = shortcut.key
        if len(key_name) == 1:
            key_name = key_name.upper()
        elif key_name == 'space':
            key_name = 'Space'
        elif key_name in ('Left', 'Right', 'Up', 'Down'):
            key_name = f'{key_name} Arrow'
        elif key_name == 'Prior':
            key_name = 'Page Up'
        elif key_name == 'Next':
            key_name = 'Page Down'

        parts.append(key_name)

        return '+'.join(parts)


# Example usage and default shortcuts for Datamosh GUI
def register_datamosh_shortcuts(manager: ShortcutManager, app):
    """
    Register standard shortcuts for Datamosh GUI.

    Args:
        manager: ShortcutManager instance
        app: MoshApp instance with methods to call
    """
    shortcuts = [
        # File operations
        Shortcut('o', (Modifier.CTRL,),
                lambda: app._select_input(),
                "Open video file",
                "File"),
        Shortcut('a', (Modifier.CTRL,),
                lambda: app._add_append(),
                "Add append clip",
                "File"),
        Shortcut('q', (Modifier.CTRL,),
                lambda: app._on_exit(),
                "Quit application",
                "File"),

        # Rendering
        Shortcut('r', (Modifier.CTRL,),
                lambda: app._start_worker("render"),
                "Render moshed video",
                "Render"),
        Shortcut('p', (Modifier.CTRL,),
                lambda: app._start_worker("preview"),
                "Preview moshed video",
                "Render"),

        # Navigation
        Shortcut('Left', (),
                lambda: app._select_previous_clip(),
                "Select previous clip",
                "Navigation"),
        Shortcut('Right', (),
                lambda: app._select_next_clip(),
                "Select next clip",
                "Navigation"),

        # Help
        Shortcut('F1', (),
                manager.show_help_dialog,
                "Show keyboard shortcuts",
                "Help"),
        Shortcut('question', (Modifier.SHIFT,),
                manager.show_help_dialog,
                "Show keyboard shortcuts",
                "Help"),
    ]

    manager.register_many(shortcuts)
