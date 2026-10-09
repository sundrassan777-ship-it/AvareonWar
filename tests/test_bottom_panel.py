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


# ===========================================================================
# Empty plot view
# ===========================================================================

def _select_empty_plot(game):
    territory = _three_plot_territory(game)
    game.selected_territory_info = None
    game.selected_plot = (territory, 1)
    return territory


class TestEmptyPlotView:

    def test_buttons_fill_the_panel_and_fit_the_screen(self, any_res_game):
        g = any_res_game
        _select_empty_plot(g)
        g.draw_bottom_ui()
        buttons = list(g.building_buttons.values())
        assert len(buttons) == len(g.game_state.building_types)
        panel = _panel(g)
        content_h = g.bottom_panel_kit.content_bottom() - g.bottom_panel_kit.content_top()
        for rect in buttons:
            assert panel.contains(rect)
        for left, right in zip(buttons, buttons[1:]):
            assert left.right < right.left
        # As tall as the content area, unless the screen width is what limits them
        size = buttons[0].h
        width_limited = buttons[-1].right >= g.screen.get_width() - 3 * g.bottom_panel_kit.px(14)
        assert size >= content_h - 1 or width_limited
        # Clearly bigger than the old fixed 1.5 x BUTTON_SIZE_SQUARE circles
        import main
        assert size > int(main.BUTTON_SIZE_SQUARE * 1.5)

    def test_limit_line_pushes_the_row_down(self, game):
        territory = _select_empty_plot(game)
        size, _gap, row_y, limit_y = game._empty_plot_button_layout(False)
        size_l, _gap_l, row_y_l, limit_y_l = game._empty_plot_button_layout(True)
        assert row_y_l + size_l <= game.bottom_panel_kit.content_bottom()
        assert row_y_l > limit_y_l + game.bottom_panel_kit.line_height('body_bold') - 1
        # Drawn without errors when the limit applies
        started = game.game_state.buildings_started_this_turn
        started.add(territory) if hasattr(started, 'add') else started.append(territory)
        game.draw_bottom_ui()
        assert all(r.top >= row_y_l for r in game.building_buttons.values())


# ===========================================================================
# Army view (army composition)
# ===========================================================================

def _open_army(game, units=7, territory_total=None):
    """Open the Army view on a garrison of `units` for player 0."""
    territory = _three_plot_territory(game, units=units)
    game.selected_territory_info = None
    game._select_army_garrison((territory, 0))
    return territory


class TestArmyLayout:

    def test_sections_inside_panel_and_ordered(self, any_res_game):
        g = any_res_game
        rects = [g._army_view_layout()['rects'][k] for k in ('info', 'units', 'help')]
        for rect in rects:
            assert _panel(g).contains(rect)
        for left, right in zip(rects, rects[1:]):
            assert left.right < right.left

    def test_full_army_fits_the_units_section(self, any_res_game):
        """15 units (the army limit) = 3 full rows, inside the section at 720p too."""
        g = any_res_game
        _open_army(g, units=15)
        g.draw_bottom_ui()
        units = g._army_view_layout()['rects']['units']
        assert len(g.army_composition_buttons) == 15
        for rect, _uid in g.army_composition_buttons:
            assert units.contains(rect)

    def test_buttons_in_the_right_column_of_the_info_section(self, any_res_game):
        g = any_res_game
        _open_army(g)
        g.draw_bottom_ui()
        info = g._army_view_layout()['rects']['info']
        for rect in (g.select_all_button, g.deselect_all_button):
            assert info.contains(rect)
            assert rect.left > info.centerx - info.w // 10  # Right of the T's upright
        assert g.select_all_button.bottom < g.deselect_all_button.top


class TestArmyButtons:

    def test_select_and_deselect_all_still_work(self, game):
        territory = _open_army(game, units=4)
        units = game.game_state.territory_garrisons[territory][0]['units']
        units[3]['status'] = 'moved'
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.deselect_all_button.center) is True
        assert game.selected_army_units == []
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.select_all_button.center) is True
        assert sorted(game.selected_army_units) == sorted(u['id'] for u in units[:3])

    def test_hover_and_flash_change_pixels(self, game):
        _open_army(game)

        def pixels():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.select_all_button
            return sum(sum(tuple(game.screen.get_at((rect.left + int(rect.w * f), rect.centery)))[:3])
                       for f in (0.2, 0.24, 0.76, 0.8))

        normal = pixels()
        game.mouse_pos = game.select_all_button.center
        hover = pixels()
        game.clicked_element = ('army_comp', 'select_all')
        assert normal < hover < pixels()

    def test_total_coloured_by_territory_limit(self, game, monkeypatch):
        """Total uses the Army Limit colours: yellow from 12, red at 15."""
        drawn = {}
        kit = game.bottom_panel_kit
        real = kit.left_text

        def spy(text, role, color, x, y, shadow=True):
            drawn[text] = color
            return real(text, role, color, x, y, shadow)

        monkeypatch.setattr(kit, 'left_text', spy)
        _open_army(game, units=12)
        game.draw_bottom_ui()
        assert drawn["Total: 12/15"] == game._army_limit_color(12)
        assert drawn["Total: 12/15"] != game._army_limit_color(5)
        assert any(text.startswith("Ready to Move: 12") for text in drawn)


class TestArmyInfoTweaks:
    """Owner feedback 2026-10-09: T anchored on the rule's diamond, roomier buttons."""

    def test_t_hangs_from_the_rule_diamond(self, any_res_game, monkeypatch):
        g = any_res_game
        kit = g.bottom_panel_kit
        calls = {'rule': [], 'vrule': []}
        real_rule, real_vrule = kit.rule, kit.vertical_rule

        def rule(rect, y, width_frac=0.92):
            calls['rule'].append((rect.copy(), y))
            return real_rule(rect, y, width_frac)

        def vrule(x, y0, y1):
            calls['vrule'].append((x, y0, y1))
            return real_vrule(x, y0, y1)

        monkeypatch.setattr(kit, 'rule', rule)
        monkeypatch.setattr(kit, 'vertical_rule', vrule)
        _open_army(g)
        g.draw_bottom_ui()
        info = g._army_view_layout()['rects']['info']
        header_rule = [c for c in calls['rule'] if c[0] == info][0]
        x, y0, _y1 = calls['vrule'][0]
        # kit.rule() centres the art on rect.centerx; its diamond is mid-art, 3 px down
        assert x == info.centerx == header_rule[0].centerx
        assert y0 == header_rule[1] + 3

    def test_buttons_have_room_between_them(self, game):
        _open_army(game)
        game.draw_bottom_ui()
        assert game.deselect_all_button.top - game.select_all_button.bottom >= game.bottom_panel_kit.px(10)


class TestBottomPanelTooltipReach:
    """Regression (owner report 2026-10-09): the Training Grounds building button
    showed no tooltip. Bottom-panel tooltips were cut off in the rightmost 250 px,
    and the bigger empty-plot buttons put Training Grounds inside that strip."""

    def test_rightmost_building_button_shows_its_tooltip(self, any_res_game, monkeypatch):
        import pygame
        g = any_res_game
        _select_empty_plot(g)
        g.draw_bottom_ui()
        rect = g.building_buttons['Training Grounds']
        assert rect.centerx > g.screen.get_width() - 250  # Inside the old dead strip

        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: rect.center)
        g.mouse_pos = rect.center
        drawn = []
        monkeypatch.setattr(g, 'draw_button_tooltip', lambda pos, data: drawn.append(data))

        g.update_frame_tooltips()  # Starts the hover timer
        assert g.hover_target_button == ('building', 'Training Grounds')
        g.hover_start_time_button -= 5000  # Past the tooltip delay
        g.update_frame_tooltips()
        assert ('building', 'Training Grounds') in drawn


# ===========================================================================
# Hero view
# ===========================================================================

def _open_hero(game, hero=None):
    """Give player 0 a hero in a Keep and open its Hero view."""
    gs = game.game_state
    territory = _three_plot_territory(game)
    hero = hero or list(gs.HERO_TYPES)[0]
    gs.buildings.setdefault(territory, {})[0] = 'Keep'
    gs.heroes.setdefault(0, {})[hero] = {'keep_territory': territory, 'keep_plot': 0, 'ability_cooldowns': {}}
    game.selected_territory_info = None
    game.selected_hero = hero
    return hero


class TestHeroView:

    def test_sections_match_the_army_view(self, any_res_game):
        """Same pillars as the Army view, so switching views doesn't shift them."""
        g = any_res_game
        assert g._hero_view_layout()['pillars'] == g._army_view_layout()['pillars']
        for rect in g._hero_view_layout()['rects'].values():
            assert _panel(g).contains(rect)

    def test_abilities_in_a_centred_row(self, any_res_game):
        g = any_res_game
        hero = _open_hero(g)
        g.draw_bottom_ui()
        section = g._hero_view_layout()['rects']['abilities']
        rects = [g.hero_ability_buttons[(hero, i)] for i in range(3)]
        for rect in rects:
            assert section.contains(rect)
            assert rect.size == rects[0].size
            assert rect.top == rects[0].top
        assert abs((rects[0].left + rects[-1].right) // 2 - section.centerx) <= 1
        # Bigger than the old fixed 60 px at the reference resolution and above
        if g.bottom_panel_kit.scale >= 1:
            assert rects[0].w >= 60

    def test_every_hero_draws(self, game):
        """Each hero type (description lengths vary) draws without errors."""
        for hero in list(game.game_state.HERO_TYPES):
            game.game_state.heroes[0] = {}
            _open_hero(game, hero)
            game.draw_bottom_ui()
            assert (hero, 0) in game.hero_ability_buttons
