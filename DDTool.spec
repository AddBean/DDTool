# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

version_file = Path('build/ddtool-version.txt')
version_file.parent.mkdir(exist_ok=True)
version_file.write_text(os.environ.get('DDTOOL_VERSION', '0.0.0'), encoding='utf-8')

a = Analysis(
    ['src/ddtool/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[('vendor/scrcpy-win64-v4.1', 'vendor/scrcpy-win64-v4.1'), ('assets/tray_icon.png', 'assets'),
           ('assets/app.ico', 'assets'), ('src/ddtool/qml', 'ddtool/qml'), ('LICENSE', '.'), (str(version_file), '.')],
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
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/app.ico'],
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DDTool')
