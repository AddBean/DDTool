from __future__ import annotations

import json
import hashlib
import os
import re
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


def valid_target(key: str) -> bool:
    return key in TARGETS or (key.startswith("action:") and 7 < len(key) <= 256 and key.isprintable())


def entry_token(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class ShortcutConfig:
    enabled: bool = False
    label: str = DEFAULT_LABEL
    mode: str = "chooser"
    targets: tuple[str, ...] = ("actions", "devices", "power", "folder")
    direct_run: bool = False

    @classmethod
    def parse(cls, data: dict) -> ShortcutConfig:
        enabled, label, mode, targets = (data.get(key) for key in ("enabled", "label", "mode", "targets"))
        direct_run = data.get("direct_run", False)
        if type(enabled) is not bool or type(direct_run) is not bool or not isinstance(label, str) or not isinstance(mode, str):
            raise ValueError("右键入口设置格式无效。")
        label = label.strip()
        if not 1 <= len(label) <= 36 or not label.isprintable() or "&" in label:
            raise ValueError("菜单名称须为 1–36 个可打印字符，且不能含 &。")
        if mode not in {"chooser", "pinned"} and not valid_target(mode):
            raise ValueError("请选择有效的直达功能。")
        if (not isinstance(targets, list) or not all(isinstance(key, str) and valid_target(key) for key in targets)
                or len(targets) != len(set(targets))):
            raise ValueError("快捷列表包含无效或重复的功能。")
        if enabled and mode in {"chooser", "pinned"} and not targets:
            raise ValueError("请为快捷列表至少选择一个功能。")
        return cls(enabled, label, mode, tuple(targets), direct_run and mode == "pinned")

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
    entry: str = ""

    @classmethod
    def parse(cls, arguments: list[str]) -> Activation:
        if not arguments or arguments[0] != "--shell-shortcut":
            return cls()
        if len(arguments) < 2 or arguments[1] not in SCOPES:
            raise ValueError("Invalid context-menu activation")
        scope, *parameters = arguments[1:]
        entry = ""
        if parameters and re.fullmatch(r"--entry=[a-f0-9]{24}", parameters[0]):
            entry = parameters.pop(0)[8:]
        if not parameters and scope == "desktop":
            return cls(scope, "", entry)
        if len(parameters) != 1 or not parameters[0]:
            raise ValueError("Invalid context-menu activation")
        return cls(scope, parameters[0], entry)

    def encode(self) -> bytes:
        values = [self.scope, self.directory] + ([self.entry] if self.entry else [])
        return json.dumps(values, ensure_ascii=True).encode("ascii") + b"\n"

    @classmethod
    def decode(cls, message: bytes) -> Activation:
        if len(message) > MAX_MESSAGE or not message.endswith(b"\n"):
            raise ValueError("Invalid activation frame")
        data = json.loads(message)
        if data == ["", ""]:
            return cls()
        if not isinstance(data, list) or len(data) not in {2, 3} or not all(isinstance(item, str) for item in data):
            raise ValueError("Invalid activation message")
        if len(data) == 3 and re.fullmatch(r"[a-f0-9]{24}", data[2]) is None:
            raise ValueError("Invalid entry token")
        return cls.parse(["--shell-shortcut", data[0], *([f"--entry={data[2]}"] if len(data) == 3 else []),
                          *([data[1]] if data[1] else [])])

    def existing_directory(self) -> Path | None:
        if not self.directory or "\0" in self.directory:
            return None
        if sys.platform == "win32" and self.directory.startswith(("\\\\.\\", "\\\\?\\")):
            return None
        path = Path(self.directory)
        if path.is_absolute() and path.is_dir():
            return path
        return None


def apply_integration(config: ShortcutConfig, labels: dict[str, str] | None = None) -> None:
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
    if sys.platform == "win32" and config.mode == "pinned":
        apply_registration(config, Path(sys.executable), labels=labels or {})
    else:
        apply_registration(config, Path(sys.executable))
