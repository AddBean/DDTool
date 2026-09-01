from __future__ import annotations

import json
import locale
import os
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import BooleanVar, StringVar, TclError, Text, Toplevel, messagebox, ttk
import tkinter as tk
from typing import Any, Callable

from ddtool.config import APP_TITLE, get_config_dir
from ddtool.macos_ui import configure_command_text, configure_dialog
from ddtool.platform import IS_MACOS

_open_dialog: Toplevel | None = None
_reorder_dialog: Toplevel | None = None
DEFAULT_MENU_NAME = "快捷操作"
SYSTEM_SHORTCUTS_MENU = "系统快捷"
SETTINGS_MENU = "工具设置"
RESERVED_TOP_MENUS = frozenset({"退出", SETTINGS_MENU})
BUILTIN_TOP_MENUS = (DEFAULT_MENU_NAME, "手机操作", SYSTEM_SHORTCUTS_MENU, SETTINGS_MENU)
FIXED_TRAY_MENUS = ("手机操作", SYSTEM_SHORTCUTS_MENU, DEFAULT_MENU_NAME, SETTINGS_MENU, "退出")
LOCKED_MENU_ROOTS = frozenset({SYSTEM_SHORTCUTS_MENU, "手机操作"})
BUILTIN_COMMAND_POSTPONE_LOCK = "ddtool:postpone-lock"
SHELL_CMD = "cmd"
SHELL_POWERSHELL = "powershell"
SHELL_ZSH = "zsh"
TERMINAL_AUTO = "auto"
TERMINAL_GHOSTTY = "ghostty"
TERMINAL_APPLE = "terminal"
TERMINAL_ITERM2 = "iterm2"
TERMINAL_CHOICES = (
    (TERMINAL_AUTO, "自动（优先 Ghostty）"),
    (TERMINAL_GHOSTTY, "Ghostty"),
    (TERMINAL_APPLE, "Terminal"),
    (TERMINAL_ITERM2, "iTerm2"),
)
DEFAULT_SHELL = SHELL_ZSH if IS_MACOS else SHELL_CMD


def context_menu_events() -> tuple[str, ...]:
    """Return pointer gestures that open a context menu on this platform."""
    if IS_MACOS:
        # Aqua Tk reports a trackpad/two-finger click as Button-2 on some
        # versions, Button-3 on others; Control-click remains Button-1.
        return ("<Button-2>", "<Button-3>", "<Control-Button-1>")
    return ("<Button-3>",)


def bind_context_menu(widget: Any, handler: Callable[[Any], str]) -> None:
    for sequence in context_menu_events():
        widget.bind(sequence, handler, add="+")


@dataclass(slots=True)
class QuickAction:
    id: str
    name: str
    command: str
    keep_terminal: bool = False
    menu_path: str = ""
    shell: str = DEFAULT_SHELL
    terminal: str = TERMINAL_AUTO

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuickAction | None":
        command = _normalize_command(str(data.get("command") or ""))
        if not command:
            return None
        location = str(data.get("location") or "").strip()
        if location:
            name, menu_path = split_location(location)
        else:
            name = str(data.get("name") or "").strip()
            menu_path = normalize_menu_path(str(data.get("menu_path") or ""))
        if not name:
            return None
        action_id = str(data.get("id") or "").strip() or uuid.uuid4().hex
        if "shell" in data:
            shell = _normalize_shell(data.get("shell"))
        else:
            shell = _infer_shell(command)
        return cls(
            id=action_id,
            name=name,
            command=command,
            keep_terminal=bool(data.get("keep_terminal", False)),
            menu_path=menu_path,
            shell=shell,
            terminal=_normalize_terminal(data.get("terminal")),
        )


class MenuTree:
    def __init__(self) -> None:
        self.children: dict[str, MenuTree] = {}
        self.entries: list[tuple[str, Any]] = []

    @property
    def has_items(self) -> bool:
        return bool(self.entries)

    def add(self, parts: tuple[str, ...], action: QuickAction) -> None:
        if not parts:
            self.entries.append(("action", action))
            return
        head, *tail = parts
        if head not in self.children:
            self.children[head] = MenuTree()
            self.entries.append(("menu", head))
        self.children[head].add(tuple(tail), action)


def parse_menu_path(raw: str) -> tuple[str, ...]:
    text = (raw or "").replace("\\", "/")
    parts = tuple(part.strip() for part in text.split("/") if part.strip())
    if parts and parts[0] == DEFAULT_MENU_NAME:
        return parts[1:]
    return parts


def normalize_menu_path(raw: str) -> str:
    return "/".join(parse_menu_path(raw))


def split_location(raw: str) -> tuple[str, str]:
    parts = parse_menu_path(raw)
    if not parts:
        return "", ""
    return parts[-1], "/".join(parts[:-1])


def action_menu_parts(action: QuickAction) -> tuple[str, ...]:
    return parse_menu_path(action.menu_path)


def action_full_path(action: QuickAction) -> str:
    parts = action_menu_parts(action)
    if not parts:
        return action.name
    return "/".join((*parts, action.name))


def collect_menu_paths(actions: list[QuickAction]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        if path and path not in seen:
            seen.add(path)
            found.append(path)

    _add(SYSTEM_SHORTCUTS_MENU)
    for action in actions:
        parts = parse_menu_path(action.menu_path)
        for index in range(len(parts)):
            _add("/".join(parts[: index + 1]))
    return found


def build_action_tree(actions: list[QuickAction]) -> MenuTree:
    root = MenuTree()
    for action in actions:
        root.add(action_menu_parts(action), action)
    return root


WINDOWS_QUICK_ACTIONS = (
    QuickAction("preset-postpone-lock", "推迟锁屏", BUILTIN_COMMAND_POSTPONE_LOCK, False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-ipconfig", "查看 IP", "ipconfig", True, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-flushdns", "刷新 DNS", "ipconfig /flushdns", True, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-netstat", "查看端口占用", "netstat -ano", True, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-ncpa", "网络连接", "ncpa.cpl", False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-devmgmt", "设备管理器", "devmgmt.msc", False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-taskmgr", "任务管理器", "taskmgr", False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-env", "系统环境变量", "rundll32.exe sysdm.cpl,EditEnvironmentVariables", False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-explorer", "重启资源管理器", "taskkill /f /im explorer.exe & start explorer.exe", False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-hosts", "打开 hosts", r"notepad %SystemRoot%\System32\drivers\etc\hosts", False, SYSTEM_SHORTCUTS_MENU),
    QuickAction("preset-powershell", "打开 PowerShell", "start powershell", False, SYSTEM_SHORTCUTS_MENU),
)

MACOS_QUICK_ACTIONS = (
    QuickAction("preset-postpone-lock", "推迟锁屏", BUILTIN_COMMAND_POSTPONE_LOCK, False, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-ifconfig", "查看 IP", "ifconfig", True, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-flushdns-macos", "刷新 DNS", "sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder", True, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-netstat-macos", "查看端口占用", "lsof -nP -iTCP -sTCP:LISTEN", True, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-network-settings-macos", "网络设置", "open 'x-apple.systempreferences:com.apple.Network-Settings.extension'", False, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-activity-monitor", "活动监视器", "open -a 'Activity Monitor'", False, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-hosts-macos", "打开 hosts", "open -a TextEdit /etc/hosts", False, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
    QuickAction("preset-terminal", "打开终端", "open -a Terminal", False, SYSTEM_SHORTCUTS_MENU, SHELL_ZSH),
)

DEFAULT_QUICK_ACTIONS = MACOS_QUICK_ACTIONS if IS_MACOS else WINDOWS_QUICK_ACTIONS


def get_quick_actions_path() -> Path:
    return get_config_dir() / "quick_actions.json"


def _parse_actions(raw_items: Any) -> tuple[list[QuickAction], bool]:
    if not isinstance(raw_items, list):
        return [], False
    actions: list[QuickAction] = []
    changed = False
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if "shell" not in item or (IS_MACOS and "terminal" not in item):
            changed = True
        action = QuickAction.from_dict(item)
        if action:
            actions.append(action)
    return actions, changed


def _preset_ids() -> set[str]:
    return {preset.id for preset in DEFAULT_QUICK_ACTIONS}


def _custom_newest_first(actions: list[QuickAction]) -> list[QuickAction]:
    preset_ids = _preset_ids()
    custom = [action for action in actions if action.id not in preset_ids]
    presets = [action for action in actions if action.id in preset_ids]
    return [*reversed(custom), *presets]


def _read_store() -> tuple[list[QuickAction], list[str], bool, bool]:
    path = get_quick_actions_path()
    if not path.exists():
        return [], [], False, True

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], [], False, True

    if isinstance(data, list):
        actions, changed = _parse_actions(data)
        return actions, [], changed, False
    if not isinstance(data, dict):
        return [], [], False, True

    seeded = [
        str(item)
        for item in data.get("seeded_presets", [])
        if str(item).strip()
    ]
    actions, changed = _parse_actions(data.get("actions", []))
    newest_first = data.get("order") == "newest_first"
    return actions, seeded, changed, newest_first


def _write_store(actions: list[QuickAction], seeded_presets: list[str]) -> None:
    path = get_quick_actions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "seeded_presets": seeded_presets,
                "order": "newest_first",
                "actions": [asdict(action) for action in actions],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _merge_presets(
    actions: list[QuickAction],
    seeded_presets: list[str],
) -> tuple[list[QuickAction], list[str], bool]:
    existing_ids = {action.id for action in actions}
    existing_names = {action.name for action in actions}
    seeded = set(seeded_presets)
    changed = False
    merged = list(actions)
    for preset in DEFAULT_QUICK_ACTIONS:
        if preset.id in seeded:
            continue
        seeded.add(preset.id)
        changed = True
        if preset.id in existing_ids or preset.name in existing_names:
            continue
        merged.append(preset)
    return merged, sorted(seeded), changed


def _relocate_presets(actions: list[QuickAction]) -> tuple[list[QuickAction], bool]:
    presets = {preset.id: preset for preset in DEFAULT_QUICK_ACTIONS}
    changed = False
    updated: list[QuickAction] = []
    for action in actions:
        preset = presets.get(action.id)
        if preset is not None and action.menu_path == "":
            action = QuickAction(
                id=action.id,
                name=action.name,
                command=action.command,
                keep_terminal=action.keep_terminal,
                menu_path=preset.menu_path,
                shell=action.shell,
                terminal=action.terminal,
            )
            changed = True
        updated.append(action)
    return updated, changed


def load_quick_actions() -> list[QuickAction]:
    actions, seeded_presets, migrated, newest_first = _read_store()
    actions, relocated = _relocate_presets(actions)
    actions, seeded_presets, changed = _merge_presets(actions, seeded_presets)
    if not newest_first:
        actions = _custom_newest_first(actions)
    if relocated or changed or migrated or not newest_first or not get_quick_actions_path().exists():
        _write_store(actions, seeded_presets)
    return actions


def save_quick_actions(actions: list[QuickAction]) -> None:
    _, seeded_presets, _, _ = _read_store()
    _write_store(actions, sorted(set(seeded_presets)))


def dump_quick_actions_store() -> dict[str, Any]:
    load_quick_actions()
    actions, seeded_presets, _, _ = _read_store()
    return {
        "seeded_presets": seeded_presets,
        "order": "newest_first",
        "actions": [asdict(action) for action in actions],
    }


def replace_quick_actions_store(data: Any) -> None:
    if isinstance(data, list):
        actions, _ = _parse_actions(data)
        _write_store(_custom_newest_first(actions), [])
        return
    if not isinstance(data, dict):
        raise ValueError("快捷操作配置格式无效")
    seeded = [
        str(item)
        for item in data.get("seeded_presets", [])
        if str(item).strip()
    ]
    actions, _ = _parse_actions(data.get("actions", []))
    if data.get("order") != "newest_first":
        actions = _custom_newest_first(actions)
    _write_store(actions, seeded)


def add_quick_action(
    location: str,
    command: str,
    keep_terminal: bool,
    shell: str = DEFAULT_SHELL,
    terminal: str = TERMINAL_AUTO,
) -> QuickAction:
    name, menu_path = split_location(location)
    action = QuickAction(
        id=uuid.uuid4().hex,
        name=name,
        command=_normalize_command(command),
        keep_terminal=keep_terminal,
        menu_path=menu_path,
        shell=_normalize_shell(shell),
        terminal=_normalize_terminal(terminal),
    )
    actions = load_quick_actions()
    actions.insert(0, action)
    save_quick_actions(actions)
    return action


def update_quick_action(
    action_id: str,
    location: str,
    command: str,
    keep_terminal: bool,
    shell: str = DEFAULT_SHELL,
    terminal: str = TERMINAL_AUTO,
) -> QuickAction | None:
    name, menu_path = split_location(location)
    updated: QuickAction | None = None
    actions: list[QuickAction] = []
    for action in load_quick_actions():
        if action.id != action_id:
            actions.append(action)
            continue
        updated = QuickAction(
            id=action.id,
            name=name,
            command=_normalize_command(command),
            keep_terminal=keep_terminal,
            menu_path=menu_path,
            shell=_normalize_shell(shell),
            terminal=_normalize_terminal(terminal),
        )
        actions.append(updated)
    if updated is None:
        return None
    save_quick_actions(actions)
    return updated


def delete_quick_action(action_id: str) -> None:
    save_quick_actions(
        [action for action in load_quick_actions() if action.id != action_id]
    )


def list_custom_actions() -> list[QuickAction]:
    preset_ids = _preset_ids()
    return [action for action in load_quick_actions() if action.id not in preset_ids]


def replace_custom_order(custom: list[QuickAction]) -> None:
    preset_ids = _preset_ids()
    current = load_quick_actions()
    presets = [action for action in current if action.id in preset_ids]
    by_id = {action.id: action for action in current if action.id not in preset_ids}
    ordered: list[QuickAction] = []
    seen: set[str] = set()
    for action in custom:
        original = by_id.get(action.id)
        if original is None or action.id in seen:
            continue
        seen.add(action.id)
        if original.menu_path != action.menu_path:
            original = QuickAction(
                id=original.id,
                name=original.name,
                command=original.command,
                keep_terminal=original.keep_terminal,
                menu_path=action.menu_path,
                shell=original.shell,
                terminal=original.terminal,
            )
        ordered.append(original)
    for action in current:
        if action.id not in preset_ids and action.id not in seen:
            ordered.append(action)
    save_quick_actions(ordered + presets)


CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)


def _normalize_command(command: str) -> str:
    return command.replace("\r\n", "\n").replace("\r", "\n").strip()


def _normalize_shell(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if IS_MACOS:
        if value in {"powershell", "pwsh", "ps"}:
            return SHELL_POWERSHELL
        return SHELL_ZSH
    if value in {"powershell", "pwsh", "ps"}:
        return SHELL_POWERSHELL
    return SHELL_CMD


def _normalize_terminal(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    supported = {key for key, _label in TERMINAL_CHOICES}
    return value if value in supported else TERMINAL_AUTO


def _infer_shell(command: str) -> str:
    if IS_MACOS:
        return SHELL_ZSH
    lowered = command.lstrip().lower()
    if lowered.startswith(("powershell ", "powershell.exe", "pwsh ", "pwsh.exe")):
        return SHELL_CMD
    if lowered.startswith("$") or ".ps1" in lowered:
        return SHELL_POWERSHELL
    return SHELL_CMD


def _write_command_script(command: str, shell: str = DEFAULT_SHELL) -> str:
    if shell == SHELL_ZSH:
        suffix = ".command"
        encoding = "utf-8"
        newline = "\n"
    elif shell == SHELL_POWERSHELL:
        suffix = ".ps1"
        encoding = "utf-8-sig"
        newline = "\n"
    else:
        suffix = ".cmd"
        encoding = locale.getpreferredencoding(False) or "utf-8"
        newline = "\r\n"
    fd, path = tempfile.mkstemp(prefix="ddtool-quick-", suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding=encoding, errors="replace", newline=newline) as handle:
            if shell == SHELL_ZSH:
                handle.write("#!/bin/zsh\n")
                handle.write(command)
                handle.write("\n")
                handle.write('rm -f -- "$0"\n')
            elif shell == SHELL_POWERSHELL:
                handle.write(command)
                handle.write("\n")
                handle.write(
                    "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n"
                )
            else:
                handle.write("@echo off\n")
                handle.write(command)
                handle.write("\n")
                handle.write('del "%~f0" >nul 2>&1\n')
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    if shell == SHELL_ZSH:
        os.chmod(path, 0o700)
    return path


def _popen_detached(args: list[str], *, cwd: str, creationflags: int) -> None:
    kwargs = {
        "cwd": cwd,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    try:
        subprocess.Popen(args, creationflags=creationflags, **kwargs)
        return
    except OSError:
        fallback = creationflags & ~CREATE_BREAKAWAY_FROM_JOB
        if fallback == creationflags:
            raise
        subprocess.Popen(args, creationflags=fallback, **kwargs)


def run_quick_action(action: QuickAction) -> None:
    if action.command.startswith("ddtool:"):
        messagebox.showerror(APP_TITLE, f"无法执行内置快捷操作：\n{action.command}")
        return
    shell = _normalize_shell(action.shell)
    command = _normalize_command(action.command)
    if IS_MACOS:
        _run_macos_quick_action(command, action.keep_terminal, action.terminal)
        return
    use_script = "\n" in command or shell == SHELL_POWERSHELL
    if use_script:
        try:
            command = _write_command_script(command, shell)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"写入临时脚本失败：\n{exc}")
            return
    cwd = os.path.expanduser("~")
    # 从 Cursor 等宿主进程里启动时，直接 CreateProcess(cmd) 会被校验拦截。
    # 用 start 拉开进程树，并允许脱离父 Job。
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
    if shell == SHELL_POWERSHELL:
        powershell = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            command,
        ]
        if action.keep_terminal:
            args = ["cmd.exe", "/c", "start", "", "powershell.exe", "-NoExit", *powershell[1:]]
        else:
            args = ["cmd.exe", "/c", *powershell]
            flags |= DETACHED_PROCESS
    elif action.keep_terminal:
        # start 把第一个带引号的参数当成窗口标题。无空格的「豆荚工具」
        # 不会被 list2cmdline 加引号，会被当成要启动的程序，于是弹出
        # 「Windows 找不到文件'豆荚工具'」。空字符串会被加引号变成 ""。
        args = ["cmd.exe", "/c", "start", "", "cmd.exe", "/d", "/k", command]
    else:
        args = ["cmd.exe", "/c", command]
        flags |= DETACHED_PROCESS
    try:
        _popen_detached(args, cwd=cwd, creationflags=flags)
    except OSError as exc:
        messagebox.showerror(APP_TITLE, f"执行快捷操作失败：\n{exc}")


def _macos_app_exists(app_name: str) -> bool:
    candidates = (
        Path("/Applications") / app_name,
        Path.home() / "Applications" / app_name,
    )
    return any(candidate.exists() for candidate in candidates)


def _resolve_macos_terminal(terminal: str) -> str:
    terminal = _normalize_terminal(terminal)
    if terminal != TERMINAL_AUTO:
        return terminal
    if _macos_app_exists("Ghostty.app"):
        return TERMINAL_GHOSTTY
    if _macos_app_exists("iTerm.app"):
        return TERMINAL_ITERM2
    return TERMINAL_APPLE


def macos_terminal_launch_args(script: str, terminal: str) -> list[str]:
    terminal = _resolve_macos_terminal(terminal)
    if terminal == TERMINAL_GHOSTTY:
        return [
            "open",
            "-na",
            "Ghostty.app",
            "--args",
            "-e",
            "/bin/zsh",
            script,
        ]
    if terminal == TERMINAL_ITERM2:
        return ["open", "-a", "iTerm", script]
    return ["open", "-a", "Terminal", script]


def _run_macos_quick_action(
    command: str,
    keep_terminal: bool,
    terminal: str = TERMINAL_AUTO,
) -> None:
    try:
        if keep_terminal:
            script = _write_command_script(command, SHELL_ZSH)
            subprocess.Popen(
                macos_terminal_launch_args(script, terminal),
                cwd=str(Path.home()),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        subprocess.Popen(
            ["/bin/zsh", "-lc", command],
            cwd=str(Path.home()),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        messagebox.showerror(APP_TITLE, f"执行快捷操作失败：\n{exc}")


def show_add_quick_action_dialog(
    parent: Any,
    on_saved: Callable[[], None] | None = None,
) -> None:
    show_quick_action_dialog(parent, on_saved)


def show_edit_quick_action_dialog(
    parent: Any,
    action: QuickAction,
    on_saved: Callable[[], None] | None = None,
) -> None:
    show_quick_action_dialog(parent, on_saved, action=action)


def show_reorder_quick_actions_dialog(
    parent: Any,
    on_saved: Callable[[], None] | None = None,
) -> None:
    global _reorder_dialog
    if _reorder_dialog is not None:
        try:
            if _reorder_dialog.winfo_exists():
                _reorder_dialog.destroy()
        except TclError:
            pass
        _reorder_dialog = None

    all_actions = load_quick_actions()
    actions_by_id = {action.id: action for action in all_actions}
    preset_ids = _preset_ids()

    dialog = Toplevel(parent)
    _reorder_dialog = dialog
    dialog.title("编辑快捷操作")
    dialog.minsize(420, 460)
    dialog.attributes("-topmost", True)
    palette = configure_dialog(dialog)

    ttk.Label(
        dialog,
        text="拖动排列：文件夹上半=前方，下半=放入组内；操作上半=前方，下半=后方；空白=顶层。右键删除自定义操作。",
        wraplength=380,
        justify="left",
        style="DDTool.Secondary.TLabel" if IS_MACOS else "TLabel",
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 8))

    tree_frame = ttk.Frame(
        dialog, style="DDTool.TFrame" if IS_MACOS else "TFrame"
    )
    tree_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=16, pady=8)
    style = ttk.Style(dialog)
    tree_style = "DDTool.Treeview" if IS_MACOS else "Reorder.Treeview"
    if not IS_MACOS:
        style.configure(tree_style, rowheight=26)
    tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", style=tree_style)
    scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)
    if palette is not None:
        tree.tag_configure("folder", foreground=palette.text)
        tree.tag_configure("locked", foreground=palette.secondary_text)
        tree.tag_configure("action", foreground=palette.text)
        tree.tag_configure("preset", foreground=palette.secondary_text)
        tree.tag_configure(
            "drop", background=palette.selected, foreground=palette.selected_text
        )
    else:
        tree.tag_configure("folder", foreground="#1a365d")
        tree.tag_configure("locked", foreground="#888888")
        tree.tag_configure("action", foreground="#222222")
        tree.tag_configure("preset", foreground="#666666")
        tree.tag_configure("drop", background="#d0e7ff")

    def _ensure_folder(parts: tuple[str, ...]) -> str:
        parent = ""
        path_parts: list[str] = []
        for part in parts:
            path_parts.append(part)
            path = "/".join(path_parts)
            iid = f"folder:{path}"
            if not tree.exists(iid):
                tags = ["folder"]
                if path in LOCKED_MENU_ROOTS:
                    tags.append("locked")
                tree.insert(parent, "end", iid=iid, text=part, open=True, tags=tuple(tags))
            parent = iid
        return parent

    for action in all_actions:
        parts = action_menu_parts(action)
        parent = _ensure_folder(parts) if parts else ""
        tags = ("action",) if action.id not in preset_ids else ("action", "preset")
        tree.insert(parent, "end", iid=f"action:{action.id}", text=action.name, tags=tags)

    if not tree.get_children(""):
        tree.insert("", "end", iid="empty", text="（暂无快捷操作）", tags=("locked",))

    drag: dict[str, Any] = {"iid": None, "x": 0, "y": 0, "active": False, "drop": None}

    def _folder_path(iid: str) -> str:
        return iid[7:] if iid.startswith("folder:") else ""

    def _action_id(iid: str) -> str:
        return iid[7:]

    def _is_locked(iid: str) -> bool:
        return bool(iid) and "locked" in tree.item(iid, "tags")

    def _is_preset(iid: str) -> bool:
        return bool(iid) and "preset" in tree.item(iid, "tags")

    def _is_descendant(item: str, ancestor: str) -> bool:
        current = item
        while current:
            current = tree.parent(current)
            if current == ancestor:
                return True
        return False

    def _tags_without_drop(iid: str) -> tuple[str, ...]:
        return tuple(tag for tag in tree.item(iid, "tags") if tag != "drop")

    def _clear_drop_highlight() -> None:
        previous = drag["drop"]
        if previous and tree.exists(previous):
            tree.item(previous, tags=_tags_without_drop(previous))
        drag["drop"] = None

    def _set_drop_highlight(iid: str | None) -> None:
        if drag["drop"] == iid:
            return
        _clear_drop_highlight()
        if iid and tree.exists(iid):
            tree.item(iid, tags=(*_tags_without_drop(iid), "drop"))
            drag["drop"] = iid

    def _prune_empty_folders() -> None:
        def prune(parent: str = "") -> None:
            for iid in list(tree.get_children(parent)):
                if iid.startswith("folder:"):
                    prune(iid)
                    if not tree.get_children(iid) and not _is_locked(iid):
                        tree.delete(iid)

        prune()

    def _persist() -> None:
        def walk(parent: str, path: str) -> None:
            for iid in tree.get_children(parent):
                if iid.startswith("action:"):
                    actions_by_id[_action_id(iid)].menu_path = path
                else:
                    folder_name = tree.item(iid, "text")
                    new_path = f"{path}/{folder_name}" if path else folder_name
                    walk(iid, new_path)

        walk("", "")
        _prune_empty_folders()
        ordered: list[QuickAction] = []

        def collect(parent: str = "") -> None:
            for iid in tree.get_children(parent):
                if iid.startswith("action:"):
                    ordered.append(actions_by_id[_action_id(iid)])
                else:
                    collect(iid)

        collect()
        save_quick_actions(ordered)
        if on_saved:
            on_saved()

    def _can_drop(src: str, target: str | None, event_y: int) -> str | None:
        """返回 'before' / 'into' / 'after' / 'root' / None。"""
        if not src or not tree.exists(src) or _is_locked(src) or src == "empty":
            return None
        src_parent = tree.parent(src)
        src_in_locked = src_parent != "" and _is_locked(src_parent)
        if not target or not tree.exists(target) or target == "empty":
            return None if src_in_locked else "root"
        if src == target or _is_descendant(target, src):
            return None
        target_is_folder = target.startswith("folder:")
        target_parent = tree.parent(target)
        target_in_locked = target_parent != "" and _is_locked(target_parent)
        target_is_locked_folder = target_is_folder and _is_locked(target)
        bbox = tree.bbox(target)
        if not bbox:
            return None
        upper = (event_y - bbox[1]) < bbox[3] / 2
        if src_in_locked:
            if target_parent != src_parent or target_is_locked_folder:
                return None
            return "before" if upper else "after"
        if target_is_locked_folder or target_in_locked:
            return None
        if target_is_folder:
            return "before" if upper else "into"
        return "before" if upper else "after"

    def _apply_drop(src: str, target: str | None, event_y: int) -> bool:
        zone = _can_drop(src, target, event_y)
        if zone is None:
            return False
        if zone == "root":
            tree.move(src, "", "end")
            return True
        if zone == "into":
            tree.move(src, target, "end")
            return True
        dest_parent = tree.parent(target)
        siblings = [iid for iid in tree.get_children(dest_parent) if iid != src]
        if target not in siblings:
            return False
        idx = siblings.index(target)
        if zone == "after":
            idx += 1
        tree.move(src, dest_parent, idx)
        return True

    def _on_press(event: Any) -> None:
        if tree.identify_element(event.x, event.y) == "Treeitem.indicator":
            drag["iid"] = None
            return
        iid = tree.identify_row(event.y)
        drag["iid"] = iid if iid and not _is_locked(iid) else None
        drag["x"] = event.x
        drag["y"] = event.y
        drag["active"] = False

    def _on_motion(event: Any) -> None:
        src = drag["iid"]
        if not src:
            return
        if not drag["active"]:
            if abs(event.x - drag["x"]) < 6 and abs(event.y - drag["y"]) < 6:
                return
            drag["active"] = True
            tree.configure(cursor="hand2")
            tree.selection_set(src)
        target = tree.identify_row(event.y)
        if target and target != src and _can_drop(src, target, event.y) is not None:
            _set_drop_highlight(target)
        else:
            _set_drop_highlight(None)

    def _on_release(event: Any) -> None:
        src = drag["iid"]
        active = drag["active"]
        drag["iid"] = None
        drag["active"] = False
        tree.configure(cursor="")
        _clear_drop_highlight()
        if not src or not active:
            return
        if _apply_drop(src, tree.identify_row(event.y), event.y):
            _persist()
            if tree.exists(src):
                tree.selection_set(src)

    def _on_wheel(event: Any) -> str:
        tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _refresh_tree() -> None:
        new_actions = load_quick_actions()
        actions_by_id.clear()
        actions_by_id.update({a.id: a for a in new_actions})
        for iid in list(tree.get_children("")):
            tree.delete(iid)
        pids = _preset_ids()
        for action in new_actions:
            parts = action_menu_parts(action)
            parent = _ensure_folder(parts) if parts else ""
            tags = ("action",) if action.id not in pids else ("action", "preset")
            tree.insert(parent, "end", iid=f"action:{action.id}", text=action.name, tags=tags)
        if not tree.get_children(""):
            tree.insert("", "end", iid="empty", text="（暂无快捷操作）", tags=("locked",))

    def _edit_action(iid: str) -> None:
        if not iid.startswith("action:"):
            return
        action = actions_by_id.get(_action_id(iid))
        if action is None:
            return
        dialog.grab_release()
        dialog.attributes("-topmost", False)
        show_edit_quick_action_dialog(dialog, action, _refresh_tree)
        edit_dlg = _open_dialog
        if edit_dlg is not None and edit_dlg.winfo_exists():
            dialog.wait_window(edit_dlg)
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.focus_force()

    def _delete_action(iid: str) -> None:
        if not iid.startswith("action:") or _is_preset(iid):
            return
        action = actions_by_id.get(_action_id(iid))
        if action is None:
            return
        dialog.attributes("-topmost", False)
        confirmed = messagebox.askyesno(dialog, f"确定删除「{action.name}」？")
        dialog.attributes("-topmost", True)
        if not confirmed:
            return
        del actions_by_id[action.id]
        tree.delete(iid)
        _prune_empty_folders()
        if not tree.get_children(""):
            tree.insert("", "end", iid="empty", text="（暂无快捷操作）", tags=("locked",))
        _persist()

    def _on_right_click(event: Any) -> str:
        iid = tree.identify_row(event.y)
        if not iid or not tree.exists(iid) or iid == "empty":
            return "break"
        tree.selection_set(iid)
        menu = tk.Menu(dialog, tearoff=0)
        if iid.startswith("action:"):
            menu.add_command(label="编辑", command=lambda: _edit_action(iid))
            if _is_preset(iid):
                menu.add_command(label="内置操作不可删除", state="disabled")
            else:
                menu.add_command(label="删除", command=lambda: _delete_action(iid))
        else:
            menu.add_command(label="文件夹由其中的操作自动管理", state="disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _close() -> None:
        global _reorder_dialog
        _persist()
        if _reorder_dialog is dialog:
            _reorder_dialog = None
        dialog.destroy()

    tree.bind("<ButtonPress-1>", _on_press)
    tree.bind("<B1-Motion>", _on_motion)
    tree.bind("<ButtonRelease-1>", _on_release)
    tree.bind("<MouseWheel>", _on_wheel)
    bind_context_menu(tree, _on_right_click)

    ttk.Button(dialog, text="完成", width=8, command=_close).grid(
        row=2, column=1, sticky="e", padx=16, pady=(8, 16)
    )
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(1, weight=1)
    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.bind("<Escape>", lambda _event: _close())

    dialog.update_idletasks()
    width, height = 480, 520
    x = (dialog.winfo_screenwidth() - width) // 2
    y = (dialog.winfo_screenheight() - height) // 2
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.lift()
    dialog.focus_force()
    dialog.grab_set()


def show_quick_action_dialog(
    parent: Any,
    on_saved: Callable[[], None] | None = None,
    *,
    action: QuickAction | None = None,
) -> None:
    global _open_dialog
    if _open_dialog is not None:
        try:
            if _open_dialog.winfo_exists():
                _open_dialog.destroy()
        except TclError:
            pass
        _open_dialog = None

    editing = action is not None
    dialog = Toplevel(parent)
    _open_dialog = dialog
    dialog.title("编辑快捷操作" if editing else "添加快捷操作")
    dialog.minsize(600 if IS_MACOS else 520, 430 if IS_MACOS else 360)
    dialog.attributes("-topmost", True)
    palette = configure_dialog(dialog)

    location_var = StringVar(value=action_full_path(action) if action else "")
    keep_var = BooleanVar(value=action.keep_terminal if action else False)
    shell_var = StringVar(value=_normalize_shell(action.shell if action else DEFAULT_SHELL))
    terminal_labels = {key: label for key, label in TERMINAL_CHOICES}
    terminal_keys = {label: key for key, label in TERMINAL_CHOICES}
    terminal_var = StringVar(
        value=terminal_labels[_normalize_terminal(action.terminal if action else None)]
    )

    label_style = "DDTool.TLabel" if IS_MACOS else "TLabel"
    secondary_style = "DDTool.Secondary.TLabel" if IS_MACOS else "TLabel"
    frame_style = "DDTool.TFrame" if IS_MACOS else "TFrame"
    check_style = "DDTool.TCheckbutton" if IS_MACOS else "TCheckbutton"
    radio_style = "DDTool.TRadiobutton" if IS_MACOS else "TRadiobutton"

    ttk.Label(dialog, text="名称", style=label_style).grid(
        row=0, column=0, sticky="e", padx=(20, 10), pady=(20, 8)
    )
    location_entry = ttk.Combobox(
        dialog,
        textvariable=location_var,
        values=collect_menu_paths(load_quick_actions()),
        width=40,
    )
    location_entry.grid(row=0, column=1, columnspan=2, sticky="we", padx=(0, 20), pady=(20, 8))
    ttk.Label(
        dialog,
        text="可用 / 分层，最后一段是名称，如 快捷菜单/编译命令/编译项目",
        style=secondary_style,
    ).grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, 20))

    ttk.Label(dialog, text="指令", style=label_style).grid(
        row=2, column=0, sticky="ne", padx=(20, 10), pady=10
    )
    command_frame = ttk.Frame(dialog, style=frame_style)
    command_frame.grid(row=2, column=1, columnspan=2, sticky="nsew", padx=(0, 20), pady=10)
    command_text = Text(command_frame, width=42, height=8, wrap="none", undo=True, font="TkFixedFont")
    command_scroll_y = ttk.Scrollbar(command_frame, orient="vertical", command=command_text.yview)
    command_scroll_x = ttk.Scrollbar(command_frame, orient="horizontal", command=command_text.xview)
    command_text.configure(yscrollcommand=command_scroll_y.set, xscrollcommand=command_scroll_x.set)
    configure_command_text(command_text, palette)
    command_text.grid(row=0, column=0, sticky="nsew")
    command_scroll_y.grid(row=0, column=1, sticky="ns")
    command_scroll_x.grid(row=1, column=0, sticky="ew")
    command_frame.columnconfigure(0, weight=1)
    command_frame.rowconfigure(0, weight=1)
    if action is not None:
        command_text.insert("1.0", action.command)
    ttk.Label(
        dialog,
        text="支持多行；指令框内 Enter 换行，Ctrl+Enter 保存",
        style=secondary_style,
    ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(0, 20))

    ttk.Label(dialog, text="运行环境", style=label_style).grid(
        row=4, column=0, sticky="e", padx=(20, 10), pady=(14, 8)
    )
    options_row = ttk.Frame(dialog, style=frame_style)
    options_row.grid(row=4, column=1, columnspan=2, sticky="we", padx=(0, 20), pady=(14, 8))
    if IS_MACOS:
        ttk.Label(options_row, text="Shell", style=secondary_style).pack(side="left")
        shell_picker = ttk.Combobox(
            options_row,
            textvariable=shell_var,
            values=(SHELL_ZSH,),
            state="readonly",
            width=8,
        )
        shell_picker.pack(side="left", padx=(8, 20))
        ttk.Label(options_row, text="终端", style=secondary_style).pack(side="left")
        terminal_picker = ttk.Combobox(
            options_row,
            textvariable=terminal_var,
            values=tuple(label for _key, label in TERMINAL_CHOICES),
            state="readonly",
            width=20,
        )
        terminal_picker.pack(side="left", padx=(8, 0))
    else:
        ttk.Radiobutton(
            options_row, text="CMD", variable=shell_var, value=SHELL_CMD, style=radio_style
        ).pack(side="left")
        ttk.Radiobutton(
            options_row,
            text="PowerShell",
            variable=shell_var,
            value=SHELL_POWERSHELL,
            style=radio_style,
        ).pack(
            side="left", padx=(12, 0)
        )
    ttk.Checkbutton(
        dialog,
        text="执行后保留终端窗口",
        variable=keep_var,
        style=check_style,
    ).grid(row=5, column=1, columnspan=2, sticky="w", padx=(0, 20), pady=(0, 8))
    if IS_MACOS:
        ttk.Label(
            dialog,
            text="终端应用仅在保留窗口时使用；自动模式优先 Ghostty。",
            style=secondary_style,
        ).grid(row=6, column=1, columnspan=2, sticky="w", padx=(0, 20))

    def _close() -> None:
        global _open_dialog
        if _open_dialog is dialog:
            _open_dialog = None
        dialog.destroy()

    def _save(_event: Any = None) -> str | None:
        location = location_var.get().strip()
        command = _normalize_command(command_text.get("1.0", "end-1c"))
        name, menu_path = split_location(location)
        if not name:
            messagebox.showwarning(APP_TITLE, "请输入名称，例如 编译项目 或 快捷菜单/编译命令/编译项目。", parent=dialog)
            location_entry.focus_set()
            return "break"
        if not command:
            messagebox.showwarning(APP_TITLE, "请输入终端指令。", parent=dialog)
            command_text.focus_set()
            return "break"
        parts = parse_menu_path(location)
        if parts and parts[0] in RESERVED_TOP_MENUS:
            messagebox.showwarning(APP_TITLE, f"「{parts[0]}」是系统菜单，请换一个名称。", parent=dialog)
            location_entry.focus_set()
            return "break"
        if name in RESERVED_TOP_MENUS or name == DEFAULT_MENU_NAME:
            messagebox.showwarning(APP_TITLE, f"「{name}」是系统菜单，请换一个名称。", parent=dialog)
            location_entry.focus_set()
            return "break"
        if action is not None:
            saved = update_quick_action(
                action.id,
                location,
                command,
                keep_var.get(),
                shell_var.get(),
                terminal_keys.get(terminal_var.get(), TERMINAL_AUTO),
            )
            if saved is None:
                messagebox.showerror(APP_TITLE, "该快捷操作已不存在，可能已被删除。", parent=dialog)
                return "break"
        else:
            add_quick_action(
                location,
                command,
                keep_var.get(),
                shell_var.get(),
                terminal_keys.get(terminal_var.get(), TERMINAL_AUTO),
            )
        if on_saved:
            on_saved()
        _close()
        return "break"

    def _on_return(event: Any) -> str | None:
        if event.widget is command_text:
            return None
        return _save(event)

    def _select_all(event: Any) -> str:
        event.widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    button_row = 7 if IS_MACOS else 6
    ttk.Button(dialog, text="确定", width=8, command=_save).grid(
        row=button_row, column=1, sticky="e", padx=(0, 8), pady=(12, 20)
    )
    ttk.Button(dialog, text="取消", width=8, command=_close).grid(
        row=button_row, column=2, sticky="e", padx=(0, 20), pady=(12, 20)
    )

    dialog.columnconfigure(1, weight=1)
    dialog.rowconfigure(2, weight=1)
    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.bind("<Return>", _on_return)
    dialog.bind("<Control-Return>", _save)
    command_text.bind("<Control-Return>", _save)
    command_text.bind("<Control-a>", _select_all)
    command_text.bind("<Control-A>", _select_all)
    dialog.bind("<Escape>", lambda _event: _close())

    dialog.update_idletasks()
    width, height = (640, 480) if IS_MACOS else (560, 400)
    x = (dialog.winfo_screenwidth() - width) // 2
    y = (dialog.winfo_screenheight() - height) // 2
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    location_entry.focus_set()
    if action is not None:
        command_text.focus_set()
    dialog.lift()
    dialog.focus_force()
    dialog.grab_set()
