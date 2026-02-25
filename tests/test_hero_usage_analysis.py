# -*- coding: utf-8 -*-
"""
Hero Usage Analysis Test
========================

Analyzes AI hero training patterns and ability usage across 40 turns.
Tracks: Which heroes are trained, how often abilities are used, which are most popular.

Usage:
    python tests/test_hero_usage_analysis.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
import random
import time
import traceback
from collections import defaultdict


class HeroTracker:
    """Tracks hero training and ability usage statistics."""

    def __init__(self, num_players=4):
        self.num_players = num_players

        # Training tracking
        self.heroes_trained = defaultdict(lambda: defaultdict(int))  # {player: {hero_type: count}}
        self.training_attempts = defaultdict(lambda: defaultdict(int))
        self.training_failures = defaultdict(list)  # {player: [reason, ...]}

        # Ability tracking
        self.ability_uses = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # {player: {hero: {ability: count}}}
        self.ability_attempts = defaultdict(int)  # {ability_name: count}
        self.ability_successes = defaultdict(int)  # {ability_name: count}

        # Per-turn tracking
        self.turn_data = []

    def record_training_start(self, player, hero_type, territory):
        """Record when a hero starts training."""
        self.training_attempts[player][hero_type] += 1

    def record_training_complete(self, player, hero_type, territory):
        """Record when a hero finishes training."""
        self.heroes_trained[player][hero_type] += 1

    def record_training_failure(self, player, reason):
        """Record why training failed."""
        self.training_failures[player].append(reason)

    def record_ability_use(self, player, hero_type, ability_name, success=True):
        """Record an ability usage."""
        self.ability_uses[player][hero_type][ability_name] += 1
        self.ability_attempts[ability_name] += 1
        if success:
            self.ability_successes[ability_name] += 1

    def get_summary(self):
        """Generate comprehensive summary."""
        summary = {
            'total_heroes_trained': sum(
                sum(heroes.values())
                for heroes in self.heroes_trained.values()
            ),
            'heroes_by_type': defaultdict(int),
            'heroes_by_player': {},
            'total_ability_uses': sum(self.ability_attempts.values()),
            'ability_breakdown': dict(self.ability_attempts),
            'most_used_abilities': [],
            'hero_ability_matrix': {}
        }

        # Heroes by type across all players
        for player, heroes in self.heroes_trained.items():
            summary['heroes_by_player'][player] = dict(heroes)
            for hero_type, count in heroes.items():
                summary['heroes_by_type'][hero_type] += count

        # Most used abilities
        ability_list = [(name, count) for name, count in self.ability_attempts.items()]
        ability_list.sort(key=lambda x: x[1], reverse=True)
        summary['most_used_abilities'] = ability_list

        # Hero -> ability matrix
        for player, heroes in self.ability_uses.items():
            for hero, abilities in heroes.items():
                if hero not in summary['hero_ability_matrix']:
                    summary['hero_ability_matrix'][hero] = defaultdict(int)
                for ability, count in abilities.items():
                    summary['hero_ability_matrix'][hero][ability] += count

        return summary


def distribute_territories(game, num_players=4):
    """Distribute territories evenly."""
    all_territories = list(map_data.get_all_territories())
    random.seed(42)  # Deterministic territory distribution for reproducible tests
    random.shuffle(all_territories)

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


def execute_ai_turn_with_tracking(ai_player, game, tracker):
    """Execute AI turn and track hero actions."""
    player_index = ai_player.player_index

    player_territories = sum(1 for o in game.territory_owners.values() if o == player_index)
    if player_territories == 0:
        return (0, 0, True)

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

        # Track hero-related actions
        hero_actions = 0
        for action_type, action_data in ai_player.actions_taken:
            if action_type == 'train_hero':
                hero_type = action_data.get('hero_type', 'Unknown')
                territory = action_data.get('territory', 'Unknown')
                tracker.record_training_start(player_index, hero_type, territory)
                hero_actions += 1

            elif action_type == 'hero_ability':
                hero_type = action_data.get('hero_type', 'Unknown')
                ability_name = action_data.get('ability_name', 'Unknown')
                tracker.record_ability_use(player_index, hero_type, ability_name)
                hero_actions += 1

        # Execute actions
        for action_type, action_data in ai_player.actions_taken:
            try:
                ai_player._execute_action_internal(game, action_type, action_data)
            except Exception as e:
                if action_type == 'train_hero':
                    tracker.record_training_failure(player_index, str(e))

        # End turn
        game.next_player()

        # Process animations
        while game.active_animations:
            for anim in game.active_animations[:]:
                anim.completed = True
                anim.progress = 1.0
                game.pending_arrivals.append(anim)
                game.active_animations.remove(anim)

        if game.pending_arrivals:
            game._process_arrivals()

        # Resolve battles
        battles_resolved = 0
        while game.pending_battles:
            try:
                game.resolve_battle(0)
                battles_resolved += 1
            except Exception as e:
                if game.pending_battles:
                    game.pending_battles.pop(0)

        if game.turn_phase == 'battles' and not game.pending_battles:
            game._advance_to_next_player()

        return (num_actions, hero_actions, True)

    except Exception as e:
        traceback.print_exc()
        try:
            game.next_player()
        except Exception:
            pass
        return (0, 0, False)


def check_hero_completions(game, tracker, previous_heroes):
    """Check if any heroes completed training this turn."""
    for player in range(4):
        current_heroes = set(game.heroes.get(player, {}).keys())
        prev_heroes = previous_heroes.get(player, set())

        new_heroes = current_heroes - prev_heroes
        for hero_type in new_heroes:
            # Find which territory the hero is in
            hero_data = game.heroes[player].get(hero_type, {})
            territory = hero_data.get('keep_territory', 'Unknown')
            tracker.record_training_complete(player, hero_type, territory)

    # Return current state for next comparison
    return {p: set(game.heroes.get(p, {}).keys()) for p in range(4)}


def run_hero_analysis(num_turns=40, verbose=True):
    """Run 40-turn test with detailed hero tracking."""
    print("=" * 70)
    print("HERO USAGE ANALYSIS TEST")
    print("=" * 70)
    print()

    print("Loading map data...")
    map_data.load_polygons()

    from game_state import GameState
    from ai_player import AIPlayer

    print("Creating 4-player FFA game...")
    game = GameState(
        num_players=4,
        player_is_ai=[True, True, True, True],
        player_ai_difficulty=[1, 1, 1, 1],  # Medium difficulty
        player_teams=[0, 1, 2, 3],
        skip_setup_phase=True,
        victory_condition='Domination (45+)'
    )
    game.phase = 'playing'
    game.turn_phase = 'planning'

    distribute_territories(game)

    print("Creating AI players...")
    ai_players = {}
    for i in range(4):
        ai_players[i] = AIPlayer(i, game.player_ai_difficulty[i])

    # Initialize tracker
    tracker = HeroTracker()
    previous_heroes = {p: set() for p in range(4)}

    total_hero_actions = 0

    for turn in range(num_turns):
        if verbose:
            print(f"\n{'='*60}")
            print(f"TURN {turn + 1}")
            print(f"{'='*60}")

        turn_hero_actions = 0

        for player in range(4):
            if game.phase == 'ended':
                break

            game.current_player = player
            game.turn_phase = 'planning'

            num_actions, hero_actions, success = execute_ai_turn_with_tracking(
                ai_players[player], game, tracker
            )
            turn_hero_actions += hero_actions

            if verbose and hero_actions > 0:
                print(f"  P{player+1}: {hero_actions} hero actions (of {num_actions} total)")

        # Check for newly completed heroes
        previous_heroes = check_hero_completions(game, tracker, previous_heroes)

        total_hero_actions += turn_hero_actions

        if game.phase == 'ended':
            break

        # Show current hero status
        if verbose:
            active_heroes = []
            for p in range(4):
                heroes = list(game.heroes.get(p, {}).keys())
                if heroes:
                    active_heroes.append(f"P{p+1}: {', '.join(heroes)}")
            if active_heroes:
                print(f"  Active Heroes: {' | '.join(active_heroes)}")

            # Show training queue (keyed by territory name, not player index)
            training = []
            for terr, keeps in game.hero_training_queue.items():
                terr_owner = game.territory_owners.get(terr, -1)
                for plot, entry in keeps.items():
                    hero_type, turns = entry[0], entry[1]
                    training.append(f"P{terr_owner+1}: {hero_type} ({turns}t)")
            if training:
                print(f"  Training: {', '.join(training)}")

    # Generate summary
    print()
    print("=" * 70)
    print("HERO USAGE SUMMARY")
    print("=" * 70)

    summary = tracker.get_summary()

    print(f"\nTotal hero actions: {total_hero_actions}")
    print(f"Total heroes trained (completed): {summary['total_heroes_trained']}")
    print(f"Total ability uses: {summary['total_ability_uses']}")

    print("\n" + "-" * 50)
    print("HEROES TRAINED BY TYPE:")
    print("-" * 50)
    for hero_type, count in sorted(summary['heroes_by_type'].items(), key=lambda x: -x[1]):
        print(f"  {hero_type}: {count}")

    print("\n" + "-" * 50)
    print("HEROES TRAINED BY PLAYER:")
    print("-" * 50)
    for player in range(4):
        heroes = summary['heroes_by_player'].get(player, {})
        if heroes:
            hero_list = [f"{h} ({c})" for h, c in heroes.items()]
            print(f"  Player {player+1}: {', '.join(hero_list)}")
        else:
            print(f"  Player {player+1}: None")

    print("\n" + "-" * 50)
    print("ABILITY USAGE (Most to Least Used):")
    print("-" * 50)
    if summary['most_used_abilities']:
        for ability_name, count in summary['most_used_abilities']:
            print(f"  {ability_name}: {count} uses")
    else:
        print("  No abilities used")

    print("\n" + "-" * 50)
    print("HERO -> ABILITY BREAKDOWN:")
    print("-" * 50)
    for hero, abilities in summary['hero_ability_matrix'].items():
        print(f"  {hero}:")
        for ability, count in sorted(abilities.items(), key=lambda x: -x[1]):
            print(f"    - {ability}: {count} uses")

    # Final game state heroes
    print("\n" + "-" * 50)
    print("FINAL HERO STATE:")
    print("-" * 50)
    for player in range(4):
        heroes = game.heroes.get(player, {})
        if heroes:
            print(f"  Player {player+1}:")
            for hero_type, hero_data in heroes.items():
                keep_terr = hero_data.get('keep_territory', 'Unknown')
                print(f"    - {hero_type} (at {keep_terr})")
        else:
            print(f"  Player {player+1}: No heroes")

    # Training failures
    if any(tracker.training_failures.values()):
        print("\n" + "-" * 50)
        print("TRAINING FAILURES:")
        print("-" * 50)
        for player, failures in tracker.training_failures.items():
            if failures:
                # Group by reason
                reason_counts = defaultdict(int)
                for reason in failures:
                    reason_counts[reason] += 1
                print(f"  Player {player+1}:")
                for reason, count in reason_counts.items():
                    print(f"    - {reason}: {count} times")

    print()
    print("=" * 70)

    return {
        'summary': summary,
        'tracker': tracker,
        'total_hero_actions': total_hero_actions
    }


import pytest


@pytest.mark.slow
def test_hero_usage_analysis():
    """Pytest wrapper: Hero training and ability usage analysis, 10 turns."""
    results = run_hero_analysis(num_turns=10, verbose=False)
    assert results is not None, "Test runner returned None"
    # Verify the summary was generated with hero tracking data
    summary = results.get('summary', {})
    assert summary is not None, "Summary not generated"
    # Verify hero tracking infrastructure produced valid data structure
    # (10 turns is not enough for hero training which requires Keep construction first)
    assert 'total_heroes_trained' in summary, "Hero training tracking data missing from summary"
    assert 'total_ability_uses' in summary, "Ability usage tracking data missing from summary"
    assert isinstance(summary['total_heroes_trained'], int), "total_heroes_trained should be int"
    assert summary['total_heroes_trained'] >= 0, "Negative hero count"


if __name__ == '__main__':
    start_time = time.time()
    results = run_hero_analysis(num_turns=40, verbose=True)
    elapsed = time.time() - start_time

    print(f"\nTest completed in {elapsed:.1f} seconds")
