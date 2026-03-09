# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for AvareonWar

import os

block_cipher = None

# Project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

# Steamworks SDK: include steam_api64.dll if present (optional dependency)
steam_binaries = []
steam_dll = os.path.join(PROJECT_ROOT, 'steam_api64.dll')
if os.path.exists(steam_dll):
    steam_binaries.append((steam_dll, '.'))

# Data files to include (source, destination in bundle)
datas = [
    # Assets folder
    (os.path.join(PROJECT_ROOT, 'assets'), 'assets'),
    # Config folder
    (os.path.join(PROJECT_ROOT, 'config'), 'config'),
    # JSON data files
    (os.path.join(PROJECT_ROOT, 'economic_data.json'), '.'),
    (os.path.join(PROJECT_ROOT, 'territory_polygons.json'), '.'),
    (os.path.join(PROJECT_ROOT, 'plots.json'), '.'),
    (os.path.join(PROJECT_ROOT, 'territory_bonuses.json'), '.'),
    (os.path.join(PROJECT_ROOT, 'campaign_data.json'), '.'),
    (os.path.join(PROJECT_ROOT, 'cutscene_data.json'), '.'),
    (os.path.join(PROJECT_ROOT, 'config.json'), '.'),
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=steam_binaries,
    datas=datas,
    hiddenimports=[
        'pygame',
        'pygame.mixer',
        'pygame.font',
        'pygame.image',
        'pygame.transform',
        'pygame.draw',
        'pygame.display',
        'pygame.event',
        'pygame.key',
        'pygame.mouse',
        'pygame.time',
        'pygame.surface',
        'pygame.rect',
        'pygame.color',
        'json',
        'random',
        'math',
        'threading',
        'socket',
        'queue',
        'time',
        'os',
        'sys',
        'miniupnpc',
        'steamworks',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'PIL', 'Pillow', 'tkinter', '_tkinter',
        'pytest', 'pytest_cov', 'pytest_timeout',
        'unittest', 'doctest',
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
    [],
    exclude_binaries=True,
    name='War of Avareon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window - set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'assets', 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='War of Avareon',
)
