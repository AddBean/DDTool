from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from tkinter import Tk, filedialog, messagebox
from typing import Callable

import pystray
from pystray import Menu, MenuItem

from ddtool.autostart import is_enabled as is_autostart_enabled, set_enabled as set_autostart_enabled
from ddtool.config import (
    APP_NAME,
    APP_TITLE,
    AppConfig,
    build_export_payload,
    load_config,
    parse_import_payload,
    replace_config,
)
from ddtool.icon import create_tray_icon
from ddtool.macos_ui import hide_dock_icon
from ddtool.platform import IS_MACOS, IS_WINDOWS
from ddtool.phone_forward import ForwardController
from ddtool.quick_actions import (
    BUILTIN_COMMAND_POSTPONE_LOCK,
    BUILTIN_TOP_MENUS,
    SETTINGS_MENU,
    SYSTEM_SHORTCUTS_MENU,
    MenuTree,
    QuickAction,
    build_action_tree,
    dump_quick_actions_store,
    load_quick_actions,
    replace_quick_actions_store,
    run_quick_action,
    show_add_quick_action_dialog,
    show_reorder_quick_actions_dialog,
)
from ddtool.resources import bundled_icon_ico
from ddtool.phone_mirror import MirrorController
from ddtool.phone_network import NetworkController
from ddtool.system_lock import LockScreenDelayer


class DDToolTrayApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.withdraw()
        hide_dock_icon()
        ico = bundled_icon_ico()
        if IS_WINDOWS and ico.exists():
            self.root.iconbitmap(default=str(ico))

        self.root.title(APP_TITLE)
        config = load_config()
        self.mirror = MirrorController(config)
        self.forward = ForwardController(config)
        self.network = NetworkController(config)
        self.lock_screen = LockScreenDelayer()
        self.icon = pystray.Icon(
            APP_NAME,
            create_tray_icon(),
            APP_TITLE,
            Menu(self._tray_menu_items),
        )

    def run(self) -> None:
        if IS_MACOS:
            # Cocoa requires status-bar setup on the main thread. run_detached
            # prepares pystray before Tk takes over the application loop.
            self.icon.run_detached()
            self.root.mainloop()
            return
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.mainloop()

    def _run_on_ui(self, callback: Callable[[], None]) -> None:
        """Run a tray callback safely on Tk's UI thread.

        Cocoa invokes status-menu callbacks on the macOS main thread already.
        Scheduling those callbacks again with ``Tk.after`` can leave a Tcl
        timer pointing at Python while NSApplication is shutting down, which
        aborts the process in ``PyEval_RestoreThread``.  Windows pystray
        callbacks still arrive on its worker thread and must use ``after``.
        """
        if IS_MACOS:
            callback()
            return
        self.root.after(0, callback)

    @staticmethod
    def _notify(icon: pystray.Icon, message: str) -> None:
        try:
            icon.notify(message, APP_TITLE)
        except (NotImplementedError, AttributeError):
            pass

    # -- 手机菜单回调 ------------------------------------------------

    def _mirror_phone(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(self.mirror.start)

    def _install_mcp(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(self.forward.install)

    def _start_network(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(self.network.start)

    def _stop_network(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(self._stop_network_on_ui)

    def _stop_network_on_ui(self) -> None:
        self.network.stop()
        messagebox.showinfo(APP_TITLE, "网络共享已停止。")

    # -- 系统功能 ---------------------------------------------------

    def _postpone_lock_screen(self, icon: pystray.Icon, _item: MenuItem) -> None:
        self.lock_screen.postpone()
        self._notify(icon, "已推迟 1 小时后自动锁屏")

    # -- 快捷操作 ---------------------------------------------------

    def _tray_menu_items(self):
        tree = build_action_tree(load_quick_actions())
        has_custom = False
        for kind, value in tree.entries:
            if kind == "menu":
                if value in BUILTIN_TOP_MENUS:
                    continue
                has_custom = True
                yield MenuItem(value, Menu(self._make_node_menu(tree.children[value])))
            else:
                has_custom = True
                yield MenuItem(value.name, self._make_run_quick_action(value))
        if has_custom:
            yield Menu.SEPARATOR
        yield MenuItem("手机操作", Menu(self._make_phone_menu(tree)))
        system_node = tree.children.get(SYSTEM_SHORTCUTS_MENU)
        if system_node and system_node.has_items:
            yield MenuItem(SYSTEM_SHORTCUTS_MENU, Menu(self._make_node_menu(system_node)))
        else:
            yield MenuItem(SYSTEM_SHORTCUTS_MENU, Menu(self._empty_menu))
        yield MenuItem("快捷操作", Menu(self._make_quick_menu()))
        yield MenuItem(SETTINGS_MENU, Menu(self._make_settings_menu()))
        yield MenuItem("退出", self._quit)

    def _empty_menu(self):
        yield MenuItem("（暂无操作）", None, enabled=False)

    def _make_phone_menu(self, tree: MenuTree):
        def generate():
            yield MenuItem("镜像手机", self._mirror_phone)
            yield MenuItem("安装MCP", self._install_mcp)
            yield MenuItem("共享网络", self._start_network)
            yield MenuItem("停止共享", self._stop_network)
            extra = tree.children.get("手机操作")
            if extra and extra.has_items:
                yield Menu.SEPARATOR
                yield from self._yield_node_items(extra)

        return generate

    def _make_quick_menu(self):
        def generate():
            yield MenuItem("添加操作", self._add_quick_action)
            yield MenuItem("编辑操作", self._reorder_quick_actions)

        return generate

    def _make_settings_menu(self):
        def generate():
            yield MenuItem(
                "开机启动",
                self._toggle_autostart,
                checked=lambda _item: is_autostart_enabled(),
            )
            yield Menu.SEPARATOR
            yield MenuItem("导出配置", self._export_settings)
            yield MenuItem("导入配置", self._import_settings)

        return generate

    def _make_node_menu(self, node: MenuTree):
        def generate():
            yield from self._yield_node_items(node)

        return generate

    def _yield_node_items(self, node: MenuTree):
        for kind, value in node.entries:
            if kind == "menu":
                yield MenuItem(value, Menu(self._make_node_menu(node.children[value])))
            else:
                yield MenuItem(value.name, self._make_run_quick_action(value))

    def _add_quick_action(self, icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(lambda: self._open_add_quick_action_dialog(icon))

    def _open_add_quick_action_dialog(self, icon: pystray.Icon) -> None:
        show_add_quick_action_dialog(self.root, icon.update_menu)

    def _reorder_quick_actions(self, icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(lambda: self._open_reorder_quick_actions_dialog(icon))

    def _open_reorder_quick_actions_dialog(self, icon: pystray.Icon) -> None:
        show_reorder_quick_actions_dialog(self.root, icon.update_menu)

    def _make_run_quick_action(self, action: QuickAction):
        def _run(icon: pystray.Icon, item: MenuItem) -> None:
            if action.command == BUILTIN_COMMAND_POSTPONE_LOCK:
                self._postpone_lock_screen(icon, item)
                return
            self._run_on_ui(lambda a=action: run_quick_action(a))

        return _run

    def _toggle_autostart(self, icon: pystray.Icon, _item: MenuItem) -> None:
        enable = not is_autostart_enabled()
        try:
            set_autostart_enabled(enable)
        except OSError as exc:
            self._run_on_ui(
                lambda: messagebox.showerror(APP_TITLE, f"设置开机启动失败：\n{exc}")
            )
            return
        self._notify(icon, "已开启开机启动" if enable else "已关闭开机启动")

    def _export_settings(self, icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(lambda: self._export_settings_on_ui(icon))

    def _import_settings(self, icon: pystray.Icon, _item: MenuItem) -> None:
        self._run_on_ui(lambda: self._import_settings_on_ui(icon))

    def _pick_settings_file(self, *, save: bool) -> str:
        self.root.attributes("-topmost", True)
        try:
            if save:
                return filedialog.asksaveasfilename(
                    parent=self.root,
                    title="导出配置",
                    defaultextension=".json",
                    filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
                    initialfile=f"豆荚工具-配置-{date.today().isoformat()}.json",
                )
            return filedialog.askopenfilename(
                parent=self.root,
                title="导入配置",
                filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            )
        finally:
            self.root.attributes("-topmost", False)

    def _export_settings_on_ui(self, icon: pystray.Icon) -> None:
        filename = self._pick_settings_file(save=True)
        if not filename:
            return
        payload = build_export_payload(dump_quick_actions_store())
        try:
            Path(filename).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"导出配置失败：\n{exc}")
            return
        self._notify(icon, "配置已导出")

    def _import_settings_on_ui(self, icon: pystray.Icon) -> None:
        filename = self._pick_settings_file(save=False)
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            config_data, quick_actions_data = parse_import_payload(data)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            messagebox.showerror(APP_TITLE, f"导入配置失败：\n{exc}")
            return
        if config_data is None and quick_actions_data is None:
            messagebox.showerror(APP_TITLE, "配置文件里没有可导入的内容。")
            return
        parts: list[str] = []
        if config_data is not None:
            parts.append("工具配置")
        if quick_actions_data is not None:
            parts.append("快捷操作")
        if not messagebox.askyesno(
            APP_TITLE,
            f"导入将覆盖当前的{'、'.join(parts)}，确定继续？",
        ):
            return
        try:
            if config_data is not None:
                self._apply_imported_config(replace_config(config_data))
            if quick_actions_data is not None:
                replace_quick_actions_store(quick_actions_data)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror(APP_TITLE, f"导入配置失败：\n{exc}")
            return
        icon.update_menu()
        self._notify(icon, "配置已导入")

    def _apply_imported_config(self, config: AppConfig) -> None:
        self.mirror.config = config
        self.forward.config = config
        self.network.config = config

    # -- 退出 -------------------------------------------------------

    def _quit(self, icon: pystray.Icon, _item: MenuItem) -> None:
        self.forward.stop()
        self.network.stop()
        self.mirror.stop()
        self.lock_screen.cancel()
        if IS_MACOS:
            # icon.stop() stops the shared NSApplication.  With Tk owning that
            # same Cocoa loop, stopping it before a queued root.destroy callback
            # lets Tcl call into an already-finalizing Python interpreter.
            icon.visible = False
            self.root.quit()
            self.root.destroy()
            return
        icon.stop()
        self.root.after(0, self.root.destroy)


def main() -> None:
    DDToolTrayApp().run()
