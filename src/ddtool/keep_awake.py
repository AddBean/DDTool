from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from ddtool.platform import IS_MACOS, IS_WINDOWS
from ddtool.system_lock import lock_workstation


class EndAction(str, Enum):
    DEFAULT = "default"
    LOCK = "lock"
    SHUTDOWN = "shutdown"


END_ACTION_LABELS = {
    EndAction.DEFAULT: "恢复默认（允许睡眠/锁屏）",
    EndAction.LOCK: "锁屏",
    EndAction.SHUTDOWN: "关机",
}

DURATION_PRESETS = (
    (30 * 60, "30 分钟"),
    (60 * 60, "1 小时"),
    (2 * 60 * 60, "2 小时"),
    (4 * 60 * 60, "4 小时"),
    (8 * 60 * 60, "8 小时"),
)


@dataclass(slots=True)
class KeepAwakeStatus:
    active: bool
    remaining_seconds: int
    end_action: EndAction
    allow_display_off: bool
    message: str


class KeepAwakeController:
    """Prevent system sleep / lock for a timed session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._deadline: float | None = None
        self._end_action = EndAction.DEFAULT
        self._allow_display_off = False
        self._caffeinate: subprocess.Popen[bytes] | None = None
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                pass

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def status(self) -> KeepAwakeStatus:
        with self._lock:
            active = self._thread is not None and self._thread.is_alive()
            remaining = 0
            if active and self._deadline is not None:
                remaining = max(0, int(self._deadline - time.monotonic()))
            end_action = self._end_action
            allow_display_off = self._allow_display_off
        if not active:
            return KeepAwakeStatus(False, 0, end_action, allow_display_off, "未启用")
        label = END_ACTION_LABELS[end_action]
        display = "允许黑屏" if allow_display_off else "保持亮屏"
        return KeepAwakeStatus(
            True,
            remaining,
            end_action,
            allow_display_off,
            f"防睡眠中（{display}），剩余 {_format_duration(remaining)}，结束后：{label}",
        )

    def start(
        self,
        duration_seconds: int,
        end_action: EndAction,
        *,
        allow_display_off: bool = False,
    ) -> None:
        if duration_seconds <= 0:
            raise ValueError("时长必须大于 0")
        if end_action not in EndAction:
            raise ValueError(f"未知结束动作：{end_action}")
        with self._lock:
            self._stop_locked(run_end_action=False)
            self._stop.clear()
            self._deadline = time.monotonic() + duration_seconds
            self._end_action = end_action
            self._allow_display_off = allow_display_off
            self._thread = threading.Thread(
                target=self._run,
                args=(duration_seconds, end_action, allow_display_off),
                name="ddtool-keep-awake",
                daemon=True,
            )
            self._thread.start()
        self._notify()

    def stop(self, *, run_end_action: bool = False) -> None:
        with self._lock:
            self._stop_locked(run_end_action=run_end_action)
        self._notify()

    def _stop_locked(self, *, run_end_action: bool) -> None:
        end_action = self._end_action
        self._stop.set()
        self._kill_caffeinate()
        thread = self._thread
        self._thread = None
        self._deadline = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._clear_os_assertion()
        if run_end_action:
            _perform_end_action(end_action)

    def _run(
        self,
        duration_seconds: int,
        end_action: EndAction,
        allow_display_off: bool,
    ) -> None:
        try:
            self._begin_os_assertion(allow_display_off=allow_display_off)
            if allow_display_off:
                # Let the assertion settle, then turn the panel off without locking.
                time.sleep(0.8)
                if not self._stop.is_set():
                    _turn_display_off()
            deadline = time.monotonic() + duration_seconds
            while not self._stop.wait(timeout=15):
                if time.monotonic() >= deadline:
                    break
                self._refresh_os_assertion(allow_display_off=allow_display_off)
            if self._stop.is_set():
                self._clear_os_assertion()
                return
            self._clear_os_assertion()
            with self._lock:
                self._thread = None
                self._deadline = None
            _perform_end_action(end_action)
        finally:
            self._kill_caffeinate()
            self._clear_os_assertion()
            self._notify()

    def _begin_os_assertion(self, *, allow_display_off: bool) -> None:
        if IS_WINDOWS:
            _windows_set_execution_state(keep_display_on=not allow_display_off)
            return
        if IS_MACOS:
            self._kill_caffeinate()
            # -d keeps display awake; omit it when user allows black screen.
            args = ["caffeinate", "-ims"]
            if not allow_display_off:
                args.append("-d")
            try:
                self._caffeinate = subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                self._caffeinate = None

    def _refresh_os_assertion(self, *, allow_display_off: bool) -> None:
        if IS_WINDOWS:
            _windows_set_execution_state(keep_display_on=not allow_display_off)

    def _clear_os_assertion(self) -> None:
        if IS_WINDOWS:
            _windows_set_execution_state(keep_display_on=False, active=False)
        self._kill_caffeinate()

    def _kill_caffeinate(self) -> None:
        process = self._caffeinate
        self._caffeinate = None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass


_controller = KeepAwakeController()


def get_keep_awake_controller() -> KeepAwakeController:
    return _controller


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} 小时 {minutes:02d} 分"
    if minutes:
        return f"{minutes} 分 {secs:02d} 秒"
    return f"{secs} 秒"


def _windows_set_execution_state(*, keep_display_on: bool, active: bool = True) -> None:
    import ctypes

    es_continuous = 0x80000000
    es_system_required = 0x00000001
    es_display_required = 0x00000002
    flags = es_continuous
    if active:
        flags |= es_system_required
        if keep_display_on:
            flags |= es_display_required
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def _turn_display_off() -> None:
    """Blank the panel without locking the session; input can wake it."""
    if IS_WINDOWS:
        import ctypes

        hwnd_broadcast = 0xFFFF
        wm_syscommand = 0x0112
        sc_monitorpower = 0xF170
        ctypes.windll.user32.SendMessageW(hwnd_broadcast, wm_syscommand, sc_monitorpower, 2)
        return
    if IS_MACOS:
        subprocess.run(
            ["pmset", "displaysleepnow"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )


def _perform_end_action(action: EndAction) -> None:
    if action == EndAction.DEFAULT:
        return
    if action == EndAction.LOCK:
        lock_workstation()
        return
    if action == EndAction.SHUTDOWN:
        _shutdown_system()


def _shutdown_system() -> None:
    if IS_WINDOWS:
        subprocess.Popen(
            ["shutdown", "/s", "/t", "0"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        return
    if IS_MACOS:
        subprocess.Popen(
            [
                "osascript",
                "-e",
                'tell application "System Events" to shut down',
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
