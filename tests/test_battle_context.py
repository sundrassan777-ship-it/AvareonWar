# -*- coding: utf-8 -*-
"""
A simultaneous round's battles come out the same whatever order they are fought in -
found in the FFA test game of 2026-10-14 (10 of its 100 battles came out differently on a
client).

Every PC sets the round's battles up from the same state, then resolves its own battles
first and replays the others. Battles read live heroes and territorial bonuses, so one
that killed a hero or changed a bonus territory's owner changed the next one: round 36,
Neil Hevilneu slain at Daomea - Red's Aelatania army was 24.4 strong (13 survivors) on the
host and Green, 20.6 (12) on Blue, who fought Daomea first. Twice Green missed Scavenge the
Fallen gold the same way.

Now the round's heroes and territorial bonuses are frozen once when its battles are set up
(SimPhaseManager._setup_battles_for_ui -> GameState.capture_battle_context, BattleContext
on each Battle): Vanquish the Enemy and the bonuses in the strength, Pillage / Champion
of the People when buildings fall, Scavenge the Fallen. A hero slain in the battle being
resolved still counts as dead there (as before), Safe Haven stays live. Sequential battles
carry no context and keep reading live values.

Also: an alliance choice arriving while this PC's own armies still march waits for them
(like a battle result) - applied earlier, the territory changed hands before our arrivals.
"""

import logging
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import map_data  # noqa: E402
import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from game_state import Battle, GameState  # noqa: E402
from network_config import MessageType  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402

RED, BLUE, GREEN, AI = 0, 1, 2, 3
NEIL = 'Neil Hévilneu'
DARIUS = 'Darius Brennhen'
ASFORD = 'Vearen Asford'
SELEDRA = 'Seledra Rennervail'
DAOMEA, AELATANIA = 'Daomea', 'Aelatania'


# ============================================================================
# HELPERS
# ============================================================================

def _round(num_players=4, used=()):
    """A simultaneous game; every player keeps a spare territory (check_victory runs
    inside a battle and would knock out a player whose last territory falls)."""
    gs = GameState(num_players=num_players, player_is_ai=[False] * num_players,
                   player_ai_difficulty=[1] * num_players, skip_setup_phase=True)
    gs.phase = 'playing'
    sim = SimultaneousGameState(gs)
    pm = SimPhaseManager(sim)
    sim.phase_manager = pm
    spares = [t for t in sorted(map_data.get_all_territories()) if t not in used]
    for player in range(num_players):
        h.place(gs, spares[player], player, h.units('Swordsman'))
    return gs, pm


def _arrive(gs, territory, player, *unit_types):
    """`player`'s army stands in `territory` after this round's arrivals."""
    gs.territory_garrisons.setdefault(territory, {})[player] = {
        'unmoved': 0, 'moved': len(unit_types), 'units': h.units(*unit_types, status='moved')}


def _hero(gs, player, hero, territory, plot=0):
    gs.heroes[player][hero] = {'keep_territory': territory, 'keep_plot': plot, 'status': 'active'}
    gs.hero_ownership[player].add(hero)


def _set_up(pm, battles):
    """The round's battles, set up as simultaneous mode does after its arrivals."""
    pm.pending_battles = [pm._create_battle_conflict(t, players) for t, players in battles]
    pm._setup_battles_for_ui()


def _fight(gs, territory, seed=7):
    index = next(i for i, b in enumerate(gs.pending_battles) if b.territory == territory)
    assert gs.resolve_battle(index, rng=random.Random(seed))


def _strength_line(gs, territory, player):
    """The '(Effective Strength: x)' line `player` got in the battle at `territory`."""
    start = gs.messages.index(f"=== Resolving battle at {territory} ===")
    for line in gs.messages[start + 1:]:
        if line.startswith("=== Resolving battle at"):
            break
        if line.startswith(f"  Player {player + 1}:") and "Effective Strength" in line:
            return line
    raise AssertionError(f"no strength line for Player {player + 1} at {territory}")


def _units(gs, territory, player):
    return sorted(u['type'] for u in (gs.territory_garrisons.get(territory, {}).get(player) or {})
                  .get('units', []))


def _bonus_territory(kinds=('swordsman_str', 'archer_str', 'pikeman_str', 'cavalry_str')):
    """(territory, bonus kind, unit type) of a territory with a unit strength bonus."""
    unit_of = {'swordsman_str': 'Swordsman', 'archer_str': 'Archer',
               'pikeman_str': 'Pikeman', 'cavalry_str': 'Cavalry'}
    for kind in kinds:
        for territory in sorted(map_data.get_all_territories()):
            if map_data.get_territory_bonus(territory) == kind:
                return territory, kind, unit_of[kind]
    pytest.skip("this map has no unit strength bonus territory")


# ============================================================================
# THE ROUND 36 BATTLES: NEIL SLAIN AT DAOMEA, RED ATTACKING AELATANIA
# ============================================================================

def _round_36():
    """Blue takes Red's Daomea (Neil's Keep); Red attacks the AI's Aelatania."""
    gs, pm = _round(used=(DAOMEA, AELATANIA))
    h.place(gs, DAOMEA, RED, h.units('Archer'), buildings={0: 'Keep'})
    _hero(gs, RED, NEIL, DAOMEA)
    _arrive(gs, DAOMEA, BLUE, 'Captain', 'Captain', 'Cavalry', 'Pikeman', 'Swordsman')
    h.place(gs, AELATANIA, AI, h.units('Archer', 'Pikeman'))
    _arrive(gs, AELATANIA, RED, *(['Archer'] * 5 + ['Captain'] + ['Cavalry'] * 2
                                  + ['Pikeman'] * 2 + ['Swordsman'] * 3))
    _set_up(pm, [(DAOMEA, [RED, BLUE]), (AELATANIA, [AI, RED])])
    return gs


class TestOrderDoesNotMatter:

    @pytest.mark.parametrize('order', [(AELATANIA, DAOMEA), (DAOMEA, AELATANIA)])
    def test_neil_counts_at_aelatania_whichever_battle_comes_first(self, order):
        """Blue's PC fought Daomea first and Red's army lost Neil's +20%."""
        aelatania_first = _round_36()
        _fight(aelatania_first, AELATANIA)
        expected = _strength_line(aelatania_first, AELATANIA, RED)

        gs = _round_36()
        for territory in order:
            _fight(gs, territory)
        assert NEIL not in gs.heroes[RED]                      # he still dies at Daomea
        assert _strength_line(gs, AELATANIA, RED) == expected
        assert _units(gs, AELATANIA, RED) == _units(aelatania_first, AELATANIA, RED)

    def test_a_bonus_territory_lost_first_still_counts(self):
        """A territory with a unit strength bonus changes hands in another battle first."""
        bonus, kind, unit = _bonus_territory()
        target = next(t for t in sorted(map_data.get_all_territories())
                      if t != bonus and map_data.get_territory_bonus(t) != kind)

        def build():
            gs, pm = _round(used=(bonus, target))
            h.place(gs, bonus, RED, h.units('Archer'))
            _arrive(gs, bonus, BLUE, *(['Cavalry'] * 6))           # Blue takes it
            h.place(gs, target, AI, h.units('Swordsman', 'Swordsman'))
            _arrive(gs, target, RED, *([unit] * 6))                # Red attacks with that unit
            assert kind in gs.calculate_player_territorial_bonuses(RED)   # Red has it now
            _set_up(pm, [(bonus, [RED, BLUE]), (target, [AI, RED])])
            return gs

        target_first = build()
        _fight(target_first, target)
        bonus_first = build()
        _fight(bonus_first, bonus)
        assert bonus_first.territory_owners[bonus] == BLUE
        _fight(bonus_first, target)
        assert _strength_line(bonus_first, target, RED) == _strength_line(target_first, target, RED)

    @pytest.mark.parametrize('darius_keep_first', [True, False])
    def test_scavenge_the_fallen_in_either_order(self, darius_keep_first):
        """The AI loses Darius's Keep and another territory in one round: Scavenge for the
        other territory either way - none for the battle that kills Darius, as before."""
        keep, other = sorted(t for t in map_data.get_all_territories())[10:12]
        gs, pm = _round(used=(keep, other))
        h.place(gs, keep, AI, h.units('Archer'), buildings={0: 'Keep'})
        _hero(gs, AI, DARIUS, keep)
        _arrive(gs, keep, BLUE, *(['Cavalry'] * 8))
        h.place(gs, other, AI, h.units('Archer'))
        _arrive(gs, other, RED, *(['Cavalry'] * 6))
        _set_up(pm, [(keep, [AI, BLUE]), (other, [AI, RED])])
        gold = gs.player_gold[AI]
        for territory in ((keep, other) if darius_keep_first else (other, keep)):
            _fight(gs, territory)
        assert DARIUS not in gs.heroes[AI]
        assert gs.player_gold[AI] == gold + 30

    @pytest.mark.parametrize('asford_keep_first', [True, False])
    def test_pillage_in_either_order(self, asford_keep_first):
        """Blue loses Asford's Keep and takes a Keep from Red in the same round."""
        asford_keep, red_keep = sorted(t for t in map_data.get_all_territories())[10:12]
        gs, pm = _round(used=(asford_keep, red_keep))
        h.place(gs, asford_keep, BLUE, h.units('Archer'), buildings={0: 'Keep'})
        _hero(gs, BLUE, ASFORD, asford_keep)
        _arrive(gs, asford_keep, GREEN, *(['Cavalry'] * 8))
        h.place(gs, red_keep, RED, h.units('Archer'), buildings={0: 'Keep'})
        _arrive(gs, red_keep, BLUE, *(['Cavalry'] * 8))
        _set_up(pm, [(asford_keep, [BLUE, GREEN]), (red_keep, [RED, BLUE])])
        gold = gs.player_gold[BLUE]
        for territory in ((asford_keep, red_keep) if asford_keep_first else (red_keep, asford_keep)):
            _fight(gs, territory)
        assert gs.territory_owners[red_keep] == BLUE
        assert gs.player_gold[BLUE] == gold + 200

    @pytest.mark.parametrize('seledra_keep_first', [True, False])
    def test_champion_of_the_people_in_either_order(self, seledra_keep_first):
        """Red loses Seledra's Keep and takes a Farm territory in the same round."""
        seledra_keep, farmland = sorted(t for t in map_data.get_all_territories())[10:12]
        gs, pm = _round(used=(seledra_keep, farmland))
        h.place(gs, seledra_keep, RED, h.units('Archer'), buildings={0: 'Keep'})
        _hero(gs, RED, SELEDRA, seledra_keep)
        _arrive(gs, seledra_keep, BLUE, *(['Cavalry'] * 8))
        h.place(gs, farmland, AI, h.units('Archer'), buildings={0: 'Farm'})
        _arrive(gs, farmland, RED, *(['Cavalry'] * 6))
        _set_up(pm, [(seledra_keep, [RED, BLUE]), (farmland, [AI, RED])])
        for territory in ((seledra_keep, farmland) if seledra_keep_first else (farmland, seledra_keep)):
            _fight(gs, territory)
        assert gs.territory_owners[farmland] == RED
        assert gs.buildings.get(farmland) == {0: 'Farm'}


# ============================================================================
# THE CONTEXT ITSELF
# ============================================================================

class TestContext:

    def test_one_context_per_round_taken_before_any_battle(self):
        gs = _round_36()
        first, second = gs.pending_battles
        assert first.battle_context is second.battle_context
        context = first.battle_context
        assert context.has_hero(RED, gs.VANQUISH_HEROES)
        assert context.bonuses(RED) == gs.calculate_player_territorial_bonuses(RED)
        assert context.bonuses(-1) == {}                       # neutral: none, as live

    def test_the_context_does_not_follow_later_changes(self):
        gs = _round_36()
        context = gs.pending_battles[0].battle_context
        del gs.heroes[RED][NEIL]
        assert context.has_hero(RED, gs.VANQUISH_HEROES)
        assert not context.has_hero(RED, gs.VANQUISH_HEROES, slain=[NEIL])

    def test_sequential_battles_read_live_values(self):
        """A battle built anywhere else has no context: today's live values."""
        gs = GameState(num_players=2, skip_setup_phase=True)
        assert Battle('X').battle_context is None
        territory = h.spread_territories(2)[0]
        h.place(gs, territory, RED, h.units('Swordsman'))
        _hero(gs, RED, NEIL, territory)
        with_neil = gs.calculate_army_effective_strength(
            {'Swordsman': 3}, {'Archer': 1}, player=RED, territory=territory)
        del gs.heroes[RED][NEIL]
        without = gs.calculate_army_effective_strength(
            {'Swordsman': 3}, {'Archer': 1}, player=RED, territory=territory)
        assert with_neil > without

    def test_the_battle_window_shows_the_strength_the_battle_uses(self):
        """The window's strength bars read the same frozen values as the fight."""
        from ui.effects.battle_interface import EnhancedBattleInterface
        gs = _round_36()
        index = next(i for i, b in enumerate(gs.pending_battles) if b.territory == AELATANIA)
        battle = gs.pending_battles[index]
        del gs.heroes[RED][NEIL]                               # e.g. Daomea fought already
        window = SimpleNamespace(
            game_state=gs, battle_index=index, territory=AELATANIA,
            attacker_player=RED, attacker_composition=battle.army_compositions[RED],
            defender_players=[AI], defender_composition=battle.army_compositions[AI],
            has_keep=False, keep_bonus=0, attacker_count=battle.armies[RED],
            defender_count=battle.armies[AI])
        EnhancedBattleInterface._calculate_effective_strengths(window)
        _, strengths = gs._calculate_battle_strengths(battle, list(battle.armies.items()))
        assert window.attacker_strength == pytest.approx(strengths[RED])
        live = gs.calculate_army_effective_strength(
            battle.army_compositions[RED], battle.army_compositions[AI], RED, AELATANIA,
            unit_avg_levels=gs.get_unit_avg_levels(AELATANIA, RED))
        assert window.attacker_strength > live                 # Neil's +20% still in it


# ============================================================================
# TWO PCS: EACH FIGHTS ITS OWN BATTLE FIRST
# ============================================================================

def _two_routes(avoid):
    """(a, x, b, y): a borders x, b borders y, all different, none in `avoid`."""
    territories = [t for t in sorted(map_data.get_all_territories()) if t not in avoid]
    for a in territories:
        for x in sorted(map_data.get_neighbors(a)):
            if x in avoid:
                continue
            for b in territories:
                if b in (a, x):
                    continue
                for y in sorted(map_data.get_neighbors(b)):
                    if y not in avoid and y not in (a, x, b):
                        return a, x, b, y
    raise AssertionError("no two separate routes on this map")


class TestTwoPCs:

    def test_both_pcs_get_the_same_result_without_a_correction(self, make_session, monkeypatch, caplog):
        """The host takes the client's Keep where Neil lives; the client attacks the host
        with 9 Swordsmen against 1 - 10.8 : 1 with Neil (no losses), 9 : 1 without (one
        lost). Each PC fights its own battle first. The host used to replay the client's
        battle without Neil and log that its result differed."""
        monkeypatch.setattr(map_data, 'get_territory_bonus', lambda territory: None)
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, x, b, y = _two_routes(set(h.spread_territories(2)))

        def arrange(gs):
            h.place(gs, a, 0, h.units(*['Cavalry'] * 6))
            h.place(gs, x, 1, h.units('Archer'), buildings={0: 'Keep'})
            _hero(gs, 1, NEIL, x)
            h.place(gs, b, 1, h.units(*['Swordsman'] * 9))
            h.place(gs, y, 0, h.units('Swordsman'))
            gs.invalidate_territorial_bonus_cache()
        session.on_all(arrange)
        host, client = session.game(0), session.game(1)
        assert host.game_state.add_movement_order_for_units(a, x, list(range(6)))
        assert client.game_state.add_movement_order_for_units(b, y, list(range(9)))
        h.click_end_turn(client)
        session.step_all()
        h.click_end_turn(host)

        def both_battles_on_both():
            return all({bt.territory for bt in session.gs(i).pending_battles} == {x, y}
                       for i in (0, 1))
        session.step_until(both_battles_on_both, max_steps=400)

        caplog.set_level(logging.WARNING, logger='main')
        for game, territory in ((host, x), (client, y)):        # each its own battle first
            h.open_battle(game, territory)
            h.fight(game)
            h.close_battle(game)
        session.step_until(lambda: host.sim_state.round_number == 2, max_steps=400)
        session.run_until_quiet()

        assert not [r for r in caplog.records if 'differs from the resolver' in r.getMessage()]
        for index in (0, 1):
            gs = session.gs(index)
            assert gs.territory_owners[x] == 0 and NEIL not in gs.heroes[1]
            assert gs.territory_owners[y] == 1
            assert _units(gs, y, 1) == ['Swordsman'] * 9

    def test_an_alliance_choice_waits_for_our_own_arrivals(self, make_session):
        """The host's choice reaches a client whose armies still march: held, then
        applied once they have arrived - not before (the territory changed hands before
        the client's own arrivals)."""
        session = make_session(num_players=3, turn_mode='simultaneous', teams=[0, 0, 1])
        client = session.game(1)
        gs = client.game_state
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 1, h.units('Swordsman'))
        gs.active_animations = [object()]                      # our armies still marching
        message = {'type': MessageType.SIM_ALLIANCE_CHOICE,
                   'data': {'territory': b, 'new_owner': 0}}
        client._handle_network_message(message)
        assert client._held_network_messages == [message]
        assert gs.territory_owners[b] != 0

        gs.active_animations = []                              # our armies have arrived
        client._release_held_network_messages()
        assert client._held_network_messages == []
        assert gs.territory_owners[b] == 0
