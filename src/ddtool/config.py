from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


APP_NAME = "DDTool"
APP_TITLE = "豆荚工具"


@dataclass(slots=True)
class AppConfig:
    scrcpy_path: str = "scrcpy"
    scrcpy_args: list[str] | None = None
    gnirehtet_path: str = "gnirehtet"
    forward_local_port: int = 19999
    forward_phone_port: int = 9999
    mcp_server_name: str = "phone-mcp"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        args = data.get("scrcpy_args")
        return cls(
            scrcpy_path=str(data.get("scrcpy_path") or "scrcpy"),
            scrcpy_args=args if isinstance(args, list) else [],
            gnirehtet_path=str(data.get("gnirehtet_path") or "gnirehtet"),
            forward_local_port=int(data.get("forward_local_port", 19999)),
            forward_phone_port=int(data.get("forward_phone_port", 9999)),
            mcp_server_name=str(data.get("mcp_server_name", "phone-mcp")),
        )


def get_config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if sys.platform == "win32" and appdata:
        return Path(appdata) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / APP_NAME.lower()
    return Path.home() / f".{APP_NAME.lower()}"


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def load_config() -> AppConfig:
    path = get_config_path()
    if not path.exists():
        config = AppConfig(scrcpy_args=[])
        save_config(config)
        return config

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppConfig(scrcpy_args=[])

    if not isinstance(data, dict):
        return AppConfig(scrcpy_args=[])
    return AppConfig.from_dict(data)


def save_config(config: AppConfig) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def config_to_dict(config: AppConfig | None = None) -> dict[str, Any]:
    if config is None:
        config = load_config()
    return asdict(config)


def replace_config(data: dict[str, Any]) -> AppConfig:
    try:
        config = AppConfig.from_dict(data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"工具配置字段无效：{exc}") from exc
    save_config(config)
    return config


_APP_CONFIG_KEYS = {
    "scrcpy_path",
    "scrcpy_args",
    "gnirehtet_path",
    "forward_local_port",
    "forward_phone_port",
    "mcp_server_name",
}


def build_export_payload(quick_actions: dict[str, Any]) -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "config": config_to_dict(),
        "quick_actions": quick_actions,
    }


def parse_import_payload(data: Any) -> tuple[dict[str, Any] | None, Any | None]:
    if isinstance(data, list):
        return None, data
    if not isinstance(data, dict):
        raise ValueError("配置文件不是有效的 JSON 对象")

    if data.get("app") == APP_NAME or ("config" in data and "quick_actions" in data):
        config_data = data.get("config")
        if config_data is not None and not isinstance(config_data, dict):
            raise ValueError("config 字段格式无效")
        return (config_data if isinstance(config_data, dict) else None, data.get("quick_actions"))

    if "actions" in data or "seeded_presets" in data:
        return None, data

    if _APP_CONFIG_KEYS & data.keys():
        return data, None

    raise ValueError("无法识别的配置文件格式")
