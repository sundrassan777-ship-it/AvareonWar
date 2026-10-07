# -*- coding: utf-8 -*-
"""
Tests: Phase 3 (visual / tint) fixes of the Action Failure Feedback effort.

Rule R1 of the effort: a refused action needs no error message when its button is
hidden, red or greyed. These fixes make buttons that LOOKED available (but were
refused) show their real state instead:

  - One shared per-type building rule (get_building_type_block_reason) for
    start_construction(), the map icons and the bottom panel — the copies had
    drifted (Square limit / no Keep in a Fortress territory looked available).
  - One shared training-queue limit (MAX_TRAINING_QUEUE); the map icons used < 5.
  - End Turn greyed while armies move / battles are unresolved (sequential) and
    when a campaign mission blocks it (intro/pause).
  - Battle markers greyed on any turn that isn't the local player's, re-evaluated
    every frame (was: AI turns only, decided once).
  - Sidebar tabs / order cancel buttons locked by a mission are greyed.
  - "Save failed!" is flagged as an error (drawn red).
"""

import os
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
# conftest.py autouse fixture handles load_polygons() + cleanup

from game_state import GameState, Battle, MovementOrder

TERRITORY = "Lobardia"
GREY = (120, 120, 120)


@pytest.fixture
def gs():
    state = GameState(num_players=2, player_is_ai=[False, False],
                      player_ai_difficulty=[1, 1], skip_setup_phase=True)
    state.current_player = 0
    state.territory_owners[TERRITORY] = 0
    state.player_gold[0] = 5000
    return state


# ===========================================================================
# Shared building rule
# ===========================================================================

class TestBuildingTypeBlockReason:

    def test_plain_building_is_allowed(self, gs):
        assert gs.get_building_type_block_reason(TERRITORY, 'Farm') is None

    @pytest.mark.parametrize("building", ['Keep', 'Training Grounds', 'Square'])
    def test_unique_building_already_built(self, gs, building):
        gs.buildings.setdefault(TERRITORY, {})[0] = building
        assert gs.get_building_type_block_reason(TERRITORY, building) is not None

    @pytest.mark.parametrize("building", ['Keep', 'Training Grounds', 'Square'])
    def test_unique_building_under_construction(self, gs, building):
        gs.under_construction.setdefault(TERRITORY, {})[1] = (building, 2, 100)
        assert gs.get_building_type_block_reason(TERRITORY, building) is not None

    def test_no_keep_in_fortress_territory(self, gs, monkeypatch):
        # Only Azincournean Highlands has fortress territories; mark one on this map
        monkeypatch.setattr(map_data, 'FORTRESS_TERRITORIES', {TERRITORY})
        assert gs.get_building_type_block_reason(TERRITORY, 'Keep') is not None
        assert gs.get_building_type_block_reason(TERRITORY, 'Farm') is None
        # ...and start_construction() refuses it with the same rule
        assert gs.start_construction(TERRITORY, 0, 'Keep') is False

    def test_start_construction_uses_the_same_rule(self, gs):
        gs.buildings.setdefault(TERRITORY, {})[0] = 'Square'
        assert gs.start_construction(TERRITORY, 1, 'Square') is False
        assert "Only one Square allowed per territory!" in [str(m) for m in gs.messages][-1]


class TestTrainingQueueLimit:

    def test_backend_refuses_at_max_training_queue(self, gs):
        gs.buildings.setdefault(TERRITORY, {})[0] = 'Barracks'
        gs.training_queue[TERRITORY] = {0: [('Swordsman', 1, 25)] * gs.MAX_TRAINING_QUEUE}
        assert gs.start_training(TERRITORY, 0, 'Swordsman') is False
        assert gs.last_action_error == 'queue_full'


# ===========================================================================
# Rendering (real Game)
# ===========================================================================

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
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                       'player_ai_difficulty': [1, 1]})
    g.game_state.phase = 'playing'
    g.game_state.turn_phase = 'planning'
    g.game_state.current_player = 0
    g.tutorial_mission = None
    return g


def _end_turn_color(game):
    """Colour draw_bottom_ui() passes for the End Turn button."""
    captured = {}
    real = game.draw_feedback_button

    def spy(rect, color, button_type, button_id, *a, **k):
        if button_id == 'end_turn':
            captured['color'] = color
        return real(rect, color, button_type, button_id, *a, **k)

    with mock.patch.object(game, 'draw_feedback_button', side_effect=spy):
        game.draw_bottom_ui()
    return captured.get('color')


class TestEndTurnButton:

    def test_normal_planning_is_not_grey(self, game):
        assert _end_turn_color(game) != GREY

    def test_grey_while_armies_move(self, game):
        game.game_state.turn_phase = 'execution'
        assert _end_turn_color(game) == GREY

    def test_grey_with_unresolved_battles(self, game):
        game.game_state.turn_phase = 'battles'
        game.game_state.pending_battles = [Battle(TERRITORY)]
        assert _end_turn_color(game) == GREY

    def test_grey_when_mission_blocks_end_turn(self, game):
        game.tutorial_mission = SimpleNamespace(
            active=True,
            should_highlight_button=lambda b: False,
            is_button_locked=lambda b: False,        # campaign missions never lock buttons...
            is_action_allowed=lambda a, **k: a != 'end_turn',  # ...they block via this
            is_timer_visible=lambda: True,
        )
        with mock.patch.object(game, '_is_tutorial_active', return_value=True):
            assert _end_turn_color(game) == GREY


class TestBattleMarkers:

    def _markers(self, game):
        game.game_state.turn_phase = 'battles'
        game.game_state.pending_battles = [Battle(TERRITORY)]
        game.map_renderer.draw_battle_markers()
        return game.map_renderer.battle_effects[TERRITORY]

    def test_own_turn_is_clickable(self, game):
        assert self._markers(game).greyed_out is False

    def test_other_players_turn_is_grey_and_updates(self, game):
        game.game_state.current_player = 1
        assert self._markers(game).greyed_out is True
        # Turn changes -> the same marker is re-evaluated, not stuck grey
        game.game_state.current_player = 0
        assert self._markers(game).greyed_out is False

    def test_remote_human_turn_is_grey(self, game):
        """Multiplayer: a remote human's turn used to show clickable markers."""
        game.game_state.player_is_ai = [False, False]
        game.multiplayer_mode = True
        game.local_player_index = 0
        game.game_state.current_player = 1
        assert self._markers(game).greyed_out is True


class TestLockedSidebarControls:

    def _mission(self, blocked):
        return SimpleNamespace(
            active=True,
            should_highlight_button=lambda b: False,
            is_button_locked=lambda b: False,
            is_action_allowed=lambda a, **k: not blocked(a, k),
        )

    def test_locked_tab_is_greyed(self, game):
        import main
        game.game_state.sidebar_expanded = True
        game.game_state.active_sidebar_tab = 'action_queue'
        game.tutorial_mission = self._mission(lambda a, k: a == 'sidebar_tab' and k.get('tab_name') == 'heroes')
        sidebar_x = main.WINDOW_WIDTH - main.UIConstants.SIDEBAR_WIDTH
        game.ui_renderer._draw_sidebar_tab_buttons(sidebar_x, main.TOP_PANEL_HEIGHT, main.UIConstants.SIDEBAR_WIDTH, 500)
        heroes = game.sidebar_tab_buttons['heroes']
        other = game.sidebar_tab_buttons['technology']
        # The bookmarks are textured sprites now (sidebar overhaul), so compare the
        # tabs' average brightness instead of one exact pixel: locked < inactive.
        import pygame

        def brightness(rect):
            return sum(pygame.transform.average_color(game.screen, rect)[:3])

        assert brightness(heroes) < brightness(other) * 0.85

    def test_locked_cancel_all_is_greyed(self, game):
        game.game_state.sidebar_expanded = True
        game.game_state.active_sidebar_tab = 'action_queue'
        game.game_state.movement_orders = [MovementOrder(TERRITORY, 'Lentria', 1, 0, [0])]
        game.tutorial_mission = self._mission(lambda a, k: a in ('cancel_order', 'cancel_all_orders'))
        game.draw_order_sidebar()
        rect = game.cancel_all_button
        assert rect is not None
        assert game.screen.get_at((rect.x + 6, rect.y + 6))[:3] == (110, 110, 110)


class TestSaveFeedback:

    def test_failed_save_is_flagged_as_error(self, game):
        game.save_dialog_active = True
        game.save_name_input = "x"
        with mock.patch('save_manager.save_game', return_value=None):
            game._execute_save_game()
        assert game.save_feedback_message == "Save failed!"
        assert game.save_feedback_is_error is True
