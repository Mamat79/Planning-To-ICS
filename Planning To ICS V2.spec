# -*- mode: python ; coding: utf-8 -*-

import os

release_version = os.environ.get('PLANNING_RELEASE_VERSION', '2.0')
notice_path = f'output\\pdf\\Planning_to_ICS_V{release_version}_Notice.pdf'

a = Analysis(
    ['planning_native.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets\\planning-to-ics.ico', 'assets'),
        ('assets\\planning-to-ics.png', 'assets'),
        ('assets\\planning-to-ics.ico', '.'),
        (notice_path, '.'),
    ],
    hiddenimports=['tzdata'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'webview'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Planning to ICS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=['assets\\planning-to-ics.ico'],
    version='version_info.txt',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Planning to ICS',
)
