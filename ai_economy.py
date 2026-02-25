"""
AI Economy Module
Economic decision-making for building construction and technology research.

This module handles all economic decisions including:
- Building placement (Farm, Mine, Barracks, Keep, Square)
- Technology research priority
- Resource budget allocation

Classes:
    BuildingPlanner: Decides which buildings to construct and where
    TechResearcher: Selects technologies to research
    BudgetAllocator: Manages gold allocation across priorities
    EconomyManager: Main economic decision coordinator
"""

import random
import map_data

from utils.logger import get_logger
logger = get_logger(__name__)


class BuildingPlanner:
    """Decides which buildings to construct and where"""

    def __init__(self):
        # M23 FIX: Cache TerritoryScorer and ThreatAnalyzer to avoid per-call instantiation
        from ai_strategy import TerritoryScorer, ThreatAnalyzer
        self._scorer = TerritoryScorer()
        self._threat_analyzer = ThreatAnalyzer()

    def select_building_action(self, game_state, player_index, available_gold, difficulty_config, exclude_territories=None):
        """
        Select best building to construct this turn.

        Args:
            game_state: GameState instance
            player_index (int): Player making decision
            available_gold (int): Gold available to spend
            difficulty_config (dict): AI difficulty settings
            exclude_territories (set): Territories to exclude from consideration (already planned for building)

        Returns:
            tuple: (territory, plot_index, building_type, priority_score) or None
                   OR ('upgrade_castle', territory, plot_index, score) for Castle upgrades
        """
        if exclude_territories is None:
            exclude_territories = set()

        candidates = []

        # Find all owned territories
        owned_territories = [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]

        # PRIORITY: Check for Castle upgrades first (if any tech requires Castle)
        castle_upgrade = self._select_castle_upgrade(game_state, player_index, available_gold)
        if castle_upgrade:
            return castle_upgrade

        for territory in owned_territories:
            # Check if we can build here (one per territory per turn)
            if territory in game_state.buildings_started_this_turn:
                continue

            # Check if territory is excluded (already planned for building this turn)
            if territory in exclude_territories:
                continue

            # Get available plots
            available_plots = self._get_available_plots(territory, game_state)
            if not available_plots:
                continue

            # M14 FIX: Use dynamic building types from game_state instead of hardcoded list
            # This ensures new building types are automatically considered by the AI
            for building_type in game_state.building_types.keys():
                cost = game_state.get_effective_cost(building_type,
                    game_state.building_types[building_type]['cost'], player_index)

                if cost > available_gold:
                    continue

                # Score this building placement
                score = self.score_building_placement(
                    territory, building_type, game_state, player_index
                )

                if score > 0:
                    plot_idx = available_plots[0]
                    candidates.append((territory, plot_idx, building_type, score))

        if not candidates:
            return None

        # Sort by score
        candidates.sort(key=lambda x: x[3], reverse=True)
        return candidates[0]

    def _select_castle_upgrade(self, game_state, player_index, available_gold):
        """
        Select a Keep to upgrade to Castle.

        Castle upgrade is triggered when:
        1. Any Castle-required tech is already available (unlocked but not researched), OR
        2. AI has researched at least 2 techs in any column (approaching Castle-required techs), OR
        3. AI has researched row 2 in Column 1 (Animal Handling - next is Battlement Archery which requires Castle), OR
        4. AI has high income (300+) and plenty of gold (can afford to prepare)

        Args:
            game_state: GameState instance
            player_index (int): Player index
            available_gold (int): Available gold

        Returns:
            tuple: ('upgrade_castle', territory, plot_index, score) or None
        """
        # Check if Castle upgrade costs are affordable
        castle_upgrade_cost = 100  # Cost to upgrade Keep to Castle
        if available_gold < castle_upgrade_cost:
            return None

        # Check if already has a Castle
        has_castle = game_state.player_has_castle(player_index)
        if has_castle:
            return None  # Already have a Castle, no need for another

        # Check if any Castle-required techs are available (unlocked but not researched)
        available_techs = game_state.player_tech_available.get(player_index, set())
        researched_techs = game_state.player_tech_researched.get(player_index, set())

        needs_castle_for_tech = False
        castle_tech_blocked = None  # Track which Castle tech is waiting
        for tech_id in available_techs:
            if tech_id in researched_techs:
                continue

            # Find tech definition
            tech = next((t for t in game_state.technologies if t['id'] == tech_id), None)
            if tech and tech.get('requires_castle', False):
                needs_castle_for_tech = True
                castle_tech_blocked = tech['name']
                break

        # Check if AI has researched enough to be approaching Castle techs
        # Castle techs are typically in row 3+ (tech_X_3, tech_X_4, etc.)
        approaching_castle_techs = False
        column_1_approaching = False  # Track Column 1 specifically (military techs)
        column_0_approaching = False  # Track Column 0 (economy techs)

        for tech_id in researched_techs:
            parts = tech_id.split('_')
            if len(parts) >= 3:
                col = int(parts[1])
                row = int(parts[2])
                if row >= 2:  # Has researched row 2, next is row 3 which often requires Castle
                    approaching_castle_techs = True
                    if col == 1:
                        column_1_approaching = True  # Military tech path needs Castle soon
                    elif col == 0:
                        column_0_approaching = True  # Economy tech path needs Castle soon

        # Check if AI has high income and gold (proactive upgrade)
        current_income = game_state.calculate_player_income(player_index)
        has_strong_economy = current_income >= 230 and available_gold >= 150

        # Check tech progress in each column - if invested in any column, prioritize Castle
        # Count techs researched per column (rows 0-2 don't require Castle, row 3+ does)
        column_tech_counts = {0: 0, 1: 0, 2: 0}
        for tech_id in researched_techs:
            parts = tech_id.split('_')
            if len(parts) >= 3:
                col = int(parts[1])
                if col in column_tech_counts:
                    column_tech_counts[col] += 1

        # If invested in ANY column (2+ techs), prioritize Castle to unlock row 3+ techs
        invested_in_any_column = any(count >= 2 for count in column_tech_counts.values())

        # Decide if we should upgrade - prioritize Castle when ANY tech path is advancing
        should_upgrade = (
            needs_castle_for_tech or  # Direct need: Castle tech is unlocked but blocked
            approaching_castle_techs or  # Close to Castle techs in any column
            has_strong_economy or  # Can afford proactive upgrade
            invested_in_any_column  # Invested in any tech path (2+ techs in any column)
        )

        if not should_upgrade:
            return None

        # Log reason for upgrade
        if needs_castle_for_tech:
            logger.debug(f"Castle Priority: Player {player_index + 1} needs Castle for: {castle_tech_blocked}")
        elif approaching_castle_techs:
            columns_approaching = []
            if column_0_approaching:
                columns_approaching.append("economy")
            if column_1_approaching:
                columns_approaching.append("military")
            logger.debug(f"Castle Priority: Player {player_index + 1} approaching Castle techs ({', '.join(columns_approaching) if columns_approaching else 'command'})")
        elif invested_in_any_column:
            invested_cols = [f"col{c}:{n}" for c, n in column_tech_counts.items() if n >= 2]
            logger.debug(f"Castle Priority: Player {player_index + 1} invested in tech paths ({', '.join(invested_cols)})")

        # Find Keeps that can be upgraded
        owned_territories = [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]

        for territory in owned_territories:
            if territory not in game_state.buildings:
                continue

            for plot_idx, building_type in game_state.buildings[territory].items():
                if building_type != 'Keep':
                    continue

                # Check if already upgraded to Castle
                is_castle = (
                    territory in game_state.castle_upgrades and
                    plot_idx in game_state.castle_upgrades[territory]
                )

                # Check if upgrade in progress
                is_upgrading = (
                    territory in game_state.castle_upgrades_in_progress and
                    plot_idx in game_state.castle_upgrades_in_progress[territory]
                )

                if not is_castle and not is_upgrading:
                    # Found a Keep that can be upgraded!
                    # Return with HIGH priority score (150+)
                    return ('upgrade_castle', territory, plot_idx, 150.0)

        return None

    def _get_available_plots(self, territory, game_state):
        """
        Get list of available building plots in a territory.

        Returns:
            list: Available plot indices
        """
        plots = map_data.TERRITORY_PLOTS.get(territory, [])
        if territory not in game_state.buildings:
            game_state.buildings[territory] = {}

        available = []
        for i in range(len(plots)):
            # Check if plot is empty (not built and not under construction)
            is_built = i in game_state.buildings[territory]
            is_under_construction = (
                territory in game_state.under_construction and
                i in game_state.under_construction[territory]
            )

            if not is_built and not is_under_construction:
                available.append(i)

        return available

    def score_building_placement(self, territory, building_type, game_state, player_index):
        """
        Score a building placement (0-100, except Keep which can exceed 100 for hero enabling).

        Uses generic _score_building() with per-type config and modifier functions
        to eliminate duplication across building scoring methods.

        Args:
            territory (str): Territory name
            building_type (str): Building type
            game_state: GameState instance
            player_index (int): Player index

        Returns:
            float: Placement score (0-100, or higher for Keep hero enabling)
        """
        return self._score_building(territory, building_type, game_state, player_index)

    # ---- Per-type scoring configuration ----
    # Each building type defines:
    #   'base_score_fn': callable(self, territory, building_type, game_state, player_index) -> float
    #   'modifiers': list of callable(self, score, territory, building_type, game_state, player_index) -> float
    #   'cap': max score (None = uncapped, e.g. Keep for hero enabling)

    def _score_building(self, territory, building_type, game_state, player_index):
        """
        Generic building scoring method. Dispatches to per-type config for base score
        computation and modifiers, then applies score cap.

        Replaces the individual _score_income_building, _score_barracks, _score_keep,
        and _score_square methods with a unified pipeline:
          1. Compute base score via type-specific base_score_fn
          2. Apply type-specific modifier functions in order
          3. Cap the score (if applicable for the building type)

        Args:
            territory (str): Territory name
            building_type (str): Building type ('Farm', 'Mine', 'Barracks', 'Keep', 'Square')
            game_state: GameState instance
            player_index (int): Player index

        Returns:
            float: Placement score
        """
        # Building type scoring configuration - maps each type to its scoring pipeline
        building_configs = {
            'Farm': {
                'base_score_fn': self._base_score_income,
                'modifiers': [self._mod_square_synergy, self._mod_mine_preference, self._mod_income_tech_bonus],
                'cap': 100.0,
            },
            'Mine': {
                'base_score_fn': self._base_score_income,
                'modifiers': [self._mod_square_synergy, self._mod_mine_preference, self._mod_income_tech_bonus],
                'cap': 100.0,
            },
            'Barracks': {
                'base_score_fn': self._base_score_barracks,
                'modifiers': [self._mod_frontier_bonus, self._mod_enemy_neighbor_bonus, self._mod_nearby_barracks_penalty],
                'cap': 100.0,
            },
            'Keep': {
                'base_score_fn': self._base_score_keep,
                'modifiers': [self._mod_keep_high_value_threat, self._mod_keep_capital_assault, self._mod_keep_hero_enabling],
                'cap': None,  # Keep can exceed 100 when hero enabling is critical
            },
            'Square': {
                'base_score_fn': self._base_score_square,
                'modifiers': [self._mod_square_income_multiplier],
                'cap': 100.0,
            },
        }

        config = building_configs.get(building_type)
        if not config:
            return 0.0

        # Step 1: Compute base score
        score = config['base_score_fn'](territory, building_type, game_state, player_index)

        # Early exit if base score is 0 or negative (e.g. Keep already exists)
        if score <= 0.0:
            return score

        # Step 2: Apply modifiers in order
        for modifier_fn in config['modifiers']:
            score = modifier_fn(score, territory, building_type, game_state, player_index)
            # Early exit if a modifier zeroes out the score
            if score <= 0.0:
                return score

        # Step 3: Apply cap
        if config['cap'] is not None:
            score = min(score, config['cap'])

        return score

    # ---- Base score functions (one per building type) ----

    def _base_score_income(self, territory, building_type, game_state, player_index):
        """Base score for Farm/Mine: territory income * 2"""
        base_income = map_data.get_territory_income(territory)
        return base_income * 2.0

    def _base_score_barracks(self, territory, building_type, game_state, player_index):
        """Base score for Barracks: fixed 50.0"""
        return 50.0

    def _base_score_keep(self, territory, building_type, game_state, player_index):
        """
        Base score for Keep: territory value + threat level.
        Returns 0 if territory already has a Keep or one is under construction.
        """
        # CRITICAL: Only one Keep allowed per territory
        # Check if territory already has a Keep
        if territory in game_state.buildings:
            for bt in game_state.buildings[territory].values():
                if bt in ['Keep', 'Castle']:
                    return 0.0  # Already has a Keep

        # Check if Keep is under construction in this territory
        # Format: under_construction[territory][plot_index] = (building_type, turns_remaining)
        if territory in game_state.under_construction:
            for building_type_tuple in game_state.under_construction[territory].values():
                if building_type_tuple[0] == 'Keep':
                    return 0.0  # Already building a Keep here

        # M23 FIX: Use cached scorer and threat_analyzer instead of creating per call
        # Territory value and threat level combined
        territory_value = self._scorer.calculate_territory_value(territory, game_state, player_index)
        threat_level = self._threat_analyzer.calculate_territory_threat(territory, game_state, player_index)

        # Store these on self temporarily for the high-value-threat modifier
        self._keep_territory_value = territory_value
        self._keep_threat_level = threat_level

        return territory_value * 0.5 + threat_level * 0.5

    def _base_score_square(self, territory, building_type, game_state, player_index):
        """
        Base score for Square: 0 if fewer than 2 income buildings, otherwise
        income_building_count * 15.0
        """
        income_building_count = 0
        if territory in game_state.buildings:
            for bt in game_state.buildings[territory].values():
                if bt in ['Farm', 'Mine']:
                    income_building_count += 1

        # Squares only valuable with 2+ income buildings
        if income_building_count < 2:
            return 0.0

        return income_building_count * 15.0

    # ---- Modifier functions ----
    # Each takes (self, score, territory, building_type, game_state, player_index) -> float

    def _mod_square_synergy(self, score, territory, building_type, game_state, player_index):
        """Income buildings (Farm/Mine) score higher when territory has a Square"""
        has_square = self._territory_has_building(territory, 'Square', game_state)
        if has_square:
            score *= 1.5  # Square makes income buildings much better
        return score

    def _mod_mine_preference(self, score, territory, building_type, game_state, player_index):
        """Mines score slightly higher than Farms"""
        if building_type == 'Mine':
            score *= 1.1
        return score

    def _mod_income_tech_bonus(self, score, territory, building_type, game_state, player_index):
        """Boost score if relevant farming/mining tech is researched"""
        if building_type == 'Farm':
            if 6 in game_state.player_tech_researched[player_index]:  # Efficient Farming I
                score *= 1.1
        elif building_type == 'Mine':
            if 8 in game_state.player_tech_researched[player_index]:  # Efficient Mining I
                score *= 1.1
        return score

    def _mod_frontier_bonus(self, score, territory, building_type, game_state, player_index):
        """Barracks score higher on frontier territories"""
        is_frontier = self._is_frontier_territory(territory, game_state, player_index)
        if is_frontier:
            score += 20.0
        return score

    def _mod_enemy_neighbor_bonus(self, score, territory, building_type, game_state, player_index):
        """Barracks score higher with more enemy neighbors"""
        neighbors = map_data.get_neighbors(territory)
        enemy_neighbors = sum(
            1 for n in neighbors
            if game_state.territory_owners.get(n, -1) not in [-1, player_index]
        )
        score += enemy_neighbors * 10.0
        return score

    def _mod_nearby_barracks_penalty(self, score, territory, building_type, game_state, player_index):
        """Penalize Barracks if there's already one in an adjacent territory"""
        neighbors = map_data.get_neighbors(territory)
        has_nearby_barracks = any(
            self._territory_has_building(n, 'Barracks', game_state)
            for n in neighbors
        )
        if has_nearby_barracks:
            score *= 0.5  # Prefer spreading out Barracks
        return score

    def _mod_keep_high_value_threat(self, score, territory, building_type, game_state, player_index):
        """Bonus if territory is both high-value AND high-threat"""
        territory_value = self._keep_territory_value
        threat_level = self._keep_threat_level
        if territory_value > 60 and threat_level > 40:
            score += 20.0
        return score

    def _mod_keep_capital_assault(self, score, territory, building_type, game_state, player_index):
        """Capital Assault: Prioritize Keep in capital territory"""
        if game_state.victory_condition == "Capital Assault":
            capital = game_state.player_starting_territories.get(player_index)
            if territory == capital:
                # Massive bonus for building Keep in capital
                score += 50.0
                logger.debug(f"Capital Defense: Player {player_index + 1} prioritizing Keep in capital {territory}")
        return score

    def _mod_keep_hero_enabling(self, score, territory, building_type, game_state, player_index):
        """
        HERO ENABLING: Big bonus if AI has no Keep yet.
        Checks all owned territories for existing/under-construction Keeps.
        """
        # Check if player already has a Keep somewhere (built or under construction)
        has_keep = False
        for terr, owner in game_state.territory_owners.items():
            if owner != player_index:
                continue
            # Check built Keeps
            if terr in game_state.buildings:
                for bt in game_state.buildings[terr].values():
                    if bt in ['Keep', 'Castle']:
                        has_keep = True
                        break
            # Check under construction Keeps
            # Format: under_construction[territory][plot_index] = (building_type, turns_remaining)
            if not has_keep and terr in game_state.under_construction:
                for building_type_tuple in game_state.under_construction[terr].values():
                    if building_type_tuple[0] == 'Keep':
                        has_keep = True
                        break
            if has_keep:
                break

        if not has_keep:
            # Check if we have enough gold to benefit from heroes after building Keep
            # Keep costs ~150-200, cheapest hero costs 150 (Brennhen)
            player_gold = game_state.player_gold[player_index]
            territory_count = sum(1 for o in game_state.territory_owners.values() if o == player_index)

            # Prioritize Keep if:
            # - Past early game (8+ territories) AND
            # - Have reasonable gold (400+) to eventually train a hero
            # HIGH PRIORITY - score > 100 to beat all other buildings
            if territory_count >= 8 and player_gold >= 300:
                score += 120.0  # Very high bonus - MUST build Keep for heroes
                logger.debug(f"Hero Enable: Player {player_index + 1} prioritizing Keep for hero training (gold: {player_gold})")
            elif territory_count >= 12:
                # Even without tons of gold, mid-game should have a Keep
                score += 80.0

        return score

    def _mod_square_income_multiplier(self, score, territory, building_type, game_state, player_index):
        """Square score bonus from territory income (how much will be multiplied)"""
        territory_income = game_state.calculate_territory_income(territory)
        score += territory_income * 0.5
        return score

    def _territory_has_building(self, territory, building_type, game_state):
        """Check if territory has a specific building type"""
        if territory not in game_state.buildings:
            return False

        return building_type in game_state.buildings[territory].values()

    def _is_frontier_territory(self, territory, game_state, player_index):
        """Check if territory is on the frontier (borders enemy/neutral)"""
        neighbors = map_data.get_neighbors(territory)
        for neighbor in neighbors:
            owner = game_state.territory_owners.get(neighbor, -1)
            if owner != player_index:  # Enemy or neutral
                return True
        return False

    def select_buildings_to_demolish(self, game_state, player_index, available_gold, max_demolitions=1):
        """
        Select economy buildings to demolish when AI has excess gold.

        Multi-tier war economy: At higher gold levels, more buildings are demolished
        to make room for Barracks/Keeps. No longer requires all plots to be occupied.

        Non-military buildings priority: Farm > Mine > Market > other non-military.

        Args:
            game_state: GameState instance
            player_index (int): Player making decision
            available_gold (int): Gold available
            max_demolitions (int): Max buildings to demolish this turn

        Returns:
            list: [(territory, plot_index), ...] or empty list
        """
        # Minimum gold threshold for any demolition (scaled to 10/15/20 income tiers)
        if available_gold < 1200:
            return []

        # Military buildings that should never be demolished
        military_buildings = {'Barracks', 'Keep'}

        owned_territories = [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]

        # Demolition priority order: Farm first, then Mine, then Market, then others
        demolish_priority = {'Farm': 4, 'Mine': 3, 'Market': 2}

        demolition_candidates = []

        for territory in owned_territories:
            if territory not in game_state.buildings:
                continue

            # Check if territory already has a Barracks or needs one
            has_barracks = self._territory_has_building(territory, 'Barracks', game_state)
            has_keep = self._territory_has_building(territory, 'Keep', game_state)

            # Check if there's an open plot already (no demolition needed here)
            total_plots = len(map_data.TERRITORY_PLOTS.get(territory, []))
            occupied_plots = len([b for b in game_state.buildings[territory].values() if b is not None])
            has_open_plot = occupied_plots < total_plots

            for plot_idx, building_type in game_state.buildings[territory].items():
                if building_type is None or building_type in military_buildings:
                    continue

                # Score: Higher = more likely to demolish
                score = demolish_priority.get(building_type, 1)

                # Prefer frontier territories (good place for Barracks/Keep)
                is_frontier = self._is_frontier_territory(territory, game_state, player_index)
                if is_frontier:
                    score += 3

                # Prefer territories without Barracks (need to build one)
                if not has_barracks:
                    score += 5

                # Prefer territories without open plots (must demolish to build)
                if not has_open_plot:
                    score += 4

                # Penalty if territory has Square synergy
                has_square = self._territory_has_building(territory, 'Square', game_state)
                if has_square and building_type == 'Farm':
                    score -= 2

                demolition_candidates.append((territory, plot_idx, score))

        if not demolition_candidates:
            return []

        # Sort by score (highest first) and return top N
        demolition_candidates.sort(key=lambda x: x[2], reverse=True)
        return [(t, p) for t, p, s in demolition_candidates[:max_demolitions]]


class TechResearcher:
    """Selects technologies to research"""

    # Tech priorities by difficulty
    # Tech IDs are in format "tech_{col}_{row}" where col=0-2, row=0-6
    # Column 0 = Economy, Column 1 = Military, Column 2 = Command/Utility
    # All difficulties now include Column 1 (military) techs for balanced research
    TECH_PRIORITIES = {
        0: {  # Easy - Focus on economy but still research military
            'tech_0_0': 90,   # Efficient Farming I
            'tech_0_1': 88,   # Efficient Mining I
            'tech_0_2': 70,   # Leave Nothing Behind
            'tech_0_3': 65,   # Supply and Demand (Castle)
            'tech_0_4': 75,   # Efficient Farming II (Castle)
            'tech_0_5': 73,   # Efficient Mining II (Castle)
            # Column 1 - Military techs (added)
            'tech_1_0': 78,   # Improved Training - reduces Swordsmen/Pikemen cost
            'tech_1_1': 72,   # Makeshift Barracks - reduces Barracks cost
            'tech_1_2': 70,   # Animal Handling - reduces Cavalry cost
            'tech_1_3': 60,   # Battlement Archery (Castle)
            'tech_1_4': 55,   # Raze the Countryside (Castle)
            'tech_1_5': 58,   # Cavalry Tactics (Castle)
        },
        1: {  # Medium - Balanced across all columns
            'tech_0_0': 85,   # Efficient Farming I
            'tech_0_1': 87,   # Efficient Mining I
            'tech_0_2': 68,   # Leave Nothing Behind
            'tech_0_3': 72,   # Supply and Demand (Castle)
            'tech_0_4': 78,   # Efficient Farming II (Castle)
            'tech_0_5': 76,   # Efficient Mining II (Castle)
            # Column 1 - Military techs (expanded)
            'tech_1_0': 82,   # Improved Training
            'tech_1_1': 78,   # Makeshift Barracks
            'tech_1_2': 80,   # Animal Handling
            'tech_1_3': 70,   # Battlement Archery (Castle)
            'tech_1_4': 65,   # Raze the Countryside (Castle)
            'tech_1_5': 75,   # Cavalry Tactics (Castle)
            'tech_1_6': 68,   # Divide and Conquer (Castle)
            # Column 2 - Command techs
            'tech_2_1': 70,   # Improved Command I
            'tech_2_2': 65,   # Royal Decree
        },
        2: {  # Hard - Strategic mix with strong military focus
            'tech_0_0': 82,   # Efficient Farming I
            'tech_0_1': 90,   # Efficient Mining I
            'tech_0_2': 65,   # Leave Nothing Behind
            'tech_0_3': 75,   # Supply and Demand (Castle)
            'tech_0_4': 80,   # Efficient Farming II (Castle)
            'tech_0_5': 88,   # Efficient Mining II (Castle)
            # Column 1 - Military techs (highest priority on Hard)
            'tech_1_0': 88,   # Improved Training
            'tech_1_1': 85,   # Makeshift Barracks
            'tech_1_2': 86,   # Animal Handling
            'tech_1_3': 78,   # Battlement Archery (Castle)
            'tech_1_4': 72,   # Raze the Countryside (Castle)
            'tech_1_5': 85,   # Cavalry Tactics (Castle)
            'tech_1_6': 82,   # Divide and Conquer (Castle)
            # Column 2 - Command techs
            'tech_2_1': 80,   # Improved Command I
            'tech_2_2': 75,   # Royal Decree
            'tech_2_4': 70,   # Heroic Fortitude (Castle)
            'tech_2_5': 78,   # Improved Command II (Castle)
        }
    }

    def select_research_action(self, game_state, player_index, difficulty):
        """
        Select best technology to research.

        Args:
            game_state: GameState instance
            player_index (int): Player index
            difficulty (int): AI difficulty level

        Returns:
            int: Technology ID to research, or None
        """
        # Check if already researching something
        if player_index in game_state.research_in_progress and game_state.research_in_progress[player_index]:
            return None

        # Get available technologies
        available_techs = self._get_available_techs(game_state, player_index)

        if not available_techs:
            return None

        # Get priority mapping for this difficulty
        priorities = self.TECH_PRIORITIES.get(difficulty, {})

        # Score each tech
        tech_scores = []
        for tech_id in available_techs:
            # Find tech by ID (technologies is a list, tech_id is a string)
            tech = next((t for t in game_state.technologies if t['id'] == tech_id), None)
            if tech is None:
                continue
            cost = tech['cost']

            # Check affordability
            if game_state.player_gold[player_index] < cost:
                continue

            # Get priority (default 50 if not in priority list)
            priority = priorities.get(tech_id, 50)

            # Adjust based on game state
            adjusted_score = self._adjust_tech_score(tech_id, priority, game_state, player_index)

            tech_scores.append((tech_id, adjusted_score))

        if not tech_scores:
            return None

        # Sort by score
        tech_scores.sort(key=lambda x: x[1], reverse=True)
        return tech_scores[0][0]

    def _get_available_techs(self, game_state, player_index):
        """
        Get list of technologies available to research.

        Uses the game state's player_tech_available to ensure we only
        consider techs that are actually unlocked (not just theoretically available).
        """
        # Get actually available techs from game state (already has prereqs checked)
        available_in_game = game_state.player_tech_available.get(player_index, set())
        researched = game_state.player_tech_researched.get(player_index, set())

        # Filter out already researched techs
        available = [tech_id for tech_id in available_in_game if tech_id not in researched]

        return available

    def _adjust_tech_score(self, tech_id, base_score, game_state, player_index):
        """
        Adjust tech score based on current game state.

        Priority System:
        - All columns are now researched more evenly (Column 1 was previously neglected)
        - Normal (< 50 command): Column 0 (economy) ≈ Column 1 (military) > Column 2 (command)
        - High command (>= 50): Column 2 (command) > Column 1 (military) > Column 0 (economy)
        - Late game (600+ income): Research nonstop (all techs prioritized)
        """
        score = base_score

        # Extract column from tech_id (format: tech_COL_ROW)
        parts = tech_id.split('_')
        column = int(parts[1])
        row = int(parts[2])

        # Check current state
        territory_count = sum(
            1 for owner in game_state.territory_owners.values()
            if owner == player_index
        )
        total_armies = game_state.get_player_army_count(player_index)
        command_limit = game_state.player_command_limit[player_index]
        current_income = game_state.calculate_player_income(player_index)

        # LATE GAME: 600+ income = research EVERYTHING aggressively
        if current_income >= 600:
            score += 40  # Massive boost to all techs

        # Check if we're at 50+ command (priority flip)
        at_command_limit = total_armies >= 50

        if at_command_limit:
            # Priority: Column 2 > Column 1 > Column 0
            if column == 2:
                # Column 2 (command techs) - HIGHEST priority
                score += 60 - (row * 3)  # Row 0 gets +60, row 1 gets +57, etc.
            elif column == 1:
                # Column 1 (military techs) - MEDIUM priority (increased from 30)
                score += 45 - (row * 2)
            else:  # column == 0
                # Column 0 (economy techs) - LOWEST priority
                score += 10 - (row * 1)
        else:
            # Priority: Column 0 ≈ Column 1 > Column 2 (Column 1 now nearly equal to Column 0)
            if column == 0:
                # Column 0 (economy techs) - HIGH priority
                score += 50 - (row * 2)
                # Extra boost early game
                if territory_count < 16:
                    score += 15
            elif column == 1:
                # Column 1 (military techs) - NOW EQUAL PRIORITY (increased from 30 to 48)
                # Military techs like Improved Training, Animal Handling are very valuable
                score += 48 - (row * 2)
                # Extra boost if we have decent army or are expanding
                if total_armies >= 20 or territory_count >= 10:
                    score += 12
                # Early military tech bonus (rows 0-2 don't require Castle)
                if row <= 2:
                    score += 10  # Encourage early military tech research
            else:  # column == 2
                # Column 2 (command/utility techs) - Still valuable, research alongside others
                # Increased base priority so AI actually researches these
                score += 25 - (row * 2)
                # Boost if we have decent income (can afford to diversify research)
                if current_income >= 150:
                    score += 15

        # Emergency boost for command techs if actually near the limit
        if column == 2 and total_armies > command_limit * 0.8:
            score += 40  # Urgent if hitting the limit

        # War economy gold tier boost: spend excess gold on research aggressively
        # Thresholds scaled to 10/15/20 income tiers
        gold = game_state.player_gold[player_index]
        if gold >= 4000:
            score = int(score * 2.0)   # Tier 3: double all scores
        elif gold >= 2400:
            score = int(score * 1.5)   # Tier 2: 50% boost
        elif gold >= 1200:
            score = int(score * 1.25)  # Tier 1: 25% boost

        return score


class BudgetAllocator:
    """Manages gold allocation across priorities"""

    def allocate_budget(self, available_gold, priorities, difficulty_config):
        """
        Allocate budget across different spending categories.

        Args:
            available_gold (int): Total gold available
            priorities (dict): Priority levels for categories
            difficulty_config (dict): AI difficulty settings

        Returns:
            dict: Budget allocation {category: amount}
        """
        allocation = {
            'buildings': 0,
            'training': 0,
            'tech': 0,
            'heroes': 0
        }

        # Reserve minimal gold for emergencies (AI should spend very aggressively)
        # Reduced from 5% to 2% to make AI stronger by utilizing more resources
        reserve = min(10, int(available_gold * 0.02))  # Only 2% reserve, max 10 gold
        spendable = available_gold - reserve

        # Allocate based on strategic priority
        if priorities.get('mode') == 'economy':
            allocation['buildings'] = int(spendable * 0.5)
            allocation['tech'] = int(spendable * 0.3)
            allocation['training'] = int(spendable * 0.2)
        elif priorities.get('mode') == 'defense':
            allocation['training'] = int(spendable * 0.6)
            allocation['buildings'] = int(spendable * 0.3)
            allocation['tech'] = int(spendable * 0.1)
        elif priorities.get('mode') == 'expansion':
            allocation['training'] = int(spendable * 0.5)
            allocation['buildings'] = int(spendable * 0.3)
            allocation['tech'] = int(spendable * 0.2)
        elif priorities.get('mode') == 'conquest_push':
            # Conquest mode: heavy military spending, minimal economy
            # AI has excess gold and should focus on army building for attacks
            allocation['training'] = int(spendable * 0.75)  # 75% to army
            allocation['buildings'] = int(spendable * 0.15)  # 15% to buildings
            allocation['tech'] = int(spendable * 0.10)       # 10% to tech
        else:  # victory_push
            allocation['training'] = int(spendable * 0.7)
            allocation['buildings'] = int(spendable * 0.2)
            allocation['tech'] = int(spendable * 0.1)

        return allocation


class EconomyManager:
    """Main economic decision coordinator"""

    def __init__(self, ai_player):
        """
        Initialize economy manager.

        Args:
            ai_player: AIPlayer instance (parent)
        """
        self.ai_player = ai_player
        self.building_planner = BuildingPlanner()
        self.tech_researcher = TechResearcher()
        self.budget_allocator = BudgetAllocator()

    def plan_economic_actions(self, game_state, strategic_priority):
        """
        Plan all economic actions for this turn.

        Args:
            game_state: GameState instance
            strategic_priority (str): Strategic mode ('economy', 'defense', etc.)

        Returns:
            list: List of economic actions to take
        """
        actions = []
        player_index = self.ai_player.player_index
        available_gold = game_state.player_gold[player_index]

        # Determine war economy tier based on gold reserves
        # Thresholds scaled to 10/15/20 income tiers
        # Tier 0: < 1200g (normal economy)
        # Tier 1: 1200-2399g (light demolition, boost research)
        # Tier 2: 2400-3999g (moderate demolition, strong research boost)
        # Tier 3: 4000+g (aggressive demolition, force research)
        if available_gold >= 4000:
            gold_tier = 3
        elif available_gold >= 2400:
            gold_tier = 2
        elif available_gold >= 1200:
            gold_tier = 1
        else:
            gold_tier = 0

        # Allocate budget
        budget = self.budget_allocator.allocate_budget(
            available_gold,
            {'mode': strategic_priority},
            self.ai_player.config
        )

        # 0. Tiered building demolition — convert economy to military at high gold
        if gold_tier >= 1:
            # Tier 1: demolish 1, Tier 2: up to 2, Tier 3: up to 4 (aggressive)
            max_demolitions = {1: 1, 2: 2, 3: 4}[gold_tier]
            demolition_targets = self.building_planner.select_buildings_to_demolish(
                game_state, player_index, available_gold, max_demolitions
            )
            for territory, plot_idx in demolition_targets:
                actions.append(('demolish', {
                    'territory': territory,
                    'plot': plot_idx
                }))
                logger.debug(f"War economy tier {gold_tier}: demolish in {territory} (gold: {available_gold})")

        # 1. Building construction (try multiple times to spend all budget)
        # The difficulty variation is applied in building selection, not in whether to build
        remaining_building_budget = budget['buildings']
        max_building_attempts = 20  # Prevent infinite loops
        building_attempts = 0
        territories_planned_for_building = set()  # Track which territories we've planned buildings for

        while remaining_building_budget >= 30 and building_attempts < max_building_attempts:
            building_attempts += 1
            building_action = self.building_planner.select_building_action(
                game_state, player_index, remaining_building_budget, self.ai_player.config,
                exclude_territories=territories_planned_for_building
            )
            if not building_action:
                break  # No more valid buildings to place

            # Check if this is a Castle upgrade (special case)
            if building_action[0] == 'upgrade_castle':
                _, territory, plot_idx, score = building_action
                castle_cost = 100  # Castle upgrade cost

                if remaining_building_budget >= castle_cost:
                    actions.append(('upgrade_castle', {
                        'territory': territory,
                        'plot': plot_idx
                    }))
                    remaining_building_budget -= castle_cost
                    logger.debug(f"Planning Castle upgrade in {territory} (needed for tech research)")
                break  # Only one Castle upgrade per turn

            territory, plot_idx, building_type, score = building_action

            building_cost = game_state.get_effective_cost(building_type,
                game_state.building_types[building_type]['cost'], player_index)

            # Apply difficulty check AFTER finding a good building (not before)
            should_build = random.random() < self.ai_player.config['building_efficiency']
            if not should_build:
                # Strengthened: Even if quality check fails, still build 70% of the time (increased from 50%)
                # This makes AI more aggressive with building placement
                should_build = random.random() < 0.7

            if should_build:
                actions.append(('build', {
                    'territory': territory,
                    'plot': plot_idx,
                    'building': building_type
                }))
                remaining_building_budget -= building_cost
                # Mark territory as planned for building this turn
                territories_planned_for_building.add(territory)
            else:
                break  # Don't keep trying if we decide not to build

        # 2. Technology research
        # War economy tiers 2+: Force research to spend gold
        # Late game (600+ income): Research nonstop
        # Normal game: Try if budget allows
        current_income = game_state.calculate_player_income(player_index)
        is_late_game = current_income >= 600

        if gold_tier >= 2 or is_late_game:
            # HIGH GOLD or LATE GAME: Always research if we can afford ANY tech
            tech_id = self.tech_researcher.select_research_action(
                game_state, player_index, self.ai_player.difficulty
            )
            if tech_id is not None:
                tech = next((t for t in game_state.technologies if t['id'] == tech_id), None)
                if tech and game_state.player_gold[player_index] >= tech['cost']:
                    actions.append(('research', {'tech_id': tech_id}))
                    if gold_tier >= 2:
                        logger.debug(f"War economy research (tier {gold_tier}): {tech['name']}")
                    else:
                        logger.debug(f"Late game research: {tech['name']} (income: {current_income})")
        elif budget['tech'] >= 80:  # Normal game threshold
            tech_id = self.tech_researcher.select_research_action(
                game_state, player_index, self.ai_player.difficulty
            )
            if tech_id is not None:
                # Apply difficulty check, but still research 60% of the time if it fails
                if random.random() < self.ai_player.config['tech_research_rate'] or random.random() < 0.6:
                    actions.append(('research', {'tech_id': tech_id}))

        return actions


# Test the economy module if run directly
if __name__ == '__main__':
    logger.info("AI Economy Module Test")
    logger.info("=" * 60)
    logger.info("Module loaded successfully")
    logger.info("Classes available:")
    logger.info("  - BuildingPlanner: Building construction decisions")
    logger.info("  - TechResearcher: Technology research selection")
    logger.info("  - BudgetAllocator: Resource budget management")
    logger.info("  - EconomyManager: Economic decision coordinator")
