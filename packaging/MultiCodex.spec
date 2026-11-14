# -*- mode: python ; coding: utf-8 -*-
# Build on Windows: pyinstaller packaging/MultiCodex.spec --noconfirm --clean
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

if sys.platform != 'win32' or sys.version_info[:2] != (3, 12):
    raise RuntimeError('Build with Windows CPython 3.12; Tcl/Tk 9 builds are not supported yet.')

ROOT = Path(SPECPATH).resolve().parent
datas = collect_data_files('customtkinter')
for distribution in ('customtkinter', 'darkdetect', 'packaging', 'psutil', 'Pillow', 'pyinstaller'):
    datas += copy_metadata(distribution)
datas += [(str(Path(sys.base_prefix) / 'LICENSE.txt'), 'licenses')]
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
