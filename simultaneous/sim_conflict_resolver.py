# -*- coding: utf-8 -*-
# simultaneous/sim_conflict_resolver.py
# Conflict Resolution for Simultaneous Turn Mode

"""
SimConflictResolver - Handles Movement Conflicts
================================================

Resolves crossing army conflicts when two players order armies
to attack each other's territories simultaneously.

Rules:
    - Stronger army attacks, weaker is forced to defend
    - Equal strength: dice roll determines attacker/defender
    - Forced defender gets popup notification
"""

import random
from typing import Dict, List, Tuple, Optional, Any


class SimConflictResolver:
    """
    Resolves crossing army and multi-army arrival conflicts.

    Crossing Armies:
        When P1 orders A->B while P2 orders B->A, the stronger
        army gets to attack while the weaker is forced to defend.

    Multi-Army Arrivals:
        When 3+ armies from different teams arrive at the same
        territory, a dice roll determines battle order.
    """

    def __init__(self, sim_state):
        """
        Initialize the conflict resolver.

        Args:
            sim_state: The SimultaneousGameState instance
        """
        self.sim_state = sim_state
        self.gs = sim_state.gs

        # Track conflicts found and their resolutions
        self.detected_conflicts: List[dict] = []
        self.forced_defenders: List[dict] = []

    def detect_crossing_conflicts(
        self, player_orders: Dict[int, List[dict]]
    ) -> List[Tuple[dict, dict]]:
        """
        Detect crossing army conflicts in movement orders.

        A crossing conflict occurs when:
        - Player A orders movement from territory X to territory Y
        - Player B orders movement from territory Y to territory X
        - Players A and B are on different teams (enemies)

        Bug fix: Multiple orders from the same player on the same route
        (e.g., 3 separate A->B orders) are aggregated into a single entry
        before pairing. This prevents duplicate conflict pairs and ensures
        the combined army strength is used for comparison.

        Args:
            player_orders: Dictionary of {player_id: [orders]}

        Returns:
            List of (order1, order2) tuples representing conflicts
            (aggregated — one entry per player per route)
        """
        self.detected_conflicts.clear()
        self.forced_defenders.clear()

        # Step 1: Aggregate movement orders by (player_id, from, to).
        # Multiple orders on the same route from the same player are combined
        # into a single aggregated entry with summed army_count.
        # This prevents duplicate conflict pairs (Bug 1) and ensures the
        # total force is used for strength comparison (Bug 2).
        aggregated = {}  # key: (player_id, from, to) -> aggregated order dict
        for player_id, orders in player_orders.items():
            for order in orders:
                if order.get('type') == 'movement':
                    agg_key = (
                        player_id,
                        order.get('from_territory'),
                        order.get('to_territory')
                    )
                    if agg_key not in aggregated:
                        # Create aggregated entry from first matching order
                        aggregated[agg_key] = {
                            'type': 'movement',
                            'from_territory': order.get('from_territory'),
                            'to_territory': order.get('to_territory'),
                            'army_count': order.get('army_count', 0),
                            'player_id': player_id
                        }
                    else:
                        # Sum army_count into existing aggregated entry
                        aggregated[agg_key]['army_count'] += order.get('army_count', 0)

        # Step 2: Find crossing pairs from the aggregated entries.
        # Since there is exactly one entry per (player, from, to), no
        # duplicate conflict pairs can be produced.
        aggregated_list = list(aggregated.values())
        conflicts = []
        # Deduplicate by territory pair + player pair to be extra safe (Bug fix safety net)
        seen_conflict_keys = set()

        for i, order1 in enumerate(aggregated_list):
            for j, order2 in enumerate(aggregated_list):
                if i >= j:
                    continue

                if self._is_crossing_conflict(order1, order2):
                    # Build a canonical key: sorted territory pair + sorted player pair
                    terr_pair = tuple(sorted([
                        order1.get('from_territory'),
                        order1.get('to_territory')
                    ]))
                    player_pair = tuple(sorted([
                        order1.get('player_id'),
                        order2.get('player_id')
                    ]))
                    conflict_key = (terr_pair, player_pair)

                    if conflict_key not in seen_conflict_keys:
                        seen_conflict_keys.add(conflict_key)
                        conflicts.append((order1, order2))

        return conflicts

    def _is_crossing_conflict(self, order1: dict, order2: dict) -> bool:
        """
        Check if two orders form a crossing conflict.

        Args:
            order1: First movement order
            order2: Second movement order

        Returns:
            True if the orders cross (A->B and B->A between enemies)
        """
        from1 = order1.get('from_territory')
        to1 = order1.get('to_territory')
        player1 = order1.get('player_id')

        from2 = order2.get('from_territory')
        to2 = order2.get('to_territory')
        player2 = order2.get('player_id')

        # Check for crossing paths
        if from1 != to2 or from2 != to1:
            return False

        # Check if players are enemies
        # Player -1 (neutral) is always hostile — avoid negative indexing into player_teams list
        team1 = -1 if player1 == -1 else self.gs.player_teams[player1]
        team2 = -1 if player2 == -1 else self.gs.player_teams[player2]

        return team1 != team2

    def resolve_crossing_conflicts(
        self,
        player_orders: Dict[int, List[dict]],
        conflicts: List[Tuple[dict, dict]]
    ) -> Dict[int, List[dict]]:
        """
        Resolve crossing conflicts and modify orders accordingly.

        The weaker army's order is cancelled (forced to defend).
        Equal strength: dice roll determines outcome.

        Conflict entries use aggregated army_count (combined from multiple
        orders on the same route). When the weaker side is determined,
        ALL of that player's orders on that route are cancelled, not just one.

        Args:
            player_orders: Dictionary of {player_id: [orders]}
            conflicts: List of (order1, order2) conflict tuples (aggregated)

        Returns:
            Modified player_orders with cancelled orders removed
        """
        # Create a copy to modify
        modified_orders = {
            player_id: list(orders)
            for player_id, orders in player_orders.items()
        }

        for order1, order2 in conflicts:
            # Strength comparison uses the aggregated army_count, which
            # is the combined strength of all orders on this route
            strength1 = self._calculate_order_strength(order1)
            strength2 = self._calculate_order_strength(order2)

            # Determine winner (attacker) and loser (forced defender)
            if strength1 > strength2:
                attacker_order = order1
                defender_order = order2
            elif strength2 > strength1:
                attacker_order = order2
                defender_order = order1
            else:
                # Equal strength - dice roll
                if random.random() < 0.5:
                    attacker_order = order1
                    defender_order = order2
                else:
                    attacker_order = order2
                    defender_order = order1

            # Cancel ALL of the defender's orders on this route (Bug 3 fix).
            # Since the defender may have submitted multiple movement orders
            # from the same territory to the same destination, we must remove
            # every one of them — not just the first match.
            self._cancel_all_route_orders(
                modified_orders,
                defender_order.get('player_id'),
                defender_order.get('from_territory'),
                defender_order.get('to_territory')
            )

            # Record forced defender for notification
            self.forced_defenders.append({
                'player_id': defender_order.get('player_id'),
                'territory': defender_order.get('from_territory'),
                'intended_target': defender_order.get('to_territory'),
                'forced_by': attacker_order.get('player_id')
            })

        return modified_orders

    def _calculate_order_strength(self, order: dict) -> int:
        """
        Calculate the effective strength of a movement order.

        Args:
            order: Movement order dictionary

        Returns:
            Effective strength value
        """
        # Base strength is army count
        army_count = order.get('army_count', 0)

        # Could add modifiers for unit composition, research, etc.
        # For now, just use raw count

        return army_count

    def _cancel_all_route_orders(
        self,
        player_orders: Dict[int, List[dict]],
        player_id: int,
        from_territory: str,
        to_territory: str
    ):
        """
        Cancel ALL movement orders for a specific player on a specific route.

        When the weaker side of a crossing conflict is determined, all of their
        orders on that route must be cancelled — not just the first match.
        This prevents partial cancellation when a player has multiple separate
        movement orders from the same source to the same destination.

        Args:
            player_orders: Dictionary of {player_id: [orders]}
            player_id: The player whose orders to cancel
            from_territory: Source territory of the route
            to_territory: Destination territory of the route
        """
        if player_id not in player_orders:
            return

        # Filter out ALL movement orders matching this player + route.
        # Keep non-movement orders and movement orders on other routes.
        player_orders[player_id] = [
            order for order in player_orders[player_id]
            if not (
                order.get('type') == 'movement' and
                order.get('from_territory') == from_territory and
                order.get('to_territory') == to_territory
            )
        ]

    def _cancel_order(self, player_orders: Dict[int, List[dict]], order: dict):
        """
        Cancel a single order by removing it from the player's order list.

        Note: For crossing conflict resolution, prefer _cancel_all_route_orders()
        which removes ALL orders on a route. This method is kept for backward
        compatibility and other use cases.

        Args:
            player_orders: Dictionary of {player_id: [orders]}
            order: Order to cancel
        """
        player_id = order.get('player_id')

        if player_id in player_orders:
            # Find and remove the first matching order
            for i, existing in enumerate(player_orders[player_id]):
                if self._orders_match(existing, order):
                    player_orders[player_id].pop(i)
                    break

    def _orders_match(self, order1: dict, order2: dict) -> bool:
        """
        Check if two orders are the same movement.

        Matches on type, from_territory, and to_territory. If both orders
        have a player_id, that is also compared to avoid matching orders
        from different players on the same route.
        """
        if not (
            order1.get('type') == order2.get('type') == 'movement' and
            order1.get('from_territory') == order2.get('from_territory') and
            order1.get('to_territory') == order2.get('to_territory')
        ):
            return False

        # If both have player_id, they must match (prevents cross-player confusion)
        pid1 = order1.get('player_id')
        pid2 = order2.get('player_id')
        if pid1 is not None and pid2 is not None:
            return pid1 == pid2

        return True

    def get_forced_defenders(self) -> List[dict]:
        """
        Get list of players who were forced to defend.

        Returns:
            List of forced defender info dictionaries
        """
        return self.forced_defenders

    def resolve_multi_army_battle(
        self,
        territory: str,
        armies: Dict[int, dict]
    ) -> List[Tuple[int, int]]:
        """
        Determine battle order for multi-army arrivals.

        When 3+ enemy armies arrive at the same territory,
        a dice roll determines who fights whom first.

        Args:
            territory: Territory where armies meet
            armies: Dictionary of {player_id: army_info}

        Returns:
            List of (player1, player2) battle pairings in order
        """
        # Group by team
        teams: Dict[int, List[int]] = {}
        for player_id in armies.keys():
            team = -1 if player_id == -1 else self.gs.player_teams[player_id]
            if team not in teams:
                teams[team] = []
            teams[team].append(player_id)

        # If only one team, no battles needed
        if len(teams) <= 1:
            return []

        # Create list of team representatives (one per team)
        team_list = list(teams.keys())
        random.shuffle(team_list)  # Dice roll for battle order

        # Generate battle pairings
        battles = []
        for i in range(len(team_list) - 1):
            # Pick a representative from each team
            team1_players = teams[team_list[i]]
            team2_players = teams[team_list[i + 1]]

            # For simplicity, use first player from each team
            # In practice, all players on a team fight together
            battles.append((team_list[i], team_list[i + 1]))

        return battles
