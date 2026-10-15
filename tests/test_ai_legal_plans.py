# -*- coding: utf-8 -*-
"""
The built-in AI plans only what the game accepts - found in the FFA test game of
2026-10-14, where the Easy AI wasted orders round after round (single-player too):

- Hero training at the Keep its Hero Darius lived in (rounds 14-19 and 23-41), though
  another of its Keeps was free in rounds 15-19 and 23-33. start_hero_training() refuses
  a Keep that is upgrading to a Castle, training a Hero or housing one; the AI checked
  only "training".
- Supply and Demand, a Castle tech, every round from 34 to 42 without a Castle: the game
  refuses Castle techs without a Castle, the AI's research pick ignored it.
- Attacks on targets 2 steps away, through a friendly territory: all 18 of the AI's
  dropped moves. No army may attack 2 steps away (find_2hop_path() allows a Captain's
  long move only into own/allied land), so the AI now moves into the friendly territory
  between instead (a staging move), and attacks from there next turn.

The simultaneous side (gold held back for the doomed Hero) is in test_sim_ai_budget.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import ai_player  # noqa: E402
import map_data  # noqa: E402
import mp_harness as h  # noqa: E402
from ai_hero import HeroSelector  # noqa: E402
from game_state import GameState  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402
from simultaneous.sim_ai import SimultaneousAI  # noqa: E402

HUMAN, AI = 0, 1
DARIUS = 'Darius Brennhen'
SUPPLY_AND_DEMAND = 'tech_0_3'      # requires a Castle
EFFICIENT_FARMING = 'tech_0_0'      # no Castle needed


def _game(gold=2000):
    gs = GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[1, 1],
                   skip_setup_phase=True)
    gs.player_gold[AI] = gold
    return gs


@pytest.fixture
def ai():
    player = ai_player.AIPlayer(AI, 1)
    yield player
    player._thread_pool.shutdown(wait=False)


def _two_keeps(gs):
    """The AI holds two territories with a Keep each; returns them in the order the AI
    looks at its Keeps (gs.territory_owners), so the first one is the one it used to take."""
    first, second = list(gs.territory_owners)[:2]
    h.place(gs, first, AI, h.units('Swordsman'), buildings={0: 'Keep'})
    h.place(gs, second, AI, h.units('Swordsman'), buildings={0: 'Keep'})
    return first, second


def _hero_lives_in(gs, territory, plot=0, hero=DARIUS):
    gs.heroes[AI][hero] = {'keep_territory': territory, 'keep_plot': plot, 'status': 'active'}
    gs.hero_ownership[AI].add(hero)


# ============================================================================
# HERO TRAINING: ONLY AT A KEEP THE GAME ACCEPTS
# ============================================================================

class TestHeroKeep:

    def test_a_keep_a_hero_lives_in_is_passed_over(self):
        """FFA game: Darius lived in the first Keep, the next Hero was planned there."""
        gs = _game()
        home, free = _two_keeps(gs)
        _hero_lives_in(gs, home)
        assert HeroSelector()._find_keep_for_training(gs, AI) == (free, 0)

    def test_a_keep_upgrading_to_a_castle_is_passed_over(self):
        gs = _game()
        upgrading, free = _two_keeps(gs)
        gs.castle_upgrades_in_progress[upgrading] = {0: 1}
        assert HeroSelector()._find_keep_for_training(gs, AI) == (free, 0)

    def test_no_free_keep_means_no_hero_is_planned(self):
        """Rounds 34-41: the AI's only Keep housed Darius - nothing to train in."""
        gs = _game()
        home = list(gs.territory_owners)[0]
        h.place(gs, home, AI, h.units('Swordsman'), buildings={0: 'Keep'})
        _hero_lives_in(gs, home)
        assert HeroSelector().select_hero_to_train(gs, AI, 1) is None

    def test_the_planned_hero_really_starts_training(self):
        gs = _game()
        home, free = _two_keeps(gs)
        _hero_lives_in(gs, home)
        hero, territory, plot = HeroSelector().select_hero_to_train(gs, AI, 1)
        gs.current_player = AI
        assert gs.start_hero_training(territory, plot, hero)
        assert gs.hero_training_queue[free][0][0] == hero


# ============================================================================
# RESEARCH: NO CASTLE TECH WITHOUT A CASTLE
# ============================================================================

class TestCastleResearch:

    def test_a_castle_tech_is_not_picked_without_a_castle(self, ai):
        """FFA game rounds 34-42: Supply and Demand, refused every round."""
        gs = _game()
        h.place(gs, list(gs.territory_owners)[0], AI, h.units('Swordsman'), buildings={0: 'Keep'})
        gs.player_tech_available[AI] = {SUPPLY_AND_DEMAND}
        assert ai.economy.tech_researcher.select_research_action(gs, AI, 1) is None

    def test_another_tech_is_picked_instead(self, ai):
        gs = _game()
        h.place(gs, list(gs.territory_owners)[0], AI, h.units('Swordsman'), buildings={0: 'Keep'})
        gs.player_tech_available[AI] = {SUPPLY_AND_DEMAND, EFFICIENT_FARMING}
        tech = ai.economy.tech_researcher.select_research_action(gs, AI, 1)
        assert tech == EFFICIENT_FARMING
        gs.current_player = AI
        assert gs.start_research(tech)

    def test_with_a_castle_the_castle_tech_is_picked_and_starts(self, ai):
        gs = _game()
        home = list(gs.territory_owners)[0]
        h.place(gs, home, AI, h.units('Swordsman'), buildings={0: 'Keep'})
        gs.castle_upgrades[home] = {0: True}
        gs.player_tech_available[AI] = {SUPPLY_AND_DEMAND}
        assert ai.economy.tech_researcher.select_research_action(gs, AI, 1) == SUPPLY_AND_DEMAND
        gs.current_player = AI
        assert gs.start_research(SUPPLY_AND_DEMAND)


# ============================================================================
# ATTACKS 2 STEPS AWAY BECOME STAGING MOVES
# ============================================================================

def _two_steps():
    """(A, B, C): A borders B, B borders C, A does not border C - sorted for determinism."""
    for a in sorted(map_data.get_all_territories()):
        for b in sorted(map_data.get_neighbors(a)):
            for c in sorted(map_data.get_neighbors(b)):
                if c != a and not map_data.are_adjacent(a, c):
                    return a, b, c
    raise AssertionError("map has no territory 2 steps from another")


def _staging_map(gs):
    """The AI's army in A, its empty territory B, the human's C beyond B."""
    a, b, c = _two_steps()
    h.place(gs, a, AI, h.units(*['Swordsman'] * 6))
    h.place(gs, b, AI)
    h.place(gs, c, HUMAN, h.units('Swordsman', 'Swordsman'))
    return a, b, c


def _only_target(planner, monkeypatch, target):
    """Make `target` the only attack worth planning (the scoring is not under test)."""
    monkeypatch.setattr(planner, '_score_attack_target',
                        lambda source, to, *args, **kwargs: 100.0 if to == target else 0.0)


def _as_moves(attacks):
    """The planner's attacks as the AI's actions (MilitaryCommander.plan_military_actions)."""
    return [('move', {'from': source, 'to': to, 'army_count': count})
            for source, to, count in attacks]


class TestStagingMoves:

    def test_a_target_2_steps_away_gets_a_move_into_the_territory_between(self, ai, monkeypatch):
        gs = _game()
        a, b, c = _staging_map(gs)
        planner = ai.military.attack_planner
        _only_target(planner, monkeypatch, c)
        attacks = planner.select_attack_targets(gs, max_attacks=3)
        assert [(source, to) for source, to, _count in attacks] == [(a, b)]
        assert attacks[0][2] >= 1

    def test_an_adjacent_target_is_still_attacked_directly(self, ai, monkeypatch):
        gs = _game()
        a, b, _c = _staging_map(gs)
        target = next(n for n in sorted(map_data.get_neighbors(a)) if n != b)
        h.place(gs, target, HUMAN, h.units('Swordsman'))
        planner = ai.military.attack_planner
        _only_target(planner, monkeypatch, target)
        attacks = planner.select_attack_targets(gs, max_attacks=3)
        assert [(source, to) for source, to, _count in attacks] == [(a, target)]

    def test_every_planned_move_is_to_a_neighbour(self, ai, monkeypatch):
        """Whatever scores well, the planner never names a territory 2 steps away."""
        gs = _game()
        _staging_map(gs)
        monkeypatch.setattr(ai.military.attack_planner, '_score_attack_target',
                            lambda *args, **kwargs: 100.0)
        attacks = ai.military.attack_planner.select_attack_targets(gs, max_attacks=7)
        assert attacks
        assert all(map_data.are_adjacent(source, to) for source, to, _count in attacks)

    def test_sequential_the_staging_order_is_created(self, ai, monkeypatch):
        gs = _game()
        a, b, c = _staging_map(gs)
        planner = ai.military.attack_planner
        _only_target(planner, monkeypatch, c)
        gs.current_player = AI
        for action_type, action_data in _as_moves(planner.select_attack_targets(gs)):
            ai._execute_action_internal(gs, action_type, action_data)
        assert [(o.from_territory, o.to_territory, o.player) for o in gs.movement_orders] == [(a, b, AI)]

    def test_simultaneous_the_host_accepts_the_staging_move(self, monkeypatch):
        gs = _game()
        a, b, c = _staging_map(gs)
        sim = SimultaneousGameState(gs)
        sim.phase_manager = SimPhaseManager(sim)
        sim_ai = SimultaneousAI(sim, ai_player)
        player = sim_ai.ai_players[AI]
        planner = player.military.attack_planner
        _only_target(planner, monkeypatch, c)
        monkeypatch.setattr(player, '_plan_turn_actions', lambda game_state: setattr(
            player, 'actions_taken', _as_moves(planner.select_attack_targets(game_state))))
        sim_ai._make_ai_decisions(AI)
        accepted = sim.phase_manager.begin_authoritative_execution({AI: list(sim.player_orders[AI])})
        assert [(o['from_territory'], o['to_territory']) for o in accepted] == [(a, b)]
