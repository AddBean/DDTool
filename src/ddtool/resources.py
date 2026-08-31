from __future__ import annotations

import sys
import shutil
from pathlib import Path

from ddtool.platform import IS_MACOS, IS_WINDOWS, executable_search_path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def bundled_scrcpy_dir() -> Path:
    if IS_WINDOWS:
        return app_base_dir() / "vendor" / "scrcpy-win64-v4.1"
    return app_base_dir() / "vendor" / "scrcpy-macos"


def bundled_scrcpy_path() -> Path:
    return bundled_scrcpy_dir() / ("scrcpy.exe" if IS_WINDOWS else "scrcpy")


def find_executable(name: str) -> Path | None:
    suffix = ".exe" if IS_WINDOWS else ""
    bundled = bundled_scrcpy_dir() / f"{name}{suffix}"
    if bundled.exists():
        return bundled
    found = shutil.which(name, path=executable_search_path())
    return Path(found) if found else None


def bundled_icon_png() -> Path:
    return app_base_dir() / "assets" / "tray_icon.png"


def bundled_icon_ico() -> Path:
    return app_base_dir() / "assets" / "app.ico"


def bundled_icon_icns() -> Path:
    return app_base_dir() / "assets" / "app.icns"
