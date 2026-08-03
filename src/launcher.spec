# -*- mode: python ; coding: utf-8 -*-
#
# BUILD-TIME BUNDLING (answers "can end users get this with zero setup?"):
# datas=[('libs', 'libs'), ...] below means whatever you (the developer) put
# in libs/ at BUILD time - PresentMon*.exe, LibreHardwareMonitorLib.dll, or
# neither - gets packed straight into the shipped BloomPlay.exe. End users
# who download your built EXE never see libs/, never download anything
# separately, and never run a second program: you do that setup once here,
# they just get a single .exe that already has it (or doesn't, and those
# two features degrade gracefully to N/A, same as today).

block_cipher = None


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('dashboard', 'dashboard'), ('libs', 'libs'), ('Data Bloom icon.svg', '.')],
    hiddenimports=[
        'pynvml',
        'wmi',
        'pythoncom',
        'GPUtil',
        'ping3',
        'qrcode',
        'openpyxl',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # Only needed if you're bundling LibreHardwareMonitorLib.dll (optional -
        # PyInstaller + pythonnet can need a nudge to bundle the CLR loader;
        # if the built EXE can't find sensors that work fine in dev mode,
        # this is the first thing to check).
        'clr',
        'clr_loader',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BloomPlay',
    icon='BloomPlay.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # windowed app (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
