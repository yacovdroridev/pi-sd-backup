# pi_sd_backup.spec
# -----------------
# PyInstaller spec file.  Produces a single-folder build in dist/pi_sd_backup/
# Run from the project root:
#   pyinstaller pi_sd_backup.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        # Include the app icon if present (place a 256x256 icon here)
        ('assets/icon.ico', 'assets') if Path('assets/icon.ico').exists() else ('main.py', '.'),
    ],
    hiddenimports=[
        # Paramiko needs these at runtime
        'paramiko',
        'paramiko.transport',
        'paramiko.sftp_client',
        'cryptography',
        # PySide6 platform plugin
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PiSdBackup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                        # no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pi_sd_backup',
)
