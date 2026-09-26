# -*- coding: utf-8 -*-
"""
Tests: "Our Hero, X, has been slain in Y!" notification.

A hero dies when an enemy captures its Keep (battle) or hits it with Regicide.
game_state records each death in hero_death_events; main.py drains that list every
frame and shows the local player a red toast for their OWN heroes — without the
denial sound (it's news, not a refused action). Demolishing your own Keep kills its
hero too, but that was the player's choice: no toast.
"""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
# conftest.py autouse fixture handles load_polygons() + cleanup

from config.action_error_messages import format_action_error
from game_state import GameState, Battle

KEEP_TERRITORY = "Lobardia"
HERO = 'Halon Nextroy'


def _hero_in_keep(gs, player, territory=KEEP_TERRITORY, hero=HERO):
    gs.territory_owners[territory] = player
    gs.buildings.setdefault(territory, {})[0] = 'Keep'
    gs.heroes.setdefault(player, {})[hero] = {'keep_territory': territory, 'keep_plot': 0}
    gs.hero_ownership[player].add(hero)


@pytest.fixture
def gs():
    state = GameState(num_players=2, player_is_ai=[False, False],
                      player_ai_difficulty=[1, 1], skip_setup_phase=True)
    state.current_player = 0
    return state


class TestDeathEvents:

    def test_keep_destroyed_by_enemy_records_death(self, gs):
        _hero_in_keep(gs, 0)
        gs.kill_heroes_in_keep(KEEP_TERRITORY, 0, 0)
        assert gs.hero_death_events == [(0, HERO, KEEP_TERRITORY)]

    def test_battle_capture_records_death(self, gs):
        """Full path: an enemy wins the battle for the Keep's territory."""
        _hero_in_keep(gs, 0)
        gs.territory_owners["Nordia"] = 0  # spare territory: no elimination mid-battle
        units = [gs._make_unit("Swordsman", i, 'ready') for i in range(1)]
        gs.territory_garrisons[KEEP_TERRITORY] = {}
        gs.add_garrison(KEEP_TERRITORY, 0, unmoved=1, moved=0, units=units)
        gs.army_units[KEEP_TERRITORY] = units[:]
        gs.armies[KEEP_TERRITORY] = 1
        gs.armies_unmoved[KEEP_TERRITORY] = 1

        battle = Battle(KEEP_TERRITORY)
        battle.original_owner = 0
        battle.add_army(0, 1, {"Swordsman": 1})
        battle.add_army(1, 20, {"Swordsman": 20})
        gs.pending_battles.append(battle)
        gs.resolve_battle(len(gs.pending_battles) - 1)

        assert gs.territory_owners[KEEP_TERRITORY] == 1
        assert (0, HERO, KEEP_TERRITORY) in gs.hero_death_events

    def test_regicide_kill_records_death(self, gs):
        _hero_in_keep(gs, 1)
        assert gs.execute_regicide(KEEP_TERRITORY, 0)[0] is True
        assert gs.hero_death_events == [(1, HERO, KEEP_TERRITORY)]

    def test_demolishing_own_keep_is_not_announced(self, gs):
        _hero_in_keep(gs, 0)
        gs.destroy_building(KEEP_TERRITORY, 0)
        assert HERO not in gs.heroes.get(0, {})     # the hero still dies...
        assert gs.hero_death_events == []           # ...but no "slain" toast


class TestMessage:

    def test_text(self):
        assert format_action_error('hero_slain', hero=HERO, territory=KEEP_TERRITORY) == \
            f"Our Hero, {HERO}, has been slain in {KEEP_TERRITORY}!"


# ===========================================================================
# main.py: drained every frame, shown to the hero's owner only
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
    return g


class TestToast:

    def test_own_hero_death_shows_toast_without_denial_sound(self, game):
        game.game_state.hero_death_events = [(0, HERO, KEEP_TERRITORY)]
        with mock.patch.object(game.chat_notification_effect, 'add_system_notification') as toast, \
                mock.patch('global_sound.play_action_denied') as sound:
            game._show_hero_death_notifications()
        toast.assert_called_once_with(f"Our Hero, {HERO}, has been slain in {KEEP_TERRITORY}!")
        sound.assert_not_called()
        assert game.game_state.hero_death_events == []

    def test_other_players_hero_death_is_silent(self, game):
        game.game_state.hero_death_events = [(1, HERO, KEEP_TERRITORY)]
        with mock.patch.object(game.chat_notification_effect, 'add_system_notification') as toast:
            game._show_hero_death_notifications()
        toast.assert_not_called()
        assert game.game_state.hero_death_events == []

    def test_two_heroes_two_toasts(self, game):
        game.game_state.hero_death_events = [(0, HERO, KEEP_TERRITORY), (0, 'Aidam Narn', 'Nordia')]
        with mock.patch.object(game.chat_notification_effect, 'add_system_notification') as toast:
            game._show_hero_death_notifications()
        assert toast.call_count == 2


# ===========================================================================
# Multiplayer: the defender's client applies BATTLE_RESOLVE instead of running
# the battle, so the slain heroes ride along in the Battle Report
# ===========================================================================

class TestBattleReportCarriesSlainHeroes:

    def test_report_lists_the_slain_hero(self, gs):
        _hero_in_keep(gs, 0)
        gs.territory_owners["Nordia"] = 0
        units = [gs._make_unit("Swordsman", 0, 'ready')]
        gs.territory_garrisons[KEEP_TERRITORY] = {}
        gs.add_garrison(KEEP_TERRITORY, 0, unmoved=1, moved=0, units=units)
        gs.army_units[KEEP_TERRITORY] = units[:]
        gs.armies[KEEP_TERRITORY] = 1
        gs.armies_unmoved[KEEP_TERRITORY] = 1
        battle = Battle(KEEP_TERRITORY)
        battle.original_owner = 0
        battle.add_army(0, 1, {"Swordsman": 1})
        battle.add_army(1, 20, {"Swordsman": 20})
        gs.pending_battles.append(battle)
        gs.resolve_battle(len(gs.pending_battles) - 1)

        report = gs.last_battle_reports[0]
        assert report['defender'] == 0
        assert report['heroes_slain'] == [HERO]

    def test_report_without_deaths_has_empty_list(self, gs):
        report = gs._make_battle_report(
            territory=KEEP_TERRITORY, defender=0, attacker=1, held=True, units_lost=0,
            units_remaining=1, structures_destroyed=0, structures_captured=0,
            structures_remaining=0, unit_breakdown={}, attacker_lost=1, attacker_survivors=0)
        assert report['heroes_slain'] == []


class TestDefendingClient:

    @pytest.fixture
    def client(self, game):
        """Act as player 1's multiplayer client, defending against player 0."""
        game.multiplayer_mode = True
        game.local_player_index = 1
        game.network_connection = None
        game.game_state.player_is_ai = [False, False]
        yield game
        game.multiplayer_mode = False
        game.local_player_index = None

    def _resolve_message(self, game, territory, heroes_slain):
        from game_state import Battle
        from network_config import MessageType
        battle = Battle(territory)
        battle.original_owner = 1
        battle.add_army(1, 1, {'Swordsman': 1})
        battle.add_army(0, 9, {'Swordsman': 9})
        game.game_state.pending_battles = [battle]
        game.game_state.territory_owners["Nordia"] = 1  # keep player 1 alive
        report = {
            'territory': territory, 'turn_number': 2, 'defender': 1, 'attacker': 0,
            'held': False, 'units_lost': 1, 'units_remaining': 0,
            'structures_destroyed': 1, 'structures_captured': 0, 'structures_remaining': 0,
            'unit_breakdown': {'Swordsman': {'original': 1, 'survived': 0, 'lost': 1}},
            'attacker_lost': 1, 'attacker_survivors': 8,
            'defender_lost': 1, 'defender_survivors': 0,
            'heroes_slain': heroes_slain,
        }
        return {'type': MessageType.BATTLE_RESOLVE, 'seq': 1, 'data': {
            'territory': territory, 'winner': 0, 'surviving_armies': 8,
            'new_owner': 0, 'battle_reports': [report]}}

    def test_defender_client_gets_the_toast(self, client):
        client.game_state.hero_death_events = []
        client._handle_network_message(self._resolve_message(client, KEEP_TERRITORY, [HERO]))
        assert client.game_state.hero_death_events == [(1, HERO, KEEP_TERRITORY)]
        with mock.patch.object(client.chat_notification_effect, 'add_system_notification') as toast:
            client._show_hero_death_notifications()
        toast.assert_called_once_with(f"Our Hero, {HERO}, has been slain in {KEEP_TERRITORY}!")

    def test_old_report_without_field_is_harmless(self, client):
        client.game_state.hero_death_events = []
        message = self._resolve_message(client, KEEP_TERRITORY, [])
        del message['data']['battle_reports'][0]['heroes_slain']
        client._handle_network_message(message)
        assert client.game_state.hero_death_events == []
