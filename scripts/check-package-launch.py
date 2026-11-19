from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ddtool.shell_shortcuts import ShortcutConfig


def check_launch(executable: Path) -> None:
    with tempfile.TemporaryDirectory() as directory:
        profile = Path(directory)
        folder = profile / "含 空格的文件夹"
        folder.mkdir()
        windows = sys.platform == "win32"
        base = profile if windows else profile / "Library" / "Application Support"
        config = base / "DDTool"
        ShortcutConfig(True, mode="devices").save(config / "shell-shortcuts.json")
        env = {**os.environ, "HOME": directory, "APPDATA": directory,
               "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"}
        options = ["--shell-shortcut", "directory" if windows else "finder", str(folder)]
        log = profile / "launch.log"
        try:
            with log.open("wb") as stream, subprocess.Popen(
                [str(executable), *options], env=env, stdout=stream, stderr=subprocess.STDOUT,
            ) as primary:
                try:
                    deadline = time.monotonic() + 15
                    lock = config / "workbench.lock"
                    while not lock.is_file() and primary.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    if not lock.is_file():
                        raise RuntimeError(f"Cold start did not hold its lock (exit: {primary.poll()}).")
                    subprocess.run([str(executable), *options], env=env, timeout=15, check=True,
                                   stdout=stream, stderr=subprocess.STDOUT)
                    if primary.poll() is not None:
                        raise RuntimeError("Primary instance exited during shortcut forwarding.")
                finally:
                    if primary.poll() is None:
                        primary.kill()
        except Exception:
            print(log.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
            raise
        output = log.read_text(encoding="utf-8", errors="replace")
        if "Traceback (most recent call last)" in output:
            raise RuntimeError(output)
    print("Packaged cold launch and second shortcut activation passed.")


if __name__ == "__main__":
    check_launch(Path(sys.argv[1]).resolve(strict=True))
