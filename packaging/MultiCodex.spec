# -*- mode: python ; coding: utf-8 -*-
# Build on Windows: pyinstaller packaging/MultiCodex.spec --noconfirm --clean
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).resolve().parent
datas = collect_data_files('customtkinter')
for distribution in ('customtkinter', 'darkdetect', 'psutil', 'Pillow'):
    datas += copy_metadata(distribution)
a = Analysis(
    [str(ROOT / 'run.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=['customtkinter', 'darkdetect', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts,
    [],
    exclude_binaries=True,
    name='MultiCodex',
    version=str(ROOT / 'packaging' / 'version_info.txt'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MultiCodex')
