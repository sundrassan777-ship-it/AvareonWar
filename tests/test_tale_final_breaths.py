# -*- coding: utf-8 -*-
"""
Tests for Book of Tales — Tale II: "Final Breaths" (tale_final_breaths.py).

Covers the scenario setup (ownership, plots, armies, techs, taxation), the
Kerunian per-target attack cap (generic ai_military.mission_ai_attack_cap hook,
planner + last-line guard), the Heroes ban (incl. the built-in AI gate), the
Nordian Rebels (rebellion schedule, transfer, passive turns, never eliminated),
victory/defeat sentinels, the Turns widget and save/restore.

A real Game on Avareon is needed (plots, adjacencies, the mouse handler), with
Campaign Mission 3's background. Game construction is slow, so it is module
scoped and each test gets a freshly set-up Tale on top of it. conftest reloads
Avareon before every test, which is the map this Tale plays on.
"""

import json
import os
import random
import sys
from collections import Counter

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import map_data  # noqa: E402
from campaign_mission_3 import MISSION_3_TERRITORIES  # noqa: E402
from tale_final_breaths import (  # noqa: E402
    TaleFinalBreaths, FACTION_TERRITORIES, PLAYER, RED, REBELS, HOLD_TURNS,
    OBJECTIVE_TERRITORIES, REBELLION_IMMUNE, PLAYER_TECHS,
    attack_cap_for_turn, rebellions_for_turn,
)

# Mirrors main.py _TALE_REGISTRY['tale_2']['config']
TALE_CONFIG = {
    'map_id': 'avareon',
    'num_players': 3,
    'player_is_ai': [False, True, True],
    'player_ai_difficulty': [0, 2, 0],
    'player_teams': [0, 1, 2],
    'win_condition': 'Total Conquest',
    'taxation_level': 0,
    'player1_territory': 'Lunedale',
    'player2_territory': 'Affrancian Uplands',
}

EXTRA_NEUTRALS = ("Zjoal Islands", "Leimarch", "Liadnon", "Ahtep", "Anodia")


@pytest.fixture(scope='module')
def game():
    pygame.init()
    map_data.load_map('avareon')
    from main import Game
    instance = Game(campaign_map='assets/CampaignMaps/Campaign3Map.png')
    instance.initialize_game(dict(TALE_CONFIG))
    yield instance
    map_data.set_tutorial_mission(None)
    map_data.clear_enabled_territories()
    pygame.display.quit()
    pygame.quit()


@pytest.fixture(autouse=True)
def _unwire():
    yield
    map_data.set_tutorial_mission(None)
    map_data.clear_enabled_territories()


def _new_tale(game, seed=0):
    """Fresh Tale on the shared Game, wired in exactly as main.py does it."""
    gs = game.game_state
    gs.movement_orders = []
    gs.pending_battles = []
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = PLAYER
    gs.turn_number = 0
    gs.turn_announcement_active = False
    gs.winner = -1
    gs.eliminated_players = set()
    for player in range(gs.num_players):
        gs.player_tech_researched[player] = set()
        gs.player_tech_available[player] = {'tech_0_0', 'tech_1_0', 'tech_2_0'}
        gs.player_command_limit[player] = 75
        gs.player_planning_time_limit[player] = 90
    game.battle_popup_visible = False
    game.game_menu_visible = False
    game.options_menu_visible = False
    game.clicked_element = None
    mission = TaleFinalBreaths(gs, game, rng=random.Random(seed))
    game.tutorial_mission = mission
    gs.tutorial_mission = mission
    map_data.set_tutorial_mission(mission)
    return mission


@pytest.fixture
def tale(game):
    return _new_tale(game)


def _owned(gs, player):
    return [t for t, o in gs.territory_owners.items() if o == player]


def _units(gs, territory, player):
    return gs.territory_garrisons.get(territory, {}).get(player, {}).get('units', [])


def _player_turn(game, tale, turn_number):
    """Start the player's turn with this gs.turn_number (visible turn = +1)."""
    gs = game.game_state
    gs.current_player = PLAYER
    gs.turn_number = turn_number
    tale.notify_event('turn_announcement_done', player_index=PLAYER)


def _run_until_exit(tale, frames=400):
    for _ in range(frames):
        result = tale.update(0.05)
        if result:
            return result
    return None


# ============================================================================
# SETUP
# ============================================================================

class TestSetup:

    def test_every_listed_territory_exists_in_mission_3(self):
        for territories in FACTION_TERRITORIES.values():
            for territory in territories:
                assert territory in MISSION_3_TERRITORIES, territory
                assert map_data.get_plots(territory), territory

    def test_ownership(self, game, tale):
        gs = game.game_state
        assert sorted(_owned(gs, PLAYER)) == sorted(FACTION_TERRITORIES[PLAYER])
        assert sorted(_owned(gs, RED)) == sorted(FACTION_TERRITORIES[RED])
        assert _owned(gs, REBELS) == []
        for territory in EXTRA_NEUTRALS:
            assert gs.territory_owners[territory] == -1
            assert gs.get_territory_total_armies(territory) == 0
            assert not gs.buildings[territory]

    def test_only_mission_3_territories_enabled(self, tale):
        for territory in MISSION_3_TERRITORIES:
            assert map_data.is_territory_enabled(territory)
            assert tale.is_territory_interactive(territory)
        # get_all_territories() is itself filtered: use the full economic data list
        assert sorted(map_data.get_all_territories()) == sorted(MISSION_3_TERRITORIES)
        outside = [t for t in map_data.TERRITORY_INCOME if t not in MISSION_3_TERRITORIES]
        assert outside and not any(map_data.is_territory_enabled(t) for t in outside)

    def test_gold_command_and_taxation(self, game, tale):
        gs = game.game_state
        assert gs.player_gold[:3] == [200, 7000, 0]
        assert gs.player_command_limit[RED] == 200
        # 100% taxation on the Zjoal Empire only
        assert gs.get_taxation_level(PLAYER) == 4
        assert gs.get_taxation_level(RED) == 0 and gs.get_taxation_level(REBELS) == 0
        gs.apply_taxation(PLAYER)
        gs.apply_taxation(RED)
        assert gs.player_gold[PLAYER] == 0 and gs.player_gold[RED] == 7000

    def test_keeps_and_castle(self, game, tale):
        gs = game.game_state
        keeps = sorted(t for t, plots in gs.buildings.items() if 'Keep' in plots.values())
        assert keeps == sorted(["Lunedale", "Affrancian Uplands", "March of Auverne", "Carnae"])
        assert gs.castle_upgrades == {'Lunedale': {0: True}}
        assert gs.player_has_castle(PLAYER) and not gs.player_has_castle(RED)

    @pytest.mark.parametrize('seed', [0, 1, 7])
    def test_plot_mix(self, game, seed):
        _new_tale(game, seed=seed)
        gs = game.game_state

        def mix(faction):
            return Counter(b for t in FACTION_TERRITORIES[faction] for b in gs.buildings[t].values())

        # Non-Keep plots: Zjoal 27 -> 20/3/3 + 1 empty; Kerunian 19 -> 14/2/2/1 Square
        assert mix(PLAYER) == Counter({'Barracks': 20, 'Mine': 3, 'Farm': 3, 'Keep': 1})
        assert mix(RED) == Counter({'Barracks': 14, 'Mine': 2, 'Farm': 2, 'Square': 1, 'Keep': 3})
        empty = sum(len(map_data.get_plots(t)) - len(gs.buildings[t]) for t in FACTION_TERRITORIES[PLAYER])
        assert empty == 1

    def test_armies_have_one_captain_and_the_right_size(self, game, tale):
        gs = game.game_state
        expected = {"Affrancian Uplands": 12, "March of Auverne": 12, "Lunedale": 12, "Free Cities": 12,
                    "Vense": 8, "Carnae": 8, "Orlais": 8, "Cualus": 8, "Damlére": 8}
        for faction, default in ((PLAYER, 3), (RED, 5)):
            for territory in FACTION_TERRITORIES[faction]:
                units = _units(gs, territory, faction)
                assert len(units) == expected.get(territory, default), territory
                assert sum(u['type'] == 'Captain' for u in units) == 1, territory
        ids = [u['id'] for f in (PLAYER, RED) for t in FACTION_TERRITORIES[f] for u in _units(gs, t, f)]
        assert len(ids) == len(set(ids)) == 79 + 88

    def test_player_techs_and_effects(self, game, tale):
        gs = game.game_state
        assert gs.player_tech_researched[PLAYER] == set(PLAYER_TECHS)
        assert gs.player_tech_available[PLAYER] == {'tech_0_3', 'tech_2_5'}
        assert gs.player_tech_researched[RED] == set()
        # A sample of effects applied through apply_tech_effect()
        assert gs.player_barracks_full_refund[PLAYER] is True         # Makeshift Barracks
        assert gs.player_farm_destruction_gold_bonus[PLAYER] > 0      # Raze the Countryside
        assert gs.player_divide_conquer_bonus[PLAYER] is True
        assert gs.player_command_limit[PLAYER] == 75 + 35             # Improved Command I
        assert gs.player_planning_time_limit[PLAYER] == 90 + 60       # Master Planner I + II
        assert gs.player_hero_limit[PLAYER] == 4 and gs.player_captain_cost_discount[PLAYER] == 33

    def test_demolishing_barracks_refunds_in_full(self, game, tale):
        gs = game.game_state
        territory, plot = next((t, i) for t in FACTION_TERRITORIES[PLAYER]
                               for i, b in gs.buildings[t].items() if b == 'Barracks')
        cost = gs.get_building_cost('Barracks', PLAYER)
        gold = gs.player_gold[PLAYER]
        gs.destroy_building(territory, plot)
        assert gs.player_gold[PLAYER] == gold + cost
        assert plot not in gs.buildings[territory]


# ============================================================================
# KERUNIAN ATTACK CAP
# ============================================================================

class TestAttackCap:

    def test_cap_formula(self):
        assert [attack_cap_for_turn(t) for t in (1, 2, 3, 4, 10, 14, 15)] == [10, 11, 11, 12, 15, 17, 17]

    def test_cap_only_for_kerunians_and_only_on_foreign_land(self, game, tale):
        from ai_military import mission_ai_attack_cap
        gs = game.game_state
        gs.turn_number = 9                                    # visible turn 10
        assert tale.get_ai_attack_cap(RED, 'Lunedale') == 15
        assert tale.get_ai_attack_cap(REBELS, 'Lunedale') is None
        assert mission_ai_attack_cap(gs, RED, 'Lunedale') == 15
        assert mission_ai_attack_cap(gs, RED, 'Zjoal Islands') == 15     # neutral too
        assert mission_ai_attack_cap(gs, RED, 'Carnae') is None          # own land
        tale.active = False
        assert mission_ai_attack_cap(gs, RED, 'Lunedale') is None

    def test_planner_respects_cap_per_target(self, game, tale):
        from ai_player import AIPlayer
        gs = game.game_state
        gs.current_player = RED
        ai = AIPlayer(RED, 2)
        try:
            for turn_number in (0, 9):
                gs.turn_number = turn_number
                cap = attack_cap_for_turn(turn_number + 1)
                attacks = ai.military.attack_planner.select_attack_targets(gs, max_attacks=7)
                per_target = Counter()
                for _frm, to, count in attacks:
                    per_target[to] += count
                assert attacks and all(n <= cap for n in per_target.values()), (turn_number, per_target)
        finally:
            ai._thread_pool.shutdown(wait=False)

    def test_move_guard_trims_to_remaining_room(self, game, tale, monkeypatch):
        import tale_final_breaths
        from ai_player import AIPlayer
        # A small cap so the stacks on the map can exceed it (the mechanism, not the tuning)
        monkeypatch.setattr(tale_final_breaths, 'ATTACK_CAP_BASE', 3)
        gs = game.game_state
        gs.current_player = RED
        gs.turn_number = 3                                    # visible turn 4 -> cap 5
        cap = attack_cap_for_turn(4)
        ai = AIPlayer(RED, 2)
        try:
            ai._execute_action_internal(gs, 'move', {'from': 'Affrancian Uplands', 'to': 'Lunedale',
                                                     'army_count': 10})
            sent = sum(o.army_count for o in gs.movement_orders
                       if o.player == RED and o.to_territory == 'Lunedale')
            assert sent == cap
            # Cap used up: a second order gets nothing more against Lunedale
            ok = ai._execute_action_internal(gs, 'move', {'from': 'Affrancian Uplands',
                                                          'to': 'Lunedale', 'army_count': 2})
            assert ok is False
            assert sum(o.army_count for o in gs.movement_orders
                       if o.player == RED and o.to_territory == 'Lunedale') == cap
            # Another target has its own allowance (Carnae holds 8 units)
            ai._execute_action_internal(gs, 'move', {'from': 'Carnae', 'to': 'Vense', 'army_count': 7})
            assert sum(o.army_count for o in gs.movement_orders
                       if o.player == RED and o.to_territory == 'Vense') == cap
        finally:
            ai._thread_pool.shutdown(wait=False)

    def test_reinforcing_own_land_is_not_capped(self, game, tale):
        from ai_player import AIPlayer
        gs = game.game_state
        gs.current_player = RED
        ai = AIPlayer(RED, 2)
        try:
            ai._execute_action_internal(gs, 'move', {'from': 'March of Auverne', 'to': 'Affrancian Uplands',
                                                     'army_count': 3})
        finally:
            ai._thread_pool.shutdown(wait=False)
        assert sum(o.army_count for o in gs.movement_orders if o.player == RED) == 3


def _red_turn(game, tale, turn_number):
    """Start the Kerunians' turn with this gs.turn_number."""
    gs = game.game_state
    gs.current_player = RED
    gs.turn_number = turn_number
    tale.notify_event('turn_announcement_done', player_index=RED)


def _red_orders(gs, target=None):
    return sum(o.army_count for o in gs.movement_orders
               if o.player == RED and (target is None or o.to_territory == target))


class TestForcedAttacks:

    def test_forced_attack_hits_an_objective_up_to_the_cap(self, game, tale):
        gs = game.game_state
        _red_turn(game, tale, 0)
        # Lunedale is the only objective the Kerunians border (from Affrancian
        # Uplands, 12 units, 1 kept home): min(cap 10, 11 spare) units
        assert _red_orders(gs, 'Lunedale') == min(attack_cap_for_turn(1), 12 - 1)
        assert _red_orders(gs) == _red_orders(gs, 'Lunedale')
        assert len(_units(gs, 'Affrancian Uplands', RED)) == 12          # still there until execution
        assert sum(u['status'] == 'ready' for u in _units(gs, 'Affrancian Uplands', RED)) >= 1

    def test_once_per_turn(self, game, tale):
        gs = game.game_state
        _red_turn(game, tale, 0)
        sent = _red_orders(gs)
        _red_turn(game, tale, 0)
        assert _red_orders(gs) == sent

    def test_ai_attacks_share_the_cap_with_the_forced_attack(self, game, tale):
        from ai_player import AIPlayer
        gs = game.game_state
        _red_turn(game, tale, 0)
        ai = AIPlayer(RED, 2)
        try:
            ok = ai._execute_action_internal(gs, 'move', {'from': 'Affrancian Uplands',
                                                          'to': 'Lunedale', 'army_count': 5})
        finally:
            ai._thread_pool.shutdown(wait=False)
        assert ok is False                                   # 10 of 10 already ordered
        assert _red_orders(gs, 'Lunedale') == attack_cap_for_turn(1)

    def test_without_objective_priority_the_best_odds_win(self, game, tale, monkeypatch):
        import tale_final_breaths
        monkeypatch.setattr(tale_final_breaths, 'FORCED_ATTACK_OBJECTIVES_FIRST', False)
        gs = game.game_state
        _red_turn(game, tale, 0)
        # Vense (8 defenders, reachable from Uplands + Carnae) beats Lunedale (12)
        assert _red_orders(gs, 'Vense') == attack_cap_for_turn(1)
        assert _red_orders(gs, 'Lunedale') == 0

    def test_reinforcements_off_by_default(self, game, tale):
        gs = game.game_state
        before = gs.get_player_army_count(RED)
        _red_turn(game, tale, 0)
        assert gs.get_player_army_count(RED) == before

    def test_reinforcements_fill_up_to_the_territory_limit(self, game, tale, monkeypatch):
        import tale_final_breaths
        monkeypatch.setattr(tale_final_breaths, 'KERUNIAN_REINFORCEMENTS', (4, 4))
        monkeypatch.setattr(tale_final_breaths, 'FORCED_ATTACK_TARGETS', 0)
        gs = game.game_state
        _red_turn(game, tale, 0)
        assert len(_units(gs, 'Orhas', RED)) == 5 + 4                     # default army 5
        assert len(_units(gs, 'Affrancian Uplands', RED)) == 15           # 12 + 3, capped
        for territory in FACTION_TERRITORIES[RED]:
            ids = [u['id'] for u in _units(gs, territory, RED)]
            assert len(ids) == len(set(ids)), territory                   # unique per garrison
        assert all(u['status'] == 'ready' for u in _units(gs, 'Orhas', RED))

    def test_front_only_reinforcements(self, game, tale, monkeypatch):
        import tale_final_breaths
        monkeypatch.setattr(tale_final_breaths, 'KERUNIAN_REINFORCEMENTS', (2, 2))
        monkeypatch.setattr(tale_final_breaths, 'KERUNIAN_REINFORCEMENTS_FRONT_ONLY', True)
        monkeypatch.setattr(tale_final_breaths, 'FORCED_ATTACK_TARGETS', 0)
        gs = game.game_state
        _red_turn(game, tale, 0)
        assert len(_units(gs, 'Carnae', RED)) == 8 + 2                    # borders Vense
        assert len(_units(gs, 'Sordia', RED)) == 5                        # deep south

    def test_no_forced_attack_once_the_game_has_ended(self, game, tale):
        gs = game.game_state
        gs.phase = 'ended'
        _red_turn(game, tale, 0)
        assert _red_orders(gs) == 0


# ============================================================================
# HEROES / AI GATES
# ============================================================================

class TestHeroesBanned:

    def test_nobody_may_train_heroes(self, game, tale):
        from ai_military import mission_allows_ai_action
        gs = game.game_state
        for player in (PLAYER, RED, REBELS):
            gs.current_player = player
            assert tale.is_action_allowed('train_hero') is False
            assert mission_allows_ai_action(gs, 'train_hero', territory='Carnae', hero_type='x') is False
        assert tale.should_hide_hero_training() is True

    def test_ai_train_hero_action_is_refused(self, game, tale):
        from ai_player import AIPlayer
        gs = game.game_state
        gs.current_player = RED
        gs.player_gold[RED] = 7000
        hero_type = next(iter(gs.HERO_TYPES))
        ai = AIPlayer(RED, 2)
        try:
            ok = ai._execute_action_internal(gs, 'train_hero', {
                'territory': 'Carnae', 'keep_plot': 0, 'hero_type': hero_type})
            # The planner drops it too
            planned = ai.hero_manager.plan_hero_actions(gs)
        finally:
            ai._thread_pool.shutdown(wait=False)
        assert ok is False
        assert not gs.hero_training_queue.get('Carnae')
        assert not any(a[0] == 'train_hero' for a in planned)

    def test_no_mission_allows_everything(self):
        from ai_military import mission_allows_ai_action, mission_ai_attack_cap

        class _GS:
            tutorial_mission = None
            territory_owners = {}

        assert mission_allows_ai_action(_GS(), 'train_hero') is True
        assert mission_ai_attack_cap(_GS(), 1, 'Lunedale') is None

    def test_counter_composition_ignores_captains(self):
        """Regression: a Captain-majority enemy made the AI try to train unit type None."""
        from ai_military import ArmyComposer
        comp = ArmyComposer().calculate_counter_composition({'Captain': 2, 'Archer': 1}, None)
        assert None not in comp and max(comp, key=comp.get) == 'Cavalry'   # Cavalry beats Archers
        comp = ArmyComposer().calculate_counter_composition({'Captain': 1}, None)
        assert set(comp) == {'Swordsman', 'Archer', 'Pikeman', 'Cavalry'}


# ============================================================================
# NORDIAN REBELS
# ============================================================================

class TestRebellions:

    def test_schedule(self):
        # Every other turn until turn 6, then every turn
        assert [rebellions_for_turn(t) for t in range(1, 16)] == [
            0, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

    def test_rebellions_fire_on_even_turns(self, game, tale):
        gs = game.game_state
        counts = []
        for turn_number in range(1, 15):                      # visible turns 2-15
            before = len(_owned(gs, REBELS))
            _player_turn(game, tale, turn_number)
            counts.append(len(_owned(gs, REBELS)) - before)
        assert counts == [rebellions_for_turn(t) for t in range(2, 16)]
        assert sum(counts) == 12

    def test_same_turn_never_applied_twice(self, game, tale):
        _player_turn(game, tale, 1)
        _player_turn(game, tale, 1)
        assert len(_owned(game.game_state, REBELS)) == 1

    def test_immune_territories_never_rebel(self, game):
        for seed in range(5):
            tale = _new_tale(game, seed=seed)
            for turn_number in range(1, 15):
                _player_turn(game, tale, turn_number)
            gs = game.game_state
            assert all(gs.territory_owners[t] == PLAYER for t in REBELLION_IMMUNE)
            assert len(tale.get_rebellion_candidates()) == 1   # 13 eligible, 12 rebelled

    def test_rebels_take_armies_and_buildings(self, game, tale, monkeypatch):
        gs = game.game_state
        monkeypatch.setattr(tale.rng, 'choice', lambda seq: 'Vense')
        units = [u['id'] for u in _units(gs, 'Vense', PLAYER)]
        buildings = dict(gs.buildings['Vense'])
        _player_turn(game, tale, 1)
        assert gs.territory_owners['Vense'] == REBELS
        assert [u['id'] for u in _units(gs, 'Vense', REBELS)] == units
        assert all(u['status'] == 'ready' for u in _units(gs, 'Vense', REBELS))
        assert _units(gs, 'Vense', PLAYER) == []
        assert gs.buildings['Vense'] == buildings
        assert any('Vense has rebelled' in m for m in gs.messages[-3:])

    def test_rebels_never_attack(self, game, tale):
        gs = game.game_state
        gs.territory_owners['Vense'] = REBELS
        assert tale.is_ai_target_allowed(REBELS, 'Vense') is True        # own land
        assert tale.is_ai_target_allowed(REBELS, 'Lunedale') is False
        assert tale.is_ai_target_allowed(REBELS, 'Zjoal Islands') is False
        assert tale.is_ai_target_allowed(RED, 'Lunedale') is True

    def test_rebel_turn_is_blocked_and_ends_itself(self, game, tale):
        gs = game.game_state
        gs.current_player = RED
        assert tale.block_ai is False
        gs.current_player = REBELS
        assert tale.block_ai is True
        gs.turn_phase = 'planning'
        assert tale.update_ai_turn(0.05) is True
        assert gs.current_player == PLAYER and gs.turn_number == 1

    def test_rebels_survive_losing_every_territory(self, game, tale):
        """Wiped out Rebels stay in play and rebel again next time."""
        gs = game.game_state
        _player_turn(game, tale, 1)
        rebel_land = _owned(gs, REBELS)
        assert len(rebel_land) == 1
        gs.territory_owners[rebel_land[0]] = PLAYER           # player retakes it
        gs.check_victory()
        assert REBELS in gs.eliminated_players                # engine's silent mark...
        assert gs.phase == 'playing'                          # ...doesn't end the game
        tale.update(0.05)
        assert REBELS not in gs.eliminated_players            # ...and the Tale undoes it
        _player_turn(game, tale, 3)                           # visible turn 4: rebellion
        assert len(_owned(gs, REBELS)) == 1
        assert gs.phase == 'playing'


# ============================================================================
# VICTORY / DEFEAT
# ============================================================================

class TestEndgame:

    def test_turns_remaining(self, game, tale):
        gs = game.game_state
        assert tale.get_turns_remaining() == HOLD_TURNS
        gs.turn_number = 14
        assert tale.get_turns_remaining() == 1
        gs.turn_number = 20
        assert tale.get_turns_remaining() == 0

    def test_not_won_before_fifteen_turns(self, game, tale):
        for turn_number in range(1, HOLD_TURNS):
            _player_turn(game, tale, turn_number)
        assert game.game_state.phase == 'playing'

    def test_holding_out_is_victory(self, game, tale):
        gs = game.game_state
        _player_turn(game, tale, HOLD_TURNS)
        assert gs.winner == PLAYER and gs.phase == 'ended'
        assert all(q['completed'] for q in tale.get_quest_log())
        assert _run_until_exit(tale) == 'exit_campaign'
        assert tale.victory_image is not None

    @pytest.mark.parametrize('objective', OBJECTIVE_TERRITORIES)
    def test_losing_an_objective_is_defeat(self, game, tale, objective):
        gs = game.game_state
        gs.territory_owners[objective] = RED
        tale.notify_event('territory_conquered', territory=objective, new_owner=RED)
        assert gs.phase == 'ended' and gs.winner != PLAYER
        assert _run_until_exit(tale) == 'exit_campaign_defeat'

    def test_objective_lost_any_other_way_is_defeat(self, game, tale):
        game.game_state.territory_owners['Free Cities'] = -1
        assert _run_until_exit(tale) == 'exit_campaign_defeat'

    def test_engine_last_team_standing_counts_as_victory(self, game, tale):
        gs = game.game_state
        gs.winner = PLAYER
        gs.phase = 'ended'
        assert _run_until_exit(tale) == 'exit_campaign'

    def test_cleanup_restores_shared_state(self, game, tale):
        _player_turn(game, tale, HOLD_TURNS)
        assert _run_until_exit(tale) == 'exit_campaign'
        gs = game.game_state
        assert gs.player_taxation_override == {}
        outside = next(t for t in map_data.TERRITORY_INCOME if t not in MISSION_3_TERRITORIES)
        assert map_data.is_territory_enabled(outside)      # territory filter cleared
        assert tale.active is False


# ============================================================================
# WIDGET / SAVE / BOOK OF TALES
# ============================================================================

class TestWidgetAndSave:

    def test_widget_swallows_clicks(self, game, tale):
        tale.render(game.screen)
        rect = tale._widget_rect
        assert rect is not None and rect.width > 0
        assert tale.handle_click(rect.center) is True
        assert tale.handle_click((rect.right + 50, rect.top - 50)) is False
        game.mouse.handle_left_click(rect.center)       # through the real handler: no crash

    def test_save_restore_roundtrip(self, game, tale):
        gs = game.game_state
        _player_turn(game, tale, 1)
        data = json.loads(json.dumps(tale.get_save_state()))
        gs.player_taxation_override = {}                 # as if the game state were rebuilt
        restored = _new_tale(game, seed=3)
        restored.restore_save_state(data)
        assert restored._last_turn_handled == 1
        assert gs.get_taxation_level(PLAYER) == 4
        # The same turn isn't applied again after loading
        before = len(_owned(gs, REBELS))
        _player_turn(game, restored, 1)
        assert len(_owned(gs, REBELS)) == before

    def test_save_label(self):
        import save_manager
        assert save_manager._MISSION_TEXTS['tale_2'] == 'Tale: Final Breaths'

    def test_tale_2_listed_and_registered(self):
        import book_of_tales
        entry = next(t for t in book_of_tales.SCENARIOS if t['id'] == 'tale_2')
        assert entry['name'] == 'Final Breaths' and not entry.get('hidden')
        assert '100%' in entry['description']
        # _TALE_REGISTRY lives under main.py's __main__ block: check its source
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py'),
                  encoding='utf-8') as f:
            source = f.read()
        assert "'import': ('tale_final_breaths', 'TaleFinalBreaths')" in source
