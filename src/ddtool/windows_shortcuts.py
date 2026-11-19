from __future__ import annotations

from pathlib import Path
from subprocess import list2cmdline

from ddtool.shell_shortcuts import ShortcutConfig, entry_token


OWNER = "com.ddtool.app"
VERB = "DDTool.Shortcuts"
LOCATIONS = {
    "directory": r"Software\Classes\Directory\shell",
    "background": r"Software\Classes\Directory\Background\shell",
    "desktop": r"Software\Classes\DesktopBackground\Shell",
}


def launch_command(executable: Path, scope: str, entry: str = "") -> str:
    command = list2cmdline([str(executable), "--shell-shortcut", scope, *([f"--entry={entry}"] if entry else [])])
    return command + {"directory": r' "%1\."', "background": r' "%V\."', "desktop": ""}[scope]


def apply_registration(config: ShortcutConfig, executable: Path, *, only_matching: bool = False,
                       labels: dict[str, str] | None = None) -> None:
    import winreg

    root = winreg.HKEY_CURRENT_USER
    desired = {}
    existing = {}
    labels = labels or {}
    for scope, parent in LOCATIONS.items():
        if config.enabled:
            if config.mode == "pinned":
                for target in config.targets:
                    if target in labels:
                        token = entry_token(target)
                        label = "".join(char for char in labels[target] if char.isprintable()).replace("&", "&&")[:80]
                        desired[rf"{parent}\{VERB}.{token}"] = (scope, label or config.label, token)
            else:
                desired[rf"{parent}\{VERB}"] = (scope, config.label, "")
        try:
            with winreg.OpenKey(root, parent) as parent_key:
                names = [winreg.EnumKey(parent_key, index) for index in range(winreg.QueryInfoKey(parent_key)[0])]
        except FileNotFoundError:
            continue
        for name in names:
            prefix, _, token = name.rpartition(".")
            if name != VERB and not (prefix == VERB and len(token) == 24 and all(char in "0123456789abcdef" for char in token)):
                continue
            key_path = rf"{parent}\{name}"
            with winreg.OpenKey(root, key_path) as key:
                try:
                    owner = winreg.QueryValueEx(key, "DDToolOwner")[0]
                except FileNotFoundError:
                    owner = None
                if owner != OWNER:
                    if key_path in desired:
                        raise ValueError("同名系统菜单已存在，未覆盖其他注册项。")
                    continue
            existing[key_path] = (scope, "" if name == VERB else token)

    for key_path, (scope, label, token) in desired.items():
        with winreg.CreateKey(root, key_path) as key:
            winreg.SetValueEx(key, "DDToolOwner", 0, winreg.REG_SZ, OWNER)
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, label)
            if scope == "directory":
                winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Single")
        with winreg.CreateKey(root, rf"{key_path}\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, launch_command(executable, scope, token))

    for key_path in existing.keys() - desired.keys():
        scope, token = existing[key_path]
        command_path = rf"{key_path}\command"
        if only_matching:
            try:
                with winreg.OpenKey(root, command_path) as key:
                    if winreg.QueryValueEx(key, "")[0] != launch_command(executable, scope, token):
                        continue
            except FileNotFoundError:
                continue
        try:
            winreg.DeleteKey(root, command_path)
        except FileNotFoundError:
            pass
        winreg.DeleteKey(root, key_path)
