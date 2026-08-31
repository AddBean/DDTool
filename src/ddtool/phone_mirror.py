from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from ddtool.config import APP_TITLE, AppConfig, get_config_path
from ddtool.platform import subprocess_creation_flags
from ddtool.resources import find_executable


@dataclass(slots=True)
class MirrorController:
    config: AppConfig
    process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo(APP_TITLE, "手机镜像已经在运行。")
            return

        scrcpy = resolve_scrcpy_path(self.config)
        if not scrcpy:
            messagebox.showerror(
                APP_TITLE,
                "没有找到 scrcpy。\n\n"
                "程序会优先使用内置 scrcpy；如果你要使用自定义版本，"
                f"请编辑配置文件：\n{get_config_path()}",
            )
            return

        check = check_scrcpy(scrcpy)
        if check:
            messagebox.showerror(APP_TITLE, check)
            return

        device_error = check_connected_device(scrcpy)
        if device_error:
            messagebox.showerror(APP_TITLE, device_error)
            return

        command = [str(scrcpy), *(self.config.scrcpy_args or [])]

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=str(scrcpy.parent),
                creationflags=_creation_flags(),
            )
        except FileNotFoundError:
            messagebox.showerror(
                APP_TITLE,
                "没有找到 scrcpy。\n\n"
                f"请安装 scrcpy，或编辑配置文件：\n{get_config_path()}",
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"启动 scrcpy 失败：\n{exc}")

        if self.process:
            try:
                self.process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                return

            stderr = b""
            if self.process.stderr:
                stderr = self.process.stderr.read()
            message = stderr.decode("utf-8", errors="replace").strip()
            if message:
                messagebox.showerror(APP_TITLE, f"手机镜像启动失败：\n{message}")

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()


def _creation_flags() -> int:
    return subprocess_creation_flags()


def resolve_scrcpy_path(config: AppConfig) -> Path | None:
    configured = (config.scrcpy_path or "").strip()
    if configured and configured.lower() != "scrcpy":
        path = Path(configured)
        return path if path.exists() else None

    return find_executable("scrcpy")


def check_scrcpy(scrcpy: Path) -> str | None:
    try:
        result = subprocess.run(
            [str(scrcpy), "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(scrcpy.parent) if scrcpy.parent != Path(".") else None,
            creationflags=_creation_flags(),
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return "没有找到 scrcpy。"
    except subprocess.TimeoutExpired:
        return "scrcpy 响应超时，请检查程序文件是否完整。"
    except OSError as exc:
        return f"scrcpy 无法运行：\n{exc}"

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        if not error:
            error = "未知错误"
        return f"scrcpy 自检失败：\n{error}"
    return None


def check_connected_device(scrcpy: Path) -> str | None:
    adb = find_executable("adb")
    if not adb:
        return "没有找到 adb，请安装 Android Platform Tools。"
    command = [str(adb), "devices"]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(scrcpy.parent) if scrcpy.parent != Path(".") else None,
            creationflags=_creation_flags(),
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return "ADB 检测设备超时，请重新插拔手机后再试。"
    except OSError as exc:
        return f"ADB 检测设备失败：\n{exc}"

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        if not error:
            error = "未知错误"
        return f"ADB 检测设备失败：\n{error}"

    output = result.stdout.decode("utf-8", errors="replace")
    devices = [
        line
        for line in output.splitlines()
        if line.strip() and not line.lower().startswith("list of devices")
    ]
    ready_devices = [line for line in devices if line.split()[-1:] == ["device"]]
    if ready_devices:
        return None

    if devices:
        return "手机已连接但未授权，请在手机上允许 USB 调试授权后再试。"
    return "没有检测到手机，请连接手机并打开 USB 调试后再试。"


def run_mirror_smoke_test(config: AppConfig, seconds: int = 3) -> int:
    scrcpy = resolve_scrcpy_path(config)
    if not scrcpy:
        print("scrcpy was not found.", file=sys.stderr)
        return 1

    check_error = check_scrcpy(scrcpy) or check_connected_device(scrcpy)
    if check_error:
        print(check_error, file=sys.stderr)
        return 1

    result = subprocess.run(
        [str(scrcpy), f"--time-limit={seconds}", "--no-audio"],
        cwd=str(scrcpy.parent),
        creationflags=_creation_flags(),
        timeout=seconds + 15,
        check=False,
    )
    return result.returncode
