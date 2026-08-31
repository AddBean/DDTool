from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from ddtool.config import APP_TITLE, AppConfig, get_config_path
from ddtool.dns_proxy import DnsProxy
from ddtool.platform import IS_WINDOWS, subprocess_creation_flags
from ddtool.resources import find_executable


GNIRETET_DEFAULT_DIR = Path.home() / "gnirehtet" / "gnirehtet-rust-win64"


@dataclass(slots=True)
class NetworkController:
    config: AppConfig
    process: subprocess.Popen[bytes] | None = None
    dns_proxy: DnsProxy | None = None

    def start(self) -> None:
        gnirehtet = _resolve_gnirehtet_path(self.config)
        if not gnirehtet:
            messagebox.showerror(
                APP_TITLE,
                "没有找到 gnirehtet。\n\n"
                f"请编辑配置文件：\n{get_config_path()}",
            )
            return

        adb = _find_adb()
        device_error = _check_adb_device(adb)
        if device_error:
            messagebox.showerror(APP_TITLE, device_error)
            return

        already_running = (self.process and self.process.poll() is None) or _gnirehtet_running()
        if already_running:
            self.stop()
            time.sleep(0.8)

        dns = _start_dns_proxy(self)
        command = [str(gnirehtet), "run", "-d", dns]
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(gnirehtet.parent),
                creationflags=_creation_flags(),
            )
        except FileNotFoundError:
            self._stop_dns_proxy()
            messagebox.showerror(
                APP_TITLE,
                "没有找到 gnirehtet。\n\n"
                f"请编辑配置文件：\n{get_config_path()}",
            )
            return
        except OSError as exc:
            self._stop_dns_proxy()
            messagebox.showerror(APP_TITLE, f"启动 gnirehtet 失败：\n{exc}")
            return

        try:
            self.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            messagebox.showinfo(
                APP_TITLE,
                "已启动网络共享。\n\n"
                "请在手机上允许 VPN 连接，稍等几秒即可上网。",
            )
            return

        self.process = None
        self._stop_dns_proxy()
        messagebox.showerror(
            APP_TITLE,
            "网络共享启动失败，请确认：\n"
            "1. 手机已连接并开启 USB 调试\n"
            "2. 手机上已允许该电脑调试\n"
            "3. 端口 31416 未被占用",
        )

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        gnirehtet = _resolve_gnirehtet_path(self.config)
        if gnirehtet:
            try:
                subprocess.run(
                    [str(gnirehtet), "stop"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=str(gnirehtet.parent),
                    creationflags=_creation_flags(),
                    timeout=10,
                    check=False,
                )
            except OSError:
                pass

        self._stop_dns_proxy()

    def _stop_dns_proxy(self) -> None:
        if self.dns_proxy is not None:
            self.dns_proxy.stop()
            self.dns_proxy = None


FALLBACK_DNS = "223.5.5.5,223.6.6.6"
HOST_DNS = "10.0.2.2"


def _start_dns_proxy(controller: NetworkController) -> str:
    proxy = DnsProxy()
    try:
        proxy.start()
    except OSError:
        return FALLBACK_DNS
    if not _query_local_dns():
        proxy.stop()
        return FALLBACK_DNS
    controller.dns_proxy = proxy
    return HOST_DNS


def _query_local_dns() -> bool:
    import socket
    import struct

    name = "www.baidu.com"
    question = b"".join(len(p).to_bytes(1, "big") + p.encode() for p in name.split("."))
    packet = struct.pack("!HHHHHH", 0x2345, 0x0100, 1, 0, 0, 0) + question + b"\x00" + struct.pack("!HH", 1, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    try:
        sock.sendto(packet, ("127.0.0.1", 53))
        data, _ = sock.recvfrom(4096)
        return len(data) >= 12
    except OSError:
        return False
    finally:
        sock.close()


def _creation_flags() -> int:
    return subprocess_creation_flags()


def _resolve_gnirehtet_path(config: AppConfig) -> Path | None:
    configured = (config.gnirehtet_path or "").strip()
    if configured and configured.lower() != "gnirehtet":
        path = Path(configured)
        return path if path.exists() else None

    default = GNIRETET_DEFAULT_DIR / "gnirehtet.exe"
    if IS_WINDOWS and default.exists():
        return default
    return find_executable("gnirehtet")


def _find_adb() -> Path | None:
    return find_executable("adb")


def _check_adb_device(adb: Path | None) -> str | None:
    if not adb:
        return (
            "没有找到 adb。\n\n"
            "请安装 Android SDK Platform Tools，"
            "或确保 adb 在系统 PATH 中。"
        )

    try:
        result = subprocess.run(
            [str(adb), "devices"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_creation_flags(),
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return "没有找到 adb。"
    except subprocess.TimeoutExpired:
        return "ADB 检测设备超时，请重新插拔手机后再试。"
    except OSError as exc:
        return f"ADB 检测设备失败：\n{exc}"

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        return f"ADB 检测设备失败：\n{error}" if error else "ADB 检测设备失败。"

    output = result.stdout.decode("utf-8", errors="replace")
    devices = [
        line for line in output.splitlines()
        if line.strip() and not line.lower().startswith("list of devices")
    ]
    ready = [line for line in devices if line.split()[-1:] == ["device"]]
    if ready:
        return None
    if devices:
        return "手机已连接但未授权，请在手机上允许 USB 调试授权后再试。"
    return "没有检测到手机，请连接手机并打开 USB 调试后再试。"


def _gnirehtet_running() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq gnirehtet.exe", "/NH"],
            capture_output=True,
            creationflags=_creation_flags(),
            timeout=5,
            check=False,
        )
        return "gnirehtet.exe" in result.stdout.decode("utf-8", errors="replace").lower()
    except OSError:
        return False
