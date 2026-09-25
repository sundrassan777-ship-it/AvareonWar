# -*- coding: utf-8 -*-
"""
Tests: Phase 6 of the Action Failure Feedback effort — hero abilities.

The execute_* refusal texts used to be written inline in game_state/heroes.py.
They now come from config/action_error_messages.py via _ability_refusal(), which
also records last_action_error (+ args) so main.py shows the denial sound + toast.
The (False, text) return shape is unchanged for the AI and network callers.

Regicide on a Keep without a hero still counts as a cast (cooldown spent, by
design) but now records 'regicide_no_hero' so the caster gets a toast.
"""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import map_data
# conftest.py autouse fixture handles load_polygons() + cleanup

from config.action_error_messages import ACTION_ERROR_MESSAGES, format_action_error
from game_state import GameState

MINE = "Lobardia"
ENEMY = "Lentria"


def _units(gs, territory, player, count):
    gs.territory_owners[territory] = player
    units = [gs._make_unit("Swordsman", i, 'ready') for i in range(count)]
    gs.territory_garrisons[territory] = {}
    gs.add_garrison(territory, player, unmoved=count, moved=0, units=units)
    gs.army_units[territory] = units[:]
    gs.armies[territory] = count
    gs.armies_unmoved[territory] = count


def _hero(gs, player, hero, keep_territory, keep_plot=0):
    gs.territory_owners[keep_territory] = player
    gs.buildings.setdefault(keep_territory, {})[keep_plot] = 'Keep'
    gs.heroes.setdefault(player, {})[hero] = {'keep_territory': keep_territory, 'keep_plot': keep_plot}
    gs.hero_ownership[player].add(hero)


@pytest.fixture
def gs():
    state = GameState(num_players=2, player_is_ai=[False, False],
                      player_ai_difficulty=[1, 1], skip_setup_phase=True)
    state.current_player = 0
    state.territory_owners[MINE] = 0
    state.territory_owners[ENEMY] = 1
    return state


def _assert_refused(result, gs, code, **fmt):
    assert result[0] is False
    assert gs.last_action_error == code
    assert (gs.last_action_error_args or {}) == fmt
    assert result[1] == format_action_error(code, **fmt)


# ===========================================================================
# Refusal codes
# ===========================================================================

class TestAbilityRefusalCodes:

    def test_levy_on_enemy_land(self, gs):
        _assert_refused(gs.execute_levy(ENEMY, 0), gs, 'ability_not_own_territory')

    def test_relentless_charge_on_enemy_land(self, gs):
        _assert_refused(gs.execute_relentless_charge(ENEMY, 0), gs, 'ability_not_own_territory')

    def test_relentless_charge_too_many_units(self, gs):
        _units(gs, MINE, 0, 12)
        _assert_refused(gs.execute_relentless_charge(MINE, 0), gs, 'charge_too_many', current=12)

    def test_decisive_strike_own_territory(self, gs):
        _assert_refused(gs.execute_decisive_strike(MINE, 0), gs, 'ability_own_territory')

    def test_decisive_strike_neutral(self, gs):
        gs.territory_owners[ENEMY] = -1
        _assert_refused(gs.execute_decisive_strike(ENEMY, 0), gs, 'ability_neutral')

    def test_decisive_strike_min_units(self, gs):
        _units(gs, ENEMY, 1, 1)
        _assert_refused(gs.execute_decisive_strike(ENEMY, 0), gs, 'strike_min_units', count=1)

    def test_aggressive_diplomacy_too_many(self, gs):
        _units(gs, ENEMY, 1, 3)
        _assert_refused(gs.execute_aggressive_diplomacy(ENEMY, 0), gs, 'diplomacy_too_many', current=3)

    def test_aggressive_diplomacy_keep(self, gs):
        gs.buildings.setdefault(ENEMY, {})[0] = 'Keep'
        _assert_refused(gs.execute_aggressive_diplomacy(ENEMY, 0), gs, 'diplomacy_keep')

    def test_regicide_no_keep(self, gs):
        _assert_refused(gs.execute_regicide(ENEMY, 0), gs, 'regicide_no_keep')

    def test_valorous_charge_full_destination(self, gs):
        _hero(gs, 0, 'Serthus Diarcess', MINE)
        _units(gs, MINE, 0, 3)
        other = "Venexia"
        _units(gs, other, 0, 15)
        _assert_refused(gs.execute_valorous_charge(other, 0), gs, 'valorous_full', territory=other, count=15)

    def test_reinforce_keep_full(self, gs):
        _hero(gs, 0, 'Darius Brennhen', MINE)
        _units(gs, MINE, 0, 14)
        _assert_refused(gs.execute_reinforce(0), gs, 'reinforce_too_many', current=14)

    def test_text_comes_from_the_message_table(self, gs, monkeypatch):
        """Editing the table changes what the ability returns (no inline copies left)."""
        monkeypatch.setitem(ACTION_ERROR_MESSAGES, 'ability_not_own_territory', "Edited text!")
        assert gs.execute_levy(ENEMY, 0) == (False, "Edited text!")

    def test_result_shape_unchanged_for_ai(self, gs):
        result = gs.execute_levy(ENEMY, 0)
        assert isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], str)


class TestRegicideMiss:

    def test_no_hero_is_a_cast_with_a_notice(self, gs):
        gs.buildings.setdefault(ENEMY, {})[0] = 'Keep'
        result = gs.execute_regicide(ENEMY, 0)
        assert result[0] is True               # still a cast -> cooldown spent (by design)
        assert gs.last_action_error == 'regicide_no_hero'

    def test_hit_has_no_notice(self, gs):
        _hero(gs, 1, 'Halon Nextroy', ENEMY)
        gs.last_action_error = None
        assert gs.execute_regicide(ENEMY, 0)[0] is True
        assert gs.last_action_error is None


class TestActivateReinforce:

    def test_activate_records_reinforce_code(self, gs):
        _hero(gs, 0, 'Darius Brennhen', MINE)
        _units(gs, MINE, 0, 14)
        result = gs.activate_hero_ability('Darius Brennhen', 0)
        assert isinstance(result, str)
        assert gs.last_action_error == 'reinforce_too_many'
        assert gs.last_action_error_args == {'current': 14}


# ===========================================================================
# main.py wiring (real Game)
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


def _target(game, hero, ability_name, ability_index, owner):
    from test_action_feedback_phase2 import _visible_territory_point
    territory, pos = _visible_territory_point(game)
    game.game_state.territory_owners[territory] = owner
    game.ability_targeting_active = True
    game.ability_targeting_hero = hero
    game.ability_targeting_ability_name = ability_name
    game.ability_targeting_ability_index = ability_index
    return territory, pos


class TestTargetingToast:

    def test_refused_target_shows_coded_toast(self, game):
        territory, pos = _target(game, 'Halon Nextroy', 'Levy', 1, owner=1)
        with mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(game, 'show_action_error') as show:
            game.handle_map_area_click(pos)
        show.assert_called_once_with('ability_not_own_territory')
        assert game.ability_targeting_active is True   # pick another target

    def test_stale_code_is_not_shown_on_success(self, game):
        territory, pos = _target(game, 'Halon Nextroy', 'Levy', 1, owner=0)
        _hero(game.game_state, 0, 'Halon Nextroy', territory)
        game.game_state.last_action_error = 'gold'   # left behind by e.g. an AI call
        with mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(game, 'show_action_error') as show:
            game.handle_map_area_click(pos)
        show.assert_not_called()
        assert game.ability_targeting_active is False

    def test_regicide_miss_toasts_and_spends_cooldown(self, game):
        territory, pos = _target(game, 'Aidam Narn', 'Regicide', 1, owner=1)
        gs = game.game_state
        _hero(gs, 0, 'Aidam Narn', "Venexia")
        gs.buildings.setdefault(territory, {})[0] = 'Keep'
        with mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(game, 'show_action_error') as show:
            game.handle_map_area_click(pos)
        show.assert_called_once_with('regicide_no_hero')
        assert gs.hero_ability_cooldowns[0]['Aidam Narn']['Regicide'] > 0
