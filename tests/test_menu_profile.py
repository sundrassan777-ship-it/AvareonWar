# -*- coding: utf-8 -*-
"""
The main menu's Profile window - the player card (ui/profile_panel.py, drawn with
ui/menu_kit.py; the "Menu Glow-up", phase 3):

- layout at 720p-1440p: card, titles, portraits and buttons inside the window and apart;
  the card's content inside the card; every title fits its chip
- win rates: games played never fewer than wins (the older profile's 210 wins / 8 games)
- choices: an unlocked title / portrait is chosen (one click sound), a locked one is not
  (its hover tooltip says what unlocks it), "No title" clears the title
- the name: typed on the card (Backspace, at most 20), Enter ends the typing and then
  saves, Esc ends the typing and then cancels; a Steam name is not editable
- Save writes the choices, Cancel drops them; View leaves for the Achievements window and
  comes back with the choices as they were left
- feedback: buttons, View, titles and portraits lit on hover, brighter on the flash
- the drop: no clicks until landed; performance: no smoothscale in steady frames

Settings are never written (settings.save stubbed) and restored afterwards.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.quit()
    pygame.display.init()
    pygame.display.set_mode((1600, 900))
    yield
    pygame.display.set_mode((1600, 900))


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """Counts click sounds and saves; restores the in-memory settings; no Steam name.
    A known profile: one achievement's title and one's portrait earned, everything else
    locked, so the choices below have both kinds on any PC (they used to follow this PC's
    config.json, and on a fresh profile they skipped or checked only the locked side)."""
    from achievement_manager import ACHIEVEMENTS, achievement_manager
    from global_sound import sound_manager
    from settings_manager import settings
    from steam_integration import steam_manager
    # Every achievement that grants the first title / the first portrait (one reward can
    # come from several, and the panel reads one of them)
    wanted = {(kind, next(a['reward_id'] for a in ACHIEVEMENTS if a.get('reward_type') == kind))
              for kind in ('title', 'icon')}
    earned = {a['id']: '2026-10-01T12:00:00' for a in ACHIEVEMENTS
              if {(a.get('reward_type'), a.get('reward_id')), (a.get('reward_type_2'), a.get('reward_id_2'))} & wanted}
    before = dict(settings.settings)
    settings.settings['earned_achievements'] = earned   # the panel reloads the manager from here
    achievement_manager.load()
    counts = {'clicks': 0, 'saves': 0}
    monkeypatch.setattr(sound_manager, 'play_ui_click',
                        lambda *a, **k: counts.__setitem__('clicks', counts['clicks'] + 1))
    monkeypatch.setattr(settings, 'save', lambda *a, **k: counts.__setitem__('saves', counts['saves'] + 1))
    monkeypatch.setattr(type(steam_manager), 'is_available', property(lambda self: False), raising=False)
    yield counts
    settings.settings.clear()
    settings.settings.update(before)
    achievement_manager.load()


def make_menu(size=(1600, 900)):
    """A MainMenu at `size` with the Profile window open and landed."""
    import main_menu
    if pygame.display.get_surface().get_size() != size:
        pygame.display.set_mode(size)
    menu = main_menu.MainMenu(pygame.display.get_surface())
    menu._open_profile()
    menu.profile_panel.anim.finish()
    return menu


def click(menu, element):
    menu.handle_click(menu.profile_panel.part_rect(element).center)


def key(menu, k, unicode=''):
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=unicode))
    menu.handle_events()


def brightness(surface, rect):
    r, g, b = pygame.transform.average_color(surface, rect)[:3]
    return r + g + b


# ------------------------------------------------------------------------------ layout

@pytest.mark.parametrize('size', RESOLUTIONS)
def test_layout_fits(size):
    menu = make_menu(size)
    panel = menu.profile_panel
    kit = menu.menu_kit
    window = panel.rect()
    assert pygame.Rect((0, 0), size).contains(window)
    L = panel.layout()
    board = pygame.Rect(0, 0, *window.size).inflate(-2 * kit.border(), -2 * kit.border())
    card = L['card']
    assert board.contains(card)
    for name in ('portrait', 'name', 'title_line', 'level', 'ach', 'view'):
        assert card.contains(L[name]), name
    for tile in L['tiles']:
        assert card.contains(tile)
    pickers = list(L['titles'].values()) + list(L['portraits'].values()) + [L['no_title']]
    for r in pickers:
        assert board.contains(r) and not r.colliderect(card)
        assert r.bottom <= L['footer_top']
    rects = list(L['titles'].values()) + list(L['portraits'].values())
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not a.colliderect(b)
    assert not L['cancel'].colliderect(L['save'])
    assert L['card'].bottom <= L['footer_top']
    # Every title fits its chip unshortened
    room = next(iter(L['titles'].values())).w - kit.px(20) - kit.px(14)
    for title, _u, _a in panel.titles:
        assert kit.font('title_chip').size(title)[0] <= room, title


def test_win_rate_never_above_100_percent():
    from ui.profile_panel import win_line
    assert win_line(210, 8) == (210, "210 played · 100%")      # The older profile
    assert win_line(3, 10) == (10, "10 played · 30%")
    assert win_line(0, 0)[1].endswith("–")


# ------------------------------------------------------------------------------ choices

def test_titles(quiet):
    menu = make_menu()
    panel = menu.profile_panel
    unlocked = [t for t, u, _a in panel.titles if u]
    locked = [t for t, u, _a in panel.titles if not u]
    if locked:
        before = menu.temp_selected_title
        click(menu, ('title', locked[0]))
        assert menu.temp_selected_title == before and quiet['clicks'] == 0
    if unlocked:
        menu.temp_selected_title = None
        click(menu, ('title', unlocked[0]))
        assert menu.temp_selected_title == unlocked[0] and quiet['clicks'] == 1
        click(menu, ('title', unlocked[0]))             # Already chosen: no sound
        assert quiet['clicks'] == 1
        click(menu, ('no_title',))
        assert menu.temp_selected_title is None


def test_portraits(quiet):
    menu = make_menu()
    panel = menu.profile_panel
    menu.temp_player_icon = 0
    click(menu, ('portrait', 3))
    assert menu.temp_player_icon == 3
    click(menu, ('portrait', 0))
    assert menu.temp_player_icon == 0
    locked = [p for p, _n, u, _a in panel.rewards if not u]
    if locked:
        click(menu, ('portrait', locked[0]))
        assert menu.temp_player_icon == 0
    unlocked = [p for p, _n, u, _a in panel.rewards if u]
    if unlocked:
        click(menu, ('portrait', unlocked[0]))
        assert menu.temp_player_icon == unlocked[0]
        assert panel.portrait_path(unlocked[0]) == unlocked[0]


def test_locked_hover_shows_what_unlocks_it(monkeypatch):
    menu = make_menu()
    panel = menu.profile_panel
    shown = []
    real = menu.menu_kit.tooltip
    monkeypatch.setattr(menu.menu_kit, 'tooltip', lambda title, lines: shown.append((title, lines)) or real(title, lines))
    locked = [(p, a) for p, _n, u, a in panel.rewards if not u and a is not None]
    if not locked:
        pytest.skip("every reward portrait is unlocked here")
    path, ach = locked[0]
    panel.update_hover(panel.part_rect(('portrait', path)).center)
    menu.render()
    assert shown and shown[-1][1][0] == f"Unlock: {ach['name']}"


# ------------------------------------------------------------------------------ the name

def test_typing_the_name(quiet):
    from settings_manager import settings
    menu = make_menu()
    panel = menu.profile_panel
    menu.temp_player_name = "Weel"
    click(menu, ('name',))
    assert panel.editing
    key(menu, pygame.K_BACKSPACE)
    for ch in "ar":
        key(menu, pygame.key.key_code(ch), ch)
    assert menu.temp_player_name == "Weear"
    for ch in "x" * 30:
        key(menu, pygame.K_x, ch)
    assert len(menu.temp_player_name) == 20
    key(menu, pygame.K_RETURN, '\r')                    # Ends the typing, saves nothing
    assert not panel.editing and menu.show_profile and quiet['saves'] == 0
    key(menu, pygame.K_RETURN, '\r')                    # Now Enter saves
    assert not menu.show_profile and quiet['saves'] == 1
    assert settings.get_player_name() == menu.temp_player_name


def test_esc_ends_typing_then_cancels(quiet):
    from settings_manager import settings
    menu = make_menu()
    panel = menu.profile_panel
    saved = settings.get_player_name()
    click(menu, ('name',))
    key(menu, pygame.K_z, 'z')
    key(menu, pygame.K_ESCAPE, '\x1b')
    assert not panel.editing and menu.show_profile
    key(menu, pygame.K_ESCAPE, '\x1b')
    assert not menu.show_profile and quiet['saves'] == 0 and settings.get_player_name() == saved
    menu._open_profile()
    assert menu.temp_player_name == saved               # The typing was dropped


def test_steam_name_is_not_editable():
    menu = make_menu()
    menu._steam_name_active = True
    click(menu, ('name',))
    assert not menu.profile_panel.editing
    menu.render()
    menu.render()                                       # The "Steam" tag, nothing raises


# ------------------------------------------------------------------------------ save / cancel / view

def test_save_and_cancel(quiet):
    from settings_manager import settings
    menu = make_menu()
    menu.temp_player_icon = 5
    click(menu, ('button', 'save'))
    assert settings.get_player_icon() == 5 and quiet['saves'] == 1 and not menu.show_profile
    menu._open_profile()
    menu.profile_panel.anim.finish()
    menu.temp_player_icon = 2
    click(menu, ('button', 'cancel'))
    assert settings.get_player_icon() == 5 and quiet['saves'] == 1
    menu._open_profile()
    assert menu.temp_player_icon == 5


def test_view_goes_to_achievements_and_comes_back():
    menu = make_menu()
    menu.temp_player_icon = 6                            # An unsaved choice
    click(menu, ('view',))
    assert not menu.show_profile
    for _ in range(80):                                  # The card leaves, Achievements drops in
        menu._update_options_animation(1 / 60)
    assert menu.show_achievements and menu.achievements_panel.anim.settled_open
    menu._close_achievements()
    for _ in range(80):
        menu._update_options_animation(1 / 60)
    assert menu.show_profile and menu.profile_panel.anim.settled_open
    assert menu.temp_player_icon == 6                    # As it was left


# ------------------------------------------------------------------------------ feedback

@pytest.mark.parametrize('which', ['save', 'cancel', 'view', 'title', 'hero'])
def test_hover_then_flash_brighter(which):
    menu = make_menu()
    panel = menu.profile_panel
    menu.temp_player_icon = 0
    menu.temp_selected_title = None
    if which in ('save', 'cancel'):
        element = ('button', which)
    elif which == 'view':
        element = ('view',)
    elif which == 'title':
        unlocked = [t for t, u, _a in panel.titles if u]
        if not unlocked:
            pytest.skip("no unlocked title here")
        element = ('title', unlocked[0])
    else:
        element = ('portrait', 4)
    rect = panel.part_rect(element)
    probe = rect.inflate(-rect.w // 4, -rect.h // 4)
    panel.update_hover((1, 1))
    menu.render()
    normal = brightness(menu.screen, probe)
    panel.update_hover(rect.center)
    menu.render()
    hover = brightness(menu.screen, probe)
    panel._flash = (element, pygame.time.get_ticks() + 10000)
    menu.render()
    flash = brightness(menu.screen, probe)
    if which == 'hero':
        assert normal < hover <= flash, (element, normal, hover, flash)
    else:
        assert normal < hover < flash, (element, normal, hover, flash)


# ------------------------------------------------------------------------------ the drop, performance

def test_no_clicks_until_landed(quiet):
    menu = make_menu()
    panel = menu.profile_panel
    menu._close_profile()
    panel.anim.finish()
    menu._open_profile()
    panel.anim.progress = 0.7
    menu.temp_player_icon = 0
    click(menu, ('portrait', 2))
    assert menu.temp_player_icon == 0 and quiet['clicks'] == 0


def test_no_smoothscale_in_steady_frames(monkeypatch):
    menu = make_menu()
    panel = menu.profile_panel

    def everything():
        for element in ([('title', t) for t, _u, _a in panel.titles]
                        + [('portrait', k) for k in panel.layout()['portraits']]
                        + [('view',), ('button', 'save'), ('button', 'cancel'), ('name',)]):
            panel.update_hover(panel.part_rect(element).center)
            menu.render()
    everything()                                        # Warm: tooltips, lit sprites
    calls = []
    real = pygame.transform.smoothscale
    monkeypatch.setattr(pygame.transform, 'smoothscale', lambda *a, **k: calls.append(1) or real(*a, **k))
    everything()
    assert calls == []
