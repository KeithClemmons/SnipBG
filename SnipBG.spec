# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build for SnipBG on Windows, macOS and Linux.
# Run via build_exe.bat / build_release.sh (or: python -m PyInstaller SnipBG.spec).

import re
import sys

from PyInstaller.utils.hooks import collect_data_files

with open('app.py', encoding='utf-8') as f:
    VERSION = re.search(r'APP_VERSION = "(.+?)"', f.read()).group(1)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    # config.yaml from the model package is copied to the user's profile on first run.
    datas=[('snipbg.ico', '.'), ('snipbg.png', '.')] + collect_data_files('transparent_background'),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Never used by SnipBG: pymatting (and its numba/llvmlite JIT) is an optional
    # post-processing step in transparent_background that we don't call; matplotlib
    # is only pulled in by optional imports. Saves ~120 MB.
    excludes=['pymatting', 'numba', 'llvmlite', 'matplotlib'],
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
    # PyInstaller converts the PNG to .icns on macOS (needs Pillow).
    icon=['snipbg.ico'] if sys.platform == 'win32' else ['snipbg.png'],
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

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='SnipBG.app',
        icon='snipbg.png',
        bundle_identifier='com.keithclemmons.snipbg',
        version=VERSION,
        info_plist={
            'CFBundleShortVersionString': VERSION,
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
        },
    )
