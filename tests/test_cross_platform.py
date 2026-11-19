from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ddtool import autostart
from ddtool.config import AppConfig
from ddtool.notices import Reporter
from ddtool.phone_mirror import MirrorController
from ddtool.quick_actions import (
    MACOS_QUICK_ACTIONS,
    SHELL_ZSH,
    TERMINAL_AUTO,
    TERMINAL_GHOSTTY,
    QuickAction,
    macos_terminal_launch_args,
    run_quick_action,
)


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

    def test_mirror_reports_missing_tool_without_gui(self) -> None:
        reports = []
        with patch("ddtool.phone_mirror.resolve_scrcpy_path", return_value=None):
            MirrorController(AppConfig(), reporter=Reporter(lambda *args: reports.append(args))).start()
        self.assertEqual(reports[0][0], "error")
        self.assertIn("scrcpy", reports[0][1])

    def test_macos_command_launch_reports_failure_without_gui(self) -> None:
        reports = []
        with (
            patch("ddtool.quick_actions.IS_MACOS", True),
            patch("ddtool.quick_actions.subprocess.Popen", side_effect=OSError("spawn failed")),
        ):
            run_quick_action(QuickAction("test", "Test", "pwd"), Reporter(lambda *args: reports.append(args)))
        self.assertEqual(reports[0][0], "error")
        self.assertIn("spawn failed", reports[0][1])

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

if __name__ == "__main__":
    unittest.main()
