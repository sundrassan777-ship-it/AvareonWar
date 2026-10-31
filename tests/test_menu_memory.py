# -*- coding: utf-8 -*-
"""
The main menu's memory (the "slow blits" investigation, 2026-10-31): a MainMenu used to
hold 126 MB of surfaces - the 1024 px originals of its 60 px corner buttons - keep them
alive through the whole game (main.py), and decode them again on every return to the
menu (0.9 s).

- utils.surface_utils.load_scaled_cached(): decoded once, only the scaled surface kept,
  None for a missing file, the icon frame's brightening
- a MainMenu holds a few MB of surfaces besides the screen; a later one decodes no image
- the corner buttons still have their pictures (default "?", heroes, rewards, icons)
- main.py lets the menu go once it has run
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.quit()
    pygame.display.init()
    pygame.display.set_mode((1600, 900))
    yield
    pygame.display.set_mode((1600, 900))


@pytest.fixture(autouse=True)
def no_saving(monkeypatch):
    from settings_manager import settings
    monkeypatch.setattr(settings, 'save', lambda *a, **k: None)


def _surface_bytes(value):
    if isinstance(value, pygame.Surface):
        w, h = value.get_size()
        return w * h * value.get_bytesize()
    if isinstance(value, (list, tuple)):
        return sum(_surface_bytes(v) for v in value)
    if isinstance(value, dict):
        return sum(_surface_bytes(v) for v in value.values())
    return 0


def test_load_scaled_cached(monkeypatch, tmp_path):
    from utils import surface_utils
    path = tmp_path / 'big.png'
    source = pygame.Surface((256, 256))
    source.fill((100, 100, 100))
    pygame.image.save(source, str(path))
    loads = []
    real = pygame.image.load
    monkeypatch.setattr(pygame.image, 'load', lambda p, *a: loads.append(p) or real(p, *a))
    first = surface_utils.load_scaled_cached(str(path), (60, 60))
    again = surface_utils.load_scaled_cached(str(path), (60, 60))
    assert first is again and first.get_size() == (60, 60) and len(loads) == 1
    lit = surface_utils.load_scaled_cached(str(path), (60, 60), brighten=51)
    assert abs(lit.get_at((30, 30))[0] - (first.get_at((30, 30))[0] + 51)) <= 1
    missing = str(tmp_path / 'nothing.png')
    assert surface_utils.load_scaled_cached(missing, (60, 60)) is None
    assert surface_utils.load_scaled_cached(missing, (60, 60)) is None
    assert loads.count(missing) == 1                     # A missing file is remembered too


def test_a_main_menu_holds_a_few_megabytes():
    import main_menu
    menu = main_menu.MainMenu(pygame.display.get_surface())
    held = sum(_surface_bytes(v) for k, v in vars(menu).items() if k != 'screen') / 2 ** 20
    assert held <= 20, f"a MainMenu holds {held:.1f} MB of surfaces (it was ~120 MB)"
    for name in ('hero_icons', 'reward_icons_raw', 'icon_border', 'achievement_button_icon',
                 'replays_button_icon', 'wishlist_button_icon', 'button_bg_image'):
        assert not hasattr(menu, name), f"{name}: a full-size original kept on the menu"


def test_a_later_main_menu_decodes_no_image(monkeypatch):
    import main_menu
    main_menu.MainMenu(pygame.display.get_surface())     # Decodes what it needs (if not yet)
    loads = []
    real = pygame.image.load
    monkeypatch.setattr(pygame.image, 'load', lambda p, *a: loads.append(p) or real(p, *a))
    menu = main_menu.MainMenu(pygame.display.get_surface())
    menu.render()
    assert loads == []


def test_corner_buttons_keep_their_pictures(monkeypatch):
    import main_menu
    from achievement_manager import ALL_REWARD_ICON_PATHS
    from settings_manager import settings
    menu = main_menu.MainMenu(pygame.display.get_surface())
    size = menu.profile_button_rect.size
    assert len(menu.hero_icons_button_scaled) == len(menu.HERO_ICON_FILES)
    assert all(s is not None and s.get_size() == size for s in menu.hero_icons_button_scaled)
    assert set(menu.reward_icons_button_scaled) == set(ALL_REWARD_ICON_PATHS)
    assert all(s is not None and s.get_size() == size for s in menu.reward_icons_button_scaled.values())
    assert menu.icon_border_button_scaled.get_size() == (size[0] + 2, size[1] + 2)
    for name in ('achievement_button_icon_scaled', 'replays_button_icon_scaled'):
        assert getattr(menu, name).get_size() == size, name
    # The profile button with the default "?", a hero and a reward portrait
    rect = menu.profile_button_rect
    looks = []
    for icon in (0, 3, ALL_REWARD_ICON_PATHS[0]):
        monkeypatch.setattr(settings, 'get_player_icon', lambda icon=icon: icon)
        menu.screen.fill((0, 0, 0))
        menu._draw_profile_button()
        looks.append(pygame.transform.average_color(menu.screen, rect))
    assert all(sum(look[:3]) > 0 for look in looks)
    assert len({tuple(look) for look in looks}) == 3      # Three different pictures


def test_main_py_lets_the_menu_go():
    with open(os.path.join(ROOT, 'main.py'), encoding='utf-8') as f:
        source = f.read()
    run = source.index("action = main_menu.run()")
    released = source.index("main_menu = None", run)
    next_menu = source.find("MainMenu(screen)", run)
    assert next_menu == -1 or released < next_menu
