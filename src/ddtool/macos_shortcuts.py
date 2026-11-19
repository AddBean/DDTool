from __future__ import annotations

import ctypes
import os
import plistlib
import shlex
import tempfile
from pathlib import Path
from uuid import uuid4

from ddtool.shell_shortcuts import ShortcutConfig


WORKFLOW_NAME = "DDTool Folder Shortcuts.workflow"
OWNER = "com.ddtool.app.folder-shortcuts"
FILE_INPUT = "com.apple.Automator.fileSystemObject.folders"


def write_workflow(destination: Path, label: str, launcher: list[str]) -> None:
    contents = destination / "Contents"
    contents.mkdir(parents=True)
    metadata = {
        "CFBundleIdentifier": OWNER,
        "CFBundleName": label,
        "CFBundleVersion": "1",
        "NSServices": [{
            "NSMenuItem": {"default": label},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": ["public.folder"],
        }],
    }
    workflow = {
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "connectors": {},
        "actions": [{"action": {
            "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
            "ActionName": "Run Shell Script",
            "BundleIdentifier": "com.apple.RunShellScript",
            "AMActionVersion": "2.0.3",
            "ActionParameters": {
                "CheckedForUserDefaultShell": True,
                "COMMAND_STRING": f'if [ "$#" -eq 1 ] && [ -d "$1" ]; then\n  exec {shlex.join(launcher)} "$1"\nfi',
                "inputMethod": 1,
                "shell": "/bin/sh",
                "source": "",
            },
            "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
            "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
            "InputUUID": str(uuid4()),
            "OutputUUID": str(uuid4()),
            "UUID": str(uuid4()),
        }}],
        "workflowMetaData": {
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": FILE_INPUT,
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }
    (contents / "Info.plist").write_bytes(plistlib.dumps(metadata))
    (contents / "document.wflow").write_bytes(plistlib.dumps(workflow))


def apply_registration(config: ShortcutConfig, executable: Path, services: Path | None = None) -> None:
    services = services if services is not None else Path.home() / "Library" / "Services"
    destination = services / WORKFLOW_NAME
    present = destination.is_symlink() or destination.exists()
    if present:
        try:
            contents = destination / "Contents"
            info = contents / "Info.plist"
            owned = not any(path.is_symlink() for path in (destination, contents, info)) and (
                plistlib.loads(info.read_bytes()).get("CFBundleIdentifier") == OWNER
            )
        except (OSError, ValueError, AttributeError, plistlib.InvalidFileException):
            owned = False
        if not owned:
            if config.enabled:
                raise ValueError("同名 Finder 快捷操作已存在，未覆盖其他工作流。")
            return
    if config.enabled:
        bundle = executable.parents[2] if len(executable.parents) >= 3 else executable
        if bundle.suffix != ".app" or executable.parent != bundle / "Contents" / "MacOS":
            raise ValueError("请将豆荚工具放入“应用程序”后再开启 Finder 入口。")
        if str(bundle).startswith("/Volumes/") or "AppTranslocation" in bundle.parts:
            raise ValueError("请退出应用，从“应用程序”重新打开后再开启 Finder 入口。")
        services.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=services) as directory:
            staging = Path(directory) / WORKFLOW_NAME
            backup = Path(directory) / "previous"
            write_workflow(staging, config.label, ["/usr/bin/open", "-n", "-a", str(bundle), "--args", "--shell-shortcut", "finder"])
            if present:
                os.replace(destination, backup)
            try:
                os.replace(staging, destination)
            except OSError:
                if present:
                    os.replace(backup, destination)
                raise
    elif present:
        with tempfile.TemporaryDirectory(dir=services) as directory:
            os.replace(destination, Path(directory) / WORKFLOW_NAME)
    else:
        return
    _refresh_services()


def _refresh_services() -> None:
    framework = ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    refresh = framework.NSUpdateDynamicServices
    refresh.argtypes = []
    refresh.restype = None
    refresh()
