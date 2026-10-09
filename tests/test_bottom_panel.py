# -*- coding: utf-8 -*-
"""
Tests: the bottom panel overhaul (rendering/bottom_panel_kit.py + main.py views).

Every section of the bottom panel is laid out as: centred headline, gold rule,
content. These tests pin the shared geometry and the End Turn section:

  - section_rect() stays inside the panel and between the pillars, at 1280x720,
    1600x900, 1920x1080 and 2560x1440 (panel 180 / 211 / 253 / 300 px tall)
  - End Turn: button + timer fit their section at every resolution, even with a
    player name that wraps; greyed/highlight rules; hover and click flash change
    pixels; the turn number follows sequential vs simultaneous mode
  - CampaignBTN inner tint colours the wood only, never the gold frame

Resolutions are forced by swapping main.set_display_mode for an offscreen surface:
the window size a test machine allows (and the dummy driver's 1600x900 cap) must
not decide what gets tested.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _make_game(width, height, monkeypatch):
    import pygame
    import main
    # Offscreen surface of exactly the requested size (see module docstring)
    monkeypatch.setattr(main, 'set_display_mode',
                        lambda size, fs=False, vs=False, force_reinit=False: (pygame.Surface(size), False))
    monkeypatch.setattr(main, '_set_app_icon', lambda: None)
    g = main.Game()
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
    g.apply_display_settings(width, height, False)
    gs = g.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    g.tutorial_mission = None
    g.mouse_pos = (0, 0)
    g.clicked_element = None
    return g


@pytest.fixture
def game(pygame_display, monkeypatch):
    return _make_game(1600, 900, monkeypatch)


@pytest.fixture(params=RESOLUTIONS, ids=lambda r: '%dx%d' % r)
def any_res_game(request, pygame_display, monkeypatch):
    return _make_game(request.param[0], request.param[1], monkeypatch)


def _panel(game):
    import pygame
    top, height = game.bottom_panel_geometry()
    return pygame.Rect(0, top, game.screen.get_width(), height)


# ===========================================================================
# Kit geometry
# ===========================================================================

class TestSectionRect:

    def test_inside_panel_and_clear_of_pillars(self, any_res_game):
        g = any_res_game
        kit = g.bottom_panel_kit
        panel = _panel(g)
        left_x, right_x = 400, 800
        rect = kit.section_rect(left_x, right_x)
        assert panel.contains(rect)
        half = g.separator_width // 2
        assert rect.left > left_x + half and rect.right < right_x - half
        # Below the wooden beam along the top edge
        assert rect.top >= panel.top + int(panel.height * 0.1)

    def test_leftmost_section_starts_at_screen_edge(self, game):
        rect = game.bottom_panel_kit.section_rect(None, 300)
        assert 0 < rect.left < 30

    def test_fonts_follow_panel_height_not_ui_scale(self, pygame_display, monkeypatch):
        """At 2560x1440 ui_scale is 1.6 but the panel only grows to 300 px (x1.42)."""
        big = _make_game(2560, 1440, monkeypatch)
        assert big.ui_scale > 1.5
        assert abs(big.bottom_panel_kit.scale - 300 / 211.0) < 0.01


# ===========================================================================
# End Turn section
# ===========================================================================

class TestEndTurnLayout:

    def test_button_and_timer_inside_section(self, any_res_game):
        g = any_res_game
        g.draw_bottom_ui()
        section = g._end_turn_section_rect()
        assert section.contains(g.end_turn_button)
        assert _panel(g).contains(g.end_turn_button)

    def test_long_name_still_fits_at_720p(self, pygame_display, monkeypatch):
        g = _make_game(1280, 720, monkeypatch)
        g.game_state.get_player_name = lambda i, include_title=True: 'Archduke Maximilian of Upper Rossenburg'
        g.draw_bottom_ui()
        section = g._end_turn_section_rect()
        assert section.contains(g.end_turn_button)

    def test_button_is_centred(self, game):
        game.draw_bottom_ui()
        section = game._end_turn_section_rect()
        assert abs(game.end_turn_button.centerx - section.centerx) <= 1


class TestEndTurnState:

    def test_normal(self, game):
        assert game._end_turn_button_state() == ('normal', 'End Turn')

    def test_locked_while_armies_move(self, game):
        game.game_state.turn_phase = 'execution'
        assert game._end_turn_button_state()[0] == 'locked'

    def test_tutorial_highlight(self, game, monkeypatch):
        game.tutorial_mission = SimpleNamespace(
            active=True, should_highlight_button=lambda b: b == 'end_turn',
            is_button_locked=lambda b: False, is_action_allowed=lambda a, **k: True,
            is_timer_visible=lambda: True)
        monkeypatch.setattr(game, '_is_tutorial_active', lambda: True)
        assert game._end_turn_button_state()[0] == 'highlight'
        game.draw_bottom_ui()  # Draws the pulse ring without errors

    def test_sim_ready_shows_waiting(self, game, monkeypatch):
        game.sim_state = SimpleNamespace(sim_phase='planning', players_ready={0: True},
                                         get_waiting_player_names=lambda: ['AI Player 2'],
                                         round_number=4)
        monkeypatch.setattr(game, 'get_local_player', lambda: 0)
        assert game._end_turn_button_state() == ('locked', 'Waiting...')
        assert game._planning_timer_info() == ('waiting', ['AI Player 2'])

    def test_sim_resolving_label(self, game):
        game.sim_state = SimpleNamespace(sim_phase='resolving', players_ready={})
        assert game._end_turn_button_state() == ('locked', 'Resolving...')


class TestTurnNumber:

    def test_sequential_is_one_based(self, game):
        game.game_state.turn_number = 0
        assert game._display_turn_number() == 1
        game.game_state.turn_number = 6
        assert game._display_turn_number() == 7

    def test_simultaneous_uses_round_number(self, game):
        game.sim_state = SimpleNamespace(round_number=5)
        assert game._display_turn_number() == 5


class TestEndTurnFeedback:
    """Hover brightens and a click flash brightens more (pixel check, like the sidebar audit)."""

    def _button_pixels(self, game):
        import pygame
        game.screen.fill((0, 0, 0))
        game.draw_bottom_ui()
        rect = game.end_turn_button
        # Sample a strip through the wood, away from the label in the middle
        y = rect.centery
        xs = [rect.left + int(rect.w * f) for f in (0.22, 0.25, 0.28, 0.72, 0.75, 0.78)]
        return [tuple(game.screen.get_at((x, y)))[:3] for x in xs]

    def test_hover_and_flash_change_pixels(self, game):
        normal = self._button_pixels(game)
        game.mouse_pos = game.end_turn_button.center
        hover = self._button_pixels(game)
        game.clicked_element = ('bottom_button', 'end_turn')
        flash = self._button_pixels(game)
        assert sum(map(sum, hover)) > sum(map(sum, normal))
        assert sum(map(sum, flash)) > sum(map(sum, hover))


# ===========================================================================
# Ornate button art
# ===========================================================================

class TestInnerTint:

    def test_wood_tinted_frame_untouched(self, pygame_display):
        from utils.surface_utils import get_campaign_button_image, tint_campaign_button_wood
        art = get_campaign_button_image()
        tinted = tint_campaign_button_wood(art, (120, 220, 110))
        w, h = art.get_size()
        # Middle of the wood: now green-dominant (it was brown: red-dominant)
        wood = tinted.get_at((w // 2, h // 2))
        assert wood.g > wood.r and art.get_at((w // 2, h // 2)).r > art.get_at((w // 2, h // 2)).g
        # Gold frame pixels INSIDE the tint window (the notch beside the left end
        # cap) are untouched - only the colour test keeps them gold
        for x, y in ((229, 192), (230, 108), (233, 102)):
            px = (round(x * w / 1502.0), round(y * h / 297.0))
            assert art.get_at(px).g >= 150 and art.get_at(px).a == 255  # really gold
            assert tinted.get_at(px) == art.get_at(px)


class TestTutorialOutline:

    def test_band_traces_the_button_shape(self, game):
        """The highlight hugs the pointed caps: corners empty, tips covered, inside empty."""
        size = (220, 44)
        t = 3
        band = game.bottom_panel_kit.button_outline(size, thickness=t)
        assert band.get_size() == (size[0] + 2 * t, size[1] + 2 * t)
        w, h = band.get_size()
        # A box ring would colour the corners; the traced band leaves them empty
        assert band.get_at((1, 1)).a == 0 and band.get_at((w - 2, h - 2)).a == 0
        # ...but does run around the left and right points (they sit above mid-height)
        assert any(band.get_at((x, y)).a for x in range(0, 2 * t + 2) for y in range(h))
        assert any(band.get_at((x, y)).a for x in range(w - 2 * t - 2, w) for y in range(h))
        # The button itself is not covered
        assert band.get_at((w // 2, h // 2)).a == 0
        # Cached per size
        assert game.bottom_panel_kit.button_outline(size, thickness=t) is band


# ===========================================================================
# Territory view
# ===========================================================================

def _three_plot_territory(game, owner=0, units=5):
    """An owned territory with 3 plots, a garrison of `units` for `owner`, selected."""
    gs = game.game_state
    territory = next(t for t in sorted(gs.territory_owners) if len(game.scaled_plots.get(t, [])) == 3)
    gs.territory_owners[territory] = owner
    gs.territory_garrisons[territory] = {}
    if units:
        gs.add_garrison(territory, owner, unmoved=units)
    game.selected_territory_info = territory
    return territory


class TestTerritoryLayout:

    def test_sections_inside_panel_and_ordered(self, any_res_game):
        g = any_res_game
        layout = g._territory_view_layout()
        rects = [layout['rects'][k] for k in ('info', 'plots', 'forces', 'lore')]
        panel = _panel(g)
        for rect in rects:
            assert panel.contains(rect)
        for left, right in zip(rects, rects[1:]):
            assert left.right < right.left
        # The first section starts after the End Turn section
        assert rects[0].left > g._end_turn_section_rect().right

    def test_three_plots_fill_the_section(self, any_res_game):
        g = any_res_game
        _three_plot_territory(g)
        g.draw_bottom_ui()
        plots = g._territory_view_layout()['rects']['plots']
        buttons = [rect for rect, _t, _i in g.territory_info_plot_buttons]
        assert len(buttons) == 3
        for rect in buttons:
            assert plots.contains(rect)
        span = buttons[-1].right - buttons[0].left
        # Width-limited sections fill >= 85%; height-limited ones (wide screens) use
        # the full content height instead
        height_limited = buttons[0].h >= plots.bottom - buttons[0].top - 1
        assert span >= 0.85 * plots.w or height_limited
        assert abs((buttons[0].left + buttons[-1].right) // 2 - plots.centerx) <= 2

    def test_controls_inside_forces_section(self, any_res_game):
        g = any_res_game
        _three_plot_territory(g)
        g.draw_bottom_ui()
        forces = g._territory_view_layout()['rects']['forces']
        assert forces.contains(g.select_army_button)


class TestForces:

    def test_entries_order_and_hero(self, game):
        gs = game.game_state
        territory = _three_plot_territory(game, units=4)
        units = gs.territory_garrisons[territory][0]['units']
        for unit, unit_type in zip(units, ['Captain', 'Archer', 'Swordsman', 'Archer']):
            unit['type'] = unit_type
        hero = list(gs.HERO_TYPES)[0]
        gs.heroes.setdefault(1, {})[hero] = {'keep_territory': territory, 'keep_plot': 0}
        entries = game._forces_entries(territory)
        assert [(e['kind'], e['name']) for e in entries] == [
            ('unit', 'Swordsman'), ('unit', 'Archer'), ('unit', 'Captain'), ('hero', hero)]
        assert entries[1]['count'] == 2
        assert entries[3]['player'] == 1

    def test_army_limit_colours(self, game):
        import main
        assert game._army_limit_color(11) == main.BROWN_TEXT_PRIMARY
        yellow, red = game._army_limit_color(12), game._army_limit_color(15)
        assert yellow != main.BROWN_TEXT_PRIMARY and red != yellow
        assert red[0] > red[1] and yellow[1] > 150  # red is red, yellow is yellow

    def test_no_forces_draws_without_grid(self, game):
        _three_plot_territory(game, units=0)
        game.draw_bottom_ui()
        assert game.forces_hero_button is None


class TestSelectArmy:

    def test_enabled_with_own_garrison(self, game):
        territory = _three_plot_territory(game)
        assert game._can_select_army_in(territory)

    def test_greyed_without_own_units(self, game):
        territory = _three_plot_territory(game, owner=1)
        assert not game._can_select_army_in(territory)

    def test_greyed_outside_planning(self, game):
        territory = _three_plot_territory(game)
        game.game_state.turn_phase = 'execution'
        assert not game._can_select_army_in(territory)

    def test_click_opens_own_garrison(self, game):
        territory = _three_plot_territory(game)
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.select_army_button.center) is True
        assert game.show_army_composition and game.army_composition_territory == territory
        assert game.army_composition_player == 0
        assert game.selected_territory_info is None  # Switched to the Army view
        assert game.clicked_element == ('army', territory)  # The map banner flashes

    def test_greyed_click_is_consumed_without_action(self, game):
        _three_plot_territory(game, owner=1)
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.select_army_button.center) is True
        assert not game.show_army_composition

    def test_hover_and_flash_change_pixels(self, game):
        _three_plot_territory(game)

        def pixels():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.select_army_button
            return sum(sum(tuple(game.screen.get_at((rect.left + int(rect.w * f), rect.centery)))[:3])
                       for f in (0.2, 0.24, 0.76, 0.8))

        normal = pixels()
        game.mouse_pos = game.select_army_button.center
        hover = pixels()
        game.clicked_element = ('bottom_button', 'select_army')
        assert normal < hover < pixels()


class TestForcesHeroPortrait:

    def _with_hero(self, game, player):
        gs = game.game_state
        territory = _three_plot_territory(game, owner=player)
        hero = list(gs.HERO_TYPES)[0]
        gs.buildings.setdefault(territory, {})[0] = 'Keep'
        gs.heroes.setdefault(player, {})[hero] = {'keep_territory': territory, 'keep_plot': 0,
                                                  'ability_cooldowns': {}}
        return hero

    def test_own_hero_opens_hero_view(self, game, monkeypatch):
        import global_sound
        monkeypatch.setattr(global_sound, 'play_hero_select_sound', lambda name: None)
        hero = self._with_hero(game, 0)
        game.draw_bottom_ui()
        rect, name = game.forces_hero_button
        assert name == hero
        forces = game._territory_view_layout()['rects']['forces']
        assert forces.contains(rect)
        assert game.handle_bottom_ui_click(rect.center) is True
        assert game.selected_hero == hero
        assert game.selected_territory_info is None
        assert game.clicked_element == ('bottom_button', ('forces_hero', hero))
        game.draw_bottom_ui()  # The Hero view draws for it

    def test_enemy_hero_not_clickable(self, game):
        self._with_hero(game, 1)
        game.draw_bottom_ui()
        assert game.forces_hero_button is None


class TestForcesGridPlacement:
    """Owner feedback 2026-10-09: fixed column slots (a lone column stays left),
    columns spread across the section, rows from the top, hover shows the name."""

    def _cells(self, game, unit_types):
        gs = game.game_state
        territory = _three_plot_territory(game, units=len(unit_types))
        for unit, unit_type in zip(gs.territory_garrisons[territory][0]['units'], unit_types):
            unit['type'] = unit_type
        game.draw_bottom_ui()
        return [rect for rect, _entry in game.forces_cells]

    def test_lone_column_uses_the_left_slot(self, game):
        one = self._cells(game, ['Swordsman'])
        four = self._cells(game, ['Swordsman', 'Archer', 'Pikeman', 'Cavalry'])
        assert one[0].topleft == four[0].topleft  # Same slot, same top row
        assert four[3].left > four[0].left        # 4th entry starts the 2nd column

    def test_columns_spread_across_the_section(self, game):
        cells = self._cells(game, ['Swordsman', 'Archer', 'Pikeman', 'Cavalry'])
        forces = game._territory_view_layout()['rects']['forces']
        left_col, right_col = cells[0], cells[3]
        assert left_col.left < forces.left + forces.w * 0.2
        assert right_col.left > forces.centerx
        for rect in cells:
            assert forces.contains(rect)

    def test_hover_label_names_the_unit(self, game):
        cells = self._cells(game, ['Archer', 'Archer'])
        game.mouse_pos = cells[0].center
        game.draw_bottom_ui()
        assert game.bottom_panel_tooltip[0] == "2\u00d7 Archers"
        game._draw_bottom_panel_tooltip()  # Draws without errors
        game.mouse_pos = (0, 0)
        game.draw_bottom_ui()
        assert game.bottom_panel_tooltip is None
