# -*- coding: utf-8 -*-
# simultaneous/sim_ai.py
# AI Adapter for Simultaneous Turn Mode

"""
SimultaneousAI - AI Adapter for Simultaneous Mode
==================================================

Handles AI decision-making for simultaneous turn mode.
The AI plans all moves during the planning phase, then
marks itself as ready.

Key differences from sequential AI:
    - No explicit turn ending (marks ready instead)
    - Simulated delay to feel natural
    - Plans without seeing other players' orders
    - Actions are queued as orders instead of executed immediately
"""

import random
import time
import threading
from typing import Optional

from ai_player import AIPlayer
from utils.logger import get_logger
from .sim_debug import sim_log

logger = get_logger(__name__)


class SimultaneousAI:
    """
    AI adapter for simultaneous turn mode.

    AI players plan during the planning phase like human players,
    with a simulated delay to feel natural. Uses the existing AIPlayer
    class for decision-making but queues orders instead of executing.
    """

    # Difficulty-based thinking delays (seconds) - reduced for faster gameplay
    THINKING_DELAY = {
        0: (1.5, 3.0),   # Easy: 1.5-3 seconds
        1: (1.0, 2.0),   # Medium: 1-2 seconds
        2: (0.5, 1.0)    # Hard: 0.5-1 seconds
    }

    # Safety timeout for AI planning (seconds)
    # If AI decision-making takes longer than this, use whatever orders
    # have been generated so far and mark the AI as ready
    AI_PLANNING_TIMEOUT = 30

    def __init__(self, sim_state, ai_player_module):
        """
        Initialize the simultaneous AI adapter.

        Args:
            sim_state: The SimultaneousGameState instance
            ai_player_module: Reference to the ai_player module for decision logic
        """
        self.sim_state = sim_state
        self.gs = sim_state.gs

        # Create AIPlayer instances for each AI player
        # These are used for their planning logic, not execution
        self.ai_players = {}
        for player_id in range(self.gs.num_players):
            if self.gs.player_is_ai[player_id]:
                difficulty = self.gs.player_ai_difficulty[player_id]
                self.ai_players[player_id] = AIPlayer(player_id, difficulty)
                sim_log.ai(player_id, f"Created AIPlayer (difficulty {difficulty})")

        # Track which AI players are currently planning
        self.ai_planning = {}  # {player_id: threading.Thread}

        # Planning complete flags
        self.ai_ready = {}  # {player_id: bool}

        sim_log.detail(f"SimultaneousAI initialized for {self.gs.num_players} players")

    def start_planning_phase(self):
        """
        Called when a new planning phase starts.

        Initiates AI planning for all AI players.
        """
        sim_log.phase("Starting planning phase for AI players")
        for player_id in range(self.gs.num_players):
            if self.gs.player_is_ai[player_id]:
                self.ai_ready[player_id] = False
                self._start_ai_planning(player_id)
                sim_log.ai(player_id, "Started planning thread")

    def _start_ai_planning(self, player_id: int):
        """
        Start AI planning in a background thread with simulated delay.

        Args:
            player_id: The AI player index
        """
        if player_id in self.ai_planning and self.ai_planning[player_id].is_alive():
            sim_log.ai(player_id, "Already planning, skipping")
            return  # Already planning

        thread = threading.Thread(
            target=self._ai_planning_thread,
            args=(player_id,),
            daemon=True
        )
        self.ai_planning[player_id] = thread
        thread.start()
        sim_log.ai(player_id, "Planning thread started")

    def _ai_planning_thread(self, player_id: int):
        """
        AI planning thread with simulated delay and safety timeout.

        If AI decision-making exceeds AI_PLANNING_TIMEOUT seconds, the thread
        uses whatever orders have been generated so far and marks the AI ready.

        Args:
            player_id: The AI player index
        """
        try:
            # Get difficulty-based delay
            difficulty = self.gs.player_ai_difficulty[player_id]
            min_delay, max_delay = self.THINKING_DELAY.get(difficulty, (1.0, 2.0))
            think_time = random.uniform(min_delay, max_delay)

            sim_log.ai(player_id, f"Thinking for {think_time:.1f}s (difficulty {difficulty})")

            # Simulate thinking time
            time.sleep(think_time)

            # Make decisions using existing AI logic with a safety timeout.
            # Run _make_ai_decisions in a sub-thread so we can join with a timeout.
            # If it takes longer than AI_PLANNING_TIMEOUT, we proceed with
            # whatever orders have been queued so far.
            decision_thread = threading.Thread(
                target=self._make_ai_decisions,
                args=(player_id,),
                daemon=True
            )
            decision_thread.start()
            decision_thread.join(timeout=self.AI_PLANNING_TIMEOUT)

            if decision_thread.is_alive():
                # AI planning exceeded timeout - proceed with partial orders
                sim_log.error(
                    f"AI player {player_id} planning timed out after "
                    f"{self.AI_PLANNING_TIMEOUT}s, using partial orders"
                )
                logger.warning(
                    f"AI player {player_id} planning timed out after "
                    f"{self.AI_PLANNING_TIMEOUT}s, proceeding with partial orders"
                )
                # Note: the sub-thread will continue in the background as a daemon
                # thread, but we don't wait for it - we mark ready now

            # Mark AI as ready
            sim_log.ai(player_id, "Marking ready")
            self.ai_ready[player_id] = True
            self.sim_state.mark_ready(player_id)
            sim_log.ai(player_id, "Now ready")

        except Exception as e:
            # Log AI planning error with full traceback
            sim_log.error(f"Error in AI planning for player {player_id}: {e}")
            logger.error(f"Error in AI planning for player {player_id}: {e}", exc_info=True)
            # Mark ready anyway to prevent blocking
            self.ai_ready[player_id] = True
            self.sim_state.mark_ready(player_id)

    def _make_ai_decisions(self, player_id: int):
        """
        Make AI decisions for movement, building, and training.

        Uses the existing AIPlayer planning logic but queues orders
        instead of executing them immediately.

        IMPORTANT: The AIPlayer's planning logic was designed for sequential mode
        where actions are executed immediately. In simultaneous mode, multiple
        move planners (defensive, reinforcement, attacks) may try to move the
        same armies. We validate and cap movement orders to available armies.

        Args:
            player_id: The AI player index
        """
        sim_log.ai(player_id, "Making decisions")

        # Reset unit selection tracking for this planning session
        # This prevents selecting the same unit for multiple movement orders
        self._selected_unit_ids = {}  # {territory: set of unit IDs already selected}

        if player_id not in self.ai_players:
            sim_log.error(f"No AIPlayer instance for player {player_id}")
            return

        ai_player = self.ai_players[player_id]

        try:
            # Use AIPlayer's planning method to get actions
            ai_player.actions_taken = []
            ai_player._plan_turn_actions(self.gs)

            sim_log.ai(player_id, f"Planned {len(ai_player.actions_taken)} actions (before validation)")

            # Validate and fix movement orders to prevent over-allocation
            # Track armies committed from each territory
            committed_armies = {}  # {territory: count}
            validated_actions = []

            for action_type, action_data in ai_player.actions_taken:
                if action_type == 'move':
                    from_terr = action_data['from']
                    requested_count = action_data.get('army_count', 1)

                    # Get available armies in this territory for this player
                    garrison = self.gs.territory_garrisons.get(from_terr, {})
                    player_garrison = garrison.get(player_id, {})
                    total_available = player_garrison.get('unmoved', 0)

                    # Subtract already committed armies
                    already_committed = committed_armies.get(from_terr, 0)
                    remaining_available = total_available - already_committed

                    if remaining_available <= 0:
                        # No armies left to move from this territory
                        sim_log.ai(player_id, f"SKIPPING move from {from_terr}: no armies remaining")
                        continue

                    # Cap the requested count to what's actually available
                    actual_count = min(requested_count, remaining_available)

                    if actual_count != requested_count:
                        sim_log.ai(player_id, f"CAPPED move from {from_terr}: {requested_count} -> {actual_count}")

                    # Update committed count
                    committed_armies[from_terr] = already_committed + actual_count

                    # Create validated action with corrected count
                    validated_action_data = action_data.copy()
                    validated_action_data['army_count'] = actual_count
                    validated_actions.append((action_type, validated_action_data))
                else:
                    # Non-movement actions pass through unchanged
                    validated_actions.append((action_type, action_data))

            sim_log.ai(player_id, f"Validated {len(validated_actions)} actions")

            # Convert validated actions to orders and queue them
            for action_type, action_data in validated_actions:
                self._queue_action_as_order(player_id, action_type, action_data)

        except Exception as e:
            # Log AI decision-making error with full traceback
            sim_log.error(f"Error planning for AI player {player_id}: {e}")
            logger.error(f"Error planning for AI player {player_id}: {e}", exc_info=True)

    def _queue_action_as_order(self, player_id: int, action_type: str, action_data: dict):
        """
        Convert an AI action to an order and queue it.

        Args:
            player_id: The AI player index
            action_type: Type of action ('build', 'train', 'move', etc.)
            action_data: Action-specific parameters
        """
        order = None

        if action_type == 'build':
            order = {
                'type': 'build',
                'player_id': player_id,
                'territory': action_data['territory'],
                'building_type': action_data['building'],
                'plot_index': action_data['plot']
            }
            sim_log.ai(player_id, f"Queuing build: {action_data['building']} in {action_data['territory']}")

        elif action_type == 'train':
            order = {
                'type': 'train',
                'player_id': player_id,
                'territory': action_data['territory'],
                'unit_type': action_data['unit_type'],
                'barracks_plot': action_data['barracks_plot']
            }
            sim_log.ai(player_id, f"Queuing train: {action_data['unit_type']} in {action_data['territory']}")

        elif action_type == 'move':
            army_count = action_data.get('army_count', 1)
            from_territory = action_data['from']

            # Get specific unit IDs to move (preserves unit composition)
            # This ensures AI units don't all become Swordsmen
            unit_ids = []
            garrison = self.gs.territory_garrisons.get(from_territory, {})
            player_garrison = garrison.get(player_id, {})
            units = player_garrison.get('units', [])

            # Get set of already-selected unit IDs for this territory
            # (prevents selecting same unit for multiple movements in one planning session)
            if not hasattr(self, '_selected_unit_ids'):
                self._selected_unit_ids = {}
            already_selected = self._selected_unit_ids.get(from_territory, set())

            # Select units that are ready to move AND not already selected for another order
            units_selected = 0
            for unit in units:
                if units_selected >= army_count:
                    break
                unit_id = unit.get('id')
                if unit.get('status') == 'ready' and unit_id not in already_selected:
                    unit_ids.append(unit_id)
                    units_selected += 1

            # Track the newly selected units so they won't be selected again
            if from_territory not in self._selected_unit_ids:
                self._selected_unit_ids[from_territory] = set()
            self._selected_unit_ids[from_territory].update(unit_ids)

            order = {
                'type': 'movement',
                'player_id': player_id,
                'from_territory': from_territory,
                'to_territory': action_data['to'],
                'army_count': army_count,
                'unit_ids': unit_ids  # Include specific units to preserve composition
            }
            sim_log.ai(player_id, f"Queuing move: {from_territory} -> {action_data['to']} ({army_count} armies)")

        elif action_type == 'research':
            order = {
                'type': 'research',
                'player_id': player_id,
                'tech_id': action_data['tech_id']
            }
            sim_log.ai(player_id, f"Queuing research: {action_data['tech_id']}")

        elif action_type == 'upgrade_castle':
            order = {
                'type': 'upgrade_castle',
                'player_id': player_id,
                'territory': action_data['territory'],
                'plot_index': action_data['plot']
            }
            sim_log.ai(player_id, f"Queuing castle upgrade in {action_data['territory']}")

        elif action_type == 'demolish':
            order = {
                'type': 'demolish',
                'player_id': player_id,
                'territory': action_data['territory'],
                'plot_index': action_data['plot']
            }
            sim_log.ai(player_id, f"Queuing demolish in {action_data['territory']}")

        elif action_type == 'hero_ability':
            # AI uses hero_type/ability_name from ai_hero.py
            order = {
                'type': 'hero_ability',
                'player_id': player_id,
                'hero_type': action_data.get('hero_type'),  # Hero name (e.g., 'Brennhen')
                'ability_name': action_data.get('ability_name'),  # Ability name (e.g., 'Reinforce')
                'target': action_data.get('target')  # Target territory or None
            }
            sim_log.ai(player_id, f"Queuing hero ability: {action_data.get('hero_type')} - {action_data.get('ability_name')}")

        elif action_type == 'train_hero':
            # AI provides territory and keep_plot from ai_hero.py
            order = {
                'type': 'train_hero',
                'player_id': player_id,
                'hero_type': action_data.get('hero_type'),
                'territory': action_data.get('territory'),  # Territory with the Keep
                'keep_plot': action_data.get('keep_plot')   # Keep's plot index
            }
            sim_log.ai(player_id, f"Queuing hero training: {action_data.get('hero_type')} in {action_data.get('territory')}")

        else:
            sim_log.error(f"Unknown AI action type: {action_type}")
            return

        if order:
            self.sim_state.add_order(player_id, order)

    def is_all_ai_ready(self) -> bool:
        """Check if all AI players have finished planning."""
        for player_id in range(self.gs.num_players):
            if self.gs.player_is_ai[player_id]:
                if not self.ai_ready.get(player_id, False):
                    return False
        return True

    def cancel_planning(self):
        """Cancel all AI planning (e.g., when game ends)."""
        # Threads are daemon threads, so they'll stop when main thread ends
        self.ai_planning.clear()
        self.ai_ready.clear()
