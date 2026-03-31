# game_state/military.py
# Military mixin for GameState (Phase 7 decomposition)

"""
Military system: army management, movement orders, battle resolution.

Provides methods for army selection, movement orders, unit composition,
battle resolution, and processing of army arrivals after movement.
"""

import random
import time
import math
import map_data
from utils.logger import get_logger
from game_state.data_definitions import OVERWHELMING_ADVANTAGE_RATIO

logger = get_logger(__name__)


class MilitaryMixin:
    """Mixin providing military and combat methods for GameState."""

    def get_player_army_count(self, player_index):
        """
        Get total number of armies controlled by a player across the entire map.
        This includes armies in territories and armies in training.

        FPS OPT: Cached with dirty-flag + 30-frame periodic fallback.
        Called every frame from draw_top_panel(); without caching iterates all 57 territories.
        """
        # FPS OPT: Lazy init cache structures
        if not hasattr(self, '_army_count_cache'):
            self._army_count_cache = {}
            self._army_count_dirty = set()
            self._army_count_frame = {}
            self._army_count_frame_counter = 0

        self._army_count_frame_counter += 1

        # Return cached value if clean and within 30-frame safety window
        if (player_index in self._army_count_cache and
                player_index not in self._army_count_dirty and
                self._army_count_frame_counter - self._army_count_frame.get(player_index, 0) < 30):
            return self._army_count_cache[player_index]

        # Cache miss or dirty — recompute
        self._army_count_dirty.discard(player_index)
        total = 0

        for territory, owner in self.territory_owners.items():
            if owner == player_index:
                total += self.armies.get(territory, 0)

        for territory, training_data in self.training_queue.items():
            if self.territory_owners.get(territory, -1) == player_index:
                for unit_type, turns_left in training_data.items():
                    total += len(turns_left)

        self._army_count_cache[player_index] = total
        self._army_count_frame[player_index] = self._army_count_frame_counter
        return total

    def invalidate_army_count_cache(self, player_index=None):
        """FPS OPT: Mark army count cache dirty. Call on army add/remove/train/kill."""
        if not hasattr(self, '_army_count_dirty'):
            return
        if player_index is None:
            self._army_count_dirty = set(range(self.num_players))
        else:
            self._army_count_dirty.add(player_index)

    def select_army(self, territory):
        """Select an army for issuing movement orders"""
        # Check if current player has a garrison in this territory (can be allied territory)
        garrison = self.territory_garrisons.get(territory, {}).get(self.current_player)

        if not garrison or garrison.get('unmoved', 0) <= 0:
            self.add_message("No armies available to move in this territory")
            return False

        # Select the army (works for own territory OR allied territory with garrison)
        army_count = garrison['unmoved']
        self.selected_army = (territory, army_count)
        return True

    def deselect_army(self):
        """Deselect the currently selected army"""
        self.selected_army = None

    def get_unit_composition(self, territory):
        """
        Get the composition of units in a territory across ALL garrisons.
        Returns dict: {unit_type: count}
        Example: {'Swordsman': 3, 'Archer': 2, 'Cavalry': 1}
        """
        # IMPORTANT: Gather units from ALL garrisons (multi-garrison support)
        all_units = []
        total_garrison_count = 0
        garrisons = self.territory_garrisons.get(territory, {})

        for player_index, garrison_data in garrisons.items():
            units = garrison_data.get('units', [])
            garrison_count = garrison_data.get('unmoved', 0) + garrison_data.get('moved', 0)
            total_garrison_count += garrison_count
            all_units.extend(units)

        # VALIDATION: Check if unit count matches garrison counts
        unit_list_count = len(all_units)
        if unit_list_count != total_garrison_count:
            logger.warning(f"[TOOLTIP MISMATCH] {territory}: "
                  f"Unit list has {unit_list_count} units but garrison counts show {total_garrison_count}")

            # Fix the mismatch by truncating unit list to match garrison count
            if unit_list_count > total_garrison_count:
                logger.warning(f"[TOOLTIP MISMATCH] Truncating unit list from {unit_list_count} to {total_garrison_count}")
                all_units = all_units[:total_garrison_count]

        composition = {}
        for unit in all_units:
            unit_type = unit.get('type', 'Swordsman')
            composition[unit_type] = composition.get(unit_type, 0) + 1

        return composition

    # --- Veterancy/Experience helper methods ---

    def award_unit_xp(self, unit, amount):
        """Award XP to a unit dict, auto-level-up if thresholds reached.
        Returns the unit's new level."""
        # Ensure xp/level fields exist (defensive for legacy units)
        if 'xp' not in unit:
            unit['xp'] = 0
        if 'level' not in unit:
            unit['level'] = 0
        if amount <= 0:
            return unit['level']
        unit['xp'] += amount
        # Check for level-ups against cumulative thresholds
        while unit['level'] < self.MAX_LEVEL:
            threshold = self.LEVEL_XP_CUMULATIVE[unit['level']]
            if unit['xp'] >= threshold:
                unit['level'] += 1
            else:
                break
        return unit['level']

    def get_unit_avg_levels(self, territory, player=None):
        """Get average level per unit type for a garrison.
        Returns dict: {unit_type: avg_level}.
        If player is None, averages across all garrisons."""
        garrisons = self.territory_garrisons.get(territory, {})
        type_levels = {}  # {unit_type: [level, level, ...]}
        for p_idx, garrison_data in garrisons.items():
            if player is not None and p_idx != player:
                continue
            for unit in garrison_data.get('units', []):
                ut = unit.get('type', 'Swordsman')
                lv = unit.get('level', 0)
                type_levels.setdefault(ut, []).append(lv)
        result = {}
        for ut, levels in type_levels.items():
            result[ut] = sum(levels) / len(levels) if levels else 0
        return result

    def army_has_captain(self, territory, player=None):
        """Check if a player's garrison in a territory contains at least one Captain.
        Used for Captain extended movement (2-hop through allied territory)."""
        if player is None:
            player = self.current_player
        garrison = self.territory_garrisons.get(territory, {}).get(player)
        if not garrison:
            return False
        for unit in garrison.get('units', []):
            if unit.get('type') == 'Captain':
                return True
        return False

    def find_2hop_path(self, from_territory, to_territory, player):
        """Find an intermediate allied territory connecting from_territory to to_territory.
        For Captain extended movement: army can move 2 hops if intermediate and destination
        are allied (own or ally). Does NOT allow 2-hop attacks on enemy territories.
        Returns intermediate territory name, or None if no valid 2-hop path exists."""
        # 2-hop only for non-adjacent territories (adjacent = use normal movement)
        if map_data.are_adjacent(from_territory, to_territory):
            return None

        # Destination must be allied (own or ally) — no 2-hop attacks
        dest_owner = self.territory_owners.get(to_territory, -1)
        if dest_owner != player and not (dest_owner >= 0 and self.are_allies(player, dest_owner)):
            return None

        # Find intermediate territory: adjacent to both source and dest, and allied
        from_neighbors = set(map_data.get_neighbors(from_territory))
        to_neighbors = set(map_data.get_neighbors(to_territory))
        candidates = from_neighbors & to_neighbors  # Must be adjacent to both

        for intermediate in candidates:
            inter_owner = self.territory_owners.get(intermediate, -1)
            if inter_owner == player or (inter_owner >= 0 and self.are_allies(player, inter_owner)):
                return intermediate

        return None

    # R11: get_building_xp_data() and award_building_xp() moved to BuildingMixin (buildings.py)
    # — they belong with building logic alongside _tick_building_xp()

    def calculate_unit_effectiveness(self, attacker_type, defender_composition):
        """
        Calculate the effectiveness of a single attacker unit type against an enemy composition.
        Returns: effectiveness multiplier (0.5x, 1x, or 2x based on matchup)
        """
        if not defender_composition:
            return 1.0  # Neutral if no enemies
        
        attacker_info = self.UNIT_TYPES[attacker_type]
        counters = attacker_info['counters']  # Who this unit is strong against
        countered_by = attacker_info['countered_by']  # Who is strong against this unit
        
        # Count enemies by matchup type
        countered_enemies = defender_composition.get(counters, 0)  # Enemies this unit counters
        countering_enemies = defender_composition.get(countered_by, 0)  # Enemies that counter this unit
        total_enemies = sum(defender_composition.values())
        
        if total_enemies == 0:
            return 1.0
        
        # Calculate weighted effectiveness based on enemy composition
        # If fighting mostly countered enemies: closer to 2x
        # If fighting mostly countering enemies: closer to 0.5x
        # Otherwise: closer to 1x
        
        countered_ratio = countered_enemies / total_enemies
        countering_ratio = countering_enemies / total_enemies
        neutral_ratio = 1.0 - countered_ratio - countering_ratio
        
        # Weighted average of effectiveness
        effectiveness = (countered_ratio * 2.0) + (neutral_ratio * 1.0) + (countering_ratio * 0.5)
        
        return effectiveness

    def calculate_army_effective_strength(self, composition, enemy_composition, player=None, territory=None, is_keep_phase1=False, unit_avg_levels=None):
        """
        Calculate the total effective strength of an army against an enemy.

        Args:
            composition: Dict of {unit_type: count} for the army
            enemy_composition: Dict of {unit_type: count} for the enemies
            player: Optional player index for conditional bonuses
            territory: Optional territory name for location-based bonuses
            is_keep_phase1: Optional flag indicating this is Phase 1 of a Keep battle
            unit_avg_levels: Optional dict {unit_type: avg_level} for veterancy bonus

        Returns: float representing total effective strength
        """
        if not composition:
            return 0.0

        if not enemy_composition:
            # No enemies, just return total count
            return float(sum(composition.values()))

        # Captain Army Bonus: +12% strength to all non-Captain units (non-stacking)
        # Having 1+ Captains in the army applies the bonus; multiple Captains don't stack
        has_captain_bonus = composition.get('Captain', 0) > 0
        captain_bonus_pct = self.UNIT_TYPES['Captain'].get('army_bonus', 0.12) if has_captain_bonus else 0.0

        total_strength = 0.0
        for unit_type, count in composition.items():
            effectiveness = self.calculate_unit_effectiveness(unit_type, enemy_composition)

            # Base unit strength (Captain = 0.25, all others = 1.0)
            unit_strength = self.UNIT_TYPES.get(unit_type, {}).get('strength', 1.0)

            # Apply base strength multiplier (default 1.0)
            base_multiplier = 1.0

            # Battlement Archery: +50% strength for Archers in territories with friendly Keep/Castle
            if (unit_type == 'Archer' and player is not None and territory is not None):
                bonus_percent = self.player_archer_keep_strength_bonus[player]
                if bonus_percent > 0:
                    # Check if territory has a friendly Keep or Castle
                    if self.has_friendly_keep(territory, player):
                        base_multiplier += bonus_percent / 100.0

            # Cavalry Tactics: +33% strength for Cavalry units (works in normal battles and Keep Phase 1)
            if (unit_type == 'Cavalry' and player is not None):
                bonus_percent = self.player_cavalry_strength_bonus[player]
                if bonus_percent > 0:
                    base_multiplier += bonus_percent / 100.0

            # Divide and Conquer: +20% strength for Pikemen/Swordsmen (works in normal battles and Keep Phase 1)
            if (unit_type in ['Pikeman', 'Swordsman'] and player is not None):
                if self.player_divide_conquer_bonus[player]:
                    base_multiplier += 0.20

            # Vanquish the Enemy (Neil Hévilneu): +20% strength for Swordsmen, Pikemen, Archers, and Cavalry
            if (unit_type in ['Swordsman', 'Pikeman', 'Archer', 'Cavalry'] and player is not None):
                if self.player_has_hevilneu(player):
                    base_multiplier += 0.20

            # Territorial unit strength bonuses: +10% per bonus territory
            if player is not None:
                territorial_bonuses = self.calculate_player_territorial_bonuses(player)
                if unit_type == 'Pikeman' and 'pikeman_str' in territorial_bonuses:
                    base_multiplier += territorial_bonuses['pikeman_str'] / 100.0
                elif unit_type == 'Archer' and 'archer_str' in territorial_bonuses:
                    base_multiplier += territorial_bonuses['archer_str'] / 100.0
                elif unit_type == 'Swordsman' and 'swordsman_str' in territorial_bonuses:
                    base_multiplier += territorial_bonuses['swordsman_str'] / 100.0
                elif unit_type == 'Cavalry' and 'cavalry_str' in territorial_bonuses:
                    base_multiplier += territorial_bonuses['cavalry_str'] / 100.0

            # Veterancy bonus: +15% effective strength per unit level
            level_bonus = 1.0
            if unit_avg_levels and unit_type in unit_avg_levels:
                avg_level = unit_avg_levels[unit_type]
                level_bonus = 1.0 + avg_level * self.UNIT_LEVEL_STRENGTH_BONUS

            # Captain army bonus: +12% to non-Captain units when army has a Captain
            captain_multiplier = 1.0
            if unit_type != 'Captain' and captain_bonus_pct > 0:
                captain_multiplier = 1.0 + captain_bonus_pct

            total_strength += count * unit_strength * effectiveness * base_multiplier * level_bonus * captain_multiplier

        return total_strength

    # R3: Removed dead code calculate_army_base_strength() — had a KeyError bug
    # (referenced non-existent 'strength' key in UNIT_TYPES) and zero callers

    def apply_casualties_with_priority(self, territory, casualties, enemy_composition):
        """
        Remove casualties from a territory's army using veterancy-aware priority:
        PRIMARY: Level (lowest level dies first - veterans survive battles)
        SECONDARY: Counter matchup (countered → neutral → advantaged within same level)

        Returns: dict of casualties by type {unit_type: count}
        """
        if territory not in self.army_units or casualties <= 0:
            return {}
        
        units = self.army_units[territory]
        if not units:
            return {}
        
        # Categorize units by their effectiveness against the enemy
        countered_units = []  # 0.5x - removed first
        neutral_units = []    # 1x - removed second
        advantaged_units = [] # 2x - removed last
        
        for unit in units:
            unit_type = unit.get('type', 'Swordsman')
            unit_info = self.UNIT_TYPES[unit_type]
            
            if not enemy_composition:
                # No enemy info, treat as neutral
                neutral_units.append(unit)
                continue
            
            counters = unit_info['counters']
            countered_by = unit_info['countered_by']
            
            # Check if this unit type is heavily countered or countering
            countering_enemies = enemy_composition.get(countered_by, 0)
            countered_enemies = enemy_composition.get(counters, 0)
            total_enemies = sum(enemy_composition.values())
            
            if total_enemies > 0:
                countering_ratio = countering_enemies / total_enemies
                countered_ratio = countered_enemies / total_enemies
                
                # Categorize based on dominant matchup
                if countering_ratio > 0.5:  # More than half enemies counter this unit
                    countered_units.append(unit)
                elif countered_ratio > 0.5:  # This unit counters more than half
                    advantaged_units.append(unit)
                else:
                    neutral_units.append(unit)
            else:
                neutral_units.append(unit)
        
        # Veterancy-aware casualty priority:
        # PRIMARY: level ASC (lowest level dies first - veterans survive)
        # SECONDARY: counter tier ASC (countered dies before neutral before advantaged)
        # Build a single sorted list of (level, tier, unit) for unified priority
        tier_map = {}
        for u in countered_units:
            tier_map[id(u)] = 0   # countered = most vulnerable tier
        for u in neutral_units:
            tier_map[id(u)] = 1
        for u in advantaged_units:
            tier_map[id(u)] = 2   # advantaged = least vulnerable tier

        # Captains die last (lore: behind the army as support), regardless of level/tier
        all_sorted = sorted(units, key=lambda u: (1 if u.get('type') == 'Captain' else 0, u.get('level', 0), tier_map.get(id(u), 1)))

        # Apply casualties: kill from front (lowest level + worst matchup first)
        casualties_applied = {}
        remaining_casualties = casualties
        units_to_remove = []

        for unit in all_sorted:
            if remaining_casualties <= 0:
                break
            unit_type = unit.get('type', 'Swordsman')
            casualties_applied[unit_type] = casualties_applied.get(unit_type, 0) + 1
            units_to_remove.append(unit)
            remaining_casualties -= 1

        for unit in units_to_remove:
            units.remove(unit)

        return casualties_applied

    def apply_multi_garrison_casualties(self, territory, casualties, enemy_composition, owner_player):
        """
        Apply casualties to multi-garrison defenders in a territory.

        Casualty Order (USER REQUIREMENT):
        1. Allied garrisons die FIRST (sorted by player index for consistency)
        2. Owner's garrison dies LAST

        Within each garrison:
        - Follow veterancy priority (level ASC, then countered → neutral → advantaged)

        Args:
            territory: Territory name
            casualties: Total casualties to apply
            enemy_composition: Enemy unit composition for priority calculation
            owner_player: The territory owner (whose garrison is last to take casualties)

        Returns:
            dict: {player_index: {unit_type: count}} - casualties by player and unit type
        """
        if territory not in self.territory_garrisons:
            return {}

        total_casualties_applied = {}
        remaining_casualties = casualties

        # Get all players with garrisons in this territory
        garrison_players = list(self.territory_garrisons[territory].keys())

        # Sort: Allies first (by player index), owner last
        garrison_players.sort(key=lambda p: (p == owner_player, p))

        # Apply casualties to each garrison in order
        for player in garrison_players:
            if remaining_casualties <= 0:
                break

            garrison = self.territory_garrisons[territory][player]
            garrison_size = len(garrison['units'])

            if garrison_size == 0:
                continue

            # Calculate how many casualties this garrison can take
            casualties_for_garrison = min(remaining_casualties, garrison_size)

            # Apply casualties to this garrison using priority system
            # Temporarily set up army_units to use priority system
            old_army_units = self.army_units.get(territory, [])
            self.army_units[territory] = garrison['units']

            garrison_casualties = self.apply_casualties_with_priority(
                territory,
                casualties_for_garrison,
                enemy_composition
            )

            # Update garrison units list
            garrison['units'] = self.army_units[territory]

            # Restore old army_units
            self.army_units[territory] = old_army_units

            # Track casualties by player
            if player not in total_casualties_applied:
                total_casualties_applied[player] = {}

            for unit_type, count in garrison_casualties.items():
                total_casualties_applied[player][unit_type] = total_casualties_applied[player].get(unit_type, 0) + count

            # Reduce remaining casualties
            remaining_casualties -= casualties_for_garrison

            # Update garrison counts
            garrison['unmoved'] = max(0, garrison['unmoved'] - casualties_for_garrison)
            if garrison['unmoved'] < 0:
                garrison['moved'] = max(0, garrison['moved'] + garrison['unmoved'])
                garrison['unmoved'] = 0

        # Sync garrison counts with actual unit lists to fix any desync from
        # separate count/unit modifications during casualty application
        for player in garrison_players:
            self._sync_garrison_counts(territory, player)

        return total_casualties_applied

    def destroy_buildings(self, territory, previous_owner=None, new_owner=None):
        """
        Destroy all buildings (completed and under construction) in a territory.

        Champion of the People: If new_owner has Seledra, Farms and Mines are preserved.
        Pillage: If new_owner has Vearen Asford and destroys an enemy Keep, gain 200 Gold.

        Args:
            territory: Territory name
            previous_owner: Previous owner index (for hero handling)
            new_owner: New owner index (for Champion of the People ability)
        """
        # Check for Pillage ability BEFORE destroying buildings
        # Pillage: Award gold if new_owner has Vearen Asford and is destroying an enemy Keep
        keep_existed = False
        if territory in self.buildings:
            for plot_index, building_type in self.buildings[territory].items():
                if building_type == 'Keep':
                    keep_existed = True
                    break

        # Pillage triggers when:
        # 1. A Keep existed in the territory
        # 2. Territory had a previous owner (not neutral)
        # 3. New owner is different from previous owner (enemy Keep)
        # 4. New owner has Vearen Asford active
        if keep_existed and previous_owner is not None and previous_owner >= 0:
            if new_owner is not None and new_owner >= 0 and new_owner != previous_owner:
                if self.player_has_asford(new_owner):
                    self.player_gold[new_owner] += 200
                    self.add_message(f"  Pillage! Vearen Asford plunders 200 Gold from the ruins!")

        # Check if Champion of the People is active (new owner has Seledra)
        champion_active = new_owner is not None and new_owner >= 0 and self.player_has_seledra(new_owner)

        # Kill heroes and cancel hero training before destroying buildings
        if previous_owner is not None and territory in self.buildings:
            for plot_index, building_type in list(self.buildings[territory].items()):
                if building_type == 'Keep':
                    # Kill heroes (returns count for recap stat tracking)
                    heroes_killed_count = self.kill_heroes_in_keep(territory, plot_index, previous_owner)
                    # Track enemy heroes killed by the conquering player
                    if heroes_killed_count > 0 and new_owner is not None and new_owner >= 0:
                        self._track_stat(new_owner, 'heroes_killed', heroes_killed_count)
                        # Player Level: award XP for killing enemy heroes (10 per hero)
                        self._track_stat(new_owner, 'xp_earned', 10 * heroes_killed_count)

                    # Cancel training
                    if (territory in self.hero_training_queue and
                        plot_index in self.hero_training_queue[territory]):
                        # C1 fix: handle 3-tuple (hero_type, time, paid_cost) from Audit #3 H1
                        entry = self.hero_training_queue[territory][plot_index]
                        hero_type = entry[0]
                        del self.hero_training_queue[territory][plot_index]
                        if not self.hero_training_queue[territory]:
                            del self.hero_training_queue[territory]
                        self.hero_ownership[previous_owner].discard(hero_type)

        # Remove completed buildings (with Champion of the People exception)
        if territory in self.buildings:
            saved_buildings = {}
            destroyed_count = 0
            saved_count = 0
            destroyed_farms = 0  # Track destroyed Farms for Raze the Countryside
            destroyed_mines = 0  # Track destroyed Mines for Leave Nothing Behind

            for plot_index, building_type in list(self.buildings[territory].items()):
                if building_type is None:
                    continue

                # Champion of the People: Save Farms and Mines if new owner has Seledra
                if champion_active and building_type in ['Farm', 'Mine']:
                    saved_buildings[plot_index] = building_type
                    saved_count += 1
                else:
                    destroyed_count += 1
                    # Track destroyed Farms for Raze the Countryside and Leave Nothing Behind
                    if building_type == 'Farm':
                        destroyed_farms += 1
                    elif building_type == 'Mine':
                        destroyed_mines += 1

            # Update buildings dict
            if saved_buildings:
                self.buildings[territory] = saved_buildings
                # Veterancy: Clean up XP for destroyed plots, preserve saved ones
                if territory in self.building_xp:
                    saved_plots = set(saved_buildings.keys())
                    for plot_idx in list(self.building_xp[territory].keys()):
                        if plot_idx not in saved_plots:
                            del self.building_xp[territory][plot_idx]
                    if not self.building_xp[territory]:
                        del self.building_xp[territory]
                self.add_message(f"  {saved_count} Farm(s)/Mine(s) saved by Champion of the People in {territory}!")
            else:
                del self.buildings[territory]
                # Veterancy: Remove all building XP data for this territory
                if territory in self.building_xp:
                    del self.building_xp[territory]

            if destroyed_count > 0:
                self.add_message(f"  {destroyed_count} building(s) destroyed in {territory}")
                # Track buildings destroyed by conquering player for recap screen
                if new_owner is not None and new_owner >= 0:
                    self._track_stat(new_owner, 'buildings_destroyed', destroyed_count)

            # Raze the Countryside: Award gold for destroyed enemy Farms
            if destroyed_farms > 0 and new_owner is not None and new_owner >= 0:
                gold_bonus = self.player_farm_destruction_gold_bonus[new_owner]
                if gold_bonus > 0 and previous_owner is not None and previous_owner != new_owner:
                    total_gold = gold_bonus * destroyed_farms
                    self.player_gold[new_owner] += total_gold
                    self.add_message(f"  Raze the Countryside! Gained {total_gold} Gold from destroying {destroyed_farms} Farm(s)!")

            # Leave Nothing Behind: Refund 50% of cost for destroyed Farms and Mines
            if (destroyed_farms > 0 or destroyed_mines > 0) and previous_owner is not None and previous_owner >= 0:
                if 'tech_0_2' in self.player_tech_researched.get(previous_owner, set()):
                    # L4 fix: Use actual building costs instead of hardcoded values
                    farm_cost = self.building_types.get('Farm', {}).get('cost', 30)
                    mine_cost = self.building_types.get('Mine', {}).get('cost', 40)
                    farm_recovery = destroyed_farms * (farm_cost // 2)  # 50% recovery
                    mine_recovery = destroyed_mines * (mine_cost // 2)  # 50% recovery
                    total_recovery = farm_recovery + mine_recovery

                    if total_recovery > 0:
                        self.player_gold[previous_owner] += total_recovery
                        recovery_details = []
                        if destroyed_farms > 0:
                            recovery_details.append(f"{destroyed_farms} Farm(s) = {farm_recovery}g")
                        if destroyed_mines > 0:
                            recovery_details.append(f"{destroyed_mines} Mine(s) = {mine_recovery}g")
                        self.add_message(f"  Leave Nothing Behind! Player {previous_owner + 1} recovered {total_recovery} Gold ({', '.join(recovery_details)})")

        # Cancel buildings under construction (Champion doesn't save these - not yet built)
        if territory in self.under_construction:
            construction_count = len(self.under_construction[territory])
            if construction_count > 0:
                self.add_message(f"  {construction_count} construction(s) cancelled in {territory}")
            del self.under_construction[territory]

        # Cancel Castle upgrades in progress (no refund)
        if territory in self.castle_upgrades_in_progress:
            del self.castle_upgrades_in_progress[territory]

        # Remove Castle upgrade flags
        if territory in self.castle_upgrades:
            del self.castle_upgrades[territory]

    def add_movement_order(self, from_territory, to_territory):
        """Create a movement order for the selected army"""
        # Tutorial hook: check if movement action is allowed
        if self.tutorial_mission and not self.tutorial_mission.is_action_allowed(
                'move', from_territory=from_territory, to_territory=to_territory):
            return False

        # Validate: army must be selected
        if not self.selected_army:
            return False
        
        selected_territory, army_count = self.selected_army
        
        # Validate: from_territory matches selected army
        if from_territory != selected_territory:
            return False
        
        # Validate: territories must be adjacent (or reachable via Captain 2-hop)
        is_adjacent = map_data.are_adjacent(from_territory, to_territory)
        intermediate_territory = None
        if not is_adjacent:
            # Check for Captain extended movement (2-hop through allied territory)
            if self.army_has_captain(from_territory):
                intermediate_territory = self.find_2hop_path(from_territory, to_territory, self.current_player)
            if not intermediate_territory:
                self.add_message("Territories are not adjacent!")
                return False

        # R8 fix: Validate against current player's garrison, not territory owner's
        # In allied scenarios, a player may garrison in territory they don't own
        garrison = self.territory_garrisons.get(from_territory, {}).get(self.current_player)
        if not garrison or garrison.get('unmoved', 0) <= 0:
            self.add_message("No armies available to move")
            return False

        # Validate: army limit for reinforcements (moving to own territory or ally territory)
        dest_owner = self.territory_owners.get(to_territory, -1)
        from_owner = self.territory_owners.get(from_territory, -1)
        is_ally_reinforcement = (dest_owner >= 0 and from_owner >= 0 and self.are_allies(from_owner, dest_owner))
        is_own_reinforcement = (dest_owner == from_owner and dest_owner != -1)

        if is_own_reinforcement or is_ally_reinforcement:
            # This is a reinforcement (own or ally) - check total army limit
            # Uses projected capacity: current + incoming - outgoing orders
            projected, _ = self._get_effective_capacity(to_territory)
            if projected + army_count > self.MAX_ARMIES_PER_TERRITORY:
                self.add_message(f"Cannot reinforce {to_territory}: would exceed army limit of {self.MAX_ARMIES_PER_TERRITORY}!")
                return False

        # Check if order already exists from this territory
        # If so, automatically cancel it and replace with new order
        for i, order in enumerate(self.movement_orders):
            if order.from_territory == from_territory:
                # Auto-cancel the old order
                # Reset unit status if this order has unit_ids (Phase 3)
                if order.unit_ids and order.from_territory in self.army_units:
                    units = self.army_units[order.from_territory]
                    for unit in units:
                        if unit.get('order') == order:
                            unit['status'] = 'ready'
                            unit['order'] = None
                # Remove old order
                self.movement_orders.pop(i)
                self.add_message(f"Previous order cancelled and replaced")
                break
        
        # Create the order
        # Deferred import to avoid circular import (MovementOrder defined in game_state/__init__.py)
        from game_state import MovementOrder
        order_player = self.current_player

        order = MovementOrder(
            from_territory=from_territory,
            to_territory=to_territory,
            army_count=army_count,
            player=order_player,
            intermediate_territory=intermediate_territory  # Captain 2-hop path
        )
        
        self.movement_orders.append(order)
        self.add_message(f"Order created: {army_count} armies {from_territory} -> {to_territory}")
        
        # Revalidate: if old outgoing was replaced with smaller order, from_territory
        # retains more armies, so incoming orders to from_territory might now overflow
        cancelled = self._revalidate_incoming_orders(from_territory)
        if cancelled:
            self.add_message(f"Auto-cancelled incoming to {from_territory} (capacity exceeded):")
            for desc in cancelled:
                self.add_message(f"  - {desc}")

        # Keep army selected for chaining orders
        return True

    def add_movement_order_for_units(self, from_territory, to_territory, unit_ids, player=None):
        """
        Create a movement order for specific army units (Phase 3).
        
        Automatically cancels any existing orders for the selected units before
        creating the new order. This is a key Phase 3 feature that allows
        fine-grained control over army composition and movement.
        
        Auto-Cancel Behavior:
            If units have existing orders to different destinations:
            - Full overlap: Remove entire old order
            - Partial overlap: Remove units from old order, update count
            - Reset overlapping units to 'ready' status
            - Show message: "Previous orders for selected armies cancelled"
        
        This auto-cancel happens BEFORE validation, which is critical:
            1. Auto-cancel orders â†’ Reset units to 'ready'
            2. Validate status â†’ Units are now 'ready' (PASS)
            3. Create new order â†’ SUCCESS
        
        Wrong order would fail validation before auto-cancel could run!
        
        Args:
            from_territory: Source territory name (e.g., "France")
            to_territory: Destination territory name (e.g., "Spain")
            unit_ids: List of unit IDs (0-indexed) to move
        
        Returns:
            bool: True if order created successfully, False otherwise
        
        Validation Checks:
            - unit_ids must not be empty
            - Territories must be adjacent (with error handling)
            - Units must have 'ready' status (after auto-cancel)
            - Territory must have a valid owner
        
        Side Effects:
            - Updates self.movement_orders (may add/remove/modify)
            - Changes unit status to 'ordered' for selected units
            - Resets status to 'ready' for units in cancelled orders
            - Adds message to action log
        
        Error Handling:
            - Adjacency check wrapped in try/except (Phase 1B)
            - Territory owner lookup protected (Phase 1B)
            - Logs errors without crashing
        
        Used By:
            - Army composition UI (when creating split orders)
            - Click handlers (when moving specific units)
        
        Related Methods:
            - cancel_movement_order() - Manual order cancellation
            - execute_all_orders() - Executes these orders
        """
        # Determine which player's garrison to use
        if player is None:
            player = self.current_player

        # Tutorial hook: check if movement action is allowed (only for human player 0)
        # AI player (1) movements during scripted sequences are not restricted
        if player == 0 and self.tutorial_mission and not self.tutorial_mission.is_action_allowed(
                'move', from_territory=from_territory, to_territory=to_territory):
            return False

        # Validate: must have units selected
        if not unit_ids:
            return False

        # Get units from the specific player's garrison (multi-garrison support)
        garrison = self.territory_garrisons.get(from_territory, {}).get(player)
        if not garrison:
            self.add_message(f"No garrison found for player {player + 1} in {from_territory}")
            return False

        units = garrison.get('units', [])
        
        # FIRST: Auto-cancel any existing orders for selected units
        # This must happen BEFORE status validation
        orders_to_remove = []
        units_to_reset = []

        for i, order in enumerate(self.movement_orders):
            # Only check orders from the same player's garrison in this territory
            if order.from_territory == from_territory and order.player == player and order.unit_ids:
                # Check if any unit IDs overlap
                overlap = set(unit_ids) & set(order.unit_ids)
                if overlap:
                    # Collect units to reset from the multi-garrison system
                    order_garrison = self.territory_garrisons.get(order.from_territory, {}).get(order.player)
                    if order_garrison:
                        for unit in order_garrison.get('units', []):
                            if unit['id'] in overlap and unit.get('order') == order:
                                units_to_reset.append(unit)

                    # Check if order only contains overlapping units
                    if set(order.unit_ids) == overlap:
                        # Cancel entire order (all units overlap)
                        orders_to_remove.append(i)
                    else:
                        # Partial overlap - remove overlapping units from order
                        order.unit_ids = [uid for uid in order.unit_ids if uid not in overlap]
                        order.army_count = len(order.unit_ids)

        # Reset status of overlapping units (makes them 'ready' again)
        for unit in units_to_reset:
            unit['status'] = 'ready'
            unit['order'] = None
        
        # Remove orders that were fully cancelled (in reverse to maintain indices)
        for i in reversed(orders_to_remove):
            self.movement_orders.pop(i)
        
        if units_to_reset:
            self.add_message(f"Previous orders for selected armies cancelled")
        
        # NOW: Validate that all units are 'ready' status
        # (After auto-cancel, previously 'ordered' units are now 'ready')
        ready_units = [u['id'] for u in units if u['status'] == 'ready']
        invalid_units = [uid for uid in unit_ids if uid not in ready_units]
        if invalid_units:
            self.add_message("Some selected armies are not ready to move")
            return False

        # Validate: territories must be adjacent (or reachable via Captain 2-hop)
        intermediate_territory = None
        try:
            is_adjacent = map_data.are_adjacent(from_territory, to_territory)
            if not is_adjacent:
                # Check Captain extended movement — Captain must be in the selected units
                has_captain_in_selection = any(
                    u.get('type') == 'Captain' for u in units if u['id'] in unit_ids
                )
                if has_captain_in_selection:
                    intermediate_territory = self.find_2hop_path(from_territory, to_territory, player)
                if not intermediate_territory:
                    self.add_message("Territories are not adjacent!")
                    return False
        except Exception as e:
            self.log_error(f"Failed to check adjacency between {from_territory} and {to_territory}", e)
            self.add_message("Error checking territory adjacency")
            return False

        # Use the player parameter (which player is making this order)
        # In multi-garrison territories, this is the garrison owner, not territory owner
        order_player = player

        # Validate: army limit for reinforcements (moving to own territory or ally territory)
        dest_owner = self.territory_owners.get(to_territory, -1)
        is_ally_reinforcement = (dest_owner >= 0 and order_player >= 0 and self.are_allies(order_player, dest_owner))
        is_own_reinforcement = (dest_owner == order_player)

        if is_own_reinforcement or is_ally_reinforcement:
            # This is a reinforcement (own or ally) - check total army limit
            # Uses projected capacity: current + incoming - outgoing orders
            projected, _ = self._get_effective_capacity(to_territory)
            if projected + len(unit_ids) > self.MAX_ARMIES_PER_TERRITORY:
                self.add_message(f"Cannot reinforce {to_territory}: would exceed army limit of {self.MAX_ARMIES_PER_TERRITORY}!")
                return False

        # Create the order with unit IDs
        # Deferred import to avoid circular import (MovementOrder defined in game_state/__init__.py)
        from game_state import MovementOrder
        order = MovementOrder(
            from_territory=from_territory,
            to_territory=to_territory,
            army_count=len(unit_ids),
            player=order_player,
            unit_ids=unit_ids,
            intermediate_territory=intermediate_territory  # Captain 2-hop path
        )
        
        self.movement_orders.append(order)

        # Mark units as 'ordered'
        for unit in units:
            if unit['id'] in unit_ids:
                unit['status'] = 'ordered'
                unit['order'] = order
        
        self.add_message(f"Order created: {len(unit_ids)} armies {from_territory} -> {to_territory}")
        
        # Tutorial hook: notify that movement order was created
        if self.tutorial_mission:
            self.tutorial_mission.notify_event('order_created',
                                               from_territory=from_territory,
                                               to_territory=to_territory,
                                               player=self.current_player)

        # Revalidate: auto-cancelled unit orders freed up armies in from_territory,
        # so incoming orders to from_territory might now overflow
        cancelled = self._revalidate_incoming_orders(from_territory)
        if cancelled:
            self.add_message(f"Auto-cancelled incoming to {from_territory} (capacity exceeded):")
            for desc in cancelled:
                self.add_message(f"  - {desc}")

        return True

    def cancel_movement_order(self, order_index):
        """Cancel a specific movement order"""
        if 0 <= order_index < len(self.movement_orders):
            order = self.movement_orders[order_index]

            # Reset unit status if this order has unit_ids (use multi-garrison system)
            if order.unit_ids:
                garrison = self.territory_garrisons.get(order.from_territory, {}).get(order.player)
                if garrison:
                    for unit in garrison.get('units', []):
                        # Reset any units that have this order
                        if unit.get('order') == order:
                            unit['status'] = 'ready'
                            unit['order'] = None
            self.add_message(f"Order cancelled: {order.from_territory} -> {order.to_territory}")
            self.movement_orders.pop(order_index)

            # Revalidate: cancelled outgoing order means from_territory keeps its
            # armies, so incoming orders to from_territory might now overflow
            cancelled = self._revalidate_incoming_orders(order.from_territory)
            if cancelled:
                self.add_message(f"Auto-cancelled incoming to {order.from_territory} (capacity exceeded):")
                for desc in cancelled:
                    self.add_message(f"  - {desc}")

            return True
        return False

    def cancel_all_orders(self):
        """Cancel all movement orders"""
        count = len(self.movement_orders)
        
        # Reset all unit statuses (use multi-garrison system)
        for order in self.movement_orders:
            if order.unit_ids:
                garrison = self.territory_garrisons.get(order.from_territory, {}).get(order.player)
                if garrison:
                    for unit in garrison.get('units', []):
                        if unit.get('order') == order:
                            unit['status'] = 'ready'
                            unit['order'] = None
        
        self.movement_orders = []
        if count > 0:
            self.add_message(f"Cancelled {count} orders")
        return count

    def execute_all_orders(self):
        """
        Execute all movement orders simultaneously and detect battles.
        
        This is the core order execution system that processes all planned movements
        at once (simultaneous movement). It handles army limits, garrison mechanics,
        battle detection, and status updates for both whole-army and unit-level orders.
        
        Execution Phases:
            1. Validation - Check army limits for friendly territories
            2. Garrison Extraction - Remove units from origin territories
            3. Arrival Processing - Add units to destination territories
            4. Battle Detection - Find territories with multiple players
            5. Status Updates - Mark units as 'moved'
            6. Cleanup - Clear orders and transition to battle phase
        
        Army Limit Enforcement:
            - Friendly territories: Enforced (max 15 armies per territory)
            - Enemy territories: Not enforced (battles resolve counts)
            - Orders that would exceed limit are skipped with warning
        
        Garrison Mechanics:
            - Origin territory: Units removed (armies_unmoved decreases)
            - Destination territory: Units added (armies increases)
            - Unit IDs: Preserved for Phase 3 unit tracking
        
        Battle Detection:
            Creates Battle objects for territories with:
            - Multiple different players present
            - Includes original owner as defender (if any)
            - Preserves unit composition for combat calculation
        
        Status Management:
            Phase 2 (Whole armies):
            - armies_unmoved â†’ armies_moved for entire count
            
            Phase 3 (Individual units):
            - Unit status: 'ordered' â†’ 'moved'
            - Unit order: References cleared
            - army_units dict: Updated in destination territories
        
        Order Types Handled:
            1. Whole army orders (army_count, no unit_ids)
            2. Unit-specific orders (army_count, unit_ids list)
        
        Side Effects:
            - Clears self.movement_orders
            - Updates armies, armies_unmoved, armies_moved
            - Updates army_units (if Phase 3 orders present)
            - Creates pending_battles list
            - Changes turn_phase to 'battles'
            - Adds messages to action log
        
        Messaging:
            - Shows execution start message
            - Shows each successful move
            - Shows army limit warnings
            - Shows battle detection messages
        
        Called By:
            - "Execute Orders" button in bottom UI
            - Only available in 'planning' phase
        
        Related Methods:
            - add_movement_order() - Creates orders
            - resolve_battle() - Processes battles
            - next_turn() - Ends battle phase
        
        Error Conditions:
            - No orders: Shows message, returns early
            - Army limit exceeded: Skips order with warning
            - Invalid territories: Should not happen (validated at creation)
        """
        # Deferred import to avoid circular import (ArmyAnimation defined in game_state/__init__.py)
        from game_state import ArmyAnimation
        if not self.movement_orders:
            self.add_message("No orders to execute")
            return
        
        # Clear army selection
        self.selected_army = None

        # Change phase to execution
        self.turn_phase = 'execution'
        self.add_message(f"=== Executing {len(self.movement_orders)} orders ===")

        # Step 1: Validate moves and check army limits for friendly territories
        # Safety net: creation-time validation + revalidation should keep orders consistent,
        # but this catches any edge cases. Uses net-aware capacity (accounts for outgoing).
        valid_orders = []
        for order in self.movement_orders:
            to_terr = order.to_territory
            from_terr = order.from_territory
            army_count = order.army_count

            # Check if this is a reinforcement (moving to own territory)
            dest_owner = self.territory_owners.get(to_terr, -1)
            if dest_owner == order.player:
                # This is a reinforcement - check army limit with net-aware capacity
                # Legacy counter fix: use get_territory_total_armies for allied garrisons
                current_garrison = self.get_territory_total_armies(to_terr)
                # Subtract armies ordered to leave this destination
                outgoing_from_dest = sum(
                    o.army_count for o in self.movement_orders
                    if o.from_territory == to_terr
                )
                # Count incoming already validated for this destination
                incoming_already_valid = sum(
                    o.army_count for o in valid_orders
                    if o.to_territory == to_terr
                )
                effective = current_garrison - outgoing_from_dest + incoming_already_valid + army_count
                if effective > self.MAX_ARMIES_PER_TERRITORY:
                    excess = effective - self.MAX_ARMIES_PER_TERRITORY
                    logger.warning(f"Order skipped: Player {order.player + 1} reinforcement to {to_terr} "
                                   f"would exceed army limit (effective={effective}, "
                                   f"limit={self.MAX_ARMIES_PER_TERRITORY})")
                    self.add_message(f"Player {order.player + 1}: Cannot reinforce {to_terr} - would exceed army limit!")
                    self.add_message(f"  {army_count} armies remain in {from_terr}")
                    continue  # Skip this order, armies stay in source

            # Order is valid
            valid_orders.append(order)
        
        # Step 2: Deduct armies from source territories (only for valid orders)
        # Track territories that have had units removed so we can reassign IDs at the end
        territories_modified = set()

        # Pre-calculate which players will arrive at each destination (for animation positioning)
        destination_arrivals = {}  # {territory: set of player indices}
        for order in valid_orders:
            to_terr = order.to_territory
            if to_terr not in destination_arrivals:
                destination_arrivals[to_terr] = set()
            destination_arrivals[to_terr].add(order.player)

        for order in valid_orders:
            from_terr = order.from_territory
            to_terr = order.to_territory
            player = order.player

            # Check if this order specifies individual units (Phase 3)
            if order.unit_ids:
                # NEW SYSTEM: Remove specific units and track their types
                army_count = len(order.unit_ids)

                # Collect unit types that are moving
                moving_unit_types = {}
                # Veterancy: collect actual unit dicts to preserve xp/level through animation
                extracted_units = []

                # Get garrison for this player
                garrison = self.territory_garrisons.get(from_terr, {}).get(player)

                if garrison:
                    # Remove units from garrison
                    units = garrison.get('units', [])

                    # Collect types of moving units
                    for unit in units:
                        if unit['id'] in order.unit_ids:
                            unit_type = unit.get('type', 'Swordsman')
                            moving_unit_types[unit_type] = moving_unit_types.get(unit_type, 0) + 1

                    # Remove units with these IDs (handle duplicate IDs correctly)
                    units_before = len(garrison['units'])
                    remaining_units = []
                    ids_to_remove = list(order.unit_ids)  # Make a mutable copy
                    actual_removed = 0

                    for unit in units:
                        if unit['id'] in ids_to_remove:
                            # Remove this ID from the list (only removes first occurrence)
                            ids_to_remove.remove(unit['id'])
                            actual_removed += 1
                            extracted_units.append(unit)  # Preserve unit dict with xp/level
                        else:
                            remaining_units.append(unit)

                    garrison['units'] = remaining_units

                    # Validate count matches
                    if actual_removed != army_count:
                        logger.warning(f"[TOOLTIP MISMATCH] {from_terr} Player {player}: "
                              f"Order specified {army_count} unit IDs but removed {actual_removed} units. "
                              f"Unit ID mismatch (possibly duplicate IDs).")

                    # Mark this territory for ID reassignment later
                    territories_modified.add(from_terr)

                    # Clear order references for remaining units
                    for unit in garrison['units']:
                        if unit.get('order') == order:
                            unit['order'] = None
                            # Also reset status if it was 'ordered'
                            if unit.get('status') == 'ordered':
                                unit['status'] = 'ready'

                    # M3 fix: Clamp to 0 to prevent negative unmoved count
                    garrison['unmoved'] = max(0, garrison['unmoved'] - actual_removed)

                    # Sync to legacy arrays ONLY if this player is the owner
                    # (Allies moving shouldn't affect owner's legacy data)
                    if self.territory_owners.get(from_terr, -1) == player:
                        self.sync_legacy_garrison_data(from_terr)
                else:
                    # Fallback: no garrison, use legacy system
                    if from_terr in self.army_units:
                        units = self.army_units[from_terr]
                        for unit in units:
                            if unit['id'] in order.unit_ids:
                                unit_type = unit.get('type', 'Swordsman')
                                moving_unit_types[unit_type] = moving_unit_types.get(unit_type, 0) + 1
                                extracted_units.append(unit)  # Preserve unit dict with xp/level
                        self.army_units[from_terr] = [u for u in units if u['id'] not in order.unit_ids]
                        territories_modified.add(from_terr)
                        for unit in self.army_units[from_terr]:
                            if unit.get('order') == order:
                                unit['order'] = None
                                # Also reset status if it was 'ordered'
                                if unit.get('status') == 'ordered':
                                    unit['status'] = 'ready'

                    self.armies_unmoved[from_terr] -= army_count
                    self.armies[from_terr] = self.armies_unmoved[from_terr] + self.armies_moved.get(from_terr, 0)

                self.add_message(f"Player {order.player + 1}: {army_count} armies leave {from_terr}")

                # Store this order's composition for its animation (not accumulated!)
                order_composition = moving_unit_types.copy()
            else:
                # LEGACY SYSTEM: Use army_count from order, default to Swordsmen
                army_count = order.army_count
                # Veterancy: collect actual unit dicts to preserve xp/level through animation
                extracted_units = []

                # Get garrison for this player
                garrison = self.territory_garrisons.get(from_terr, {}).get(player)

                if garrison:
                    # Use garrison system
                    available = garrison.get('unmoved', 0)
                    if available >= army_count:
                        # Remove units from garrison (take first N unmoved units)
                        units = garrison.get('units', [])
                        remaining_units = []
                        removed_count = 0

                        for unit in units:
                            if removed_count < army_count and unit['status'] == 'ready':
                                removed_count += 1
                                extracted_units.append(unit)  # Preserve unit dict with xp/level
                            else:
                                remaining_units.append(unit)

                        # Validate we got enough units
                        if removed_count < army_count:
                            logger.warning(f"[TOOLTIP MISMATCH] {from_terr} Player {player}: "
                                  f"Requested {army_count} units but only found {removed_count} ready units. "
                                  f"Garrison claims unmoved={available} but units list mismatch.")

                        # Update garrison count with actual removed count
                        garrison['unmoved'] -= removed_count
                        garrison['units'] = remaining_units
                        territories_modified.add(from_terr)

                        # Sync to legacy arrays ONLY if this player is the owner
                        # (Allies moving shouldn't affect owner's legacy data)
                        if self.territory_owners.get(from_terr, -1) == player:
                            self.sync_legacy_garrison_data(from_terr)
                        self.add_message(f"Player {order.player + 1}: {army_count} armies leave {from_terr}")
                    else:
                        # Shouldn't happen with proper validation - log for diagnostics
                        logger.warning(f"Order partially executed: Player {player} requested {army_count} "
                                       f"armies from {from_terr} but only {available} available in garrison. "
                                       f"Sending {available} instead.")
                        garrison['unmoved'] = 0
                        # Collect ready units being extracted, keep non-ready
                        for u in garrison.get('units', []):
                            if u['status'] == 'ready':
                                extracted_units.append(u)  # Preserve unit dict with xp/level
                        garrison['units'] = [u for u in garrison.get('units', []) if u['status'] != 'ready']
                        territories_modified.add(from_terr)
                        army_count = available
                        self.sync_legacy_garrison_data(from_terr)
                        self.add_message(f"Warning: Only {available} armies available from {from_terr}")
                else:
                    # Fallback: no garrison, use legacy system
                    if self.armies_unmoved[from_terr] >= army_count:
                        self.armies_unmoved[from_terr] -= army_count
                        self.armies[from_terr] = self.armies_unmoved[from_terr] + self.armies_moved.get(from_terr, 0)
                        self.add_message(f"Player {order.player + 1}: {army_count} armies leave {from_terr}")
                    else:
                        # Insufficient armies in legacy system - log for diagnostics
                        available = self.armies_unmoved[from_terr]
                        logger.warning(f"Order partially executed (legacy): Player {order.player + 1} "
                                       f"requested {army_count} armies from {from_terr} but only "
                                       f"{available} unmoved available. Sending {available} instead.")
                        self.armies_unmoved[from_terr] = 0
                        army_count = available
                        self.armies[from_terr] = self.armies_moved.get(from_terr, 0)
                        self.add_message(f"Warning: Only {available} armies available from {from_terr}")

                # Default composition (all Swordsmen for legacy orders)
                order_composition = {'Swordsman': army_count}

            # Calculate start and end positions for animation (accounting for multi-garrison)
            from_pos = None
            to_pos = None

            if self.game and hasattr(self.game, 'scaled_centers'):
                # Get FROM position
                from_center = self.game.scaled_centers.get(from_terr)
                if from_center:
                    garrisons_from = self.territory_garrisons.get(from_terr, {})
                    num_garrisons_from = sum(1 for g in garrisons_from.values() if g.get('unmoved', 0) + g.get('moved', 0) > 0)

                    if num_garrisons_from > 1:
                        # Multi-garrison source: use flag position
                        flag_positions = self.get_flag_positions_for_territory(from_terr, from_center[0], from_center[1], num_garrisons_from)
                        # Assign positions to all existing garrisons first
                        for player_index in sorted(garrisons_from.keys()):
                            g = garrisons_from[player_index]
                            if g.get('unmoved', 0) + g.get('moved', 0) > 0:
                                self.assign_garrison_position(from_terr, player_index, num_garrisons_from)
                        # Get assigned position for this player
                        garrison_index = self.assign_garrison_position(from_terr, order.player, num_garrisons_from)
                        if garrison_index < len(flag_positions):
                            from_pos = flag_positions[garrison_index]
                        else:
                            from_pos = from_center
                    else:
                        # Single garrison: use territory center
                        from_pos = from_center

                # Get TO position (BEFORE armies arrive, so check current state + ALL future arrivals)
                to_center = self.game.scaled_centers.get(to_terr)
                if to_center:
                    garrisons_to = self.territory_garrisons.get(to_terr, {})

                    # Count garrisons that will exist AFTER ALL orders arrive
                    # Include current non-empty garrisons + ALL arriving players
                    future_garrisons = set()
                    for player_index, garrison in garrisons_to.items():
                        if garrison.get('unmoved', 0) + garrison.get('moved', 0) > 0:
                            future_garrisons.add(player_index)
                    # Add ALL arriving players (not just this order's player)
                    if to_terr in destination_arrivals:
                        future_garrisons.update(destination_arrivals[to_terr])

                    num_future_garrisons = len(future_garrisons)
                    to_owner = self.territory_owners.get(to_terr, -1)

                    # Check if this will be a multi-garrison situation OR if arriving at ally territory
                    # Use flag positions if:
                    # 1. Multiple garrisons will exist, OR
                    # 2. Territory is owned by someone else (ally) - even if only 1 garrison
                    needs_flag_position = (num_future_garrisons > 1) or (to_owner != -1 and to_owner != order.player)

                    if needs_flag_position:
                        # Use flag position (multi-garrison or allied territory)
                        # For allied territory with 0 current garrisons, treat as if there will be 2
                        # (one for owner, one for arriving ally) for positioning purposes
                        position_count = max(num_future_garrisons, 2)
                        flag_positions = self.get_flag_positions_for_territory(to_terr, to_center[0], to_center[1], position_count)
                        # Assign positions to all CURRENT garrisons first (before arrivals)
                        for player_index in garrisons_to.keys():
                            g = garrisons_to[player_index]
                            if g.get('unmoved', 0) + g.get('moved', 0) > 0:
                                self.assign_garrison_position(to_terr, player_index, position_count)
                        # Now assign position for arriving garrison (will get first available slot)
                        garrison_index = self.assign_garrison_position(to_terr, order.player, position_count)
                        if garrison_index < len(flag_positions):
                            to_pos = flag_positions[garrison_index]
                        else:
                            to_pos = to_center
                    else:
                        # Single garrison destination, arriving at own/neutral territory: use territory center
                        to_pos = to_center

            # Create animation for this movement with THIS ORDER'S composition only
            # Pass extracted_units to preserve xp/level through the animation pipeline
            animation = ArmyAnimation(
                from_territory=from_terr,
                to_territory=to_terr,
                army_count=army_count,
                player=order.player,
                unit_ids=order.unit_ids,
                composition=order_composition,
                from_pos=from_pos,
                to_pos=to_pos,
                units=extracted_units,
                intermediate_territory=order.intermediate_territory  # Captain 2-hop path
            )
            self.active_animations.append(animation)

        # Step 2.5: NOW reassign IDs for all modified territories
        # This happens AFTER all orders are processed, so subsequent orders use correct IDs
        for territory in territories_modified:
            # Reassign IDs in garrison system (for each player's garrison)
            if territory in self.territory_garrisons:
                for player_garrison in self.territory_garrisons[territory].values():
                    for i, unit in enumerate(player_garrison.get('units', [])):
                        unit['id'] = i

            # Also handle legacy army_units if present
            if territory in self.army_units:
                for i, unit in enumerate(self.army_units[territory]):
                    unit['id'] = i

            # IMPORTANT: Cleanup empty garrisons to prevent ghost flags
            self.cleanup_empty_garrisons(territory)

        # Clear executed orders
        self.movement_orders = []

        # Step 3: Animations will be updated by update_animations() in main loop
        # Battles will be detected when animations complete via _process_arrivals()

        # Stay in execution phase until animations complete
        # (turn_phase will be updated when animations finish)
        if self.active_animations:
            self.add_message(f"=== Armies moving... ===")

    # ========================================
    # UTILITY: UNIT COMPOSITION FORMATTING
    # ========================================

    def _format_unit_composition(self, units_dict):
        """
        Format a unit composition dict into a human-readable string.

        Consolidates duplicated formatting logic used throughout battle resolution
        and order execution. Sorts by unit type name for consistent display order.

        Args:
            units_dict: Dict mapping unit type names to counts, e.g. {'Swordsman': 3, 'Archer': 2}

        Returns:
            str: Formatted string like "2 Archer, 3 Swordsman" (sorted alphabetically by type)
        """
        if not units_dict:
            return "none"
        return ", ".join([f"{count} {unit_type}" for unit_type, count in sorted(units_dict.items())])

    # ========================================
    # PHASE 6: EXTRACTED BATTLE RESOLUTION METHODS
    # ========================================
    
    def _calculate_battle_strengths(self, battle, player_armies):
        """
        Calculate effective strength for each player in battle.
        
        Phase 6: Extracted from resolve_battle() for maintainability.
        Handles unit composition analysis and strength calculation.
        """
        player_compositions = {}
        player_effective_strengths = {}
        
        # Get compositions for each player
        for player, count in player_armies:
            if player in battle.army_compositions:
                player_compositions[player] = battle.army_compositions[player]
            else:
                # Fallback to Swordsmen if no composition tracked
                player_compositions[player] = {'Swordsman': count}
        
        # Calculate effective strength for each player against ALL enemies
        for player, count in player_armies:
            # Build combined enemy composition
            enemy_composition = {}
            for enemy_player, enemy_count in player_armies:
                if enemy_player != player:
                    enemy_comp = player_compositions.get(enemy_player, {})
                    for unit_type, unit_count in enemy_comp.items():
                        enemy_composition[unit_type] = enemy_composition.get(unit_type, 0) + unit_count
            
            # Calculate effective strength (pass player and territory for conditional bonuses)
            player_composition = player_compositions[player]
            territory = battle.territory if hasattr(battle, 'territory') else None
            # Veterancy: compute average unit levels for strength bonus
            avg_levels = self.get_unit_avg_levels(territory, player) if territory else None
            effective_strength = self.calculate_army_effective_strength(
                player_composition, enemy_composition, player=player, territory=territory,
                unit_avg_levels=avg_levels
            )
            player_effective_strengths[player] = effective_strength
            
            # Log composition and strength
            comp_str = self._format_unit_composition(player_composition)
            player_name = "Neutral" if player == -1 else f"Player {player + 1}"
            self.add_message(f"  {player_name}: {comp_str} (Effective Strength: {effective_strength:.1f})")
        
        # Veterancy: Pre-calculate bonus XP from enemy levels for each player
        # Stored on battle object so _update_battle_results can award XP after casualties
        battle.enemy_level_xp_bonus = {}
        territory = battle.territory if hasattr(battle, 'territory') else None
        if territory:
            for player, count in player_armies:
                bonus_xp = 0
                # Sum up levels of all enemy units this player would kill
                for enemy_player, enemy_count in player_armies:
                    if enemy_player == player:
                        continue
                    enemy_garrison = self.territory_garrisons.get(territory, {}).get(enemy_player)
                    if enemy_garrison:
                        for unit in enemy_garrison.get('units', []):
                            bonus_xp += unit.get('level', 0)  # +1 XP per enemy level
                battle.enemy_level_xp_bonus[player] = bonus_xp

        return player_compositions, player_effective_strengths

    def _determine_battle_winner(self, player_effective_strengths):
        """
        Determine battle winner based on effective strengths.
        
        Phase 6: Extracted from resolve_battle() for maintainability.
        """
        # Find the player with maximum effective strength
        max_strength = max(player_effective_strengths.values())
        players_with_max = [p for p, s in player_effective_strengths.items() if abs(s - max_strength) < 0.01]
        
        # If only one player has the most effective strength, they win
        if len(players_with_max) == 1:
            winner = players_with_max[0]
            winner_name = "Neutral" if winner == -1 else f"Player {winner + 1}"
            self.add_message(f"  {winner_name} WINS with superior effective strength!")
            return winner, players_with_max
        else:
            # Tie - will need dice roll
            return None, players_with_max

    def _resolve_keep_battle(self, battle, player_armies, player_compositions, territory, defender, original_garrison):
        """
        Resolve two-phase Keep battle: Phase 1 (garrison with counters) + Phase 2 (Keep type-neutral).
        
        This is the proper Keep battle system where:
        - Phase 1: Attackers vs Garrison uses unit type counters
        - Phase 2: Remaining attackers vs Keep is pure numerical
        
        Returns: tuple (winner_player_index, surviving_armies)
        """
        import math

        # Identify attacker(s) - validate that exactly 1 non-defender exists
        non_defenders = [p for p in battle.armies.keys() if p != defender]
        if len(non_defenders) == 0:
            # No attackers found - should not happen, log and return defender wins
            logger.warning(f"Keep battle in {territory}: No attackers found among "
                           f"battle participants {list(battle.armies.keys())} with defender={defender}. "
                           f"Defaulting to defender victory.")
            return defender, original_garrison
        elif len(non_defenders) > 1:
            # Multiple attackers in a Keep battle - not expected by the two-phase system.
            # Use the one with the most armies and log the anomaly.
            logger.warning(f"Keep battle in {territory}: Expected 1 attacker but found "
                           f"{len(non_defenders)} non-defenders: {non_defenders}. "
                           f"Using strongest attacker for Keep battle resolution.")
            attacker = max(non_defenders, key=lambda p: battle.armies.get(p, 0))
        else:
            attacker = non_defenders[0]

        attacker_comp = player_compositions.get(attacker, {})
        garrison_comp = player_compositions.get(defender, {})
        
        self.add_message(f"  Territory has Keep - Two-Phase Combat:")
        self.add_message(f"    Phase 1: Attackers vs Garrison (unit counters apply)")
        self.add_message(f"    Phase 2: Remaining attackers vs Keep (type-neutral)")
        
        # Remove Keep bonus from garrison composition to get actual garrison
        garrison_actual = {}
        total_with_keep = sum(garrison_comp.values())
        if total_with_keep > original_garrison:
            # Scale down to get actual garrison units
            scale = original_garrison / total_with_keep if total_with_keep > 0 else 1
            for ut, uc in garrison_comp.items():
                garrison_actual[ut] = int(uc * scale)
        else:
            garrison_actual = garrison_comp.copy()
        
        # PHASE 1: Attackers vs Garrison (WITH UNIT TYPE COUNTERS)
        if original_garrison > 0:
            # Veterancy: compute average unit levels for attacker and defender
            attacker_avg_levels = self.get_unit_avg_levels(territory, attacker)
            defender_avg_levels = self.get_unit_avg_levels(territory, defender)
            # Calculate EFFECTIVE strengths (counters apply, with conditional bonuses!)
            attacker_strength = self.calculate_army_effective_strength(
                attacker_comp, garrison_actual, player=attacker, territory=territory, is_keep_phase1=True,
                unit_avg_levels=attacker_avg_levels
            )
            garrison_strength = self.calculate_army_effective_strength(
                garrison_actual, attacker_comp, player=defender, territory=territory, is_keep_phase1=False,
                unit_avg_levels=defender_avg_levels
            )

            comp_str_attacker = self._format_unit_composition(attacker_comp)
            comp_str_garrison = self._format_unit_composition(garrison_actual)

            self.add_message(f"  Phase 1: {comp_str_attacker} (Effective: {attacker_strength:.1f}) vs {comp_str_garrison} (Effective: {garrison_strength:.1f})")

            # Determine Phase 1 winner based on effective strength
            attacker_count = sum(attacker_comp.values())
            garrison_count = sum(garrison_actual.values())

            if attacker_strength > garrison_strength:
                # Attackers win Phase 1
                # Casualties scale with strength ratio — dominant attackers lose fewer
                strength_ratio = garrison_strength / attacker_strength if attacker_strength > 0 else 1.0
                # Overwhelming advantage: 0 casualties if strength >= 10:1 ratio
                if attacker_strength >= OVERWHELMING_ADVANTAGE_RATIO * garrison_strength:
                    attacker_casualties = 0
                else:
                    attacker_casualties = max(1, round(garrison_count * strength_ratio))
                remaining_attackers = max(0, attacker_count - attacker_casualties)
                remaining_garrison = 0

                # Apply casualties to defending garrison(s) - allies die first
                has_allied_defenders = (hasattr(battle, 'allied_defenders') and
                                       len(battle.allied_defenders) > 0)

                if has_allied_defenders:
                    # Multi-garrison defense - apply casualties using priority system
                    casualties_by_player = self.apply_multi_garrison_casualties(
                        territory, garrison_count, attacker_comp, defender
                    )

                    # Log casualties by player
                    for player_index, player_casualties in casualties_by_player.items():
                        if player_casualties:
                            casualty_str = self._format_unit_composition(player_casualties)
                            player_name = self.get_player_name(player_index)
                            if player_index == defender:
                                self.add_message(f"      Owner ({player_name}) casualties: {casualty_str}")
                            else:
                                self.add_message(f"      Ally ({player_name}) casualties: {casualty_str}")
                else:
                    # Single garrison - casualties already handled by strength calculation
                    casualties_by_type = self.apply_casualties_with_priority(territory, garrison_count, attacker_comp)
                    if casualties_by_type:
                        casualty_str = self._format_unit_composition(casualties_by_type)
                        self.add_message(f"      Garrison casualties: {casualty_str}")

                self.add_message(f"    Garrison eliminated. {remaining_attackers} attacker(s) remain.")
            elif garrison_strength > attacker_strength:
                # Garrison wins Phase 1
                # Casualties scale with strength ratio — dominant garrison loses fewer
                strength_ratio = attacker_strength / garrison_strength if garrison_strength > 0 else 1.0
                # Overwhelming advantage: 0 casualties if strength >= 10:1 ratio
                if garrison_strength >= OVERWHELMING_ADVANTAGE_RATIO * attacker_strength:
                    garrison_casualties = 0
                else:
                    garrison_casualties = max(1, round(attacker_count * strength_ratio))
                remaining_attackers = 0
                remaining_garrison = max(0, garrison_count - garrison_casualties)

                # Apply casualties to defending garrison(s)
                has_allied_defenders = (hasattr(battle, 'allied_defenders') and
                                       len(battle.allied_defenders) > 0)
                casualties = garrison_count - remaining_garrison

                if has_allied_defenders and casualties > 0:
                    # Multi-garrison defense - apply casualties using priority system
                    casualties_by_player = self.apply_multi_garrison_casualties(
                        territory, casualties, attacker_comp, defender
                    )

                    # Log casualties by player
                    for player_index, player_casualties in casualties_by_player.items():
                        if player_casualties:
                            casualty_str = self._format_unit_composition(player_casualties)
                            player_name = self.get_player_name(player_index)
                            if player_index == defender:
                                self.add_message(f"      Owner ({player_name}) casualties: {casualty_str}")
                            else:
                                self.add_message(f"      Ally ({player_name}) casualties: {casualty_str}")
                elif casualties > 0:
                    # Single garrison
                    casualties_by_type = self.apply_casualties_with_priority(territory, casualties, attacker_comp)
                    if casualties_by_type:
                        casualty_str = self._format_unit_composition(casualties_by_type)
                        self.add_message(f"      Garrison casualties: {casualty_str}")

                self.add_message(f"    Attackers repelled. {remaining_garrison} garrison survives.")
            else:
                # Perfect tie in Phase 1 - mutual elimination
                remaining_attackers = 0
                remaining_garrison = 0

                # All garrison units eliminated - apply casualties
                has_allied_defenders = (hasattr(battle, 'allied_defenders') and
                                       len(battle.allied_defenders) > 0)

                if has_allied_defenders:
                    casualties_by_player = self.apply_multi_garrison_casualties(
                        territory, garrison_count, attacker_comp, defender
                    )

                    for player_index, player_casualties in casualties_by_player.items():
                        if player_casualties:
                            casualty_str = self._format_unit_composition(player_casualties)
                            player_name = self.get_player_name(player_index)
                            if player_index == defender:
                                self.add_message(f"      Owner ({player_name}) casualties: {casualty_str}")
                            else:
                                self.add_message(f"      Ally ({player_name}) casualties: {casualty_str}")
                else:
                    casualties_by_type = self.apply_casualties_with_priority(territory, garrison_count, attacker_comp)
                    if casualties_by_type:
                        casualty_str = self._format_unit_composition(casualties_by_type)
                        self.add_message(f"      Garrison casualties: {casualty_str}")

                self.add_message(f"    Garrison and attackers eliminate each other.")
        else:
            # No garrison - attackers proceed directly to Keep
            remaining_attackers = sum(attacker_comp.values())
            remaining_garrison = 0
            self.add_message(f"  Phase 1: No garrison present. Attackers proceed to Keep.")
        
        # PHASE 2: Remaining Attackers vs Keep (TYPE-NEUTRAL, PURE NUMBERS)
        keep_defense = battle.keep_bonus

        if remaining_attackers > 0:
            # Calculate attacker strength with Divide and Conquer bonus (if applicable)
            attacker_phase2_strength = float(remaining_attackers)

            # Apply Divide and Conquer bonus for Archers in Phase 2
            if self.player_divide_conquer_bonus[attacker]:
                # Calculate weighted strength bonus based on Archer ratio
                bonus_strength = 0.0
                total_attackers = sum(attacker_comp.values())

                if total_attackers > 0:
                    # Only Archers get +50% strength in Phase 2
                    archer_count = attacker_comp.get('Archer', 0)
                    if archer_count > 0:
                        archer_ratio = archer_count / total_attackers
                        remaining_archers = remaining_attackers * archer_ratio
                        bonus_strength = remaining_archers * 0.50

                attacker_phase2_strength += bonus_strength
                self.add_message(f"  Phase 2: {remaining_attackers} remaining attacker(s) (Effective: {attacker_phase2_strength:.1f}) vs Keep (+{keep_defense} armies)")
            else:
                self.add_message(f"  Phase 2: {remaining_attackers} remaining attacker(s) vs Keep (+{keep_defense} armies)")

            if attacker_phase2_strength > keep_defense:
                # Attackers breach Keep
                surviving_armies = remaining_attackers - keep_defense
                winner = attacker
                self.add_message(f"    Keep destroyed! Attackers win with {surviving_armies} army(ies).")
            elif abs(attacker_phase2_strength - keep_defense) < 0.01:
                # Exact tie - all destroyed
                surviving_armies = 0
                winner = defender  # Keep holds by tiebreaker
                self.add_message(f"    Perfect clash! Keep barely holds. All armies destroyed.")
            else:
                # Keep holds
                surviving_armies = remaining_garrison  # What survived from garrison
                winner = defender
                if remaining_garrison == 0:
                    self.add_message(f"    Keep holds! Attackers destroyed. No garrison remains.")
                else:
                    self.add_message(f"    Keep holds! Attackers destroyed. {remaining_garrison} garrison survives.")
        else:
            # No attackers reached Phase 2
            surviving_armies = remaining_garrison
            winner = defender
            if original_garrison > 0:
                self.add_message(f"  Garrison successfully defended. {surviving_armies} army(ies) remain.")
            else:
                self.add_message(f"  Keep successfully defended alone!")
        
        return winner, surviving_armies

    def _apply_battle_casualties_simple(self, battle, winner, player_armies, player_compositions, territory, player_effective_strengths=None):
        """
        Apply casualties using simple system (no Keep bonus).
        Casualties scale with strength ratio — dominant forces lose fewer units.

        Phase 6: Extracted from resolve_battle() for maintainability.
        """
        winner_count = battle.armies[winner]
        loser_count = sum(count for player, count in player_armies if player != winner)

        # Scale casualties by effective strength ratio (counters reduce losses)
        if player_effective_strengths:
            winner_strength = player_effective_strengths.get(winner, 0)
            loser_strength = sum(s for p, s in player_effective_strengths.items() if p != winner)
            strength_ratio = loser_strength / winner_strength if winner_strength > 0 else 1.0
            # Overwhelming advantage: winner takes 0 casualties if strength >= 10:1 ratio
            if winner_strength >= OVERWHELMING_ADVANTAGE_RATIO * loser_strength:
                casualties_int = 0
            else:
                casualties_int = max(1, round(loser_count * strength_ratio))
        else:
            # Fallback: old behavior if no strength data available
            casualties_int = loser_count

        # Calculate survivors
        surviving_armies = max(1, winner_count - casualties_int)
        casualties = winner_count - surviving_armies

        # Apply casualties to winner's army using priority system
        if winner == battle.original_owner:
            # Winner is defender - check if there are allied defenders
            # Get enemy composition for priority calculation
            enemy_comp = {}
            for p in player_armies:
                if p[0] != winner:
                    comp = player_compositions.get(p[0], {})
                    for ut, uc in comp.items():
                        enemy_comp[ut] = enemy_comp.get(ut, 0) + uc

            # Check if there are allied garrisons defending this territory
            has_allied_defenders = (hasattr(battle, 'allied_defenders') and
                                   len(battle.allied_defenders) > 0)

            if has_allied_defenders:
                # Use multi-garrison casualty system (allies die first, owner dies last)
                casualties_by_player = self.apply_multi_garrison_casualties(
                    territory, casualties, enemy_comp, battle.original_owner
                )

                # Log casualties by player
                for player_index, player_casualties in casualties_by_player.items():
                    if player_casualties:
                        casualty_str = self._format_unit_composition(player_casualties)
                        if player_index == battle.original_owner:
                            self.add_message(f"  Owner (Player {player_index + 1}) casualties: {casualty_str}")
                        else:
                            self.add_message(f"  Ally (Player {player_index + 1}) casualties: {casualty_str}")
            else:
                # Single garrison - use existing priority system
                casualties_by_type = self.apply_casualties_with_priority(territory, casualties, enemy_comp)

                # Log casualties
                if casualties_by_type:
                    casualty_str = self._format_unit_composition(casualties_by_type)
                    self.add_message(f"  Defender casualties: {casualty_str}")
        # Note: For attacker winners, casualty priority is handled in _update_battle_results
        # by sorting surviving units by level DESC (highest-level units survive first)

        if casualties > 0:
            self.add_message(f"  Winner lost {casualties} armies in battle. {surviving_armies} survive.")
        else:
            self.add_message(f"  Winner suffers no casualties. {surviving_armies} armies remain.")

        return surviving_armies

    def _handle_battle_tie_with_dice(self, battle, players_with_max, player_armies, territory):
        """
        Handle battle tie using dice roll system.
        
        Phase 6: Extracted from resolve_battle() for maintainability.
        """
        import random
        
        # Roll dice only for tied players
        results = {}
        for player in players_with_max:
            army_count = battle.armies[player]
            roll = sum(random.randint(1, 6) for _ in range(army_count))
            results[player] = roll
            player_label = "Neutral" if player == -1 else f"Player {player + 1}"
            self.add_message(f"  {player_label} ({army_count} armies) rolls: {roll}")
        
        # Store roll results for display
        battle.dice_results = results
        
        # Find winner (highest roll)
        winner = max(results, key=results.get)
        winner_roll = results[winner]
        winner_count = battle.armies[winner]
        
        # Check for tie in dice
        tied_in_dice = [p for p, roll in results.items() if roll == winner_roll]
        
        if len(tied_in_dice) > 1:
            # Perfect tie - all armies destroyed, territory neutral
            # No new owner (becomes neutral), so Champion of the People doesn't apply
            self.destroy_buildings(territory, battle.original_owner, new_owner=-1)

            self.territory_owners[territory] = -1  # Neutral
            self._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
            self.invalidate_income_cache()  # FPS OPT: Ownership affects income
            self.invalidate_army_count_cache()  # FPS OPT: Army counts change on ownership change
            self.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses
            self.armies[territory] = 0
            self.armies_unmoved[territory] = 0
            self.armies_moved[territory] = 0

            # BUG FIX: Clear all garrisons (was missing, causing phantom army flags on map)
            # This is the source of truth for army rendering, must be cleared
            self.territory_garrisons[territory] = {}

            # Clear army_units
            if territory in self.army_units:
                self.army_units[territory] = []

            self.add_message(f"  PERFECT TIE! All armies destroyed. {territory} becomes neutral.")
            return -1, 0
        else:
            # Winner determined by dice
            surviving_armies = 1  # Winner keeps 1 army
            casualties = winner_count - 1
            
            winner_name = "Neutral" if winner == -1 else f"Player {winner + 1}"
            if casualties > 0:
                self.add_message(f"  {winner_name} WINS! Lost {casualties} battalions, {surviving_armies} remains")
            else:
                self.add_message(f"  {winner_name} WINS! {surviving_armies} battalion remains")
            
            return winner, surviving_armies

    def _update_battle_results(self, battle, winner, surviving_armies, player_compositions, territory):
        """
        Update game state with battle results.
        
        Phase 6: Extracted from resolve_battle() for maintainability.
        """
        if winner == -1 and surviving_armies == 0:
            # Perfect tie handled in dice method (all armies destroyed, territory neutral)
            battle.resolved = True
            battle.winner = -1
            return
        # Note: winner == -1 with surviving_armies > 0 means neutral garrison won — continue with normal cleanup
        
        # Veterancy: Check if territory's Keep has a Hero BEFORE buildings are destroyed
        # (destroy_buildings kills heroes, so we must check first)
        battle._keep_had_hero = False
        if battle.original_owner != winner:
            buildings = self.buildings.get(territory, {})
            for plot_idx, btype in buildings.items():
                if btype == 'Keep':
                    if self.keep_has_hero(territory, plot_idx, battle.original_owner):
                        battle._keep_had_hero = True
                        break

        # Destroy buildings if territory changes hands
        # Champion of the People: Pass winner as new_owner to preserve Farms/Mines
        if battle.original_owner != winner:
            self.destroy_buildings(territory, battle.original_owner, new_owner=winner)

        # Safe Haven & Scavenge the Fallen: Check abilities for losing players
        # This needs to happen BEFORE clearing old units
        for loser_player, loser_army_count in battle.armies.items():
            if loser_player == winner:
                continue  # Skip winner
            if loser_player == -1:
                continue  # Neutral armies have no heroes, gold, or abilities

            # Only trigger if loser had armies (actual battle, not empty territory capture)
            if loser_army_count > 0:
                # Scavenge the Fallen: Grant gold to losing player with Darius Brennhen
                if self.player_has_darius_brennhen(loser_player):
                    scavenge_gold = 30
                    self.player_gold[loser_player] += scavenge_gold
                    self.add_message(f"  Scavenge the Fallen: Player {loser_player + 1} gains {scavenge_gold} Gold from the battle!")

            # Safe Haven: Check if loser can retreat a unit to hero's Keep
            safe_haven_territories = self.get_safe_haven_territories(loser_player)
            if territory in safe_haven_territories:
                # Get loser's composition
                loser_comp = player_compositions.get(loser_player, {})
                if loser_comp:
                    # Get hero's Keep territory (Brennhen or Regnus Aevencourne)
                    if 'Darius Brennhen' in self.heroes[loser_player]:
                        brennhen_data = self.heroes[loser_player]['Darius Brennhen']
                    else:
                        brennhen_data = self.heroes[loser_player]['Regnus Aevencourne']
                    keep_territory = brennhen_data['keep_territory']

                    # Check if Keep territory has room for one more unit
                    # Legacy counter fix: use get_territory_total_armies for allied garrisons
                    current_keep_armies = self.get_territory_total_armies(keep_territory)
                    if current_keep_armies < self.MAX_ARMIES_PER_TERRITORY:
                        # Pick a random unit type from loser's composition
                        import random
                        available_types = list(loser_comp.keys())
                        retreating_unit_type = random.choice(available_types)

                        # Add retreating unit to Keep territory
                        if keep_territory not in self.army_units:
                            self.army_units[keep_territory] = []

                        # Find next available ID
                        existing_ids = [u['id'] for u in self.army_units[keep_territory]]
                        next_id = 0
                        while next_id in existing_ids:
                            next_id += 1

                        # Create retreating unit (exhausted from battle, loses XP)
                        # Phase 2E: Use _make_unit() factory for consistent unit dict creation
                        self.army_units[keep_territory].append(self._make_unit(retreating_unit_type, next_id))

                        # M4 fix: Update garrison system alongside legacy counters
                        self.add_garrison(
                            keep_territory, loser_player,
                            unmoved=0, moved=1,
                            units=[self._make_unit(retreating_unit_type, next_id)]
                        )
                        # Update legacy army counters for Keep territory
                        self.armies_moved[keep_territory] += 1
                        self.armies[keep_territory] = self.armies_moved[keep_territory] + self.armies_unmoved[keep_territory]

                        # Log the retreat
                        self.add_message(f"  Safe Haven: 1 {retreating_unit_type} from Player {loser_player + 1} retreats to {keep_territory}!")

        # Set territory ownership
        self.territory_owners[territory] = winner
        self._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
        self.invalidate_income_cache()  # FPS OPT: Ownership affects income
        self.invalidate_army_count_cache()  # FPS OPT: Army counts change on ownership change
        self.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses

        # Tutorial hook: notify territory conquered (only if ownership changed)
        if self.tutorial_mission and battle.original_owner != winner:
            self.tutorial_mission.notify_event(
                'territory_conquered',
                territory=territory,
                new_owner=winner
            )

        # Player Level: award XP for conquering enemy territory with a battle
        if battle.original_owner != winner:
            self._track_stat(winner, 'xp_earned', 8)

        # Capital Assault: Check if conquered territory is enemy's capital
        # Note: Allies cannot eliminate each other - only enemies can capture capitals
        if self.victory_condition == "Capital Assault":
            for player_index, capital in self.player_starting_territories.items():
                # Check: capital matches, not self, and not an ally (enemies only)
                if capital == territory and player_index != winner and not self.are_allies(winner, player_index):
                    # Capital conquered - eliminate the player
                    logger.info(f"[CAPITAL ASSAULT] Player {winner + 1} conquered Player {player_index + 1}'s capital!")
                    self.eliminate_player(player_index)
                    # R9: Note: check_victory() is called at end of _update_battle_results()

        # Enforce army limit on surviving armies
        if surviving_armies > self.MAX_ARMIES_PER_TERRITORY:
            excess = surviving_armies - self.MAX_ARMIES_PER_TERRITORY
            self.add_message(f"  Army overflow: {excess} excess armies disbanded (territory limit: {self.MAX_ARMIES_PER_TERRITORY})")
            surviving_armies = self.MAX_ARMIES_PER_TERRITORY

        # Veterancy-aware survivor preservation: use actual surviving unit objects
        # from the garrison after casualties were applied (preserves XP/level).
        # The casualty system already removed dead units from army_units/garrisons.
        survivor_units = []
        if surviving_armies > 0:
            # Try to get actual surviving units from winner's garrison (preserves XP)
            winner_garrison = self.territory_garrisons.get(territory, {}).get(winner)
            if winner_garrison and winner_garrison.get('units'):
                # Surviving units are whatever remains after apply_casualties_with_priority
                actual_survivors = list(winner_garrison['units'])
                # Sort by level DESC so highest-level units are kept if we need to trim
                actual_survivors.sort(key=lambda u: u.get('level', 0), reverse=True)
                survivor_units = actual_survivors[:surviving_armies]
            elif territory in self.army_units and self.army_units[territory]:
                # Fallback to army_units (legacy path)
                actual_survivors = list(self.army_units[territory])
                actual_survivors.sort(key=lambda u: u.get('level', 0), reverse=True)
                survivor_units = actual_survivors[:surviving_armies]

            # If we couldn't find actual units (edge case), create from composition
            if not survivor_units:
                winner_label = "Neutral" if winner == -1 else f"Player {winner + 1}"
                logger.warning(f"[UNIT_TYPE_DIAG] _update_battle_results fallback: no survivor units found "
                               f"for {winner_label} at {territory} ({surviving_armies} should survive). "
                               f"Reconstructing from composition.")
                winner_comp = player_compositions.get(winner, {})
                unit_id = 0
                if winner_comp:
                    total_winner_armies = sum(winner_comp.values())
                    for unit_type, count in winner_comp.items():
                        proportion = count / total_winner_armies if total_winner_armies > 0 else 0
                        allocated = max(1, int(surviving_armies * proportion)) if proportion > 0 else 0
                        for _ in range(min(allocated, count)):
                            if unit_id >= surviving_armies:
                                break
                            # Phase 2E: Use _make_unit() factory for consistent unit dict creation
                            survivor_units.append(self._make_unit(unit_type, unit_id))
                            unit_id += 1
                # Fill remaining with Swordsmen if needed
                if len(survivor_units) < surviving_armies:
                    logger.warning(f"[UNIT_TYPE_DIAG] _update_battle_results: filling {surviving_armies - len(survivor_units)} "
                                   f"remaining survivor slots with default Swordsmen at {territory}")
                while len(survivor_units) < surviving_armies:
                    # Phase 2E: Use _make_unit() factory for consistent unit dict creation
                    survivor_units.append(self._make_unit('Swordsman', len(survivor_units)))

            # Mark all survivors as 'moved' (just fought) and re-index IDs
            for idx, unit in enumerate(survivor_units):
                unit['id'] = idx
                unit['status'] = 'moved'
                unit['order'] = None

            # --- Award battle XP to winning survivors ---
            # Only winners gain XP (confirmed). Calculate total XP from killed enemies.
            total_enemies_killed = sum(c for p, c in battle.armies.items() if p != winner)
            if total_enemies_killed > 0:
                # Calculate XP: 10 + enemy_level per enemy killed
                # We need to estimate enemy levels from garrison data before they were cleared
                # Use battle's stored composition + avg levels if available
                total_battle_xp = total_enemies_killed * self.BATTLE_XP_PER_KILL
                # Add bonus XP for high-level enemies killed
                # Check if battle has stored enemy unit level data
                if hasattr(battle, 'enemy_level_xp_bonus'):
                    total_battle_xp += battle.enemy_level_xp_bonus.get(winner, 0)
                # Hero Keep destruction bonus: +100 XP flat when destroying a Keep with a Hero
                if getattr(battle, '_keep_had_hero', False) and battle.original_owner != winner:
                    total_battle_xp += self.HERO_KEEP_DESTROY_XP
                    self.add_message(f"  Veterancy: +{self.HERO_KEEP_DESTROY_XP} XP bonus for destroying Hero Keep!")
                for unit in survivor_units:
                    self.award_unit_xp(unit, total_battle_xp)

        # IMPORTANT: Clear ALL garrisons in the territory (removes losing defenders)
        # Then set only the winner's garrison
        self.territory_garrisons[territory] = {}

        # Set garrison as source of truth (just fought, can't move)
        self.set_garrison_armies(territory, winner, unmoved=0, moved=surviving_armies, units=survivor_units)

        battle.resolved = True
        battle.winner = winner
        battle.surviving_armies = surviving_armies

        # Game logger: record battle resolution event
        if self.game_logger:
            self.game_logger.record_battle(territory, battle.armies, winner, self.turn_number)

        # Track units_killed stats for recap screen
        if winner >= 0:
            # Winner killed all loser armies
            total_losers_killed = sum(c for p, c in battle.armies.items() if p != winner)
            self._track_stat(winner, 'units_killed', total_losers_killed)
            # Losers collectively killed winner's casualties (proportional credit)
            winner_original = battle.armies.get(winner, 0)
            winner_casualties = winner_original - surviving_armies
            if winner_casualties > 0:
                losers = [(p, c) for p, c in battle.armies.items() if p != winner and c > 0]
                total_loser_armies = sum(c for _, c in losers)
                for loser_p, loser_c in losers:
                    credit = round(winner_casualties * loser_c / total_loser_armies) if total_loser_armies > 0 else 0
                    self._track_stat(loser_p, 'units_killed', max(0, credit))

        # IMPORTANT: Cleanup any empty garrisons (belt & suspenders)
        self.cleanup_empty_garrisons(territory)

        # Check for victory
        self.check_victory()

    def resolve_battle(self, battle_index):
        """
        Resolve a battle using deterministic combat with unit type effectiveness.
        
        Phase 6: Refactored into sub-methods for maintainability.
        Main method now orchestrates battle resolution:
        1. Calculate strengths - _calculate_battle_strengths()
        2. Determine winner - _determine_battle_winner()
        3. Apply casualties - _apply_battle_casualties_*()
        4. Handle ties - _handle_battle_tie_with_dice()
        5. Update results - _update_battle_results()
        
        Battle System (Tier 3):
            - Rock-Paper-Scissors counter system
            - Deterministic outcome (no dice unless tied)
            - Unit composition matters significantly
            - Terrain effects from Keep defense bonus
        
        Unit Counter System:
            Swordsman > Pikeman > Cavalry > Archer > Swordsman
            - Countered units: 0.75x effectiveness
            - Counter units: 1.25x effectiveness
            - Neutral matchup: 1.0x effectiveness
        
        Combat Formula:
            For each player:
            1. Calculate base strength = sum(unit_count * base_strength)
            2. Apply counter modifiers based on opponent composition
            3. Add Keep defense bonus (if defender has fortress)
            4. Player with highest effective strength wins
        
        Keep Defense Bonus:
            - Two-phase combat: Garrison â†’ Keep
            - Adds +2 armies worth of strength to defender
            - Only applies to territory's original owner
        
        Phase 6 Refactoring Benefits:
            - Each method < 250 lines
            - Clear single responsibilities
            - Much easier to modify battle logic
            - Better code organization
        
        Args:
            battle_index: Index into self.pending_battles list
        
        Returns:
            bool: True if battle resolved successfully, False if invalid/already resolved
        """
        # Validate battle
        if battle_index < 0 or battle_index >= len(self.pending_battles):
            return False
        
        battle = self.pending_battles[battle_index]
        if battle.resolved:
            return False
        
        territory = battle.territory
        self.add_message(f"=== Resolving battle at {territory} ===")
        
        # Get army counts and compositions
        player_armies = list(battle.armies.items())
        
        # Check for Keep FIRST
        defender = battle.original_owner
        has_keep = (hasattr(battle, 'keep_bonus_player') and 
                   battle.keep_bonus_player is not None and 
                   battle.keep_bonus > 0)
        
        if has_keep:
            # KEEP BATTLE: Use two-phase combat system
            # Phase 1 with counters, Phase 2 type-neutral
            # This determines the winner organically through combat
            
            # Step 1: Get compositions
            player_compositions = {}
            for player, count in player_armies:
                if player in battle.army_compositions:
                    player_compositions[player] = battle.army_compositions[player]
                else:
                    player_compositions[player] = {'Swordsman': count}
            
            # Step 2: Run two-phase Keep battle (determines winner internally)
            original_garrison = battle.original_garrison if hasattr(battle, 'original_garrison') else 0
            winner, surviving_armies = self._resolve_keep_battle(
                battle, player_armies, player_compositions, territory, defender, original_garrison
            )
            
            # Step 3: Update game state
            self._update_battle_results(battle, winner, surviving_armies, player_compositions, territory)
        
        else:
            # NORMAL BATTLE: Use effective strength to determine winner
            
            # Step 1: Calculate effective strengths (with counters)
            player_compositions, player_effective_strengths = self._calculate_battle_strengths(battle, player_armies)
            
            # Step 2: Determine winner based on effective strength
            winner, players_with_max = self._determine_battle_winner(player_effective_strengths)
            
            # Step 3: Apply casualties or handle tie
            if winner is not None:
                # Clear winner - apply strength-scaled casualties
                surviving_armies = self._apply_battle_casualties_simple(
                    battle, winner, player_armies, player_compositions, territory, player_effective_strengths
                )
                
                # Step 4: Update game state
                self._update_battle_results(battle, winner, surviving_armies, player_compositions, territory)
            
            else:
                # Tie - use dice roll system
                self.add_message(f"  TIE detected! Rolling dice to determine winner...")
                winner, surviving_armies = self._handle_battle_tie_with_dice(
                    battle, players_with_max, player_armies, territory
                )
                
                # Update game state
                self._update_battle_results(battle, winner, surviving_armies, player_compositions, territory)
        
        # Tutorial hook: notify battle resolved (only if player 0 won)
        if self.tutorial_mission and winner == 0:
            self.tutorial_mission.notify_event('battle_won', territory=territory)

        # Enforce army limits after battle resolution (winner may exceed cap)
        self._enforce_army_limits()

        # Cleanup
        self.pending_battles.pop(battle_index)

        # Check if more battles remain
        if len(self.pending_battles) == 0:
            self.add_message("=== All battles resolved! ===")
            # Set flag to indicate turn should advance after popup closes
            # Don't advance immediately - wait for player to close battle results popup
            self.ready_to_advance_turn = True
            logger.info(f"[TURN_DEBUG] ready_to_advance_turn set to True (all battles resolved, turn_phase={self.turn_phase})")

        return True

    def _process_arrivals(self):
        """
        Process all pending army arrivals after animations complete.
        This handles the actual army movement and battle detection.
        """
        # Deferred import to avoid circular import (Battle defined in game_state/__init__.py)
        from game_state import Battle
        # Track which territories will receive armies from which players
        # Format: {territory: {player: army_count}}
        incoming_armies = {}
        moving_compositions = {}  # {(to_territory, player): {unit_type: count}}
        # Veterancy: aggregate actual unit dicts to preserve xp/level through movement
        moving_units = {}  # {(to_territory, player): [unit_dicts]}

        for anim in self.pending_arrivals:
            to_terr = anim.to_territory
            player = anim.player
            army_count = anim.army_count

            # Track composition key
            comp_key = (to_terr, player)

            # Store composition for battle
            if comp_key not in moving_compositions:
                moving_compositions[comp_key] = {}
            for unit_type, count in anim.composition.items():
                moving_compositions[comp_key][unit_type] = moving_compositions[comp_key].get(unit_type, 0) + count

            # Aggregate actual unit dicts from animation (preserves xp/level)
            if anim.units:
                if comp_key not in moving_units:
                    moving_units[comp_key] = []
                moving_units[comp_key].extend(anim.units)

            # Track arrivals
            if to_terr not in incoming_armies:
                incoming_armies[to_terr] = {}
            if player not in incoming_armies[to_terr]:
                incoming_armies[to_terr][player] = 0
            incoming_armies[to_terr][player] += army_count

            self.add_message(f"Player {player + 1}: {army_count} armies arrive in {to_terr}")

        # Clear pending arrivals
        self.pending_arrivals = []

        # Now process arrivals and detect battles (same logic as execute_all_orders)
        self.pending_battles = []

        for territory, player_armies in incoming_armies.items():
            current_owner = self.territory_owners[territory]
            # Use LIVE garrison count from garrison system (includes all player garrisons)
            current_garrison = self.get_territory_total_unmoved(territory) + self.get_territory_total_moved(territory)

            # Check for Keep defense (works even without garrison!)
            keep_bonus = 0
            has_keep = False
            keep_plot_with_hero = None
            if current_owner != -1 and territory in self.buildings:
                for plot_index, building_type in self.buildings[territory].items():
                    if building_type == 'Keep':
                        has_keep = True
                        keep_bonus = 2

                        # Check if this Keep has a hero and player has Improved Last Resort
                        if self.keep_has_hero(territory, plot_index, current_owner):
                            hero_defense_bonus = self.player_hero_keep_defense_bonus[current_owner]
                            if hero_defense_bonus > 0:
                                keep_bonus += hero_defense_bonus
                                keep_plot_with_hero = plot_index
                        break

            # Check if neutral territory has a garrison (Neutral Armies game mode)
            has_neutral_garrison = (
                current_owner == -1 and
                territory in self.territory_garrisons and
                -1 in self.territory_garrisons[territory] and
                (self.territory_garrisons[territory][-1].get('unmoved', 0) +
                 self.territory_garrisons[territory][-1].get('moved', 0)) > 0
            )

            # Add defender's forces (garrison + Keep) ONLY if there will be a battle
            # Check if there will be a battle (multiple players arriving, or attacker vs defender/neutral)
            potential_battle = len(incoming_armies[territory]) > 1 or (
                len(incoming_armies[territory]) == 1 and
                ((current_owner != -1 and current_owner not in incoming_armies[territory]) or
                 has_neutral_garrison)
            )

            # Add ALL allied garrisons to battle (owner + allies with garrisons)
            # IMPORTANT: In multi-garrison territories, ALL allied defenders should fight together
            if current_owner != -1 and potential_battle:
                # Get all garrisons in this territory
                all_garrisons = self.territory_garrisons.get(territory, {})

                # Add owner's garrison
                owner_garrison_data = all_garrisons.get(current_owner)
                owner_garrison_count = 0
                if owner_garrison_data:
                    owner_garrison_count = owner_garrison_data.get('unmoved', 0) + owner_garrison_data.get('moved', 0)

                # Add allied garrisons (players who are allied with owner and have garrison here)
                for garrison_player, garrison_data in all_garrisons.items():
                    garrison_count = garrison_data.get('unmoved', 0) + garrison_data.get('moved', 0)
                    if garrison_count <= 0:
                        continue

                    # Check if this player should defend (owner OR ally of owner)
                    is_defender = (garrison_player == current_owner or
                                 (garrison_player not in incoming_armies[territory] and
                                  self.are_allies(garrison_player, current_owner)))

                    if is_defender:
                        if garrison_player not in player_armies:
                            player_armies[garrison_player] = 0
                        player_armies[garrison_player] += garrison_count

                        # Get composition for this garrison
                        garrison_comp = garrison_data.get('units', [])
                        if garrison_comp:
                            comp_key = (territory, garrison_player)
                            if comp_key not in moving_compositions:
                                moving_compositions[comp_key] = {}
                            for unit in garrison_comp:
                                unit_type = unit.get('type', 'Swordsman')
                                moving_compositions[comp_key][unit_type] = moving_compositions[comp_key].get(unit_type, 0) + 1

                # Add Keep defense (only for owner)
                if has_keep and (owner_garrison_count > 0 or current_owner not in player_armies):
                    if current_owner not in player_armies:
                        player_armies[current_owner] = 0
                    player_armies[current_owner] += keep_bonus
                    if current_garrison > 0:
                        self.add_message(f"Keep in {territory} provides +{keep_bonus} defense bonus!")
                    else:
                        self.add_message(f"Keep in {territory} defends alone with {keep_bonus} armies!")

            # Neutral armies defend their territory (no Keep, no allies — just garrison)
            elif has_neutral_garrison and potential_battle:
                neutral_garrison = self.territory_garrisons[territory][-1]
                neutral_count = neutral_garrison.get('unmoved', 0) + neutral_garrison.get('moved', 0)
                if neutral_count > 0:
                    player_armies[-1] = neutral_count
                    # Add neutral army composition for battle resolution
                    neutral_units = neutral_garrison.get('units', [])
                    if neutral_units:
                        comp_key = (territory, -1)
                        moving_compositions[comp_key] = {}
                        for unit in neutral_units:
                            unit_type = unit.get('type', 'Swordsman')
                            moving_compositions[comp_key][unit_type] = moving_compositions[comp_key].get(unit_type, 0) + 1

            # Count unique players involved
            unique_players = len(player_armies)

            if unique_players == 1:
                # Uncontested - just update ownership and garrison
                winner = list(player_armies.keys())[0]
                winner_armies = player_armies[winner]

                # Check if this is a reinforcement (same owner), ally reinforcement, or conquest
                # Own reinforcement if moving to territory you already own (regardless of garrison)
                is_own_reinforcement = (winner == current_owner and current_owner != -1)
                is_ally_reinforcement = (current_owner != -1 and current_owner != winner and
                                        self.are_allies(winner, current_owner))

                # For own reinforcements, add the existing garrison to the arriving armies
                if is_own_reinforcement:
                    winner_armies += current_garrison
                    # Enforce army limit
                    if winner_armies > self.MAX_ARMIES_PER_TERRITORY:
                        excess = winner_armies - self.MAX_ARMIES_PER_TERRITORY
                        self.add_message(f"Army overflow in {territory}: {excess} excess armies disbanded (limit: {self.MAX_ARMIES_PER_TERRITORY})")
                        winner_armies = self.MAX_ARMIES_PER_TERRITORY

                # Get composition for arriving forces
                comp_key = (territory, winner)
                composition = moving_compositions.get(comp_key, {})

                # Handle buildings for conquests (Champion of the People ability)
                if not is_own_reinforcement and not is_ally_reinforcement and current_owner != -1:
                    # This is a conquest - destroy buildings (or preserve Farms/Mines if Champion active)
                    self.destroy_buildings(territory, current_owner, new_owner=winner)

                if is_own_reinforcement:
                    # OWN REINFORCEMENT: Merge arriving armies into owner's garrison
                    # Use multi-garrison system
                    # Add arriving armies to owner's garrison
                    units = []
                    arriving_count = winner_armies - current_garrison  # Actual count after caps

                    # FIX: Calculate proper unit IDs starting from existing garrison's max ID
                    # This prevents duplicate IDs that cause unit selection bugs
                    existing_garrison = self.territory_garrisons.get(territory, {}).get(winner)
                    existing_units = existing_garrison.get('units', []) if existing_garrison else []
                    next_id = max([u['id'] for u in existing_units], default=-1) + 1

                    # Veterancy: use actual unit dicts from animation to preserve xp/level
                    arriving_units = moving_units.get(comp_key, [])
                    if arriving_units:
                        # Reuse actual unit dicts (preserves xp/level), reassign IDs and status
                        for unit in arriving_units[:arriving_count]:
                            unit['id'] = next_id
                            unit['status'] = 'moved'
                            unit['order'] = None
                            units.append(unit)
                            next_id += 1
                    elif composition:
                        # Fallback: create units based on composition (no xp data available)
                        units_created = 0
                        for unit_type, count in composition.items():
                            for _ in range(count):
                                if units_created < arriving_count:
                                    # Phase 2E: Use _make_unit() factory
                                    units.append(self._make_unit(unit_type, next_id))
                                    next_id += 1
                                    units_created += 1
                    else:
                        # Fallback: create default Swordsmen
                        for i in range(arriving_count):
                            # Phase 2E: Use _make_unit() factory
                            units.append(self._make_unit('Swordsman', next_id + i))

                    # Add to garrison (use actual unit count to ensure consistency)
                    self.add_garrison(territory, winner, moved=len(units), units=units)

                    # Sync garrison counts with actual unit list after incremental add
                    self._sync_garrison_counts(territory, winner)

                    # Sync legacy data
                    self.sync_legacy_garrison_data(territory)

                    self.add_message(f"Player {winner + 1} reinforced {territory} ({winner_armies} total armies)")

                elif is_ally_reinforcement:
                    # ALLY REINFORCEMENT: Create separate garrison for ally
                    # Check total army limit across all garrisons
                    total_in_territory = self.get_territory_total_armies(territory)
                    if total_in_territory + winner_armies > self.MAX_ARMIES_PER_TERRITORY:
                        excess = (total_in_territory + winner_armies) - self.MAX_ARMIES_PER_TERRITORY
                        winner_armies -= excess
                        self.add_message(f"Army overflow in {territory}: {excess} ally armies disbanded (limit: {self.MAX_ARMIES_PER_TERRITORY})")

                    # Create units for ally garrison
                    # Veterancy: use actual unit dicts from animation to preserve xp/level
                    comp_key = (territory, winner)
                    arriving_units = moving_units.get(comp_key, [])
                    units = []
                    if arriving_units:
                        # Reuse actual unit dicts (preserves xp/level), reassign IDs and status
                        for i, unit in enumerate(arriving_units[:winner_armies]):
                            unit['id'] = i
                            unit['status'] = 'moved'
                            unit['order'] = None
                            units.append(unit)
                    elif composition:
                        count_added = 0
                        for unit_type, count in composition.items():
                            for _ in range(count):
                                if count_added >= winner_armies:
                                    break
                                # Phase 2E: Use _make_unit() factory
                                units.append(self._make_unit(unit_type, count_added))
                                count_added += 1
                            if count_added >= winner_armies:
                                break
                    else:
                        # Fallback: create default Swordsmen
                        for i in range(winner_armies):
                            # Phase 2E: Use _make_unit() factory
                            units.append(self._make_unit('Swordsman', i))

                    # Add ally garrison (ownership stays with current_owner)
                    # Use actual unit count to ensure consistency
                    self.add_garrison(territory, winner, moved=len(units), units=units)

                    # Sync garrison counts with actual unit list after incremental add
                    self._sync_garrison_counts(territory, winner)

                    # Sync legacy data (represents owner's garrison only)
                    self.sync_legacy_garrison_data(territory)

                    self.add_message(f"Player {winner + 1} reinforced ally {territory} with {winner_armies} armies")

                else:
                    # CONQUEST: Take over territory with new garrison
                    # Clear all existing garrisons (previous owner and any allies)
                    self.territory_garrisons[territory] = {}

                    # Create units for conqueror's garrison
                    # Veterancy: use actual unit dicts from animation to preserve xp/level
                    arriving_units = moving_units.get(comp_key, [])
                    units = []
                    if arriving_units:
                        # Reuse actual unit dicts (preserves xp/level), reassign IDs and status
                        for i, unit in enumerate(arriving_units[:winner_armies]):
                            unit['id'] = i
                            unit['status'] = 'moved'
                            unit['order'] = None
                            units.append(unit)
                    elif composition:
                        # Fallback: create units from composition (no xp data available)
                        units_created = 0
                        for unit_type, count in composition.items():
                            for i in range(count):
                                if units_created < winner_armies:
                                    # Phase 2E: Use _make_unit() factory
                                    units.append(self._make_unit(unit_type, units_created))
                                    units_created += 1
                    else:
                        # Fallback: create default Swordsmen
                        for i in range(winner_armies):
                            # Phase 2E: Use _make_unit() factory
                            units.append(self._make_unit('Swordsman', i))

                    # Update ownership
                    self.territory_owners[territory] = winner
                    self._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    self.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses

                    # Campaign hook: notify territory conquered (uncontested takeover)
                    if self.tutorial_mission and current_owner != winner:
                        self.tutorial_mission.notify_event(
                            'territory_conquered',
                            territory=territory,
                            new_owner=winner
                        )

                    # Capital Assault: Check if conquered territory is enemy's capital
                    logger.debug(f"Conquered {territory}, Victory Condition: {self.victory_condition}")
                    logger.debug(f"Starting territories: {self.player_starting_territories}")
                    logger.debug(f"Winner: {winner}")

                    if self.victory_condition == "Capital Assault":
                        logger.debug(f"In Capital Assault check")
                        for player_index, capital in self.player_starting_territories.items():
                            logger.debug(f"Checking player {player_index}'s capital {capital} vs conquered {territory}")
                            # Check: capital matches, not self, and not an ally (enemies only)
                            if capital == territory and player_index != winner and not self.are_allies(winner, player_index):
                                # Capital conquered - eliminate the player
                                logger.info(f"[CAPITAL ASSAULT] Player {winner + 1} conquered Player {player_index + 1}'s capital via army movement!")
                                self.eliminate_player(player_index)

                    # Add conqueror's garrison (use actual unit count)
                    self.add_garrison(territory, winner, moved=len(units), units=units)

                    # Sync garrison counts with actual unit list after add
                    self._sync_garrison_counts(territory, winner)

                    # Sync legacy data
                    self.sync_legacy_garrison_data(territory)

                    self.add_message(f"Player {winner + 1} conquers {territory} ({winner_armies} armies)")

                    # Player Level: award XP based on conquest type (uncontested)
                    if current_owner == -1:
                        # Neutral territory conquest
                        self._track_stat(winner, 'xp_earned', 2)
                    else:
                        # Enemy territory conquered without a battle
                        self._track_stat(winner, 'xp_earned', 4)

                    # Check victory after any uncontested territory capture
                    # (Domination, Total Conquest, Capital Assault — all victory conditions)
                    self.check_victory()

            elif unique_players > 1:
                # TEAM CHECK: Group allies together before creating battles
                # Allies cannot fight each other - combine their forces into teams
                team_armies = {}  # {team_leader: total_count}
                team_compositions = {}  # {team_leader: {unit_type: count}}
                player_to_team_leader = {}  # {player: team_leader} mapping

                for player in player_armies.keys():
                    # Find team leader (lowest player index in the team)
                    team_leader = player
                    for other_player in player_armies.keys():
                        if other_player < team_leader and self.are_allies(player, other_player):
                            team_leader = other_player

                    player_to_team_leader[player] = team_leader

                    # Add this player's armies to their team
                    if team_leader not in team_armies:
                        team_armies[team_leader] = 0
                        team_compositions[team_leader] = {}

                    team_armies[team_leader] += player_armies[player]

                    # Combine compositions
                    comp_key = (territory, player)
                    composition = moving_compositions.get(comp_key, {})

                    # For defending garrison, get composition from multi-garrison system
                    if player in self.territory_garrisons.get(territory, {}):
                        garrison_composition = {}
                        garrison_units = self.territory_garrisons[territory][player]['units']
                        for unit in garrison_units:
                            unit_type = unit.get('type', 'Swordsman')
                            garrison_composition[unit_type] = garrison_composition.get(unit_type, 0) + 1
                        composition = garrison_composition
                    elif not composition and player in player_armies:
                        # Default to Swordsmen if no composition found
                        composition = {'Swordsman': player_armies[player]}

                    # Merge composition into team composition
                    for unit_type, count in composition.items():
                        team_compositions[team_leader][unit_type] = team_compositions[team_leader].get(unit_type, 0) + count

                # Check if there's actually a battle after grouping allies
                unique_teams = len(team_armies)

                if unique_teams == 1:
                    # All players are allies! No battle
                    # Keep each player's garrison separate (multi-garrison system)
                    # Only merge ownership if territory was neutral or unowned

                    # Determine who should own the territory
                    if current_owner == -1:
                        # Neutral territory - assign to team leader
                        team_leader = list(team_armies.keys())[0]
                        self.territory_owners[territory] = team_leader
                        self._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                        self.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses
                        owner_msg = f"Player {team_leader + 1} captures"
                    else:
                        # Territory already owned by someone (ally) - keep current ownership
                        owner_msg = f"Allied reinforcement in"

                    # Check total army limit
                    total_armies = sum(team_armies.values())
                    if total_armies > self.MAX_ARMIES_PER_TERRITORY:
                        excess = total_armies - self.MAX_ARMIES_PER_TERRITORY
                        self.add_message(f"{owner_msg} {territory}: {excess} excess armies disbanded (limit: {self.MAX_ARMIES_PER_TERRITORY})")
                        # Proportionally reduce each player's armies
                        reduction_factor = self.MAX_ARMIES_PER_TERRITORY / total_armies
                        for player in player_armies.keys():
                            player_armies[player] = int(player_armies[player] * reduction_factor)

                    # Create separate garrisons for each player
                    for player, army_count in player_armies.items():
                        if army_count == 0:
                            continue

                        # Get composition for this player
                        comp_key = (territory, player)
                        composition = moving_compositions.get(comp_key, {})

                        # Check if this player already has a garrison (defender)
                        existing_garrison = self.territory_garrisons.get(territory, {}).get(player)
                        if existing_garrison:
                            # This player already has a garrison - ADD arriving armies to it
                            # CRITICAL: player_armies may include defender's garrison IF player is owner
                            # R9: If player is owner and defending, their garrison was added in _process_arrivals()
                            # If player is NOT owner but has garrison (visitor), garrison NOT in player_armies

                            # Check if this player is the owner (defender)
                            if player == current_owner:
                                # Owner defending - player_armies includes garrison + arrivals
                                # Subtract garrison to get only arrivals
                                existing_count = existing_garrison.get('unmoved', 0) + existing_garrison.get('moved', 0)
                                arriving_count = army_count - existing_count

                                if arriving_count < 0:
                                    # FIX: Negative arriving_count means we need to REDUCE the garrison
                                    # This happens when overflow reduction was applied
                                    reduction_needed = abs(arriving_count)
                                    self._reduce_garrison(territory, player, reduction_needed)
                                    continue
                                elif arriving_count == 0:
                                    # No new arrivals, only defender - skip
                                    continue
                            else:
                                # Not owner - player_armies contains ONLY arrivals
                                # Don't subtract anything
                                arriving_count = army_count

                            # Create units for arriving armies only
                            units_to_add = []
                            # Start unit IDs after existing units
                            existing_units = existing_garrison.get('units', [])
                            next_id = max([u['id'] for u in existing_units], default=-1) + 1

                            # Veterancy: use actual unit dicts from animation to preserve xp/level
                            arriving_units = moving_units.get(comp_key, [])
                            if arriving_units:
                                for unit in arriving_units[:arriving_count]:
                                    unit['id'] = next_id
                                    unit['status'] = 'moved'
                                    unit['order'] = None
                                    units_to_add.append(unit)
                                    next_id += 1
                            elif composition:
                                units_created = 0
                                for unit_type, count in composition.items():
                                    for _ in range(count):
                                        if units_created >= arriving_count:
                                            break
                                        # Phase 2E: Use _make_unit() factory
                                        units_to_add.append(self._make_unit(unit_type, next_id))
                                        next_id += 1
                                        units_created += 1
                                    if units_created >= arriving_count:
                                        break
                            else:
                                # Default to Swordsmen — diagnostic: no unit data or composition available
                                logger.warning(f"[UNIT_TYPE_DIAG] _process_arrivals reinforcement fallback: "
                                               f"creating {arriving_count} default Swordsmen for Player {player + 1} "
                                               f"at {territory} (no extracted_units or composition)")
                                for i in range(arriving_count):
                                    # Phase 2E: Use _make_unit() factory
                                    units_to_add.append(self._make_unit('Swordsman', next_id + i))

                            # Add arriving armies to existing garrison using add_garrison
                            self.add_garrison(territory, player, unmoved=0, moved=arriving_count, units=units_to_add)
                            # Sync garrison counts with actual unit list after incremental add
                            self._sync_garrison_counts(territory, player)
                            continue

                        # Create units for arriving player (new garrison)
                        # Veterancy: use actual unit dicts from animation to preserve xp/level
                        arriving_units = moving_units.get(comp_key, [])
                        units = []
                        if arriving_units:
                            for i, unit in enumerate(arriving_units[:army_count]):
                                unit['id'] = i
                                unit['status'] = 'moved'
                                unit['order'] = None
                                units.append(unit)
                        elif composition:
                            unit_id = 0
                            for unit_type, count in composition.items():
                                for _ in range(count):
                                    # Phase 2E: Use _make_unit() factory
                                    units.append(self._make_unit(unit_type, unit_id))
                                    unit_id += 1
                        else:
                            # Default to Swordsmen — diagnostic: no unit data or composition available
                            logger.warning(f"[UNIT_TYPE_DIAG] _process_arrivals new garrison fallback: "
                                           f"creating {army_count} default Swordsmen for Player {player + 1} "
                                           f"at {territory} (no extracted_units or composition)")
                            for i in range(army_count):
                                # Phase 2E: Use _make_unit() factory
                                units.append(self._make_unit('Swordsman', i))

                        # Set garrison for this player (new garrison)
                        self.set_garrison_armies(territory, player, unmoved=0, moved=army_count, units=units)
                        # Sync garrison counts with actual unit list after set
                        self._sync_garrison_counts(territory, player)

                    self.add_message(f"{owner_msg} {territory}: {total_armies} allied armies")

                else:
                    # Multiple teams - create a battle!

                    # Show individual participants before grouping
                    self.add_message(f"=== BATTLE in {territory}! ===")
                    self.add_message(f"  Participants:")
                    for player, army_count in sorted(player_armies.items()):
                        team_leader = player_to_team_leader[player]
                        if team_leader == player:
                            # Team leader - show as leader
                            team_members = [p for p, leader in player_to_team_leader.items() if leader == team_leader]
                            if len(team_members) > 1:
                                allies_str = ", ".join([str(p + 1) for p in team_members if p != player])
                                self.add_message(f"    Player {player + 1}: {army_count} armies (allied with Player {allies_str})")
                            else:
                                self.add_message(f"    Player {player + 1}: {army_count} armies")
                        else:
                            # Team member - show as reinforcing ally
                            self.add_message(f"    Player {player + 1}: {army_count} armies (supporting Player {team_leader + 1})")

                    battle = Battle(territory)
                    battle.original_owner = current_owner

                    # Add team armies to the battle
                    for team_leader, count in team_armies.items():
                        # Get composition for this team
                        composition = team_compositions[team_leader]

                        battle.add_army(team_leader, count, composition)

                        # Track allied defenders (players who are NOT the team leader but are on the team)
                        # These are allies reinforcing the territory
                        for player, leader in player_to_team_leader.items():
                            if leader == team_leader and player != team_leader:
                                # This player is an ally of the team leader
                                if player in self.territory_garrisons.get(territory, {}):
                                    # This ally has a garrison in the territory (defending ally)
                                    battle.allied_defenders.append(player)

                        # Track Keep bonus (if team leader is the original owner)
                        if team_leader == current_owner and has_keep:
                            battle.keep_bonus = keep_bonus
                            battle.keep_bonus_player = team_leader
                            battle.original_garrison = current_garrison

                    # Veterancy: Create garrisons for arriving attackers using actual unit dicts
                    # This preserves xp/level so _update_battle_results can find surviving units
                    for player in player_armies.keys():
                        # Skip players who already have a garrison (defenders)
                        if player in self.territory_garrisons.get(territory, {}):
                            continue
                        # Get actual unit dicts from animation pipeline
                        comp_key = (territory, player)
                        arriving_units = moving_units.get(comp_key, [])
                        if arriving_units:
                            # Use actual unit objects (preserves xp/level)
                            units = []
                            for i, unit in enumerate(arriving_units):
                                unit['id'] = i
                                unit['status'] = 'moved'
                                unit['order'] = None
                                units.append(unit)
                            self.set_garrison_armies(territory, player, unmoved=0, moved=len(units), units=units)
                        else:
                            # Fallback: create from composition
                            composition = moving_compositions.get(comp_key, {})
                            units = []
                            unit_id = 0
                            if composition:
                                for unit_type, count in composition.items():
                                    for _ in range(count):
                                        # Phase 2E: Use _make_unit() factory
                                        units.append(self._make_unit(unit_type, unit_id))
                                        unit_id += 1
                            else:
                                for i in range(player_armies.get(player, 0)):
                                    # Phase 2E: Use _make_unit() factory
                                    units.append(self._make_unit('Swordsman', i))
                            if units:
                                self.set_garrison_armies(territory, player, unmoved=0, moved=len(units), units=units)

                    self.pending_battles.append(battle)

                # Add message if hero defense bonus is active
                if keep_plot_with_hero is not None and self.player_hero_keep_defense_bonus[current_owner] > 0:
                    self.add_message(f"  Hero present in Keep/Castle! Defense bonus increased to +{keep_bonus}")

                # Clear the territory's garrison (it's now in the battle)
                self.armies[territory] = 0
                self.armies_unmoved[territory] = 0
                self.armies_moved[territory] = 0

        # Enforce army limits after all arrivals processed (safety net for multi-deposit)
        self._enforce_army_limits()

        # If battles were created, transition to battles phase
        if self.pending_battles:
            self.turn_phase = 'battles'
            self.add_message(f"{len(self.pending_battles)} battles detected! Resolve them to continue.")
            logger.info(f"[TURN_DEBUG] _process_arrivals: {len(self.pending_battles)} battles → turn_phase='battles'")
        else:
            # No battles - animations complete, advance to next player immediately
            logger.info(f"[TURN_DEBUG] _process_arrivals: no battles, turn_phase={self.turn_phase}")
            if self.turn_phase == 'execution':
                self._advance_to_next_player()

    # R3: Removed legacy can_move_army() and move_army() — 0 external callers.
    # These used simple army-count subtraction without unit composition, animations,
    # or proper garrison handling. The order/animation system replaced them.
