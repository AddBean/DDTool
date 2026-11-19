from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from ddtool.local_activation import receive_activations
from ddtool.macos_shortcuts import OWNER, WORKFLOW_NAME, apply_registration as apply_macos, write_workflow
from ddtool.shell_shortcuts import MAX_MESSAGE, Activation, ShortcutConfig, entry_token
from ddtool.windows_shortcuts import LOCATIONS, VERB, apply_registration as apply_windows, launch_command, plain_menu_label


class ShellShortcutTests(unittest.TestCase):
    def test_configuration_round_trip_and_validation(self) -> None:
        config = ShortcutConfig(True, "开发工具", "chooser", ("power", "folder"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shortcuts.json"
            config.save(path)
            self.assertEqual(ShortcutConfig.load(path), config)
        for override in ({"mode": "command"}, {"targets": ["power", "power"]},
                         {"targets": [{"key": "power"}]}, {"label": "a&b"}, {"targets": []}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                ShortcutConfig.parse({**config.values(), **override})
        self.assertEqual(ShortcutConfig.parse({**config.values(), "mode": "folder", "targets": []}).mode, "folder")

    def test_activation_keeps_quoted_unicode_and_rejects_other_payloads(self) -> None:
        path = "C:\\中文 空格\\' $;"
        request = Activation.parse(["--shell-shortcut", "directory", path])
        self.assertEqual(Activation.decode(request.encode()), request)
        self.assertEqual(Activation.decode(Activation("desktop").encode()), Activation("desktop"))
        for payload in (b'["exec","/tmp"]\n', b'["finder",1]\n', b'["directory",""]\n', b"{}", b"a" * MAX_MESSAGE):
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                Activation.decode(payload)
        self.assertIsNone(Activation("directory", ".").existing_directory())

    def test_windows_command_uses_folder_placeholders_not_a_shell(self) -> None:
        executable = Path(r"C:\Program Files\DDTool\DDTool.exe")
        for scope, expected in (("desktop", ""), ("background", r' "%V\."'), ("directory", r' "%1\."')):
            with self.subTest(scope=scope):
                self.assertEqual(launch_command(executable, scope), f'"{executable}" --shell-shortcut {scope}{expected}')

    def test_windows_menu_labels_do_not_expand_resources_or_mnemonics(self) -> None:
        self.assertEqual(plain_menu_label(" @资源&工具\n "), "＠资源&&工具")

    @unittest.skipUnless(sys.platform == "win32", "requires the Windows registry")
    def test_windows_real_registry_isolated_registration(self) -> None:
        import winreg

        base = rf"Software\DDToolTest-{uuid4()}"
        locations = {scope: rf"{base}\{scope}" for scope in LOCATIONS}
        executable = Path(r"C:\Program Files\DDTool\DDTool.exe")
        config = ShortcutConfig(True, "开发工作台")
        foreign = rf"{locations['desktop']}\{VERB}"
        with patch("ddtool.windows_shortcuts.LOCATIONS", locations):
            try:
                apply_windows(config, executable)
                for scope, parent in locations.items():
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{parent}\{VERB}") as key:
                        self.assertEqual(winreg.QueryValueEx(key, "MUIVerb")[0], config.label)
                        if scope == "directory":
                            self.assertEqual(winreg.QueryValueEx(key, "MultiSelectModel")[0], "Single")
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{parent}\{VERB}\command") as key:
                        self.assertEqual(winreg.QueryValueEx(key, "")[0], launch_command(executable, scope))
                apply_windows(replace(config, label="我的入口"), executable)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, foreign) as key:
                    self.assertEqual(winreg.QueryValueEx(key, "MUIVerb")[0], "我的入口")
                pinned = replace(config, mode="pinned", targets=("folder", "action:sample"))
                labels = {"folder": "打开目录", "action:sample": "构建"}
                apply_windows(pinned, executable, labels=labels)
                for scope, parent in locations.items():
                    for target in pinned.targets:
                        token = entry_token(target)
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{parent}\{VERB}.{token}\command") as key:
                            self.assertEqual(winreg.QueryValueEx(key, "")[0], launch_command(executable, scope, token))
                apply_windows(ShortcutConfig(), executable, only_matching=True)
                for parent in locations.values():
                    with self.assertRaises(FileNotFoundError):
                        winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{parent}\{VERB}.{entry_token('folder')}")
                apply_windows(ShortcutConfig(), executable)
                for parent in locations.values():
                    with self.assertRaises(FileNotFoundError):
                        winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{parent}\{VERB}")
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, foreign) as key:
                    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "foreign")
                with self.assertRaises(ValueError):
                    apply_windows(config, executable)
                apply_windows(ShortcutConfig(), executable)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, foreign) as key:
                    self.assertEqual(winreg.QueryValueEx(key, "MUIVerb")[0], "foreign")
            finally:
                apply_windows(ShortcutConfig(), executable)
                for path in [foreign, *locations.values(), base]:
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
                    except FileNotFoundError:
                        pass

    def test_macos_workflow_is_installed_updated_removed_and_checks_ownership(self) -> None:
        config = ShortcutConfig(True, "开发工具")
        with tempfile.TemporaryDirectory() as directory, patch("ddtool.macos_shortcuts._refresh_services") as refresh:
            services = Path(directory)
            executable = services / "豆 荚.app" / "Contents" / "MacOS" / "DDTool"
            apply_macos(config, executable, services)
            destination = services / WORKFLOW_NAME
            info_path = destination / "Contents" / "Info.plist"
            info = plistlib.loads(info_path.read_bytes())
            self.assertEqual(info["CFBundleIdentifier"], OWNER)
            self.assertEqual(info["NSServices"][0]["NSSendFileTypes"], ["public.folder"])
            apply_macos(replace(config, label="我的入口"), executable, services)
            self.assertEqual(plistlib.loads(info_path.read_bytes())["CFBundleName"], "我的入口")
            apply_macos(ShortcutConfig(), executable, services)
            self.assertFalse(destination.exists())
            self.assertEqual(refresh.call_count, 3)
            destination.mkdir()
            with self.assertRaises(ValueError):
                apply_macos(config, executable, services)
            apply_macos(ShortcutConfig(), executable, services)
            self.assertTrue(destination.is_dir())

    @unittest.skipUnless(sys.platform == "darwin", "requires the macOS Automator runner")
    def test_automator_passes_exact_folder_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            folder = parent / "中文 空格 ' $;"
            folder.mkdir()
            output = parent / "argv.txt"
            workflow = parent / "Test.workflow"
            script = 'printf "%s" "$2" > "$1"'
            write_workflow(workflow, "测试入口", ["/bin/sh", "-c", script, "ddtool-test", str(output)])
            result = subprocess.run(["/usr/bin/automator", "-i", str(folder), str(workflow)],
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(output.read_text(encoding="utf-8"), str(folder))

    def test_secondary_instance_forwards_context_and_receives_ack(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication([])
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        name = f"ddtool-test-{uuid4().hex}"
        received = []
        receive_activations(server, received.append)
        self.assertTrue(server.listen(name), server.errorString())
        self.addCleanup(server.close)
        request = Activation("directory", "C:\\中文 文件夹")
        script = (
            "import sys; from PySide6.QtCore import QCoreApplication; "
            "from ddtool.local_activation import send_activation; from ddtool.shell_shortcuts import Activation; "
            "app = QCoreApplication([]); sys.exit(not send_activation(sys.argv[1], Activation(*sys.argv[2:])))"
        )
        with subprocess.Popen([sys.executable, "-c", script, name, request.scope, request.directory]) as client:
            deadline = time.monotonic() + 6
            while client.poll() is None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)
            if client.poll() is None:
                client.kill()
            self.assertEqual(client.wait(), 0)
        self.assertEqual(received, [request])
