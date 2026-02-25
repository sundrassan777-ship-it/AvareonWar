# -*- coding: utf-8 -*-
"""
Fixed 40-Turn FFA Sequential Mode Test
======================================

Properly simulates animation completion by adding to pending_arrivals.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
import random
import time
import traceback


def distribute_territories_ffa(game, num_players=4):
    """Distribute 57 territories evenly among 4 players for balanced FFA start."""
    all_territories = list(map_data.get_all_territories())
    random.shuffle(all_territories)

    print(f"Distributing {len(all_territories)} territories among {num_players} players...")

    for i, territory in enumerate(all_territories):
        player = i % num_players
        game.territory_owners[territory] = player
        game.armies[territory] = 3
        game.armies_unmoved[territory] = 3
        game.armies_moved[territory] = 0

        army_units = [
            {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': 0},
            {'type': 'Archer', 'status': 'ready', 'order': None, 'id': 1},
            {'type': 'Pikeman', 'status': 'ready', 'order': None, 'id': 2}
        ]
        game.army_units[territory] = army_units.copy()
        game.add_garrison(territory, player, unmoved=3, moved=0, units=army_units.copy())

        if player not in game.player_starting_territories:
            game.player_starting_territories[player] = territory

    counts = [0] * num_players
    for owner in game.territory_owners.values():
        if owner >= 0:
            counts[owner] += 1
    print(f"Territory distribution: {counts}")


def execute_ai_turn_fixed(ai_player, game):
    """
    Execute AI turn with FIXED animation processing.
    Properly adds completed animations to pending_arrivals.
    """
    player_index = ai_player.player_index

    player_territories = sum(1 for o in game.territory_owners.values() if o == player_index)
    if player_territories == 0:
        return (0, 0, True)

    try:
        # Plan actions
        ai_player.actions_taken = []
        ai_player._plan_turn_actions(game)
        num_actions = len(ai_player.actions_taken)

        # Execute actions
        for action_type, action_data in ai_player.actions_taken:
            try:
                ai_player._execute_action_internal(game, action_type, action_data)
            except Exception as e:
                print(f"    [ERROR] Action {action_type} failed: {e}")

        # End turn - this calls execute_all_orders() if orders exist
        game.next_player()

        # FIX: Properly simulate animation completion
        # Move animations to pending_arrivals (like update_animations does)
        while game.active_animations:
            for anim in game.active_animations[:]:  # Copy list to avoid modification during iteration
                anim.completed = True
                anim.progress = 1.0
                # KEY FIX: Add to pending_arrivals like update_animations() does
                game.pending_arrivals.append(anim)
                game.active_animations.remove(anim)

        # Now process arrivals (this detects battles)
        if game.pending_arrivals:
            game._process_arrivals()

        # Resolve all battles
        battles_resolved = 0
        while game.pending_battles:
            try:
                game.resolve_battle(0)
                battles_resolved += 1
            except Exception as e:
                print(f"    [ERROR] Battle resolution failed: {e}")
                if game.pending_battles:
                    game.pending_battles.pop(0)

        # After battles resolved, advance to next player if needed
        if game.turn_phase == 'battles' and not game.pending_battles:
            game._advance_to_next_player()

        return (num_actions, battles_resolved, True)

    except Exception as e:
        print(f"    [CRITICAL] AI turn failed: {e}")
        traceback.print_exc()
        try:
            game.next_player()
        except Exception:
            pass
        return (0, 0, False)


def get_territory_counts(game, num_players=4):
    counts = [0] * num_players
    for owner in game.territory_owners.values():
        if owner >= 0:
            counts[owner] += 1
    return counts


def run_fixed_test(num_turns=40, verbose=True):
    """Run sequential test with fixed animation processing."""
    print("=" * 60)
    print("40-TURN FFA SEQUENTIAL MODE TEST (FIXED)")
    print("=" * 60)
    print()

    print("Loading map data...")
    map_data.load_polygons()

    from game_state import GameState
    from ai_player import AIPlayer

    print("Creating 4-player FFA game...")
    game = GameState(
        num_players=4,
        player_is_ai=[True, True, True, True],
        player_ai_difficulty=[1, 1, 1, 1],
        player_teams=[0, 1, 2, 3],
        skip_setup_phase=True,
        victory_condition='Domination (45+)'
    )
    game.phase = 'playing'
    game.turn_phase = 'planning'

    distribute_territories_ffa(game)

    print("Creating AI players...")
    ai_players = {}
    for i in range(4):
        ai_players[i] = AIPlayer(i, game.player_ai_difficulty[i])

    total_battles = 0
    final_turn = 0

    for turn in range(num_turns):
        final_turn = turn + 1

        if verbose:
            print(f"\n{'='*50}")
            print(f"TURN {turn + 1}")
            print(f"{'='*50}")

        turn_battles = 0
        for player in range(4):
            if game.phase == 'ended':
                break

            game.current_player = player
            game.turn_phase = 'planning'

            num_actions, battles, success = execute_ai_turn_fixed(ai_players[player], game)
            turn_battles += battles

            if verbose and (num_actions > 0 or battles > 0):
                print(f"  P{player+1}: {num_actions} actions, {battles} battles")

        total_battles += turn_battles

        if game.phase == 'ended':
            break

        terr_counts = get_territory_counts(game)

        if verbose:
            print(f"  Territories: {terr_counts}")
            if turn_battles > 0:
                print(f"  ** {turn_battles} battles this turn! **")

        # Check for victory/stalemate
        active_players = sum(1 for c in terr_counts if c > 0)
        if active_players <= 1:
            print(f"  [STALEMATE] Only {active_players} player(s) remaining")
            break

        for p, c in enumerate(terr_counts):
            if c >= 45:
                print(f"  [VICTORY] Player {p+1} reached {c} territories!")
                break

    # Summary
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Turns completed: {final_turn}")
    print(f"Total battles: {total_battles}")

    final_terr = get_territory_counts(game)
    print(f"Final territories: {final_terr}")
    print(f"Starting was: [15, 14, 14, 14]")
    print(f"Territory changes: {[final_terr[i] - [15,14,14,14][i] for i in range(4)]}")
    print()

    return {
        'turns': final_turn,
        'battles': total_battles,
        'territories': final_terr
    }


if __name__ == '__main__':
    start_time = time.time()
    results = run_fixed_test(num_turns=40, verbose=True)
    elapsed = time.time() - start_time

    print(f"Test completed in {elapsed:.1f} seconds")
    print(f"Result: {'SUCCESS - Battles occurred!' if results['battles'] > 0 else 'No battles'}")
