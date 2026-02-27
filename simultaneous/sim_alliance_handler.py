# -*- coding: utf-8 -*-
# simultaneous/sim_alliance_handler.py
# Alliance Territory Handler for Simultaneous Turn Mode

"""
SimAllianceHandler - Handles Allied Territory Capture
======================================================

When multiple allied armies arrive at a neutral or enemy territory
simultaneously, this handler manages the territory ownership decision.

Rules:
    - Biggest army owner gets to choose the new territory owner
    - If tied, lowest player index wins (deterministic for multiplayer sync)
    - All allied armies remain in territory with original ownership
    - Blue particle marker indicates alliance arrival
"""

from typing import Dict, List, Optional


class SimAllianceHandler:
    """
    Handles alliance arrival scenarios and territory ownership decisions.

    When allied players capture territory together:
    1. Territory ownership must be assigned to ONE player
    2. The player with the biggest army chooses (or dice roll if tied)
    3. All armies remain in territory, keeping original owners
    4. If army limit exceeded, territory marked for overflow
    """

    def __init__(self, sim_state):
        """
        Initialize the alliance handler.

        Args:
            sim_state: The SimultaneousGameState instance
        """
        self.sim_state = sim_state
        self.gs = sim_state.gs

    def determine_chooser(self, territory: str, allied_players: List[int]) -> int:
        """
        Determine which player gets to choose the territory owner.

        The player with the biggest army chooses. If tied, dice roll.

        Args:
            territory: Territory being captured
            allied_players: List of allied player IDs present

        Returns:
            Player ID who gets to choose
        """
        if len(allied_players) == 1:
            return allied_players[0]

        # Find player with biggest army
        max_army = 0
        candidates = []

        for player_id in allied_players:
            army_count = self._get_player_army_count(territory, player_id)

            if army_count > max_army:
                max_army = army_count
                candidates = [player_id]
            elif army_count == max_army:
                candidates.append(player_id)

        # If tied, use deterministic tiebreaker (lowest player index)
        # IMPORTANT: Do NOT use random.choice here - it causes desync between host and client
        # because each side would independently roll dice and get different results
        if len(candidates) > 1:
            return min(candidates)  # Lowest player index wins tie

        return candidates[0]

    def _get_player_army_count(self, territory: str, player_id: int) -> int:
        """
        Get a player's army count in a territory.

        Args:
            territory: Territory name
            player_id: Player index

        Returns:
            Total army count (unmoved + moved)
        """
        garrison = self.gs.territory_garrisons.get(territory, {})
        player_garrison = garrison.get(player_id, {})
        return player_garrison.get('unmoved', 0) + player_garrison.get('moved', 0)

    def get_ownership_options(
        self,
        territory: str,
        allied_players: List[int]
    ) -> List[dict]:
        """
        Get the list of ownership options for the chooser.

        Options include all participating allies plus self.

        Args:
            territory: Territory being assigned
            allied_players: List of allied player IDs

        Returns:
            List of option dictionaries with player info
        """
        options = []

        for player_id in allied_players:
            player_name = self.gs.player_names[player_id]
            if not player_name:
                player_name = f"Player {player_id + 1}"

            army_count = self._get_player_army_count(territory, player_id)

            options.append({
                'player_id': player_id,
                'name': player_name,
                'army_count': army_count,
                'color': self.gs.player_colors[player_id]
            })

        return options

    def assign_territory(self, territory: str, new_owner: int):
        """
        Assign territory ownership to a player.

        All allied armies remain in territory with their original owners.
        Territory ownership transfers to the chosen player.

        Args:
            territory: Territory name
            new_owner: Player who will own the territory
        """
        # Set new owner
        self.gs.territory_owners[territory] = new_owner
        self.gs.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses

        # Check for army overflow
        self._check_overflow(territory)

    def _check_overflow(self, territory: str):
        """
        Check if territory has army overflow and mark if so.

        Args:
            territory: Territory name
        """
        garrison = self.gs.territory_garrisons.get(territory, {})
        total = sum(
            g.get('unmoved', 0) + g.get('moved', 0)
            for g in garrison.values()
        )

        if total > self.gs.MAX_ARMIES_PER_TERRITORY:
            self.sim_state.mark_overflow_territory(territory)

    def calculate_allied_casualties(
        self,
        territory: str,
        allied_players: List[int],
        total_casualties: int
    ) -> Dict[int, int]:
        """
        Calculate casualty distribution among allied armies.

        Casualties are distributed proportionally based on army size.

        Args:
            territory: Territory where battle occurred
            allied_players: List of allied player IDs
            total_casualties: Total casualties to distribute

        Returns:
            Dictionary of {player_id: casualties}
        """
        if total_casualties <= 0:
            return {}

        # Calculate total allied army
        total_army = 0
        player_armies = {}

        for player_id in allied_players:
            army = self._get_player_army_count(territory, player_id)
            player_armies[player_id] = army
            total_army += army

        if total_army <= 0:
            return {}

        # Distribute proportionally
        casualties = {}
        remaining = total_casualties

        for player_id, army in player_armies.items():
            # Proportional share
            share = int((army / total_army) * total_casualties)
            # Cap at player's actual army
            share = min(share, army)
            casualties[player_id] = share
            remaining -= share

        # Distribute any remaining casualties to largest armies
        if remaining > 0:
            # Sort by army size descending
            sorted_players = sorted(
                player_armies.items(),
                key=lambda x: x[1],
                reverse=True
            )

            for player_id, army in sorted_players:
                if remaining <= 0:
                    break

                current = casualties.get(player_id, 0)
                can_take = army - current

                if can_take > 0:
                    take = min(can_take, remaining)
                    casualties[player_id] = current + take
                    remaining -= take

        return casualties

    def apply_casualties(
        self,
        territory: str,
        casualties: Dict[int, int]
    ):
        """
        Apply casualties to player garrisons in a territory.

        Args:
            territory: Territory name
            casualties: Dictionary of {player_id: casualties}
        """
        garrison = self.gs.territory_garrisons.get(territory, {})

        for player_id, count in casualties.items():
            if player_id not in garrison:
                continue

            player_garrison = garrison[player_id]
            remaining = count

            # Remove from moved first
            moved = player_garrison.get('moved', 0)
            from_moved = min(moved, remaining)
            player_garrison['moved'] = moved - from_moved
            remaining -= from_moved

            # Then from unmoved
            if remaining > 0:
                unmoved = player_garrison.get('unmoved', 0)
                from_unmoved = min(unmoved, remaining)
                player_garrison['unmoved'] = unmoved - from_unmoved

            # Remove units from unit list if tracked
            units = player_garrison.get('units', [])
            if units and count > 0:
                # Remove units from the end
                for _ in range(min(count, len(units))):
                    units.pop()
