# -*- coding: utf-8 -*-
"""
Simultaneous-mode AI spending - found in the first multiplayer test game (2026-10-12).

The AI planner was written for sequential turns, where each purchase is paid the moment
it is made and a later one simply fails when the gold runs out. In simultaneous mode
nothing is paid while planning, so the AI planned every purchase against its full gold,
and the round then pays builds and training first: its Hero training (and research),
paid last, failed round after round - one AI tried a Hero for 7 rounds running.
SimultaneousAI._fit_actions_to_gold() keeps the purchases it can pay for, in its own
priority order (Heroes first), and keeps Heroes and Castle upgrades of one Keep apart.

Also found: the territory bonus "Hero Training Cost" was never applied -
start_hero_training() charged the base price minus Royal Decree only.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_player  # noqa: E402
import mp_harness as h  # noqa: E402
from game_state import GameState  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402
from simultaneous.sim_ai import SimultaneousAI  # noqa: E402

HERO = 'Halon Nextroy'         # 400 gold
HOME = 'Amennia'               # 3 plots, no territory bonus
BONUS_TERRITORY = 'Mose'       # "Hero Training Cost" -3%


def setup(gold):
    """Player 2 (AI) holds HOME with a Keep (plot 0) and Barracks (plot 1)."""
    gs = GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[1, 1],
                   skip_setup_phase=True)
    sim = SimultaneousGameState(gs)
    sim.phase_manager = SimPhaseManager(sim)
    ai = SimultaneousAI(sim, ai_player)
    h.place(gs, HOME, 1, h.units('Swordsman'), buildings={0: 'Keep', 1: 'Barracks'})
    gs.player_gold[1] = gold
    return gs, sim, ai


def planned_round():
    """What the AI planned in the test game: a Hero first, then cheaper things."""
    return [
        ('train_hero', {'hero_type': HERO, 'territory': HOME, 'keep_plot': 0}),
        ('build', {'territory': HOME, 'building': 'Farm', 'plot': 2}),
        ('train', {'territory': HOME, 'unit_type': 'Swordsman', 'barracks_plot': 1}),
    ]


class TestGoldBudget:

    def test_purchases_are_kept_in_the_ais_order_while_it_can_pay(self):
        _gs, _sim, ai = setup(gold=420)
        kept = ai._fit_actions_to_gold(1, planned_round())
        assert [action for action, _ in kept] == ['train_hero']          # 20 gold left

    def test_actions_that_cost_nothing_are_always_kept(self):
        _gs, _sim, ai = setup(gold=0)
        ability = ('hero_ability', {'hero_type': HERO, 'ability_name': 'Levy', 'target': None})
        kept = ai._fit_actions_to_gold(1, [ability] + planned_round())
        assert kept == [ability]

    def test_the_hero_the_ai_wanted_is_trained_this_round(self, monkeypatch):
        """End to end: the AI's orders for the round, executed by the round."""
        gs, sim, ai = setup(gold=420)
        player = ai.ai_players[1]
        monkeypatch.setattr(player, '_plan_turn_actions',
                            lambda game_state: setattr(player, 'actions_taken', planned_round()))
        ai._make_ai_decisions(1)
        sim.phase_manager._execute_orders(list(sim.player_orders[1]), start_movement=False)
        assert gs.hero_training_queue[HOME][0][0] == HERO
        assert gs.player_gold[1] == 20


class TestHeroesAndCastleUpgrades:

    def test_one_keep_gets_a_hero_or_an_upgrade_whichever_was_planned_first(self):
        _gs, _sim, ai = setup(gold=2000)
        hero = ('train_hero', {'hero_type': HERO, 'territory': HOME, 'keep_plot': 0})
        upgrade = ('upgrade_castle', {'territory': HOME, 'plot': 0})
        assert [a for a, _ in ai._fit_actions_to_gold(1, [hero, upgrade])] == ['train_hero']
        assert [a for a, _ in ai._fit_actions_to_gold(1, [upgrade, hero])] == ['upgrade_castle']

    def test_no_hero_at_a_keep_being_upgraded(self):
        gs, _sim, ai = setup(gold=2000)
        gs.castle_upgrades_in_progress[HOME] = {0: 1}
        hero = ('train_hero', {'hero_type': HERO, 'territory': HOME, 'keep_plot': 0})
        assert ai._fit_actions_to_gold(1, [hero]) == []


class TestHeroPrice:

    def test_the_hero_training_cost_bonus_lowers_the_price(self):
        gs = GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[1, 1],
                       skip_setup_phase=True)
        h.place(gs, BONUS_TERRITORY, 0)
        h.place(gs, HOME, 0, buildings={0: 'Keep'})
        gs.current_player = 0
        gs.player_gold[0] = 1000
        price = int(400 * 97 / 100)                      # -3% for one bonus territory
        assert gs.get_hero_cost(HERO, 0) == price
        assert gs.start_hero_training(HOME, 0, HERO)
        assert gs.player_gold[0] == 1000 - price
        assert gs.hero_training_queue[HOME][0][2] == price       # refunded in full on cancel
