# -*- coding: utf-8 -*-
# simultaneous/sim_phase_manager.py
# Phase Manager for Simultaneous Turn Mode

"""
SimPhaseManager - Manages Phase Transitions in Simultaneous Mode
================================================================

Handles the planning -> execution -> resolution -> planning cycle
for simultaneous turn gameplay.
"""

from typing import Dict, List, Optional, Any
import random
import traceback

import map_data
from game_state import ArmyAnimation, Battle
from utils.logger import get_logger
from .sim_conflict_resolver import SimConflictResolver
from .sim_alliance_handler import SimAllianceHandler
from .sim_debug import sim_log

logger = get_logger(__name__)


class SimPhaseManager:
    """
    Manages phase transitions and execution flow for simultaneous mode.

    Phases:
        1. Planning: All players queue orders (hidden from each other)
        2. Execution: Orders merge and execute with animations
        3. Resolution: Battles and conflicts resolved
        4. Return to Planning for next round
    """

    def __init__(self, sim_state):
        """
        Initialize the phase manager.

        Args:
            sim_state: The SimultaneousGameState instance
        """
        self.sim_state = sim_state
        self.gs = sim_state.gs  # Underlying GameState

        # Conflict resolver for crossing armies and multi-battles
        self.conflict_resolver = SimConflictResolver(sim_state)

        # Alliance handler for allied territory capture
        self.alliance_handler = SimAllianceHandler(sim_state)

        # Pending battles to resolve
        self.pending_battles: List[dict] = []

        # Pending alliance markers to resolve
        self.pending_alliance_markers: List[dict] = []

        # Current battle being resolved (for UI)
        self.current_battle: Optional[dict] = None

        # Player who resolves current battle
        self.battle_resolver_player: Optional[int] = None

        # Execution state
        self.execution_complete = False
        self.animations_complete = False

    def begin_execution(self, player_orders: Dict[int, List[dict]]):
        """
        Begin the execution phase with all player orders.

        Args:
            player_orders: Dictionary of {player_id: [orders]}
        """
        self.sim_state.sim_phase = 'executing'
        self.execution_complete = False
        self.animations_complete = False

        # Step 1: Detect and resolve crossing army conflicts
        crossing_conflicts = self.conflict_resolver.detect_crossing_conflicts(player_orders)
        resolved_orders = self.conflict_resolver.resolve_crossing_conflicts(
            player_orders, crossing_conflicts
        )

        # Continue with resolved orders
        self._execute_resolved_orders(resolved_orders)

    def begin_execution_with_resolved(self, resolved_orders: Dict[int, List[dict]]):
        """
        Begin the execution phase with already-resolved orders.

        Used by multiplayer host when conflict detection was done before
        sending SIM_ALL_READY to clients. Skips conflict detection to avoid
        duplicate processing.

        Args:
            resolved_orders: Dictionary of {player_id: [orders]} after conflict resolution
        """
        self.sim_state.sim_phase = 'executing'
        self.execution_complete = False
        self.animations_complete = False

        # Skip conflict detection - already done before sending to clients
        self._execute_resolved_orders(resolved_orders)

    def _execute_resolved_orders(self, resolved_orders: Dict[int, List[dict]]):
        """
        Execute orders after conflict resolution.

        Args:
            resolved_orders: Dictionary of {player_id: [orders]} after conflict resolution
        """
        # Step 2: Merge all orders into unified execution queue
        merged_orders = self._merge_orders(resolved_orders)
        sim_log.phase(f"Merged {len(merged_orders)} orders from all players")

        # Step 3: Validate orders (check army limits, etc.)
        valid_orders = self._validate_orders(merged_orders)
        sim_log.phase(f"{len(valid_orders)} valid orders after validation")
        for order in valid_orders:
            sim_log.order(order.get('player_id'), order.get('type'), str(order))

        # Step 4: Execute orders (creates animations)
        self._execute_orders(valid_orders)

    def _merge_orders(self, player_orders: Dict[int, List[dict]]) -> List[dict]:
        """
        Merge orders from all players into a single list with deduplication.

        Duplicate movement orders (same player, source, and target) are removed
        to prevent double army movement from redundant order submissions.

        Args:
            player_orders: Dictionary of {player_id: [orders]}

        Returns:
            Combined list of all orders with player attribution (no duplicates)
        """
        merged = []
        # Track seen movement orders to prevent duplicates
        # Key: (player_id, source_territory, target_territory)
        seen_movement_orders = set()

        for player_id, orders in player_orders.items():
            for order in orders:
                # Add player_id to order if not present
                order_copy = order.copy()
                order_copy['player_id'] = player_id

                # Deduplicate movement orders by (player, source, target)
                if order_copy.get('type') == 'movement':
                    dedup_key = (
                        player_id,
                        order_copy.get('from_territory'),
                        order_copy.get('to_territory')
                    )
                    if dedup_key in seen_movement_orders:
                        sim_log.detail(
                            f"Skipping duplicate movement order: P{player_id} "
                            f"{order_copy.get('from_territory')} -> {order_copy.get('to_territory')}"
                        )
                        continue
                    seen_movement_orders.add(dedup_key)

                merged.append(order_copy)

        return merged

    def _validate_orders(self, orders: List[dict]) -> List[dict]:
        """
        Validate orders and remove invalid ones.

        Args:
            orders: List of order dictionaries

        Returns:
            List of valid orders
        """
        valid = []

        for order in orders:
            if self._is_order_valid(order):
                valid.append(order)

        return valid

    def _is_order_valid(self, order: dict) -> bool:
        """
        Check if an order is valid.

        Args:
            order: Order dictionary

        Returns:
            True if order is valid
        """
        order_type = order.get('type')

        if order_type == 'movement':
            return self._validate_movement_order(order)
        elif order_type == 'build':
            return self._validate_build_order(order)
        elif order_type == 'train':
            return self._validate_train_order(order)
        elif order_type == 'train_hero':
            # Hero training validation: check that required fields exist
            # Actual validation (gold, hero limits) happens in game_state.start_hero_training
            return (order.get('territory') is not None and
                    order.get('hero_type') is not None and
                    (order.get('keep_plot') is not None or order.get('keep_plot_index') is not None))
        elif order_type in ('research', 'upgrade_castle', 'demolish', 'hero_ability'):
            # These order types are validated during execution
            return True

        return False

    def _validate_movement_order(self, order: dict) -> bool:
        """Validate a movement order."""
        from_territory = order.get('from_territory')
        to_territory = order.get('to_territory')
        player_id = order.get('player_id')
        army_count = order.get('army_count', 0)

        # Check territories exist
        if not from_territory or not to_territory:
            return False

        # Check adjacency (or Captain 2-hop through allied territory)
        adjacent = map_data.get_neighbors(from_territory)
        if to_territory not in adjacent:
            # Check for Captain extended movement
            if self.gs.army_has_captain(from_territory, player_id):
                intermediate = self.gs.find_2hop_path(from_territory, to_territory, player_id)
                if intermediate is None:
                    return False
                # Valid 2-hop path — continue validation
            else:
                return False

        # In multiplayer mode, skip garrison validation for remote player orders
        # Remote orders were already validated on the sender's side before sending
        # Host doesn't have accurate garrison data for remote players (training not synced)
        local_player = self.sim_state.local_player_index
        is_remote_order = local_player is not None and player_id != local_player

        if not is_remote_order:
            # Only validate garrison for local player orders
            # Check player owns/has garrison in from_territory
            garrison = self.gs.territory_garrisons.get(from_territory, {})
            player_garrison = garrison.get(player_id, {})
            unmoved = player_garrison.get('unmoved', 0)

            if army_count > unmoved:
                sim_log.detail(f"Movement validation failed: P{player_id} has {unmoved} unmoved, wants {army_count}")
                return False
        else:
            sim_log.detail(f"Skipping garrison validation for remote player {player_id} order")

        # Check destination army limit
        dest_garrison = self.gs.territory_garrisons.get(to_territory, {})
        dest_total = sum(
            g.get('unmoved', 0) + g.get('moved', 0)
            for g in dest_garrison.values()
        )

        # Allow movement even if it would exceed limit temporarily
        # (will be marked as overflow)
        # But don't allow moving TO a territory that's already at 2x limit
        if dest_total >= self.gs.MAX_ARMIES_PER_TERRITORY * 2:
            return False

        return True

    def _validate_build_order(self, order: dict) -> bool:
        """Validate a build order."""
        territory = order.get('territory')
        player_id = order.get('player_id')
        building_type = order.get('building_type')
        plot_index = order.get('plot_index')

        # Check player owns territory
        if self.gs.territory_owners.get(territory) != player_id:
            return False

        # Check player has gold
        cost = self.gs.building_types.get(building_type, {}).get('cost', 0)
        if self.gs.player_gold[player_id] < cost:
            return False

        # Check plot is empty
        buildings = self.gs.buildings.get(territory, {})
        if plot_index in buildings and buildings[plot_index]:
            return False

        return True

    def _validate_train_order(self, order: dict) -> bool:
        """Validate a train order."""
        territory = order.get('territory')
        player_id = order.get('player_id')
        unit_type = order.get('unit_type')

        # Check player owns territory
        if self.gs.territory_owners.get(territory) != player_id:
            return False

        # Check player has gold
        cost = self.gs.UNIT_TYPES.get(unit_type, {}).get('cost', 0)
        if self.gs.player_gold[player_id] < cost:
            return False

        # Check territory has barracks
        has_barracks = False
        buildings = self.gs.buildings.get(territory, {})
        for building in buildings.values():
            if building == 'Barracks':
                has_barracks = True
                break

        return has_barracks

    def _execute_orders(self, orders: List[dict]):
        """
        Execute all validated orders.

        This creates animations for movements and applies
        build/train orders immediately.

        Args:
            orders: List of valid order dictionaries
        """
        # Separate by type
        movement_orders = [o for o in orders if o.get('type') == 'movement']
        build_orders = [o for o in orders if o.get('type') == 'build']
        train_orders = [o for o in orders if o.get('type') == 'train']
        research_orders = [o for o in orders if o.get('type') == 'research']
        upgrade_castle_orders = [o for o in orders if o.get('type') == 'upgrade_castle']
        demolish_orders = [o for o in orders if o.get('type') == 'demolish']
        hero_ability_orders = [o for o in orders if o.get('type') == 'hero_ability']
        train_hero_orders = [o for o in orders if o.get('type') == 'train_hero']

        # Apply demolish orders first (frees up plots for builds)
        for order in demolish_orders:
            self._apply_demolish_order(order)

        # Apply build orders
        for order in build_orders:
            self._apply_build_order(order)

        # Apply upgrade castle orders
        for order in upgrade_castle_orders:
            self._apply_upgrade_castle_order(order)

        # Apply train orders
        for order in train_orders:
            self._apply_train_order(order)

        # Apply research orders
        for order in research_orders:
            self._apply_research_order(order)

        # Apply hero ability orders
        for order in hero_ability_orders:
            self._apply_hero_ability_order(order)

        # Apply train hero orders
        for order in train_hero_orders:
            self._apply_train_hero_order(order)

        # Execute movement orders (creates animations)
        self._execute_movement_orders(movement_orders)

    def _apply_build_order(self, order: dict):
        """Apply a build order to game state."""
        territory = order.get('territory')
        player_id = order.get('player_id')
        building_type = order.get('building_type')
        plot_index = order.get('plot_index')

        # In multiplayer, skip execution for local player's orders
        # Local player already executed when they clicked (for visual feedback)
        # Only execute remote player orders
        local_player = self.sim_state.local_player_index
        if local_player is not None and player_id == local_player:
            sim_log.detail(f"Skipping build order for local player {player_id} (already executed)")
            return

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        # start_construction handles gold deduction internally
        success = self.gs.start_construction(territory, plot_index, building_type)
        if success:
            sim_log.order(player_id, "build", f"{building_type} in {territory}")
        else:
            sim_log.error(f"Player {player_id} failed to build {building_type} in {territory}")

        self.gs.current_player = original_player

    def _apply_train_order(self, order: dict):
        """Apply a train order to game state."""
        territory = order.get('territory')
        player_id = order.get('player_id')
        unit_type = order.get('unit_type')
        barracks_plot = order.get('barracks_plot')

        # In multiplayer, skip execution for local player's orders
        # Local player already executed when they clicked (for visual feedback)
        # Only execute remote player orders
        local_player = self.sim_state.local_player_index
        if local_player is not None and player_id == local_player:
            sim_log.detail(f"Skipping train order for local player {player_id} (already executed)")
            return

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        # start_training handles gold deduction internally
        success = self.gs.start_training(territory, barracks_plot, unit_type)
        if success:
            sim_log.order(player_id, "train", f"{unit_type} in {territory}")
        else:
            sim_log.error(f"Player {player_id} failed to train {unit_type} in {territory}")

        self.gs.current_player = original_player

    def _apply_research_order(self, order: dict):
        """Apply a research order to game state."""
        player_id = order.get('player_id')
        tech_id = order.get('tech_id')

        # In multiplayer, skip execution for local player's orders
        # Local player already executed when they clicked (for visual feedback)
        local_player = self.sim_state.local_player_index
        if local_player is not None and player_id == local_player:
            sim_log.detail(f"Skipping research order for local player {player_id} (already executed)")
            return

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        # start_research handles gold deduction internally
        success = self.gs.start_research(tech_id)
        if success:
            sim_log.order(player_id, "research", f"tech {tech_id}")
        else:
            sim_log.error(f"Player {player_id} failed to research tech {tech_id}")

        self.gs.current_player = original_player

    def _apply_upgrade_castle_order(self, order: dict):
        """Apply a castle upgrade order to game state."""
        territory = order.get('territory')
        player_id = order.get('player_id')
        plot_index = order.get('plot_index')

        # In multiplayer, skip execution for local player's orders
        # Local player already executed when they clicked (for visual feedback)
        # Only execute remote player orders
        local_player = self.sim_state.local_player_index
        if local_player is not None and player_id == local_player:
            sim_log.detail(f"Skipping upgrade_castle order for local player {player_id} (already executed)")
            return

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        success = self.gs.start_castle_upgrade(territory, plot_index)
        if success:
            sim_log.order(player_id, "upgrade_castle", f"in {territory}")
        else:
            sim_log.error(f"Player {player_id} failed to upgrade castle in {territory}")

        self.gs.current_player = original_player

    def _apply_demolish_order(self, order: dict):
        """Apply a demolish order to game state."""
        territory = order.get('territory')
        player_id = order.get('player_id')
        plot_index = order.get('plot_index')

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        success = self.gs.destroy_building(territory, plot_index)
        if success:
            sim_log.order(player_id, "demolish", f"in {territory}")
        else:
            sim_log.error(f"Player {player_id} failed to demolish building in {territory}")

        self.gs.current_player = original_player

    def _apply_hero_ability_order(self, order: dict):
        """Apply a hero ability order to game state."""
        player_id = order.get('player_id')
        hero_type = order.get('hero_type')  # Hero name (e.g., 'Brennhen')
        ability_name = order.get('ability_name')  # Ability name (e.g., 'Reinforce')
        target = order.get('target')  # Target territory or None

        if not hero_type or not ability_name:
            sim_log.error("Invalid hero ability order: missing hero_type or ability_name")
            return

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        try:
            # Find the ability index from the hero's abilities list
            hero_info = self.gs.HERO_TYPES.get(hero_type)
            if not hero_info:
                sim_log.error(f"Unknown hero type: {hero_type}")
                return

            ability_index = None
            abilities = hero_info.get('abilities', [])
            for i, ability in enumerate(abilities):
                if ability.get('name') == ability_name:
                    ability_index = i
                    break

            if ability_index is None:
                sim_log.error(f"Unknown ability '{ability_name}' for hero {hero_type}")
                return

            # Activate the hero ability
            result = self.gs.activate_hero_ability(hero_type, ability_index)

            if result == 'requires_targeting' and target:
                # Execute targeted abilities
                if ability_name == 'Relentless Charge':
                    # FIX: Arguments were swapped - signature is (target_territory, owner)
                    self.gs.execute_relentless_charge(target, player_id)
                    sim_log.order(player_id, "hero_ability", f"Relentless Charge on {target}")
                elif ability_name == 'Aggressive Diplomacy':
                    # FIX: Arguments were swapped - signature is (target_territory, owner)
                    self.gs.execute_aggressive_diplomacy(target, player_id)
                    sim_log.order(player_id, "hero_ability", f"Aggressive Diplomacy on {target}")
                elif ability_name == 'Levy':
                    # FIX: Arguments were swapped - signature is (target_territory, owner)
                    self.gs.execute_levy(target, player_id)
                    sim_log.order(player_id, "hero_ability", f"Levy on {target}")
                else:
                    sim_log.error(f"Unknown targeted ability: {ability_name}")
            elif result is True:
                sim_log.order(player_id, "hero_ability", f"{hero_type}'s {ability_name}")
            elif isinstance(result, str) and result != 'requires_targeting':
                # Error message returned
                sim_log.error(f"Hero ability failed: {result}")
            else:
                sim_log.detail(f"Hero ability activation returned: {result}")

        except Exception as e:
            # Log hero ability error with full traceback
            sim_log.error(f"Error executing hero ability for player {player_id}: {e}")
            logger.error(f"Error executing hero ability for player {player_id}: {e}", exc_info=True)
        finally:
            self.gs.current_player = original_player

    def _apply_train_hero_order(self, order: dict):
        """Apply a hero training order to game state."""
        player_id = order.get('player_id')
        hero_type = order.get('hero_type')
        territory = order.get('territory')
        # Support both field names for compatibility
        keep_plot = order.get('keep_plot') if order.get('keep_plot') is not None else order.get('keep_plot_index')

        if not hero_type:
            sim_log.error("Invalid hero training order: missing hero_type")
            return

        if not territory or keep_plot is None:
            sim_log.error("Invalid hero training order: missing territory or keep_plot")
            return

        # In multiplayer, skip execution for local player's orders
        # Local player already executed when they clicked (for visual feedback)
        # Only execute remote player orders
        local_player = self.sim_state.local_player_index
        if local_player is not None and player_id == local_player:
            sim_log.detail(f"Skipping train_hero order for local player {player_id} (already executed)")
            return

        # GameState methods use current_player, so temporarily set it
        original_player = self.gs.current_player
        self.gs.current_player = player_id

        try:
            # Call the actual hero training method
            success = self.gs.start_hero_training(territory, keep_plot, hero_type)
            if success:
                sim_log.order(player_id, "train_hero", f"{hero_type} in {territory}")
            else:
                sim_log.error(f"Player {player_id} failed to train hero {hero_type} in {territory}")
        except Exception as e:
            # Log hero training error with full traceback
            sim_log.error(f"Error starting hero training for player {player_id}: {e}")
            logger.error(f"Error starting hero training for player {player_id}: {e}", exc_info=True)
        finally:
            self.gs.current_player = original_player

    def _execute_movement_orders(self, orders: List[dict]):
        """
        Execute movement orders, creating animations.

        All movements happen SIMULTANEOUSLY.

        Args:
            orders: List of movement order dictionaries
        """
        sim_log.phase(f"Executing {len(orders)} movement orders")

        # Initialize pending arrivals tracking
        self._sim_pending_arrivals = []

        if not orders:
            sim_log.phase("No movement orders, completing animations immediately")
            self.animations_complete = True
            self._on_animations_complete()
            return

        # Create movement animations for all orders
        for order in orders:
            sim_log.detail(f"Creating animation: {order.get('from_territory')} -> {order.get('to_territory')}")
            self._create_movement_animation(order)

        sim_log.phase(f"Created {len(self.gs.active_animations)} animations, waiting for completion")
        # main.py will call on_animations_complete when active_animations becomes empty

    def _create_movement_animation(self, order: dict):
        """
        Create an animation for a movement order.

        Creates ArmyAnimation objects and adds them to game_state.active_animations.
        The main loop's animation system will update these and call on_animations_complete
        when all finish.

        Args:
            order: Movement order dictionary
        """
        from_territory = order.get('from_territory')
        to_territory = order.get('to_territory')
        player_id = order.get('player_id')
        army_count = order.get('army_count')
        unit_ids = order.get('unit_ids', [])

        # Extract units from source territory
        garrison = self.gs.territory_garrisons.get(from_territory, {})
        player_garrison = garrison.get(player_id, {})

        # Determine composition
        composition = self._extract_composition(player_garrison, army_count, unit_ids)

        # Reduce unmoved count at source
        unmoved = player_garrison.get('unmoved', 0)
        player_garrison['unmoved'] = max(0, unmoved - army_count)

        # Also update legacy armies dict for compatibility
        self.gs.armies[from_territory] = max(0, self.gs.armies.get(from_territory, 0) - army_count)

        # Remove units from source garrison if tracking individual units
        # Veterancy: collect extracted units to preserve xp/level through animation
        extracted_units = []
        units = player_garrison.get('units', [])
        if unit_ids:
            # Remove specific units, preserving the extracted dicts
            remaining = []
            ids_set = set(unit_ids)
            for u in units:
                if u.get('id') in ids_set:
                    extracted_units.append(u)
                    ids_set.discard(u.get('id'))
                else:
                    remaining.append(u)
            player_garrison['units'] = remaining
        elif units and army_count > 0:
            # Remove any units (from the end), preserving extracted dicts
            removed = 0
            new_units = []
            for unit in reversed(units):
                if removed < army_count:
                    removed += 1
                    extracted_units.insert(0, unit)
                else:
                    new_units.insert(0, unit)
            player_garrison['units'] = new_units

        # Sync garrison counts with actual unit list after unit removal to fix
        # desync where count decrements don't match the number of units removed
        self.gs._sync_garrison_counts(from_territory, player_id)

        # Create ArmyAnimation object directly (like execute_all_orders does)
        # Pass extracted_units to preserve xp/level through animation pipeline
        animation = ArmyAnimation(
            from_territory=from_territory,
            to_territory=to_territory,
            army_count=army_count,
            player=player_id,
            unit_ids=unit_ids,
            composition=composition,
            units=extracted_units
        )

        # Add to game_state's active animations list
        self.gs.active_animations.append(animation)

        # Cleanup empty garrison at source to prevent ghost flags
        if hasattr(self.gs, 'cleanup_empty_garrisons'):
            self.gs.cleanup_empty_garrisons(from_territory)

        # Also track in pending_arrivals for processing when complete
        # (Similar to how execute_all_orders works - arrivals processed after animations)
        if not hasattr(self, '_sim_pending_arrivals'):
            self._sim_pending_arrivals = []
        self._sim_pending_arrivals.append(animation)

    def _extract_composition(self, garrison: dict, count: int, unit_ids: List) -> dict:
        """
        Extract unit composition from a garrison.

        Args:
            garrison: Player garrison dictionary
            count: Number of units to extract
            unit_ids: Specific unit IDs (if any)

        Returns:
            Composition dictionary {unit_type: count}
        """
        composition = {}
        units = garrison.get('units', [])

        if unit_ids:
            # Extract specific units
            for unit_id in unit_ids:
                for unit in units:
                    if unit.get('id') == unit_id:
                        unit_type = unit.get('type', 'Swordsman')
                        composition[unit_type] = composition.get(unit_type, 0) + 1
                        break
        else:
            # Extract any units (from the end to match removal order)
            # Note: Removal in _execute_movement_orders uses reversed(units)
            extracted = 0
            for unit in reversed(units):
                if extracted >= count:
                    break
                unit_type = unit.get('type', 'Swordsman')
                composition[unit_type] = composition.get(unit_type, 0) + 1
                extracted += 1

        # Fallback: If no units tracked but count > 0, default to Swordsmen
        # This handles cases where the units list isn't populated
        if not composition and count > 0:
            sim_log.sync(f"WARNING: No units found in garrison, defaulting {count} to Swordsmen")
            composition['Swordsman'] = count

        return composition

    def on_animations_complete(self):
        """Called when all movement animations are complete."""
        self.animations_complete = True
        self._on_animations_complete()

    def _on_animations_complete(self):
        """Handle completion of movement animations."""
        sim_log.phase("Animations complete, processing arrivals")

        # Process arrivals - add armies to destination territories
        self._process_arrivals()

        # Detect battles and alliance arrivals
        self._detect_conflicts()
        sim_log.phase(f"Conflicts: {len(self.pending_battles)} battles, {len(self.pending_alliance_markers)} alliance markers")

        # Move to resolution phase
        self.sim_state.advance_to_resolution()

        # Set up battle objects for the battle UI (instead of auto-resolving)
        if self.pending_battles:
            sim_log.battle(f"Setting up {len(self.pending_battles)} battles for UI resolution")
            self._setup_battles_for_ui()
            # Don't complete round yet - wait for battles to be resolved via UI
            return

        # If no battles/markers, complete the round
        # In multiplayer, only host completes (broadcasts SIM_ROUND_COMPLETE)
        # Client waits for SIM_ROUND_COMPLETE from host
        if not self.pending_battles and not self.pending_alliance_markers:
            if not self.sim_state.is_multiplayer_client:
                sim_log.phase("No battles/markers, completing round")
                self.sim_state.complete_round()
            else:
                sim_log.sync("Client waiting for SIM_ROUND_COMPLETE from host")

    def _process_arrivals(self):
        """Process all pending army arrivals after animations complete."""
        arrivals = getattr(self, '_sim_pending_arrivals', [])
        sim_log.phase(f"Processing {len(arrivals)} arrivals")

        # Track which territories received armies for ownership check
        territories_with_arrivals = set()

        for anim in arrivals:
            to_territory = anim.to_territory
            player_id = anim.player
            army_count = anim.army_count
            composition = anim.composition or {}
            unit_ids = anim.unit_ids or []

            territories_with_arrivals.add(to_territory)

            # Get or create garrison at destination
            if to_territory not in self.gs.territory_garrisons:
                self.gs.territory_garrisons[to_territory] = {}
            garrison = self.gs.territory_garrisons[to_territory]

            if player_id not in garrison:
                garrison[player_id] = {'unmoved': 0, 'moved': 0, 'units': []}
            player_garrison = garrison[player_id]

            # Add to moved count (these armies can't move again this round)
            player_garrison['moved'] = player_garrison.get('moved', 0) + army_count

            # Add units to destination
            units = player_garrison.get('units', [])
            if not units:
                player_garrison['units'] = []
                units = player_garrison['units']

            # Veterancy: use actual unit dicts from animation to preserve xp/level
            extracted_units = getattr(anim, 'units', []) or []
            units_created = 0
            if extracted_units:
                # Reuse actual unit dicts (preserves xp/level), reassign IDs and status
                for unit in extracted_units:
                    unit['id'] = len(units)
                    unit['status'] = 'moved'
                    unit['order'] = None
                    units.append(unit)
                    units_created += 1
            else:
                # Fallback: create unit objects based on composition
                for unit_type, count in composition.items():
                    for _ in range(count):
                        new_id = len(units)
                        units.append({
                            'id': new_id,
                            'type': unit_type,
                            'status': 'moved',
                            'xp': 0,
                            'level': 0
                        })
                        units_created += 1

            # Fallback: If composition was empty but army_count > 0, create default Swordsmen
            if units_created < army_count:
                remaining = army_count - units_created
                sim_log.sync(f"WARNING: Creating {remaining} default Swordsmen (composition incomplete)")
                for _ in range(remaining):
                    new_id = len(units)
                    units.append({
                        'id': new_id,
                        'type': 'Swordsman',
                        'status': 'moved',
                        'xp': 0,
                        'level': 0
                    })

            # Update armies count in legacy system (for compatibility)
            self.gs.armies[to_territory] = self.gs.armies.get(to_territory, 0) + army_count

            # Sync garrison counts with actual unit list after incremental arrival add
            self.gs._sync_garrison_counts(to_territory, player_id)

            sim_log.detail(f"{army_count} armies arrived in {to_territory} for player {player_id}")

        # Check for territory captures (no battle needed if no defenders)
        for territory in territories_with_arrivals:
            current_owner = self.gs.territory_owners.get(territory, -1)
            garrison = self.gs.territory_garrisons.get(territory, {})
            players_present = [
                pid for pid, pg in garrison.items()
                if (pg.get('unmoved', 0) + pg.get('moved', 0)) > 0
            ]


            sim_log.detail(f"Territory {territory}: owner={current_owner}, players_present={players_present}")

            if current_owner == -1:
                # Neutral territory - check who has armies there
                if len(players_present) == 1:
                    # Single player captures neutral territory
                    new_owner = players_present[0]
                    self.gs.territory_owners[territory] = new_owner
                    self.gs._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    self.gs.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses
                    sim_log.sync(f"Player {new_owner} captured neutral territory {territory}")
                    # Capital Assault: Check if this neutral territory was someone's capital (rare edge case)
                    self._check_capital_assault_eliminations(territory, new_owner)
                    # Check victory after any uncontested capture (Domination, Total Conquest, etc.)
                    self.gs.check_victory()
                elif len(players_present) > 1:
                    # Multiple players arrived - _detect_conflicts will handle it as a battle
                    sim_log.battle(f"Multiple players ({players_present}) at neutral {territory} - battle needed")

            elif len(players_present) == 1:
                # Enemy/allied territory with only ONE player having armies
                # If that player is NOT the owner and is an enemy, they capture it
                sole_player = players_present[0]
                owner_team = self.gs.player_teams[current_owner] if current_owner >= 0 else -1
                sole_player_team = -1 if sole_player == -1 else self.gs.player_teams[sole_player]

                # Check if sole player is NOT allied with owner (enemy capture)
                if owner_team != sole_player_team:
                    # Enemy captures undefended territory
                    self.gs.territory_owners[territory] = sole_player
                    self.gs._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    self.gs.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses
                    sim_log.sync(f"Player {sole_player} captured undefended territory {territory} (was P{current_owner})")

                    # Destroy buildings on conquest (respects Seledra's Champion of the People)
                    # Matches single-turn behavior in military.py _process_arrivals()
                    self.gs.destroy_buildings(territory, current_owner, new_owner=sole_player)

                    # Capital Assault: Check if captured territory is enemy's capital
                    self._check_capital_assault_eliminations(territory, sole_player)
                    # Check victory after any uncontested capture (Domination, Total Conquest, etc.)
                    self.gs.check_victory()

                    # Cleanup old owner's empty garrison if present
                    if current_owner >= 0 and current_owner in garrison:
                        del garrison[current_owner]
                        sim_log.detail(f"Removed empty garrison of player {current_owner} from {territory}")

        # Enforce army limits after all arrivals processed (safety net for simultaneous deposits)
        self.gs._enforce_army_limits()

        # Clear pending arrivals
        self._sim_pending_arrivals = []

    def _detect_conflicts(self):
        """Detect battles and alliance arrivals after movements."""
        # Clear previous
        self.pending_battles.clear()
        self.pending_alliance_markers.clear()

        # Check all territories for conflicts
        # Important: Check both owned territories AND territories with garrisons
        # This ensures neutral territories with arriving armies are also checked
        territories_to_check = set(self.gs.territory_owners.keys())
        territories_to_check.update(self.gs.territory_garrisons.keys())

        sim_log.detail(f"Checking {len(territories_to_check)} territories for conflicts")

        for territory in territories_to_check:
            # Debug: check garrison state for territories with armies
            garrison = self.gs.territory_garrisons.get(territory, {})
            players_with_armies = [
                (pid, pg.get('unmoved', 0) + pg.get('moved', 0))
                for pid, pg in garrison.items()
                if (pg.get('unmoved', 0) + pg.get('moved', 0)) > 0
            ]
            if len(players_with_armies) > 1:
                sim_log.conflict(f"Territory {territory} has multiple players: {players_with_armies}")

            conflict = self._check_territory_conflict(territory)

            if conflict:
                if conflict['type'] == 'battle':
                    sim_log.battle(f"Battle detected at {territory}: players {conflict['players']}")
                    self.pending_battles.append(conflict)
                elif conflict['type'] == 'alliance':
                    sim_log.alliance(f"Alliance marker at {territory}: players {conflict['players']}")
                    self.pending_alliance_markers.append(conflict)

    def _check_territory_conflict(self, territory: str) -> Optional[dict]:
        """
        Check a territory for battle or alliance arrival.

        Args:
            territory: Territory name

        Returns:
            Conflict dictionary or None
        """
        garrison = self.gs.territory_garrisons.get(territory, {})

        # Get all players with armies in this territory (including neutral player -1)
        players_present = [
            player_id for player_id, player_garrison in garrison.items()
            if (player_garrison.get('unmoved', 0) + player_garrison.get('moved', 0)) > 0
        ]

        if len(players_present) <= 1:
            return None  # No conflict

        # Check if all players are allies
        # Player -1 (neutral armies) is always hostile — use team -1 instead of
        # player_teams[-1] which would use Python negative indexing (returning last player's team)
        teams = set()
        for player_id in players_present:
            if player_id == -1:
                team = -1  # Neutral armies are hostile to all players
            else:
                team = self.gs.player_teams[player_id]
            teams.add(team)

        if len(teams) == 1:
            # All same team - alliance arrival (only if neutral/enemy territory)
            owner = self.gs.territory_owners.get(territory, -1)
            owner_team = self.gs.player_teams[owner] if owner >= 0 else -1

            if owner_team not in teams:
                # Territory being captured by allies
                return self._create_alliance_conflict(territory, players_present)
        else:
            # Multiple teams - battle
            return self._create_battle_conflict(territory, players_present)

        return None

    def _create_battle_conflict(self, territory: str, players: List[int]) -> dict:
        """Create a battle conflict descriptor."""
        # Determine resolver based on attacker/defender roles:
        # - If attacking an owned territory: ATTACKER always resolves (regardless of strength)
        # - If multiple attackers at neutral territory: highest effective strength resolves

        territory_owner = self.gs.territory_owners.get(territory, -1)
        owner_team = self.gs.player_teams[territory_owner] if territory_owner >= 0 else -1

        # Identify attackers (non-owners/non-allies) vs defenders (owner/allies)
        # Player -1 (neutral) is always a defender in their own territory, never an attacker
        attackers = []
        defenders = []
        for player_id in players:
            if player_id == -1:
                # Neutral garrison is always a defender in neutral-owned territory
                defenders.append(player_id)
            else:
                player_team = self.gs.player_teams[player_id]
                if territory_owner >= 0 and player_team == owner_team:
                    defenders.append(player_id)
                else:
                    attackers.append(player_id)

        # Check if attackers are from multiple teams (multi-way battle)
        attacker_teams = set()
        for attacker_id in attackers:
            attacker_teams.add(-1 if attacker_id == -1 else self.gs.player_teams[attacker_id])

        is_multi_way_battle = len(attacker_teams) > 1
        sim_log.battle(f"{territory}: owner={territory_owner}, attackers={attackers}, defenders={defenders}, multi-way={is_multi_way_battle}")

        # Get compositions for all players (needed for effective strength calc)
        player_compositions = {}
        garrison = self.gs.territory_garrisons.get(territory, {})

        for player_id in players:
            player_garrison = garrison.get(player_id, {})
            units = player_garrison.get('units', [])
            composition = {}
            for unit in units:
                unit_type = unit.get('type', 'Swordsman')
                composition[unit_type] = composition.get(unit_type, 0) + 1

            # Fallback: if no units tracked, count as Swordsmen
            if not composition:
                army_count = player_garrison.get('unmoved', 0) + player_garrison.get('moved', 0)
                if army_count > 0:
                    composition['Swordsman'] = army_count

            player_compositions[player_id] = composition

        # Determine resolver based on battle type:
        # 1. Single attacker vs garrison → Attacker ALWAYS resolves (regardless of strength)
        # 2. Multiple allied attackers (same team) vs enemy → Highest effective strength among allies
        # 3. Multi-way battle (attackers from different teams) → Highest effective strength among ALL participants
        #    (dice roll determines battle order, but strongest player controls the UI)

        if is_multi_way_battle:
            # Multi-way battle: consider ALL real participants for resolver (never neutral -1)
            resolver_candidates = [p for p in players if p != -1]
            sim_log.detail(f"Multi-way battle - considering all {len(resolver_candidates)} participants for resolver")
        else:
            # Standard attack: resolver chosen from attackers only (never neutral -1)
            resolver_candidates = [p for p in attackers if p != -1] if attackers else [p for p in players if p != -1]

        if len(resolver_candidates) == 1:
            # Single attacker - they are the resolver (regardless of strength)
            resolver = resolver_candidates[0]
            sim_log.detail(f"Single attacker - player {resolver} is resolver")
        else:
            # Multiple candidates - use effective strength
            max_strength = 0
            resolver = resolver_candidates[0]

            for player_id in resolver_candidates:
                my_composition = player_compositions.get(player_id, {})

                # Aggregate all enemy compositions (opponents from different teams)
                my_team = -1 if player_id == -1 else self.gs.player_teams[player_id]
                enemy_composition = {}
                for opp_id in players:
                    opp_team = -1 if opp_id == -1 else self.gs.player_teams[opp_id]
                    if opp_team != my_team:
                        opp_comp = player_compositions.get(opp_id, {})
                        for unit_type, count in opp_comp.items():
                            enemy_composition[unit_type] = enemy_composition.get(unit_type, 0) + count

                # Calculate effective strength using game_state method
                if hasattr(self.gs, 'calculate_army_effective_strength'):
                    strength = self.gs.calculate_army_effective_strength(my_composition, enemy_composition)
                else:
                    # Fallback: just count armies
                    strength = sum(my_composition.values())

                sim_log.detail(f"Player {player_id} strength: {strength:.2f}", my_composition)

                if strength > max_strength:
                    max_strength = strength
                    resolver = player_id

            if is_multi_way_battle:
                sim_log.battle(f"Multi-way battle resolver: player {resolver} (strength: {max_strength:.2f})")
            else:
                sim_log.battle(f"Allied attackers resolver: player {resolver} (strength: {max_strength:.2f})")

        return {
            'type': 'battle',
            'territory': territory,
            'players': players,
            'resolver': resolver,
            'is_multi_way': is_multi_way_battle,  # For dice roll order in multi-way battles
            'attackers': attackers,  # List of attacking players (for UI to show correct sides)
            'defenders': defenders   # List of defending players (owner + allies)
        }

    def _create_alliance_conflict(self, territory: str, players: List[int]) -> dict:
        """Create an alliance arrival conflict descriptor."""
        # Find player with biggest army to choose owner
        max_army = 0
        chooser = players[0]

        for player_id in players:
            army = self._get_player_army_count_in_territory(territory, player_id)
            if army > max_army:
                max_army = army
                chooser = player_id

        return {
            'type': 'alliance',
            'territory': territory,
            'players': players,
            'chooser': chooser
        }

    def _get_player_strength_in_territory(self, territory: str, player_id: int) -> int:
        """Get a player's total effective strength in a territory."""
        garrison = self.gs.territory_garrisons.get(territory, {})
        player_garrison = garrison.get(player_id, {})
        return player_garrison.get('unmoved', 0) + player_garrison.get('moved', 0)

    def _get_player_army_count_in_territory(self, territory: str, player_id: int) -> int:
        """Get a player's army count in a territory."""
        return self._get_player_strength_in_territory(territory, player_id)

    def get_next_battle(self) -> Optional[dict]:
        """Get the next battle to resolve, or None if all resolved."""
        if self.pending_battles:
            return self.pending_battles[0]
        return None

    def resolve_current_battle(self, result: dict):
        """
        Mark the current battle as resolved.

        Args:
            result: Battle result dictionary
        """
        if self.pending_battles:
            self.pending_battles.pop(0)

        # Check for elimination
        for player_id in range(self.gs.num_players):
            if self._is_player_eliminated(player_id):
                self.sim_state.eliminate_player(player_id)

        # If no more battles, check alliance markers
        # H6 fix: gate behind is_multiplayer_client check (matches _on_animations_complete
        # and resolve_alliance_marker) to prevent client desync
        if not self.pending_battles:
            if not self.pending_alliance_markers:
                if not self.sim_state.is_multiplayer_client:
                    self.sim_state.complete_round()

    def _is_player_eliminated(self, player_id: int) -> bool:
        """Check if a player has been eliminated (no territories or capital lost in Capital Assault)."""
        # Already eliminated?
        if player_id in self.sim_state.eliminated_players:
            return False  # Already handled

        # Check for 0 territories
        territories = [t for t, owner in self.gs.territory_owners.items() if owner == player_id]
        if len(territories) == 0:
            return True

        # Check for Capital Assault: player lost their capital to an enemy
        # Note: If an ally owns the capital, the player is NOT eliminated
        if self.gs.victory_condition == "Capital Assault":
            if hasattr(self.gs, 'player_starting_territories'):
                capital = self.gs.player_starting_territories.get(player_id)
                if capital is not None:
                    current_owner = self.gs.territory_owners.get(capital, -1)
                    # Only eliminate if capital is owned by an enemy (not self or ally)
                    if current_owner != player_id and current_owner >= 0 and not self.gs.are_allies(player_id, current_owner):
                        # Player lost their capital to an enemy - they are eliminated
                        logger.info(f"[CAPITAL ASSAULT] Player {player_id + 1}'s capital {capital} was captured by enemy Player {current_owner + 1}!")
                        return True

        return False

    def _check_capital_assault_eliminations(self, captured_territory: str, new_owner: int):
        """
        Check if capturing a territory eliminates any player in Capital Assault mode.

        Args:
            captured_territory: The territory that was just captured
            new_owner: The player who captured it
        """
        if self.gs.victory_condition != "Capital Assault":
            return

        if not hasattr(self.gs, 'player_starting_territories'):
            return

        # Check if this territory is anyone's capital
        # Note: Allies cannot eliminate each other - only enemies can capture capitals
        for player_index, capital in self.gs.player_starting_territories.items():
            # Check: capital matches, not self, and not an ally (enemies only)
            if capital == captured_territory and player_index != new_owner and not self.gs.are_allies(new_owner, player_index):
                # Capital conquered - eliminate the player
                if player_index not in self.sim_state.eliminated_players:
                    logger.info(f"[CAPITAL ASSAULT] Player {new_owner + 1} conquered Player {player_index + 1}'s capital!")
                    self.gs.eliminate_player(player_index)
                    self.sim_state.eliminate_player(player_index)
                    # Check for victory after elimination
                    self.gs.check_victory()

    def get_next_alliance_marker(self) -> Optional[dict]:
        """Get the next alliance marker to resolve, or None if all resolved."""
        if self.pending_alliance_markers:
            return self.pending_alliance_markers[0]
        return None

    def resolve_alliance_marker(self, territory: str, new_owner: int):
        """
        Resolve an alliance marker by assigning territory ownership.

        Args:
            territory: Territory being assigned
            new_owner: Player who will own the territory
        """
        self.alliance_handler.assign_territory(territory, new_owner)

        if self.pending_alliance_markers:
            self.pending_alliance_markers.pop(0)

        # If no more markers, complete round
        # In multiplayer, only host completes (broadcasts SIM_ROUND_COMPLETE)
        # Client waits for SIM_ROUND_COMPLETE from host
        if not self.pending_alliance_markers and not self.pending_battles:
            if not self.sim_state.is_multiplayer_client:
                self.sim_state.complete_round()
            else:
                sim_log.sync("Client waiting for SIM_ROUND_COMPLETE from host")

    def _setup_battles_for_ui(self):
        """
        Set up proper Battle objects for the battle UI system.

        Creates Battle objects from the detected conflicts and adds them to
        game_state.pending_battles so the main loop can render battle markers
        and the player can resolve battles using the standard battle UI.

        Allies are grouped by team - their armies are combined under the team leader.
        """
        # Process all detected battles
        battles_to_setup = list(self.pending_battles)
        self.pending_battles.clear()

        for battle_data in battles_to_setup:
            territory = battle_data['territory']
            players = battle_data['players']

            sim_log.battle(f"Setting up battle at {territory} between players {players}")

            # Group players by team (allies fight together)
            # Map each player to their team leader (lowest player index on same team)
            player_to_team_leader = {}
            for player_id in players:
                team = -1 if player_id == -1 else self.gs.player_teams[player_id]
                # Find team leader (lowest index player on same team in this battle)
                team_members = [p for p in players if (-1 if p == -1 else self.gs.player_teams[p]) == team]
                team_leader = min(team_members)
                player_to_team_leader[player_id] = team_leader

            # Aggregate armies by team leader
            team_armies = {}  # {team_leader: total_count}
            team_compositions = {}  # {team_leader: {unit_type: count}}
            team_members_map = {}  # {team_leader: [member_ids]}

            garrison = self.gs.territory_garrisons.get(territory, {})

            for player_id in players:
                team_leader = player_to_team_leader[player_id]

                if team_leader not in team_armies:
                    team_armies[team_leader] = 0
                    team_compositions[team_leader] = {}
                    team_members_map[team_leader] = []

                team_members_map[team_leader].append(player_id)

                # Get this player's army
                player_garrison = garrison.get(player_id, {})
                army_count = player_garrison.get('unmoved', 0) + player_garrison.get('moved', 0)
                team_armies[team_leader] += army_count

                # Get composition from units list
                units = player_garrison.get('units', [])
                for unit in units:
                    unit_type = unit.get('type', 'Swordsman')
                    team_compositions[team_leader][unit_type] = team_compositions[team_leader].get(unit_type, 0) + 1

                # If no units tracked, default to swordsmen
                if not units and army_count > 0:
                    team_compositions[team_leader]['Swordsman'] = team_compositions[team_leader].get('Swordsman', 0) + army_count

            # Create a Battle object with team leaders
            battle = Battle(territory)
            battle.original_owner = self.gs.territory_owners.get(territory, -1)

            # Add team armies to battle (under team leader)
            for team_leader, count in team_armies.items():
                composition = team_compositions[team_leader]
                battle.add_army(team_leader, count, composition)

                # Track allied defenders (allies who are NOT the team leader)
                for member in team_members_map[team_leader]:
                    if member != team_leader:
                        battle.allied_defenders.append(member)
                        sim_log.detail(f"Player {member} fighting as ally of team leader {team_leader}")

            # Check for Keep bonus (defender bonus)
            if battle.original_owner >= 0:
                owner_team_leader = player_to_team_leader.get(battle.original_owner, battle.original_owner)
                if owner_team_leader in team_armies:
                    buildings = self.gs.buildings.get(territory, {})
                    for building in buildings.values():
                        if building in ['Keep', 'Fortress']:
                            battle.keep_bonus = 2
                            battle.keep_bonus_player = owner_team_leader
                            break

            # Store original garrison size for Keep battles
            if battle.original_owner >= 0:
                owner_garrison = garrison.get(battle.original_owner, {})
                battle.original_garrison = owner_garrison.get('unmoved', 0) + owner_garrison.get('moved', 0)

            # Store team members map for post-battle alliance handling
            battle.team_members_map = team_members_map

            # Store the resolver (player with highest effective strength who can click the marker)
            # In simultaneous mode, only the resolver can interact with the battle
            battle.resolver = battle_data.get('resolver')
            battle.is_multi_way = battle_data.get('is_multi_way', False)
            # Store attackers list for battle interface to show correct sides
            battle.attackers = battle_data.get('attackers', [])
            sim_log.battle(f"Resolver: P{battle.resolver}, multi-way: {battle.is_multi_way}, attackers: {battle.attackers}")

            # Add to game_state.pending_battles for the UI system
            self.gs.pending_battles.append(battle)
            sim_log.battle(f"Battle queued: {territory} (teams: {list(team_armies.keys())})")

    def _resolve_battle_combat(self, battle: Battle) -> tuple:
        """
        Resolve combat between armies in a battle.

        Uses the same counter system as sequential mode:
        Swordsman > Pikeman > Cavalry > Archer > Swordsman

        Args:
            battle: Battle object with armies and compositions

        Returns:
            Tuple of (winner_player_id, surviving_army_count)
        """
        player_armies = list(battle.armies.items())

        # Calculate effective strengths
        player_strengths = {}

        for player_id, army_count in player_armies:
            composition = battle.army_compositions.get(player_id, {'Swordsman': army_count})
            # Use 'strength' key (Captain = 0.25, all others = 1.0)
            base_strength = sum(
                count * self.gs.UNIT_TYPES.get(unit_type, {}).get('strength', 1.0)
                for unit_type, count in composition.items()
            )

            # Captain army bonus: +12% strength to non-Captain units (non-stacking)
            has_captain = composition.get('Captain', 0) > 0
            if has_captain:
                captain_bonus_pct = self.gs.UNIT_TYPES.get('Captain', {}).get('army_bonus', 0.12)
                bonus_strength = sum(
                    count * self.gs.UNIT_TYPES.get(ut, {}).get('strength', 1.0) * captain_bonus_pct
                    for ut, count in composition.items() if ut != 'Captain'
                )
                base_strength += bonus_strength

            # Apply counter modifiers based on opponent compositions
            total_modifier = 0
            num_opponents = 0

            for opp_id, _ in player_armies:
                if opp_id == player_id:
                    continue
                opp_comp = battle.army_compositions.get(opp_id, {})
                modifier = self._calculate_counter_modifier(composition, opp_comp)
                total_modifier += modifier
                num_opponents += 1

            if num_opponents > 0:
                avg_modifier = total_modifier / num_opponents
                base_strength *= avg_modifier

            # Add Keep defense bonus
            if battle.keep_bonus_player == player_id and battle.keep_bonus > 0:
                base_strength += battle.keep_bonus * self.gs.UNIT_TYPES.get('Swordsman', {}).get('strength', 1.0)

            player_strengths[player_id] = base_strength
            sim_log.battle(f"Player {player_id}: {army_count} armies, strength={base_strength:.1f}")

        # Determine winner
        max_strength = max(player_strengths.values())
        winners = [p for p, s in player_strengths.items() if s == max_strength]

        if len(winners) > 1:
            # Tie - dice roll
            winner = random.choice(winners)
            sim_log.battle(f"Tie resolved by dice roll, winner: {winner}")
        else:
            winner = winners[0]

        # Calculate casualties (simplified - winner loses proportional to loser's strength)
        winner_strength = player_strengths[winner]
        total_enemy_strength = sum(s for p, s in player_strengths.items() if p != winner)

        if winner_strength > 0:
            casualty_ratio = min(0.9, total_enemy_strength / (winner_strength * 2))
        else:
            casualty_ratio = 0.9

        original_count = battle.armies[winner]
        surviving = max(1, int(original_count * (1 - casualty_ratio)))

        return winner, surviving

    def _calculate_counter_modifier(self, attacker_comp: dict, defender_comp: dict) -> float:
        """
        Calculate counter modifier for attacker against defender composition.

        Counter system: Swordsman > Pikeman > Cavalry > Archer > Swordsman

        Returns:
            Modifier (1.0 = neutral, >1.0 = advantage, <1.0 = disadvantage)
        """
        # Counter relationships (what each unit is strong against)
        # Captain has no counter relationships (support unit)
        counters = {
            'Swordsman': 'Pikeman',
            'Pikeman': 'Cavalry',
            'Cavalry': 'Archer',
            'Archer': 'Swordsman',
            'Captain': None
        }

        total_attacker_units = sum(attacker_comp.values())
        total_defender_units = sum(defender_comp.values())

        if total_attacker_units == 0 or total_defender_units == 0:
            return 1.0

        # Calculate weighted modifier
        total_modifier = 0
        total_weight = 0

        for att_type, att_count in attacker_comp.items():
            countered_type = counters.get(att_type)

            for def_type, def_count in defender_comp.items():
                weight = att_count * def_count

                if countered_type == def_type:
                    # Attacker counters defender - 2.0x effectiveness
                    modifier = 2.0
                elif def_type in counters and counters[def_type] == att_type:
                    # Defender counters attacker - 0.5x effectiveness
                    modifier = 0.5
                else:
                    modifier = 1.0

                total_modifier += modifier * weight
                total_weight += weight

        if total_weight > 0:
            return total_modifier / total_weight
        return 1.0

    def _apply_battle_result(self, territory: str, winner: int, surviving: int,
                             players: List[int], battle: Battle):
        """
        Apply battle results to game state.

        Args:
            territory: Territory where battle occurred
            winner: Winner player ID
            surviving: Number of surviving armies for winner
            players: All players involved in battle
            battle: Battle object with composition data
        """
        garrison = self.gs.territory_garrisons.get(territory, {})

        # Remove all losing player garrisons
        for player_id in players:
            if player_id != winner:
                if player_id in garrison:
                    sim_log.detail(f"Removing player {player_id} garrison from {territory}")
                    del garrison[player_id]

        # Update winner's garrison to surviving count
        if winner in garrison:
            winner_garrison = garrison[winner]

            # Get original composition to determine survivor types
            original_comp = battle.army_compositions.get(winner, {})
            original_total = sum(original_comp.values())

            if original_total > 0 and surviving > 0:
                # M4 fix: preserve XP/veterancy from existing units instead of resetting
                # Build list of surviving units by proportionally reducing each type
                ratio = surviving / original_total
                existing_units = winner_garrison.get('units', [])

                # Group existing units by type, preserving XP data
                units_by_type = {}
                for unit in existing_units:
                    ut = unit.get('type', 'Swordsman')
                    if ut not in units_by_type:
                        units_by_type[ut] = []
                    units_by_type[ut].append(unit)

                new_units = []
                remaining = surviving

                for unit_type, count in original_comp.items():
                    kept = min(remaining, max(1 if count > 0 and remaining > 0 else 0,
                                            int(count * ratio)))
                    # Reuse existing units (with their XP) if available
                    available = units_by_type.get(unit_type, [])
                    for i in range(kept):
                        if i < len(available):
                            # Preserve veteran unit
                            unit = available[i].copy()
                            unit['id'] = len(new_units)
                            unit['status'] = 'moved'
                            unit['order'] = None
                        else:
                            # Fallback: create new unit (shouldn't happen normally)
                            unit = {
                                'id': len(new_units),
                                'type': unit_type,
                                'status': 'moved',
                                'order': None,
                                'xp': 0,
                                'level': 0
                            }
                        new_units.append(unit)
                        remaining -= 1

                winner_garrison['units'] = new_units
            else:
                # Just update counts
                winner_garrison['units'] = []

            # Update army counts
            winner_garrison['unmoved'] = 0
            winner_garrison['moved'] = surviving

        # Update territory ownership
        # IMPORTANT: If defending allies win, the original owner keeps the territory
        # Only transfer ownership if the winner is from a different team (enemy)
        old_owner = self.gs.territory_owners.get(territory, -1)

        if old_owner >= 0:
            old_owner_team = self.gs.player_teams[old_owner]
            winner_team = self.gs.player_teams[winner]

            if old_owner_team == winner_team:
                # Winner is allied with original owner - original owner keeps territory
                # This handles the case where allied defenders successfully defend
                new_owner = old_owner
                sim_log.sync(f"Territory {territory} defended - owner {old_owner} retains")
            else:
                # Winner is from enemy team - they capture the territory
                new_owner = winner
                sim_log.sync(f"Territory {territory} captured by P{winner} (was P{old_owner})")
        else:
            # Neutral territory - winner captures it
            new_owner = winner
            sim_log.sync(f"Territory {territory} captured from neutral by P{winner}")

        self.gs.territory_owners[territory] = new_owner
        self.gs._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
        self.gs.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses

        # Capital Assault: Check if captured territory is a capital
        if new_owner != old_owner and old_owner >= 0:
            self._check_capital_assault_eliminations(territory, new_owner)

        # Update legacy armies dict
        self.gs.armies[territory] = surviving

        # Cleanup empty garrisons
        if hasattr(self.gs, 'cleanup_empty_garrisons'):
            self.gs.cleanup_empty_garrisons(territory)

        # Enforce army limits after battle resolution (winner may exceed cap)
        self.gs._enforce_army_limits()

        # Check for player elimination (0 territories or capital lost)
        elimination_occurred = False
        for player_id in players:
            if player_id != winner and player_id != -1:  # Neutral player -1 can't be "eliminated"
                if self._is_player_eliminated(player_id):
                    self.sim_state.eliminate_player(player_id)
                    sim_log.sync(f"Player {player_id} ELIMINATED!")
                    elimination_occurred = True

        # Check for victory after battle resolution (all victory conditions)
        self.gs.check_victory()
