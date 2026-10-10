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
from player_level import (XP_MULTIPLAYER_VICTORY_BONUS, XP_VICTORY_BONUS,  # noqa: E402
                          player_level_manager)


def finished_multiplayer_game(local_index, winner, teams=None, num_players=2):
    """A finished multiplayer game as seen on the PC of `local_index`."""
    gs = GameState(num_players=num_players, player_is_ai=[False] * num_players,
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

    @pytest.mark.xfail(strict=True, reason="H6: multiplayer achievements credit the first human "
                       "(the host) on every PC, so a client's win is never counted")
    def test_client_win_is_counted_on_the_client(self, achievements):
        achievements.record_game_result(finished_multiplayer_game(local_index=1, winner=1))
        assert achievements.stats.get('multiplayer_wins', 0) == 1

    @pytest.mark.xfail(strict=True, reason="H6: the host's win is counted as a win on every "
                       "client's PC")
    def test_host_win_is_not_a_win_for_the_client(self, achievements):
        achievements.record_game_result(finished_multiplayer_game(local_index=1, winner=0))
        assert achievements.stats.get('multiplayer_wins', 0) == 0
        assert achievements.stats.get('multiplayer_games_finished', 0) == 1

    @pytest.mark.xfail(strict=True, reason="H6/M6: a team victory is credited only to the team's "
                       "representative player")
    def test_team_victory_counts_for_every_member(self, achievements):
        # Host alone on team 1; players 2 and 3 win together and player 2 is the
        # representative - the test runs on player 3's PC
        game = finished_multiplayer_game(local_index=2, winner=1, teams=[1, 0, 0], num_players=3)
        achievements.record_game_result(game)
        assert achievements.stats.get('multiplayer_wins', 0) == 1


class TestPlayerLevel:

    def test_client_win_pays_the_victory_bonus(self):
        """Already correct (player_level reads gs.local_player_index); kept as a guard."""
        game = finished_multiplayer_game(local_index=1, winner=1)
        bonus = player_level_manager._calculate_end_bonus(game, game.game_state, 1, False, True, None)
        assert bonus == XP_MULTIPLAYER_VICTORY_BONUS   # 1 human vs 1 human: doubled

    @pytest.mark.xfail(strict=True, reason="M6: team-victory XP goes only to the team's "
                       "representative; allies get the defeat bonus")
    def test_team_victory_pays_every_member(self):
        game = finished_multiplayer_game(local_index=1, winner=0, teams=[0, 0, 1], num_players=3)
        bonus = player_level_manager._calculate_end_bonus(game, game.game_state, 1, False, True, None)
        assert bonus == XP_VICTORY_BONUS          # 2 humans vs 1: not doubled
