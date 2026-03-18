# -*- coding: utf-8 -*-
# simultaneous/sim_state.py
# Simultaneous Game State Wrapper

"""
SimultaneousGameState - Wrapper for Simultaneous Turn Mode
==========================================================

This class wraps the existing GameState to add simultaneous turn functionality.
It manages per-player order queues, ready states, timers, and round progression.

Design:
    - Delegates most operations to the underlying GameState
    - Adds simultaneous-specific state (player orders, ready flags, timers)
    - Coordinates with SimPhaseManager for phase transitions
"""

import time
import threading
from typing import Dict, List, Optional, Any

import map_data
from .sim_debug import sim_log, set_round, set_multiplayer_context


class SimultaneousGameState:
    """
    Wrapper around GameState that adds simultaneous turn functionality.

    In simultaneous mode:
    - All players plan their moves at the same time during the planning phase
    - Orders are hidden from other players until execution
    - When all players are ready (or timers expire), orders execute together
    - Conflicts are resolved through the SimConflictResolver
    """

    # Timer constants (in seconds)
    BASE_TIMER = 60  # Base planning time
    MASTER_PLANNER_BONUS = 30  # Bonus per Master Planner upgrade level
    READY_SAFETY_TIMEOUT = 120  # Safety timeout: force-mark unresponsive players as ready after 120s

    def __init__(self, game_state):
        """
        Initialize simultaneous mode wrapper.

        Args:
            game_state: The underlying GameState instance to wrap
        """
        self.gs = game_state  # Delegate to existing GameState

        # Per-player order queues (hidden from each other)
        # Format: {player_id: [order_dict, ...]}
        self.player_orders: Dict[int, List[dict]] = {
            player_id: [] for player_id in range(game_state.num_players)
        }

        # Ready flags - players who have clicked "End Turn"
        self.players_ready: Dict[int, bool] = {
            player_id: False for player_id in range(game_state.num_players)
        }

        # Per-player timers (remaining seconds)
        # Initialized based on each player's Master Planner research level
        self.player_timers: Dict[int, float] = {}
        self._initialize_timers()

        # Timer start timestamps (for calculating elapsed time)
        self.timer_start_time: Optional[float] = None

        # Safety timeout: tracks when planning phase started (absolute time)
        # If any player hasn't readied after READY_SAFETY_TIMEOUT seconds,
        # they are force-marked as ready to prevent indefinite stalling
        self.planning_phase_start_time: Optional[float] = None

        # Round tracking (replaces turn_number for simultaneous mode)
        self.round_number = 1

        # Simultaneous mode phase
        # 'planning' - All players can queue orders
        # 'executing' - Orders are being animated
        # 'resolving' - Battles and conflicts being resolved
        self.sim_phase = 'planning'

        # Overflow territory tracking
        # Format: {territory: expiry_round}
        # Territories with overflow armies that will disband if not moved
        self.overflow_territories: Dict[str, int] = {}

        # Crossing army conflicts detected during execution
        # Format: [(player1_order, player2_order, resolution_result), ...]
        self.crossing_conflicts: List[tuple] = []

        # Alliance arrival markers pending resolution
        # Format: {territory: {'armies': [...], 'marker_owner': player_id}}
        self.alliance_arrivals: Dict[str, dict] = {}

        # Track eliminated players
        self.eliminated_players: List[int] = []

        # Store reference to phase manager (set externally)
        self.phase_manager = None

        # Thread-safety: deferred execution flag
        # When AI background thread triggers all-ready, execution is deferred to main thread
        # to prevent race conditions with current_player during complete_round()
        self._execution_pending = False

        # Multiplayer flag: True if this is a client (not host)
        # When True, mark_ready won't trigger _begin_execution locally
        # Client waits for SIM_ALL_READY from host instead
        self.is_multiplayer_client = False

        # Multiplayer flag: True if this is a host (not client)
        # When True, mark_ready triggers execution via callback instead of _begin_execution
        # This allows the host to send SIM_ALL_READY to clients
        self.is_multiplayer_host = False

        # Local player index for multiplayer mode
        # Used to determine which orders to validate vs trust from remote
        # None for single-player, 0 for host, 1+ for clients
        self.local_player_index = None

        # Callback for multiplayer host when all players ready
        # Set by main.py to handle SIM_ALL_READY broadcasting
        self.on_all_ready_callback = None

        # Callback for multiplayer host when round completes
        # Set by main.py to broadcast SIM_ROUND_COMPLETE to clients
        self.on_round_complete_callback = None

    def _initialize_timers(self):
        """Initialize planning timers for all players based on research levels."""
        for player_id in range(self.gs.num_players):
            self.player_timers[player_id] = self._get_timer_limit(player_id)

    def _get_timer_limit(self, player_id: int) -> float:
        """
        Calculate timer limit for a player based on Master Planner upgrades.

        Args:
            player_id: The player index

        Returns:
            Timer limit in seconds
        """
        base = self.BASE_TIMER

        # Check for Master Planner research upgrades
        # Master Planner I and II each add 30 seconds
        bonus = 0

        # Check research progress for this player
        # Tech IDs are formatted as "tech_{col}_{row}" where Master Planner I is col=2, row=0
        # and Master Planner II is col=2, row=3
        if hasattr(self.gs, 'player_tech_researched'):
            player_research = self.gs.player_tech_researched.get(player_id, set())

            # Master Planner I (column 2, row 0)
            if 'tech_2_0' in player_research:
                bonus += self.MASTER_PLANNER_BONUS

            # Master Planner II (column 2, row 3)
            if 'tech_2_3' in player_research:
                bonus += self.MASTER_PLANNER_BONUS

        return base + bonus

    def start_planning_phase(self):
        """Start a new planning phase. Reset timers and ready states."""
        self.sim_phase = 'planning'

        # Reset ready flags
        for player_id in self.players_ready:
            self.players_ready[player_id] = False

        # Reset timers
        self._initialize_timers()
        # Use monotonic clock to avoid inaccuracies from NTP/DST adjustments
        self.timer_start_time = time.monotonic()

        # Record planning phase start for safety timeout
        # monotonic() is used so DST/NTP changes don't affect elapsed time calculations
        self.planning_phase_start_time = time.monotonic()

        # Clear previous round's data
        self.crossing_conflicts.clear()
        self.alliance_arrivals.clear()

        # Clear building limit tracking for new turn (allows one building per territory)
        self.gs.buildings_started_this_turn.clear()

        # Reset all unit statuses from 'moved' to 'unmoved' for the new round
        self._reset_unit_movement_status()

        # Check for auto-ready (players with no valid moves)
        self._check_auto_ready()

    def _reset_unit_movement_status(self):
        """Reset all units to unmoved status for the new planning phase."""
        for territory, garrison in self.gs.territory_garrisons.items():
            for player_id, player_garrison in garrison.items():
                # Convert moved armies back to unmoved
                moved = player_garrison.get('moved', 0)
                unmoved = player_garrison.get('unmoved', 0)
                player_garrison['unmoved'] = unmoved + moved
                player_garrison['moved'] = 0

                # Reset unit status from 'moved' to 'ready'
                units = player_garrison.get('units', [])
                for unit in units:
                    if unit.get('status') == 'moved':
                        unit['status'] = 'ready'

        # Legacy arrays are auto-synced via sync_legacy_garrison_data() in reset_garrison_moved_status()
        sim_log.detail("Reset all units to unmoved status for new round")

    def _check_auto_ready(self):
        """Auto-mark players as ready if they have no valid moves."""
        for player_id in range(self.gs.num_players):
            if player_id in self.eliminated_players:
                self.players_ready[player_id] = True
                sim_log.state(f"Player {player_id} auto-ready (eliminated)")
                continue

            # Check if player has any valid actions
            has_valid_action = self._player_has_valid_actions(player_id)
            sim_log.detail(f"Player {player_id} has_valid_action={has_valid_action}")

            if not has_valid_action:
                self.players_ready[player_id] = True
                sim_log.state(f"Player {player_id} auto-ready (no valid actions)")

    def _player_has_valid_actions(self, player_id: int) -> bool:
        """
        Check if a player has any valid actions available.

        Args:
            player_id: The player index

        Returns:
            True if player can take at least one action
        """
        # Check for owned territories with armies that can move
        # Get territories owned by this specific player
        player_territories = [t for t, owner in self.gs.territory_owners.items() if owner == player_id]
        for territory in player_territories:
            # Check if territory has unmoved armies
            garrison = self.gs.territory_garrisons.get(territory, {})
            player_garrison = garrison.get(player_id, {})
            unmoved = player_garrison.get('unmoved', 0)

            if unmoved > 0:
                # Check if there are adjacent territories to move to
                adjacent = map_data.get_neighbors(territory)
                if adjacent:
                    return True

        # Check if player has gold for any action
        gold = self.gs.player_gold[player_id]
        if gold > 0:
            # Could potentially build or train something
            return True

        return False

    def add_order(self, player_id: int, order: dict):
        """
        Add an order to a player's queue.

        Orders are NOT visible to other players and are NOT executed
        until all players are ready.

        Args:
            player_id: The player adding the order
            order: Order dictionary with type and parameters
        """
        if self.sim_phase != 'planning':
            return  # Can only add orders during planning phase

        if self.players_ready.get(player_id, False):
            return  # Can't add orders after marking ready

        self.player_orders[player_id].append(order)

    def remove_order(self, player_id: int, order_index: int):
        """
        Remove an order from a player's queue.

        Args:
            player_id: The player removing the order
            order_index: Index of order to remove
        """
        if self.sim_phase != 'planning':
            return

        if self.players_ready.get(player_id, False):
            return

        if 0 <= order_index < len(self.player_orders[player_id]):
            self.player_orders[player_id].pop(order_index)

    def clear_orders(self, player_id: int):
        """
        Clear all orders for a player.

        Args:
            player_id: The player whose orders to clear
        """
        if self.sim_phase != 'planning':
            return

        if self.players_ready.get(player_id, False):
            return

        self.player_orders[player_id].clear()

    def mark_ready(self, player_id: int):
        """
        Mark a player as ready (finished planning).

        Once ready, the player cannot modify their orders.
        When all players are ready, the execution phase begins.
        If called from a background thread (AI planning), execution is deferred
        to the main thread to prevent race conditions with current_player.

        Args:
            player_id: The player marking ready
        """
        sim_log.state(f"mark_ready called for player {player_id}, phase={self.sim_phase}")
        if self.sim_phase != 'planning':
            sim_log.state(f"Ignoring mark_ready - not in planning phase")
            return

        # Guard against duplicate calls - prevents triggering callbacks multiple times
        if self.players_ready.get(player_id, False):
            sim_log.state(f"Ignoring mark_ready - player {player_id} already ready")
            return

        self.players_ready[player_id] = True
        sim_log.ready(player_id, self.players_ready)

        # Check if all players are now ready
        if self.all_players_ready():
            # In multiplayer, only the HOST triggers execution
            # Client waits for SIM_ALL_READY message from host
            if self.is_multiplayer_client:
                sim_log.sync("All players ready (client) - waiting for SIM_ALL_READY from host")
            elif self.is_multiplayer_host and self.on_all_ready_callback:
                # Multiplayer HOST: use callback to send SIM_ALL_READY and execute
                sim_log.sync("All players ready (host) - triggering broadcast callback")
                self.on_all_ready_callback()
            else:
                # Single-player or local game: check if we're on the main thread
                # If called from AI background thread, defer execution to main thread
                # to prevent race conditions (complete_round modifies current_player)
                if threading.current_thread() is not threading.main_thread():
                    sim_log.phase("All players ready (from background thread) - deferring execution to main thread")
                    self._execution_pending = True
                else:
                    sim_log.phase("All players ready, beginning execution (single-player)")
                    self._begin_execution()

    def all_players_ready(self) -> bool:
        """Check if all players are ready to execute."""
        return all(self.players_ready.values())

    def get_waiting_players(self) -> List[int]:
        """Get list of player IDs who are not yet ready."""
        return [
            player_id for player_id, ready in self.players_ready.items()
            if not ready
        ]

    def get_waiting_player_names(self) -> List[str]:
        """Get list of player names who are not yet ready."""
        waiting = self.get_waiting_players()
        names = []

        for player_id in waiting:
            name = self.gs.player_names[player_id]
            if name:
                names.append(name)
            else:
                names.append(f"Player {player_id + 1}")

        return names

    def update_timers(self, dt: float):
        """
        Update player timers and check for expiration.

        Args:
            dt: Delta time in seconds since last update
        """
        if self.sim_phase != 'planning':
            return

        # Safety timeout: force-mark all unresponsive players as ready after 120s
        # This prevents indefinite stalling if a player disconnects or becomes unresponsive
        if self.planning_phase_start_time is not None:
            # Use monotonic() to avoid NTP/DST skew in elapsed time calculation
            elapsed = time.monotonic() - self.planning_phase_start_time
            if elapsed >= self.READY_SAFETY_TIMEOUT:
                waiting = self.get_waiting_players()
                if waiting:
                    sim_log.state(
                        f"Safety timeout ({self.READY_SAFETY_TIMEOUT}s) reached, "
                        f"force-marking {len(waiting)} unresponsive players as ready: {waiting}"
                    )
                    for pid in waiting:
                        # Skip remote human players — they send their own SIM_PLAYER_READY via network
                        # Force-marking them here would mark them ready with empty orders
                        if self.is_multiplayer_host and pid != 0 and not self.gs.player_is_ai[pid]:
                            sim_log.state(f"Safety timeout: skipping remote human player {pid}")
                            continue
                        self.player_timers[pid] = 0
                        self.mark_ready(pid)
                    return  # mark_ready will trigger execution, skip per-player updates

        for player_id in range(self.gs.num_players):
            if self.players_ready.get(player_id, False):
                continue  # Already ready, don't update timer

            self.player_timers[player_id] -= dt

            # Check for timer expiration
            if self.player_timers[player_id] <= 0:
                self.player_timers[player_id] = 0
                # Don't auto-ready remote human players — they send SIM_PLAYER_READY via network
                # Auto-readying them here would mark them ready with empty orders
                if self.is_multiplayer_host and player_id != 0 and not self.gs.player_is_ai[player_id]:
                    sim_log.state(f"Timer expired for remote player {player_id} - awaiting network ready")
                    continue
                self.mark_ready(player_id)  # Auto-ready when timer expires

    def get_remaining_time(self, player_id: int) -> float:
        """
        Get remaining planning time for a player.

        Args:
            player_id: The player index

        Returns:
            Remaining time in seconds
        """
        return max(0, self.player_timers.get(player_id, 0))

    def check_deferred_execution(self):
        """Check if execution was deferred from AI thread and run it on main thread.

        Called from the main game loop to safely trigger execution that was
        deferred when mark_ready() was called from an AI background thread.
        """
        if self._execution_pending:
            self._execution_pending = False
            sim_log.phase("Processing deferred execution on main thread")
            self._begin_execution()

    def _begin_execution(self):
        """Begin the execution phase - merge and execute all orders."""
        self.sim_phase = 'executing'

        # Phase manager will handle the actual execution
        if self.phase_manager:
            self.phase_manager.begin_execution(self.player_orders)

    def advance_to_resolution(self):
        """Move from execution to resolution phase."""
        self.sim_phase = 'resolving'

    def complete_round(self):
        """
        Complete the current round and start a new planning phase.

        This is called after all battles are resolved.
        """
        # Don't advance to next round if game has ended (victory/defeat detected)
        if self.gs.phase == 'ended':
            return

        # Apply income and finish constructions/research for all players
        # Note: finish_constructions, finish_research use gs.current_player internally,
        # so we temporarily set it for each player
        # IMPORTANT: finish_training is called AFTER start_planning_phase to ensure
        # newly trained units keep their 'moved' status (can't move on turn they spawn)
        # M8 fix: use try/finally to restore current_player on exception
        original_player = self.gs.current_player
        try:
            for player_id in range(self.gs.num_players):
                if player_id not in self.eliminated_players:
                    self.gs.collect_income(player_id)
                    # Temporarily set current_player for methods that depend on it
                    self.gs.current_player = player_id
                    self.gs.last_completed_buildings = self.gs.finish_constructions()
                    self.gs.finish_research()
                    self.gs.finish_castle_upgrades()
                    # Award XP to Farms/Mines (veterancy system)
                    self.gs._tick_building_xp()
                    # Award XP to units in territories with Training Grounds
                    self.gs._tick_training_grounds_xp()
        finally:
            # Restore original current_player
            self.gs.current_player = original_player

        # Decrement cooldowns
        if hasattr(self.gs, '_decrement_hero_cooldowns_and_silence'):
            self.gs._decrement_hero_cooldowns_and_silence()

        # Handle overflow territories
        self._process_overflow_territories()

        # Clear orders for next round
        for player_id in self.player_orders:
            self.player_orders[player_id].clear()

        # Increment round
        self.round_number += 1
        # Sync turn_number with round_number for game logger consistency
        self.gs.turn_number = self.round_number
        set_round(self.round_number)  # Update debug context
        sim_log.phase(f"Round complete. Starting round {self.round_number}")

        # Game logger: record round snapshot for the completed round
        if self.gs.game_logger:
            self.gs.game_logger.record_round_snapshot(self.round_number)

        # Replay recorder: snapshot at end of each simultaneous round
        if self.gs.replay_recorder:
            self.gs.replay_recorder.record_snapshot()

        # Start new planning phase (resets all 'moved' units to 'ready')
        self.start_planning_phase()

        # NOW finish training for all players - units spawn with 'moved' status
        # and won't be reset since start_planning_phase already ran
        # Also finish hero training (decrement timers and complete heroes)
        # M8 fix: use try/finally to restore current_player on exception
        original_player = self.gs.current_player
        try:
            for player_id in range(self.gs.num_players):
                if player_id not in self.eliminated_players:
                    self.gs.current_player = player_id
                    self.gs.finish_training()
                    # Hero training completion - decrements timer and completes hero when ready
                    if hasattr(self.gs, 'finish_hero_training'):
                        self.gs.finish_hero_training()
        finally:
            self.gs.current_player = original_player

        # Callback for multiplayer host to broadcast round completion
        if self.is_multiplayer_host and self.on_round_complete_callback:
            self.on_round_complete_callback(self.round_number)

    def _process_overflow_territories(self):
        """Disband excess armies in overflow territories that expired."""
        territories_to_remove = []

        for territory, expiry_round in self.overflow_territories.items():
            if self.round_number >= expiry_round:
                # Disband excess armies
                self._disband_excess_armies(territory)
                territories_to_remove.append(territory)

        for territory in territories_to_remove:
            del self.overflow_territories[territory]

    def _disband_excess_armies(self, territory: str):
        """
        Disband armies exceeding the limit in a territory.

        Args:
            territory: Territory name
        """
        max_armies = self.gs.MAX_ARMIES_PER_TERRITORY

        # Count total armies
        total = 0
        garrison = self.gs.territory_garrisons.get(territory, {})
        for player_garrison in garrison.values():
            total += player_garrison.get('unmoved', 0)
            total += player_garrison.get('moved', 0)

        if total <= max_armies:
            return  # No overflow

        excess = total - max_armies

        # Remove excess armies, starting from non-owner garrisons
        owner = self.gs.territory_owners.get(territory, -1)

        # First remove from allied (non-owner) garrisons
        for player_id, player_garrison in garrison.items():
            if player_id == owner:
                continue  # Skip owner for now

            unmoved = player_garrison.get('unmoved', 0)
            moved = player_garrison.get('moved', 0)
            player_total = unmoved + moved

            to_remove = min(player_total, excess)
            if to_remove > 0:
                # Remove from moved first, then unmoved
                from_moved = min(moved, to_remove)
                player_garrison['moved'] -= from_moved
                to_remove -= from_moved

                from_unmoved = min(unmoved, to_remove)
                player_garrison['unmoved'] -= from_unmoved

                # M5 fix: also remove units from the units list to stay in sync
                total_removed = from_moved + from_unmoved
                units = player_garrison.get('units', [])
                if units and total_removed > 0:
                    for _ in range(min(total_removed, len(units))):
                        units.pop()

                excess -= total_removed

                if excess <= 0:
                    break

        # If still excess, remove from owner
        if excess > 0 and owner >= 0 and owner in garrison:
            owner_garrison = garrison[owner]
            unmoved = owner_garrison.get('unmoved', 0)
            moved = owner_garrison.get('moved', 0)

            to_remove = min(unmoved + moved, excess)
            from_moved = min(moved, to_remove)
            owner_garrison['moved'] -= from_moved
            to_remove -= from_moved

            from_unmoved = min(unmoved, to_remove)
            owner_garrison['unmoved'] -= from_unmoved

            # M5 fix: also remove units from the units list
            total_removed = from_moved + from_unmoved
            units = owner_garrison.get('units', [])
            if units and total_removed > 0:
                for _ in range(min(total_removed, len(units))):
                    units.pop()

    def mark_overflow_territory(self, territory: str):
        """
        Mark a territory as having overflow armies.

        Args:
            territory: Territory name
        """
        # Overflow expires at end of NEXT round
        self.overflow_territories[territory] = self.round_number + 2

    def is_overflow_territory(self, territory: str) -> bool:
        """Check if a territory has overflow armies."""
        return territory in self.overflow_territories

    # ========== Ally Visibility (Multiplayer Alliance Support) ==========

    def are_allies(self, player1: int, player2: int) -> bool:
        """
        Check if two players are on the same team (allies).

        Args:
            player1: First player index
            player2: Second player index

        Returns:
            True if players are on the same team
        """
        if player1 == player2:
            return True  # Player is always allied with themselves

        # Check if game_state has player_teams
        # C1 fix: player_teams is a list, not dict — use index access with bounds check
        if hasattr(self.gs, 'player_teams') and self.gs.player_teams:
            if player1 < len(self.gs.player_teams) and player2 < len(self.gs.player_teams):
                team1 = self.gs.player_teams[player1]
                team2 = self.gs.player_teams[player2]
                return team1 == team2

        # Fallback: No alliance system, players are not allies
        return False

    def get_visible_orders_for_player(self, player_id: int) -> List[dict]:
        """
        Get orders visible to a player during planning phase.

        In simultaneous mode, players can see their own orders and
        their allies' orders (if alliance system is enabled).

        Args:
            player_id: The viewing player's index

        Returns:
            List of order dicts with 'is_ally' flag added
        """
        visible_orders = []

        for other_player, orders in self.player_orders.items():
            if other_player == player_id:
                # Own orders - always visible
                for order in orders:
                    order_copy = order.copy()
                    order_copy['owner_player'] = player_id
                    order_copy['is_ally'] = False
                    order_copy['is_own'] = True
                    visible_orders.append(order_copy)
            elif self.are_allies(player_id, other_player):
                # Allied player's orders - visible with ally flag
                for order in orders:
                    order_copy = order.copy()
                    order_copy['owner_player'] = other_player
                    order_copy['is_ally'] = True
                    order_copy['is_own'] = False
                    visible_orders.append(order_copy)
            # Enemy orders are not visible

        return visible_orders

    def get_allied_players(self, player_id: int) -> List[int]:
        """
        Get list of allied player indices for a given player.

        Args:
            player_id: The player to find allies for

        Returns:
            List of allied player indices (not including self)
        """
        allies = []
        for other_id in range(self.gs.num_players):
            if other_id != player_id and self.are_allies(player_id, other_id):
                allies.append(other_id)
        return allies

    def get_ally_markers(self, player_id: int) -> List[dict]:
        """
        Get movement markers from allied players for visual display.

        Returns simplified marker info for rendering (from/to territories,
        not full order details).

        Args:
            player_id: The viewing player's index

        Returns:
            List of marker dicts with 'from_territory', 'to_territory', 'ally_player'
        """
        markers = []

        for ally_id in self.get_allied_players(player_id):
            for order in self.player_orders.get(ally_id, []):
                if order.get('type') == 'movement':
                    markers.append({
                        'from_territory': order.get('from_territory'),
                        'to_territory': order.get('to_territory'),
                        'ally_player': ally_id,
                        'army_count': order.get('army_count', 0)
                    })

        return markers

    def eliminate_player(self, player_id: int):
        """
        Mark a player as eliminated.

        Args:
            player_id: The eliminated player
        """
        if player_id not in self.eliminated_players:
            self.eliminated_players.append(player_id)
            self.players_ready[player_id] = True  # No longer participates

    # Delegate common GameState methods
    def __getattr__(self, name):
        """Delegate attribute access to underlying GameState."""
        return getattr(self.gs, name)
