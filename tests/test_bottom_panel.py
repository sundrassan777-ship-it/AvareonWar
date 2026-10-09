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


class TestHeroPortraitPosition:
    """Owner feedback 2026-10-09: the portrait moved sideways with the title length."""

    def test_portrait_does_not_move_between_heroes(self, any_res_game):
        g = any_res_game
        positions = set()
        for hero in list(g.game_state.HERO_TYPES):
            g.game_state.heroes[0] = {}
            _open_hero(g, hero)
            g.draw_bottom_ui()
            positions.add(tuple(g.hero_view_portrait_rect))
        assert len(positions) == 1
        general = g._hero_view_layout()['rects']['general']
        assert general.contains(pygame_rect(positions.pop()))


def pygame_rect(values):
    import pygame
    return pygame.Rect(values)


class TestHeroPortraitPan:
    """Owner request 2026-10-09: the Hero view portrait pans to the hero's Keep,
    like the portrait on the sidebar Heroes tab card."""

    def test_click_pans_to_the_keep(self, game, monkeypatch):
        hero = _open_hero(game)
        keep = game.game_state.heroes[0][hero]['keep_territory']
        panned = []
        monkeypatch.setattr(game, 'start_sidebar_camera_pan', lambda territory: panned.append(territory) or True)
        game.draw_bottom_ui()
        rect, name = game.hero_view_portrait_button
        assert name == hero
        assert game.handle_bottom_ui_click(rect.center) is True
        assert panned == [keep]
        assert game.clicked_element == ('bottom_button', ('hero_portrait', hero))
        assert game.selected_hero == hero  # Stays on the Hero view

    def test_hover_and_flash_brighten_the_portrait(self, game):
        _open_hero(game)

        def brightness():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.hero_view_portrait_rect
            return sum(sum(tuple(game.screen.get_at((rect.left + int(rect.w * fx), rect.top + int(rect.h * fy))))[:3])
                       for fx in (0.3, 0.5, 0.7) for fy in (0.3, 0.5, 0.7))

        normal = brightness()
        game.mouse_pos = game.hero_view_portrait_rect.center
        hover = brightness()
        game.clicked_element = ('bottom_button', ('hero_portrait', game.selected_hero))
        assert normal < hover < brightness()

    def test_no_pan_button_when_camera_pan_is_off(self, game, monkeypatch):
        import main
        monkeypatch.setattr(main.UIConstants, 'SIDEBAR_CAMERA_PAN', False)
        _open_hero(game)
        game.draw_bottom_ui()
        assert game.hero_view_portrait_button is None


# ===========================================================================
# Plot building view (finished / under construction) - owner design 2026-10-09:
# icon left; headline, rule, description (+ Farm/Mine level + XP BattleBar),
# rule, Demolish / Cancel button right of it
# ===========================================================================

def _select_building_plot(game, building=None, under_construction=None, xp=None):
    """Select plot 1 of an owned territory holding `building` (finished) or an
    `under_construction` entry (building_type, turns_remaining, cost)."""
    territory = _three_plot_territory(game)
    game.selected_territory_info = None
    gs = game.game_state
    gs.buildings.setdefault(territory, {}).pop(1, None)
    gs.under_construction.setdefault(territory, {}).pop(1, None)
    if building:
        gs.buildings[territory][1] = building
    if under_construction:
        gs.under_construction[territory][1] = under_construction
    if xp is not None:
        gs.building_xp.setdefault(territory, {})[1] = xp
    game.selected_plot = (territory, 1)
    return territory


def _spy_buttons(game, monkeypatch):
    """Record every kit.ornate_button() call: label -> (tint, locked, rect)."""
    drawn = {}
    kit = game.bottom_panel_kit
    real = kit.ornate_button

    def spy(rect, label, inner_tint, flash_key=None, locked=False, role='button', hover_pos=None):
        drawn[label] = (inner_tint, locked, rect)
        return real(rect, label, inner_tint, flash_key=flash_key, locked=locked, role=role,
                    hover_pos=hover_pos)

    monkeypatch.setattr(kit, 'ornate_button', spy)
    return drawn


PLOT_VIEW_CASES = [
    {'building': 'Square'},
    {'building': 'Training Grounds'},
    {'building': 'Farm', 'xp': {'xp': 50, 'level': 1}},
    {'building': 'Mine', 'xp': {'xp': 240, 'level': 5}},
    {'under_construction': ('Barracks', 2, 100)},
    {'under_construction': ('Training Grounds', 1, 100)},
]


class TestPlotBuildingLayout:

    def test_icon_matches_the_empty_plot_button(self, any_res_game):
        """The icon takes the first empty-plot button's size and spot (no jump when
        construction starts); the text column is right of it, inside the panel."""
        import pygame
        g = any_res_game
        layout = g._plot_building_view_layout()
        size, _gap, row_y, _limit = g._empty_plot_button_layout(False)
        assert layout['icon'] == pygame.Rect(int(g.screen.get_width() * 0.25), row_y, size, size)
        assert layout['column'].left > layout['icon'].right
        for rect in layout.values():
            assert _panel(g).contains(rect)

    @pytest.mark.parametrize('case', PLOT_VIEW_CASES,
                             ids=lambda c: c.get('building') or 'building_' + c['under_construction'][0])
    def test_every_state_fits_the_column(self, any_res_game, monkeypatch, case):
        g = any_res_game
        bars = []
        kit = g.bottom_panel_kit
        real_bar = kit.battlebar
        monkeypatch.setattr(kit, 'battlebar', lambda rect, *a, **k: bars.append(rect) or real_bar(rect, *a, **k))
        _select_building_plot(g, **case)
        g.draw_bottom_ui()
        column = g._plot_building_view_layout()['column']
        button = g.cancel_button if 'under_construction' in case else g.demolish_button
        assert button is not None and column.contains(button)
        assert button.bottom <= kit.content_bottom()
        # Farm / Mine: the XP BattleBar sits in the column, above the button (the End
        # Turn section's timer is a BattleBar too - left of the column)
        bars = [b for b in bars if b.left >= column.left]
        if case.get('xp'):
            assert len(bars) == 1
            assert column.contains(bars[0]) and bars[0].bottom < button.top
        else:
            assert bars == []


class TestPlotBuildingIcon:

    def _channel_spread(self, game):
        """Largest |r-b| / |r-g| over the middle of the icon. The circle border is
        switched off: its art lays a faint warm glaze over the whole circle."""
        game.circle_border = None
        game.screen.fill((0, 0, 0))
        game.draw_bottom_ui()
        icon = game._plot_building_view_layout()['icon']
        spread = 0
        for fx in (0.35, 0.45, 0.55, 0.65):
            for fy in (0.35, 0.45, 0.55, 0.65):
                r, gg, b = tuple(game.screen.get_at((icon.left + int(icon.w * fx), icon.top + int(icon.h * fy))))[:3]
                spread = max(spread, abs(r - b), abs(r - gg))
        return spread

    def test_under_construction_icon_is_greyed(self, game):
        _select_building_plot(game, under_construction=('Farm', 2, 50))
        assert self._channel_spread(game) <= 2

    def test_finished_icon_in_full_colour(self, game):
        _select_building_plot(game, building='Farm')
        assert self._channel_spread(game) > 10


class TestPlotBuildingButtons:

    def test_cancel_still_cancels(self, game):
        territory = _select_building_plot(game, under_construction=('Square', 2, 120))
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.cancel_button.center) is True
        assert 1 not in game.game_state.under_construction.get(territory, {})
        assert game.clicked_element == ('cancel', 'construction')

    def test_demolish_still_demolishes(self, game):
        territory = _select_building_plot(game, building='Square')
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.demolish_button.center) is True
        assert 1 not in game.game_state.buildings.get(territory, {})
        assert game.clicked_element == ('demolish', 'building')

    def test_hover_and_flash_change_pixels(self, game):
        _select_building_plot(game, building='Square')

        def pixels():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.demolish_button
            return sum(sum(tuple(game.screen.get_at((rect.left + int(rect.w * f), rect.centery)))[:3])
                       for f in (0.2, 0.24, 0.76, 0.8))

        normal = pixels()
        game.mouse_pos = game.demolish_button.center
        hover = pixels()
        game.clicked_element = ('demolish', 'building')
        assert normal < hover < pixels()

    def test_labels_and_tints(self, game, monkeypatch):
        import main
        drawn = _spy_buttons(game, monkeypatch)
        _select_building_plot(game, building='Square')
        game.draw_bottom_ui()
        assert drawn['Demolish (50%)'][:2] == (main.TINT_DEMOLISH, False)
        _select_building_plot(game, under_construction=('Mine', 3, 80))
        game.draw_bottom_ui()
        assert drawn['Cancel'][:2] == (main.TINT_DEMOLISH, False)

    def test_confiscate_shows_the_real_refund(self, game, monkeypatch):
        """With Erec Silvyr a Farm/Mine demolish refunds 175% (destroy_building());
        the button used to say 50%. Other buildings keep 50%."""
        import main
        drawn = _spy_buttons(game, monkeypatch)
        monkeypatch.setattr(game.game_state, 'player_has_silvyr', lambda p: True)
        _select_building_plot(game, building='Farm')
        game.draw_bottom_ui()
        assert drawn['Demolish (175%)'][0] == main.TINT_CONFISCATE
        drawn.clear()
        _select_building_plot(game, building='Square')
        game.draw_bottom_ui()
        assert 'Demolish (50%)' in drawn and 'Demolish (175%)' not in drawn

    def test_greyed_while_the_mission_forbids_it(self, game, monkeypatch):
        drawn = _spy_buttons(game, monkeypatch)
        game.tutorial_mission = SimpleNamespace(
            active=True, should_highlight_button=lambda b: False, is_button_locked=lambda b: False,
            is_action_allowed=lambda a, **k: a not in ('demolish', 'cancel_construction'),
            is_timer_visible=lambda: True)
        territory = _select_building_plot(game, building='Square')
        game.draw_bottom_ui()
        assert drawn['Demolish (50%)'][1] is True
        # The click is consumed without demolishing (same check as before)
        assert game.handle_bottom_ui_click(game.demolish_button.center) is True
        assert game.game_state.buildings[territory][1] == 'Square'
        _select_building_plot(game, under_construction=('Farm', 2, 50))
        game.draw_bottom_ui()
        assert drawn['Cancel'][1] is True


class TestBuildingXpView:

    def test_bar_fill_and_label(self, game):
        _select_building_plot(game, building='Farm', xp={'xp': 50, 'level': 1})
        xp = game._building_xp_view(*game.selected_plot)
        # Level 1 spans 30..75 XP: 20 of 45
        assert xp['label'] == '20/45 XP'
        assert abs(xp['fill'] - 20 / 45) < 1e-6
        assert xp['bonus_pct'] == 10

    def test_max_level(self, game):
        _select_building_plot(game, building='Mine', xp={'xp': 240, 'level': 5})
        xp = game._building_xp_view(*game.selected_plot)
        assert (xp['label'], xp['fill'], xp['bonus_pct']) == ('MAX', 1.0, 50)


# ===========================================================================
# Barracks view - owner design 2026-10-09: Barracks (unit buttons) / Training
# Queue (n/4) / Barracks Info (facts + hotkeys, Demolish)
# ===========================================================================

def _open_barracks(game, queue=()):
    """Select a finished Barracks on plot 0 of an owned territory with `queue`."""
    territory = _three_plot_territory(game)
    game.selected_territory_info = None
    gs = game.game_state
    gs.buildings.setdefault(territory, {})[0] = 'Barracks'
    gs.training_queue.setdefault(territory, {})[0] = list(queue)
    game.selected_barracks = (territory, 0)
    return territory


FULL_QUEUE = [('Swordsman', 0, 30), ('Archer', 1, 30), ('Pikeman', 1, 30), ('Cavalry', 1, 50)]


class TestBarracksLayout:

    def test_sections_inside_panel_and_ordered(self, any_res_game):
        g = any_res_game
        rects = [g._barracks_view_layout()['rects'][k] for k in ('units', 'queue', 'info')]
        for rect in rects:
            assert _panel(g).contains(rect)
        for left, right in zip(rects, rects[1:]):
            assert left.right < right.left

    def test_unit_buttons_fit_in_a_row(self, any_res_game):
        g = any_res_game
        _open_barracks(g)
        g.draw_bottom_ui()
        units = g._barracks_view_layout()['rects']['units']
        buttons = [g.train_buttons[u] for u in g.TRAINING_UNIT_ORDER]
        for rect in buttons:
            assert units.contains(rect)
            assert rect.w >= 40  # Readable at 720p too
        for left, right in zip(buttons, buttons[1:]):
            assert left.right < right.left and left.top == right.top

    def test_full_queue_fits_its_section(self, any_res_game):
        g = any_res_game
        _open_barracks(g, FULL_QUEUE)
        g.draw_bottom_ui()
        queue = g._barracks_view_layout()['rects']['queue']
        assert [i for _r, i in g.queue_cancel_buttons] == [0, 1, 2, 3]
        for rect, _i in g.queue_cancel_buttons:
            assert queue.contains(rect)
        tops = [r.top for r, _i in g.queue_cancel_buttons]
        assert tops == sorted(tops) and len(set(tops)) == 4

    def test_demolish_inside_info_section(self, any_res_game):
        g = any_res_game
        _open_barracks(g)
        g.draw_bottom_ui()
        info = g._barracks_view_layout()['rects']['info']
        assert info.contains(g.demolish_barracks_button)
        assert abs(g.demolish_barracks_button.centerx - info.centerx) <= 1


class TestBarracksContent:

    def _texts(self, game, monkeypatch):
        drawn = {}
        kit = game.bottom_panel_kit
        real_left, real_centered = kit.left_text, kit.centered_text

        def left(text, role, color, x, y, shadow=True):
            drawn[text] = color
            return real_left(text, role, color, x, y, shadow)

        def centered(text, role, color, cx, y, shadow=True):
            drawn[text] = color
            return real_centered(text, role, color, cx, y, shadow)

        monkeypatch.setattr(kit, 'left_text', left)
        monkeypatch.setattr(kit, 'centered_text', centered)
        return drawn

    def test_queue_count_in_the_headline(self, game, monkeypatch):
        import main
        drawn = self._texts(game, monkeypatch)
        _open_barracks(game, FULL_QUEUE[1:3])
        game.draw_bottom_ui()
        assert drawn['(2/4)'] == main.BOTTOM_GOLD_TEXT
        _open_barracks(game, FULL_QUEUE)
        game.draw_bottom_ui()
        assert drawn['(4/4)'] == (232, 82, 70)  # Red when full

    def test_queue_texts(self, game, monkeypatch):
        drawn = self._texts(game, monkeypatch)
        _open_barracks(game, FULL_QUEUE)
        game.draw_bottom_ui()
        assert 'Swordsman (Army Limit Reached)' in drawn
        assert 'Archer (waiting)' in drawn
        _open_barracks(game, [('Archer', 1, 30)])
        game.draw_bottom_ui()
        assert 'Archer (training... 1 turn)' in drawn

    def test_empty_queue(self, game, monkeypatch):
        drawn = self._texts(game, monkeypatch)
        _open_barracks(game)
        game.draw_bottom_ui()
        assert 'No units in queue' in drawn
        assert game.queue_cancel_buttons == []

    def test_hotkeys_section_lists_every_hotkey(self, game, monkeypatch):
        """Captain's hotkey (T) was missing from the old Controls list. The section
        shows only the hotkeys (owner: no gold / armies / command lines)."""
        drawn = self._texts(game, monkeypatch)
        _open_barracks(game)
        game.draw_bottom_ui()
        for key, unit in (('S', 'Swordsman'), ('A', 'Archer'), ('P', 'Pikeman'),
                          ('C', 'Cavalry'), ('T', 'Captain')):
            assert f'[{key}] {unit}' in drawn
        assert 'Hotkeys' in drawn and 'Barracks Info' not in drawn
        assert not any(t.startswith(('Gold: ', 'Armies: ', 'Command: ')) for t in drawn)

    def test_hotkeys_match_the_keyboard_handler(self):
        import main
        import pygame
        from input.keyboard_handler import _TRAINING_SHORTCUTS
        listed = {pygame.key.key_code(k.lower()): unit for k, unit in main.Game.TRAINING_HOTKEYS}
        assert listed == _TRAINING_SHORTCUTS

    def test_demolish_label_follows_the_refund(self, game, monkeypatch):
        import main
        drawn = _spy_buttons(game, monkeypatch)
        _open_barracks(game)
        game.draw_bottom_ui()
        assert drawn['Demolish (50%)'][:2] == (main.TINT_DEMOLISH, False)
        game.game_state.player_barracks_full_refund[0] = True  # Makeshift Barracks
        game.draw_bottom_ui()
        assert 'Demolish (100%)' in drawn


class TestBarracksButtons:

    def test_demolish_still_works(self, game):
        territory = _open_barracks(game)
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.demolish_barracks_button.center) is True
        assert 0 not in game.game_state.buildings.get(territory, {})
        assert game.selected_barracks is None

    def test_demolish_hover_and_flash_change_pixels(self, game):
        _open_barracks(game)

        def pixels():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.demolish_barracks_button
            return sum(sum(tuple(game.screen.get_at((rect.left + int(rect.w * f), rect.centery)))[:3])
                       for f in (0.2, 0.24, 0.76, 0.8))

        normal = pixels()
        game.mouse_pos = game.demolish_barracks_button.center
        hover = pixels()
        game.clicked_element = ('demolish', 'barracks')
        assert normal < hover < pixels()

    def test_queue_cancel_still_works(self, game):
        territory = _open_barracks(game, [('Archer', 1, 30), ('Pikeman', 1, 30)])
        game.draw_bottom_ui()
        rect, index = game.queue_cancel_buttons[1]
        assert game.handle_bottom_ui_click(rect.center) is True
        assert [e[0] for e in game.game_state.training_queue[territory][0]] == ['Archer']

    def test_queue_cancel_hover_and_flash_change_pixels(self, game):
        _open_barracks(game, [('Archer', 1, 30)])

        def pixels():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.queue_cancel_buttons[0][0]
            return sum(sum(tuple(game.screen.get_at((rect.left + 2, rect.top + 2)))[:3]) for _ in (0,))

        normal = pixels()
        game.mouse_pos = game.queue_cancel_buttons[0][0].center
        hover = pixels()
        game.clicked_element = ('queue_cancel', 0)
        assert normal < hover < pixels()

    def test_train_button_still_trains(self, game):
        territory = _open_barracks(game)
        game.game_state.player_gold[0] = 1000
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.train_buttons['Archer'].center) is True
        assert [e[0] for e in game.game_state.training_queue[territory][0]] == ['Archer']


# ===========================================================================
# Orphaned button tooltips: a hover whose buttons are no longer drawn is dropped
# (owner report 2026-10-09: Territory view plot icon hovered + clicked -> the
# tooltip stayed in the bottom panel and followed the mouse forever)
# ===========================================================================

class TestOrphanedTooltips:

    def _hover_frames(self, game, monkeypatch, pos, frames=2):
        import pygame
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pos)
        game.mouse_pos = pos
        for _ in range(frames):
            game.draw_bottom_ui()
            game.update_frame_tooltips()

    def test_territory_plot_tooltip_gone_after_the_click(self, game, monkeypatch):
        territory = _three_plot_territory(game)
        game.game_state.buildings.setdefault(territory, {})[0] = 'Barracks'
        game.game_state.training_queue.setdefault(territory, {})[0] = []
        game.draw_bottom_ui()
        rect = next(r for r, _t, i in game.territory_info_plot_buttons if i == 0)
        drawn = []
        monkeypatch.setattr(game, 'draw_button_tooltip', lambda pos, data: drawn.append(data))
        self._hover_frames(game, monkeypatch, rect.center)
        assert game.hover_target_button and game.hover_target_button[0] == 'plot'
        game.hover_start_time_button -= 5000  # Past the tooltip delay
        self._hover_frames(game, monkeypatch, rect.center, frames=1)
        assert drawn  # The plot tooltip is showing

        assert game.handle_bottom_ui_click(rect.center) is True  # Opens the Barracks view
        assert game.selected_barracks == (territory, 0)
        drawn.clear()
        # The cursor moves on over empty panel space (bottom of the empty queue) -
        # where the old tooltip kept following it
        queue = game._barracks_view_layout()['rects']['queue']
        self._hover_frames(game, monkeypatch, (queue.centerx, queue.bottom - 2))
        assert game.hover_target_button is None
        assert not [d for d in drawn if d[0] == 'plot']

    def test_map_training_icon_tooltip_gone_when_barracks_deselected(self, game, monkeypatch):
        """Escape (or the turn passing) while the cursor is on a quick-access icon:
        the icons stop drawing, so their hover must not survive."""
        game.hover_target_button = ('map_training', 'Archer')
        game.show_tooltip_button = ('map_training', 'Archer')
        game.selected_barracks = None
        self._hover_frames(game, monkeypatch, (400, 300), frames=1)
        assert game.hover_target_button is None and game.show_tooltip_button is None

    def test_forces_label_cleared_on_ai_turn(self, game):
        """The Forces-icon label (bottom_panel_tooltip) is reset by draw_bottom_ui(),
        which does not run during AI turns - the empty panel must reset it too."""
        game.bottom_panel_tooltip = ("5x Swordsmen", (300, 800))
        game.draw_empty_bottom_ui_panel()
        assert game.bottom_panel_tooltip is None

    def test_live_hover_survives_frames(self, game, monkeypatch):
        """No false release: a button still drawn keeps its hover and timer."""
        _open_barracks(game)
        game.draw_bottom_ui()
        rect = game.train_buttons['Archer']
        self._hover_frames(game, monkeypatch, rect.center)
        started = game.hover_start_time_button
        self._hover_frames(game, monkeypatch, rect.center, frames=3)
        assert game.hover_target_button == ('training', 'Archer')
        assert game.hover_start_time_button == started


# ===========================================================================
# Keep view - owner design 2026-10-09: Keep (4x2 hero portraits) / Castle upgrade
# (no headline) / Training Status (row + progress bar) / Hero Info (Hero Limit,
# rules, Demolish)
# ===========================================================================

def _open_keep(game, gold=1000):
    """Select a finished Keep on plot 0 of an owned territory (no hero yet)."""
    territory = _three_plot_territory(game)
    game.selected_territory_info = None
    gs = game.game_state
    gs.buildings.setdefault(territory, {})[0] = 'Keep'
    gs.hero_training_queue.pop(territory, None)
    gs.castle_upgrades.pop(territory, None)
    gs.castle_upgrades_in_progress.pop(territory, None)
    gs.player_gold[0] = gold
    game.selected_keep = (territory, 0)
    return territory


def _trainable_heroes(game):
    types = game.game_state.HERO_TYPES
    return [h for h in types if types[h].get('trainable', True)]


class TestKeepLayout:

    def test_sections_inside_panel_and_ordered(self, any_res_game):
        g = any_res_game
        rects = [g._keep_view_layout()['rects'][k] for k in ('heroes', 'castle', 'training', 'info')]
        for rect in rects:
            assert _panel(g).contains(rect)
        for left, right in zip(rects, rects[1:]):
            assert left.right < right.left

    def test_hero_portraits_fit_a_4x2_grid(self, any_res_game):
        g = any_res_game
        _open_keep(g)
        g.draw_bottom_ui()
        heroes = g._keep_view_layout()['rects']['heroes']
        trainable = _trainable_heroes(g)
        assert sorted(g.hero_train_buttons) == sorted(trainable)
        rects = [g.hero_train_buttons[h] for h in trainable]
        for rect in rects:
            assert heroes.contains(rect)
            assert rect.w >= 50  # Readable at 720p too
        assert len({r.top for r in rects}) == 2 and len({r.left for r in rects}) == 4
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                assert not a.colliderect(b)

    def test_castle_icon_keeps_its_spot_in_every_state(self, any_res_game):
        g = any_res_game
        territory = _open_keep(g)
        castle = g._keep_view_layout()['rects']['castle']
        spots = []
        for state in ('available', 'upgrading', 'castle'):
            if state == 'upgrading':
                g.game_state.castle_upgrades_in_progress[territory] = {0: 2}
            elif state == 'castle':
                g.game_state.castle_upgrades_in_progress.pop(territory, None)
                g.game_state.castle_upgrades[territory] = {0: True}
            g.draw_bottom_ui()
            assert castle.contains(g.castle_icon_rect)
            spots.append(g.castle_icon_rect)
        assert spots[0] == spots[1] == spots[2]

    def test_demolish_inside_info_section(self, any_res_game):
        g = any_res_game
        _open_keep(g)
        g.draw_bottom_ui()
        info = g._keep_view_layout()['rects']['info']
        assert info.contains(g.demolish_keep_button)


class TestCastleStates:

    def test_available_is_clickable(self, game):
        _open_keep(game)
        game.draw_bottom_ui()
        assert game.castle_upgrade_button == game.castle_icon_rect

    def test_not_clickable_without_gold(self, game):
        _open_keep(game, gold=100)
        game.draw_bottom_ui()
        assert game.castle_upgrade_button is None

    def test_upgrading_shows_cancel_inside_the_section(self, any_res_game):
        g = any_res_game
        territory = _open_keep(g)
        g.game_state.castle_upgrades_in_progress[territory] = {0: 2}
        g.draw_bottom_ui()
        castle = g._keep_view_layout()['rects']['castle']
        assert g.castle_upgrade_button is None
        assert castle.contains(g.castle_upgrade_cancel_button)

    def test_castle_done_is_not_clickable(self, game, monkeypatch):
        """Owner choice: the icon stays, in full colour, captioned "Upgrade
        Finished" (not "Castle" - the headline says that); no button, no cancel,
        no tooltip."""
        texts = []
        kit = game.bottom_panel_kit
        real = kit.centered_text
        monkeypatch.setattr(kit, 'centered_text', lambda t, *a, **k: texts.append(t) or real(t, *a, **k))
        territory = _open_keep(game)
        game.game_state.castle_upgrades[territory] = {0: True}
        game.draw_bottom_ui()
        assert game.castle_upgrade_button is None and game.castle_upgrade_cancel_button is None
        assert 'Upgrade Finished' in texts
        game.mouse_pos = game.castle_icon_rect.center
        game.draw_bottom_ui()
        assert game.castle_button_is_hovering is False

    def test_upgrade_click_still_works(self, game):
        territory = _open_keep(game)
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.castle_icon_rect.center) is True
        assert game.game_state.is_upgrading_to_castle(territory, 0)
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.castle_upgrade_cancel_button.center) is True
        assert not game.game_state.is_upgrading_to_castle(territory, 0)

    def test_upgrading_icon_tint_is_cached(self, game, monkeypatch):
        """The yellow "upgrading" tint used to allocate a Surface every frame."""
        import pygame
        territory = _open_keep(game)
        game.game_state.castle_upgrades_in_progress[territory] = {0: 2}
        game.draw_bottom_ui()  # Builds the cached tint
        made = []
        real_surface = pygame.Surface

        def counting(*a, **k):
            made.append(a)
            return real_surface(*a, **k)

        monkeypatch.setattr(pygame, 'Surface', counting)
        size = game.castle_icon_rect.w
        game.draw_bottom_ui()
        assert not [a for a in made if a and tuple(a[0]) == (size, size)]


class TestKeepTrainingStatus:

    def test_progress_bar_follows_training_time(self, game):
        territory = _open_keep(game)
        hero = 'Aidam Narn'  # training_time 5
        total = game.game_state.HERO_TYPES[hero]['training_time']
        game.game_state.hero_training_queue[territory] = {0: (hero, 3, 300)}
        game.draw_bottom_ui()
        bar, frac = game.keep_training_bar
        assert abs(frac - (total - 3) / float(total)) < 1e-6
        training = game._keep_view_layout()['rects']['training']
        assert training.contains(bar) and training.contains(game.hero_cancel_button)

    def test_fits_at_every_resolution(self, any_res_game):
        g = any_res_game
        territory = _open_keep(g)
        g.game_state.hero_training_queue[territory] = {0: ('Seledra Rennervail', 1, 300)}
        g.draw_bottom_ui()
        training = g._keep_view_layout()['rects']['training']
        bar, _frac = g.keep_training_bar
        assert training.contains(bar)
        assert bar.bottom + g.bottom_panel_kit.line_height('small') <= training.bottom

    def test_cancel_still_works(self, game):
        territory = _open_keep(game)
        game.game_state.hero_training_queue[territory] = {0: ('Aidam Narn', 3, 300)}
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.hero_cancel_button.center) is True
        assert territory not in game.game_state.hero_training_queue or \
            0 not in game.game_state.hero_training_queue[territory]
        assert game.clicked_element == ('hero_cancel', 'training')

    def test_nothing_in_training(self, game):
        _open_keep(game)
        game.draw_bottom_ui()
        assert game.hero_cancel_button is None and game.keep_training_bar is None


class TestKeepHeroInfo:

    def _left_texts(self, game, monkeypatch):
        drawn = {}
        kit = game.bottom_panel_kit
        real = kit.left_text

        def spy(text, role, color, x, y, shadow=True):
            drawn[text] = color
            return real(text, role, color, x, y, shadow)

        monkeypatch.setattr(kit, 'left_text', spy)
        return drawn

    def test_hero_limit_red_once_reached(self, game, monkeypatch):
        """Red at the limit: 3, or 4 with Heroic Fortitude (player_hero_limit)."""
        import main
        drawn = self._left_texts(game, monkeypatch)
        gs = game.game_state
        _open_keep(game)
        gs.hero_ownership[0] = {'Halon Nextroy', 'Erec Silvyr'}
        game.draw_bottom_ui()
        assert drawn['Hero Limit: 2/3'] == main.BROWN_TEXT_PRIMARY
        gs.hero_ownership[0] = {'Halon Nextroy', 'Erec Silvyr', 'Vearen Asford'}
        game.draw_bottom_ui()
        assert drawn['Hero Limit: 3/3'] == (232, 82, 70)
        gs.player_hero_limit[0] = 4  # Heroic Fortitude researched
        game.draw_bottom_ui()
        assert drawn['Hero Limit: 3/4'] == main.BROWN_TEXT_PRIMARY

    def test_rules_listed(self, game, monkeypatch):
        drawn = self._left_texts(game, monkeypatch)
        _open_keep(game)
        game.draw_bottom_ui()
        for fragment in ("trained once", "only have one", "slain upon"):
            assert any(fragment in text for text in drawn), fragment

    def test_demolish_still_works(self, game):
        territory = _open_keep(game)
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.demolish_keep_button.center) is True
        assert 0 not in game.game_state.buildings.get(territory, {})

    def test_demolish_hover_and_flash_change_pixels(self, game):
        _open_keep(game)

        def pixels():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            rect = game.demolish_keep_button
            return sum(sum(tuple(game.screen.get_at((rect.left + int(rect.w * f), rect.centery)))[:3])
                       for f in (0.2, 0.24, 0.76, 0.8))

        normal = pixels()
        game.mouse_pos = game.demolish_keep_button.center
        hover = pixels()
        game.clicked_element = ('demolish', 'keep')
        assert normal < hover < pixels()

    def test_hero_portrait_click_still_trains(self, game):
        territory = _open_keep(game)
        hero = _trainable_heroes(game)[0]
        game.draw_bottom_ui()
        assert game.handle_bottom_ui_click(game.hero_train_buttons[hero].center) is True
        assert game.game_state.hero_training_queue[territory][0][0] == hero


class TestKeepHeroCard:
    """Owner request 2026-10-09: a Keep whose hero is trained shows that hero
    (portrait, name, title) under the headline instead of the training grid, and
    clicking it opens the Hero view like the Territory view's Forces portrait."""

    HERO = 'Neil Hévilneu'  # Longest title: two lines

    def _give_keep_a_hero(self, game):
        territory = _open_keep(game)
        gs = game.game_state
        gs.heroes.setdefault(0, {})[self.HERO] = {'keep_territory': territory, 'keep_plot': 0}
        gs.hero_ownership[0] = {self.HERO}
        return territory

    def test_card_replaces_the_grid_and_fits(self, any_res_game):
        g = any_res_game
        self._give_keep_a_hero(g)
        g.draw_bottom_ui()
        assert g.hero_train_buttons == {}
        card, name = g.keep_hero_button
        assert name == self.HERO
        assert g._keep_view_layout()['rects']['heroes'].contains(card)

    def test_name_and_title_drawn(self, game, monkeypatch):
        drawn = []
        kit = game.bottom_panel_kit
        real = kit.left_text
        monkeypatch.setattr(kit, 'left_text', lambda t, *a, **k: drawn.append(t) or real(t, *a, **k))
        self._give_keep_a_hero(game)
        game.draw_bottom_ui()
        assert self.HERO in drawn
        assert any('Supreme Commander' in t for t in drawn)

    def test_click_opens_the_hero_view(self, game):
        self._give_keep_a_hero(game)
        game.draw_bottom_ui()
        card, _name = game.keep_hero_button
        assert game.handle_bottom_ui_click(card.center) is True
        assert game.selected_hero == self.HERO
        assert game.selected_keep is None
        assert game.clicked_element == ('bottom_button', ('keep_hero', self.HERO))

    def test_hover_and_flash_brighten_the_portrait(self, game):
        self._give_keep_a_hero(game)

        def brightness():
            game.screen.fill((0, 0, 0))
            game.draw_bottom_ui()
            card, _name = game.keep_hero_button
            size = card.h
            return sum(sum(tuple(game.screen.get_at((card.left + int(size * fx), card.top + int(size * fy))))[:3])
                       for fx in (0.3, 0.5, 0.7) for fy in (0.3, 0.5, 0.7))

        normal = brightness()
        game.mouse_pos = game.keep_hero_button[0].center
        hover = brightness()
        game.clicked_element = ('bottom_button', ('keep_hero', self.HERO))
        assert normal < hover < brightness()

    def test_no_card_without_a_hero(self, game):
        _open_keep(game)
        game.draw_bottom_ui()
        assert game.keep_hero_button is None
        assert len(game.hero_train_buttons) == len(_trainable_heroes(game))
