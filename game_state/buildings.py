# game_state/buildings.py
# Buildings & technology mixin for GameState (Phase 7 decomposition)

"""
Building system: construction, training, castle upgrades, technology research.

Provides methods for building construction/demolition, unit training,
castle upgrades, and technology research.
"""

from utils.logger import get_logger

logger = get_logger(__name__)


class BuildingMixin:
    """Mixin providing building, training, and technology methods for GameState."""

    # ── Building Queries ────────────────────────────────────────────

    def get_current_player_territories(self):
        """Get list of territories owned by current player"""
        return [t for t, owner in self.territory_owners.items() if owner == self.current_player]

    def has_fortress(self, territory):
        """Check if territory has a completed Fortress (Keep) building"""
        if territory not in self.buildings:
            return False

        for plot_index, building_type in self.buildings[territory].items():
            if building_type == 'Keep':
                return True
        return False

    def has_training_grounds(self, territory):
        """Check if territory has a completed Training Grounds building"""
        if territory not in self.buildings:
            return False
        for plot_index, building_type in self.buildings[territory].items():
            if building_type == 'Training Grounds':
                return True
        return False

    def has_square(self, territory):
        """Check if territory has a completed Square building"""
        if territory not in self.buildings:
            return False
        for plot_index, building_type in self.buildings[territory].items():
            if building_type == 'Square':
                return True
        return False

    def is_castle(self, territory, plot_index):
        """Check if a Keep at this location has been upgraded to Castle"""
        if territory not in self.castle_upgrades:
            return False
        return plot_index in self.castle_upgrades.get(territory, {})

    def is_upgrading_to_castle(self, territory, plot_index):
        """Check if a Keep is currently being upgraded to Castle"""
        if territory not in self.castle_upgrades_in_progress:
            return False
        return plot_index in self.castle_upgrades_in_progress.get(territory, {})

    def player_has_castle(self, player_id):
        """Check if a player owns at least one Castle anywhere on the map"""
        for territory in self.castle_upgrades:
            # Check if this territory is owned by the player
            if self.territory_owners.get(territory) == player_id:
                # Check if there are any castles in this territory
                if self.castle_upgrades[territory]:
                    return True
        return False

    def has_friendly_keep(self, territory, player_id):
        """Check if a territory has a friendly Keep or Castle owned by the player"""
        # Check if player owns the territory
        if self.territory_owners.get(territory) != player_id:
            return False

        # Check if territory has any buildings
        if territory not in self.buildings:
            return False

        # Check if any building is a Keep
        for plot_index, building_type in self.buildings[territory].items():
            if building_type == 'Keep':
                return True

        return False

    def keep_has_hero(self, territory, plot_index, player_id):
        """Check if a Keep/Castle has a hero residing in it"""
        if player_id not in self.heroes:
            return False

        for hero_name, hero_data in self.heroes[player_id].items():
            if (hero_data['keep_territory'] == territory and
                hero_data['keep_plot'] == plot_index):
                return True
        return False

    def get_keep_display_info(self, territory, plot_index):
        """
        Get display letter and name for Keep/Castle.
        Returns: (letter, name) tuple

        Note: Per requirements, show 'C' immediately when upgrade starts,
        not after 2 turns complete.
        """
        # During upgrade OR after upgrade complete, show as Castle
        if (self.is_upgrading_to_castle(territory, plot_index) or
            self.is_castle(territory, plot_index)):
            return ('C', 'Castle')
        return ('K', 'Keep')

    # ── Building Construction ───────────────────────────────────────

    def start_construction(self, territory, plot_index, building_type):
        """Start construction of a building"""
        # Tutorial hook: check if building action is allowed
        if self.tutorial_mission and not self.tutorial_mission.is_action_allowed(
                'build', building_type=building_type, territory=territory):
            return False

        # Check if player owns territory (with error handling)
        try:
            if self.territory_owners[territory] != self.current_player:
                return False
        except KeyError:
            self.log_error(f"Territory '{territory}' not found in territory_owners")
            return False

        # Check if building type exists (with error handling)
        if building_type not in self.building_types:
            self.log_error(f"Invalid building type '{building_type}'")
            return False

        # Check one building per territory per turn limit
        if territory in self.buildings_started_this_turn:
            self.add_message("Only one building per territory per turn!")
            return False

        # Special rule: Only one Keep (Fortress) allowed per territory
        if building_type == 'Keep':
            # Check completed Keeps
            if self.has_fortress(territory):
                self.add_message("Only one Fortress allowed per territory!")
                return False
            # Check Keeps under construction
            if territory in self.under_construction:
                for plot_idx, entry in self.under_construction[territory].items():
                    bldg_type = entry[0]  # under_construction entry is (building_type, turns_remaining, cost)
                    if bldg_type == 'Keep':
                        self.add_message("Already building a Fortress in this territory!")
                        return False

        # Special rule: Only one Training Grounds allowed per territory
        if building_type == 'Training Grounds':
            if self.has_training_grounds(territory):
                self.add_message("Only one Training Grounds allowed per territory!")
                return False
            if territory in self.under_construction:
                for plot_idx, entry in self.under_construction[territory].items():
                    if entry[0] == 'Training Grounds':
                        self.add_message("Already building Training Grounds in this territory!")
                        return False

        # Special rule: Only one Square allowed per territory
        if building_type == 'Square':
            if self.has_square(territory):
                self.add_message("Only one Square allowed per territory!")
                return False
            if territory in self.under_construction:
                for plot_idx, entry in self.under_construction[territory].items():
                    if entry[0] == 'Square':
                        self.add_message("Already building a Square in this territory!")
                        return False

        # Check if plot is empty
        if territory in self.buildings and plot_index in self.buildings[territory]:
            if self.buildings[territory][plot_index] is not None:
                return False  # Plot occupied

        # Check if already under construction
        if territory in self.under_construction and plot_index in self.under_construction[territory]:
            return False  # Already building something

        # Check if player has enough gold (with error handling)
        try:
            # Get effective cost with all discounts applied
            cost = self.get_building_cost(building_type, self.current_player)

            if self.player_gold[self.current_player] < cost:
                self.add_message("Not enough Resources!")
                return False
        except (KeyError, IndexError) as e:
            self.log_error(f"Failed to check building cost for {building_type}", e)
            return False

        # Deduct gold and track spending for recap screen
        self.player_gold[self.current_player] -= cost
        self._track_stat(self.current_player, 'gold_spent', cost)
        # Track building type at start time (not finish) so conquered buildings credit original builder
        if building_type in ('Farm', 'Mine', 'Square'):
            self._track_stat(self.current_player, 'economy_buildings_built')
        elif building_type in ('Barracks', 'Training Grounds'):
            self._track_stat(self.current_player, 'barracks_built')
        elif building_type == 'Keep':
            self._track_stat(self.current_player, 'keeps_built')

        # Determine construction time (Keep takes 2 turns, others take 1 turn)
        if building_type == 'Keep':
            turns_to_build = 2  # Completes at START of 2nd turn (4 total turns in 2P)
        else:
            turns_to_build = 1

        # Add to construction queue — H2 fix: store paid_cost for accurate refund on cancel
        if territory not in self.under_construction:
            self.under_construction[territory] = {}
        self.under_construction[territory][plot_index] = (building_type, turns_to_build, cost)

        # Mark this territory as having started construction this turn
        self.buildings_started_this_turn.add(territory)

        if turns_to_build > 1:
            self.add_message(f"Player {self.current_player + 1} started building {building_type} ({cost} gold, {turns_to_build} turns)")
        else:
            self.add_message(f"Player {self.current_player + 1} started building {building_type} ({cost} gold)")

        # Tutorial hook: notify that construction started
        if self.tutorial_mission:
            self.tutorial_mission.notify_event('build_started', building_type=building_type, territory=territory)

        return True

    # R11: get_building_xp_data() and award_building_xp() moved here from MilitaryMixin (military.py)
    # — they belong with building logic alongside _tick_building_xp()

    def get_building_xp_data(self, territory, plot_index):
        """Get building XP/level data, defaulting to {'xp': 0, 'level': 0}."""
        if territory in self.building_xp and plot_index in self.building_xp[territory]:
            return self.building_xp[territory][plot_index]
        return {'xp': 0, 'level': 0}

    def award_building_xp(self, territory, plot_index, amount):
        """Award XP to a building, auto-level-up. Returns new level."""
        if amount <= 0:
            return 0
        if territory not in self.building_xp:
            self.building_xp[territory] = {}
        if plot_index not in self.building_xp[territory]:
            self.building_xp[territory][plot_index] = {'xp': 0, 'level': 0}
        data = self.building_xp[territory][plot_index]
        data['xp'] += amount
        # Check for level-ups against cumulative thresholds
        current_level = data['level']
        while current_level < self.MAX_LEVEL:
            threshold = self.LEVEL_XP_CUMULATIVE[current_level]
            if data['xp'] >= threshold:
                current_level += 1
                data['level'] = current_level
            else:
                break
        return data['level']

    def _tick_building_xp(self):
        """Award XP to all Farms and Mines owned by the current player.
        Called at start of each player's turn. Skips newly completed buildings."""
        newly_completed = set()
        if hasattr(self, 'last_completed_buildings') and self.last_completed_buildings:
            # finish_constructions() returns (territory, building_type, plot_index) tuples
            for territory, building_type, plot_index in self.last_completed_buildings:
                newly_completed.add((territory, plot_index))

        xp_awarded_count = 0
        for territory, plots in self.buildings.items():
            if self.territory_owners.get(territory) != self.current_player:
                continue
            for plot_index, building_type in plots.items():
                if building_type in ('Farm', 'Mine'):
                    # Skip buildings that just finished construction this turn
                    if (territory, plot_index) in newly_completed:
                        logger.debug(f"Skipping newly completed {building_type} in {territory} plot {plot_index}")
                        continue
                    old_level = self.get_building_xp_data(territory, plot_index)['level']
                    new_level = self.award_building_xp(territory, plot_index, self.BUILDING_XP_PER_TURN)
                    xp_awarded_count += 1
                    logger.debug(f"  Awarded {self.BUILDING_XP_PER_TURN} XP to {building_type} in {territory} plot {plot_index} "
                                 f"(now: {self.get_building_xp_data(territory, plot_index)})")
                    if new_level > old_level:
                        self.add_message(f"  {building_type} in {territory} reached level {new_level}!")
        if xp_awarded_count > 0:
            logger.info(f"Building XP tick: +{self.BUILDING_XP_PER_TURN} XP to {xp_awarded_count} Farms/Mines for Player {self.current_player + 1}")
            self.add_message(f"  +{self.BUILDING_XP_PER_TURN} XP to {xp_awarded_count} building{'s' if xp_awarded_count > 1 else ''}")

    def _tick_training_grounds_xp(self):
        """Award XP to all units garrisoned in territories with Training Grounds.
        Called at start of each player's turn. Skips territories where
        Training Grounds just completed this turn (same pattern as building XP)."""
        # Identify territories where Training Grounds just finished construction
        newly_completed_territories = set()
        if hasattr(self, 'last_completed_buildings') and self.last_completed_buildings:
            for territory, building_type, plot_index in self.last_completed_buildings:
                if building_type == 'Training Grounds':
                    newly_completed_territories.add(territory)

        xp_amount = self.TRAINING_GROUNDS_UNIT_XP_PER_TURN
        territories_affected = 0
        total_units_trained = 0

        for territory, plots in self.buildings.items():
            if self.territory_owners.get(territory) != self.current_player:
                continue
            # Check if territory has a completed Training Grounds
            has_tg = any(bt == 'Training Grounds' for bt in plots.values() if bt is not None)
            if not has_tg:
                continue
            # Skip if Training Grounds just completed this turn
            if territory in newly_completed_territories:
                logger.debug(f"Skipping newly completed Training Grounds in {territory}")
                continue

            # Award XP to all units in this territory's garrison
            garrison = self.territory_garrisons.get(territory, {})
            player_garrison = garrison.get(self.current_player)
            if not player_garrison:
                continue
            units = player_garrison.get('units', [])
            if not units:
                continue

            for unit in units:
                self.award_unit_xp(unit, xp_amount)
            territories_affected += 1
            total_units_trained += len(units)

        if territories_affected > 0:
            logger.info(f"Training Grounds XP tick: +{xp_amount} XP to {total_units_trained} units "
                        f"in {territories_affected} territor{'ies' if territories_affected > 1 else 'y'} "
                        f"for Player {self.current_player + 1}")
            self.add_message(f"  Training Grounds: +{xp_amount} XP to {total_units_trained} unit{'s' if total_units_trained > 1 else ''} "
                             f"in {territories_affected} territor{'ies' if territories_affected > 1 else 'y'}")

    def finish_constructions(self):
        """Finish all buildings that completed this turn (only counts owner's turns)"""
        completed = []

        for territory in list(self.under_construction.keys()):
            # Only count turns for buildings owned by current player
            if self.territory_owners[territory] != self.current_player:
                continue

            for plot_index in list(self.under_construction[territory].keys()):
                # H2 fix: entries are now (building_type, turns, paid_cost) 3-tuples
                entry = self.under_construction[territory][plot_index]
                building_type, turns_remaining = entry[0], entry[1]
                paid_cost = entry[2] if len(entry) == 3 else 0

                # Decrease turns remaining (only on owner's turn)
                turns_remaining -= 1

                if turns_remaining <= 0:
                    # Construction complete!
                    if territory not in self.buildings:
                        self.buildings[territory] = {}
                    self.buildings[territory][plot_index] = building_type

                    # Remove from construction queue
                    del self.under_construction[territory][plot_index]
                    if not self.under_construction[territory]:
                        del self.under_construction[territory]

                    completed.append((territory, building_type, plot_index))
                else:
                    # Update turns remaining — preserve paid_cost
                    self.under_construction[territory][plot_index] = (building_type, turns_remaining, paid_cost)

        # Add messages for completed buildings (stats tracked at start_construction time)
        for territory, building_type, plot_index in completed:
            owner = self.territory_owners[territory]
            self.add_message(f"Player {owner + 1}: {building_type} completed in {territory}")
            # Player Level: award XP for completing a building
            self._track_stat(owner, 'xp_earned', 2)
            # Game logger: record individual building type (Farm, Mine, Square, etc.)
            if self.game_logger:
                self.game_logger.record_building_completed(owner, building_type, territory, self.turn_number)

        # FPS OPT: Buildings affect income — invalidate cache for owners of completed buildings
        if completed:
            affected_players = set()
            for territory, building_type, plot_index in completed:
                owner = self.territory_owners.get(territory, -1)
                if owner >= 0:
                    affected_players.add(owner)
            for p in affected_players:
                self.invalidate_income_cache(p)

        # Return completed buildings for network synchronization
        return completed

    def cancel_construction(self, territory, plot_index):
        """Cancel construction and refund 100%"""
        if territory not in self.under_construction:
            return False

        if plot_index not in self.under_construction[territory]:
            return False

        # H2 fix: use stored paid_cost for accurate refund
        entry = self.under_construction[territory][plot_index]
        building_type = entry[0]
        owner = self.territory_owners[territory]

        if len(entry) == 3:
            cost = entry[2]  # paid_cost stored at construction time
        else:
            # Backwards compat: old format without paid_cost
            cost = self.get_building_cost(building_type, owner)

        # Refund 100% of what was actually paid
        self.player_gold[owner] += cost

        # Remove from construction
        del self.under_construction[territory][plot_index]
        if not self.under_construction[territory]:
            del self.under_construction[territory]

        # Allow building again on this territory this turn (since we canceled)
        self.buildings_started_this_turn.discard(territory)

        self.add_message(f"Construction canceled, {cost} gold refunded")
        return True

    def destroy_building(self, territory, plot_index):
        """Destroy completed building and refund 50%"""
        if territory not in self.buildings:
            return False

        if plot_index not in self.buildings[territory]:
            return False

        if self.buildings[territory][plot_index] is None:
            return False  # No building here

        building_type = self.buildings[territory][plot_index]
        owner = self.territory_owners[territory]

        # Get effective cost with all discounts applied (what was actually paid)
        cost = self.get_building_cost(building_type, owner)

        # Add upgrade cost if this is a Castle
        if building_type == 'Keep' and self.is_castle(territory, plot_index):
            cost += 150  # Castle upgrade cost

        # Calculate refund based on building type
        if building_type == 'Barracks' and self.player_barracks_full_refund[owner]:
            # Makeshift Barracks: 100% refund
            refund = cost
        elif building_type in ['Farm', 'Mine'] and self.player_has_silvyr(owner):
            # Confiscate (Erec Silvyr): 175% refund for Farms and Mines
            refund = int(cost * 1.75)
        else:
            # Standard refund: 50%
            refund = cost // 2

        # Refund gold
        self.player_gold[owner] += refund

        # Remove building (delete the entry, don't set to None)
        del self.buildings[territory][plot_index]

        # Veterancy: Remove building XP data for demolished building
        if territory in self.building_xp and plot_index in self.building_xp[territory]:
            del self.building_xp[territory][plot_index]
            if not self.building_xp[territory]:
                del self.building_xp[territory]

        # If this was a Barracks, clear its training queue (no refund)
        if building_type == 'Barracks':
            self.clear_training_queue(territory, plot_index)

        # If this was a Keep, kill heroes and cancel training (no refund)
        if building_type == 'Keep':
            # Kill heroes in this Keep
            self.kill_heroes_in_keep(territory, plot_index, owner)

            # Cancel hero training (no refund on demolish)
            if (territory in self.hero_training_queue and
                plot_index in self.hero_training_queue[territory]):
                # C1 fix: handle 3-tuple (hero_type, time, paid_cost) from Audit #3 H1
                entry = self.hero_training_queue[territory][plot_index]
                hero_type = entry[0]
                del self.hero_training_queue[territory][plot_index]
                if not self.hero_training_queue[territory]:
                    del self.hero_training_queue[territory]
                self.hero_ownership[owner].discard(hero_type)
                self.add_message("Hero training cancelled (Keep demolished)")

            # Clean up Castle tracking
            if self.is_castle(territory, plot_index):
                del self.castle_upgrades[territory][plot_index]
                if not self.castle_upgrades[territory]:
                    del self.castle_upgrades[territory]

            # Clean up Castle upgrade in progress
            if self.is_upgrading_to_castle(territory, plot_index):
                del self.castle_upgrades_in_progress[territory][plot_index]
                if not self.castle_upgrades_in_progress[territory]:
                    del self.castle_upgrades_in_progress[territory]

        # Note: Demolishing does NOT consume your building slot
        # You can still build one building this turn if you haven't already

        self.add_message(f"{building_type} destroyed, {refund} gold refunded")
        return True

    def has_barracks(self, territory):
        """Check if territory has a completed Barracks building and return plot indices"""
        barracks_plots = []
        if territory not in self.buildings:
            return barracks_plots

        for plot_index, building_type in self.buildings[territory].items():
            if building_type == 'Barracks':
                barracks_plots.append(plot_index)
        return barracks_plots

    # ── Unit Training ───────────────────────────────────────────────

    def start_training(self, territory, barracks_plot_index, unit_type='Swordsman'):
        """Start training a unit at a specific Barracks"""
        # Tutorial hook: check if training action is allowed
        if self.tutorial_mission and not self.tutorial_mission.is_action_allowed(
                'train', unit_type=unit_type, territory=territory):
            return False

        # Validate unit type (with error handling)
        if unit_type not in self.UNIT_TYPES:
            self.add_message(f"Invalid unit type: {unit_type}")
            self.log_error(f"Invalid unit type: {unit_type}")
            return False

        # Check ownership (with error handling)
        try:
            if self.territory_owners.get(territory, -1) != self.current_player:
                self.add_message("You don't own this territory!")
                return False
        except Exception as e:
            self.log_error(f"Failed to check territory ownership for {territory}", e)
            return False

        # Check if this is actually a Barracks (with error handling)
        try:
            if territory not in self.buildings or barracks_plot_index not in self.buildings[territory]:
                return False
            if self.buildings[territory][barracks_plot_index] != 'Barracks':
                self.add_message("This is not a Barracks!")
                return False
        except Exception as e:
            self.log_error(f"Failed to check Barracks in {territory}[{barracks_plot_index}]", e)
            return False

        # Check army limit - prevent training if at max
        # M1 fix: use get_territory_total_armies to include allied garrisons
        current_armies = self.get_territory_total_armies(territory)
        if current_armies >= self.MAX_ARMIES_PER_TERRITORY:
            self.add_message(f"Army limit reached in {territory}! (Max {self.MAX_ARMIES_PER_TERRITORY} per territory)")
            return False

        # Check command limit - prevent training if at max
        current_command = self.get_player_army_count(self.current_player)
        command_limit = self.player_command_limit[self.current_player]
        if current_command >= command_limit:
            self.add_message(f"Command limit reached! ({current_command}/{command_limit})")
            return False

        # Initialize training queue for this Barracks if needed
        if territory not in self.training_queue:
            self.training_queue[territory] = {}
        if barracks_plot_index not in self.training_queue[territory]:
            self.training_queue[territory][barracks_plot_index] = []

        # Check queue limit (4 units per Barracks)
        if len(self.training_queue[territory][barracks_plot_index]) >= 4:
            self.add_message("Training queue full! (Max 4 per Barracks)")
            return False

        # Get unit cost based on type (with error handling)
        try:
            base_cost = self.UNIT_TYPES[unit_type]['cost']
            unit_cost = self.get_effective_cost(unit_type, base_cost, self.current_player)
            if self.player_gold[self.current_player] < unit_cost:
                self.add_message(f"Not enough gold to train {unit_type}! (Need {unit_cost} gold)")
                return False
        except (KeyError, IndexError) as e:
            self.log_error(f"Failed to get unit cost for {unit_type}", e)
            return False

        # Deduct gold and track spending/units for recap screen
        self.player_gold[self.current_player] -= unit_cost
        self._track_stat(self.current_player, 'gold_spent', unit_cost)
        # Track at start time so conquered territories don't credit new owner
        self._track_stat(self.current_player, 'units_trained')
        # Track per-unit-type training for achievements
        _unit_stat_map = {'Pikeman': 'pikemen_trained', 'Archer': 'archers_trained',
                          'Swordsman': 'swordsmen_trained', 'Cavalry': 'cavalry_trained',
                          'Captain': 'captains_trained'}
        if unit_type in _unit_stat_map:
            self._track_stat(self.current_player, _unit_stat_map[unit_type])

        # Add to queue (unit_type, turns_remaining, cost_paid)
        # M1 fix: Store actual cost paid so cancel_training refunds the correct amount
        # (bonuses may change between training start and cancellation)
        self.training_queue[territory][barracks_plot_index].append((unit_type, 1, unit_cost))

        self.add_message(f"Player {self.current_player + 1} started training {unit_type} in {territory} ({unit_cost} gold, 1 turn)")
        # FPS OPT: Training affects army count and production glow
        self.invalidate_army_count_cache(self.current_player)
        self._training_version += 1

        # Tutorial hook: notify that training started
        if self.tutorial_mission:
            self.tutorial_mission.notify_event('train_started', unit_type=unit_type, territory=territory)

        return True

    def cancel_training(self, territory, barracks_plot_index, queue_index):
        """Cancel training in queue for full refund"""
        if territory not in self.training_queue:
            return False
        if barracks_plot_index not in self.training_queue[territory]:
            return False
        if queue_index >= len(self.training_queue[territory][barracks_plot_index]):
            return False

        # Get unit info — queue entries are (unit_type, turns_remaining, cost_paid)
        # M1 fix: Use stored cost_paid for accurate refund (bonuses may have changed
        # since training started). Fall back to recalculating if legacy tuple format.
        entry = self.training_queue[territory][barracks_plot_index][queue_index]
        owner = self.territory_owners[territory]
        if len(entry) >= 3:
            unit_type, turns_remaining, unit_cost = entry
        else:
            unit_type, turns_remaining = entry[:2]
            base_cost = self.UNIT_TYPES.get(unit_type, {}).get('cost', 25)
            unit_cost = self.get_effective_cost(unit_type, base_cost, owner)

        # Refund gold
        self.player_gold[owner] += unit_cost

        # Remove from queue
        self.training_queue[territory][barracks_plot_index].pop(queue_index)

        # Clean up empty structures
        if not self.training_queue[territory][barracks_plot_index]:
            del self.training_queue[territory][barracks_plot_index]
        if not self.training_queue[territory]:
            del self.training_queue[territory]

        self.add_message(f"Training canceled, {unit_cost} gold refunded")
        self._training_version += 1  # FPS OPT: Production glow sync
        return True

    def clear_training_queue(self, territory, barracks_plot_index=None):
        """Clear training queue (no refund) when Barracks is destroyed"""
        if territory not in self.training_queue:
            return

        if barracks_plot_index is not None:
            # Clear specific Barracks queue
            if barracks_plot_index in self.training_queue[territory]:
                del self.training_queue[territory][barracks_plot_index]
                if not self.training_queue[territory]:
                    del self.training_queue[territory]
        else:
            # Clear all queues in territory
            del self.training_queue[territory]

    def finish_training(self):
        """Complete training for units that are done (called at start of current player's turn)"""
        if not hasattr(self, 'training_queue'):
            self.training_queue = {}
            return

        # Track completed units for network synchronization
        completed_units = []

        territories_to_remove = []

        for territory, barracks_dict in list(self.training_queue.items()):
            # Only process territories owned by current player
            owner = self.territory_owners.get(territory, -1)
            if owner != self.current_player:
                continue  # Skip territories not owned by current player

            barracks_to_remove = []

            for barracks_plot_index, queue in list(barracks_dict.items()):
                # Verify barracks still exists (not destroyed)
                barracks_exists = (territory in self.buildings and
                                  barracks_plot_index in self.buildings[territory] and
                                  self.buildings[territory][barracks_plot_index] == 'Barracks')

                if not barracks_exists:
                    # Barracks was destroyed, clear queue (no refund)
                    barracks_to_remove.append(barracks_plot_index)
                    continue

                # Process first unit in queue
                # M1 fix: entries are (unit_type, turns_remaining[, cost_paid])
                if queue:
                    unit_type = queue[0][0]
                    turns_remaining = queue[0][1] - 1
                    cost_paid = queue[0][2] if len(queue[0]) >= 3 else None

                    if turns_remaining <= 0:
                        # Check army limit before spawning
                        # M2 fix: use get_territory_total_armies to include allied garrisons
                        current_armies = self.get_territory_total_armies(territory)
                        if current_armies >= self.MAX_ARMIES_PER_TERRITORY:
                            # At army limit - pause training (don't spawn, don't remove from queue)
                            self.add_message(f"{territory}: Training paused - army limit reached ({self.MAX_ARMIES_PER_TERRITORY}/{self.MAX_ARMIES_PER_TERRITORY})")
                            # Keep unit in queue with 0 turns (will check again next turn)
                            queue[0] = (unit_type, 0) if cost_paid is None else (unit_type, 0, cost_paid)
                            continue  # Skip to next Barracks

                        # Training complete! Spawn unit
                        # Check if territory is affected by Haste ability
                        haste_affected_territories = self.get_haste_affected_territories(owner)
                        has_haste = territory in haste_affected_territories

                        # Add army as "moved" (can't move this turn) or "unmoved" if Haste is active
                        if has_haste:
                            self.armies_unmoved[territory] += 1
                        else:
                            self.armies_moved[territory] += 1
                        self.armies[territory] = self.armies_moved[territory] + self.armies_unmoved[territory]

                        # Add unit to army_units with correct type
                        if territory not in self.army_units:
                            self.army_units[territory] = []

                        # Find next available ID using garrison system (authoritative)
                        # army_units (legacy) can have stale IDs after execute_all_orders() reassignment
                        garrison_data = self.territory_garrisons.get(territory, {}).get(owner, {})
                        garrison_units = garrison_data.get('units', []) if garrison_data else []
                        existing_ids = [u['id'] for u in garrison_units] if garrison_units else [u['id'] for u in self.army_units[territory]]
                        next_id = 0
                        while next_id in existing_ids:
                            next_id += 1

                        # Add the new unit with its specific type (freshly trained, no XP)
                        # Haste makes units ready immediately, otherwise they're moved (exhausted)
                        # Phase 2E: Use _make_unit() factory for consistent unit dict creation
                        new_unit = self._make_unit(unit_type, next_id, 'ready' if has_haste else 'moved')
                        self.army_units[territory].append(new_unit)

                        # Update garrison system
                        if owner in self.territory_garrisons.get(territory, {}):
                            # Owner already has a garrison - add unit to it
                            garrison = self.territory_garrisons[territory][owner]
                            if 'units' not in garrison:
                                garrison['units'] = []
                            garrison['units'].append(new_unit.copy())
                            if has_haste:
                                garrison['unmoved'] = garrison.get('unmoved', 0) + 1
                            else:
                                garrison['moved'] = garrison.get('moved', 0) + 1
                        else:
                            # Create new garrison for owner
                            self.add_garrison(
                                territory, owner,
                                unmoved=1 if has_haste else 0,
                                moved=0 if has_haste else 1,
                                units=[new_unit.copy()]
                            )

                        # M2 fix: Sync legacy garrison data after updating garrison system
                        self.sync_legacy_garrison_data(territory)

                        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
                        self.add_message(f"Player {owner + 1}: {unit_type} trained in {territory}{haste_msg}")

                        # Player Level: award XP for training a unit
                        self._track_stat(owner, 'xp_earned', 2)

                        # Track for network sync
                        completed_units.append({
                            'territory': territory,
                            'unit_type': unit_type,
                            'has_haste': has_haste,
                            'unit_id': next_id
                        })

                        # Remove from queue
                        queue.pop(0)

                        # Update remaining items in queue (decrement their timers too if needed)
                        # Actually, only first item trains, others wait
                    else:
                        # Update timer (preserve cost_paid if stored)
                        queue[0] = (unit_type, turns_remaining) if cost_paid is None else (unit_type, turns_remaining, cost_paid)

                # Clean up empty queue
                if not queue:
                    barracks_to_remove.append(barracks_plot_index)

            for barracks_plot_index in barracks_to_remove:
                del barracks_dict[barracks_plot_index]

            if not barracks_dict:
                territories_to_remove.append(territory)

        for territory in territories_to_remove:
            del self.training_queue[territory]

        # FPS OPT: Training affects army counts and production glow
        if completed_units:
            self.invalidate_army_count_cache(self.current_player)
            self._training_version += 1

        # Return completed units for network synchronization
        return completed_units

    # ── Castle Upgrades ─────────────────────────────────────────────

    def start_castle_upgrade(self, territory, keep_plot_index):
        """
        Start upgrading a Keep to Castle.

        Rules:
        - Costs 150 gold
        - Takes 2 turns
        - Keep retains all functionality during upgrade
        - Cannot upgrade while hero is training
        - 100% refund on cancellation
        """
        UPGRADE_COST = 150
        UPGRADE_TIME = 2

        # 1. Check ownership
        if self.territory_owners.get(territory, -1) != self.current_player:
            self.add_message("You don't own this territory!")
            return False

        # 2. Verify this is a Keep
        if (territory not in self.buildings or
            keep_plot_index not in self.buildings[territory] or
            self.buildings[territory][keep_plot_index] != 'Keep'):
            self.add_message("This is not a Keep!")
            return False

        # 3. Check if already a Castle
        if self.is_castle(territory, keep_plot_index):
            self.add_message("This Keep is already a Castle!")
            return False

        # 4. Check if already upgrading
        if self.is_upgrading_to_castle(territory, keep_plot_index):
            self.add_message("This Keep is already being upgraded!")
            return False

        # 5. Check if hero is training (CANNOT upgrade during training)
        if (territory in self.hero_training_queue and
            keep_plot_index in self.hero_training_queue[territory]):
            self.add_message("Cannot upgrade while hero is training!")
            return False

        # 6. Check gold
        if self.player_gold[self.current_player] < UPGRADE_COST:
            self.add_message(f"Not enough gold! (Need {UPGRADE_COST})")
            return False

        # 7. Deduct gold and track spending for recap screen
        self.player_gold[self.current_player] -= UPGRADE_COST
        self._track_stat(self.current_player, 'gold_spent', UPGRADE_COST)

        # 8. Add to upgrade tracking
        if territory not in self.castle_upgrades_in_progress:
            self.castle_upgrades_in_progress[territory] = {}
        self.castle_upgrades_in_progress[territory][keep_plot_index] = UPGRADE_TIME

        self.add_message(f"Upgrading Keep to Castle ({UPGRADE_COST} gold, {UPGRADE_TIME} turns)")
        return True

    def cancel_castle_upgrade(self, territory, keep_plot_index):
        """Cancel Castle upgrade with 100% refund (150 gold)"""
        UPGRADE_COST = 150

        # 1. Validate upgrade exists
        if (territory not in self.castle_upgrades_in_progress or
            keep_plot_index not in self.castle_upgrades_in_progress[territory]):
            return False

        # 2. Get owner
        owner = self.territory_owners[territory]

        # 3. 100% refund
        self.player_gold[owner] += UPGRADE_COST

        # 4. Remove from upgrade tracking
        del self.castle_upgrades_in_progress[territory][keep_plot_index]
        if not self.castle_upgrades_in_progress[territory]:
            del self.castle_upgrades_in_progress[territory]

        self.add_message(f"Castle upgrade cancelled, {UPGRADE_COST} gold refunded (100%)")
        return True

    def finish_castle_upgrades(self):
        """Complete Castle upgrades (called at start of player's turn)"""
        completed = []
        completed_with_plots = []  # Store (territory, plot_index) tuples for effects

        for territory in list(self.castle_upgrades_in_progress.keys()):
            # Only count turns for upgrades owned by current player
            if self.territory_owners.get(territory, -1) != self.current_player:
                continue

            for plot_index in list(self.castle_upgrades_in_progress[territory].keys()):
                turns_remaining = self.castle_upgrades_in_progress[territory][plot_index]

                # Verify Keep still exists
                keep_exists = (territory in self.buildings and
                              plot_index in self.buildings[territory] and
                              self.buildings[territory][plot_index] == 'Keep')

                if not keep_exists:
                    # Keep destroyed - lose upgrade progress (no refund)
                    del self.castle_upgrades_in_progress[territory][plot_index]
                    if not self.castle_upgrades_in_progress[territory]:
                        del self.castle_upgrades_in_progress[territory]
                    continue

                # Decrease turns remaining
                turns_remaining -= 1

                if turns_remaining <= 0:
                    # Upgrade complete!
                    if territory not in self.castle_upgrades:
                        self.castle_upgrades[territory] = {}
                    self.castle_upgrades[territory][plot_index] = True

                    # Remove from in-progress tracking
                    del self.castle_upgrades_in_progress[territory][plot_index]
                    if not self.castle_upgrades_in_progress[territory]:
                        del self.castle_upgrades_in_progress[territory]

                    completed.append(territory)
                    completed_with_plots.append((territory, plot_index))
                else:
                    # Update turns remaining
                    self.castle_upgrades_in_progress[territory][plot_index] = turns_remaining

        # Add messages for completed upgrades
        for territory in completed:
            owner = self.territory_owners[territory]
            self.add_message(f"Player {owner + 1}: Castle upgrade complete in {territory}!")

        # Play castle completion sound for human player only (if any castles completed)
        if completed:
            owner = self.territory_owners[completed[0]]  # Get owner of first completed castle
            # FIX: Check if owner is human (not AI) - sounds should never play for AI actions
            should_play_sound = not self.player_is_ai[owner]
            if self.network_mode and should_play_sound:
                # Additional check: only play if this is the local player's castle
                should_play_sound = (owner == self.local_player_index)

            if should_play_sound:
                from global_sound import play_castle_complete_sound, sound_manager
                # Check if a sound is currently playing (likely research completion)
                is_sound_playing = any(
                    channel and channel.get_busy()
                    for channel in sound_manager.currently_playing.values()
                )
                # Queue if something is playing, otherwise play immediately
                play_castle_complete_sound(use_queue=is_sound_playing)

        # Sync fix: store completed castle upgrades for network notifications
        self.last_completed_castle_upgrades = completed_with_plots

        # Trigger visual effects for completed upgrades
        if self.map_renderer:
            for territory, plot_index in completed_with_plots:
                self.map_renderer.trigger_castle_upgrade_effect(territory, plot_index)

    # ── Technology Research ──────────────────────────────────────────

    def start_research(self, tech_id):
        """
        Start research on a technology.

        Requirements:
        - Technology must be available (not locked)
        - Technology must not be already researched
        - No other research can be in progress
        - Player must have enough gold

        Args:
            tech_id: The technology ID to research

        Returns:
            bool: True if research started successfully, False otherwise
        """
        # Find the technology
        tech = None
        for t in self.technologies:
            if t['id'] == tech_id:
                tech = t
                break

        if not tech:
            self.add_message("Technology not found!")
            return False

        # Check if technology is available (per-player)
        if tech_id not in self.player_tech_available[self.current_player]:
            self.add_message(f"{tech['name']} is locked!")
            return False

        # Check if already researched (per-player)
        if tech_id in self.player_tech_researched[self.current_player]:
            self.add_message(f"{tech['name']} is already researched!")
            return False

        # Check if another research is in progress
        if self.current_player in self.research_in_progress:
            current_research = self.research_in_progress[self.current_player]
            # Find the tech name for the message
            for t in self.technologies:
                if t['id'] == current_research['tech_id']:
                    self.add_message(f"Already researching {t['name']}!")
                    break
            return False

        # Check special requirements (e.g., Castle requirement)
        if tech.get('requires_castle', False):
            if not self.player_has_castle(self.current_player):
                self.add_message(f"{tech['name']} requires a Castle!")
                return False

        # Check cost (apply hero modifiers and territorial bonuses)
        base_cost = tech.get('cost', 0)
        cost = self.get_effective_tech_cost(base_cost, self.current_player)

        if cost > 0:
            if self.player_gold[self.current_player] < cost:
                self.add_message(f"Not enough gold! (Need {cost})")
                return False

            # Deduct cost and track spending for recap screen
            self.player_gold[self.current_player] -= cost
            self._track_stat(self.current_player, 'gold_spent', cost)

        # Start research
        turns = tech.get('turns', 1)

        # Apply Ruthless Ingenuity (Erec Silvyr): -1 turn (minimum 1)
        if self.player_has_silvyr(self.current_player):
            turns = max(1, turns - 1)
        # M2 fix: Store cost_paid so cancel_research refunds exact amount paid
        self.research_in_progress[self.current_player] = {
            'tech_id': tech_id,
            'turns_remaining': turns,
            'cost_paid': cost
        }

        self.add_message(f"Started research: {tech['name']} ({cost} gold, {turns} turns)")

        # Tutorial hook: notify research started
        if self.tutorial_mission:
            self.tutorial_mission.notify_event('research_started', tech_id=tech_id)

        return True

    def cancel_research(self, player_id=None):
        """
        Cancel research in progress with full refund.

        Args:
            player_id: The player whose research to cancel (defaults to current_player)

        Returns:
            bool: True if research was cancelled, False if no research in progress
        """
        if player_id is None:
            player_id = self.current_player

        # Check if research is in progress
        if player_id not in self.research_in_progress:
            self.add_message("No research in progress!")
            return False

        # Get the research info
        research = self.research_in_progress[player_id]
        tech_id = research['tech_id']

        # Look up tech name for message
        tech = None
        for t in self.technologies:
            if t['id'] == tech_id:
                tech = t
                break
        tech_name = tech['name'] if tech else tech_id

        # M2 fix: Use stored cost_paid for accurate refund (bonuses may have changed).
        # Fall back to recalculating if legacy format without cost_paid.
        cost = research.get('cost_paid')
        if cost is None:
            if not tech:
                return False
            base_cost = tech.get('cost', 0)
            cost = self.get_effective_tech_cost(base_cost, player_id)

        if cost > 0:
            self.player_gold[player_id] += cost

        # Remove from research tracking
        del self.research_in_progress[player_id]

        self.add_message(f"Research cancelled: {tech_name}, {cost} gold refunded (100%)")
        return True

    def finish_research(self):
        """
        Complete research (called at start of player's turn).
        Similar to finish_castle_upgrades.
        """
        # Check if current player has research in progress
        if self.current_player not in self.research_in_progress:
            return

        research = self.research_in_progress[self.current_player]
        tech_id = research['tech_id']
        turns_remaining = research['turns_remaining']

        # Decrease turns remaining
        turns_remaining -= 1

        if turns_remaining <= 0:
            # Research complete!
            # Find the technology
            tech = None
            for t in self.technologies:
                if t['id'] == tech_id:
                    tech = t
                    break

            if tech:
                # Mark as researched (per-player)
                self.player_tech_researched[self.current_player].add(tech_id)

                # Player Level: award XP for completing technology research
                self._track_stat(self.current_player, 'xp_earned', 4)

                # Game logger: record tech research completion event
                if self.game_logger:
                    self.game_logger.record_tech_researched(self.current_player, tech_id, self.turn_number)

                # Remove from available (already researched)
                self.player_tech_available[self.current_player].discard(tech_id)

                # Apply the effect
                effect_type = tech.get('effect_type')
                effect_value = tech.get('effect_value')

                if effect_type == 'time_limit' and effect_value:
                    # Increase planning time limit
                    self.player_planning_time_limit[self.current_player] += effect_value
                    self.add_message(f"Research complete: {tech['name']}! Planning time increased by {effect_value}s")
                elif effect_type == 'command_limit' and effect_value:
                    # Increase command limit
                    self.player_command_limit[self.current_player] += effect_value
                    new_limit = self.player_command_limit[self.current_player]
                    self.add_message(f"Research complete: {tech['name']}! Command limit increased to {new_limit}")
                elif effect_type == 'cost_reduction' and effect_value:
                    # Apply cost reduction for Heroes and Keeps
                    self.player_royal_decree_discount[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Hero and Keep costs reduced by {effect_value}%")
                elif effect_type == 'unit_cost_reduction' and effect_value:
                    # Apply cost reduction for Swordsmen and Pikemen
                    self.player_training_cost_discount[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Swordsman and Pikeman costs reduced by {effect_value}%")
                elif effect_type == 'cavalry_cost_reduction' and effect_value:
                    # Apply cost reduction for Cavalry
                    self.player_cavalry_cost_discount[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Cavalry cost reduced by {effect_value}%")
                elif effect_type == 'archer_keep_strength' and effect_value:
                    # Apply strength bonus for Archers in territories with friendly Keep/Castle
                    self.player_archer_keep_strength_bonus[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Archers gain +{effect_value}% strength in territories with friendly Keep/Castle")
                elif effect_type == 'farm_destruction_bonus' and effect_value:
                    # Apply gold bonus for destroying enemy Farms
                    self.player_farm_destruction_gold_bonus[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Gain {effect_value} Gold whenever you destroy an enemy Farm")
                elif effect_type == 'cavalry_strength_bonus' and effect_value:
                    # Apply strength bonus for Cavalry units
                    self.player_cavalry_strength_bonus[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Cavalry units gain +{effect_value}% strength")
                elif effect_type == 'keep_siege_bonus' and effect_value:
                    # Enable Divide and Conquer bonus for attacking Keeps
                    self.player_divide_conquer_bonus[self.current_player] = True
                    self.add_message(f"Research complete: {tech['name']}! Pikemen/Swordsmen +20% strength, Archers +50% in Keep Phase 2")
                elif effect_type == 'barracks_upgrade' and effect_value:
                    # Apply cost reduction for Barracks and enable full refund on demolish
                    self.player_barracks_cost_discount[self.current_player] = effect_value
                    self.player_barracks_full_refund[self.current_player] = True
                    self.add_message(f"Research complete: {tech['name']}! Barracks cost reduced by {effect_value}%, demolish returns 100%")
                elif effect_type == 'hero_limit' and effect_value:
                    # Set hero limit to the new value + Captain cost discount (Heroic Fortitude)
                    self.player_hero_limit[self.current_player] = effect_value
                    self.player_captain_cost_discount[self.current_player] = 33  # 75g → 50g
                    self.add_message(f"Research complete: {tech['name']}! Hero limit increased to {effect_value}. Captain cost reduced to 50g.")
                elif effect_type == 'hero_keep_defense' and effect_value:
                    # Set hero keep defense bonus
                    self.player_hero_keep_defense_bonus[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Keeps/Castles with heroes gain +{effect_value} defense bonus")
                else:
                    self.add_message(f"Research complete: {tech['name']}!")

                # Play research completion sound for human player only
                # FIX: Check if current player is human (not AI) - sounds should never play for AI actions
                should_play_sound = not self.player_is_ai[self.current_player]
                if self.network_mode and should_play_sound:
                    # Multiplayer: only play if this is the local player's research
                    should_play_sound = (self.current_player == self.local_player_index)

                if should_play_sound:
                    from global_sound import play_research_complete_sound
                    play_research_complete_sound(use_queue=False)

                # Unlock next technology in the same column (per-player)
                next_row = tech['row'] + 1
                if next_row < 7:  # Max 7 rows
                    next_tech_id = f"tech_{tech['column']}_{next_row}"
                    self.player_tech_available[self.current_player].add(next_tech_id)

            # Remove from research tracking
            del self.research_in_progress[self.current_player]
            # FPS OPT: Tech affects income (e.g. Laws of Trade) — invalidate cache
            self.invalidate_income_cache(self.current_player)
        else:
            # Update turns remaining
            self.research_in_progress[self.current_player]['turns_remaining'] = turns_remaining
