# -*- mode: python ; coding: utf-8 -*-
# VIDEOCU v1 - PyInstaller Spec File

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('.env.example', '.'),
        ('client_secrets.json.example', '.'),
    ],
    hiddenimports=[
        'google.generativeai',
        'google.oauth2',
        'google_auth_oauthlib',
        'googleapiclient',
        'moviepy',
        'moviepy.video.fx.all',
        'moviepy.audio.fx.all',
        'elevenlabs',
        'pytrends',
        'TikTokApi',
        'instagrapi',
        'PIL',
        'numpy',
        'imageio',
        'imageio_ffmpeg',
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'sqlalchemy',
        'pydantic',
        'requests',
        'dotenv',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VIDEOCU_v1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
)
