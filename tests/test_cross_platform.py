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
                patch.object(autostart, "_macos_agent_loaded", return_value=True),
            ):
                autostart.set_enabled(True)
                payload = plistlib.loads(target.read_bytes())
                self.assertEqual(payload["Label"], "com.ddtool.app")
                self.assertTrue(payload["RunAtLoad"])
                autostart.set_enabled(False)
                self.assertFalse(target.exists())

    def test_windows_enable_clears_startup_approved_disable(self) -> None:
        run_values: dict[str, str] = {
            "豆荚工具": r'"C:\Program Files\DDTool\DDTool.exe" --background',
        }
        approved: dict[str, bytes] = {
            "豆荚工具": bytes([0x03, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        }

        class FakeKey:
            def __init__(self, store: dict, writable: bool = False) -> None:
                self.store = store
                self.writable = writable

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def open_key(_root, path, *_args):
            store = run_values if path == autostart._RUN_KEY else approved
            return FakeKey(store, writable=True)

        def create_key(_root, path):
            return open_key(_root, path)

        def query_value(key, name):
            if name not in key.store:
                raise FileNotFoundError(name)
            return key.store[name], 1

        def set_value(key, name, _reserved, _type, value):
            key.store[name] = value

        def delete_value(key, name):
            del key.store[name]

        fake_winreg = type(
            "winreg",
            (),
            {
                "HKEY_CURRENT_USER": object(),
                "KEY_SET_VALUE": 2,
                "KEY_READ": 1,
                "REG_SZ": 1,
                "REG_BINARY": 3,
                "OpenKey": staticmethod(open_key),
                "CreateKey": staticmethod(create_key),
                "QueryValueEx": staticmethod(query_value),
                "SetValueEx": staticmethod(set_value),
                "DeleteValue": staticmethod(delete_value),
            },
        )
        with (
            patch.object(autostart, "IS_MACOS", False),
            patch.object(autostart, "IS_WINDOWS", True),
            patch.object(autostart, "winreg", fake_winreg, create=True),
            patch.object(autostart, "launch_command", return_value=r'"C:\Program Files\DDTool\DDTool.exe" --background'),
            patch.object(Path, "is_file", return_value=True),
        ):
            self.assertFalse(autostart.is_enabled())
            self.assertIn("系统已禁用", autostart.status())
            autostart.set_enabled(True)
            self.assertEqual(run_values["豆荚工具"], r'"C:\Program Files\DDTool\DDTool.exe" --background')
            self.assertEqual(approved["豆荚工具"], autostart._STARTUP_ENABLED)
            self.assertTrue(autostart.is_enabled())
            self.assertIn("托盘", autostart.status())
            autostart.set_enabled(False)
            self.assertNotIn("豆荚工具", run_values)
            self.assertNotIn("豆荚工具", approved)
            self.assertFalse(autostart.is_enabled())

    def test_macos_status_accepts_legacy_agent_without_background_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "com.ddtool.app.plist"
            exe = Path(temp_dir) / "DDTool"
            exe.write_text("", encoding="utf-8")
            target.write_bytes(
                plistlib.dumps(
                    {
                        "Label": "com.ddtool.app",
                        "ProgramArguments": [str(exe)],
                        "RunAtLoad": True,
                    },
                    sort_keys=False,
                )
            )
            with (
                patch.object(autostart, "IS_MACOS", True),
                patch.object(autostart, "IS_WINDOWS", False),
                patch.object(autostart, "_LAUNCH_AGENT", target),
                patch.object(autostart, "_macos_agent_loaded", return_value=True),
            ):
                self.assertTrue(autostart.is_enabled())
                self.assertIn("菜单栏", autostart.status())
                self.assertNotIn("失效", autostart.status())

if __name__ == "__main__":
    unittest.main()
