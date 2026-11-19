from __future__ import annotations

import sys

from ddtool.config import APP_TITLE, load_config
from ddtool.icon import create_tray_icon
from ddtool.phone_mirror import check_scrcpy, resolve_scrcpy_path, run_mirror_smoke_test


def smoke_test() -> int:
    config = load_config()
    icon = create_tray_icon()
    if icon.size != (64, 64):
        print("Unexpected tray icon size.", file=sys.stderr)
        return 1
    scrcpy = resolve_scrcpy_path(config)
    if not scrcpy:
        print("scrcpy was not found.", file=sys.stderr)
        return 1
    check_error = check_scrcpy(scrcpy)
    if check_error:
        print(check_error, file=sys.stderr)
        return 1
    print(f"{APP_TITLE} smoke test passed.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--smoke-test"]:
        raise SystemExit(smoke_test())
    if sys.argv[1:] == ["--mirror-smoke-test"]:
        raise SystemExit(run_mirror_smoke_test(load_config()))
    if sys.argv[1:] == ["--ui-smoke-test"]:
        from ddtool.tray_app import ui_smoke_test

        raise SystemExit(ui_smoke_test())
    from ddtool.tray_app import main

    raise SystemExit(main())
