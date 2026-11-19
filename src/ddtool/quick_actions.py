from __future__ import annotations

import json
import locale
import os
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ddtool.config import get_config_dir
from ddtool.notices import Reporter
from ddtool.platform import IS_MACOS

DEFAULT_MENU_NAME = "快捷操作"
LEGACY_SYSTEM_SHORTCUTS_MENU = "系统快捷"
SYSTEM_COMMANDS_MENU = "系统命令"
SYSTEM_SHORTCUTS_MENU = SYSTEM_COMMANDS_MENU  # 兼容旧导入名
SETTINGS_MENU = "工具设置"
RESERVED_TOP_MENUS = frozenset({"退出", SETTINGS_MENU})
BUILTIN_TOP_MENUS = (DEFAULT_MENU_NAME, "手机操作", SYSTEM_COMMANDS_MENU, SETTINGS_MENU)
FIXED_TRAY_MENUS = ("手机操作", SYSTEM_COMMANDS_MENU, DEFAULT_MENU_NAME, SETTINGS_MENU, "退出")
LOCKED_MENU_ROOTS = frozenset({SYSTEM_COMMANDS_MENU, "手机操作"})
BUILTIN_COMMAND_POSTPONE_LOCK = "ddtool:postpone-lock"
BUILTIN_COMMAND_KEEP_AWAKE = "ddtool:keep-awake"
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

    _add(SYSTEM_COMMANDS_MENU)
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
    QuickAction("preset-keep-awake", "防睡眠", BUILTIN_COMMAND_KEEP_AWAKE, False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-postpone-lock", "推迟锁屏", BUILTIN_COMMAND_POSTPONE_LOCK, False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-ipconfig", "查看 IP", "ipconfig", True, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-flushdns", "刷新 DNS", "ipconfig /flushdns", True, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-netstat", "查看端口占用", "netstat -ano", True, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-ncpa", "网络连接", "ncpa.cpl", False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-devmgmt", "设备管理器", "devmgmt.msc", False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-taskmgr", "任务管理器", "taskmgr", False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-env", "系统环境变量", "rundll32.exe sysdm.cpl,EditEnvironmentVariables", False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-explorer", "重启资源管理器", "taskkill /f /im explorer.exe & start explorer.exe", False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-hosts", "打开 hosts", r"notepad %SystemRoot%\System32\drivers\etc\hosts", False, SYSTEM_COMMANDS_MENU),
    QuickAction("preset-powershell", "打开 PowerShell", "start powershell", False, SYSTEM_COMMANDS_MENU),
)

MACOS_QUICK_ACTIONS = (
    QuickAction("preset-keep-awake", "防睡眠", BUILTIN_COMMAND_KEEP_AWAKE, False, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-postpone-lock", "推迟锁屏", BUILTIN_COMMAND_POSTPONE_LOCK, False, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-ifconfig", "查看 IP", "ifconfig", True, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-flushdns-macos", "刷新 DNS", "sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder", True, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-netstat-macos", "查看端口占用", "lsof -nP -iTCP -sTCP:LISTEN", True, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-network-settings-macos", "网络设置", "open 'x-apple.systempreferences:com.apple.Network-Settings.extension'", False, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-activity-monitor", "活动监视器", "open -a 'Activity Monitor'", False, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-hosts-macos", "打开 hosts", "open -a TextEdit /etc/hosts", False, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
    QuickAction("preset-terminal", "打开终端", "open -a Terminal", False, SYSTEM_COMMANDS_MENU, SHELL_ZSH),
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


def _migrate_system_menu_name(actions: list[QuickAction]) -> tuple[list[QuickAction], bool]:
    """Rename legacy「系统快捷」menu paths to「系统命令」."""
    changed = False
    updated: list[QuickAction] = []
    legacy = LEGACY_SYSTEM_SHORTCUTS_MENU
    target = SYSTEM_COMMANDS_MENU
    for action in actions:
        path = action.menu_path
        if path == legacy or path.startswith(f"{legacy}/"):
            new_path = target + path[len(legacy) :]
            action = QuickAction(
                id=action.id,
                name=action.name,
                command=action.command,
                keep_terminal=action.keep_terminal,
                menu_path=new_path,
                shell=action.shell,
                terminal=action.terminal,
            )
            changed = True
        updated.append(action)
    return updated, changed


def load_quick_actions() -> list[QuickAction]:
    actions, seeded_presets, migrated, newest_first = _read_store()
    actions, renamed = _migrate_system_menu_name(actions)
    actions, relocated = _relocate_presets(actions)
    actions, seeded_presets, changed = _merge_presets(actions, seeded_presets)
    if not newest_first:
        actions = _custom_newest_first(actions)
    if (
        renamed
        or relocated
        or changed
        or migrated
        or not newest_first
        or not get_quick_actions_path().exists()
    ):
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


def run_quick_action(action: QuickAction, reporter: Reporter | None = None) -> None:
    reporter = reporter or Reporter()
    if action.command.startswith("ddtool:"):
        reporter.error(f"无法执行内置快捷操作：\n{action.command}")
        return
    shell = _normalize_shell(action.shell)
    command = _normalize_command(action.command)
    if IS_MACOS:
        _run_macos_quick_action(command, action.keep_terminal, action.terminal, reporter)
        return
    use_script = "\n" in command or shell == SHELL_POWERSHELL
    if use_script:
        try:
            command = _write_command_script(command, shell)
        except OSError as exc:
            reporter.error(f"写入临时脚本失败：\n{exc}")
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
        reporter.error(f"执行快捷操作失败：\n{exc}")


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
    terminal: str,
    reporter: Reporter,
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
        reporter.error(f"执行快捷操作失败：\n{exc}")
