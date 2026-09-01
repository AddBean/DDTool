# -*- mode: python ; coding: utf-8 -*-

import os


app_version = os.environ.get('DDTOOL_VERSION', '0.0.0').lstrip('v')


a = Analysis(
    ['src/ddtool/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[('assets/tray_icon.png', 'assets')],
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
