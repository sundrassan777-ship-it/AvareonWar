# -*- coding: utf-8 -*-
"""
Multiplayer progression tests (pre-launch multiplayer audit): achievements and
player-level XP must credit the LOCAL player of each PC, and a team victory is a
victory for every member of the winning team.

Uses a real GameState with a lightweight stand-in for Game (achievements and XP
only read game_state + the multiplayer flags). Nothing is written to disk.

xfail(strict=True) tests reproduce confirmed audit findings (ID in the reason); the
fixing phase removes the marker.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from achievement_manager import achievement_manager  # noqa: E402
from game_state import GameState  # noqa: E402
from player_level import (DISCONNECT_FARMING_XP_THRESHOLD,  # noqa: E402
                          XP_MULTIPLAYER_VICTORY_BONUS, XP_VICTORY_BONUS,
                          has_human_opponent, player_level_manager)


def finished_multiplayer_game(local_index, winner, teams=None, num_players=2, ai=None):
    """A finished multiplayer game as seen on the PC of `local_index` (`ai`: which
    players are computer players, default none)."""
    gs = GameState(num_players=num_players, player_is_ai=list(ai or [False] * num_players),
                   player_ai_difficulty=[1] * num_players, player_teams=teams,
                   skip_setup_phase=True, network_mode=True, local_player_index=local_index)
    gs.phase = 'ended'
    gs.winner = winner
    return SimpleNamespace(game_state=gs, multiplayer_mode=True, network_connection=object(),
                           local_player_index=local_index, tutorial_mission=None)


@pytest.fixture
def achievements(monkeypatch):
    """The real achievement manager with private stats and no saving / unlocking."""
    monkeypatch.setattr(achievement_manager, 'stats', {})
    monkeypatch.setattr(achievement_manager, 'save', lambda: None)
    monkeypatch.setattr(achievement_manager, '_check_new_achievements', lambda: [])
    return achievement_manager


class TestAchievements:

    def test_client_win_is_counted_on_the_client(self, achievements):
        achievements.record_game_result(finished_multiplayer_game(local_index=1, winner=1))
        assert achievements.stats.get('multiplayer_wins', 0) == 1

    def test_host_win_is_not_a_win_for_the_client(self, achievements):
        achievements.record_game_result(finished_multiplayer_game(local_index=1, winner=0))
        assert achievements.stats.get('multiplayer_wins', 0) == 0
        assert achievements.stats.get('multiplayer_games_finished', 0) == 1

    def test_team_victory_counts_for_every_member(self, achievements):
        # Host alone on team 1; players 2 and 3 win together and player 2 is the
        # representative - the test runs on player 3's PC
        game = finished_multiplayer_game(local_index=2, winner=1, teams=[1, 0, 0], num_players=3)
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 1


class TestHumanOpponentRequired:
    """Multiplayer wins ("A Step Into the World" and the other Conquest achievements)
    need at least one human enemy - a host alone against AI slots used to earn them."""

    def test_win_against_ai_only_is_not_a_multiplayer_win(self, achievements):
        game = finished_multiplayer_game(local_index=0, winner=0, num_players=3,
                                         ai=[False, True, True])
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 0
        assert achievements.stats.get('multiplayer_games_finished', 0) == 0

    def test_human_ally_against_ai_enemies_does_not_count(self, achievements):
        game = finished_multiplayer_game(local_index=1, winner=0, teams=[0, 0, 1],
                                         num_players=3, ai=[False, False, True])
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 0

    def test_one_human_enemy_among_ais_counts(self, achievements):
        game = finished_multiplayer_game(local_index=0, winner=0, num_players=3,
                                         ai=[False, True, False])
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 1
        assert achievements.stats.get('multiplayer_games_finished', 0) == 1

    def test_human_enemy_taken_over_by_the_ai_after_playing_counts(self, achievements):
        game = finished_multiplayer_game(local_index=0, winner=0, ai=[False, True])
        game.game_state.ai_takeover_xp = {1: DISCONNECT_FARMING_XP_THRESHOLD + 10}
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 1

    def test_human_enemy_who_left_at_once_does_not_count(self, achievements):
        game = finished_multiplayer_game(local_index=0, winner=0, ai=[False, True])
        game.game_state.ai_takeover_xp = {1: 0}
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 0

    def test_loss_against_ai_only_is_not_counted_either(self, achievements):
        game = finished_multiplayer_game(local_index=0, winner=1, ai=[False, True])
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_games_finished', 0) == 0

    def test_helper_ignores_bad_player_index(self):
        gs = finished_multiplayer_game(local_index=0, winner=0).game_state
        assert has_human_opponent(gs, 0)
        assert not has_human_opponent(gs, None)
        assert not has_human_opponent(gs, 5)


class TestPlayerLevel:

    def test_client_win_pays_the_victory_bonus(self):
        """Already correct (player_level reads gs.local_player_index); kept as a guard."""
        game = finished_multiplayer_game(local_index=1, winner=1)
        bonus = player_level_manager._calculate_end_bonus(game, game.game_state, 1, False, True, None)
        assert bonus == XP_MULTIPLAYER_VICTORY_BONUS   # 1 human vs 1 human: doubled

    def test_team_victory_pays_every_member(self):
        game = finished_multiplayer_game(local_index=1, winner=0, teams=[0, 0, 1], num_players=3)
        bonus = player_level_manager._calculate_end_bonus(game, game.game_state, 1, False, True, None)
        assert bonus == XP_VICTORY_BONUS          # 2 humans vs 1: not doubled
