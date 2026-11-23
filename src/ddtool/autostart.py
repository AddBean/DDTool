from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from ddtool.config import APP_TITLE, get_config_dir
from ddtool.platform import IS_MACOS, IS_WINDOWS

if IS_WINDOWS:
    import winreg
else:
    winreg = None  # 非 Windows 供测试注入

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APPROVAL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
_VALUE_NAME = APP_TITLE
_LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.ddtool.app.plist"
_LAUNCH_LABEL = "com.ddtool.app"
# Windows 8+：StartupApproved 首字节 02/06=允许，03/07=任务管理器/设置里禁用
_STARTUP_ENABLED = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
_STARTUP_DISABLED_MARKERS = {0x03, 0x07}


def _program_paths(arguments: list[object]) -> list[Path]:
    return [Path(str(arg)) for arg in arguments if str(arg) and not str(arg).startswith("-")]


def _windows_run_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _regtype = winreg.QueryValueEx(key, _VALUE_NAME)
    except OSError:
        return None
    command = str(value).strip()
    return command or None


def _windows_startup_disabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APPROVAL_KEY) as key:
            approval = winreg.QueryValueEx(key, _VALUE_NAME)[0]
    except OSError:
        return False
    return isinstance(approval, bytes) and len(approval) >= 1 and approval[0] in _STARTUP_DISABLED_MARKERS


def _windows_set_startup_approved(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _APPROVAL_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_BINARY, _STARTUP_ENABLED)
            return
        try:
            winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) in {2, 3}:
                return
            raise


def _windows_command_executable(command: str) -> str:
    if command.startswith('"'):
        return command.split('"', 2)[1]
    return command.partition(" ")[0]


def launch_arguments() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--background"]

    python = Path(sys.executable).absolute()
    pythonw = python.with_name("pythonw.exe" if IS_WINDOWS else "pythonw")
    exe = pythonw if pythonw.exists() else python
    src = Path(__file__).resolve().parents[1]
    entry = get_config_dir() / "autostart_entry.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "import sys\n"
        f"sys.path.insert(0, {json.dumps(str(src))})\n"
        "from ddtool.tray_app import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    return [str(exe), str(entry), "--background"]


def launch_command() -> str:
    return subprocess.list2cmdline(launch_arguments())


def is_enabled() -> bool:
    if IS_MACOS:
        return _LAUNCH_AGENT.exists()
    if not IS_WINDOWS:
        return False
    if _windows_run_command() is None:
        return False
    return not _windows_startup_disabled()


def status() -> str:
    if IS_WINDOWS:
        command = _windows_run_command()
        if command is None:
            return "未启用"
        try:
            executable = _windows_command_executable(command)
            if not executable or not Path(executable).is_file():
                return "启动路径已失效，请关闭后重新启用"
            if _windows_startup_disabled():
                return "系统已禁用 · 请在本页重新打开，或到系统设置的启动应用中启用"
            return "已登记 · 登录后驻留托盘"
        except (OSError, ValueError, TypeError, AttributeError, IndexError):
            return "已登记 · 无法确认系统状态"
    if not is_enabled():
        return "未启用"
    try:
        settings = plistlib.loads(_LAUNCH_AGENT.read_bytes())
        paths = _program_paths(settings.get("ProgramArguments", []))
        if settings.get("Label") != _LAUNCH_LABEL or not paths or not all(path.is_file() for path in paths):
            return "启动路径已失效，请关闭后重新启用"
        if _macos_agent_loaded():
            return "已登记 · 登录后驻留菜单栏（不显示程序坞图标）"
        return "已登记 · 下次登录生效；若未出现请到系统设置确认后台项目"
    except (OSError, ValueError, TypeError, AttributeError, IndexError, plistlib.InvalidFileException):
        return "已登记 · 无法确认系统状态"


def _macos_agent_domain() -> str:
    return f"gui/{os.getuid()}"


def _macos_agent_loaded() -> bool:
    result = subprocess.run(
        ["launchctl", "print", f"{_macos_agent_domain()}/{_LAUNCH_LABEL}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _macos_reload_agent() -> None:
    domain = _macos_agent_domain()
    subprocess.run(
        ["launchctl", "bootout", domain, str(_LAUNCH_AGENT)],
        capture_output=True,
        text=True,
        check=False,
    )
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(_LAUNCH_AGENT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or result.stdout.strip() or "无法加载登录启动项")


def remove_install_registration(executable: Path) -> None:
    if not IS_WINDOWS:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            command = winreg.QueryValueEx(key, _VALUE_NAME)[0]
            if command == subprocess.list2cmdline([str(executable), "--background"]):
                winreg.DeleteValue(key, _VALUE_NAME)
                _windows_set_startup_approved(False)
    except FileNotFoundError:
        pass


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
            "Label": _LAUNCH_LABEL,
            "ProgramArguments": launch_arguments(),
            "RunAtLoad": True,
            "ProcessType": "Interactive",
        }
        _LAUNCH_AGENT.write_bytes(plistlib.dumps(payload, sort_keys=False))
        # 已由本进程占用时不强制 bootout，避免设置开关把自己杀掉；仅在未加载时 bootstrap。
        if not _macos_agent_loaded():
            _macos_reload_agent()
        return
    command = launch_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)
    # 任务管理器/系统设置禁用后会留下 StartupApproved=03/07；只写 Run 不够，必须一并放行。
    _windows_set_startup_approved(True)


def _disable() -> None:
    if IS_MACOS:
        # 只移除 plist，避免 bootout 把正在改设置的本进程杀掉；下次登录不再拉起。
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
        pass
    except OSError as exc:
        if getattr(exc, "winerror", None) not in {2, 3}:
            raise
    _windows_set_startup_approved(False)
