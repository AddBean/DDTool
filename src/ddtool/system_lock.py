from __future__ import annotations

import subprocess
import threading

from ddtool.platform import IS_MACOS, IS_WINDOWS


def lock_workstation() -> None:
    """Lock the current user session on Windows or macOS."""
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.user32.LockWorkStation()
        return
    if IS_MACOS:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "q" using {control down, command down}',
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )


class LockScreenDelayer:
    def __init__(self, delay_seconds: int = 60 * 60) -> None:
        self.delay_seconds = delay_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def postpone(self) -> None:
        with self._lock:
            self._cancel_locked()
            self._timer = threading.Timer(self.delay_seconds, lock_workstation)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        with self._lock:
            self._cancel_locked()

    def _cancel_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
