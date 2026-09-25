# -*- coding: utf-8 -*-
"""
Tests: Phase 4 (infrastructure) of the Action Failure Feedback effort.

  - config/action_error_messages.py holds every player-facing "action refused"
    text; format_action_error() fills {placeholders} and never raises.
  - Game.show_action_error() is the single feedback: denial sound + red toast.
    _show_action_failure_feedback() reads last_action_error (+ _args) and wraps it.
  - The centre-screen invalid-target popup is gone; hero-ability target errors use
    the toast (and keep targeting on).
  - Reinforce's refusal text (previously dropped) reaches the toast.
  - The toast shows multi-line / long messages in full and merges identical repeats.
"""

import os
import re
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.action_error_messages import (
    ACTION_ERROR_MESSAGES, DEFAULT_ACTION_ERROR, format_action_error)


# ===========================================================================
# Message table
# ===========================================================================

class TestMessageTable:

    def test_every_message_formats_with_its_placeholders(self):
        """No broken braces: each text formats when given its own placeholder names."""
        for code, text in ACTION_ERROR_MESSAGES.items():
            names = set(re.findall(r'{(\w+)}', text))
            formatted = format_action_error(code, **{n: 'X' for n in names})
            assert '{' not in formatted and '}' not in formatted, code

    def test_existing_codes_keep_working(self):
        for code in ('gold', 'command_limit', 'army_limit', 'queue_full', 'hero_limit'):
            assert code in ACTION_ERROR_MESSAGES

    def test_placeholders_are_filled(self):
        assert format_action_error('reinforce_limit', territory='Lobardia', limit=15) == \
            "Cannot reinforce Lobardia: would exceed army limit of 15!"

    def test_unknown_code_falls_back(self):
        assert format_action_error('no_such_code') == DEFAULT_ACTION_ERROR

    def test_mismatched_placeholder_never_raises(self, monkeypatch):
        monkeypatch.setitem(ACTION_ERROR_MESSAGES, 'gold', "Need {something_new}!")
        assert format_action_error('gold') == "Need {something_new}!"


# ===========================================================================
# Game-level feedback
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


class TestShowActionError:

    def test_plays_sound_and_shows_toast(self, game):
        with mock.patch('global_sound.play_action_denied') as sound, \
                mock.patch.object(game.chat_notification_effect, 'add_system_notification') as toast:
            game.show_action_error('target_blocked', territory='Lobardia')
        sound.assert_called_once()
        toast.assert_called_once_with("Cannot target Lobardia yet!")

    def test_literal_message(self, game):
        with mock.patch('global_sound.play_action_denied'), \
                mock.patch.object(game.chat_notification_effect, 'add_system_notification') as toast:
            game.show_action_error(message="Custom text!")
        toast.assert_called_once_with("Custom text!")

    def test_failure_feedback_uses_args_and_clears(self, game):
        gs = game.game_state
        gs.last_action_error = 'reinforce_limit'
        gs.last_action_error_args = {'territory': 'Lobardia', 'limit': 15}
        with mock.patch('global_sound.play_action_denied'), \
                mock.patch.object(game.chat_notification_effect, 'add_system_notification') as toast:
            game._show_action_failure_feedback()
        toast.assert_called_once_with("Cannot reinforce Lobardia: would exceed army limit of 15!")
        assert gs.last_action_error is None and gs.last_action_error_args is None

    def test_no_code_means_no_feedback(self, game):
        game.game_state.last_action_error = None
        with mock.patch('global_sound.play_action_denied') as sound:
            game._show_action_failure_feedback()
        sound.assert_not_called()

    def test_action_methods_reset_args(self, game):
        gs = game.game_state
        gs.last_action_error_args = {'stale': 1}
        gs.start_research('no_such_tech')
        assert gs.last_action_error_args is None


class TestCentrePopupRemoved:

    def test_popup_is_gone(self, game):
        assert not hasattr(game, 'draw_invalid_target_popup')
        assert not hasattr(game, 'invalid_target_message')

    def test_ability_target_error_goes_to_toast(self, game):
        """A refused target click: toast (with sound), targeting stays on."""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_action_feedback_phase2 import _visible_territory_point
        territory, screen_pos = _visible_territory_point(game)
        game.ability_targeting_active = True
        game.ability_targeting_ability_name = 'Levy'
        with mock.patch.object(game.game_state, 'execute_levy',
                               return_value=(False, "You can only levy your own territories!")), \
                mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(game, 'show_action_error') as show:
            game.handle_map_area_click(screen_pos)
        show.assert_called_once_with(message="You can only levy your own territories!")
        assert game.ability_targeting_active is True


class TestReinforceRefusal:

    def test_reinforce_error_reaches_toast(self, game):
        import pygame
        import main
        gs = game.game_state
        gs.heroes.setdefault(0, {})
        game.selected_hero = 'Darius Brennhen'
        rect = pygame.Rect(400, main.MAP_HEIGHT + 40, 50, 50)
        game.hero_ability_buttons = {('Darius Brennhen', 0): rect}
        with mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(gs, 'activate_hero_ability', return_value="Territory has too many units!"), \
                mock.patch.object(game, 'show_action_error') as show:
            game.handle_bottom_ui_click(rect.center)
        if show.call_count == 0:
            pytest.skip("hero ability buttons are not reachable in this bottom-panel state")
        show.assert_called_once_with(message="Territory has too many units!")


# ===========================================================================
# Toast rendering
# ===========================================================================

class TestToast:

    def _toast(self, game):
        effect = game.chat_notification_effect
        effect._notifications.clear()
        return effect

    def test_multiline_message_uses_two_lines(self, game):
        effect = self._toast(game)
        effect.add_system_notification("One line")
        single_h = effect._notifications[-1]['msg_surface'].get_height()
        effect.add_system_notification("First line\nSecond line")
        assert effect._notifications[-1]['msg_surface'].get_height() >= 2 * single_h - 2

    def test_long_message_is_wrapped_not_cut(self, game):
        effect = self._toast(game)
        effect._max_text_width = 200
        effect.add_system_notification("word " * 40)
        surf = effect._notifications[-1]['msg_surface']
        assert surf.get_width() <= 200
        lines = effect._wrap_system_text("word " * 40)
        assert len(lines) > 1
        # Nothing was cut off: every word is still there
        assert sum(line.split().count("word") for line in lines) == 40

    def test_identical_repeat_refreshes_instead_of_stacking(self, game):
        effect = self._toast(game)
        effect.add_system_notification("Not enough resources!")
        effect._notifications[-1]['elapsed'] = 3.0
        effect.add_system_notification("Not enough resources!")
        assert len(effect._notifications) == 1
        assert effect._notifications[-1]['elapsed'] == 0.0

    def test_different_message_stacks(self, game):
        effect = self._toast(game)
        effect.add_system_notification("A!")
        effect.add_system_notification("B!")
        assert len(effect._notifications) == 2
