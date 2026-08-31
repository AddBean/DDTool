from __future__ import annotations

import json
import plistlib
import subprocess
import sys
from pathlib import Path

from ddtool.config import APP_TITLE, get_config_dir
from ddtool.platform import IS_MACOS, IS_WINDOWS

if IS_WINDOWS:
    import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = APP_TITLE
_LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.ddtool.app.plist"


def launch_arguments() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]

    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe" if IS_WINDOWS else "pythonw")
    exe = pythonw if pythonw.exists() else python
    src = Path(__file__).resolve().parents[1]
    entry = get_config_dir() / "autostart_entry.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "import sys\n"
        f"sys.path.insert(0, {json.dumps(str(src))})\n"
        "from ddtool.tray_app import main\n"
        "main()\n",
        encoding="utf-8",
    )
    return [str(exe), str(entry)]


def launch_command() -> str:
    return subprocess.list2cmdline(launch_arguments())


def is_enabled() -> bool:
    if IS_MACOS:
        return _LAUNCH_AGENT.exists()
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _regtype = winreg.QueryValueEx(key, _VALUE_NAME)
    except OSError:
        return False
    return bool(str(value).strip())


def set_enabled(enabled: bool) -> None:
    if not (IS_WINDOWS or IS_MACOS):
        raise OSError("当前系统暂不支持开机启动")
    if enabled:
        _enable()
    else:
        _disable()


def _enable() -> None:
    if IS_MACOS:
        _LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": "com.ddtool.app",
            "ProgramArguments": launch_arguments(),
            "RunAtLoad": True,
            "ProcessType": "Interactive",
        }
        _LAUNCH_AGENT.write_bytes(plistlib.dumps(payload, sort_keys=False))
        return
    command = launch_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)


def _disable() -> None:
    if IS_MACOS:
        try:
            _LAUNCH_AGENT.unlink()
        except FileNotFoundError:
            pass
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        return
    except OSError as exc:
        if getattr(exc, "winerror", None) in {2, 3}:
            return
        raise
