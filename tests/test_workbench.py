from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from ddtool.shell_shortcuts import Activation, ShortcutConfig, entry_token
from ddtool.workbench import Workbench


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        stack = self.enterContext(ExitStack())
        self.directory = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        for module in ("config", "quick_actions", "workbench"):
            stack.enter_context(patch(f"ddtool.{module}.get_config_dir", return_value=self.directory))
        self.bridge = Workbench()
        self.addCleanup(self.bridge.close)

    def test_action_crud_order_and_tray_tree(self) -> None:
        first = self.bridge.saveAction("", "开发/甲", "echo first", "zsh", "ghostty", True)
        second = self.bridge.saveAction("", "开发/乙", "echo second", "zsh", "auto", False)
        self.assertTrue(first and second)
        self.bridge.moveAction(first, -1)
        node = self.bridge.tray_tree().children["开发"]
        self.assertEqual([action.id for kind, action in node.entries], [first, second])
        self.assertEqual(self.bridge.saveAction(first, "开发/新名称", "echo updated", "zsh", "ghostty", True), first)
        action = next(item for item in self.bridge.actionItems if item["key"] == first)
        self.assertEqual((action["name"], action["terminal"], action["keepTerminal"]), ("新名称", "ghostty", True))
        self.bridge.deleteAction(second)
        self.assertNotIn(second, [item["key"] for item in self.bridge.actionItems])

    def test_app_managed_actions_cannot_be_overwritten_with_custom_commands(self) -> None:
        self.assertEqual(self.bridge.saveAction("preset-keep-awake", "防睡眠", "echo test", "zsh", "auto", False), "")
        self.assertEqual(self.bridge.saveAction("", "测试", "ddtool:postpone-lock", "zsh", "auto", False), "")
        self.assertTrue(self.bridge.latestError)

    def test_legacy_import_export_keeps_action_ids_and_preferences_separate(self) -> None:
        legacy = self.directory / "legacy.json"
        legacy.write_text(json.dumps([{"id": "legacy", "location": "开发/旧操作", "command": "echo test"}]), encoding="utf-8")
        self.bridge.setAppearance("light", "blue", True)
        self.bridge.importConfig(QUrl.fromLocalFile(str(legacy)))
        export = self.directory / "export.json"
        self.bridge.exportConfig(QUrl.fromLocalFile(str(export)))
        data = json.loads(export.read_text(encoding="utf-8"))
        self.assertTrue(any(action["id"] == "legacy" for action in data["quick_actions"]["actions"]))
        self.assertEqual(set(data), {"app", "config", "quick_actions"})
        self.assertEqual((self.bridge.theme, self.bridge.accent, self.bridge.compact), ("light", "blue", True))

    def test_device_result_returns_through_queued_signals(self) -> None:
        with patch("ddtool.phone_mirror.resolve_scrcpy_path", return_value=None):
            self.bridge.runDevice("mirror")
            self.assertTrue(self.bridge.busy)
            deadline = time.monotonic() + 2
            while self.bridge.busy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
        self.assertFalse(self.bridge.busy)
        self.assertTrue(self.bridge.latestError)
        self.assertIn("scrcpy", self.bridge.latest)

    def test_builtin_routes_to_power_without_running_a_shell_command(self) -> None:
        destinations = []
        self.bridge.navigate.connect(destinations.append)
        self.bridge.runAction("preset-keep-awake")
        self.assertEqual(destinations, ["power"])
        self.assertFalse(self.bridge.busy)

    def test_system_shortcut_routes_only_to_configured_destinations(self) -> None:
        destinations = []
        self.bridge.navigate.connect(destinations.append)
        with patch("ddtool.workbench.IS_MACOS", False), patch("ddtool.workbench.apply_integration"), \
                patch("ddtool.workbench.QDesktopServices.openUrl", return_value=True) as open_url:
            self.assertEqual(self.bridge.saveShellConfig(ShortcutConfig(True, mode="power").values()), "")
            request = Activation("directory", str(self.directory))
            self.bridge.activate_shell(request)
            self.assertEqual(destinations, ["power"])
            self.assertEqual(self.bridge.shellDirectory, str(self.directory))
            config = ShortcutConfig(True, targets=("devices", "folder"))
            self.assertEqual(self.bridge.saveShellConfig(config.values()), "")
            self.bridge.activate_shell(request)
            self.bridge.openShellTarget("settings")
            self.bridge.openShellTarget("devices")
            self.bridge.openShellTarget("folder")
            self.assertEqual(destinations, ["power", "context", "devices"])
            open_url.assert_called_once_with(QUrl.fromLocalFile(str(self.directory)))

    def test_system_registration_failure_restores_previous_configuration(self) -> None:
        with patch("ddtool.workbench.apply_integration", side_effect=[PermissionError("denied"), None]):
            self.assertIn("denied", self.bridge.saveShellConfig(ShortcutConfig(True).values()))
        self.assertFalse(self.bridge.shellConfig["enabled"])
        self.assertEqual(ShortcutConfig.load(self.directory / "shell-shortcuts.json"), ShortcutConfig())

    def test_tree_persists_empty_groups_and_moves_and_renames_nested_actions(self) -> None:
        root = self.bridge.editGroup("", "开发", "create")
        child = self.bridge.editGroup(root, "安卓", "create")
        empty = self.bridge.editGroup("", "空分组", "create")
        action = self.bridge.saveAction("", "编译", "echo build", "zsh", "auto", False)
        self.assertEqual(self.bridge.moveTree(f"a:{action}", child, "inside"), f"a:{action}")
        self.assertEqual(self.bridge.moveTree(root, child, "inside"), "")
        self.assertEqual(self.bridge.editGroup(root, "新开发", "rename"), "g:新开发")
        self.assertEqual(self.bridge.editGroup("g:新开发", "", "remove"), "")
        self.assertEqual(self.bridge.moveTree("g:新开发", empty, "inside"), "g:空分组/新开发")
        second = Workbench()
        self.addCleanup(second.close)
        row = next(item for item in second.actionTree if item["key"] == action)
        self.assertEqual(row["parentKey"], "g:空分组/新开发/安卓")
        builtin = next(item for item in second.actionTree if item["key"] == "preset-keep-awake")
        self.assertEqual(builtin["parentKey"], "b:电源与锁屏")

    def test_pinned_command_requires_confirmation_and_uses_clicked_directory(self) -> None:
        action = self.bridge.saveAction("", "编译", "echo build", "zsh", "auto", False)
        target = f"action:{action}"
        requests = []
        self.bridge.shellRunRequested.connect(lambda name, folder: requests.append((name, folder)))
        with patch("ddtool.workbench.IS_MACOS", False), patch("ddtool.workbench.apply_integration"), \
                patch.object(self.bridge, "_run_action") as execute:
            self.assertEqual(self.bridge.saveShellConfig(ShortcutConfig(True, mode="pinned", targets=(target,)).values()), "")
            self.bridge.activate_shell(Activation("directory", str(self.directory), entry_token("settings")))
            self.assertEqual(requests, [])
            request = Activation("directory", str(self.directory), entry_token(target))
            self.assertEqual(Activation.decode(request.encode()), request)
            self.bridge.activate_shell(request)
            self.assertEqual(requests, [("编译", str(self.directory))])
            execute.assert_not_called()
            self.bridge.confirmShellRun(False)
            execute.assert_not_called()
            self.bridge.activate_shell(request)
            self.bridge.confirmShellRun(True)
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[1], self.directory)
            self.bridge.deleteAction(action)
            self.assertFalse(self.bridge.shellConfig["enabled"])

    def test_pinned_direct_run_uses_folder_without_opening_workbench(self) -> None:
        action = self.bridge.saveAction("", "编译", "echo build", "zsh", "auto", False)
        target = f"action:{action}"
        request = Activation("directory", str(self.directory), entry_token(target))
        config = ShortcutConfig(True, mode="pinned", targets=(target,), direct_run=True)
        destinations, requests = [], []
        self.bridge.navigate.connect(destinations.append)
        self.bridge.shellRunRequested.connect(lambda *args: requests.append(args))
        with patch("ddtool.workbench.IS_MACOS", False), patch("ddtool.workbench.apply_integration"), \
                patch.object(self.bridge, "_run_action") as execute:
            self.assertEqual(self.bridge.saveShellConfig(config.values()), "")
            self.assertTrue(ShortcutConfig.load(self.directory / "shell-shortcuts.json").direct_run)
            self.bridge.activate_shell(request)
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[1], self.directory)
            self.assertEqual((destinations, requests), ([], []))
            self.bridge.activate_shell(Activation("directory", str(self.directory), entry_token("power")))
            self.bridge.activate_shell(Activation("directory", str(self.directory / "missing"), entry_token(target)))
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(self.bridge.saveAction(action, "编译", "echo changed", "zsh", "auto", False), action)
            self.assertFalse(self.bridge.shellConfig["direct_run"])
            self.bridge.activate_shell(request)
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(requests, [("编译", str(self.directory))])
