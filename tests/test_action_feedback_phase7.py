# -*- coding: utf-8 -*-
"""
Tests: Phase 7 of the Action Failure Feedback effort — the remaining refusals.

  - Clicking a technology while simultaneous mode resolves battles: 'wrong_phase'
    toast (the tree looks normal then, so the click needs an explanation).
  - A build shortcut key on an occupied plot / plot under construction:
    'plot_occupied' (the build buttons are hidden there, so only a key gets here).
  - Players window: Send / Enter with an empty or 0 amount: 'transfer_no_amount',
    shown red in the window's own feedback line with the denial sound (the in-game
    toast would be hidden behind the modal's dark overlay). Enter now respects the
    disabled-row guard like the Send button does.
"""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.action_error_messages import format_action_error
from game_state import GameState

TERRITORY = "Lobardia"


@pytest.fixture
def gs():
    state = GameState(num_players=2, player_is_ai=[False, False],
                      player_ai_difficulty=[1, 1], skip_setup_phase=True)
    state.current_player = 0
    state.territory_owners[TERRITORY] = 0
    state.player_gold[0] = 5000
    return state


class TestPlotOccupied:

    def test_built_plot(self, gs):
        gs.buildings.setdefault(TERRITORY, {})[0] = 'Farm'
        assert gs.start_construction(TERRITORY, 0, 'Mine') is False
        assert gs.last_action_error == 'plot_occupied'

    def test_plot_under_construction(self, gs):
        gs.under_construction.setdefault(TERRITORY, {})[0] = ('Farm', 2, 50)
        assert gs.start_construction(TERRITORY, 0, 'Mine') is False
        assert gs.last_action_error == 'plot_occupied'

    def test_empty_plot_builds(self, gs):
        assert gs.start_construction(TERRITORY, 0, 'Farm') is True
        assert gs.last_action_error is None


# ===========================================================================
# Real Game
# ===========================================================================

@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _make_game(mode='sequential'):
    from main import Game
    g = Game()
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                       'player_ai_difficulty': [1, 1], 'game_mode': mode})
    g.game_state.phase = 'playing'
    g.game_state.turn_phase = 'planning'
    g.game_state.current_player = 0
    g.game_state.territory_owners[TERRITORY] = 0
    g.tutorial_mission = None
    return g


class TestBuildShortcutOnOccupiedPlot:

    def test_key_on_occupied_plot_toasts(self, pygame_display):
        import pygame
        game = _make_game()
        game.game_state.buildings.setdefault(TERRITORY, {})[0] = 'Farm'
        game.selected_plot = (TERRITORY, 0)
        game.selected_barracks = None
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_keyboard_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0, unicode='m'))
        show.assert_called_once_with('plot_occupied')


class TestResearchWhileResolving:

    def _click(self, game, tech_rect_pos=True):
        import pygame
        rect = pygame.Rect(1400, 200, 50, 50)
        game.technology_buttons = {'some_tech': rect}
        pos = rect.center if tech_rect_pos else (1380, 400)
        with mock.patch.object(game, 'show_action_error') as show, \
                mock.patch.object(game.game_state, 'start_research') as research:
            handled = game.handle_technology_tab_click(pos)
        return handled, show, research

    def test_tech_click_while_resolving_toasts(self, pygame_display):
        game = _make_game('simultaneous')
        game.sim_state.sim_phase = 'resolving'
        handled, show, research = self._click(game)
        assert handled is True
        show.assert_called_once_with('wrong_phase')
        research.assert_not_called()

    def test_click_off_the_techs_is_silent(self, pygame_display):
        game = _make_game('simultaneous')
        game.sim_state.sim_phase = 'resolving'
        handled, show, research = self._click(game, tech_rect_pos=False)
        assert handled is False
        show.assert_not_called()


class TestGoldTransferAmount:

    @pytest.fixture
    def window(self, pygame_display):
        from players_window import PlayersWindow
        game = _make_game()
        return PlayersWindow(game)

    @pytest.mark.parametrize("text", ["", "0", "   "])
    def test_empty_or_zero_amount_shows_error(self, window, text):
        window.input_texts[1] = text
        with mock.patch('global_sound.play_action_denied') as sound, \
                mock.patch.object(window.game.game_state, 'transfer_gold') as transfer:
            window._attempt_send(0, 1)
        sound.assert_called_once()
        transfer.assert_not_called()
        assert window.feedback_message == format_action_error('transfer_no_amount')
        assert window.feedback_is_error is True

    def test_success_message_is_not_an_error(self, window):
        window.input_texts[1] = "10"
        with mock.patch.object(window.game, 'execute_gold_transfer', return_value=10):
            window._attempt_send(0, 1)
        assert window.feedback_message == "Transfer successful."
        assert window.feedback_is_error is False

    def test_enter_on_disabled_row_does_nothing(self, window):
        import pygame
        window.focused_recipient = 1
        window.input_texts[1] = ""
        window._row_disabled_reason = {1: "Cannot send Gold to enemy players."}
        with mock.patch.object(window, '_attempt_send') as send:
            window.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode='\r'))
        send.assert_not_called()
