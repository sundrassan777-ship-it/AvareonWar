# -*- coding: utf-8 -*-
"""
Stress Test Scenario Generator

Creates game states with extreme conditions for performance testing:
- Maximum armies in all territories
- All buildings constructed
- Many simultaneous movement orders
- Multiple pending battles

Usage:
    python tools/stress_test_generator.py [output_path] [--config key=value ...]

Examples:
    python tools/stress_test_generator.py stress_save.json
    python tools/stress_test_generator.py stress_save.json --num-players=4 --armies=100
"""

import json
import random
import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_stress_scenario(config=None):
    """
    Generate a stress test game state dictionary.

    Args:
        config: Dict with customization options:
            - num_players: Number of players (2-4, default 4)
            - armies_per_territory: Armies in each territory (default 50)
            - num_movement_orders: Number of pending orders (default 30)
            - buildings_per_territory: Buildings per territory (default 2)
            - include_heroes: Whether to assign heroes (default True)

    Returns:
        dict: Game state dictionary ready for saving
    """
    import map_data

    config = config or {}
    num_players = config.get('num_players', 4)
    armies_per_territory = config.get('armies_per_territory', 50)
    num_movement_orders = config.get('num_movement_orders', 30)
    buildings_per_territory = config.get('buildings_per_territory', 2)
    include_heroes = config.get('include_heroes', True)

    # Get all territories
    territories = list(map_data.territories.keys())
    num_territories = len(territories)

    print(f"Generating stress scenario:")
    print(f"  Players: {num_players}")
    print(f"  Territories: {num_territories}")
    print(f"  Armies per territory: {armies_per_territory}")
    print(f"  Movement orders: {num_movement_orders}")

    # Build game state
    game_state = {
        'turn_number': 50,
        'current_player': 0,
        'phase': 'playing',
        'territory_owners': {},
        'armies': {},
        'armies_unmoved': {},
        'territory_garrisons': {},
        'buildings': {},
        'production_queues': {},
        'movement_orders': [],
        'pending_battles': [],
        'heroes': {},
        'player_gold': {},
        'player_income': {},
    }

    # Initialize player resources
    for player in range(num_players):
        game_state['player_gold'][player] = 1000
        game_state['player_income'][player] = 100

    # Distribute territories among players
    for i, territory in enumerate(territories):
        player = i % num_players
        game_state['territory_owners'][territory] = player
        game_state['armies'][territory] = armies_per_territory
        game_state['armies_unmoved'][territory] = armies_per_territory

        # Initialize garrison
        game_state['territory_garrisons'][territory] = {
            player: {
                'unmoved': armies_per_territory,
                'moved': 0
            }
        }

        # Add buildings with production
        if buildings_per_territory >= 1:
            game_state['buildings'][territory] = {0: 'Barracks'}
            game_state['production_queues'][territory] = {0: [['Swordsman', 1]]}

        if buildings_per_territory >= 2:
            game_state['buildings'][territory][1] = 'Farm'

    # Assign heroes if requested
    if include_heroes:
        hero_names = [
            'Seledra Rennervail',
            'Vorn Ashkari',
            'Kaspar the Relentless',
            'Morgana Blackthorn'
        ]
        for player in range(min(num_players, len(hero_names))):
            # Find a territory owned by this player
            player_territories = [t for t, o in game_state['territory_owners'].items() if o == player]
            if player_territories:
                game_state['heroes'][player] = {
                    'name': hero_names[player],
                    'territory': player_territories[0],
                    'alive': True,
                    'training_turns_left': 0
                }

    # Create movement orders (creates many arrows on map)
    orders_created = 0
    for _ in range(num_movement_orders * 2):  # Try more to ensure we get enough valid ones
        if orders_created >= num_movement_orders:
            break

        from_t = random.choice(territories)
        neighbors = map_data.get_neighbors(from_t)
        if neighbors:
            to_t = random.choice(neighbors)
            player = game_state['territory_owners'][from_t]

            order = {
                'from_territory': from_t,
                'to_territory': to_t,
                'army_count': min(10, armies_per_territory // 2),
                'player': player
            }
            game_state['movement_orders'].append(order)
            orders_created += 1

    print(f"  Movement orders created: {len(game_state['movement_orders'])}")

    # Create some pending battles (territories with multiple players' armies)
    battles_created = 0
    for i in range(0, min(5, num_territories), 10):
        territory = territories[i]
        # Add a second player's army to create conflict
        defender = game_state['territory_owners'][territory]
        attacker = (defender + 1) % num_players

        game_state['pending_battles'].append({
            'territory': territory,
            'attackers': [attacker],
            'defender': defender,
            'attacker_armies': {attacker: 20},
            'defender_armies': armies_per_territory
        })
        battles_created += 1

    print(f"  Pending battles: {battles_created}")

    return {
        'version': '1.0',
        'scenario_type': 'stress_test',
        'config': config,
        'game_state': game_state
    }


def save_scenario(scenario, output_path):
    """Save scenario to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(scenario, f, indent=2)
    print(f"\nSaved stress scenario to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate stress test scenarios for AvareonWar performance testing'
    )
    parser.add_argument(
        'output',
        nargs='?',
        default='stress_scenario.json',
        help='Output file path (default: stress_scenario.json)'
    )
    parser.add_argument(
        '--num-players',
        type=int,
        default=4,
        help='Number of players (2-4, default: 4)'
    )
    parser.add_argument(
        '--armies',
        type=int,
        default=50,
        help='Armies per territory (default: 50)'
    )
    parser.add_argument(
        '--orders',
        type=int,
        default=30,
        help='Number of movement orders (default: 30)'
    )
    parser.add_argument(
        '--buildings',
        type=int,
        default=2,
        help='Buildings per territory (default: 2)'
    )
    parser.add_argument(
        '--no-heroes',
        action='store_true',
        help='Do not assign heroes'
    )

    args = parser.parse_args()

    config = {
        'num_players': max(2, min(4, args.num_players)),
        'armies_per_territory': max(1, args.armies),
        'num_movement_orders': max(0, args.orders),
        'buildings_per_territory': max(0, min(4, args.buildings)),
        'include_heroes': not args.no_heroes,
    }

    scenario = generate_stress_scenario(config)
    save_scenario(scenario, args.output)


if __name__ == '__main__':
    main()
