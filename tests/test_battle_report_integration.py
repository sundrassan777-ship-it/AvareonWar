# -*- coding: utf-8 -*-
"""
Integration tests for Battle Reports against a real Game instance.

These exercise the wiring the unit tests cannot: the per-frame promote/clear cycle,
the Priority 0 click chain, the Detail screen round trip and the top-bar button.

A real Game is needed because the feature spans game_state, main.py, the popup
renderer and ui_renderer; a stub would not prove they agree. The construction cost
is why the fixture is module scoped.
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import map_data  # noqa: E402  (conftest autouse fixture handles load/cleanup)


@pytest.fixture(scope='module')
def game():
    pygame.init()
    map_data.load_polygons()
    from main import Game
    instance = Game()
    instance.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 'Normal'],
    })
    yield instance
    pygame.display.quit()
    pygame.quit()


@pytest.fixture
def ready(game):
    """Put the game in the local player's planning phase with no reports pending."""
    gs = game.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    gs.turn_announcement_active = False
    game.game_menu_visible = False
    game.options_menu_visible = False
    game.battle_report_queues = {}
    game.battle_report_popups = []
    game.battle_report_rects = []
    game.battle_report_detail_ui = None
    gs.battle_report_inbox = []
    return game


def _report(game, **overrides):
    territory = sorted(game.scaled_centers.keys())[0]
    report = {
        'territory': territory, 'turn_number': 1, 'defender': 0, 'attacker': 1,
        'held': False, 'units_lost': 3, 'units_remaining': 0,
        'structures_destroyed': 1, 'structures_captured': 2,
        'structures_remaining': 2,
        'unit_breakdown': {'Swordsman': {'original': 3, 'survived': 0, 'lost': 3}},
        'attacker_lost': 1, 'attacker_survivors': 9,
        'defender_lost': 3, 'defender_survivors': 0,
    }
    report.update(overrides)
    return report


def _show(game, report):
    """Push a report through the capture->UI boundary and draw it."""
    game.game_state.battle_report_inbox.append(report)
    game._update_battle_reports(0.016)
    game.draw_battle_reports()


class TestPromotionAndClearing:

    def test_inbox_is_drained_into_the_viewer_queue(self, ready):
        report = _report(ready)
        _show(ready, report)
        assert ready.battle_report_popups == [report]
        assert ready.game_state.battle_report_inbox == []

    def test_draw_produces_both_button_rects(self, ready):
        _show(ready, _report(ready))
        assert [entry[1] for entry in ready.battle_report_rects] == ['detail', 'close']

    def test_end_of_planning_clears_reports(self, ready):
        _show(ready, _report(ready))
        ready.game_state.turn_phase = 'execution'
        ready._update_battle_reports(0.016)
        assert ready.battle_report_popups == []
        assert ready.battle_report_queues.get(0) == []

    def test_reports_do_not_reappear_next_turn(self, ready):
        _show(ready, _report(ready))
        ready.game_state.turn_phase = 'execution'
        ready._update_battle_reports(0.016)
        ready.game_state.turn_phase = 'planning'
        ready._update_battle_reports(0.016)
        assert ready.battle_report_popups == []

    def test_turn_announcement_hides_but_does_not_destroy(self, ready):
        """
        Reports are queued BEFORE the announcement that opens the turn they belong
        to, so the announcement must hide them without clearing the queue --
        otherwise every report is destroyed unseen.
        """
        report = _report(ready)
        ready.game_state.turn_announcement_active = True
        ready.game_state.battle_report_inbox.append(report)
        ready._update_battle_reports(0.016)
        assert ready.battle_report_popups == []

        ready.game_state.turn_announcement_active = False
        ready._update_battle_reports(0.016)
        assert ready.battle_report_popups == [report]


class TestClickRouting:

    def test_close_dismisses_only_that_report(self, ready):
        first = _report(ready)
        second = _report(ready, territory=sorted(ready.scaled_centers)[1])
        ready.game_state.battle_report_inbox.extend([first, second])
        ready._update_battle_reports(0.016)
        ready.draw_battle_reports()

        close_rect = [r for r, action, rep in ready.battle_report_rects
                      if action == 'close' and rep is first][0]
        assert ready.handle_battle_report_click(close_rect.center) is True
        assert ready.battle_report_popups == [second]

    def test_click_missing_every_popup_falls_through(self, ready):
        """Reports are Priority 0 but NOT modal: a miss must not consume the click."""
        _show(ready, _report(ready))
        assert ready.handle_battle_report_click((2, 400)) is False

    def test_open_modal_beats_priority_zero(self, ready):
        """
        A Priority 0 handler would otherwise steal clicks from the game menu, which
        sits at Priority 4.
        """
        _show(ready, _report(ready))
        rect = ready.battle_report_rects[1][0]
        ready.game_menu_visible = True
        try:
            assert ready.handle_battle_report_click(rect.center) is False
        finally:
            ready.game_menu_visible = False
        assert ready.handle_battle_report_click(rect.center) is True

    def test_hover_is_suppressed_under_a_popup(self, ready):
        _show(ready, _report(ready))
        rect = ready.battle_report_rects[0][0]
        assert ready._battle_report_rect_at(rect.center) is not None
        assert ready._battle_report_rect_at((2, 400)) is None


class TestDetailScreen:

    def test_detail_opens_and_close_removes_the_report(self, ready):
        report = _report(ready)
        _show(ready, report)
        detail_rect = ready.battle_report_rects[0][0]

        assert ready.handle_battle_report_click(detail_rect.center) is True
        assert ready.battle_report_detail_ui is not None
        # Defender POV: the attacker saw a victory, this must read as a defeat.
        assert ready.battle_report_detail_ui.current_player_won is False
        ready.draw_battle_report_detail()

        ready.close_battle_report_detail()
        assert ready.battle_report_detail_ui is None
        assert ready.battle_report_popups == []

    def test_popups_are_not_drawn_behind_the_detail_screen(self, ready):
        _show(ready, _report(ready))
        ready.handle_battle_report_click(ready.battle_report_rects[0][0].center)
        ready.draw_battle_reports()
        assert ready.battle_report_rects == []
        ready.close_battle_report_detail()


class TestCloseAllButton:

    def test_button_appears_only_with_reports(self, ready):
        ready.ui_renderer._draw_close_all_battle_reports_button(1.0)
        assert ready.close_all_battle_reports_button is None

        _show(ready, _report(ready))
        ready.ui_renderer._draw_close_all_battle_reports_button(1.0)
        assert ready.close_all_battle_reports_button is not None

    def test_button_clears_everything_and_hides_itself(self, ready):
        _show(ready, _report(ready))
        ready.ui_renderer._draw_close_all_battle_reports_button(1.0)
        ready._handle_close_all_battle_reports_click()

        assert ready.battle_report_popups == []
        assert ready.battle_report_queues.get(0) == []
        assert ready.close_all_battle_reports_button is None

    def test_button_hidden_once_planning_ends(self, ready):
        _show(ready, _report(ready))
        ready.game_state.turn_phase = 'execution'
        ready._update_battle_reports(0.016)
        ready.ui_renderer._draw_close_all_battle_reports_button(1.0)
        assert ready.close_all_battle_reports_button is None


# ===========================================================================
# Simultaneous mode
# ===========================================================================

@pytest.fixture(scope='module')
def sim_game():
    """A simultaneous-mode Game. Separate from the sequential fixture above."""
    pygame.init()
    map_data.load_polygons()
    from main import Game
    instance = Game()
    instance.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 1],
        'game_mode': 'simultaneous',
    })
    yield instance


@pytest.fixture
def sim(sim_game):
    gs = sim_game.game_state
    gs.phase = 'playing'
    gs.turn_announcement_active = False
    sim_game.sim_state.sim_phase = 'planning'
    sim_game.sim_state.players_ready = {0: False, 1: False}
    sim_game.battle_report_queues = {}
    sim_game.battle_report_popups = []
    sim_game.battle_report_rects = []
    sim_game.battle_report_detail_ui = None
    sim_game._battle_report_planning_owner = None
    gs.battle_report_inbox = []
    return sim_game


class TestSimultaneousMode:
    """
    Simultaneous mode is where the clearing rule actually bites.

    Battles resolve during the 'resolving' phase, when NOBODY is planning -- and
    because every player plans at once, the viewer IS the defender at that moment.
    A "not in planning, therefore clear" rule wiped each report on the very frame it
    was captured, so no report ever reached the screen.
    """

    def test_viewer_is_the_local_human_not_the_current_player(self, sim):
        """
        sim code temporarily swaps current_player while running each player's orders,
        and "whose turn is it" is meaningless when everyone plans together.
        """
        sim.game_state.current_player = 1      # an AI slot
        assert sim._get_report_viewer() == 0

    def test_report_captured_during_resolution_survives(self, sim):
        report = _report(sim)
        sim.sim_state.sim_phase = 'resolving'
        sim.game_state.battle_report_inbox.append(report)

        for _ in range(5):                      # several frames of the resolving phase
            sim._update_battle_reports(0.016)
        assert sim.battle_report_queues.get(0) == [report]
        assert sim.battle_report_popups == []   # not shown yet

    def test_report_appears_when_planning_begins(self, sim):
        report = _report(sim)
        sim.sim_state.sim_phase = 'resolving'
        sim.game_state.battle_report_inbox.append(report)
        sim._update_battle_reports(0.016)

        sim.sim_state.sim_phase = 'planning'
        sim._update_battle_reports(0.016)
        sim.draw_battle_reports()

        assert sim.battle_report_popups == [report]
        assert [entry[1] for entry in sim.battle_report_rects] == ['detail', 'close']

    def test_marking_ready_ends_the_phase_and_clears(self, sim):
        """A player's own planning phase ends when they mark ready, not at round end."""
        report = _report(sim)
        sim.game_state.battle_report_inbox.append(report)
        sim._update_battle_reports(0.016)
        assert sim.battle_report_popups == [report]

        sim.sim_state.players_ready[0] = True
        sim._update_battle_reports(0.016)
        assert sim.battle_report_popups == []
        assert sim.battle_report_queues.get(0) == []

    def test_unreviewed_reports_do_not_return_next_round(self, sim):
        report = _report(sim)
        sim.game_state.battle_report_inbox.append(report)
        sim._update_battle_reports(0.016)

        sim.sim_state.players_ready[0] = True   # ready up without reading them
        sim._update_battle_reports(0.016)
        sim.sim_state.sim_phase = 'resolving'
        sim._update_battle_reports(0.016)
        sim.sim_state.sim_phase = 'planning'    # next round
        sim.sim_state.players_ready[0] = False
        sim._update_battle_reports(0.016)

        assert sim.battle_report_popups == []

    def test_full_round_cycle(self, sim):
        """plan -> ready -> execute -> resolve (battle) -> plan: the report shows."""
        sim._update_battle_reports(0.016)          # planning, nothing pending
        sim.sim_state.players_ready[0] = True
        sim._update_battle_reports(0.016)          # readied up

        sim.sim_state.sim_phase = 'executing'
        sim._update_battle_reports(0.016)

        sim.sim_state.sim_phase = 'resolving'
        report = _report(sim)
        sim.game_state.battle_report_inbox.append(report)
        sim._update_battle_reports(0.016)

        sim.sim_state.sim_phase = 'planning'       # complete_round -> new planning
        sim.sim_state.players_ready = {0: False, 1: False}
        sim._update_battle_reports(0.016)

        assert sim.battle_report_popups == [report]
