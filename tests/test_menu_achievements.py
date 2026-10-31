# -*- coding: utf-8 -*-
"""
The main menu's Achievements window - the trophy wall (achievement_panel.py, drawn with
ui/menu_kit.py; the "Menu Glow-up", phase 2):

- layout at 720p-1440p: summary, chips, search, wall, card and Close inside the window and
  apart; every achievement's card fits, its name on at most two lines
- the wall: grouped by category in CATEGORIES order, earned first then the rest in the
  game's own order; the chips' counts; a chip filters; the search matches names and
  descriptions, starts from any key, Esc clears it before Esc closes the window
- medals: a click keeps one in the card, hovering one shows it; the wheel scrolls the wall
  (clamped); opening again starts fresh (All, no search, the top, the closest one chosen)
- feedback: chips, medals and Close lit on hover, brighter on their click flash
- the drop: no clicks until landed; opening one window while another fades ends that one
- performance: a later MainMenu decodes no achievement icon; no smoothscale in steady frames

Uses the achievements as this PC's config.json has them (never saved).
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
    """Counts click sounds; never saves."""
    from global_sound import sound_manager
    from settings_manager import settings
    counts = {'clicks': 0}
    monkeypatch.setattr(sound_manager, 'play_ui_click',
                        lambda *a, **k: counts.__setitem__('clicks', counts['clicks'] + 1))
    monkeypatch.setattr(settings, 'save', lambda *a, **k: None)
    yield counts


def make_menu(size=(1600, 900)):
    """A MainMenu at `size` with the Achievements window open and landed."""
    import main_menu
    if pygame.display.get_surface().get_size() != size:
        pygame.display.set_mode(size)
    menu = main_menu.MainMenu(pygame.display.get_surface())
    menu._open_achievements()
    menu.achievements_panel.anim.finish()
    return menu


def key(menu, k, unicode='', mod=0):
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=unicode))
    menu.handle_events()


def type_text(menu, text):
    for ch in text:
        key(menu, pygame.key.key_code(ch) if ch.isalpha() else pygame.K_SPACE, unicode=ch)


def brightness(surface, rect):
    r, g, b = pygame.transform.average_color(surface, rect)[:3]
    return r + g + b


# ------------------------------------------------------------------------------ layout

@pytest.mark.parametrize('size', RESOLUTIONS)
def test_layout_fits(size):
    menu = make_menu(size)
    panel = menu.achievements_panel
    kit = menu.menu_kit
    window = panel.rect()
    assert pygame.Rect((0, 0), size).contains(window)
    assert window.y - kit.banner_overhang() >= 0
    L = panel.layout()
    board = pygame.Rect(0, 0, *window.size).inflate(-2 * kit.border(), -2 * kit.border())
    for name in ('summary', 'search', 'wall', 'card', 'close'):
        assert board.contains(L[name]), name
    chips = list(L['chips'].values())
    for i, chip in enumerate(chips):
        assert board.contains(chip)
        assert not chip.colliderect(L['search']), "a chip runs into the search box"
        for other in chips[i + 1:]:
            assert not chip.colliderect(other)
    # The wall's scrollbar sits between the wall and the card
    bar_right = L['wall'].right + kit.px(8) + max(2, kit.px(6))
    assert bar_right <= L['card'].left
    assert L['wall'].bottom <= L['close'].top and L['card'].bottom <= L['close'].top
    assert not L['summary'].colliderect(L['search'])
    # The summary's two lines fit beside the bar
    assert panel._summary_surface().get_width() <= L['summary'].w
    # Every achievement's card holds its content; names on at most two lines
    inner = L['card'].w - 2 * kit.px(22)
    for a in panel.achievements:
        panel._card(a['id'])
        assert panel.card_content_bottom[a['id']] <= L['card'].h, a['id']
        lines = kit.wrap(a['name'], 'card_name', inner, max_lines=2)
        assert " ".join(lines) == a['name'], a['name']        # Whole, not cut short
    # Every medal of the wall lies inside it, across
    for _id, cell in panel.grid()['cells']:
        assert cell.left >= 0 and cell.right <= L['wall'].w


# ------------------------------------------------------------------------------ the wall

def test_groups_order_and_counts():
    from achievement_manager import achievement_manager, CATEGORIES
    menu = make_menu()
    panel = menu.achievements_panel
    every = achievement_manager.get_all_achievements()
    groups = panel.groups()
    assert [cat for cat, _l, _items in groups] == [c for c in CATEGORIES if any(a['category'] == c for a in every)]
    for cat, _label, items in groups:
        defined = [a['id'] for a in every if a['category'] == cat]
        expected = ([i for i in defined if achievement_manager.is_earned(i)]
                    + [i for i in defined if not achievement_manager.is_earned(i)])
        assert [a['id'] for a in items] == expected, cat
    counts = dict((k, c) for k, _label, c in panel.chip_counts())
    assert counts['all'] == f"{len(achievement_manager.earned)}/{len(every)}"


def test_chip_filters(quiet):
    menu = make_menu()
    panel = menu.achievements_panel
    menu.handle_click(panel.part_rect(('chip', 'campaign')).center)
    assert panel.category == 'campaign'
    assert {cat for cat, _l, _i in panel.groups()} == {'campaign'}
    assert all(panel.by_id[cid]['category'] == 'campaign' for cid, _c in panel.grid()['cells'])
    assert panel.by_id[panel.selected]['category'] == 'campaign'   # The card follows the filter
    assert quiet['clicks'] == 1
    menu.handle_click(panel.part_rect(('chip', 'campaign')).center)  # Already chosen
    assert quiet['clicks'] == 1
    menu.handle_click(panel.part_rect(('chip', 'all')).center)
    assert panel.category == 'all'


def test_search_starts_anywhere_and_esc_clears_first():
    menu = make_menu()
    panel = menu.achievements_panel
    type_text(menu, 'level')
    assert panel.search_active and panel.search_text == 'level'
    shown = [panel.by_id[cid] for cid, _c in panel.grid()['cells']]
    assert shown and all('level' in (a['name'] + a['description']).lower() for a in shown)
    key(menu, pygame.K_BACKSPACE)
    assert panel.search_text == 'leve'
    key(menu, pygame.K_ESCAPE, unicode='\x1b')
    assert panel.search_text == '' and menu.show_achievements      # Cleared, still open
    key(menu, pygame.K_ESCAPE, unicode='\x1b')
    assert not menu.show_achievements                                # Then closed


def test_search_matches_descriptions_and_nothing():
    menu = make_menu()
    panel = menu.achievements_panel
    target = next(a for a in panel.achievements if a['description'])
    word = max(target['description'].split(), key=len).strip('.,:;').lower()
    type_text(menu, word[:12])
    assert any(cid == target['id'] for cid, _c in panel.grid()['cells'])
    panel.search_text = 'zzzz no such thing'
    panel._after_search()
    assert panel.grid()['cells'] == []
    menu.render()
    menu.render()         # The "No achievement matches" line, nothing raises


def test_search_text_is_capped():
    menu = make_menu()
    panel = menu.achievements_panel
    type_text(menu, 'a' * 40)
    assert len(panel.search_text) == 30


def test_medal_click_keeps_it_and_hover_shows_it(quiet):
    menu = make_menu()
    panel = menu.achievements_panel
    cells = panel.grid()['cells']
    first, second = cells[0][0], cells[1][0]
    menu.handle_click(panel.medal_rect(second).center)
    assert panel.selected == second and quiet['clicks'] == 1
    panel.update_hover(panel.medal_rect(first).center)
    assert panel.hover == ('medal', first)
    panel.update_hover((0, 0))
    assert panel.hover is None and panel.selected == second


def test_wheel_scrolls_the_wall_clamped():
    menu = make_menu()
    panel = menu.achievements_panel
    view = panel.grid()['view']
    if not view.scrollable:
        pytest.skip("the wall fits without scrolling at this size")
    before = panel.static_key()
    for _ in range(3):
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=5, pos=(800, 450)))
        menu.handle_events()
    assert view.offset > 0 and panel.static_key() != before
    for _ in range(200):
        panel.wheel(-1)
    assert view.offset == view.max_offset
    for _ in range(200):
        panel.wheel(+1)
    assert view.offset == 0


def test_opening_again_starts_fresh():
    menu = make_menu()
    panel = menu.achievements_panel
    panel.set_category('conquest')
    panel.search_text = 'x'
    menu._close_achievements()
    panel.anim.finish()
    menu._open_achievements()
    assert panel.category == 'all' and panel.search_text == '' and not panel.search_active
    assert panel.grid()['view'].offset == 0
    if panel.closest:
        assert panel.selected == panel.closest['id']


# ------------------------------------------------------------------------------ feedback

@pytest.mark.parametrize('kind', ['chip', 'close', 'medal'])
def test_hover_then_flash_brighter(kind):
    menu = make_menu()
    panel = menu.achievements_panel
    if kind == 'chip':
        element = ('chip', 'training')
    elif kind == 'close':
        element = ('button', 'close')
    else:
        # A medal that is not the chosen one (its ring would light it anyway)
        cid = next(c for c, _cell in panel.grid()['cells'] if c != panel.selected)
        element = ('medal', cid)
    rect = panel.part_rect(element)
    probe = rect.inflate(-rect.w // 3, -rect.h // 3)
    panel.update_hover((1, 1))
    menu.render()
    normal = brightness(menu.screen, probe)
    panel.update_hover(rect.center)
    menu.render()
    hover = brightness(menu.screen, probe)
    panel._flash = (element, pygame.time.get_ticks() + 10000)
    menu.render()
    flash = brightness(menu.screen, probe)
    if kind == 'medal':
        assert normal < hover <= flash, (element, normal, hover, flash)
    else:
        assert normal < hover < flash, (element, normal, hover, flash)


# ------------------------------------------------------------------------------ the drop

def test_no_clicks_until_landed(quiet):
    menu = make_menu()
    panel = menu.achievements_panel
    menu._close_achievements()
    panel.anim.finish()
    menu._open_achievements()
    panel.anim.progress = 0.7
    menu.handle_click(panel.part_rect(('chip', 'general')).center)
    assert panel.category == 'all' and quiet['clicks'] == 0


def test_opening_while_the_other_window_fades_out():
    menu = make_menu()
    menu._close_achievements()
    menu.achievements_panel.anim.progress = 0.5      # Still fading out
    menu._open_options()
    assert not menu.achievements_panel.anim.visible
    menu.options_panel.anim.finish()
    menu.render()
    menu.render()
    menu._close_options()
    menu.options_panel.anim.progress = 0.5
    menu._open_achievements()
    assert not menu.options_panel.anim.visible and menu.show_achievements


# ------------------------------------------------------------------------------ performance

def test_a_later_main_menu_decodes_no_achievement_icon(monkeypatch):
    import main_menu
    from achievement_manager import ACHIEVEMENTS, ALL_REWARD_ICON_PATHS
    main_menu.MainMenu(pygame.display.get_surface())      # Builds them (if not built yet)
    wall_only = {a['icon'] for a in ACHIEVEMENTS} - set(ALL_REWARD_ICON_PATHS)
    loads = []
    real = pygame.image.load
    monkeypatch.setattr(pygame.image, 'load', lambda path, *a: loads.append(path) or real(path, *a))
    main_menu.MainMenu(pygame.display.get_surface())
    assert [p for p in loads if p in wall_only] == []


def test_no_smoothscale_in_steady_frames(monkeypatch):
    menu = make_menu()
    panel = menu.achievements_panel

    def everything():
        for chip in panel.layout()['chips']:
            panel.update_hover(panel.part_rect(('chip', chip)).center)
            menu.render()
        for cid, _cell in panel.grid()['cells']:
            rect = panel.medal_rect(cid)
            if panel.layout()['wall'].move(panel.rect().topleft).contains(rect):
                panel.update_hover(rect.center)
                menu.render()
    everything()                                       # Warm: cards for the hovered medals
    calls = []
    real = pygame.transform.smoothscale
    monkeypatch.setattr(pygame.transform, 'smoothscale', lambda *a, **k: calls.append(1) or real(*a, **k))
    everything()
    assert calls == []
