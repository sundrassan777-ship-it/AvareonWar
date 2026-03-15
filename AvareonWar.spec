# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for AvareonWar

import os

block_cipher = None

# Project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

# Steamworks SDK: include DLLs if present (optional — only available with Steamworks partner account)
steam_binaries = []
for dll_name in ['steam_api64.dll', 'SteamworksPy64.dll']:
    dll_path = os.path.join(PROJECT_ROOT, dll_name)
    if os.path.exists(dll_path):
        steam_binaries.append((dll_path, '.'))

# Steamworks Python wrapper (optional — only present after SDK setup)
steam_datas = []
steamworks_dir = os.path.join(PROJECT_ROOT, 'steamworks')
if os.path.isdir(steamworks_dir):
    steam_datas.append((steamworks_dir, 'steamworks'))

# steam_appid.txt — SteamworksPy requires this in CWD even when launched via Steam
steam_appid = os.path.join(PROJECT_ROOT, 'steam_appid.txt')
if os.path.isfile(steam_appid):
    steam_datas.append((steam_appid, '.'))

# Data files to include (source, destination in bundle)
datas = steam_datas + [
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
        # Campaign missions - dynamically imported via importlib.import_module()
        'tutorial_mission',
        'campaign_mission_2',
        'campaign_mission_3',
        'campaign_mission_4',
        'campaign_mission_5',
        'campaign_mission_6',
        'cutscene_player',
        'campaign_utils',
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
