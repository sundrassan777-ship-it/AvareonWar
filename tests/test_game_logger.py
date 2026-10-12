# -*- coding: utf-8 -*-
"""
Per-game JSON log (game_logger.py) - found in the log of the first multiplayer test game
(2026-10-12): its per-round records listed no battles and no buildings at all (85 battles
were fought), simultaneous rounds were filed one round late, and the round the game was
decided in was missing.

The logger now numbers rounds itself (1, 2, 3, ... in both turn modes), a round record
takes every event since the previous one, and the round in progress is written at the end.
The sequential turn counter also moves on once player 0 is knocked out (it waited for
player 0's turn, which never came again).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from game_logger import GameLogger  # noqa: E402
from game_state import GameState  # noqa: E402


def new_state(num_players=2):
    return GameState(num_players=num_players, player_is_ai=[False] + [True] * (num_players - 1),
                     player_ai_difficulty=[1] * num_players, skip_setup_phase=True)


def written_log(monkeypatch, game_logger):
    """What finalize_and_save() would write (no file)."""
    written = {}
    monkeypatch.setattr(game_logger, '_write_log_file', lambda data: written.update(data))
    game_logger.finalize_and_save()
    return written


class TestRoundRecords:

    def test_a_round_lists_its_battles_and_buildings(self):
        gs = new_state()
        log = GameLogger(gs)
        # The callers' turn numbers never matched the record's (0 in round 1, the next
        # round's number at the snapshot) - they no longer matter
        log.record_battle('Conda', {0: 3, 1: 1}, 0, 0)
        log.record_building_completed(0, 'Farm', 'Ahara', 0)
        log.record_round_snapshot(2)
        record = log.turn_data[1][0]
        assert record['battles'] == [{'territory': 'Conda', 'opponent': 1, 'won': True}]
        assert record['buildings_built'] == {'Farm': 1}
        assert log.turn_data[1][1]['battles'] == [{'territory': 'Conda', 'opponent': 0, 'won': False}]

    def test_rounds_are_numbered_from_one(self):
        gs = new_state()
        log = GameLogger(gs)
        log.record_round_snapshot(2)                         # simultaneous: the NEXT round
        log.record_hero_trained(0, 'Vearen Asford', 2)
        log.record_round_snapshot(3)
        assert sorted(log.turn_data) == [1, 2]
        assert log._all_hero_events == [(0, 'Vearen Asford', 2)]

    def test_the_round_the_game_ended_in_is_written(self, monkeypatch):
        gs = new_state()
        log = GameLogger(gs)
        log.record_round_snapshot()
        log.record_battle('Conda', {0: 3, 1: 1}, 0, 1)      # the deciding battle
        data = written_log(monkeypatch, log)
        per_turn = data['players']['0']['per_turn']
        assert sorted(per_turn, key=int) == ['1', '2']
        assert per_turn['2']['battles'][0]['territory'] == 'Conda'
        assert data['game']['total_turns'] >= 2

    def test_no_extra_round_when_nothing_happened_since(self, monkeypatch):
        gs = new_state()
        log = GameLogger(gs)
        log.record_round_snapshot()
        data = written_log(monkeypatch, log)
        assert list(data['players']['0']['per_turn']) == ['1']


class TestSequentialRounds:

    def _three_players_without_player_0(self):
        gs = new_state(num_players=3)
        territories = h.spread_territories(3)
        for player, territory in enumerate(territories):
            h.place(gs, territory, player)
        gs.phase = 'playing'
        gs.eliminated_players.add(0)
        gs.current_player = 1
        return gs

    def test_turns_still_count_once_player_0_is_out(self):
        gs = self._three_players_without_player_0()
        before = gs.turn_number
        gs._advance_to_next_player()                         # 1 -> 2
        assert gs.turn_number == before
        gs._advance_to_next_player()                         # 2 -> 1: the round is over
        assert gs.current_player == 1
        assert gs.turn_number == before + 1

    def test_the_game_log_records_those_rounds(self):
        gs = self._three_players_without_player_0()
        gs.game_logger = GameLogger(gs)
        gs._advance_to_next_player()
        gs._advance_to_next_player()
        assert list(gs.game_logger.turn_data) == [1]

    def test_a_normal_round_is_recorded_once(self):
        gs = new_state(num_players=2)
        gs.phase = 'playing'
        gs.game_logger = GameLogger(gs)
        gs._advance_to_next_player()                         # 0 -> 1
        assert gs.game_logger.turn_data == {}
        gs._advance_to_next_player()                         # 1 -> 0: round 1 is over
        assert list(gs.game_logger.turn_data) == [1] and gs.turn_number == 1
