# -*- coding: utf-8 -*-
"""
Tests: right-click context menu on the army composition unit icons.

Before this change, building a partial selection out of a garrison required
CTRL + left-click on each icon - the only keyboard-free path was "all or one".
Right-clicking a unit icon now opens a small drop-down offering Select /
Add to Group / Remove from Group / Cancel.

These tests pin:
  - which options appear, given the current selection
  - what each option does to game.selected_army_units
  - the modal contract (every click consumed, menu always closes)
  - placement (prefers down-right, flips up rather than running off screen)
  - staleness (a menu pointing at a garrison that is gone closes itself)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    g = Game()
    g.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 'Normal'],
    })
    g.game_state.phase = 'playing'
    g.game_state.turn_phase = 'planning'
    g.game_state.current_player = 0
    return g


@pytest.fixture
def strip(game):
    """
    Open the composition strip on a 3-unit garrison and fake the icon rects.

    Returns (territory, [unit_id, ...]). The rects stand in for the ones
    draw_army_composition_ui() normally builds, so these tests don't depend on
    the panel's pixel layout.
    """
    import pygame

    territory = sorted(game.game_state.territory_owners.keys())[0]
    game.game_state.territory_garrisons.clear()
    game.game_state.territory_owners[territory] = 0
    game.game_state.add_garrison(territory, 0, unmoved=3)

    units = game.game_state.territory_garrisons[territory][0]['units']
    unit_ids = [u['id'] for u in units]

    game.show_army_composition = True
    game.army_composition_territory = territory
    game.army_composition_player = 0
    game.selected_army_units = []

    # Three 45px icons in a row, inside the bottom UI
    from main import BOTTOM_UI_Y
    game.army_composition_buttons = [
        (pygame.Rect(900 + i * 50, BOTTOM_UI_Y + 30, 45, 45), uid)
        for i, uid in enumerate(unit_ids)
    ]
    return territory, unit_ids


def _icon_pos(game, index):
    """Center of the icon at `index` in the faked strip."""
    return game.army_composition_buttons[index][0].center


def _labels(game):
    return [label for _, label in game.unit_context_menu['items']]


def _click_label(game, label):
    """Draw the menu (which builds the hit rects), then click the named item."""
    game.draw_unit_context_menu()
    for rect, action_id in game.unit_context_menu_rects:
        idx = [a for a, _ in game.unit_context_menu['items']].index(action_id)
        if game.unit_context_menu['items'][idx][1] == label:
            return game.handle_unit_context_menu_click(rect.center)
    raise AssertionError('no menu item labelled %r (have %r)' % (label, _labels(game)))


# ---------------------------------------------------------------------------
# Which options appear
# ---------------------------------------------------------------------------

def test_no_other_unit_selected_offers_select_and_cancel(game, strip):
    _, unit_ids = strip
    assert game.handle_unit_context_menu_right_click(_icon_pos(game, 0)) is True
    assert _labels(game) == ['Select', 'Cancel']


def test_only_this_unit_selected_still_offers_two_options(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))
    # The clicked unit is not an "other" unit, so no group option
    assert _labels(game) == ['Select', 'Cancel']


def test_other_unit_selected_offers_add_to_group(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    assert _labels(game) == ['Select', 'Add to Group', 'Cancel']


def test_already_in_group_offers_remove_from_group(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0], unit_ids[1]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    assert _labels(game) == ['Select', 'Remove from Group', 'Cancel']


# ---------------------------------------------------------------------------
# What the options do
# ---------------------------------------------------------------------------

def test_select_replaces_the_whole_selection(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0], unit_ids[1]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 2))
    _click_label(game, 'Select')
    assert game.selected_army_units == [unit_ids[2]]
    assert game.unit_context_menu is None


def test_add_to_group_extends_the_selection(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    _click_label(game, 'Add to Group')
    assert game.selected_army_units == [unit_ids[0], unit_ids[1]]
    assert game.unit_context_menu is None


def test_remove_from_group_drops_only_that_unit(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0], unit_ids[1], unit_ids[2]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    _click_label(game, 'Remove from Group')
    assert game.selected_army_units == [unit_ids[0], unit_ids[2]]


def test_cancel_closes_without_changing_the_selection(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    _click_label(game, 'Cancel')
    assert game.selected_army_units == [unit_ids[0]]
    assert game.unit_context_menu is None


# ---------------------------------------------------------------------------
# Modal contract
# ---------------------------------------------------------------------------

def test_click_outside_closes_with_no_action_and_is_consumed(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    game.draw_unit_context_menu()

    assert game.handle_unit_context_menu_click((5, 5)) is True
    assert game.unit_context_menu is None
    assert game.selected_army_units == [unit_ids[0]]


def test_left_click_chain_routes_to_the_menu_while_open(game, strip):
    """Priority 0: nothing underneath the drop-down may see the click."""
    _, unit_ids = strip
    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))
    game.draw_unit_context_menu()

    # A click aimed at the map must be swallowed by the menu instead
    assert game.mouse.handle_left_click((200, 300)) is True
    assert game.unit_context_menu is None


def test_second_right_click_dismisses_the_menu(game, strip):
    strip
    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))
    assert game.unit_context_menu is not None

    # Right-click again inside the bottom UI: closes and consumes
    assert game.handle_unit_context_menu_right_click(_icon_pos(game, 1)) is True
    assert game.unit_context_menu is None


def test_right_click_on_the_map_while_open_only_dismisses(game, strip):
    """
    A dismissing right-click must not also issue a movement order.

    Same contract as a left-click outside the menu: close, no action, consumed.
    """
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]

    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))
    assert game.handle_unit_context_menu_right_click((400, 300)) is True
    assert game.unit_context_menu is None
    # Selection untouched - the order handler never ran
    assert game.selected_army_units == [unit_ids[0]]


def test_right_click_on_empty_strip_space_does_not_open(game, strip):
    from main import BOTTOM_UI_Y
    strip
    assert game.handle_unit_context_menu_right_click((100, BOTTOM_UI_Y + 10)) is False
    assert game.unit_context_menu is None


def test_no_menu_when_composition_strip_is_closed(game, strip):
    strip
    game.show_army_composition = False
    assert game.handle_unit_context_menu_right_click(_icon_pos(game, 0)) is False
    assert game.unit_context_menu is None


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

def test_menu_opens_down_and_right_when_it_fits(game, strip):
    """Default placement on a normal first-row icon: down and to the right."""
    from main import WINDOW_HEIGHT
    strip

    anchor = game.army_composition_buttons[0][0]
    game.handle_unit_context_menu_right_click(anchor.center)

    rect = game._get_unit_context_menu_rect()
    assert rect.top >= anchor.top      # opens downward
    assert rect.left >= anchor.left    # opens rightward
    assert rect.bottom <= WINDOW_HEIGHT


def test_menu_flips_up_rather_than_running_off_the_bottom(game, strip):
    import pygame
    from main import WINDOW_HEIGHT
    _, unit_ids = strip

    # Anchor near the bottom edge: downward placement would be clipped
    anchor = pygame.Rect(900, WINDOW_HEIGHT - 50, 45, 45)
    game.army_composition_buttons = [(anchor, unit_ids[0])]
    game.selected_army_units = [unit_ids[1]]  # force the 3-item menu
    game.handle_unit_context_menu_right_click(anchor.center)

    rect = game._get_unit_context_menu_rect()
    assert rect.bottom <= WINDOW_HEIGHT
    assert rect.bottom <= anchor.bottom  # flipped upward


def test_menu_stays_on_screen_near_the_right_edge(game, strip):
    import pygame
    from main import WINDOW_WIDTH, WINDOW_HEIGHT
    _, unit_ids = strip

    anchor = pygame.Rect(WINDOW_WIDTH - 50, WINDOW_HEIGHT - 200, 45, 45)
    game.army_composition_buttons = [(anchor, unit_ids[0])]
    game.handle_unit_context_menu_right_click(anchor.center)

    rect = game._get_unit_context_menu_rect()
    assert rect.right <= WINDOW_WIDTH
    assert rect.left >= 0


def test_item_rects_are_inside_the_panel_and_match_the_options(game, strip):
    _, unit_ids = strip
    game.selected_army_units = [unit_ids[0]]
    game.handle_unit_context_menu_right_click(_icon_pos(game, 1))
    game.draw_unit_context_menu()

    panel = game._get_unit_context_menu_rect()
    assert len(game.unit_context_menu_rects) == 3
    for rect, _action in game.unit_context_menu_rects:
        assert panel.contains(rect)


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

def test_menu_closes_when_its_unit_leaves_the_garrison(game, strip):
    territory, unit_ids = strip
    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))

    units = game.game_state.territory_garrisons[territory][0]['units']
    game.game_state.territory_garrisons[territory][0]['units'] = [
        u for u in units if u['id'] != unit_ids[0]
    ]

    game.draw_unit_context_menu()
    assert game.unit_context_menu is None
    assert game.unit_context_menu_rects == []


def test_menu_closes_when_the_strip_closes(game, strip):
    strip
    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))
    game.show_army_composition = False

    game.draw_unit_context_menu()
    assert game.unit_context_menu is None


def test_menu_closes_when_a_different_garrison_is_opened(game, strip):
    territory, _unit_ids = strip
    game.handle_unit_context_menu_right_click(_icon_pos(game, 0))

    other = [t for t in sorted(game.game_state.territory_owners.keys()) if t != territory][0]
    game.army_composition_territory = other

    game.draw_unit_context_menu()
    assert game.unit_context_menu is None


# ---------------------------------------------------------------------------
# Draw path / hover suppression
# ---------------------------------------------------------------------------

def test_strip_hover_is_suppressed_beneath_the_open_menu(game, strip):
    """
    Nothing under the drop-down may light up or raise a tooltip.

    The menu overlaps the anchor icon's corner by a few pixels, which gives a
    point that is inside both - hover there must resolve to the menu only.
    """
    territory, _unit_ids = strip

    # Use the real icon rects the panel builds, not the faked ones
    game.draw_army_composition_ui()
    assert game.army_composition_buttons, 'composition strip drew no unit icons'

    icon_rect = game.army_composition_buttons[0][0]

    # Baseline: hovering the icon with no menu open arms the unit tooltip
    game.mouse_pos = icon_rect.center
    game.draw_army_composition_ui()
    assert game.hover_target_button is not None
    assert game.hover_target_button[0] == 'army_unit_tooltip'

    # Open the menu on that icon and hover the overlapping corner
    game.handle_unit_context_menu_right_click(icon_rect.center)
    game.draw_unit_context_menu()
    menu_rect = game._get_unit_context_menu_rect()

    overlap_point = (menu_rect.left + 1, menu_rect.top + 1)
    assert icon_rect.collidepoint(overlap_point), 'menu should overlap its anchor icon'

    game.mouse_pos = overlap_point
    game.draw_army_composition_ui()
    assert game.hover_target_button is None


def test_full_bottom_ui_draws_with_the_menu_open(game, strip):
    """The whole bottom panel still renders while the drop-down is up."""
    strip
    game.draw_army_composition_ui()
    game.handle_unit_context_menu_right_click(game.army_composition_buttons[0][0].center)

    game.draw_bottom_ui()
    game.draw_unit_context_menu()

    assert game.unit_context_menu is not None
    assert len(game.unit_context_menu_rects) == 2
