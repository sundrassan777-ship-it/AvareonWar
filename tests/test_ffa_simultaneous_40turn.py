# -*- coding: utf-8 -*-
"""
40-Turn FFA Simultaneous Mode Stress Test
==========================================

Tests a 4-player Free-For-All game running for 40 rounds in simultaneous mode.
All players are AI-controlled. Validates game state consistency after each round.

Usage:
    python tests/test_ffa_simultaneous_40turn.py

Output:
    Detailed debug logging showing territory counts, gold, AI actions, battles,
    and any validation errors. Summary at end with all issues found.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
import random
import time
import traceback


class StateValidator:
    """Validates game state consistency after each round."""

    def __init__(self, game, num_players=4):
        self.game = game
        self.num_players = num_players
        self.errors = []

    def validate_all(self, round_num):
        """Run all validation checks. Returns list of errors."""
        self.errors = []
        self._check_territory_ownership()
        self._check_army_counts()
        self._check_garrison_consistency()
        self._check_gold_non_negative()
        return self.errors

    def _check_territory_ownership(self):
        """Each territory has valid owner (-1 to num_players-1)."""
        for territory, owner in self.game.territory_owners.items():
            if owner < -1 or owner >= self.num_players:
                self.errors.append(f"Invalid owner {owner} for {territory}")

    def _check_army_counts(self):
        """Per-player garrison counts non-negative and <= MAX_ARMIES_PER_TERRITORY.
        In simultaneous mode, multiple players can coexist in a territory before
        battle resolution, so we check per-player limits, not the combined total."""
        max_armies = self.game.MAX_ARMIES_PER_TERRITORY
        for territory, garrisons in self.game.territory_garrisons.items():
            for player, g in garrisons.items():
                total = g.get('unmoved', 0) + g.get('moved', 0)
                if total < 0:
                    self.errors.append(f"Negative armies ({total}) in {territory}/P{player}")
                if total > max_armies:
                    self.errors.append(f"Over limit ({total}) in {territory}/P{player}")

    def _check_garrison_consistency(self):
        """Garrison unmoved+moved should match unit list length exactly."""
        for territory, garrisons in self.game.territory_garrisons.items():
            for player, g in garrisons.items():
                total = g.get('unmoved', 0) + g.get('moved', 0)
                units = len(g.get('units', []))
                # With _sync_garrison_counts() fix, counts should match exactly
                if total != units:
                    self.errors.append(
                        f"Garrison mismatch {territory}/P{player}: "
                        f"count={total}, units={units}"
                    )

    def _check_gold_non_negative(self):
        """All player gold >= 0."""
        for i, gold in enumerate(self.game.player_gold):
            if gold < 0:
                self.errors.append(f"Player {i} has negative gold: {gold}")


def distribute_territories_ffa(game, num_players=4):
    """Distribute 57 territories evenly among 4 players for balanced FFA start."""
    all_territories = list(map_data.get_all_territories())
    random.seed(42)  # Deterministic territory distribution for reproducible tests
    random.shuffle(all_territories)

    print(f"Distributing {len(all_territories)} territories among {num_players} players...")

    for i, territory in enumerate(all_territories):
        player = i % num_players

        # Set ownership
        game.territory_owners[territory] = player
        game.armies[territory] = 3
        game.armies_unmoved[territory] = 3
        game.armies_moved[territory] = 0

        # Create units: 1 Swordsman, 1 Archer, 1 Pikeman
        army_units = [
            {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': 0},
            {'type': 'Archer', 'status': 'ready', 'order': None, 'id': 1},
            {'type': 'Pikeman', 'status': 'ready', 'order': None, 'id': 2}
        ]
        game.army_units[territory] = army_units.copy()

        # Initialize garrison
        game.add_garrison(territory, player, unmoved=3, moved=0, units=army_units.copy())

        # Track starting territory for first territory per player
        if player not in game.player_starting_territories:
            game.player_starting_territories[player] = territory

    # Count territories per player
    counts = [0] * num_players
    for owner in game.territory_owners.values():
        if owner >= 0:
            counts[owner] += 1
    print(f"Territory distribution: {counts}")


def convert_action_to_order(player_id, action_type, action_data):
    """Convert AI action to simultaneous mode order format."""
    if action_type == 'move':
        return {
            'type': 'movement',
            'player_id': player_id,
            'from_territory': action_data.get('from'),
            'to_territory': action_data.get('to'),
            'army_count': action_data.get('army_count', 1),
            'unit_ids': action_data.get('unit_ids', [])
        }
    elif action_type == 'build':
        return {
            'type': 'build',
            'player_id': player_id,
            'territory': action_data.get('territory'),
            'building_type': action_data.get('building'),
            'plot_index': action_data.get('plot')
        }
    elif action_type == 'train':
        return {
            'type': 'train',
            'player_id': player_id,
            'territory': action_data.get('territory'),
            'unit_type': action_data.get('unit_type'),
            'barracks_plot': action_data.get('barracks_plot')
        }
    elif action_type == 'research':
        return {
            'type': 'research',
            'player_id': player_id,
            'tech_id': action_data.get('tech_id')
        }
    elif action_type == 'train_hero':
        return {
            'type': 'train_hero',
            'player_id': player_id,
            'territory': action_data.get('territory'),
            'keep_plot': action_data.get('keep_plot'),
            'hero_type': action_data.get('hero_type')
        }
    elif action_type == 'upgrade_castle':
        return {
            'type': 'upgrade_castle',
            'player_id': player_id,
            'territory': action_data.get('territory'),
            'plot_index': action_data.get('plot')
        }
    elif action_type == 'demolish':
        return {
            'type': 'demolish',
            'player_id': player_id,
            'territory': action_data.get('territory'),
            'plot_index': action_data.get('plot')
        }
    elif action_type == 'hero_ability':
        return {
            'type': 'hero_ability',
            'player_id': player_id,
            'hero_type': action_data.get('hero_type'),
            'ability_name': action_data.get('ability_name'),
            'target': action_data.get('target')
        }
    return None


def make_ai_decisions_sync(sim_state, ai_players, verbose=False):
    """
    Make AI decisions for all players synchronously.
    Queues orders to sim_state and marks players ready.
    Returns dict of {player_id: orders_queued}.
    """
    orders_per_player = {}
    for player_id in range(sim_state.gs.num_players):
        if player_id in sim_state.eliminated_players:
            sim_state.mark_ready(player_id)
            orders_per_player[player_id] = 0
            continue

        # Check if player has territories
        player_territories = sum(1 for o in sim_state.gs.territory_owners.values() if o == player_id)
        if player_territories == 0:
            sim_state.eliminated_players.append(player_id)
            sim_state.mark_ready(player_id)
            orders_per_player[player_id] = 0
            continue

        ai_player = ai_players.get(player_id)
        if not ai_player:
            sim_state.mark_ready(player_id)
            orders_per_player[player_id] = 0
            continue

        try:
            # Plan actions
            ai_player.actions_taken = []
            ai_player._plan_turn_actions(sim_state.gs)

            # Convert to orders and queue
            orders_queued = 0
            for action_type, action_data in ai_player.actions_taken:
                order = convert_action_to_order(player_id, action_type, action_data)
                if order:
                    sim_state.add_order(player_id, order)
                    orders_queued += 1

            orders_per_player[player_id] = orders_queued

            if verbose:
                print(f"  P{player_id+1}: {orders_queued} orders queued")

            # Mark ready
            sim_state.mark_ready(player_id)

        except Exception as e:
            print(f"  [ERROR] P{player_id+1} planning failed: {e}")
            traceback.print_exc()
            sim_state.mark_ready(player_id)
            orders_per_player[player_id] = 0

    return orders_per_player


def execute_round_sync(sim_state, phase_manager, ai_players, verbose=False):
    """
    Execute one simultaneous round synchronously.
    Returns tuple: (success, battles_resolved, orders_per_player)
    """
    try:
        # CRITICAL: Process turn-start effects for ALL players
        # In simultaneous mode, all constructions complete at round start
        for player_id in range(sim_state.gs.num_players):
            sim_state.gs.current_player = player_id
            sim_state.gs.finish_constructions()
            sim_state.gs.finish_training()
            sim_state.gs.finish_hero_training()
            sim_state.gs.finish_research()
            sim_state.gs.finish_castle_upgrades()

        # Phase 1: Planning
        sim_state.start_planning_phase()

        # Make AI decisions
        orders_per_player = make_ai_decisions_sync(sim_state, ai_players, verbose)

        # Phase 2: Execution
        if sim_state.all_players_ready():
            # Manually trigger execution (normally happens via mark_ready callback)
            sim_state.sim_phase = 'executing'
            phase_manager.begin_execution(sim_state.player_orders)

        # Skip animations - mark all as complete
        while sim_state.gs.active_animations:
            for anim in sim_state.gs.active_animations:
                anim.completed = True
            sim_state.gs.active_animations = []

        # Process arrivals
        if hasattr(phase_manager, '_sim_pending_arrivals') and phase_manager._sim_pending_arrivals:
            phase_manager._process_arrivals()
            phase_manager._detect_conflicts()

        # Phase 3: Resolution - auto-resolve battles
        battles_resolved = 0

        # Handle pending battles from phase_manager
        while phase_manager.pending_battles:
            battle_info = phase_manager.pending_battles.pop(0)
            territory = battle_info.get('territory')
            players = battle_info.get('players', [])

            if verbose:
                print(f"    Battle at {territory}: {players}")

            # Create Battle object and add to game state's pending_battles
            # Then resolve it
            try:
                from game_state import Battle

                # Get armies for each player in this territory
                garrison = sim_state.gs.territory_garrisons.get(territory, {})
                battle = Battle(territory)

                for pid in players:
                    pg = garrison.get(pid, {})
                    army_count = pg.get('unmoved', 0) + pg.get('moved', 0)
                    if army_count > 0:
                        # Get composition
                        composition = {}
                        for unit in pg.get('units', []):
                            ut = unit.get('type', 'Swordsman')
                            composition[ut] = composition.get(ut, 0) + 1
                        battle.add_army(pid, army_count, composition)

                # Add to game state and resolve
                if battle.get_total_armies() > 0:
                    sim_state.gs.pending_battles.append(battle)
                    sim_state.gs.resolve_battle(0)
                    battles_resolved += 1

            except Exception as e:
                print(f"    [ERROR] Battle resolution failed: {e}")

        # Also resolve any battles in game state's pending_battles
        while sim_state.gs.pending_battles:
            try:
                sim_state.gs.resolve_battle(0)
                battles_resolved += 1
            except Exception as e:
                print(f"    [ERROR] Battle resolution failed: {e}")
                if sim_state.gs.pending_battles:
                    sim_state.gs.pending_battles.pop(0)

        # Complete round
        sim_state.complete_round()

        return (True, battles_resolved, orders_per_player)

    except Exception as e:
        print(f"  [CRITICAL] Round execution failed: {e}")
        traceback.print_exc()
        return (False, 0, {})


def get_territory_counts(game, num_players=4):
    """Get territory count per player."""
    counts = [0] * num_players
    for owner in game.territory_owners.values():
        if owner >= 0:
            counts[owner] += 1
    return counts


def get_total_armies(game, num_players=4):
    """Get total army count per player."""
    counts = [0] * num_players
    for territory, garrisons in game.territory_garrisons.items():
        for player, g in garrisons.items():
            if 0 <= player < num_players:
                counts[player] += g.get('unmoved', 0) + g.get('moved', 0)
    return counts


def run_simultaneous_test(num_rounds=40, verbose=True):
    """
    Run 40-round simultaneous mode FFA test.

    Args:
        num_rounds: Number of simultaneous rounds
        verbose: If True, print detailed output per round

    Returns:
        dict with test results
    """
    print("=" * 60)
    print("40-ROUND FFA SIMULTANEOUS MODE STRESS TEST")
    print("=" * 60)
    print()

    # Initialize map data
    print("Loading map data...")
    map_data.load_polygons()

    # Import after map_data loaded
    from game_state import GameState
    from ai_player import AIPlayer
    from simultaneous.sim_state import SimultaneousGameState
    from simultaneous.sim_phase_manager import SimPhaseManager

    # Create 4-AI FFA game
    print("Creating 4-player FFA game (simultaneous mode)...")
    base_game = GameState(
        num_players=4,
        player_is_ai=[True, True, True, True],
        player_ai_difficulty=[1, 1, 1, 1],
        player_teams=[0, 1, 2, 3],  # FFA
        skip_setup_phase=True,
        game_mode='simultaneous',
        victory_condition='Domination (45+)'
    )
    base_game.phase = 'playing'

    # Wrap in SimultaneousGameState
    sim_state = SimultaneousGameState(base_game)
    phase_manager = SimPhaseManager(sim_state)
    sim_state.phase_manager = phase_manager

    # Distribute territories
    distribute_territories_ffa(base_game)

    # Create AI players
    print("Creating AI players...")
    ai_players = {}
    for i in range(4):
        ai_players[i] = AIPlayer(i, base_game.player_ai_difficulty[i])

    # Validator
    validator = StateValidator(base_game)

    # Track results
    all_errors = []
    round_stats = []
    game_ended = False
    winner = None
    final_round = 0
    total_battles = 0

    try:
        # Run rounds
        for round_num in range(num_rounds):
            final_round = round_num + 1

            if base_game.phase == 'ended':
                game_ended = True
                winner = base_game.winner
                break

            if verbose:
                print(f"\n{'='*50}")
                print(f"ROUND {round_num + 1}")
                print(f"{'='*50}")

            # Execute round
            success, battles, orders_per_player = execute_round_sync(
                sim_state, phase_manager, ai_players, verbose
            )
            total_battles += battles

            if verbose and battles > 0:
                print(f"  Battles resolved: {battles}")

            # Validate state
            errors = validator.validate_all(round_num)
            if errors:
                all_errors.extend([(round_num, e) for e in errors])
                for e in errors:
                    print(f"  [VALIDATION ERROR] {e}")

            # Log round summary
            terr_counts = get_territory_counts(base_game)
            army_counts = get_total_armies(base_game)
            gold = list(base_game.player_gold)

            round_stats.append({
                'round': round_num + 1,
                'territories': terr_counts.copy(),
                'armies': army_counts.copy(),
                'gold': gold.copy(),
                'orders': [orders_per_player.get(p, 0) for p in range(4)],
                'battles': battles,
                'errors': len(errors)
            })

            if verbose:
                print(f"  Territories: {terr_counts}")
                print(f"  Armies: {army_counts}")
                print(f"  Gold: {gold}")

            # Check for victory
            if base_game.phase == 'ended':
                game_ended = True
                winner = base_game.winner
                break

            # Check for stalemate
            active_players = sum(1 for c in terr_counts if c > 0)
            if active_players <= 1:
                print(f"  [STALEMATE] Only {active_players} player(s) remaining")
                game_ended = True
                winner = terr_counts.index(max(terr_counts)) if max(terr_counts) > 0 else -1
                break

            # Check for domination victory
            for p, c in enumerate(terr_counts):
                if c >= 45:
                    print(f"  [VICTORY] Player {p+1} reached {c} territories!")
                    game_ended = True
                    winner = p
                    break

            if game_ended:
                break

    except Exception as e:
        print(f"[CRITICAL ERROR] Test failed: {e}")
        traceback.print_exc()

    # Final summary
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Rounds completed: {final_round}")
    print(f"Total battles: {total_battles}")
    print(f"Game ended: {game_ended}")
    if winner is not None and winner >= 0:
        print(f"Winner: Player {winner + 1}")
    else:
        print("Winner: None (game ongoing)")

    final_terr = get_territory_counts(base_game)
    final_armies = get_total_armies(base_game)
    print(f"Final territories: {final_terr}")
    print(f"Final armies: {final_armies}")
    print(f"Final gold: {list(base_game.player_gold)}")

    # AI behavior analysis
    print()
    print("--- AI BEHAVIOR ANALYSIS ---")
    if round_stats:
        for p in range(4):
            start_terr = round_stats[0]['territories'][p] if round_stats else 0
            end_terr = final_terr[p]
            print(f"  P{p+1}: {start_terr} -> {end_terr} territories ({end_terr - start_terr:+d})")

        total_orders = [0] * 4
        for rs in round_stats:
            for p, o in enumerate(rs.get('orders', [0, 0, 0, 0])):
                total_orders[p] += o
        for p in range(4):
            avg = total_orders[p] / len(round_stats) if round_stats else 0
            print(f"  P{p+1}: {total_orders[p]} total orders ({avg:.1f}/round)")

        total_b = sum(rs.get('battles', 0) for rs in round_stats)
        print(f"  Total battles across all rounds: {total_b}")

        if len(round_stats) >= 2:
            for p in range(4):
                gold_start = round_stats[0]['gold'][p]
                gold_end = round_stats[-1]['gold'][p]
                print(f"  P{p+1}: Gold {gold_start} -> {gold_end} ({gold_end - gold_start:+d})")

    # Building analysis
    print()
    print("--- BUILDING ANALYSIS ---")
    building_counts = {}
    for territory, plots in base_game.buildings.items():
        for plot_index, building_type in plots.items():
            building_counts[building_type] = building_counts.get(building_type, 0) + 1
    if building_counts:
        for b_type, count in sorted(building_counts.items(), key=lambda x: -x[1]):
            print(f"  {b_type}: {count}")
    else:
        print("  No buildings constructed!")

    # Hero analysis
    print()
    print("--- HERO ANALYSIS ---")
    for p in range(4):
        player_heroes = base_game.heroes.get(p, {})
        if player_heroes:
            for hero_type, hero_data in player_heroes.items():
                location = hero_data.get('keep_territory', 'Unknown')
                level = hero_data.get('level', 1)
                print(f"  P{p+1}: {hero_type} (Lv{level}) at {location}")
        else:
            print(f"  P{p+1}: No heroes")

    print()
    print(f"Total validation errors: {len(all_errors)}")
    if all_errors:
        print("Errors:")
        for round_num, error in all_errors[:20]:
            print(f"  Round {round_num+1}: {error}")
        if len(all_errors) > 20:
            print(f"  ... and {len(all_errors) - 20} more errors")

    print()
    print("=" * 60)

    return {
        'rounds_completed': final_round,
        'total_battles': total_battles,
        'game_ended': game_ended,
        'winner': winner,
        'final_territories': final_terr,
        'final_armies': final_armies,
        'final_gold': list(base_game.player_gold),
        'total_errors': len(all_errors),
        'errors': all_errors,
        'round_stats': round_stats
    }


import pytest


@pytest.mark.slow
def test_ffa_simultaneous_40turn():
    """Pytest wrapper: 4-player FFA simultaneous mode with state validation, 10 rounds."""
    results = run_simultaneous_test(num_rounds=10, verbose=False)
    assert results is not None, "Test runner returned None"
    assert results.get('total_errors', 1) == 0, f"State validation errors: {results.get('total_errors')}"
    assert results['rounds_completed'] > 0, "No rounds were completed"
    assert sum(results['final_territories']) == 57, f"Territory sum != 57: {results['final_territories']}"


if __name__ == '__main__':
    # Run with verbose output
    start_time = time.time()
    results = run_simultaneous_test(num_rounds=40, verbose=True)
    elapsed = time.time() - start_time

    print(f"\nTest completed in {elapsed:.1f} seconds")
    print(f"Result: {'PASS' if results['total_errors'] == 0 else 'FAIL'}")
    if results['total_battles'] > 0:
        print(f"SUCCESS - {results['total_battles']} battles occurred!")
    else:
        print("WARNING - No battles occurred")
