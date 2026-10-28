# -*- coding: utf-8 -*-
"""
A battle left to fight after the game was won (owner's game of 2026-10-28, simultaneous).

The AI marched its last army out of its last territory into a neutral one, and the player
took that territory the same round. The arrivals declared the win (0 territories left:
phase 'ended') and then queued the battle at the neutral territory, the player resolving
it. The victory cinematic waits for every pending battle, but the battle marker and the
Resolve Remaining Battles button both needed phase 'playing': the game hung on the map.
Now both stay usable while the victory waits for its battles.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame  # noqa: E402
import pytest  # noqa: E402

import mp_harness as h  # noqa: E402


@pytest.fixture(scope="module")
def pygame_display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _won_with_a_battle_left():
    """
    Single-player simultaneous game as in the owner's log: player 1 (AI) holds no
    territory, its last army meets the player's at a neutral territory, the game is won.
    Returns (game, territory).
    """
    from main import Game
    from game_state import Battle
    game = Game()
    game.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                          'player_ai_difficulty': [1, 1], 'game_mode': 'simultaneous'})
    game.tutorial_mission = None
    gs = game.game_state
    gs.phase = 'playing'
    home, territory = h.spread_territories(2)
    for name, owner in list(gs.territory_owners.items()):
        if owner == 1:
            gs.territory_owners[name] = -1
    h.place(gs, home, 0, h.units('Swordsman'))
    gs.territory_owners[territory] = -1
    gs.territory_garrisons[territory] = {
        0: {'unmoved': 0, 'moved': 1, 'units': h.units('Archer', status='moved')},
        1: {'unmoved': 0, 'moved': 1, 'units': h.units('Swordsman', status='moved')},
    }
    gs.sync_legacy_garrison_data(territory)

    assert gs.check_victory() == 0          # last team standing
    assert gs.phase == 'ended'

    battle = Battle(territory)
    battle.original_owner = -1
    battle.add_army(0, 1, {'Archer': 1})
    battle.add_army(1, 1, {'Swordsman': 1})
    battle.resolver = 0
    battle.team_members_map = {0: [0], 1: [1]}
    battle.attackers = [0, 1]
    battle.is_multi_way = True
    gs.pending_battles = [battle]
    game.sim_state.sim_phase = 'resolving'
    game.battle_markers = [pygame.Rect(10, 200, 20, 20)]
    # The game loop's first frame after the win: the cinematic waits for the battles
    game.victory_sequence_pending = True
    return game, territory


class TestTheBattleStaysOpen:

    def test_the_marker_opens_the_battle(self, pygame_display):
        game, _territory = _won_with_a_battle_left()
        assert game._battles_open_after_victory()
        assert game.handle_battle_marker_click(game.battle_markers[0].center) is True
        assert game.battle_popup_visible is True
        assert game.enhanced_battle_ui is not None

    def test_the_resolve_remaining_battles_button_is_drawn(self, pygame_display):
        game, _territory = _won_with_a_battle_left()
        game.ui_renderer.draw_top_panel()
        assert game.resolve_all_battles_button is not None

    def test_fighting_it_lets_the_victory_play(self, pygame_display):
        game, territory = _won_with_a_battle_left()
        game.game_state.active_animations = []
        game.turn_announcement_effect = None
        h.open_battle(game, territory)
        h.fight(game)
        h.close_battle(game)
        assert game.game_state.pending_battles == []
        assert game.enhanced_battle_ui is None
        assert game.game_state.phase == 'ended'           # still won, no new round
        assert game._all_animations_complete()            # the cinematic can start

    def test_the_button_resolves_it_and_lets_the_victory_play(self, pygame_display):
        game, _territory = _won_with_a_battle_left()
        game.game_state.active_animations = []
        game.turn_announcement_effect = None
        game.ui_renderer.draw_top_panel()
        game._handle_resolve_all_battles_click()
        assert game.game_state.pending_battles == []
        assert game.game_state.phase == 'ended'
        assert game._all_animations_complete()


class TestOnlyWhileTheVictoryWaits:

    def test_no_battle_after_the_cinematic_started(self, pygame_display):
        game, _territory = _won_with_a_battle_left()
        game.victory_sequence_active = True
        assert not game._battles_open_after_victory()
        assert game.handle_battle_marker_click(game.battle_markers[0].center) is False
        game.ui_renderer.draw_top_panel()
        assert game.resolve_all_battles_button is None

    def test_no_battle_before_the_loop_saw_the_win(self, pygame_display):
        game, _territory = _won_with_a_battle_left()
        game.victory_sequence_pending = False
        assert not game._battles_open_after_victory()
        assert game.handle_battle_marker_click(game.battle_markers[0].center) is False
        game.ui_renderer.draw_top_panel()
        assert game.resolve_all_battles_button is None

    def test_nothing_left_to_fight(self, pygame_display):
        game, _territory = _won_with_a_battle_left()
        game.game_state.pending_battles = []
        assert not game._battles_open_after_victory()
