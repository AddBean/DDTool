from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


TARGETS = {
    "actions": ("快捷操作", "打开已有操作列表，不自动执行脚本"),
    "devices": ("手机工具", "打开镜像、转发与网络共享工具"),
    "power": ("电源与锁屏", "打开防睡眠与推迟锁屏设置"),
    "activity": ("运行动态", "查看操作记录与结果"),
    "settings": ("设置", "打开工作台设置"),
    "folder": ("打开当前文件夹", "在系统文件管理器中打开本次目录"),
}
DEFAULT_LABEL = "豆荚工具快捷入口"
SCOPES = {"desktop", "background", "directory", "finder"}
MAX_MESSAGE = 128 * 1024


@dataclass(frozen=True)
class ShortcutConfig:
    enabled: bool = False
    label: str = DEFAULT_LABEL
    mode: str = "chooser"
    targets: tuple[str, ...] = ("actions", "devices", "power", "folder")

    @classmethod
    def parse(cls, data: dict) -> ShortcutConfig:
        enabled, label, mode, targets = (data.get(key) for key in ("enabled", "label", "mode", "targets"))
        if type(enabled) is not bool or not isinstance(label, str) or not isinstance(mode, str):
            raise ValueError("右键入口设置格式无效。")
        label = label.strip()
        if not 1 <= len(label) <= 36 or not label.isprintable() or "&" in label:
            raise ValueError("菜单名称须为 1–36 个可打印字符，且不能含 &。")
        if mode != "chooser" and mode not in TARGETS:
            raise ValueError("请选择有效的直达功能。")
        if (not isinstance(targets, list) or not all(isinstance(key, str) and key in TARGETS for key in targets)
                or len(targets) != len(set(targets))):
            raise ValueError("快捷列表包含无效或重复的功能。")
        if enabled and mode == "chooser" and not targets:
            raise ValueError("请为快捷列表至少选择一个功能。")
        return cls(enabled, label, mode, tuple(targets))

    def values(self) -> dict:
        return {**asdict(self), "targets": list(self.targets)}

    @classmethod
    def load(cls, path: Path) -> ShortcutConfig:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.parse(data) if isinstance(data, dict) else cls()
        except (OSError, ValueError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as stream:
                temporary = Path(stream.name)
                json.dump(self.values(), stream, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Activation:
    scope: str = ""
    directory: str = ""

    @classmethod
    def parse(cls, arguments: list[str]) -> Activation:
        if not arguments or arguments[0] != "--shell-shortcut":
            return cls()
        if len(arguments) == 2 and arguments[1] == "desktop":
            return cls("desktop")
        if len(arguments) != 3 or arguments[1] not in SCOPES or not arguments[2]:
            raise ValueError("Invalid context-menu activation")
        return cls(arguments[1], arguments[2])

    def encode(self) -> bytes:
        return json.dumps([self.scope, self.directory], ensure_ascii=True).encode("ascii") + b"\n"

    @classmethod
    def decode(cls, message: bytes) -> Activation:
        if len(message) > MAX_MESSAGE or not message.endswith(b"\n"):
            raise ValueError("Invalid activation frame")
        data = json.loads(message)
        if data == ["", ""]:
            return cls()
        if not isinstance(data, list) or len(data) != 2 or not all(isinstance(item, str) for item in data):
            raise ValueError("Invalid activation message")
        return cls.parse(["--shell-shortcut", data[0], *([data[1]] if data[1] else [])])

    def existing_directory(self) -> Path | None:
        if not self.directory or "\0" in self.directory:
            return None
        if sys.platform == "win32" and self.directory.startswith(("\\\\.\\", "\\\\?\\")):
            return None
        path = Path(self.directory)
        if path.is_absolute() and path.is_dir():
            return path
        return None


def apply_integration(config: ShortcutConfig) -> None:
    if sys.platform == "win32":
        from ddtool.windows_shortcuts import apply_registration
    elif sys.platform == "darwin":
        from ddtool.macos_shortcuts import apply_registration
    else:
        if config.enabled:
            raise ValueError("系统右键入口仅支持 Windows 与 macOS。")
        return
    if not getattr(sys, "frozen", False):
        if config.enabled:
            raise ValueError("请从安装或解压后的应用开启系统入口，源码模式不注册。")
        return
    apply_registration(config, Path(sys.executable))
