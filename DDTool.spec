# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/ddtool/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[('vendor/scrcpy-win64-v4.1', 'vendor/scrcpy-win64-v4.1'), ('assets/tray_icon.png', 'assets'), ('assets/app.ico', 'assets')],
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
    a.binaries,
    a.datas,
    [],
    name='DDTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
