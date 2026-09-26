# -*- coding: utf-8 -*-
"""
Tests: Phase 2 (input / hidden-territory) fixes of the Action Failure Feedback effort.

  5. Territories hidden by a campaign mission (map_data enabled-territories filter)
     are not drawn, so they must not be hoverable, clickable or targetable. The
     shared get_territory_at_pos() now skips them, and hero-ability targeting uses
     it instead of a private polygon loop (which let Aggressive Diplomacy etc. hit
     hidden territories).
  6. The keyboard build/train shortcuts go through the same code path as a click
     (_try_start_construction / _try_start_training): sim order / network sync,
     sim-resolving gate and failure feedback. The map-icon and bottom-panel paths
     were unified onto the same helpers.
  7. Bottom-panel build/train/hero/castle/demolish are blocked while simultaneous
     mode resolves battles, like the map quick-icons already were.
  +  Single-player simultaneous mode applied the human's map-icon training twice
     (the executor's "already executed at click" skip only worked in multiplayer).
"""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
# conftest.py autouse fixture handles load_polygons() + clear_enabled_territories()


TERRITORY = "Lobardia"


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _make_game(game_mode='sequential'):
    from main import Game
    g = Game()
    g.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [1, 1],
        'game_mode': game_mode,
    })
    gs = g.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    gs.territory_owners[TERRITORY] = 0
    gs.player_gold[0] = 5000
    g.tutorial_mission = None
    return g


@pytest.fixture
def game(pygame_display):
    return _make_game()


@pytest.fixture
def sim_game(pygame_display):
    return _make_game('simultaneous')


def _world_point_in(game, territory, on_screen=False):
    """
    A world position that get_territory_at_pos() resolves to `territory` (filter cleared).
    on_screen=True also requires the point to land in the visible map area (below the top
    panel, above the bottom UI, left of the sidebar) so a click there reaches the map.
    """
    import main
    min_x, min_y, max_x, max_y = game.map_renderer.territory_bounding_boxes[territory]
    steps = 25
    for i in range(1, steps):
        for j in range(1, steps):
            p = (min_x + (max_x - min_x) * i / steps, min_y + (max_y - min_y) * j / steps)
            if game.get_territory_at_pos(p) != territory:
                continue
            if on_screen:
                sx, sy = game.world_to_screen(p)
                if not (main.TOP_PANEL_HEIGHT + 5 < sy < main.BOTTOM_UI_Y - 5
                        and 5 < sx < main.WINDOW_WIDTH - main.UIConstants.SIDEBAR_WIDTH - 60):
                    continue
            return p
    return None


def _visible_territory_point(game):
    """(territory, screen_pos) for some territory with an interior point on screen."""
    for territory in game.scaled_polygons:
        p = _world_point_in(game, territory, on_screen=True)
        if p is not None:
            return territory, tuple(int(v) for v in game.world_to_screen(p))
    pytest.fail("no territory visible on screen")


# ===========================================================================
# 5. Hidden territories
# ===========================================================================

class TestHiddenTerritories:

    def test_hidden_territory_is_not_found(self, game):
        point = _world_point_in(game, TERRITORY)
        others = [t for t in game.scaled_polygons if t != TERRITORY]
        map_data.set_enabled_territories(others)
        assert game.get_territory_at_pos(point) != TERRITORY

    def test_enabled_territory_is_still_found(self, game):
        point = _world_point_in(game, TERRITORY)
        map_data.set_enabled_territories([TERRITORY])
        assert game.get_territory_at_pos(point) == TERRITORY

    def _levy_click(self, game, screen_pos):
        """Click `screen_pos` in Levy targeting mode; return the execute_levy mock."""
        game.ability_targeting_active = True
        game.ability_targeting_ability_name = 'Levy'
        with mock.patch.object(game.game_state, 'execute_levy', return_value=(False, 'x')) as levy, \
                mock.patch.object(game, 'is_local_player_active', return_value=True):
            game.handle_map_area_click(screen_pos)
        return levy

    def test_ability_targeting_reaches_visible_territory(self, game):
        """Positive control: the same click on a drawn territory does reach the ability."""
        territory, screen_pos = _visible_territory_point(game)
        levy = self._levy_click(game, screen_pos)
        assert levy.call_args[0][0] == territory

    def test_ability_targeting_ignores_hidden_territory(self, game):
        """Levy on a hidden territory used to reach execute_levy (and show an error)."""
        territory, screen_pos = _visible_territory_point(game)
        map_data.set_enabled_territories([t for t in game.scaled_polygons if t != territory])
        levy = self._levy_click(game, screen_pos)
        assert all(c[0][0] != territory for c in levy.call_args_list)

    def test_ability_targeting_respects_non_interactive_territory(self, game):
        """Tutorial-style non-interactive territories are filtered like left/right-click."""
        from types import SimpleNamespace
        territory, screen_pos = _visible_territory_point(game)
        game.tutorial_mission = SimpleNamespace(
            active=True,
            is_territory_interactive=lambda t: t != territory,
            is_action_allowed=lambda *a, **k: True,
        )
        levy = self._levy_click(game, screen_pos)
        levy.assert_not_called()


# ===========================================================================
# 6. Shared build/train path (map icon, bottom panel, keyboard)
# ===========================================================================

def _barracks(game, plot=0):
    game.game_state.buildings.setdefault(TERRITORY, {})[plot] = 'Barracks'
    return plot


def _queue_len(gs, plot=0):
    queue = gs.training_queue.get(TERRITORY, {})
    return len(queue.get(plot, [])) if isinstance(queue, dict) else len(queue)


class TestSharedBuildTrainPath:

    def test_failed_build_shows_feedback(self, game):
        game.game_state.player_gold[0] = 0
        with mock.patch.object(game, '_show_action_failure_feedback') as feedback:
            assert game._try_start_construction(TERRITORY, 0, 'Farm') is False
        feedback.assert_called_once()

    def test_sequential_multiplayer_build_sends_building_order(self, game):
        from network_config import MessageType
        game.multiplayer_mode = True
        game.local_player_index = 0
        with mock.patch.object(game, '_send_action_to_remote') as send:
            assert game._try_start_construction(TERRITORY, 0, 'Farm') is True
        assert send.call_args[0][0] == MessageType.BUILDING_ORDER

    def test_sequential_multiplayer_training_sends_training_order(self, game):
        """The map-icon training path never sent TRAINING_ORDER before."""
        from network_config import MessageType
        game.multiplayer_mode = True
        game.local_player_index = 0
        plot = _barracks(game)
        with mock.patch.object(game, '_send_action_to_remote') as send:
            assert game._try_start_training(TERRITORY, plot, 'Swordsman') is True
        assert send.call_args[0][0] == MessageType.TRAINING_ORDER

    def test_sim_build_and_train_queue_sim_orders(self, sim_game):
        plot = _barracks(sim_game)
        assert sim_game._try_start_training(TERRITORY, plot, 'Swordsman') is True
        assert sim_game._try_start_construction(TERRITORY, 1, 'Farm') is True
        types = [o['type'] for o in sim_game.sim_state.player_orders[0]]
        assert types == ['train', 'build']

    def test_sim_resolving_blocks_build_and_train(self, sim_game):
        plot = _barracks(sim_game)
        sim_game.sim_state.sim_phase = 'resolving'
        with mock.patch.object(sim_game.game_state, 'start_training') as train, \
                mock.patch.object(sim_game.game_state, 'start_construction') as build:
            assert sim_game._try_start_training(TERRITORY, plot, 'Swordsman') is False
            assert sim_game._try_start_construction(TERRITORY, 1, 'Farm') is False
        train.assert_not_called()
        build.assert_not_called()


class TestKeyboardShortcuts:

    def _press(self, game, key):
        import pygame
        event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode='')
        return game.handle_keyboard_input(event)

    def test_build_shortcut_uses_shared_path(self, game):
        import pygame
        game.selected_plot = (TERRITORY, 0)
        game.selected_barracks = None
        with mock.patch.object(game, '_try_start_construction', return_value=True) as build:
            self._press(game, pygame.K_f)
        build.assert_called_once_with(TERRITORY, 0, 'Farm')

    def test_train_shortcut_uses_shared_path(self, game):
        import pygame
        game.selected_plot = None
        game.selected_barracks = (TERRITORY, 0)
        with mock.patch.object(game, '_try_start_training', return_value=True) as train:
            self._press(game, pygame.K_s)
        train.assert_called_once_with(TERRITORY, 0, 'Swordsman')

    def test_failed_shortcut_gives_feedback(self, game):
        import pygame
        game.game_state.player_gold[0] = 0
        game.selected_plot = (TERRITORY, 0)
        game.selected_barracks = None
        with mock.patch.object(game, '_show_action_failure_feedback') as feedback:
            self._press(game, pygame.K_f)
        feedback.assert_called_once()

    def test_shortcut_blocked_after_ready(self, sim_game):
        import pygame
        sim_game.selected_plot = (TERRITORY, 0)
        sim_game.selected_barracks = None
        sim_game.sim_state.players_ready[0] = True
        with mock.patch.object(sim_game, '_try_start_construction') as build:
            self._press(sim_game, pygame.K_f)
        build.assert_not_called()


# ===========================================================================
# Single-player simultaneous mode: no double execution of clicked orders
# ===========================================================================

class TestSinglePlayerSimNoDoubleExecution:

    def test_click_executed_player_is_the_human(self, sim_game):
        assert sim_game.sim_state.local_player_index is None  # single-player
        assert sim_game.sim_state.click_executed_player == 0

    def test_training_is_not_applied_twice(self, sim_game):
        gs = sim_game.game_state
        plot = _barracks(sim_game)
        assert sim_game._try_start_training(TERRITORY, plot, 'Swordsman')
        gold_after_click = gs.player_gold[0]
        assert _queue_len(gs, plot) == 1

        pm = sim_game.sim_state.phase_manager
        for order in sim_game.sim_state.player_orders[0]:
            pm._apply_train_order(order)

        assert _queue_len(gs, plot) == 1
        assert gs.player_gold[0] == gold_after_click

    def test_ai_orders_are_still_applied(self, sim_game):
        """The skip only covers the human who clicked, never AI players."""
        gs = sim_game.game_state
        gs.territory_owners["Nordia"] = 1
        gs.buildings.setdefault("Nordia", {})[0] = 'Barracks'
        gs.player_gold[1] = 5000
        pm = sim_game.sim_state.phase_manager
        pm._apply_train_order({'type': 'train', 'player_id': 1, 'territory': "Nordia",
                               'barracks_plot': 0, 'unit_type': 'Swordsman'})
        queue = gs.training_queue.get("Nordia", {})
        assert len(queue.get(0, [])) == 1


# ===========================================================================
# 7. Bottom panel blocked while simultaneous mode resolves
# ===========================================================================

class TestBottomPanelSimResolvingGate:

    def test_demolish_blocked_while_resolving(self, sim_game):
        import pygame
        import main
        y = main.MAP_HEIGHT + 40
        sim_game.selected_keep = None
        sim_game.selected_barracks = None
        sim_game.selected_plot = (TERRITORY, 0)
        sim_game.game_state.buildings.setdefault(TERRITORY, {})[0] = 'Farm'
        sim_game.demolish_button = pygame.Rect(300, y, 60, 30)
        sim_game.building_buttons = {}
        sim_game.cancel_button = None
        sim_game.end_turn_button = None
        sim_game.sim_state.sim_phase = 'resolving'
        with mock.patch.object(sim_game, 'is_local_player_active', return_value=True), \
                mock.patch.object(sim_game.game_state, 'destroy_building') as destroy:
            sim_game.handle_bottom_ui_click(sim_game.demolish_button.center)
        destroy.assert_not_called()
