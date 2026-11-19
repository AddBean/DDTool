from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from ddtool import autostart, quick_actions as actions
from ddtool.config import (
    AppConfig, build_export_payload, get_config_dir, load_config, parse_import_payload, save_config,
)
from ddtool.keep_awake import DURATION_PRESETS, END_ACTION_LABELS, EndAction, KeepAwakeController
from ddtool.notices import Reporter
from ddtool.phone_forward import ForwardController
from ddtool.phone_mirror import MirrorController
from ddtool.phone_network import NetworkController
from ddtool.platform import IS_MACOS
from ddtool.shell_shortcuts import Activation, ShortcutConfig, TARGETS, apply_integration
from ddtool.system_lock import LockScreenDelayer


MAX_KEEP_AWAKE_MINUTES = 48 * 60


class Workbench(QObject):
    actionsChanged = Signal()
    activityChanged = Signal()
    preferencesChanged = Signal()
    powerChanged = Signal()
    busyChanged = Signal()
    latestChanged = Signal()
    shellConfigChanged = Signal()
    shellContextChanged = Signal()
    navigate = Signal(str)
    _reported = Signal(str, str)
    _finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._settings = QSettings(str(get_config_dir() / "workbench.ini"), QSettings.Format.IniFormat)
        self._shell_path = get_config_dir() / "shell-shortcuts.json"
        self._shell = ShortcutConfig.load(self._shell_path)
        self._shell_directory: Path | None = None
        self._shell_source = ""
        self._actions: list[actions.QuickAction] = []
        self._activity: list[dict[str, str]] = []
        self._latest = "工作台就绪"
        self._latest_error = False
        self._busy = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ddtool")
        reporter = Reporter(self._reported.emit)
        self.mirror = MirrorController(self._config, reporter=reporter)
        self.forward = ForwardController(self._config, reporter=reporter)
        self.network = NetworkController(self._config, reporter=reporter)
        self.keep_awake = KeepAwakeController()
        self.lock_screen = LockScreenDelayer()
        self._reported.connect(self._record, Qt.ConnectionType.QueuedConnection)
        self._finished.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self, interval=1000, timeout=self._tick_power)
        self._power = self.keep_awake.status()
        self.refresh_actions()

    @Property("QVariantList", notify=actionsChanged)
    def actionItems(self) -> list[dict]:
        return [
            {
                "key": action.id, "name": action.name, "group": action.menu_path or "未分组",
                "location": actions.action_full_path(action), "command": action.command,
                "shell": action.shell, "terminal": action.terminal, "keepTerminal": action.keep_terminal,
                "preset": action.id.startswith("preset-"), "builtin": action.command.startswith("ddtool:"),
            }
            for action in self._actions
        ]

    @Property("QVariantList", notify=activityChanged)
    def activity(self) -> list[dict]:
        return self._activity

    @Property(str, notify=latestChanged)
    def latest(self) -> str:
        return self._latest

    @Property(bool, notify=latestChanged)
    def latestError(self) -> bool:
        return self._latest_error

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, constant=True)
    def mac(self) -> bool:
        return IS_MACOS

    @Property(bool, constant=True)
    def shellSupported(self) -> bool:
        return sys.platform in ("darwin", "win32")

    @Property(bool, constant=True)
    def shellCanInstall(self) -> bool:
        return self.shellSupported and getattr(sys, "frozen", False)

    @Property("QVariantMap", notify=shellConfigChanged)
    def shellConfig(self) -> dict:
        return self._shell.values()

    @Property("QVariantList", constant=True)
    def shellTargets(self) -> list[dict]:
        return [{"key": key, "label": label, "detail": detail} for key, (label, detail) in TARGETS.items()]

    @Property(str, notify=shellContextChanged)
    def shellDirectory(self) -> str:
        return str(self._shell_directory) if self._shell_directory is not None else ""

    @Property(str, notify=shellContextChanged)
    def shellSource(self) -> str:
        return self._shell_source

    @Slot("QVariantMap", result=str)
    def saveShellConfig(self, values: dict) -> str:
        try:
            config = ShortcutConfig.parse(values)
            config.save(self._shell_path)
        except (OSError, ValueError) as exc:
            return str(exc)
        try:
            apply_integration(config)
        except (OSError, ValueError) as exc:
            try:
                self._shell.save(self._shell_path)
                apply_integration(self._shell)
            except (OSError, ValueError):
                return f"应用失败：{exc}；未能完全恢复旧设置，请检查权限后重试。"
            return str(exc)
        self._shell = config
        self.shellConfigChanged.emit()
        self._record("info", "系统右键入口已启用" if config.enabled else "系统右键入口已关闭")
        return ""

    def activate_shell(self, activation: Activation) -> None:
        if not self._shell.enabled:
            self.navigate.emit("context")
            return
        scopes = ("finder",) if IS_MACOS else ("desktop", "background", "directory")
        if activation.scope not in scopes:
            return
        directory = activation.existing_directory()
        if activation.scope == "desktop" and not activation.directory:
            desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
            directory = Activation("desktop", desktop).existing_directory()
        self._shell_directory = directory
        self._shell_source = {"finder": "Finder 文件夹", "directory": "选中的文件夹",
                              "background": "文件夹空白处", "desktop": "桌面"}[activation.scope]
        self.shellContextChanged.emit()
        if self._shell.mode == "chooser":
            self.navigate.emit("context")
        else:
            self._open_shell_target(self._shell.mode)

    @Slot(str)
    def openShellTarget(self, target: str) -> None:
        if self._shell.enabled and self._shell_source and target in self._shell.targets:
            self._open_shell_target(target)

    def _open_shell_target(self, target: str) -> None:
        if target == "folder":
            folder = self._shell_directory
            if folder is None or not folder.is_dir() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                self._record("error", "无法打开本次右键对应的文件夹。")
                self.navigate.emit("context")
        elif target in TARGETS:
            self.navigate.emit(target)

    @Property(str, notify=preferencesChanged)
    def theme(self) -> str:
        return self._settings.value("appearance/theme", "dark", str)

    @Property(str, notify=preferencesChanged)
    def accent(self) -> str:
        return self._settings.value("appearance/accent", "mint", str)

    @Property(bool, notify=preferencesChanged)
    def compact(self) -> bool:
        return self._settings.value("appearance/compact", False, bool)

    @Property(bool, notify=preferencesChanged)
    def autostartEnabled(self) -> bool:
        return autostart.is_enabled()

    @Property(str, notify=powerChanged)
    def powerStatus(self) -> str:
        return self._power.message

    @Property(bool, notify=powerChanged)
    def powerActive(self) -> bool:
        return self._power.active

    @Property(int, constant=True)
    def maximumPowerMinutes(self) -> int:
        return MAX_KEEP_AWAKE_MINUTES

    @Property("QVariantList", constant=True)
    def durations(self) -> list[dict]:
        return [{"label": label, "minutes": seconds // 60} for seconds, label in DURATION_PRESETS]

    @Property("QVariantList", constant=True)
    def endActions(self) -> list[dict]:
        return [{"key": action.value, "label": label} for action, label in END_ACTION_LABELS.items()]

    @Slot(str, result=int)
    def layoutValue(self, key: str) -> int:
        defaults = {"width": 1120, "height": 740, "details": 368, "collapsed": 0, "detailsHidden": 0}
        try:
            return self._settings.value(f"layout/{key}", defaults[key], int)
        except (KeyError, TypeError, ValueError):
            return 0

    @Slot(str, int)
    def saveLayoutValue(self, key: str, value: int) -> None:
        if key in {"width", "height", "details", "collapsed", "detailsHidden"}:
            self._settings.setValue(f"layout/{key}", value)

    @Slot(str, str, bool)
    def setAppearance(self, theme: str, accent: str, compact: bool) -> None:
        if theme not in {"dark", "light"} or accent not in {"mint", "blue", "amber"}:
            return
        for key, value in (("theme", theme), ("accent", accent), ("compact", compact)):
            self._settings.setValue(f"appearance/{key}", value)
        self.preferencesChanged.emit()

    @Slot(bool)
    def setAutostart(self, enabled: bool) -> None:
        self._attempt(lambda: autostart.set_enabled(enabled), "登录启动设置已更新")
        self.preferencesChanged.emit()

    @Slot()
    def openConfigDirectory(self) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_config_dir()))):
            self._record("error", "无法打开配置目录。")

    @Slot(str)
    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self._latest = "已复制到剪贴板"
        self._latest_error = False
        self.latestChanged.emit()

    @Slot()
    def clearActivity(self) -> None:
        self._activity = []
        self.activityChanged.emit()

    def refresh_actions(self) -> None:
        self._actions = actions.load_quick_actions()
        self.actionsChanged.emit()

    def tray_tree(self) -> actions.MenuTree:
        return actions.build_action_tree(self._actions)

    @Slot(str, str, str, str, str, bool, result=str)
    def saveAction(self, key: str, location: str, command: str, shell: str, terminal: str, keep: bool) -> str:
        def save() -> str:
            name, group = actions.split_location(location)
            if not name or not command.strip():
                raise ValueError("请填写操作名称和命令。")
            if actions.parse_menu_path(group or name)[0:1] in {("退出",), (actions.SETTINGS_MENU,)}:
                raise ValueError("该菜单名称由应用保留。")
            if command.lstrip().startswith("ddtool:"):
                raise ValueError("该命令前缀由应用保留。")
            if key and not self._editable(key):
                raise ValueError("只能修改已存在的自定义操作。")
            args = (location, command, keep, shell, terminal)
            saved = actions.update_quick_action(key, *args) if key else actions.add_quick_action(*args)
            if saved is None:
                raise ValueError("该操作已不存在。")
            self.refresh_actions()
            return saved.id

        return self._attempt(save, "操作已保存") or ""

    @Slot(str)
    def deleteAction(self, key: str) -> None:
        if self._editable(key):
            self._attempt(lambda: (actions.delete_quick_action(key), self.refresh_actions()), "操作已删除")

    @Slot(str, int)
    def moveAction(self, key: str, step: int) -> None:
        if step not in {-1, 1} or not self._editable(key):
            return
        def move() -> None:
            order = actions.list_custom_actions()
            current = next((index for index, action in enumerate(order) if action.id == key), -1)
            target = current + step
            if current >= 0 and 0 <= target < len(order):
                order[current], order[target] = order[target], order[current]
                actions.replace_custom_order(order)
                self.refresh_actions()
        self._attempt(move)

    def _editable(self, key: str) -> bool:
        return any(action.id == key and not key.startswith("preset-") for action in self._actions)

    @Slot(str)
    def runAction(self, key: str) -> None:
        action = next((action for action in self._actions if action.id == key), None)
        if action is None:
            return
        if action.command == actions.BUILTIN_COMMAND_KEEP_AWAKE:
            self.navigate.emit("power")
        elif action.command == actions.BUILTIN_COMMAND_POSTPONE_LOCK:
            self.postponeLock()
        else:
            def run() -> None:
                errors: list[str] = []
                actions.run_quick_action(action, Reporter(lambda _level, message: errors.append(message)))
                if errors:
                    self._reported.emit("error", "\n".join(errors))
                else:
                    self._reported.emit("info", f"已发起：{action.name}（不跟踪命令退出状态）")
            self._submit(action.name, run)

    @Slot(str)
    def runDevice(self, operation: str) -> None:
        operations = {
            "mirror": ("启动手机镜像", self.mirror.start),
            "mcp": ("安装手机 MCP", self.forward.install),
            "network": ("启动网络共享", self.network.start),
            "stop-network": ("停止网络共享", self._stop_network),
        }
        if operation in operations:
            name, callback = operations[operation]
            self._submit(name, callback)

    def _stop_network(self) -> None:
        self.network.stop()
        self._reported.emit("info", "网络共享已停止。")

    @Slot()
    def postponeLock(self) -> None:
        self._attempt(self.lock_screen.postpone, "已推迟 1 小时后自动锁屏")

    @Slot(int, str, bool)
    def startPower(self, minutes: int, end: str, allow_display_off: bool) -> None:
        if not 1 <= minutes <= MAX_KEEP_AWAKE_MINUTES:
            self._record("error", f"请输入 1 到 {MAX_KEEP_AWAKE_MINUTES} 分钟。")
            return
        self._attempt(lambda: self.keep_awake.start(minutes * 60, EndAction(end), allow_display_off=allow_display_off), "已启用防睡眠")
        self._tick_power()
        if self._power.active:
            self._timer.start()

    @Slot()
    def stopPower(self) -> None:
        self._attempt(lambda: self.keep_awake.stop(run_end_action=False), "已停止防睡眠")
        self._tick_power()

    @Slot()
    def _tick_power(self) -> None:
        self._power = self.keep_awake.status()
        if not self._power.active:
            self._timer.stop()
        self.powerChanged.emit()

    @Slot(QUrl)
    def exportConfig(self, url: QUrl) -> None:
        if url.isLocalFile():
            self._attempt(lambda: Path(url.toLocalFile()).write_text(
                json.dumps(build_export_payload(actions.dump_quick_actions_store()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            ), "配置已导出")

    @Slot(QUrl)
    def importConfig(self, url: QUrl) -> None:
        if not url.isLocalFile() or self._busy:
            return
        def load() -> None:
            raw = json.loads(Path(url.toLocalFile()).read_text(encoding="utf-8-sig"))
            config_data, action_data = parse_import_payload(raw)
            if config_data is None and action_data is None:
                raise ValueError("配置文件没有可导入的内容。")
            config = AppConfig.from_dict(config_data) if config_data is not None else None
            if action_data is not None:
                actions.replace_quick_actions_store(action_data)
            if config is not None:
                save_config(config)
                self._config = config
                self.mirror.config = config
                self.forward.config = config
                self.network.config = config
            self.refresh_actions()
        self._attempt(load, "配置已导入；运行导入的命令前请检查内容。")

    def _attempt(self, callback: Callable, success: str = ""):
        try:
            result = callback()
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            self._record("error", str(exc))
            return None
        if success:
            self._record("info", success)
        return result

    def _submit(self, name: str, callback: Callable[[], None]) -> None:
        if self._busy:
            self._record("info", "请等待正在处理的操作。")
            return
        self._busy = True
        self.busyChanged.emit()
        self._record("info", f"正在处理：{name}")

        def run() -> None:
            try:
                callback()
            except Exception as exc:
                logging.getLogger(__name__).exception("Operation failed")
                self._reported.emit("error", f"{name}：{exc}")
            finally:
                self._finished.emit()

        self._executor.submit(run)

    @Slot()
    def _finish(self) -> None:
        self._busy = False
        self.busyChanged.emit()

    @Slot(str, str)
    def _record(self, level: str, message: str) -> None:
        entry = {"level": level, "text": message, "time": datetime.now().strftime("%H:%M:%S")}
        self._activity = [entry, *self._activity[:199]]
        self._latest = message.splitlines()[0] if message else ""
        self._latest_error = level == "error"
        self.activityChanged.emit()
        self.latestChanged.emit()

    def close(self) -> None:
        self._timer.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
        callbacks = [self.lock_screen.cancel, self.keep_awake.stop, self.mirror.stop, self.forward.stop]
        if self.network.process is not None or self.network.dns_proxy is not None:
            callbacks.append(self.network.stop)
        for callback in callbacks:
            try:
                callback()
            except Exception:
                logging.getLogger(__name__).exception("Shutdown cleanup failed")
        self._settings.sync()
