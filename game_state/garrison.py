# game_state/garrison.py
# Garrison system mixin for GameState (Phase 7 decomposition)

"""
Garrison system: multi-player garrison management, legacy sync, unit movement.

Provides methods for managing the multi-garrison system where multiple players
can have armies in the same territory (e.g., allied garrisons). Also handles
sync to the legacy army tracking arrays.
"""

import math
import time
from utils.logger import get_logger

logger = get_logger(__name__)


class GarrisonMixin:
    """Mixin providing garrison management methods for GameState."""

    def assign_garrison_position(self, territory, player_index, total_garrisons):
        """
        Assign a position index to a garrison, preserving existing positions when possible.

        Args:
            territory: Territory name
            player_index: Player who owns this garrison
            total_garrisons: Total number of garrisons that will exist (current + incoming)

        Returns:
            int: Position index for this garrison (0, 1, 2, etc.)
        """
        if territory not in self.garrison_positions:
            self.garrison_positions[territory] = {}

        # Clean up positions for garrisons that no longer exist
        garrisons = self.territory_garrisons.get(territory, {})
        players_to_remove = []
        for garrison_player in self.garrison_positions[territory].keys():
            garrison = garrisons.get(garrison_player)
            if not garrison or (garrison.get('unmoved', 0) + garrison.get('moved', 0) == 0):
                players_to_remove.append(garrison_player)
        for garrison_player in players_to_remove:
            del self.garrison_positions[territory][garrison_player]

        # If this garrison already has a position, keep it
        if player_index in self.garrison_positions[territory]:
            return self.garrison_positions[territory][player_index]

        # Find the first available position
        used_positions = set(self.garrison_positions[territory].values())
        for pos_idx in range(total_garrisons):
            if pos_idx not in used_positions:
                self.garrison_positions[territory][player_index] = pos_idx
                return pos_idx

        # Fallback: assign next available position
        next_pos = len(self.garrison_positions[territory])
        self.garrison_positions[territory][player_index] = next_pos
        return next_pos

    def get_flag_positions_for_territory(self, territory, center_x, center_y, num_positions=4):
        """
        Generate multiple flag positions for a territory to show different garrisons.

        Returns positions arranged in a circle around the territory center.
        Positions are in world coordinates (before screen transformation).

        Args:
            territory: Territory name
            center_x: Territory center X in world coordinates
            center_y: Territory center Y in world coordinates
            num_positions: Number of positions to generate (default 4)

        Returns:
            list: List of (x, y) tuples for flag positions
        """
        # Distance from center for flag positions (adjust based on territory size)
        radius = 25  # World coordinate units (will be scaled with map)

        positions = []

        if num_positions == 1:
            # Single position at center
            positions.append((center_x, center_y))
        elif num_positions == 2:
            # Two positions: left and right of center
            positions.append((center_x - radius, center_y))
            positions.append((center_x + radius, center_y))
        elif num_positions == 3:
            # Three positions: arranged in triangle
            for i in range(3):
                angle = (i * 120 - 90) * math.pi / 180  # Start from top, rotate 120 degrees each
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
                positions.append((x, y))
        else:
            # Four or more positions: arranged in circle
            for i in range(num_positions):
                angle = (i * 360 / num_positions - 90) * math.pi / 180  # Start from top
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
                positions.append((x, y))

        return positions

    def get_territory_total_armies(self, territory):
        """
        Get total armies in a territory across all garrisons.

        Args:
            territory: Territory name

        Returns:
            int: Total army count (unmoved + moved) across all player garrisons
        """
        if territory not in self.territory_garrisons:
            return 0

        total = 0
        for player_garrison in self.territory_garrisons[territory].values():
            total += player_garrison.get('unmoved', 0) + player_garrison.get('moved', 0)

        return total

    def _get_effective_capacity(self, territory):
        """
        Calculate projected garrison at a territory after all current orders execute.
        Accounts for incoming orders (armies arriving) and outgoing orders (armies leaving).

        Returns:
            (projected_count, outgoing_count) where projected_count = current - outgoing + incoming
        """
        current = self.get_territory_total_armies(territory)
        incoming = sum(
            order.army_count for order in self.movement_orders
            if order.to_territory == territory
        )
        outgoing = sum(
            order.army_count for order in self.movement_orders
            if order.from_territory == territory
        )
        projected = current + incoming - outgoing
        return projected, outgoing

    def _revalidate_incoming_orders(self, territory):
        """
        After cancelling an outgoing order from territory, check if incoming orders
        to that territory now exceed army capacity. Auto-cancels excess incoming orders
        in reverse chronological order (last-added first, preserving earlier orders).

        Cancelled arrows are added to self.cancelling_arrows for visual feedback
        (red shake animation before disappearing).

        Returns:
            list of cancelled order descriptions for messaging
        """
        current = self.get_territory_total_armies(territory)
        outgoing = sum(
            order.army_count for order in self.movement_orders
            if order.from_territory == territory
        )
        # Effective capacity = how many armies can be at this territory
        effective_current = current - outgoing
        available = self.MAX_ARMIES_PER_TERRITORY - effective_current

        # Collect incoming orders to this territory, preserving list index
        incoming_orders = [
            (i, order) for i, order in enumerate(self.movement_orders)
            if order.to_territory == territory
        ]

        # Walk incoming in list order (first-added = highest priority),
        # accumulate until we exceed capacity, then cancel the rest
        accumulated = 0
        orders_to_cancel = []
        for i, order in incoming_orders:
            if accumulated + order.army_count <= available:
                accumulated += order.army_count
            else:
                orders_to_cancel.append((i, order))

        # Cancel excess orders in reverse index order to maintain valid indices
        cancelled_descriptions = []
        for i, order in reversed(orders_to_cancel):
            # Reset unit statuses if Phase 3 order
            if order.unit_ids:
                garrison = self.territory_garrisons.get(
                    order.from_territory, {}
                ).get(order.player)
                if garrison:
                    for unit in garrison.get('units', []):
                        if unit.get('order') == order:
                            unit['status'] = 'ready'
                            unit['order'] = None

            # Add to cancelling_arrows for visual feedback (red shake animation)
            self.cancelling_arrows.append({
                'from_territory': order.from_territory,
                'to_territory': order.to_territory,
                'army_count': order.army_count,
                'start_time': time.time()
            })

            cancelled_descriptions.append(
                f"{order.army_count} armies from {order.from_territory}"
            )
            self.movement_orders.pop(i)

        return cancelled_descriptions

    def get_garrison_armies(self, territory, player):
        """
        Get army count for a specific player's garrison in a territory.

        Args:
            territory: Territory name
            player: Player index

        Returns:
            dict: {'unmoved': int, 'moved': int, 'total': int} or None if no garrison
        """
        if territory not in self.territory_garrisons:
            return None

        if player not in self.territory_garrisons[territory]:
            return None

        garrison = self.territory_garrisons[territory][player]
        return {
            'unmoved': garrison.get('unmoved', 0),
            'moved': garrison.get('moved', 0),
            'total': garrison.get('unmoved', 0) + garrison.get('moved', 0)
        }

    def add_garrison(self, territory, player, unmoved=0, moved=0, units=None):
        """
        Add or update a garrison in a territory.

        Args:
            territory: Territory name
            player: Player index
            unmoved: Number of unmoved armies
            moved: Number of moved armies
            units: List of unit dicts (optional, created if None)
        """
        if territory not in self.territory_garrisons:
            self.territory_garrisons[territory] = {}

        if player not in self.territory_garrisons[territory]:
            self.territory_garrisons[territory][player] = {
                'unmoved': 0,
                'moved': 0,
                'units': []
            }

        garrison = self.territory_garrisons[territory][player]
        garrison['unmoved'] = garrison.get('unmoved', 0) + unmoved
        garrison['moved'] = garrison.get('moved', 0) + moved

        # Create units if not provided
        if units is not None:
            garrison['units'].extend(units)
        else:
            # Create default units (Swordsmen) — diagnostic: this fallback may cause unit type corruption
            total_to_create = unmoved + moved
            if total_to_create > 0:
                logger.warning(f"[UNIT_TYPE_DIAG] add_garrison fallback: creating {total_to_create} default Swordsmen "
                               f"for Player {player + 1} at {territory} (units=None passed)")
            for i in range(total_to_create):
                unit_id = len(garrison['units'])
                status = 'ready' if i < unmoved else 'moved'
                # Phase 2E: Use _make_unit() factory for consistent unit dict creation
                garrison['units'].append(self._make_unit('Swordsman', unit_id, status))

    def remove_garrison(self, territory, player):
        """
        Remove a player's garrison from a territory completely.

        Args:
            territory: Territory name
            player: Player index
        """
        if territory in self.territory_garrisons and player in self.territory_garrisons[territory]:
            del self.territory_garrisons[territory][player]

    def cleanup_empty_garrisons(self, territory):
        """
        Remove any garrisons with 0 armies from a territory.
        This prevents "ghost garrisons" that show flags but have no units.
        Also fixes unit count mismatches.

        Args:
            territory: Territory name
        """
        if territory not in self.territory_garrisons:
            return

        # Find garrisons with 0 armies or mismatched counts
        empty_garrisons = []
        for player_index, garrison_data in self.territory_garrisons[territory].items():
            total_armies = garrison_data.get('unmoved', 0) + garrison_data.get('moved', 0)
            units = garrison_data.get('units', [])
            unit_count = len(units)

            # Fix mismatched unit counts: sync counts from actual units list.
            # The units list is the source of truth - recalculate counts from it
            # instead of creating fake units or truncating the list.
            if unit_count != total_armies:
                logger.warning(f"[TOOLTIP MISMATCH] {territory} Player {player_index}: "
                      f"Count is {total_armies} but unit list has {unit_count}. "
                      f"Syncing counts from unit list.")
                logger.warning(f"  Garrison data: unmoved={garrison_data.get('unmoved')}, moved={garrison_data.get('moved')}")
                logger.warning(f"  First few units: {units[:min(5, len(units))]}")
                # Recalculate counts from actual unit statuses
                self._sync_garrison_counts(territory, player_index)
                # Re-read corrected values for empty garrison check below
                total_armies = garrison_data.get('unmoved', 0) + garrison_data.get('moved', 0)
                unit_count = len(garrison_data.get('units', []))

            # Remove if both army count and unit list are empty
            if total_armies == 0 and unit_count == 0:
                empty_garrisons.append(player_index)
            # Also fix desynced garrisons (units exist but counts are 0)
            elif total_armies == 0 and unit_count > 0:
                # This is a desync - clear the units list too
                garrison_data['units'] = []
                empty_garrisons.append(player_index)

        # Remove empty garrisons
        for player_index in empty_garrisons:
            self.remove_garrison(territory, player_index)

    def _sync_garrison_counts(self, territory, player_index):
        """
        Ensure garrison unmoved/moved counts match the actual units list length.

        This fixes desync bugs where counts diverge from the real unit list due to
        incremental count modifications in movement, casualties, or arrivals.
        Recalculates 'unmoved' and 'moved' by scanning the units list statuses.

        Status mapping:
            'ready' or 'ordered' -> counts toward 'unmoved'
            'moved' -> counts toward 'moved'

        Args:
            territory: Territory name
            player_index: Player index whose garrison to sync
        """
        garrison = self.territory_garrisons.get(territory, {}).get(player_index)
        if not garrison:
            return
        units = garrison.get('units', [])
        # Count units by status: 'ready' and 'ordered' are unmoved, 'moved' is moved
        unmoved = sum(1 for u in units if u.get('status') in ('ready', 'ordered'))
        moved = sum(1 for u in units if u.get('status') == 'moved')
        old_unmoved = garrison.get('unmoved', 0)
        old_moved = garrison.get('moved', 0)
        if old_unmoved != unmoved or old_moved != moved:
            logger.warning(f"Garrison sync fix {territory} P{player_index}: "
                           f"counts ({old_unmoved}u/{old_moved}m) -> ({unmoved}u/{moved}m) "
                           f"based on {len(units)} units")
            garrison['unmoved'] = unmoved
            garrison['moved'] = moved

    def _reduce_garrison(self, territory, player, reduction_count):
        """
        Reduce a garrison's army count by a specified amount.
        Used when army overflow needs to disband excess units.

        Args:
            territory: Territory name
            player: Player index
            reduction_count: Number of armies to remove
        """
        if territory not in self.territory_garrisons:
            return
        if player not in self.territory_garrisons[territory]:
            return

        garrison = self.territory_garrisons[territory][player]
        remaining_to_remove = reduction_count

        # Remove from 'moved' first (newer arrivals)
        moved = garrison.get('moved', 0)
        from_moved = min(moved, remaining_to_remove)
        garrison['moved'] = moved - from_moved
        remaining_to_remove -= from_moved

        # Then from 'unmoved'
        if remaining_to_remove > 0:
            unmoved = garrison.get('unmoved', 0)
            from_unmoved = min(unmoved, remaining_to_remove)
            garrison['unmoved'] = unmoved - from_unmoved
            remaining_to_remove -= from_unmoved

        # Remove units from the list (remove from end)
        units = garrison.get('units', [])
        units_to_remove = reduction_count - remaining_to_remove  # Actual units removed
        if units_to_remove > 0 and len(units) > 0:
            garrison['units'] = units[:-units_to_remove] if units_to_remove < len(units) else []

        # Sync legacy data
        self.sync_legacy_garrison_data(territory)

        # Log the reduction
        self.add_message(f"  Player {player + 1}: {reduction_count} army(ies) disbanded in {territory} (overflow)")

    def _enforce_army_limits(self):
        """
        Safety net: clamp all territory garrisons to MAX_ARMIES_PER_TERRITORY.

        Called after _process_arrivals() and resolve_battle() to catch any cases
        where multiple code paths deposit armies into the same territory in one frame,
        bypassing individual cap checks.
        """
        for territory in list(self.territory_garrisons.keys()):
            for player in list(self.territory_garrisons.get(territory, {}).keys()):
                garrison = self.territory_garrisons[territory].get(player)
                if not garrison:
                    continue
                total = garrison.get('unmoved', 0) + garrison.get('moved', 0)
                if total > self.MAX_ARMIES_PER_TERRITORY:
                    excess = total - self.MAX_ARMIES_PER_TERRITORY
                    logger.info(f"Army cap enforced: {territory} P{player} has {total}, "
                                f"reducing by {excess}")
                    self._reduce_garrison(territory, player, excess)

    def fix_unit_statuses(self, territory, player=None):
        """
        Fix invalid unit statuses in a garrison.

        Units with status='ordered' but order=None should be 'ready'.

        Args:
            territory: Territory name
            player: Optional player index (if None, fix all garrisons in territory)
        """
        if territory not in self.territory_garrisons:
            return

        garrisons_to_fix = {}
        if player is not None:
            if player in self.territory_garrisons[territory]:
                garrisons_to_fix[player] = self.territory_garrisons[territory][player]
        else:
            garrisons_to_fix = self.territory_garrisons[territory]

        for player_index, garrison_data in garrisons_to_fix.items():
            fixed_count = 0
            for unit in garrison_data.get('units', []):
                # Fix: units with 'ordered' status but order not in movement_orders list
                if unit.get('status') == 'ordered':
                    order = unit.get('order')
                    if order is None or order not in self.movement_orders:
                        # Order is None OR order has been executed/removed
                        unit['status'] = 'ready'
                        unit['order'] = None
                        fixed_count += 1

            if fixed_count > 0:
                logger.debug(f"fix_unit_statuses: Fixed {fixed_count} units in {territory} for player {player_index}")

    def sync_legacy_garrison_data(self, territory):
        """
        Sync legacy garrison dictionaries (armies, armies_unmoved, armies_moved, army_units)
        with multi-garrison system for backward compatibility.

        This should be called after updating territory_garrisons to keep old code working.
        Legacy data represents the OWNER's garrison only.

        Args:
            territory: Territory name
        """
        owner = self.territory_owners.get(territory, -1)

        if owner == -1:
            # Neutral territory - clear legacy data
            self.armies[territory] = 0
            self.armies_unmoved[territory] = 0
            self.armies_moved[territory] = 0
            if territory in self.army_units:
                self.army_units[territory] = []
        else:
            # Owned territory - sync with owner's garrison
            garrison = self.get_garrison_armies(territory, owner)
            if garrison:
                self.armies[territory] = garrison['total']
                self.armies_unmoved[territory] = garrison['unmoved']
                self.armies_moved[territory] = garrison['moved']

                # Sync units
                if territory in self.territory_garrisons and owner in self.territory_garrisons[territory]:
                    self.army_units[territory] = self.territory_garrisons[territory][owner]['units'].copy()
            else:
                # Owner has no garrison (shouldn't happen)
                self.armies[territory] = 0
                self.armies_unmoved[territory] = 0
                self.armies_moved[territory] = 0
                if territory in self.army_units:
                    self.army_units[territory] = []

    def get_territory_total_unmoved(self, territory):
        """
        Get total unmoved armies from ALL garrisons in a territory.

        This includes owner + allies, unlike armies_unmoved[territory] which only
        represents the owner's garrison.

        Args:
            territory: Territory name

        Returns:
            int: Total unmoved armies from all players
        """
        total = 0
        if territory in self.territory_garrisons:
            for garrison in self.territory_garrisons[territory].values():
                total += garrison.get('unmoved', 0)
        return total

    def get_territory_total_moved(self, territory):
        """
        Get total moved armies from ALL garrisons in a territory.

        This includes owner + allies, unlike armies_moved[territory] which only
        represents the owner's garrison.

        Args:
            territory: Territory name

        Returns:
            int: Total moved armies from all players
        """
        total = 0
        if territory in self.territory_garrisons:
            for garrison in self.territory_garrisons[territory].values():
                total += garrison.get('moved', 0)
        return total

    def get_territory_all_units(self, territory):
        """
        Get all units from ALL garrisons in a territory.

        This includes owner + allies, unlike army_units[territory] which only
        represents the owner's garrison.

        Args:
            territory: Territory name

        Returns:
            list: Combined list of all units from all players
        """
        all_units = []
        if territory in self.territory_garrisons:
            for garrison in self.territory_garrisons[territory].values():
                all_units.extend(garrison.get('units', []))
        return all_units

    def set_garrison_armies(self, territory, player, unmoved, moved, units=None):
        """
        SET (not add) a garrison to exact values. This replaces the entire garrison.

        Used primarily after combat or when you need to directly set garrison state.
        For adding to existing garrisons, use add_garrison() instead.

        Args:
            territory: Territory name
            player: Player index
            unmoved: Number of unmoved armies
            moved: Number of moved armies
            units: List of unit dicts, or None to auto-create
        """
        if territory not in self.territory_garrisons:
            self.territory_garrisons[territory] = {}

        total = unmoved + moved

        # Auto-create units if not provided — diagnostic: this fallback may cause unit type corruption
        if units is None and total > 0:
            logger.warning(f"[UNIT_TYPE_DIAG] set_garrison_armies fallback: creating {total} default Swordsmen "
                           f"for Player {player + 1} at {territory} (units=None passed)")
            units = self._create_default_units(total, unmoved)
        elif units is None:
            units = []

        # Set garrison to exact values
        self.territory_garrisons[territory][player] = {
            'unmoved': unmoved,
            'moved': moved,
            'units': units
        }

        # Sync legacy data for backward compatibility
        self.sync_legacy_garrison_data(territory)

    # Phase 2E: Unit dict factory method — single source of truth for unit dict creation.
    # All unit dicts in the codebase should be created through _make_unit() to ensure
    # consistent structure and make future field additions (e.g., new stats) trivial.
    def _make_unit(self, unit_type, unit_id, status='moved'):
        """
        Factory method for creating a single unit dict (Phase 2E dedup).

        Every unit dict in the game has the same structure: type, id, status, order, xp, level.
        This method is the single source of truth for that structure, replacing 20+ inline
        dict literals scattered throughout the codebase.

        Args:
            unit_type: Unit type string ('Swordsman', 'Archer', 'Pikeman', 'Cavalry')
            unit_id: Unique ID for the unit (int or string)
            status: 'ready' (can move) or 'moved' (already moved/exhausted). Default: 'moved'

        Returns:
            dict: Unit dict with keys: id, status, order, type, xp, level
        """
        return {
            'id': unit_id,
            'status': status,
            'order': None,
            'type': unit_type,
            'xp': 0,
            'level': 0
        }

    def _create_default_units(self, total_count, unmoved_count):
        """
        Helper to create default Swordsman units with correct statuses.

        Args:
            total_count: Total number of units to create
            unmoved_count: How many should have 'ready' status (rest will be 'moved')

        Returns:
            list: List of unit dicts
        """
        # Phase 2E: Now delegates to _make_unit() factory for consistent unit dict creation
        units = []
        for i in range(total_count):
            status = 'ready' if i < unmoved_count else 'moved'
            unit = self._make_unit('Swordsman', f'unit_{id(self)}_{i}_{total_count}', status)
            units.append(unit)
        return units

    def move_garrison_units(self, from_territory, to_territory, player, unit_count):
        """
        Move units from one territory to another within the garrison system.

        This is a complete movement workflow:
        1. Extract units from source garrison
        2. Mark them as 'moved'
        3. Add them to destination garrison
        4. Sync legacy data for both territories

        Args:
            from_territory: Source territory
            to_territory: Destination territory
            player: Player index
            unit_count: Number of units to move

        Returns:
            bool: True if successful, False if insufficient units
        """
        # Get source garrison
        source_garrison = self.territory_garrisons.get(from_territory, {}).get(player)
        if not source_garrison:
            return False

        # Check if enough unmoved units
        if source_garrison['unmoved'] < unit_count:
            return False

        # Extract units from source (take first unit_count unmoved units)
        units_to_move = []
        remaining_units = []
        units_extracted = 0

        for unit in source_garrison['units']:
            if units_extracted < unit_count and unit['status'] == 'ready':
                # Mark unit as moved and transfer it
                unit['status'] = 'moved'
                units_to_move.append(unit)
                units_extracted += 1
            else:
                remaining_units.append(unit)

        # Validate we got enough units
        if units_extracted < unit_count:
            logger.warning(f"[TOOLTIP MISMATCH] {from_territory} Player {player}: "
                  f"Requested {unit_count} units but only found {units_extracted} ready units. "
                  f"Garrison claims unmoved={source_garrison['unmoved']} but units list mismatch.")

        # Update source garrison (use actual units extracted, not requested count)
        source_garrison['unmoved'] -= units_extracted
        source_garrison['units'] = remaining_units

        # Add to destination garrison as moved units (use actual units extracted)
        self.add_garrison(to_territory, player, unmoved=0, moved=units_extracted, units=units_to_move)

        # Sync legacy data for both territories
        self.sync_legacy_garrison_data(from_territory)
        self.sync_legacy_garrison_data(to_territory)

        return True

    def reset_garrison_moved_status(self, territory):
        """
        Reset all units in a territory to 'ready' status at turn start.

        Also updates the unmoved/moved counts accordingly.
        Uses the actual unit count from the units list as the source of truth.

        Args:
            territory: Territory name
        """
        if territory not in self.territory_garrisons:
            return

        # First, fix any invalid statuses (ordered with no order)
        self.fix_unit_statuses(territory)

        for player, garrison in self.territory_garrisons[territory].items():
            # Reset all unit statuses to 'ready' and clear orders
            for unit in garrison['units']:
                # Any unit without an order should be 'ready'
                if unit.get('order') is None:
                    unit['status'] = 'ready'

            # Update counts based on ACTUAL units in list (source of truth)
            actual_unit_count = len(garrison['units'])
            old_total = garrison['unmoved'] + garrison['moved']

            if actual_unit_count != old_total:
                logger.warning(f"[TOOLTIP MISMATCH] {territory} Player {player}: "
                      f"Garrison count was {old_total} but units list has {actual_unit_count}. "
                      f"Correcting to match actual units.")

            garrison['unmoved'] = actual_unit_count
            garrison['moved'] = 0

        # Sync legacy data
        self.sync_legacy_garrison_data(territory)

    def apply_garrison_casualties(self, territory, player, casualties):
        """
        Apply casualties to a garrison, removing units.

        Removes moved units first, then unmoved units.

        Args:
            territory: Territory name
            player: Player index
            casualties: Number of units to remove

        Returns:
            int: Actual casualties applied (may be less if garrison too small)
        """
        garrison = self.territory_garrisons.get(territory, {}).get(player)
        if not garrison:
            return 0

        total = garrison['unmoved'] + garrison['moved']
        actual_casualties = min(casualties, total)

        if actual_casualties == 0:
            return 0

        # Remove units (moved first, then unmoved)
        units_to_remove = actual_casualties
        remaining_units = []

        # First pass: remove moved units
        for unit in garrison['units']:
            if units_to_remove > 0 and unit['status'] == 'moved':
                units_to_remove -= 1
                garrison['moved'] -= 1
            else:
                remaining_units.append(unit)

        # Second pass: remove unmoved units if needed
        final_units = []
        for unit in remaining_units:
            if units_to_remove > 0 and unit['status'] == 'ready':
                units_to_remove -= 1
                garrison['unmoved'] -= 1
            else:
                final_units.append(unit)

        garrison['units'] = final_units

        # Sync legacy data
        self.sync_legacy_garrison_data(territory)

        return actual_casualties
