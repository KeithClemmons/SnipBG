# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build for SnipBG. Run via build_exe.bat (or: python -m PyInstaller SnipBG.spec).

from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    # config.yaml from the model package is copied to the user's profile on first run.
    datas=[('snipbg.ico', '.')] + collect_data_files('transparent_background'),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
    # kornia compiles functions with torch.jit.script at import time, which needs the
    # original .py source files next to the bytecode.
    module_collection_mode={'kornia': 'pyz+py'},
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SnipBG',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['snipbg.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SnipBG',
)
