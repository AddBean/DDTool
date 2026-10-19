from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from tkinter import BooleanVar, StringVar, TclError, Toplevel, messagebox, ttk
from typing import Any, Callable

from ddtool.config import APP_TITLE
from ddtool.macos_ui import configure_dialog
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


_open_dialog: Toplevel | None = None
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


def show_keep_awake_dialog(
    parent: Any,
    controller: KeepAwakeController | None = None,
    on_changed: Callable[[], None] | None = None,
) -> None:
    global _open_dialog
    keep = controller or _controller
    if _open_dialog is not None:
        try:
            if _open_dialog.winfo_exists():
                try:
                    _open_dialog.deiconify()
                except TclError:
                    pass
                _open_dialog.lift()
                _open_dialog.focus_force()
                return
        except TclError:
            pass
        _open_dialog = None

    dialog = Toplevel(parent)
    _open_dialog = dialog
    dialog.title("防睡眠")
    dialog.minsize(440, 420)
    # Non-modal utility window: can be minimized / put away while the session keeps running.
    dialog.transient(parent)
    configure_dialog(dialog)

    label_style = "DDTool.TLabel" if IS_MACOS else "TLabel"
    secondary_style = "DDTool.Secondary.TLabel" if IS_MACOS else "TLabel"
    frame_style = "DDTool.TFrame" if IS_MACOS else "TFrame"
    radio_style = "DDTool.TRadiobutton" if IS_MACOS else "TRadiobutton"
    check_style = "DDTool.TCheckbutton" if IS_MACOS else "TCheckbutton"

    status = keep.status()
    status_var = StringVar(value=status.message)
    hours_var = StringVar(value="1")
    minutes_var = StringVar(value="0")
    end_var = StringVar(value=EndAction.DEFAULT.value)
    preset_var = StringVar(value="1 小时")
    display_off_var = BooleanVar(value=False)

    ttk.Label(
        dialog,
        text="长时间下载时可阻止自动睡眠与锁屏；可勾选允许黑屏，鼠标移动会唤醒屏幕但不会进入锁屏。",
        wraplength=400,
        justify="left",
        style=secondary_style,
    ).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 8))

    ttk.Label(dialog, text="当前状态", style=label_style).grid(
        row=1, column=0, sticky="ne", padx=(20, 10), pady=8
    )
    ttk.Label(dialog, textvariable=status_var, wraplength=320, style=secondary_style).grid(
        row=1, column=1, columnspan=2, sticky="w", padx=(0, 20), pady=8
    )

    ttk.Label(dialog, text="时长", style=label_style).grid(
        row=2, column=0, sticky="e", padx=(20, 10), pady=(12, 4)
    )
    duration_row = ttk.Frame(dialog, style=frame_style)
    duration_row.grid(row=2, column=1, columnspan=2, sticky="w", padx=(0, 20), pady=(12, 4))
    ttk.Combobox(
        duration_row,
        textvariable=preset_var,
        values=tuple(label for _secs, label in DURATION_PRESETS) + ("自定义",),
        state="readonly",
        width=12,
    ).pack(side="left")
    hours_spin = ttk.Spinbox(duration_row, from_=0, to=48, textvariable=hours_var, width=4)
    hours_spin.pack(side="left", padx=(12, 4))
    ttk.Label(duration_row, text="小时", style=secondary_style).pack(side="left")
    minutes_spin = ttk.Spinbox(duration_row, from_=0, to=59, textvariable=minutes_var, width=4)
    minutes_spin.pack(side="left", padx=(12, 4))
    ttk.Label(duration_row, text="分钟", style=secondary_style).pack(side="left")

    ttk.Checkbutton(
        dialog,
        text="允许黑屏（鼠标可唤醒屏幕，不锁屏）",
        variable=display_off_var,
        style=check_style,
    ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(0, 20), pady=(12, 4))

    ttk.Label(dialog, text="结束后", style=label_style).grid(
        row=4, column=0, sticky="ne", padx=(20, 10), pady=(16, 4)
    )
    end_frame = ttk.Frame(dialog, style=frame_style)
    end_frame.grid(row=4, column=1, columnspan=2, sticky="w", padx=(0, 20), pady=(16, 4))
    for action in (EndAction.DEFAULT, EndAction.LOCK, EndAction.SHUTDOWN):
        ttk.Radiobutton(
            end_frame,
            text=END_ACTION_LABELS[action],
            variable=end_var,
            value=action.value,
            style=radio_style,
        ).pack(anchor="w", pady=2)

    def _apply_preset(_event: Any = None) -> None:
        label = preset_var.get()
        for seconds, preset_label in DURATION_PRESETS:
            if preset_label == label:
                hours_var.set(str(seconds // 3600))
                minutes_var.set(str((seconds % 3600) // 60))
                hours_spin.configure(state="disabled")
                minutes_spin.configure(state="disabled")
                return
        hours_spin.configure(state="normal")
        minutes_spin.configure(state="normal")

    def _parse_duration() -> int:
        try:
            hours = int(hours_var.get().strip() or "0")
            minutes = int(minutes_var.get().strip() or "0")
        except ValueError as exc:
            raise ValueError("请输入有效的小时和分钟。") from exc
        if hours < 0 or minutes < 0 or minutes > 59:
            raise ValueError("分钟需在 0–59 之间。")
        total = hours * 3600 + minutes * 60
        if total <= 0:
            raise ValueError("时长至少 1 分钟。")
        if total > 48 * 3600:
            raise ValueError("时长最多 48 小时。")
        return total

    def _refresh_status() -> None:
        try:
            if not dialog.winfo_exists():
                return
        except TclError:
            return
        status_var.set(keep.status().message)
        dialog.after(1000, _refresh_status)

    def _close() -> None:
        global _open_dialog
        keep.remove_listener(_on_controller_changed)
        if _open_dialog is dialog:
            _open_dialog = None
        dialog.destroy()

    def _on_controller_changed() -> None:
        try:
            if dialog.winfo_exists():
                status_var.set(keep.status().message)
        except TclError:
            pass
        if on_changed:
            on_changed()

    def _start() -> None:
        try:
            duration = _parse_duration()
            action = EndAction(end_var.get())
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc), parent=dialog)
            return
        keep.start(
            duration,
            action,
            allow_display_off=bool(display_off_var.get()),
        )
        status_var.set(keep.status().message)
        if on_changed:
            on_changed()

    def _stop() -> None:
        keep.stop(run_end_action=False)
        status_var.set(keep.status().message)
        if on_changed:
            on_changed()

    buttons = ttk.Frame(dialog, style=frame_style)
    buttons.grid(row=5, column=0, columnspan=3, sticky="e", padx=20, pady=(20, 18))
    ttk.Button(buttons, text="开始", width=8, command=_start).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="停止", width=8, command=_stop).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="收起", width=8, command=_close).pack(side="left")

    dialog.columnconfigure(1, weight=1)
    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.bind("<Escape>", lambda _event: _close())
    preset_var.trace_add("write", lambda *_args: _apply_preset())
    _apply_preset()
    keep.add_listener(_on_controller_changed)

    dialog.update_idletasks()
    width, height = 480, 460
    x = (dialog.winfo_screenwidth() - width) // 2
    y = (dialog.winfo_screenheight() - height) // 2
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.lift()
    dialog.focus_force()
    # No grab_set: keep it non-modal so it can be minimized / dismissed freely.
    _refresh_status()
