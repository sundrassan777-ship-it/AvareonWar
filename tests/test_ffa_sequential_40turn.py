# -*- coding: utf-8 -*-
"""
40-Turn FFA Sequential Mode Stress Test
========================================

Tests a 4-player Free-For-All game running for 40 turns in sequential mode.
All players are AI-controlled. Validates game state consistency after each turn.

Usage:
    python tests/test_ffa_sequential_40turn.py

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
    """Validates game state consistency after each turn."""

    def __init__(self, game, num_players=4):
        self.game = game
        self.num_players = num_players
        self.errors = []

    def validate_all(self, turn_num, player_num):
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
        """Army counts non-negative and <= MAX_ARMIES_PER_TERRITORY."""
        for territory, count in self.game.armies.items():
            if count < 0:
                self.errors.append(f"Negative armies ({count}) in {territory}")
            if count > self.game.MAX_ARMIES_PER_TERRITORY:
                self.errors.append(f"Over limit ({count}) in {territory}")

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

        # Create units: 1 Swordsman, 1 Archer, 1 Pikeman (like claim_territory)
        army_units = [
            {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': 0},
            {'type': 'Archer', 'status': 'ready', 'order': None, 'id': 1},
            {'type': 'Pikeman', 'status': 'ready', 'order': None, 'id': 2}
        ]
        game.army_units[territory] = army_units.copy()

        # Initialize garrison
        game.add_garrison(territory, player, unmoved=3, moved=0, units=army_units.copy())

        # Track starting territory for first territory per player (Capital Assault)
        if player not in game.player_starting_territories:
            game.player_starting_territories[player] = territory

    # Count territories per player
    counts = [0] * num_players
    for owner in game.territory_owners.values():
        if owner >= 0:
            counts[owner] += 1
    print(f"Territory distribution: {counts}")


def execute_ai_turn_sync(ai_player, game):
    """
    Execute AI turn synchronously (no threading delays).
    Returns tuple: (num_actions, battles_resolved, success)
    """
    player_index = ai_player.player_index

    # Check if player still has territories (not eliminated)
    player_territories = sum(1 for o in game.territory_owners.values() if o == player_index)
    if player_territories == 0:
        return (0, 0, True)  # Player eliminated, skip

    try:
        # CRITICAL: Process turn-start effects (construction/training completion)
        # This is normally done in _complete_turn_announcement but we skip that animation
        game.finish_constructions()
        game.finish_training()
        game.finish_hero_training()
        game.finish_research()
        game.finish_castle_upgrades()

        # Plan actions
        ai_player.actions_taken = []
        ai_player._plan_turn_actions(game)

        num_actions = len(ai_player.actions_taken)

        # Execute actions (no delays)
        for action_type, action_data in ai_player.actions_taken:
            try:
                ai_player._execute_action_internal(game, action_type, action_data)
            except Exception as e:
                print(f"    [ERROR] Action {action_type} failed: {e}")

        # End turn - executes movement orders
        game.next_player()

        # Process animations immediately (skip actual animation)
        # FIX: Must add animations to pending_arrivals before clearing,
        # just like update_animations() does in the real game loop
        while game.active_animations:
            for anim in game.active_animations[:]:  # Copy list to avoid modification during iteration
                anim.completed = True
                anim.progress = 1.0
                # KEY: Add to pending_arrivals (this is what the original test was missing!)
                game.pending_arrivals.append(anim)
                game.active_animations.remove(anim)

        # Now process arrivals - this detects battles
        if game.pending_arrivals:
            game._process_arrivals()

        # Auto-resolve all battles
        battles_resolved = 0
        while game.pending_battles:
            try:
                game.resolve_battle(0)
                battles_resolved += 1
            except Exception as e:
                print(f"    [ERROR] Battle resolution failed: {e}")
                # Remove failed battle to prevent infinite loop
                if game.pending_battles:
                    game.pending_battles.pop(0)

        if battles_resolved > 0:
            print(f"    Resolved {battles_resolved} battles")

        # After battles resolved, advance to next player if stuck in battles phase
        if game.turn_phase == 'battles' and not game.pending_battles:
            game._advance_to_next_player()

        return (num_actions, battles_resolved, True)

    except Exception as e:
        print(f"    [CRITICAL] AI turn failed: {e}")
        traceback.print_exc()
        # Try to advance anyway
        try:
            game.next_player()
        except Exception:
            pass
        return (0, 0, False)


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


def run_sequential_test(num_turns=40, verbose=True):
    """
    Run 40-turn sequential mode FFA test.

    Args:
        num_turns: Number of full game turns (each turn = all 4 players)
        verbose: If True, print detailed output per turn

    Returns:
        dict with test results
    """
    print("=" * 60)
    print("40-TURN FFA SEQUENTIAL MODE STRESS TEST")
    print("=" * 60)
    print()

    # Initialize map data (required before GameState)
    print("Loading map data...")
    map_data.load_polygons()

    # Import GameState after map_data is loaded
    from game_state import GameState
    from ai_player import AIPlayer

    # Create 4-AI FFA game
    print("Creating 4-player FFA game...")
    game = GameState(
        num_players=4,
        player_is_ai=[True, True, True, True],
        player_ai_difficulty=[1, 1, 1, 1],  # Medium difficulty
        player_teams=[0, 1, 2, 3],  # FFA - each on own team
        skip_setup_phase=True,
        victory_condition='Domination (45+)'
    )
    game.phase = 'playing'
    game.turn_phase = 'planning'

    # Distribute territories
    distribute_territories_ffa(game)

    # Create AI players
    print("Creating AI players...")
    ai_players = {}
    for i in range(4):
        ai_players[i] = AIPlayer(i, game.player_ai_difficulty[i])

    # Validator
    validator = StateValidator(game)

    # Track results
    all_errors = []
    turn_stats = []
    game_ended = False
    winner = None
    final_turn = 0
    total_battles = 0

    try:
        # Run turns
        for turn in range(num_turns):
            final_turn = turn + 1
            turn_actions = []
            turn_errors = []
            turn_battles = 0

            if verbose:
                print(f"\n{'='*50}")
                print(f"TURN {turn + 1}")
                print(f"{'='*50}")

            for player in range(4):
                if game.phase == 'ended':
                    game_ended = True
                    winner = game.winner
                    break

                # Set current player
                game.current_player = player
                game.turn_phase = 'planning'

                # Execute AI turn
                num_actions, battles, success = execute_ai_turn_sync(ai_players[player], game)
                turn_actions.append(num_actions)
                turn_battles += battles

                # M16 fix: Track AI failures instead of silently swallowing
                if not success:
                    turn_errors.append((turn, player, "AI turn raised exception"))

                if verbose and (num_actions > 0 or battles > 0):
                    print(f"  P{player+1}: {num_actions} actions, {battles} battles")

                # Validate state after each player
                errors = validator.validate_all(turn, player)
                if errors:
                    turn_errors.extend([(turn, player, e) for e in errors])
                    all_errors.extend(turn_errors)
                    for e in errors:
                        print(f"  [VALIDATION ERROR] P{player+1}: {e}")

            if game_ended:
                break

            total_battles += turn_battles

            # Log turn summary
            terr_counts = get_territory_counts(game)
            army_counts = get_total_armies(game)
            gold = list(game.player_gold)

            turn_stats.append({
                'turn': turn + 1,
                'territories': terr_counts.copy(),
                'armies': army_counts.copy(),
                'gold': gold.copy(),
                'actions': turn_actions.copy(),
                'battles': turn_battles,
                'errors': len(turn_errors)
            })

            if verbose:
                print(f"  Territories: {terr_counts}")
                print(f"  Armies: {army_counts}")
                print(f"  Gold: {gold}")
                if turn_battles > 0:
                    print(f"  ** {turn_battles} battles this turn! **")

            # Check for victory
            if game.phase == 'ended':
                game_ended = True
                winner = game.winner
                break

            # Check for stalemate (only one player has territories)
            active_players = sum(1 for c in terr_counts if c > 0)
            if active_players <= 1:
                print(f"  [STALEMATE] Only {active_players} player(s) remaining")
                game_ended = True
                winner = terr_counts.index(max(terr_counts)) if max(terr_counts) > 0 else -1
                break

            # Check for victory condition (45+ territories)
            for p, c in enumerate(terr_counts):
                if c >= 45:
                    print(f"  [VICTORY] Player {p+1} reached {c} territories!")
                    game_ended = True
                    winner = p
                    break

    except Exception as e:
        print(f"[CRITICAL ERROR] Test failed: {e}")
        traceback.print_exc()

    # Final summary
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Turns completed: {final_turn}")
    print(f"Total battles: {total_battles}")
    print(f"Game ended: {game_ended}")
    if winner is not None and winner >= 0:
        print(f"Winner: Player {winner + 1}")
    else:
        print("Winner: None (game ongoing)")

    final_terr = get_territory_counts(game)
    final_armies = get_total_armies(game)
    print(f"Final territories: {final_terr}")
    print(f"Final armies: {final_armies}")
    print(f"Final gold: {list(game.player_gold)}")

    # AI behavior analysis
    print()
    print("--- AI BEHAVIOR ANALYSIS ---")
    if turn_stats:
        # Territory growth trends
        for p in range(4):
            start_terr = turn_stats[0]['territories'][p] if turn_stats else 0
            end_terr = final_terr[p]
            print(f"  P{p+1}: {start_terr} -> {end_terr} territories ({end_terr - start_terr:+d})")

        # Action rates
        total_actions = [0] * 4
        for ts in turn_stats:
            for p, a in enumerate(ts['actions']):
                total_actions[p] += a
        for p in range(4):
            avg = total_actions[p] / len(turn_stats) if turn_stats else 0
            print(f"  P{p+1}: {total_actions[p]} total actions ({avg:.1f}/turn)")

        # Battle frequency
        total_b = sum(ts.get('battles', 0) for ts in turn_stats)
        print(f"  Total battles across all turns: {total_b}")

        # Economy analysis
        if len(turn_stats) >= 2:
            for p in range(4):
                gold_start = turn_stats[0]['gold'][p]
                gold_end = turn_stats[-1]['gold'][p]
                print(f"  P{p+1}: Gold {gold_start} -> {gold_end} ({gold_end - gold_start:+d})")

    # Building analysis: game.buildings = {territory: {plot_index: building_type}}
    print()
    print("--- BUILDING ANALYSIS ---")
    building_counts = {}
    for territory, plots in game.buildings.items():
        for plot_index, building_type in plots.items():
            building_counts[building_type] = building_counts.get(building_type, 0) + 1
    if building_counts:
        for b_type, count in sorted(building_counts.items(), key=lambda x: -x[1]):
            print(f"  {b_type}: {count}")
    else:
        print("  No buildings constructed!")

    # Hero analysis: game.heroes = {player_index: {hero_type: hero_data}}
    print()
    print("--- HERO ANALYSIS ---")
    for p in range(4):
        player_heroes = game.heroes.get(p, {})
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
        for turn, player, error in all_errors[:20]:
            print(f"  Turn {turn+1}, P{player+1}: {error}")
        if len(all_errors) > 20:
            print(f"  ... and {len(all_errors) - 20} more errors")

    print()
    print("=" * 60)

    return {
        'turns_completed': final_turn,
        'total_battles': total_battles,
        'game_ended': game_ended,
        'winner': winner,
        'final_territories': final_terr,
        'final_armies': final_armies,
        'final_gold': list(game.player_gold),
        'total_errors': len(all_errors),
        'errors': all_errors,
        'turn_stats': turn_stats
    }


import pytest


@pytest.mark.slow
def test_ffa_sequential_40turn():
    """Pytest wrapper: 4-player FFA sequential mode with state validation, 10 turns."""
    results = run_sequential_test(num_turns=10, verbose=False)
    assert results is not None, "Test runner returned None"
    assert results.get('total_errors', 1) == 0, f"State validation errors: {results.get('total_errors')}"
    assert results['turns_completed'] > 0, "No turns were completed"
    assert sum(results['final_territories']) == 57, f"Territory sum != 57: {results['final_territories']}"


if __name__ == '__main__':
    # Run with verbose output
    start_time = time.time()
    results = run_sequential_test(num_turns=40, verbose=True)
    elapsed = time.time() - start_time

    print(f"\nTest completed in {elapsed:.1f} seconds")
    print(f"Result: {'PASS' if results['total_errors'] == 0 else 'FAIL'}")
    if results['total_battles'] > 0:
        print(f"SUCCESS - {results['total_battles']} battles occurred!")
    else:
        print("WARNING - No battles occurred")
