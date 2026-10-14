# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/admin/Documents/app/installer.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/admin/Documents/app/dist/ParentalControlService.exe', '.'), ('C:/Users/admin/Documents/app/config.json', '.'), ('C:/Users/admin/Documents/app/blocked.html', '.')],
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
    name='Install',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    manifest='C:/Users/admin/Documents/app/admin_manifest.xml',
)
