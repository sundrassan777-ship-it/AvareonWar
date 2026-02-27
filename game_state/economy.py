# game_state/economy.py
# Economy mixin for GameState (Phase 7 decomposition)

"""
Economy system: income calculation, costs, taxation, territorial bonuses.

Provides methods for calculating income, effective costs with discounts,
tax collection, and territorial bonus computation.
"""

import map_data
from utils.logger import get_logger

logger = get_logger(__name__)


class EconomyMixin:
    """Mixin providing economy and income methods for GameState."""

    # R12: BONUS_TYPES removed as class attribute — now set as instance attribute
    # in GameState.__init__ (consistent with HERO_TYPES, building_types pattern)

    def get_effective_cost(self, item_type, base_cost, player=None):
        """
        Calculate effective cost after applying all applicable discounts.

        This is the centralized cost calculation system that applies all
        active upgrades and discounts. Use this method instead of manually
        checking discount variables.

        Args:
            item_type: Type of item being purchased:
                      - 'Hero' for any hero
                      - 'Keep', 'Farm', 'Mine', 'Barracks', 'Square' for buildings
                      - 'Swordsman', 'Pikeman', 'Archer', 'Cavalry' for units
            base_cost: The base cost before any discounts
            player: Player index (if None, uses current_player)

        Returns:
            int: Effective cost after all applicable discounts

        Example:
            >>> cost = self.get_effective_cost('Keep', 100, player=0)
            >>> # Returns 85 if player 0 has Royal Decree researched
        """
        if player is None:
            player = self.current_player

        effective_cost = base_cost

        # Royal Decree: 15% discount on Heroes and Keeps
        if item_type in ['Hero', 'Keep']:
            discount_percent = self.player_royal_decree_discount[player]
            if discount_percent > 0:
                effective_cost = int(effective_cost * (100 - discount_percent) / 100)

        # Improved Training: 20% discount on Swordsmen and Pikemen
        if item_type in ['Swordsman', 'Pikeman']:
            discount_percent = self.player_training_cost_discount[player]
            if discount_percent > 0:
                effective_cost = int(effective_cost * (100 - discount_percent) / 100)

        # Animal Handling: 25% discount on Cavalry
        if item_type == 'Cavalry':
            discount_percent = self.player_cavalry_cost_discount[player]
            if discount_percent > 0:
                effective_cost = int(effective_cost * (100 - discount_percent) / 100)

        # Makeshift Barracks: 25% discount on Barracks
        if item_type == 'Barracks':
            discount_percent = self.player_barracks_cost_discount[player]
            if discount_percent > 0:
                effective_cost = int(effective_cost * (100 - discount_percent) / 100)

        # Master Negotiator (Evain Nithieln): 75% discount on Farms, Mines, and Squares
        if item_type in ['Farm', 'Mine', 'Square']:
            if self.player_master_negotiator_active[player]:
                effective_cost = int(effective_cost * 0.25)  # 75% off = pay 25%

        # Future upgrades can be added here:
        # Example: Barracks Expansion (20% off Barracks)
        # if item_type == 'Barracks':
        #     discount_percent = self.player_barracks_discount[player]
        #     if discount_percent > 0:
        #         effective_cost = int(effective_cost * (100 - discount_percent) / 100)

        # Territorial bonuses - apply cost reductions from owned territory bonuses
        territorial_bonuses = self.calculate_player_territorial_bonuses(player)

        # Building cost reduction (-15% per bonus territory)
        if item_type in ['Farm', 'Mine', 'Barracks', 'Keep', 'Square', 'Training Grounds']:
            discount_pct = abs(territorial_bonuses.get('building_cost', 0))
            if discount_pct > 0:
                effective_cost = int(effective_cost * (100 - discount_pct) / 100)

        # Unit cost reduction (-5% per bonus territory)
        if item_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
            discount_pct = abs(territorial_bonuses.get('unit_cost', 0))
            if discount_pct > 0:
                effective_cost = int(effective_cost * (100 - discount_pct) / 100)

        # Hero cost reduction (-3% per bonus territory)
        if item_type == 'Hero':
            discount_pct = abs(territorial_bonuses.get('hero_cost', 0))
            if discount_pct > 0:
                effective_cost = int(effective_cost * (100 - discount_pct) / 100)

        return effective_cost

    def calculate_player_territorial_bonuses(self, player_index):
        """
        Calculate summed territorial bonuses from all owned territories.

        Args:
            player_index: Index of the player (0-based)

        Returns:
            dict: {bonus_type: total_percent} mapping (e.g., {'income_bonus': 6, 'unit_cost': -10})
        """
        # MP1 fix: Cache per player per turn — bonuses only change with ownership changes
        cache_key = (player_index, getattr(self, 'turn_number', 0))
        if not hasattr(self, '_territorial_bonus_cache'):
            self._territorial_bonus_cache = {}
        if cache_key in self._territorial_bonus_cache:
            return self._territorial_bonus_cache[cache_key]

        bonuses = {}
        for territory, owner in self.territory_owners.items():
            if owner == player_index:
                bonus_type = map_data.get_territory_bonus(territory)
                if bonus_type:
                    # M7 fix: Guard against unknown bonus types
                    bonus_def = self.BONUS_TYPES.get(bonus_type)
                    if bonus_def:
                        bonuses[bonus_type] = bonuses.get(bonus_type, 0) + bonus_def['value']
        self._territorial_bonus_cache[cache_key] = bonuses
        return bonuses

    def get_hero_cost(self, hero_type, player=None):
        """
        Get the effective cost to train a hero (with discounts applied).

        Args:
            hero_type: Name of the hero (e.g., 'Halon Nextroy')
            player: Player index (if None, uses current_player)

        Returns:
            int: Effective hero cost after discounts
        """
        base_cost = self.HERO_TYPES[hero_type]['cost']
        return self.get_effective_cost('Hero', base_cost, player)

    def get_building_cost(self, building_type, player=None):
        """
        Get the effective cost to build a building (with discounts applied).

        Args:
            building_type: Type of building ('Keep', 'Farm', 'Mine', 'Barracks', 'Square')
            player: Player index (if None, uses current_player)

        Returns:
            int: Effective building cost after discounts
        """
        base_cost = self.building_types[building_type]['cost']
        return self.get_effective_cost(building_type, base_cost, player)

    def get_effective_tech_cost(self, base_tech_cost, player=None):
        """
        Calculate effective technology research cost with territorial bonuses and hero modifiers.

        Args:
            base_tech_cost: The base cost of the technology
            player: Player index (if None, uses current_player)

        Returns:
            int: Effective tech cost after bonuses
        """
        if player is None:
            player = self.current_player

        tech_cost = base_tech_cost

        # Apply Ruthless Ingenuity (Erec Silvyr): +33% cost
        if self.player_has_silvyr(player):
            tech_cost = int(tech_cost * 1.33)

        # Territorial bonuses: -5% per tech_cost territory
        territorial_bonuses = self.calculate_player_territorial_bonuses(player)
        discount_pct = abs(territorial_bonuses.get('tech_cost', 0))
        if discount_pct > 0:
            tech_cost = int(tech_cost * (100 - discount_pct) / 100)

        return tech_cost

    def calculate_player_income(self, player_index):
        """
        Calculate total income for a player from their territories.

        Phase 2F: Now delegates per-territory calculation to calculate_territory_income()
        to eliminate ~80 lines of duplicated income logic. The only logic that remains here
        is the iteration over owned territories and the territorial bonus applied at the end.
        """
        total_income = 0
        for territory, owner in self.territory_owners.items():
            if owner == player_index:
                # Phase 2F: Delegate to calculate_territory_income with player_index
                # to apply hero bonuses (Narn, Nithieln) in addition to base + tech bonuses
                total_income += self.calculate_territory_income(territory, player_index)

        # Apply territorial income bonus to total (applies AFTER all territory income calculated)
        territorial_bonuses = self.calculate_player_territorial_bonuses(player_index)
        income_bonus_pct = territorial_bonuses.get('income_bonus', 0)
        if income_bonus_pct > 0:
            total_income = int(total_income * (100 + income_bonus_pct) / 100)

        return total_income

    def collect_income(self, player_index):
        """Collect income for a player and add to their gold"""
        # Check if player is embargoed
        if player_index in self.embargo_blocked_players:
            # Income is blocked by Embargo
            self.add_message(f"Player {player_index + 1}: Income blocked by Embargo!")
            # Remove player from embargo list (effect only lasts one turn)
            self.embargo_blocked_players.remove(player_index)
            return

        income = self.calculate_player_income(player_index)

        # Count territories for message
        territory_count = sum(1 for owner in self.territory_owners.values() if owner == player_index)

        # Extensive Connections: Halon Nextroy gains 4 gold per territory
        extensive_connections_bonus = 0
        if self.player_has_nextroy(player_index):
            extensive_connections_bonus = territory_count * 4
            income += extensive_connections_bonus

        # Apply AI difficulty income modifier
        if self.player_is_ai[player_index]:
            difficulty = self.player_ai_difficulty[player_index]
            multipliers = [0.75, 1.0, 1.25]  # Easy, Medium, Hard
            income = int(income * multipliers[difficulty])

        self.player_gold[player_index] += income

        # Track gold earned and max income per turn for recap screen
        if income > 0:
            self._track_stat(player_index, 'gold_acquired', income)
            if income > self.player_stats.get(player_index, {}).get('max_income_per_turn', 0):
                self.player_stats[player_index]['max_income_per_turn'] = income

        if income > 0:
            base_income = income - extensive_connections_bonus
            if extensive_connections_bonus > 0:
                self.add_message(f"Player {player_index + 1} earned {base_income} gold from {territory_count} territories")
                self.add_message(f"  +{extensive_connections_bonus} gold from Extensive Connections ({territory_count} territories × 4)")
            else:
                self.add_message(f"Player {player_index + 1} earned {income} gold from {territory_count} territories")

    def apply_taxation(self, player_index):
        """Apply taxation deduction to player's gold at turn end (before income collection)"""
        # No taxation if level is 0
        if self.taxation_level == 0:
            return

        # Tax rates for each level — M13 fix: clamp index to valid range
        tax_rates = [0.0, 0.25, 0.5, 0.75, 1.0]
        clamped_level = max(0, min(self.taxation_level, len(tax_rates) - 1))
        rate = tax_rates[clamped_level]

        current_gold = self.player_gold[player_index]
        tax_amount = int(current_gold * rate)

        # Deduct tax
        self.player_gold[player_index] -= tax_amount

        # Track gold lost to taxation for recap screen
        if tax_amount > 0:
            self._track_stat(player_index, 'gold_lost_to_taxation', tax_amount)

        # Prevent negative gold (should not happen, but safety check)
        if self.player_gold[player_index] < 0:
            self.player_gold[player_index] = 0

        # Log message if tax > 0
        if tax_amount > 0:
            tax_percentage = int(rate * 100)
            self.add_message(f"Player {player_index + 1}: {tax_amount} gold lost to taxation ({tax_percentage}%)")

    def calculate_territory_income(self, territory, player_index=None):
        """
        Calculate income for a single territory.

        Phase 2F: Unified income calculation. When player_index is provided, applies
        player-specific hero bonuses (Legacy of the Empire, Farmer Subsidies).
        When called without player_index, only base income + building/tech bonuses apply.

        Args:
            territory: Territory name
            player_index: Optional player index for hero bonus calculations.
                          When None, uses territory owner for tech checks only.

        Returns:
            int: Total income from this territory (base + buildings + multipliers)
        """
        # Get base income for territory
        try:
            base_income = map_data.get_territory_income(territory)
        except (KeyError, AttributeError) as e:
            self.log_error(f"Failed to get income for territory '{territory}'", e)
            base_income = 0

        # Determine owner for technology checks
        # When player_index is provided, use it (caller knows the owner);
        # otherwise fall back to territory_owners lookup
        owner = player_index if player_index is not None else self.territory_owners.get(territory, -1)

        # Phase 2F: Legacy of the Empire (Aidam Narn): +50% base income from territories
        # Only applied when called with explicit player_index (i.e., from calculate_player_income)
        if player_index is not None and self.player_has_narn(player_index):
            base_income = int(base_income * 1.5)

        # Add building bonuses
        building_bonus = 0
        multiplier = 1.0

        if territory in self.buildings:
            for plot_index, building_type in self.buildings[territory].items():
                if building_type is None:
                    continue

                # Get building info
                try:
                    building_info = self.building_types[building_type]
                    effect = building_info['effect']
                    value = building_info['value']

                    if effect == 'income':
                        # Veterancy: +10% income per building level (applied first)
                        bldg_data = self.get_building_xp_data(territory, plot_index)
                        bldg_level = bldg_data['level']
                        if bldg_level > 0:
                            value = int(value * (1.0 + bldg_level * self.BUILDING_LEVEL_INCOME_BONUS))
                        # Phase 2F: Farmer Subsidies (Evain Nithieln): +50% income from Farms
                        # Only applied when called with explicit player_index
                        if building_type == 'Farm' and player_index is not None and self.player_has_nithieln(player_index):
                            value = int(value * 1.5)
                        # Efficient Farming I: +20% income from Farms
                        if building_type == 'Farm' and owner >= 0 and 'tech_0_0' in self.player_tech_researched.get(owner, set()):
                            value = int(value * 1.2)
                        # Efficient Farming II: Additional +20% income from Farms (stacks with I)
                        if building_type == 'Farm' and owner >= 0 and 'tech_0_4' in self.player_tech_researched.get(owner, set()):
                            value = int(value * 1.2)
                        # Efficient Mining I: +20% income from Mines
                        if building_type == 'Mine' and owner >= 0 and 'tech_0_1' in self.player_tech_researched.get(owner, set()):
                            value = int(value * 1.2)
                        # Efficient Mining II: Additional +20% income from Mines (stacks with I)
                        if building_type == 'Mine' and owner >= 0 and 'tech_0_5' in self.player_tech_researched.get(owner, set()):
                            value = int(value * 1.2)
                        # Laws of Trade: +15% for Farms/Mines if Keep nearby
                        if building_type in ['Farm', 'Mine'] and owner >= 0 and 'tech_0_6' in self.player_tech_researched.get(owner, set()):
                            # Check if territory has a Keep or is adjacent to one
                            has_nearby_keep = False
                            # Check current territory for Keep
                            if territory in self.buildings:
                                for bldg in self.buildings[territory].values():
                                    if bldg == 'Keep':
                                        has_nearby_keep = True
                                        break
                            # Check adjacent territories for Keep
                            if not has_nearby_keep:
                                try:
                                    adjacent_territories = map_data.get_neighbors(territory)
                                    for adj_territory in adjacent_territories:
                                        # M6 fix: Only count Keeps owned by the same player
                                        if self.territory_owners.get(adj_territory) != owner:
                                            continue
                                        if adj_territory in self.buildings:
                                            for bldg in self.buildings[adj_territory].values():
                                                if bldg == 'Keep':
                                                    has_nearby_keep = True
                                                    break
                                        if has_nearby_keep:
                                            break
                                except (KeyError, AttributeError):
                                    pass
                            if has_nearby_keep:
                                value = int(value * 1.15)
                        building_bonus += value
                    elif effect == 'multiplier':
                        # M3 fix: Stack multipliers instead of overwriting
                        # (e.g. two Squares should multiply together, not replace)
                        # Supply and Demand: Squares multiply by 2.5× instead of 1.5×
                        if building_type == 'Square' and owner >= 0 and 'tech_0_3' in self.player_tech_researched.get(owner, set()):
                            multiplier *= 2.5
                        else:
                            multiplier *= value
                except (KeyError, TypeError) as e:
                    self.log_error(f"Invalid building data for {building_type} in {territory}", e)
                    continue

        # Apply formula: (base + bonuses) * multiplier
        territory_income = int((base_income + building_bonus) * multiplier)
        return territory_income
