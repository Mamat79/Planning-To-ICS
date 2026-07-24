# -*- mode: python ; coding: utf-8 -*-

import os

release_version = os.environ.get('PLANNING_RELEASE_VERSION', '2.0')
notice_path = f'output/pdf/Planning_to_ICS_V{release_version}_Notice.pdf'

a = Analysis(
    ['planning_native.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/planning-to-ics.png', 'assets'),
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
    a.binaries,
    a.datas,
    [],
    name='Planning To ICS',
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
)

app = BUNDLE(
    exe,
    name='Planning To ICS.app',
    icon='assets/planning-to-ics.icns',
    bundle_identifier='com.mamat.planning-to-ics',
    info_plist={
        'CFBundleDisplayName': 'Planning to ICS',
        'CFBundleName': 'Planning to ICS',
        'CFBundleShortVersionString': release_version,
        'CFBundleVersion': release_version,
        'NSHighResolutionCapable': True,
    },
)
