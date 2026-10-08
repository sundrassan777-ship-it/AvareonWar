# -*- coding: utf-8 -*-
"""
Sidebar overhaul P5 — hover / click-flash audit.

Every clickable control in the right sidebar must look different when hovered and
when flashed (clicked_element) than when idle. Each test renders the control three
times on a blacked-out screen — idle, mouse over it, flash key set with the mouse
away — and compares the pixels inside its rect.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERO = 'Aidam Narn'


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture
def game(pygame_display):
    from main import Game
    from game_state import MovementOrder
    g = Game()
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
    g.apply_display_settings(1600, 900, False)
    gs = g.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    g.tutorial_mission = None
    territories = list(g.scaled_polygons)
    for i, t in enumerate(territories):
        gs.territory_owners[t] = i % 2
    own = [t for t in territories if gs.territory_owners[t] == 0]
    enemy = [t for t in territories if gs.territory_owners[t] == 1]
    # One active hero (Heroes tab) and one queued attack (Action Queue tab)
    gs.heroes.setdefault(0, {})[HERO] = {'keep_territory': own[0], 'keep_plot': 0, 'status': 'active'}
    gs.hero_ownership[0].add(HERO)
    garrison = gs.territory_garrisons.setdefault(own[1], {}).setdefault(0, {'unmoved': 3, 'moved': 0})
    garrison.setdefault('units', []).extend(
        {'id': f'u{k}', 'status': 'ready', 'order': None, 'type': 'Swordsman', 'xp': 0, 'level': 0}
        for k in range(3))
    gs.movement_orders.append(MovementOrder(own[1], enemy[0], 3, 0, unit_ids=['u0', 'u1', 'u2']))
    g.mouse_pos = (0, 0)
    g.clicked_element = None
    return g


def _render(game, tab, mouse_pos=(0, 0), clicked=None):
    game.game_state.active_sidebar_tab = tab
    game.mouse_pos = mouse_pos
    game.clicked_element = clicked
    game.screen.fill((0, 0, 0))
    game.draw_order_sidebar()


def _pixels(game, rect):
    import pygame
    return pygame.image.tobytes(game.screen.subsurface(rect.clip(game.screen.get_rect())), 'RGB')


def _rect_of(game, control):
    """(rect, flash key or None) of one control, read after a render."""
    if control == 'bookmark':
        return game.sidebar_tab_buttons['heroes'], ('sidebar_tab', 'heroes')
    if control == 'toggle':
        return game.sidebar_toggle_button, ('sidebar_toggle', 'toggle')
    if control == 'tech_tile':
        return game.technology_buttons['tech_0_0'], ('technology_button', 'tech_0_0')
    if control == 'order_card':
        # Hover only: the card body has no click action yet
        return game.order_card_rects[0][0], None
    if control == 'cancel_order':
        rect, order, _ = game.order_cancel_buttons[0]
        return rect, ('sidebar_cancel_order', order.order_id)
    if control == 'cancel_all':
        return game.cancel_all_button, ('sidebar_cancel_all', None)
    if control == 'hero_card':
        return game.hero_selection_buttons[HERO], ('sidebar_hero_card', HERO)
    if control == 'hero_ability':
        return game.sidebar_hero_ability_buttons[(HERO, 0)], ('sidebar_hero_ability', (HERO, 0))
    raise AssertionError(control)


TAB_OF = {'bookmark': 'technology', 'toggle': 'technology', 'tech_tile': 'technology',
          'order_card': 'action_queue', 'cancel_order': 'action_queue', 'cancel_all': 'action_queue',
          'hero_card': 'heroes', 'hero_ability': 'heroes'}


@pytest.mark.parametrize('control', list(TAB_OF))
def test_control_highlights_on_hover_and_flashes_on_click(game, control):
    tab = TAB_OF[control]
    _render(game, tab)
    rect, flash_key = _rect_of(game, control)
    rect = rect.copy()
    # Hover point: the hero card's own highlight shows off its ability icons / portrait
    point = rect.center
    if control == 'hero_card':
        point = (game.hero_portrait_rects[HERO].right + 4, game.hero_portrait_rects[HERO].centery)
    elif control == 'order_card':
        point = (rect.centerx, rect.top + 6)   # the header, clear of the Cancel Order button

    _render(game, tab)
    idle = _pixels(game, rect)
    _render(game, tab, mouse_pos=point)
    hovered = _pixels(game, rect)
    assert hovered != idle, f"{control}: no hover highlight"

    if flash_key is not None:
        _render(game, tab, clicked=flash_key)
        flashed = _pixels(game, rect)
        assert flashed != idle, f"{control}: no click flash"


def test_tech_click_sets_flash(game):
    _render(game, 'technology')
    rect = game.technology_buttons['tech_0_0']
    game.mouse.handle_left_click(rect.center)
    assert game.clicked_element == ('technology_button', 'tech_0_0')
