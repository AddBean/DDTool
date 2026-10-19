from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ddtool.keep_awake import EndAction, KeepAwakeController, _format_duration
from ddtool.quick_actions import (
    BUILTIN_COMMAND_KEEP_AWAKE,
    LEGACY_SYSTEM_SHORTCUTS_MENU,
    SYSTEM_COMMANDS_MENU,
    QuickAction,
    _migrate_system_menu_name,
    load_quick_actions,
)


class KeepAwakeTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(_format_duration(65), "1 分 05 秒")
        self.assertEqual(_format_duration(3661), "1 小时 01 分")

    def test_migrate_system_menu_name(self) -> None:
        actions = [
            QuickAction("a", "防睡眠", BUILTIN_COMMAND_KEEP_AWAKE, False, LEGACY_SYSTEM_SHORTCUTS_MENU),
            QuickAction("b", "子菜单", "echo", False, f"{LEGACY_SYSTEM_SHORTCUTS_MENU}/网络"),
            QuickAction("c", "其他", "echo", False, "快捷操作"),
        ]
        migrated, changed = _migrate_system_menu_name(actions)
        self.assertTrue(changed)
        self.assertEqual(migrated[0].menu_path, SYSTEM_COMMANDS_MENU)
        self.assertEqual(migrated[1].menu_path, f"{SYSTEM_COMMANDS_MENU}/网络")
        self.assertEqual(migrated[2].menu_path, "快捷操作")

    def test_presets_include_keep_awake_under_system_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("ddtool.quick_actions.get_config_dir", return_value=Path(temp_dir)):
                actions = load_quick_actions()
        keep = next(action for action in actions if action.id == "preset-keep-awake")
        self.assertEqual(keep.command, BUILTIN_COMMAND_KEEP_AWAKE)
        self.assertEqual(keep.menu_path, SYSTEM_COMMANDS_MENU)
        self.assertTrue(all(action.menu_path != LEGACY_SYSTEM_SHORTCUTS_MENU for action in actions))

    def test_controller_start_and_stop(self) -> None:
        controller = KeepAwakeController()
        with (
            patch.object(controller, "_begin_os_assertion"),
            patch.object(controller, "_refresh_os_assertion"),
            patch.object(controller, "_clear_os_assertion"),
            patch("ddtool.keep_awake._perform_end_action") as perform,
        ):
            controller.start(2, EndAction.LOCK, allow_display_off=True)
            self.assertTrue(controller.is_active)
            status = controller.status()
            self.assertTrue(status.active)
            self.assertTrue(status.allow_display_off)
            self.assertGreaterEqual(status.remaining_seconds, 1)
            controller.stop(run_end_action=False)
            self.assertFalse(controller.is_active)
            perform.assert_not_called()

    def test_status_tracks_display_off_option(self) -> None:
        controller = KeepAwakeController()
        with (
            patch.object(controller, "_begin_os_assertion") as begin,
            patch.object(controller, "_refresh_os_assertion"),
            patch.object(controller, "_clear_os_assertion"),
            patch("ddtool.keep_awake._turn_display_off"),
            patch("ddtool.keep_awake.time.sleep"),
        ):
            controller.start(30, EndAction.DEFAULT, allow_display_off=True)
            self.assertTrue(controller.status().allow_display_off)
            self.assertIn("允许黑屏", controller.status().message)
            # Worker may already have started; give it a tick to call begin.
            for _ in range(20):
                if begin.called:
                    break
                controller._stop.wait(0.01)
            controller.stop(run_end_action=False)
        self.assertTrue(begin.called)
        self.assertTrue(begin.call_args.kwargs.get("allow_display_off"))


if __name__ == "__main__":
    unittest.main()
