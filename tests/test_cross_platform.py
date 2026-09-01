from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ddtool import autostart
from ddtool.macos_ui import macos_palette
from ddtool.quick_actions import (
    MACOS_QUICK_ACTIONS,
    SHELL_ZSH,
    TERMINAL_AUTO,
    TERMINAL_GHOSTTY,
    QuickAction,
    bind_context_menu,
    context_menu_events,
    macos_terminal_launch_args,
)
from ddtool.tray_app import DDToolTrayApp


class CrossPlatformTests(unittest.TestCase):
    def test_macos_presets_use_zsh(self) -> None:
        self.assertTrue(MACOS_QUICK_ACTIONS)
        self.assertTrue(all(action.shell == SHELL_ZSH for action in MACOS_QUICK_ACTIONS))

    def test_quick_action_defaults_to_automatic_terminal(self) -> None:
        action = QuickAction.from_dict(
            {"name": "检查", "command": "pwd", "shell": "zsh"}
        )
        self.assertIsNotNone(action)
        self.assertEqual(action.terminal, TERMINAL_AUTO)

    def test_ghostty_launch_arguments(self) -> None:
        self.assertEqual(
            macos_terminal_launch_args("/tmp/test.command", TERMINAL_GHOSTTY),
            [
                "open",
                "-na",
                "Ghostty.app",
                "--args",
                "-e",
                "/bin/zsh",
                "/tmp/test.command",
            ],
        )

    def test_macos_palette_uses_system_colors(self) -> None:
        palette = macos_palette()
        self.assertEqual(palette.window, "systemWindowBackgroundColor")
        self.assertEqual(palette.text, "systemLabelColor")

    def test_macos_context_menu_supports_trackpad_and_control_click(self) -> None:
        with patch("ddtool.quick_actions.IS_MACOS", True):
            self.assertEqual(
                context_menu_events(),
                ("<Button-2>", "<Button-3>", "<Control-Button-1>"),
            )

    def test_context_menu_binds_every_macos_gesture(self) -> None:
        widget = MagicMock()
        handler = MagicMock()
        with patch("ddtool.quick_actions.IS_MACOS", True):
            bind_context_menu(widget, handler)
        self.assertEqual(widget.bind.call_count, 3)
        widget.bind.assert_any_call("<Button-2>", handler, add="+")
        widget.bind.assert_any_call("<Button-3>", handler, add="+")
        widget.bind.assert_any_call("<Control-Button-1>", handler, add="+")

    def test_launch_agent_is_valid_plist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "com.ddtool.app.plist"
            with (
                patch.object(autostart, "IS_MACOS", True),
                patch.object(autostart, "IS_WINDOWS", False),
                patch.object(autostart, "_LAUNCH_AGENT", target),
                patch.object(autostart, "launch_arguments", return_value=["/Applications/DDTool"]),
            ):
                autostart.set_enabled(True)
                payload = plistlib.loads(target.read_bytes())
                self.assertEqual(payload["Label"], "com.ddtool.app")
                self.assertTrue(payload["RunAtLoad"])
                autostart.set_enabled(False)
                self.assertFalse(target.exists())

    def test_macos_tray_callback_runs_without_tk_after(self) -> None:
        app = DDToolTrayApp.__new__(DDToolTrayApp)
        app.root = MagicMock()
        callback = MagicMock()
        with patch("ddtool.tray_app.IS_MACOS", True):
            app._run_on_ui(callback)
        callback.assert_called_once_with()
        app.root.after.assert_not_called()

    def test_windows_tray_callback_uses_tk_after(self) -> None:
        app = DDToolTrayApp.__new__(DDToolTrayApp)
        app.root = MagicMock()
        callback = MagicMock()
        with patch("ddtool.tray_app.IS_MACOS", False):
            app._run_on_ui(callback)
        callback.assert_not_called()
        app.root.after.assert_called_once_with(0, callback)

    def test_macos_quit_does_not_schedule_tk_callback(self) -> None:
        app = DDToolTrayApp.__new__(DDToolTrayApp)
        app.root = MagicMock()
        app.forward = MagicMock()
        app.network = MagicMock()
        app.mirror = MagicMock()
        app.lock_screen = MagicMock()
        icon = MagicMock()
        with patch("ddtool.tray_app.IS_MACOS", True):
            app._quit(icon, MagicMock())
        self.assertFalse(icon.visible)
        icon.stop.assert_not_called()
        app.root.after.assert_not_called()
        app.root.quit.assert_called_once_with()
        app.root.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
