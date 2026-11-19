from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QLockFile, QMetaObject, QObject, QTimer, Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ddtool.config import APP_NAME, APP_TITLE, get_config_dir
from ddtool.local_activation import receive_activations, send_activation
from ddtool.quick_actions import MenuTree
from ddtool.resources import bundled_icon_png
from ddtool.shell_shortcuts import Activation, ShortcutConfig
from ddtool.workbench import Workbench


def build_window(bridge: Workbench, warnings: list[str] | None = None) -> tuple[QQmlApplicationEngine, QQuickWindow]:
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    if warnings is not None:
        engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.rootContext().setContextProperty("workbench", bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    roots = engine.rootObjects()
    if not roots or not isinstance(roots[0], QQuickWindow):
        raise RuntimeError("Could not load the DDTool workbench.")
    return engine, roots[0]


class Desktop:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.bridge = Workbench()
        self.engine, self.window = build_window(self.bridge)
        self.menu = QMenu()
        self.tray = QSystemTrayIcon(app.windowIcon(), app)
        self.tray.setToolTip(APP_TITLE)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activate)
        self.bridge.actionsChanged.connect(self._rebuild_menu)
        self.bridge.navigate.connect(self.show)
        self.window.setProperty("canHide", QSystemTrayIcon.isSystemTrayAvailable())
        self.window.quitRequested.connect(app.quit)
        self._rebuild_menu()
        if self.window.property("canHide"):
            self.tray.show()

    def show(self, page: str = "") -> None:
        if page:
            self.window.setProperty("page", page)
        if self.window.windowState() == Qt.WindowState.WindowMinimized:
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def activate(self, activation: Activation) -> None:
        if activation.scope:
            self.bridge.activate_shell(activation)
        else:
            self.show()

    def _activate(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show()

    def _rebuild_menu(self) -> None:
        self.menu.clear()
        self.menu.addAction("打开工作台", lambda: self.show())
        self.menu.addSeparator()
        phone = self.menu.addMenu("手机工具")
        for label, operation in (("手机镜像", "mirror"), ("安装手机 MCP", "mcp"),
                                 ("启动网络共享", "network"), ("停止网络共享", "stop-network")):
            phone.addAction(label, lambda checked=False, value=operation: self._run_device(value))
        self.menu.addAction("防睡眠", lambda: self.show("power"))
        self.menu.addAction("推迟锁屏", self.bridge.postponeLock)
        tree = self.bridge.tray_tree()
        if tree.has_items:
            self._add_nodes(self.menu.addMenu("快捷操作"), tree)
        self.menu.addSeparator()
        self.menu.addAction("退出豆荚工具", self.app.quit)

    def _run_device(self, operation: str) -> None:
        self.show("activity")
        self.bridge.runDevice(operation)

    def _add_nodes(self, menu: QMenu, node: MenuTree) -> None:
        for kind, value in node.entries:
            if kind == "menu":
                self._add_nodes(menu.addMenu(value), node.children[value])
            else:
                menu.addAction(value.name, lambda checked=False, key=value.id: self.bridge.runAction(key))


def _socket_name() -> str:
    key = hashlib.sha256(str(get_config_dir().resolve()).encode()).hexdigest()[:20]
    return f"ddtool-{key}"


def main() -> int:
    arguments = sys.argv[1:]
    try:
        activation = Activation.parse(arguments)
    except ValueError:
        return 2
    background = arguments == ["--background"]
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setWindowIcon(QIcon(str(bundled_icon_png())))
    app.setQuitOnLastWindowClosed(False)
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config_dir / "workbench.lock"))
    lock.setStaleLockTime(0)
    server_name = _socket_name()
    if not lock.tryLock(0):
        return 0 if background or send_activation(server_name, activation) else 1

    desktop = Desktop(app)
    server = QLocalServer(app)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(server_name)

    receive_activations(server, desktop.activate)
    if not server.listen(server_name):
        desktop.bridge.close()
        raise RuntimeError(server.errorString())
    if not background:
        desktop.activate(activation)
    if not desktop.window.isVisible() and not desktop.window.property("canHide"):
        desktop.show()
    QTimer.singleShot(2500, desktop.bridge.auto_check_updates)
    try:
        return app.exec()
    finally:
        server.close()
        desktop.tray.hide()
        QMetaObject.invokeMethod(desktop.window, "persist")
        _dispose_window(desktop.engine, desktop.window)
        desktop.bridge.close()
        lock.unlock()


def _dispose_window(engine: QQmlApplicationEngine, window: QQuickWindow) -> None:
    window.hide()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(engine, QEvent.Type.DeferredDelete)


def ui_smoke_test() -> int:
    from unittest.mock import patch

    from PySide6.QtCore import QPointF
    from PySide6.QtTest import QTest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    app = QApplication(sys.argv)
    with (
        tempfile.TemporaryDirectory() as directory,
        patch("ddtool.config.get_config_dir", return_value=Path(directory)),
        patch("ddtool.quick_actions.get_config_dir", return_value=Path(directory)),
        patch("ddtool.workbench.get_config_dir", return_value=Path(directory)),
    ):
        bridge = Workbench()
        warnings: list[str] = []
        engine, window = build_window(bridge, warnings)
        window.show()
        test_action = bridge.saveAction("", "冒烟/测试操作", "echo DDTool", "zsh" if bridge.mac else "cmd", "auto", False)
        if not test_action:
            warnings.append("Could not add the smoke-test action.")
        for page in ("actions", "devices", "power", "activity", "settings", "context"):
            window.setProperty("page", page)
            app.processEvents()
        save_button = window.findChild(QObject, "saveShellShortcuts")
        with patch("ddtool.workbench.apply_integration") as register:
            if save_button is not None:
                QMetaObject.invokeMethod(save_button, "click")
            if not register.called:
                warnings.append("The shortcut form did not submit valid settings.")
            bridge.saveShellConfig(ShortcutConfig(True).values())
            bridge.activate_shell(Activation("finder" if bridge.mac else "directory", directory))
            app.processEvents()
            if bridge.shellDirectory != directory:
                warnings.append("The shortcut did not receive the folder context.")
        window.setProperty("page", "actions")
        app.processEvents()
        group_key = bridge.editGroup("", "拖拽目标", "create")
        app.processEvents()

        def visual_child(parent, name):
            if parent.objectName() == name:
                return parent
            for child in parent.childItems():
                if found := visual_child(child, name):
                    return found
            return None

        def point_for(name, fraction=0.5):
            item = visual_child(window.contentItem(), name)
            return item.mapToScene(QPointF(item.width() / 2, item.height() * fraction)).toPoint() if item is not None else None

        source_name = f"treeDrag:a:{test_action}"
        action_key = f"a:{test_action}"
        target_name = f"treeDrop:{group_key}"
        tree_list = visual_child(window.contentItem(), "actionTreeList")
        initial_order = [item["treeKey"] for item in bridge.actionTree]
        for fraction, placement, cancel in ((0.1, "before", True), (0.9, "after", False), (0.1, "before", False), (0.5, "inside", False)):
            source = point_for(source_name)
            target = point_for(target_name, fraction)
            if source is None or target is None or tree_list is None:
                warnings.append("Could not locate the tree drag handle or drop target.")
                break
            if placement == "inside":
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=target)
                app.processEvents()
            QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=source)
            QTest.mouseMove(window, target, 30)
            if tree_list.property("placement") != placement:
                warnings.append(f"The action tree did not show the {placement} drop indicator.")
            if cancel:
                QTest.keyClick(window, Qt.Key.Key_Escape)
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=target)
            app.processEvents()
            order = [item["treeKey"] for item in bridge.actionTree]
            if cancel:
                if tree_list.property("dragging") or order != initial_order:
                    warnings.append("Escape did not cancel the pending move.")
            elif placement in {"before", "after"}:
                offset = -1 if placement == "before" else 1
                if order.index(action_key) != order.index(group_key) + offset:
                    warnings.append(f"The action was not dropped {placement} the target group.")
            elif placement == "inside" and not (
                any(item["treeKey"] == action_key and item["parentKey"] == group_key for item in bridge.actionTree)
                and point_for(source_name) is not None
            ):
                warnings.append("Dropping into a collapsed group did not move and reveal the action.")

        if tree_list is not None:
            scroll_groups = [bridge.editGroup("", f"滚动测试 {index + 1}", "create") for index in range(32)]
            app.processEvents()
            source = point_for(source_name)
            edge = tree_list.mapToScene(QPointF(tree_list.width() / 2, tree_list.height() - 6)).toPoint()
            original_y = tree_list.property("contentY")
            if source is None:
                warnings.append("Could not locate the action for the auto-scroll drag.")
            else:
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=source)
                QTest.mouseMove(window, edge, 30)
                QTest.qWait(800)
                scroll_distance = tree_list.property("contentY") - original_y
                target_key = tree_list.property("targetKey")
                placement = tree_list.property("placement")
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=edge)
                app.processEvents()
                if scroll_distance <= 320 or target_key not in scroll_groups:
                    warnings.append("Dragging near the bottom did not scroll to a distant drop target.")
                else:
                    order = [item["treeKey"] for item in bridge.actionTree]
                    offset = -1 if placement == "before" else 1
                    if order.index(action_key) != order.index(target_key) + offset:
                        warnings.append("Releasing after auto-scroll did not drop at the indicated location.")
        QMetaObject.invokeMethod(window, "openPalette")
        app.processEvents()
        palette = window.findChild(QObject, "commandPalette")
        if palette is None or not palette.property("visible"):
            warnings.append("The command palette did not open.")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        bridge.deleteAction(test_action)
        if tree_list is not None:
            for key in scroll_groups:
                bridge.editGroup(key, "", "remove")
        bridge.setAppearance("light", "blue", True)
        app.processEvents()
        bridge.setAppearance("dark", "mint", False)
        snapshot = os.environ.get("DDTOOL_UI_SNAPSHOT")
        if snapshot:
            window.resize(1120, 740)
            app.processEvents()
            window.grabWindow().save(snapshot)
        _dispose_window(engine, window)
        bridge.close()
        marker = os.environ.get("DDTOOL_UI_SMOKE_RESULT")
        if marker:
            Path(marker).write_text("\n".join(warnings) if warnings else "OK", encoding="utf-8")
        if warnings and sys.stderr is not None:
            print("\n".join(warnings), file=sys.stderr)
        return int(bool(warnings) or not bridge.actionItems)
