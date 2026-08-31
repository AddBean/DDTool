from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ddtool import autostart
from ddtool.quick_actions import MACOS_QUICK_ACTIONS, SHELL_ZSH


class CrossPlatformTests(unittest.TestCase):
    def test_macos_presets_use_zsh(self) -> None:
        self.assertTrue(MACOS_QUICK_ACTIONS)
        self.assertTrue(all(action.shell == SHELL_ZSH for action in MACOS_QUICK_ACTIONS))

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
