from __future__ import annotations

import os
import sys


IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def subprocess_creation_flags() -> int:
    """Return Windows-only flags without leaking them into POSIX subprocess calls."""
    if not IS_WINDOWS:
        return 0
    import subprocess

    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def executable_search_path() -> str | None:
    """Include common Homebrew locations when Finder launches the macOS app."""
    if not IS_MACOS:
        return None
    entries = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    current = os.environ.get("PATH", "")
    if current:
        entries.append(current)
    return os.pathsep.join(entries)
