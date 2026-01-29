# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

project_dir = os.path.abspath(os.getcwd())

hiddenimports = []
hiddenimports += collect_submodules('PyQt6.QtMultimedia')


a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (os.path.join(project_dir, 'ui', 'ui_files'), os.path.join('ui', 'ui_files')),
        (os.path.join(project_dir, 'ui', 'styles'), os.path.join('ui', 'styles')),
        (os.path.join(project_dir, 'ui', 'icons'), os.path.join('ui', 'icons')),
        (os.path.join(project_dir, 'assets'), 'assets'),
        (os.path.join(project_dir, 'database', 'asil_system.db'), 'database'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6',
        'PySide6_Addons',
        'PySide6_Essentials',
        'shiboken6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SATTUP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    exclude_binaries=True,
    icon=os.path.join(project_dir, 'ui', 'icons', 'ekle.ico') if os.path.exists(os.path.join(project_dir, 'ui', 'icons', 'ekle.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='SATTUP',
)
