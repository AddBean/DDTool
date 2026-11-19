from __future__ import annotations

from pathlib import Path
from subprocess import list2cmdline

from ddtool.shell_shortcuts import ShortcutConfig


OWNER = "com.ddtool.app"
VERB = "DDTool.Shortcuts"
LOCATIONS = {
    "directory": r"Software\Classes\Directory\shell",
    "background": r"Software\Classes\Directory\Background\shell",
    "desktop": r"Software\Classes\DesktopBackground\Shell",
}


def launch_command(executable: Path, scope: str) -> str:
    command = list2cmdline([str(executable), "--shell-shortcut", scope])
    return command + {"directory": r' "%1\."', "background": r' "%V\."', "desktop": ""}[scope]


def apply_registration(config: ShortcutConfig, executable: Path) -> None:
    import winreg

    root = winreg.HKEY_CURRENT_USER
    paths = {scope: rf"{parent}\{VERB}" for scope, parent in LOCATIONS.items()}
    existing = set()
    for key_path in paths.values():
        try:
            key = winreg.OpenKey(root, key_path)
        except FileNotFoundError:
            continue
        with key:
            try:
                owner = winreg.QueryValueEx(key, "DDToolOwner")[0]
            except FileNotFoundError:
                owner = None
            if owner != OWNER:
                if config.enabled:
                    raise ValueError("同名系统菜单已存在，未覆盖其他注册项。")
                continue
        existing.add(key_path)

    for scope, key_path in paths.items():
        command_path = rf"{key_path}\command"
        if config.enabled:
            with winreg.CreateKey(root, key_path) as key:
                winreg.SetValueEx(key, "DDToolOwner", 0, winreg.REG_SZ, OWNER)
                winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, config.label)
                if scope == "directory":
                    winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Single")
            with winreg.CreateKey(root, command_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, launch_command(executable, scope))
        elif key_path in existing:
            try:
                winreg.DeleteKey(root, command_path)
            except FileNotFoundError:
                pass
            winreg.DeleteKey(root, key_path)
