from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from ddtool.config import APP_TITLE, AppConfig
from ddtool.platform import subprocess_creation_flags
from ddtool.resources import find_executable


@dataclass(frozen=True, slots=True)
class JsonMcpTarget:
    label: str
    path: Path
    require_type: str | None = None


JSON_MCP_TARGETS = [
    JsonMcpTarget("Cursor", Path.home() / ".cursor" / "mcp.json"),
    JsonMcpTarget("Claude Code", Path.home() / ".claude.json", require_type="http"),
]

CODEX_MCP_CONFIG = Path.home() / ".codex" / "config.toml"


@dataclass(slots=True)
class ForwardController:
    config: AppConfig
    _active: bool = False

    def install(self) -> None:
        """映射端口 + 安装 MCP 配置到 Cursor / ChatGPT / Claude Code"""
        adb = _find_adb()
        if not adb:
            messagebox.showerror(APP_TITLE, "没有找到 adb，请确保 adb 在系统 PATH 中。")
            return

        device_error = _check_adb_device(adb)
        if device_error:
            messagebox.showerror(APP_TITLE, device_error)
            return

        local = self.config.forward_local_port or 19999
        phone = self.config.forward_phone_port or 9999
        name = self.config.mcp_server_name or "phone-mcp"
        url = f"http://127.0.0.1:{local}"

        forward_active = _is_forward_active(adb, local, phone)
        pending_json = [
            target for target in JSON_MCP_TARGETS
            if not _is_json_mcp_installed(target, name, url)
        ]
        codex_installed = _is_codex_mcp_installed(CODEX_MCP_CONFIG, name, url)

        if forward_active and not pending_json and codex_installed:
            messagebox.showinfo(
                APP_TITLE,
                "MCP 已安装且端口映射正常，无需重复安装。",
            )
            self._active = True
            return

        if not forward_active:
            if not _setup_forward(adb, local, phone):
                return
            self._active = True
        else:
            self._active = True

        if not pending_json and codex_installed:
            messagebox.showinfo(
                APP_TITLE,
                f"端口映射已启用：手机 {phone} → 本机 {local}\n\n"
                "MCP 配置已存在，无需重复安装。",
            )
            return

        installed = []
        skipped = []
        failed = []

        cursor_entry = {"url": url}
        claude_entry = {"type": "http", "url": url}

        for target in JSON_MCP_TARGETS:
            if target not in pending_json:
                skipped.append(target.label)
                continue
            entry = claude_entry if target.require_type else cursor_entry
            try:
                _upsert_json_mcp_server(target.path, name, entry)
                installed.append(f"{target.label}: {target.path}")
            except OSError as exc:
                failed.append(f"{target.label}: {target.path}\n  {exc}")

        if not codex_installed:
            try:
                _upsert_codex_mcp_server(CODEX_MCP_CONFIG, name, url)
                installed.append(f"ChatGPT/Codex: {CODEX_MCP_CONFIG}")
            except OSError as exc:
                failed.append(f"ChatGPT/Codex: {CODEX_MCP_CONFIG}\n  {exc}")
        else:
            skipped.append("ChatGPT/Codex")

        lines = [
            f"端口映射已启用：手机 {phone} → 本机 {local}",
            f"MCP 地址：{url}（Streamable HTTP）",
            "",
        ]
        if installed:
            lines.append("MCP 配置已安装到：")
            for item in installed:
                lines.append(f"  {item}")
        if skipped:
            lines.append("")
            lines.append("以下目标已存在，已跳过：")
            for item in skipped:
                lines.append(f"  {item}")
        if failed:
            lines.append("")
            lines.append("以下位置写入失败：")
            for item in failed:
                lines.append(f"  {item}")

        messagebox.showinfo(APP_TITLE, "\n".join(lines))

    def stop(self) -> None:
        if not self._active:
            return

        adb = _find_adb()
        if not adb:
            self._active = False
            return

        local = self.config.forward_local_port or 19999

        try:
            subprocess.run(
                [str(adb), "forward", "--remove", f"tcp:{local}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creation_flags(),
                timeout=10,
                check=False,
            )
        except OSError:
            pass

        self._active = False


def _setup_forward(adb: Path, local: int, phone: int) -> bool:
    try:
        result = subprocess.run(
            [str(adb), "forward", f"tcp:{local}", f"tcp:{phone}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_creation_flags(),
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        messagebox.showerror(APP_TITLE, "没有找到 adb。")
        return False
    except subprocess.TimeoutExpired:
        messagebox.showerror(APP_TITLE, "ADB 端口映射超时，请重试。")
        return False
    except OSError as exc:
        messagebox.showerror(APP_TITLE, f"ADB 端口映射失败：\n{exc}")
        return False

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        messagebox.showerror(
            APP_TITLE,
            f"端口映射失败：\n{error}" if error else "端口映射失败。",
        )
        return False

    return True


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _is_forward_active(adb: Path, local: int, phone: int) -> bool:
    try:
        result = subprocess.run(
            [str(adb), "forward", "--list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_creation_flags(),
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False

    if result.returncode != 0:
        return False

    output = result.stdout.decode("utf-8", errors="replace")
    expected = f"tcp:{local} tcp:{phone}"
    return any(expected in line for line in output.splitlines())


def _read_json_mcp_servers(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    servers = data.get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def _is_json_mcp_installed(target: JsonMcpTarget, name: str, url: str) -> bool:
    servers = _read_json_mcp_servers(target.path)
    entry = servers.get(name)
    if not isinstance(entry, dict):
        return False

    if _normalize_url(str(entry.get("url", ""))) != _normalize_url(url):
        return False

    if target.require_type:
        entry_type = str(entry.get("type", "")).lower()
        if entry_type not in {target.require_type, "streamable-http"}:
            return False

    return True


def _is_codex_mcp_installed(path: Path, name: str, url: str) -> bool:
    if not path.exists():
        return False

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False

    servers = data.get("mcp_servers")
    if not isinstance(servers, dict):
        return False

    expected_url = _normalize_url(url)
    named = servers.get(name)
    if isinstance(named, dict):
        server_url = named.get("url")
        if isinstance(server_url, str) and _normalize_url(server_url) == expected_url:
            return True

    for server in servers.values():
        if not isinstance(server, dict):
            continue
        server_url = server.get("url")
        if isinstance(server_url, str) and _normalize_url(server_url) == expected_url:
            return True

    return False


def _upsert_json_mcp_server(path: Path, name: str, entry: dict) -> None:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}

    if not isinstance(data, dict):
        data = {}

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers

    servers[name] = entry

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert_codex_mcp_server(path: Path, name: str, url: str) -> None:
    block = (
        f"[mcp_servers.{name}]\n"
        f"enabled = true\n"
        f'url = "{url}"\n'
    )

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    section_pattern = re.compile(
        rf'^\[mcp_servers\.{re.escape(name)}\][^\[]*',
        re.MULTILINE,
    )
    if section_pattern.search(text):
        updated = section_pattern.sub(block.rstrip() + "\n", text, count=1)
    else:
        updated = text.rstrip() + "\n\n" + block

    path.write_text(updated, encoding="utf-8")


def _creation_flags() -> int:
    return subprocess_creation_flags()


def _find_adb() -> Path | None:
    return find_executable("adb")


def _check_adb_device(adb: Path) -> str | None:
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
