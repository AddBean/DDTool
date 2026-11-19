# -*- mode: python ; coding: utf-8 -*-

import os
import re
from pathlib import Path


version = re.match(r'^v?(\d+\.\d+\.\d+)(?:$|[-+])', os.environ.get('DDTOOL_VERSION', ''))
app_version = version.group(1) if version else '0.0.0'
version_file = Path('build/ddtool-version.txt')
version_file.parent.mkdir(exist_ok=True)
version_file.write_text(app_version, encoding='utf-8')


a = Analysis(
    ['src/ddtool/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[('assets/tray_icon.png', 'assets'), ('src/ddtool/qml', 'ddtool/qml'), ('LICENSE', '.'), (str(version_file), '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DDTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='DDTool',
)

app = BUNDLE(
    coll,
    name='豆荚工具.app',
    icon='assets/tray_icon.png',
    bundle_identifier='com.ddtool.app',
    info_plist={
        'CFBundleDisplayName': '豆荚工具',
        'CFBundleShortVersionString': app_version,
        'CFBundleVersion': app_version,
        'LSUIElement': True,
        'NSAppleEventsUsageDescription': '豆荚工具需要使用系统事件执行锁屏操作。',
    },
)
