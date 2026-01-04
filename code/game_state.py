# -*- coding: utf-8 -*-
# game_state.py
# Game state management

"""
War of Avareon - Core Game Logic and State Management

This module contains all game logic and state management for War of Avareon,
a turn-based territory conquest strategy game with economic and military systems.

Key Classes:
    MovementOrder: Represents a planned army movement
    Battle: Represents a combat engagement between armies
    GameState: Main game logic controller

Core Systems:
    1. Territory Control: Ownership, adjacency, victory conditions
    2. Economic System: Income generation, building construction
    3. Military System: Army training, movement, combat
    4. Building System: Farms, Mines, Barracks, Keeps, Squares
    5. Order System: Planning phase orders, simultaneous execution
    6. Battle System: Deterministic combat with unit composition
    7. Phase Management: Setup → Planning → Execution → Battles

Game Flow:
    Setup Phase:
        - Players alternate choosing starting territories (5 each)
        - Starting resources and armies granted
    
    Playing Phase (repeats):
        1. Planning Phase: Issue orders (movement, construction, training)
        2. Execution Phase: All orders execute simultaneously
        3. Battle Phase: Resolve all battles sequentially
        4. Income Phase: Collect income, finish construction/training
        5. Next Player's Turn
    
    End Phase:
        - Victory condition met (30+ territories or total conquest)
        - Victory screen displayed

Economic System:
    - Base Income: Each territory generates 5-20 gold/turn
    - Buildings: Farms (+10), Mines (+15), Squares (×1.5 multiplier)
    - Training Costs: Swordsman (25), Archer (20), Pikeman (30), Cavalry (40)
    - Building Costs: Farm (30), Mine (40), Barracks (50), Keep (100), Square (60)

Military System:
    - Army Limit: 15 per territory (prevents spam)
    - Movement: Simultaneous execution, adjacent territories only
    - Unit Types: Swordsman, Archer, Pikeman, Cavalry
    - Counter System: Rock-paper-scissors (S>P>C>A>S)
    - Combat: Deterministic based on composition + terrain

Building System:
    - Construction Time: 1 turn (Keep: 2 turns)
    - Build Limit: One building per territory per turn
    - Plot System: Multiple building slots per territory
    - Training Queue: Up to 5 units per Barracks

Battle System (Tier 3):
    - Unit Strength: Swordsman (10), Archer (8), Pikeman (12), Cavalry (15)
    - Counter Multipliers: Counter (1.25x), Countered (0.75x), Neutral (1.0x)
    - Keep Bonus: +2 effective armies for defender
    - Casualties: Winner = Winner - Loser (min 1), Loser = 0

Phase Tracking:
    Phase 1A: Constants defined (army limits, unit types)
    Phase 1B: Error handling added (log_error, safe data access)
    Phase 1C: Documentation added (comprehensive docstrings)

Data Structures:
    territory_owners: {territory_name: player_index} (-1 = neutral)
    armies: {territory_name: total_count}
    armies_unmoved: {territory_name: count} (can move this turn)
    armies_moved: {territory_name: count} (already moved)
    army_units: {territory_name: [unit_dicts]} (Phase 3, lazy init)
    buildings: {territory: {plot_index: building_type}}
    under_construction: {territory: {plot_index: (type, turns_left)}}
    training_queue: {territory: {barracks_plot: [(type, turns_left)]}}
    movement_orders: [MovementOrder objects]
    pending_battles: [Battle objects]

Constants:
    MAX_ARMIES_PER_TERRITORY: 15
    UNIT_TYPES: Dict of unit stats and counter relationships
    building_types: Dict of building costs and effects

Usage:
    game = GameState(num_players=2)
    # Game loop in main.py interacts with game
    
Dependencies:
    - map_data: Territory and adjacency information

Related Modules:
    - main.py: UI and rendering (uses GameState)
    - map_data.py: Territory data and adjacency
"""

import map_data

class MovementOrder:
    """Represents a planned army movement order"""
    def __init__(self, from_territory, to_territory, army_count, player, unit_ids=None):
        self.from_territory = from_territory
        self.to_territory = to_territory
        self.army_count = army_count
        self.player = player
        self.unit_ids = unit_ids or []  # List of specific unit IDs (Phase 3)
        self.order_id = id(self)  # Unique ID for this order

class Battle:
    """Represents a battle between armies in a territory"""
    def __init__(self, territory):
        self.territory = territory
        self.armies = {}  # {player_index: army_count}
        self.original_owner = None  # Who owned territory before battle
        self.resolved = False
        self.winner = None  # Will be set after resolution
        self.keep_bonus = 0  # Keep defense bonus (if any)
        self.keep_bonus_player = None  # Which player has the Keep bonus
        self.original_garrison = 0  # Original garrison size (before Keep bonus)
        self.army_compositions = {}  # NEW: {player_index: {unit_type: count}}
    
    def add_army(self, player, count, composition=None):
        """Add an army to this battle"""
        if player in self.armies:
            self.armies[player] += count
        else:
            self.armies[player] = count
        
        # Track composition
        if composition:
            if player not in self.army_compositions:
                self.army_compositions[player] = {}
            for unit_type, unit_count in composition.items():
                self.army_compositions[player][unit_type] = self.army_compositions[player].get(unit_type, 0) + unit_count
    
    def get_total_armies(self):
        """Get total number of armies in battle"""
        return sum(self.armies.values())
    
    def get_player_count(self):
        """Get number of different players involved"""
        return len(self.armies)

class GameState:
    # Constants
    MAX_ARMIES_PER_TERRITORY = 15  # Army limit to prevent spam
    
    # Unit type definitions (TIER 3: Multiple Unit Types)
    UNIT_TYPES = {
        'Swordsman': {
            'cost': 25,
            'letter': 'S',
            'name': 'Swordsman',
            'counters': 'Pikeman',      # Swordsman > Pikeman
            'countered_by': 'Archer'    # Archer > Swordsman
        },
        'Archer': {
            'cost': 20,
            'letter': 'A',
            'name': 'Archer',
            'counters': 'Swordsman',    # Archer > Swordsman
            'countered_by': 'Cavalry'   # Cavalry > Archer
        },
        'Pikeman': {
            'cost': 30,
            'letter': 'P',
            'name': 'Pikeman',
            'counters': 'Cavalry',      # Pikeman > Cavalry
            'countered_by': 'Swordsman' # Swordsman > Pikeman
        },
        'Cavalry': {
            'cost': 40,
            'letter': 'C',
            'name': 'Cavalry',
            'counters': 'Archer',       # Cavalry > Archer
            'countered_by': 'Pikeman'   # Pikeman > Cavalry
        }
    }
    
    def __init__(self, num_players=2):
        self.num_players = num_players
        self.current_player = 0  # Index of current player (0 to num_players-1)
        self.player_colors = [
            (200, 50, 50),    # Red
            (50, 50, 200),    # Blue
            (50, 200, 50),    # Green
            (200, 200, 50)    # Yellow
        ]
        
        # Territory ownership: territory_name -> player_index (-1 = neutral)
        self.territory_owners = {territory: -1 for territory in map_data.get_all_territories()}
        
        # Armies: territory_name -> army_size
        self.armies = {territory: 0 for territory in map_data.get_all_territories()}
        
        # Track armies that have/haven't moved this turn
        # armies_unmoved = can still move this turn
        # armies_moved = already moved, can't move again
        self.armies_unmoved = {territory: 0 for territory in map_data.get_all_territories()}
        self.armies_moved = {territory: 0 for territory in map_data.get_all_territories()}
        
        # Individual army tracking (for Phase 3: Army Composition UI)
        # Lazy initialization - only created when territory composition UI is opened
        # Format: {territory: [{'id': int, 'status': str, 'order': order_ref}, ...]}
        # status: 'ready', 'moved', 'ordered'
        self.army_units = {}
        
        # Resource system - gold per player
        self.player_gold = [0] * num_players  # Gold for each player
        self.starting_gold = 100  # Starting gold for each player
        for i in range(num_players):
            self.player_gold[i] = self.starting_gold
        
        # Building system
        # buildings: {territory: {plot_index: building_type}} or {plot_index: None} for empty
        self.buildings = {}  # Completed buildings
        # under_construction: {territory: {plot_index: (building_type, turns_remaining)}}
        self.under_construction = {}  # Buildings being built
        
        # Track buildings started this turn (one per territory per turn limit)
        self.buildings_started_this_turn = set()  # Set of territory names
        
        # Training system (for Barracks)
        # training_queue: {territory: {barracks_plot_index: [(unit_type, turns_remaining), ...]}}
        self.training_queue = {}  # Unit training queues
        
        # Building costs and definitions
        self.building_types = {
            'Farm': {'cost': 30, 'letter': 'F', 'effect': 'income', 'value': 10, 'time': 1},
            'Mine': {'cost': 40, 'letter': 'M', 'effect': 'income', 'value': 15, 'time': 1},
            'Barracks': {'cost': 50, 'letter': 'B', 'effect': 'recruitment', 'value': True, 'time': 1},
            'Keep': {'cost': 100, 'letter': 'K', 'effect': 'defense', 'value': 2, 'time': 2},
            'Square': {'cost': 60, 'letter': 'S', 'effect': 'multiplier', 'value': 1.5, 'time': 1}
        }
        
        # Game phase: 'setup', 'playing', 'ended'
        self.phase = 'setup'
        
        # For setup phase: track how many territories each player has chosen
        self.territories_chosen = [0] * num_players
        self.max_starting_territories = 5  # Each player chooses 5 starting territories
        
        # Selected territory (for UI interaction)
        self.selected_territory = None
        
        # Message log for combat and actions
        self.messages = []
        # No message limit - keep entire game history for scrolling
        
        # Winner tracking
        self.winner = -1  # -1 = no winner, 0-3 = player index
        
        # Victory condition settings (for future customization)
        self.victory_condition = 'territory_count'  # Options: 'total_conquest', 'territory_count', 'majority', 'capitals'
        self.victory_territory_threshold = 30  # For 'territory_count' mode
        
        # Turn tracking
        self.turn_number = 0  # Track turns for construction completion
        
        # Camera system (for future zoom/pan support)
        self.camera_x = 0.0          # Camera offset X (world units)
        self.camera_y = 0.0          # Camera offset Y (world units)
        self.camera_zoom = 1.0       # Zoom level (1.0 = normal)
        self.min_zoom = 0.5          # Maximum zoom out
        self.max_zoom = 3.0          # Maximum zoom in
        
        # Advanced movement system
        self.selected_army = None    # (territory_name, army_count) or None
        self.movement_orders = []    # List of MovementOrder objects
        self.pending_battles = []    # List of Battle objects (for future battle phase)
        self.turn_phase = 'planning' # 'planning', 'execution', 'battles'
        
        # UI preferences
        self.sidebar_expanded = True # Collapsible sidebar state (True = expanded, False = collapsed)
        
        # Phase B: Exclusive tab system state
        self.active_sidebar_tab = 'action_queue'  # Default active tab
        self.sidebar_tabs = ['technology', 'heroes', 'action_queue', 'action_log', 'quests', 'chat']  # Available tabs (Chat added)
        
        # Chat system
        self.chat_messages = []  # List of (timestamp, player_id, message) tuples
        
        # Testing mode - allows controlling all players for testing
        self.testing_mode = True  # Set to False for normal gameplay
        
        # Error tracking (Phase 1B: Error Handling)
        self.errors = []  # List of error messages for debugging
        self.max_errors = 50  # Keep last 50 errors
    
    def log_error(self, message, exception=None):
        """
        Log error for debugging without crashing the game.
        
        Args:
            message: Error description
            exception: Optional exception object
        """
        error_msg = f"[ERROR] {message}"
        if exception:
            error_msg += f": {str(exception)}"
        
        print(error_msg)  # Print to console for debugging
        
        # Store in error list
        self.errors.append(error_msg)
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)  # Remove oldest error
    
    def safe_get_territory_data(self, territory, data_dict, data_name, default=None):
        """
        Safely get territory data with error handling.
        
        Args:
            territory: Territory name
            data_dict: Dictionary to access
            data_name: Name of data (for error message)
            default: Default value if not found
            
        Returns:
            Value from dictionary, or default if not found
        """
        try:
            return data_dict[territory]
        except KeyError:
            self.log_error(f"Territory '{territory}' not found in {data_name}")
            return default
        except Exception as e:
            self.log_error(f"Unexpected error accessing {data_name} for territory '{territory}'", e)
            return default
    
    def get_player_color(self, player_index):
        """Get the color for a specific player"""
        if player_index == -1:
            return (150, 150, 150)  # Neutral gray
        return self.player_colors[player_index]
    
    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates (camera-aware)"""
        screen_x = (world_x * self.camera_zoom) - self.camera_x
        screen_y = (world_y * self.camera_zoom) - self.camera_y
        return (int(screen_x), int(screen_y))
    
    def screen_to_world(self, screen_x, screen_y):
        """Convert screen coordinates to world coordinates (camera-aware)"""
        # Protect against division by zero
        if self.camera_zoom == 0:
            self.camera_zoom = 0.01
        
        world_x = (screen_x + self.camera_x) / self.camera_zoom
        world_y = (screen_y + self.camera_y) / self.camera_zoom
        return (world_x, world_y)
    
    def select_army(self, territory):
        """Select an army for issuing movement orders"""
        # Validate: must be current player's territory (unless testing mode)
        if not self.testing_mode:
            if self.territory_owners.get(territory, -1) != self.current_player:
                return False
        
        # Must have unmoved armies
        if self.armies_unmoved.get(territory, 0) <= 0:
            self.add_message("No armies available to move in this territory")
            return False
        
        # Select the army
        army_count = self.armies_unmoved[territory]
        self.selected_army = (territory, army_count)
        return True
    
    def deselect_army(self):
        """Deselect the currently selected army"""
        self.selected_army = None
    
    def get_unit_composition(self, territory):
        """
        Get the composition of units in a territory.
        Returns dict: {unit_type: count}
        Example: {'Swordsman': 3, 'Archer': 2, 'Cavalry': 1}
        """
        if territory not in self.army_units:
            # Lazy init if needed
            self.ensure_army_units_exist(territory)
        
        composition = {}
        for unit in self.army_units.get(territory, []):
            unit_type = unit.get('type', 'Swordsman')
            composition[unit_type] = composition.get(unit_type, 0) + 1
        
        return composition
    
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
    
    def calculate_army_effective_strength(self, composition, enemy_composition):
        """
        Calculate the total effective strength of an army against an enemy.
        Returns: float representing total effective strength
        """
        if not composition:
            return 0.0
        
        if not enemy_composition:
            # No enemies, just return total count
            return float(sum(composition.values()))
        
        total_strength = 0.0
        for unit_type, count in composition.items():
            effectiveness = self.calculate_unit_effectiveness(unit_type, enemy_composition)
            total_strength += count * effectiveness
        
        return total_strength
    
    def calculate_army_base_strength(self, composition):
        """
        Calculate the total BASE strength of an army WITHOUT counter modifiers.
        
        Used for Keep defense battles where unit types should not matter.
        Keep defense is type-neutral - only numbers matter.
        
        Returns: float representing total base strength
        """
        if not composition:
            return 0.0
        
        total_strength = 0.0
        for unit_type, count in composition.items():
            # Get base strength from UNIT_TYPES
            unit_info = self.UNIT_TYPES.get(unit_type)
            if unit_info:
                base_strength = unit_info['strength']
                total_strength += count * base_strength
            else:
                # Fallback if unit type unknown
                total_strength += count * 10  # Default strength
        
        return total_strength
    
    def apply_casualties_with_priority(self, territory, casualties, enemy_composition):
        """
        Remove casualties from a territory's army using priority system:
        1. Remove countered units first (0.5x effectiveness)
        2. Remove neutral units second (1x effectiveness)  
        3. Remove advantaged units last (2x effectiveness)
        
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
        
        # Apply casualties in priority order
        casualties_applied = {}
        remaining_casualties = casualties
        
        # Priority 1: Countered units
        for unit in countered_units:
            if remaining_casualties <= 0:
                break
            unit_type = unit.get('type', 'Swordsman')
            casualties_applied[unit_type] = casualties_applied.get(unit_type, 0) + 1
            units.remove(unit)
            remaining_casualties -= 1
        
        # Priority 2: Neutral units
        for unit in neutral_units:
            if remaining_casualties <= 0:
                break
            unit_type = unit.get('type', 'Swordsman')
            casualties_applied[unit_type] = casualties_applied.get(unit_type, 0) + 1
            units.remove(unit)
            remaining_casualties -= 1
        
        # Priority 3: Advantaged units
        for unit in advantaged_units:
            if remaining_casualties <= 0:
                break
            unit_type = unit.get('type', 'Swordsman')
            casualties_applied[unit_type] = casualties_applied.get(unit_type, 0) + 1
            units.remove(unit)
            remaining_casualties -= 1
        
        return casualties_applied
    
    def ensure_army_units_exist(self, territory):
        """
        Ensure territory has individual army units tracked (lazy initialization).
        
        This implements lazy initialization for the Phase 3 army composition system.
        Instead of creating unit data for all territories upfront, we create it only
        when needed (when opening army composition UI or creating unit-specific orders).
        
        Synchronization Logic:
            Creates unit list based on current armies_unmoved and armies_moved totals.
            Uses LIVE totals, not armies[territory] which only updates at turn end.
        
        Mismatch Detection:
            Recreates unit list if any of these conditions are true:
            1. No unit list exists yet (first access)
            2. Count mismatch: len(army_units) != total armies
            3. Status mismatch: ready/moved counts don't match unmoved/moved
        
        Why Mismatches Happen:
            - Training completed (new units added)
            - Units moved (status changed)
            - Battle resolution (units removed)
            - Order execution (status changed)
        
        Unit Structure:
            Each unit is a dict with:
            - id: Unique identifier within territory (0-indexed)
            - status: 'ready', 'moved', or 'ordered'
            - order: Reference to MovementOrder (if ordered)
            - type: Unit type ('Swordsman' for legacy armies)
        
        Status Categories:
            - 'ready': Can be commanded this turn
            - 'ordered': Has movement order (still part of unmoved count)
            - 'moved': Already moved this turn (exhausted)
        
        Args:
            territory: Territory name to ensure units for
        
        Returns:
            list: List of unit dictionaries for this territory
        
        Side Effects:
            - May create or recreate self.army_units[territory]
            - Prints debug messages when recreating
        
        Used By:
            - Army composition UI (for displaying units)
            - add_movement_order_for_units() (for creating orders)
            - Order execution (for updating status)
        
        Performance Note:
            Lazy initialization means we only create unit data when needed,
            which is much more efficient than tracking all territories always.
        """
        # Get current totals (use live values, not cached armies[territory])
        unmoved = self.armies_unmoved.get(territory, 0)
        moved = self.armies_moved.get(territory, 0)
        total = unmoved + moved  # LIVE total, not armies[territory] which updates at turn end
        
        # Check if we need to recreate
        needs_recreation = False
        if territory not in self.army_units:
            needs_recreation = True
        else:
            # Check if count matches LIVE total
            if len(self.army_units[territory]) != total:
                # COUNT MISMATCH - recreate
                print(f"Recreating army units for {territory}: cached {len(self.army_units[territory])}, actual {total}")
                needs_recreation = True
            else:
                # Count matches, but check if STATUS distribution matches
                # Note: 'ordered' units are still part of 'ready/unmoved', so we count them together
                cached_ready = sum(1 for u in self.army_units[territory] if u['status'] in ['ready', 'ordered'])
                cached_moved = sum(1 for u in self.army_units[territory] if u['status'] == 'moved')
                if cached_ready != unmoved or cached_moved != moved:
                    # STATUS MISMATCH - recreate
                    print(f"Recreating army units for {territory}: status mismatch")
                    print(f"  Cached: {cached_ready} ready/ordered, {cached_moved} moved")
                    print(f"  Actual: {unmoved} unmoved, {moved} moved")
                    needs_recreation = True
        
        if needs_recreation:
            # Preserve existing unit types if we have them
            existing_types = {}
            if territory in self.army_units:
                for unit in self.army_units[territory]:
                    existing_types[unit['id']] = unit.get('type', 'Swordsman')
            
            units = []
            # Add ready units first (can be commanded)
            for i in range(unmoved):
                units.append({
                    'id': i,
                    'status': 'ready',
                    'order': None,
                    'type': existing_types.get(i, 'Swordsman')  # BUGFIX: Preserve type if exists
                })
            # Add moved units (exhausted this turn)
            for i in range(moved):
                unit_id = unmoved + i
                units.append({
                    'id': unit_id,
                    'status': 'moved',
                    'order': None,
                    'type': existing_types.get(unit_id, 'Swordsman')  # BUGFIX: Preserve type if exists
                })
            
            self.army_units[territory] = units
        
        return self.army_units[territory]
    
    def destroy_buildings(self, territory):
        """Destroy all buildings (completed and under construction) in a territory"""
        # Remove completed buildings
        if territory in self.buildings:
            building_count = sum(1 for building in self.buildings[territory].values() if building is not None)
            if building_count > 0:
                self.add_message(f"  {building_count} building(s) destroyed in {territory}")
            del self.buildings[territory]
        
        # Cancel buildings under construction
        if territory in self.under_construction:
            construction_count = len(self.under_construction[territory])
            if construction_count > 0:
                self.add_message(f"  {construction_count} construction(s) cancelled in {territory}")
            del self.under_construction[territory]
    
    def add_movement_order(self, from_territory, to_territory):
        """Create a movement order for the selected army"""
        # Validate: army must be selected
        if not self.selected_army:
            return False
        
        selected_territory, army_count = self.selected_army
        
        # Validate: from_territory matches selected army
        if from_territory != selected_territory:
            return False
        
        # Validate: territories must be adjacent
        if not map_data.are_adjacent(from_territory, to_territory):
            self.add_message("Territories are not adjacent!")
            return False
        
        # Validate: must have unmoved armies
        if self.armies_unmoved.get(from_territory, 0) <= 0:
            self.add_message("No armies available to move")
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
        # In testing mode, use the actual owner of the territory
        order_player = self.territory_owners[from_territory] if self.testing_mode else self.current_player
        
        order = MovementOrder(
            from_territory=from_territory,
            to_territory=to_territory,
            army_count=army_count,
            player=order_player
        )
        
        self.movement_orders.append(order)
        self.add_message(f"Order created: {army_count} armies {from_territory} ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ {to_territory}")
        
        # Keep army selected for chaining orders
        return True
    
    def add_movement_order_for_units(self, from_territory, to_territory, unit_ids):
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
            1. Auto-cancel orders → Reset units to 'ready'
            2. Validate status → Units are now 'ready' (PASS)
            3. Create new order → SUCCESS
        
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
        # Validate: must have units selected
        if not unit_ids:
            return False
        
        # Ensure army units exist
        units = self.ensure_army_units_exist(from_territory)
        
        # FIRST: Auto-cancel any existing orders for selected units
        # This must happen BEFORE status validation
        orders_to_remove = []
        units_to_reset = []
        
        for i, order in enumerate(self.movement_orders):
            if order.from_territory == from_territory and order.unit_ids:
                # Check if any unit IDs overlap
                overlap = set(unit_ids) & set(order.unit_ids)
                if overlap:
                    # Collect units to reset
                    if order.from_territory in self.army_units:
                        for unit in self.army_units[order.from_territory]:
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
        
        # Validate: territories must be adjacent (with error handling)
        try:
            if not map_data.are_adjacent(from_territory, to_territory):
                self.add_message("Territories are not adjacent!")
                return False
        except Exception as e:
            self.log_error(f"Failed to check adjacency between {from_territory} and {to_territory}", e)
            self.add_message("Error checking territory adjacency")
            return False
        
        # Get the owner of the territory (with error handling)
        try:
            order_player = self.territory_owners.get(from_territory, -1)
            if order_player == -1:
                self.add_message("Territory has no owner!")
                return False
        except Exception as e:
            self.log_error(f"Failed to get owner for territory {from_territory}", e)
            return False
        
        # Create the order with unit IDs
        order = MovementOrder(
            from_territory=from_territory,
            to_territory=to_territory,
            army_count=len(unit_ids),
            player=order_player,
            unit_ids=unit_ids
        )
        
        self.movement_orders.append(order)
        
        # Mark units as 'ordered'
        for unit in units:
            if unit['id'] in unit_ids:
                unit['status'] = 'ordered'
                unit['order'] = order
        
        self.add_message(f"Order created: {len(unit_ids)} armies {from_territory} â†’ {to_territory}")
        
        return True
    
    def cancel_movement_order(self, order_index):
        """Cancel a specific movement order"""
        if 0 <= order_index < len(self.movement_orders):
            order = self.movement_orders[order_index]
            
            # Reset unit status if this order has unit_ids (Phase 3)
            if order.unit_ids and order.from_territory in self.army_units:
                units = self.army_units[order.from_territory]
                for unit in units:
                    # Reset any units that have this order
                    if unit.get('order') == order:
                        unit['status'] = 'ready'
                        unit['order'] = None
            self.add_message(f"Order cancelled: {order.from_territory} ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ {order.to_territory}")
            self.movement_orders.pop(order_index)
            return True
        return False
    
    def cancel_all_orders(self):
        """Cancel all movement orders"""
        count = len(self.movement_orders)
        
        # Reset all unit statuses (Phase 3)
        for order in self.movement_orders:
            if order.unit_ids and order.from_territory in self.army_units:
                units = self.army_units[order.from_territory]
                for unit in units:
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
            - armies_unmoved → armies_moved for entire count
            
            Phase 3 (Individual units):
            - Unit status: 'ordered' → 'moved'
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
        if not self.movement_orders:
            self.add_message("No orders to execute")
            return
        
        # Clear army selection
        self.selected_army = None
        
        # Change phase to execution
        self.turn_phase = 'execution'
        self.add_message(f"=== Executing {len(self.movement_orders)} orders ===")
        
        # Track which territories will receive armies from which players
        # Format: {territory: {player: army_count}}
        incoming_armies = {}
        
        # Step 1: Validate moves and check army limits for friendly territories
        valid_orders = []
        for order in self.movement_orders:
            to_terr = order.to_territory
            from_terr = order.from_territory
            army_count = order.army_count
            
            # Check if this is a reinforcement (moving to own territory)
            dest_owner = self.territory_owners.get(to_terr, -1)
            if dest_owner == order.player:
                # This is a reinforcement - check army limit
                current_garrison = self.armies.get(to_terr, 0)
                if current_garrison + army_count > self.MAX_ARMIES_PER_TERRITORY:
                    # Would exceed limit - block this order
                    excess = (current_garrison + army_count) - self.MAX_ARMIES_PER_TERRITORY
                    self.add_message(f"Player {order.player + 1}: Cannot reinforce {to_terr} - would exceed army limit!")
                    self.add_message(f"  Current: {current_garrison}, Reinforcing: {army_count}, Limit: {self.MAX_ARMIES_PER_TERRITORY}")
                    self.add_message(f"  {army_count} armies remain in {from_terr}")
                    continue  # Skip this order, armies stay in source
            
            # Order is valid
            valid_orders.append(order)
        
        # Step 2: Deduct armies from source territories (only for valid orders)
        # Also track unit compositions for battles
        moving_compositions = {}  # {(to_territory, player): {unit_type: count}}
        
        for order in valid_orders:
            from_terr = order.from_territory
            to_terr = order.to_territory
            player = order.player
            
            # Track composition key
            comp_key = (to_terr, player)
            
            # Check if this order specifies individual units (Phase 3)
            if order.unit_ids:
                # NEW SYSTEM: Remove specific units and track their types
                army_count = len(order.unit_ids)
                
                # Collect unit types that are moving
                moving_unit_types = {}
                
                # Remove units from army_units if it exists
                if from_terr in self.army_units:
                    units = self.army_units[from_terr]
                    
                    # Collect types of moving units
                    for unit in units:
                        if unit['id'] in order.unit_ids:
                            unit_type = unit.get('type', 'Swordsman')
                            moving_unit_types[unit_type] = moving_unit_types.get(unit_type, 0) + 1
                    
                    # Remove units with these IDs
                    self.army_units[from_terr] = [u for u in units if u['id'] not in order.unit_ids]
                    
                    # Reassign IDs to remaining units (0-indexed, sequential)
                    for i, unit in enumerate(self.army_units[from_terr]):
                        unit['id'] = i
                        # Clear order references
                        if unit.get('order') == order:
                            unit['order'] = None
                
                # Store composition for battle
                if comp_key not in moving_compositions:
                    moving_compositions[comp_key] = {}
                for unit_type, count in moving_unit_types.items():
                    moving_compositions[comp_key][unit_type] = moving_compositions[comp_key].get(unit_type, 0) + count
                
                # Update totals
                self.armies_unmoved[from_terr] -= army_count
                # Also update the cached total immediately for consistent display
                self.armies[from_terr] = self.armies_unmoved[from_terr] + self.armies_moved.get(from_terr, 0)
                self.add_message(f"Player {order.player + 1}: {army_count} armies leave {from_terr}")
            else:
                # LEGACY SYSTEM: Use army_count from order, default to Swordsmen
                army_count = order.army_count
                
                # Default composition (all Swordsmen for legacy orders)
                if comp_key not in moving_compositions:
                    moving_compositions[comp_key] = {}
                moving_compositions[comp_key]['Swordsman'] = moving_compositions[comp_key].get('Swordsman', 0) + army_count
                
                # Deduct from unmoved armies
                if self.armies_unmoved[from_terr] >= army_count:
                    self.armies_unmoved[from_terr] -= army_count
                    # Update cached total
                    self.armies[from_terr] = self.armies_unmoved[from_terr] + self.armies_moved.get(from_terr, 0)
                    self.add_message(f"Player {order.player + 1}: {army_count} armies leave {from_terr}")
                else:
                    # Shouldn't happen with proper validation, but handle gracefully
                    available = self.armies_unmoved[from_terr]
                    self.armies_unmoved[from_terr] = 0
                    army_count = available
                    # Update cached total
                    self.armies[from_terr] = self.armies_moved.get(from_terr, 0)
                    self.add_message(f"Warning: Only {available} armies available from {from_terr}")
            
            # Track where they're going
            if to_terr not in incoming_armies:
                incoming_armies[to_terr] = {}
            if order.player not in incoming_armies[to_terr]:
                incoming_armies[to_terr][order.player] = 0
            incoming_armies[to_terr][order.player] += army_count
        
        # Step 3: Process arrivals and detect battles
        self.pending_battles = []
        
        for territory, player_armies in incoming_armies.items():
            current_owner = self.territory_owners[territory]
            # Use LIVE garrison count (unmoved + moved), not cached armies[territory]
            current_garrison = self.armies_unmoved.get(territory, 0) + self.armies_moved.get(territory, 0)
            
            # Check for Keep defense (works even without garrison!)
            keep_bonus = 0
            has_keep = False
            if current_owner != -1 and territory in self.buildings:
                for plot_index, building_type in self.buildings[territory].items():
                    if building_type == 'Keep':
                        has_keep = True
                        keep_bonus = 2
                        break
            
            # Add defender's forces (garrison + Keep)
            if current_owner != -1 and (current_garrison > 0 or has_keep):
                # Territory has defense (garrison and/or Keep)
                if current_owner not in player_armies:
                    player_armies[current_owner] = 0
                
                # Add garrison
                player_armies[current_owner] += current_garrison
                
                # Add Keep defense
                if has_keep:
                    player_armies[current_owner] += keep_bonus
                    if current_garrison > 0:
                        self.add_message(f"Keep in {territory} provides +2 defense bonus!")
                    else:
                        self.add_message(f"Keep in {territory} defends alone with 2 armies!")
            
            # Count unique players involved
            unique_players = len(player_armies)
            
            if unique_players == 1:
                # Only one player's armies - auto-capture!
                player = list(player_armies.keys())[0]
                army_count = player_armies[player]
                
                # Subtract Keep bonus if defender had it (bonus doesn't transfer)
                if current_owner != -1 and player == current_owner and keep_bonus > 0:
                    army_count = max(1, army_count - keep_bonus)
                
                if current_owner == -1:
                    # Neutral territory - no buildings to destroy
                    self.territory_owners[territory] = player
                    self.armies[territory] = army_count
                    self.armies_unmoved[territory] = 0  # Just arrived, can't move again
                    self.armies_moved[territory] = army_count
                    self.add_message(f"Player {player + 1} captures {territory} ({army_count} armies)")
                    
                    # BUGFIX: Create units with correct types (not just counts)
                    comp_key = (territory, player)
                    composition = moving_compositions.get(comp_key, {})
                    
                    # Clear old units and create new ones with correct types
                    self.army_units[territory] = []
                    unit_id = 0
                    
                    if composition:
                        # Create units based on actual composition
                        for unit_type, count in composition.items():
                            for _ in range(count):
                                self.army_units[territory].append({
                                    'id': unit_id,
                                    'status': 'moved',
                                    'order': None,
                                    'type': unit_type
                                })
                                unit_id += 1
                    else:
                        # Fallback: create default Swordsmen if no composition found
                        for _ in range(army_count):
                            self.army_units[territory].append({
                                'id': unit_id,
                                'status': 'moved',
                                'order': None,
                                'type': 'Swordsman'
                            })
                            unit_id += 1
                    
                    # BUGFIX: Check for victory after neutral conquest
                    print(f"[DEBUG] Calling check_victory() after neutral conquest")
                    self.check_victory()
                elif current_owner == player:
                    # Moving to own territory - reinforcement (limit already checked)
                    self.armies[territory] = army_count
                    self.armies_unmoved[territory] = 0
                    self.armies_moved[territory] = army_count
                    self.add_message(f"Player {player + 1} reinforces {territory} ({army_count} armies)")
                    
                    # BUGFIX: Create units with correct types (not just counts)
                    comp_key = (territory, player)
                    composition = moving_compositions.get(comp_key, {})
                    
                    # Clear old units and create new ones with correct types
                    self.army_units[territory] = []
                    unit_id = 0
                    
                    if composition:
                        # Create units based on actual composition
                        for unit_type, count in composition.items():
                            for _ in range(count):
                                self.army_units[territory].append({
                                    'id': unit_id,
                                    'status': 'moved',
                                    'order': None,
                                    'type': unit_type
                                })
                                unit_id += 1
                    else:
                        # Fallback: create default Swordsmen if no composition found
                        for _ in range(army_count):
                            self.army_units[territory].append({
                                'id': unit_id,
                                'status': 'moved',
                                'order': None,
                                'type': 'Swordsman'
                            })
                            unit_id += 1
                else:
                    # Undefended enemy territory - destroy buildings
                    self.destroy_buildings(territory)
                    self.territory_owners[territory] = player
                    self.armies[territory] = army_count
                    self.armies_unmoved[territory] = 0
                    self.armies_moved[territory] = army_count
                    self.add_message(f"Player {player + 1} takes {territory} ({army_count} armies)")
                    
                    # BUGFIX: Create units with correct types (not just counts)
                    comp_key = (territory, player)
                    composition = moving_compositions.get(comp_key, {})
                    
                    # Clear old units and create new ones with correct types
                    self.army_units[territory] = []
                    unit_id = 0
                    
                    if composition:
                        # Create units based on actual composition
                        for unit_type, count in composition.items():
                            for _ in range(count):
                                self.army_units[territory].append({
                                    'id': unit_id,
                                    'status': 'moved',
                                    'order': None,
                                    'type': unit_type
                                })
                                unit_id += 1
                    else:
                        # Fallback: create default Swordsmen if no composition found
                        for _ in range(army_count):
                            self.army_units[territory].append({
                                'id': unit_id,
                                'status': 'moved',
                                'order': None,
                                'type': 'Swordsman'
                            })
                            unit_id += 1
                    
                    # BUGFIX: Check for victory after enemy conquest
                    print(f"[DEBUG] Calling check_victory() after undefended enemy conquest")
                    self.check_victory()
            else:
                # Multiple players - BATTLE!
                battle = Battle(territory)
                battle.original_owner = current_owner
                battle.original_garrison = current_garrison  # Store original garrison
                
                # Store Keep bonus info
                if current_owner != -1 and keep_bonus > 0:
                    battle.keep_bonus = keep_bonus
                    battle.keep_bonus_player = current_owner
                
                for player, count in player_armies.items():
                    # Get composition for this player
                    comp_key = (territory, player)
                    if player == current_owner:
                        # Defender - use territory composition
                        composition = self.get_unit_composition(territory)
                    else:
                        # Attacker - use moving composition
                        composition = moving_compositions.get(comp_key, {'Swordsman': count})
                    
                    battle.add_army(player, count, composition)
                
                self.pending_battles.append(battle)
                
                # Mark territory as contested
                self.add_message(f"ÃƒÂ¢Ã…Â¡Ã¢â‚¬ÂÃƒÂ¯Ã‚Â¸Ã‚Â BATTLE at {territory}! {unique_players} players clash!")
                player_list = ", ".join([f"Player {p+1} ({c})" for p, c in player_armies.items()])
                self.add_message(f"  Forces: {player_list}")
        
        # Clear executed orders
        self.movement_orders = []
        
        # Transition to battle phase if there are battles
        if self.pending_battles:
            self.turn_phase = 'battles'
            self.add_message(f"=== {len(self.pending_battles)} battles to resolve! ===")
        else:
            # No battles, go back to planning
            self.turn_phase = 'planning'
            self.add_message("=== All orders executed successfully ===")
    
    
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
            
            # Calculate effective strength
            player_composition = player_compositions[player]
            effective_strength = self.calculate_army_effective_strength(player_composition, enemy_composition)
            player_effective_strengths[player] = effective_strength
            
            # Log composition and strength
            comp_str = ", ".join([f"{count} {unit_type}" for unit_type, count in sorted(player_composition.items())])
            self.add_message(f"  Player {player + 1}: {comp_str} (Effective Strength: {effective_strength:.1f})")
        
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
            self.add_message(f"  Player {winner + 1} WINS with superior effective strength!")
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
        
        attacker = [p for p in battle.armies.keys() if p != defender][0]
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
            # Calculate EFFECTIVE strengths (counters apply!)
            attacker_strength = self.calculate_army_effective_strength(attacker_comp, garrison_actual)
            garrison_strength = self.calculate_army_effective_strength(garrison_actual, attacker_comp)
            
            comp_str_attacker = ", ".join([f"{count} {unit_type}" for unit_type, count in sorted(attacker_comp.items())])
            comp_str_garrison = ", ".join([f"{count} {unit_type}" for unit_type, count in sorted(garrison_actual.items())])
            
            self.add_message(f"  Phase 1: {comp_str_attacker} (Effective: {attacker_strength:.1f}) vs {comp_str_garrison} (Effective: {garrison_strength:.1f})")
            
            # Determine Phase 1 winner based on effective strength
            attacker_count = sum(attacker_comp.values())
            garrison_count = sum(garrison_actual.values())
            
            if attacker_strength > garrison_strength:
                # Attackers win Phase 1
                # Casualties: Winner loses loser_count armies
                remaining_attackers = max(0, attacker_count - garrison_count)
                remaining_garrison = 0
                self.add_message(f"    Garrison eliminated. {remaining_attackers} attacker(s) remain.")
            elif garrison_strength > attacker_strength:
                # Garrison wins Phase 1
                # Casualties: Winner loses loser_count armies
                remaining_attackers = 0
                remaining_garrison = max(0, garrison_count - attacker_count)
                self.add_message(f"    Attackers repelled. {remaining_garrison} garrison survives.")
            else:
                # Perfect tie in Phase 1 - mutual elimination
                remaining_attackers = 0
                remaining_garrison = 0
                self.add_message(f"    Garrison and attackers eliminate each other.")
        else:
            # No garrison - attackers proceed directly to Keep
            remaining_attackers = sum(attacker_comp.values())
            remaining_garrison = 0
            self.add_message(f"  Phase 1: No garrison present. Attackers proceed to Keep.")
        
        # PHASE 2: Remaining Attackers vs Keep (TYPE-NEUTRAL, PURE NUMBERS)
        keep_defense = battle.keep_bonus
        
        if remaining_attackers > 0:
            self.add_message(f"  Phase 2: {remaining_attackers} remaining attacker(s) vs Keep (+{keep_defense} armies)")
            
            if remaining_attackers > keep_defense:
                # Attackers breach Keep
                surviving_armies = remaining_attackers - keep_defense
                winner = attacker
                self.add_message(f"    Keep destroyed! Attackers win with {surviving_armies} army(ies).")
            elif remaining_attackers == keep_defense:
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
    
    def _apply_battle_casualties_simple(self, battle, winner, player_armies, player_compositions, territory):
        """
        Apply casualties using simple system (no Keep bonus).
        
        Phase 6: Extracted from resolve_battle() for maintainability.
        """
        winner_count = battle.armies[winner]
        loser_count = sum(count for player, count in player_armies if player != winner)
        casualties_int = loser_count
        
        # Calculate survivors
        surviving_armies = max(1, winner_count - casualties_int)
        casualties = winner_count - surviving_armies
        
        # Apply casualties to winner's army using priority system
        if winner == battle.original_owner:
            # Winner is defender - apply casualties to territory units
            # Get enemy composition for priority calculation
            enemy_comp = {}
            for p in player_armies:
                if p[0] != winner:
                    comp = player_compositions.get(p[0], {})
                    for ut, uc in comp.items():
                        enemy_comp[ut] = enemy_comp.get(ut, 0) + uc
            
            # Apply casualties with priority
            casualties_by_type = self.apply_casualties_with_priority(territory, casualties, enemy_comp)
            
            # Log casualties
            if casualties_by_type:
                casualty_str = ", ".join([f"{count} {unit_type}" for unit_type, count in sorted(casualties_by_type.items())])
                self.add_message(f"  Defender casualties: {casualty_str}")
        
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
            self.add_message(f"  Player {player + 1} ({army_count} armies) rolls: {roll}")
        
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
            self.destroy_buildings(territory)
            
            self.territory_owners[territory] = -1  # Neutral
            self.armies[territory] = 0
            self.armies_unmoved[territory] = 0
            self.armies_moved[territory] = 0
            
            # Clear army_units
            if territory in self.army_units:
                self.army_units[territory] = []
            
            self.add_message(f"  PERFECT TIE! All armies destroyed. {territory} becomes neutral.")
            return -1, 0
        else:
            # Winner determined by dice
            surviving_armies = 1  # Winner keeps 1 army
            casualties = winner_count - 1
            
            if casualties > 0:
                self.add_message(f"  Player {winner + 1} WINS! Lost {casualties} battalions, {surviving_armies} remains")
            else:
                self.add_message(f"  Player {winner + 1} WINS! {surviving_armies} battalion remains")
            
            return winner, surviving_armies
    
    def _update_battle_results(self, battle, winner, surviving_armies, player_compositions, territory):
        """
        Update game state with battle results.
        
        Phase 6: Extracted from resolve_battle() for maintainability.
        """
        if winner == -1:
            # Perfect tie handled in dice method
            battle.resolved = True
            battle.winner = -1
            return
        
        # Destroy buildings if territory changes hands
        if battle.original_owner != winner:
            self.destroy_buildings(territory)
        
        # Set territory ownership
        self.territory_owners[territory] = winner
        self.armies[territory] = surviving_armies
        self.armies_unmoved[territory] = 0  # Just fought, can't move
        self.armies_moved[territory] = surviving_armies
        
        # Create unit with correct type from winner's composition
        winner_comp = player_compositions.get(winner, {})
        
        # Clear old units
        if territory in self.army_units:
            self.army_units[territory] = []
        else:
            self.army_units[territory] = []
        
        if winner_comp:
            # Use most common unit type from winner's composition
            most_common_type = max(winner_comp.items(), key=lambda x: x[1])[0]
            self.army_units[territory] = [{
                'id': 0,
                'status': 'moved',
                'order': None,
                'type': most_common_type
            }]
        else:
            # Fallback: create Swordsman if no composition
            self.army_units[territory] = [{
                'id': 0,
                'status': 'moved',
                'order': None,
                'type': 'Swordsman'
            }]
        
        battle.resolved = True
        battle.winner = winner
        battle.surviving_armies = surviving_armies
        
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
            - Two-phase combat: Garrison → Keep
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
                # Clear winner - apply simple casualties
                surviving_armies = self._apply_battle_casualties_simple(
                    battle, winner, player_armies, player_compositions, territory
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
        
        # Cleanup
        self.pending_battles.pop(battle_index)
        
        # Check if more battles remain
        if len(self.pending_battles) == 0:
            self.turn_phase = 'planning'
            self.add_message("=== All battles resolved! ===")
            self._advance_to_next_player()
        
        return True
    
    def _advance_to_next_player(self):
        """Internal method to advance to the next player (called after battle resolution)"""
        # Clear building limit tracking for new turn
        self.buildings_started_this_turn.clear()
        
        # Collect income for the player whose turn is ending
        if self.phase == 'playing':
            self.collect_income(self.current_player)
        
        # Merge moved and unmoved armies back into total armies
        for territory in map_data.get_all_territories():
            self.armies[territory] = self.armies_moved[territory] + self.armies_unmoved[territory]
            # Reset: all armies can move in new turn
            self.armies_unmoved[territory] = self.armies[territory]
            self.armies_moved[territory] = 0
            
            # Reset individual army unit statuses (Phase 3)
            if territory in self.army_units:
                for unit in self.army_units[territory]:
                    # Reset moved units to ready
                    if unit['status'] == 'moved':
                        unit['status'] = 'ready'
                    # Clear ordered status
                    if unit['status'] == 'ordered':
                        unit['status'] = 'ready'
                    # Clear order references
                    unit['order'] = None
        
        # Switch to next player
        self.current_player = (self.current_player + 1) % self.num_players
        self.selected_territory = None
        self.selected_army = None  # Clear army selection
        self.add_message(f"--- Player {self.current_player + 1}'s Turn ---")
        
        # Reset to planning phase for new turn
        self.turn_phase = 'planning'
        
        # Finish any buildings that complete at the START of this player's turn
        if self.phase == 'playing':
            self.finish_constructions()
            self.finish_training()  # Also finish unit training
    
    def add_message(self, message):
        """Add a message to the message log (keeps entire game history)"""
        self.messages.append(message)
        # No limit - keep all messages for full game history
        print(f"[GAME] {message}")  # Also print to console
    
    def add_chat_message(self, player_id, message):
        """Add a chat message with timestamp and player info"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.chat_messages.append((timestamp, player_id, message))
        print(f"[CHAT] [{timestamp}] Player {player_id + 1}: {message}")
    
    def calculate_player_income(self, player_index):
        """Calculate total income for a player from their territories"""
        total_income = 0
        for territory, owner in self.territory_owners.items():
            if owner == player_index:
                # Get base income for territory (with error handling)
                try:
                    base_income = map_data.get_territory_income(territory)
                except (KeyError, AttributeError) as e:
                    self.log_error(f"Failed to get income for territory '{territory}'", e)
                    base_income = 0  # Safe default
                
                # Add building bonuses
                building_bonus = 0
                multiplier = 1.0
                
                if territory in self.buildings:
                    for plot_index, building_type in self.buildings[territory].items():
                        if building_type is None:
                            continue
                        
                        # Safely access building info
                        try:
                            building_info = self.building_types[building_type]
                            effect = building_info['effect']
                            value = building_info['value']
                            
                            if effect == 'income':
                                building_bonus += value
                            elif effect == 'multiplier':
                                multiplier = value
                        except (KeyError, TypeError) as e:
                            self.log_error(f"Invalid building data for {building_type} in {territory}", e)
                            continue  # Skip this building
                
                # Apply formula: (base + bonuses) * multiplier
                territory_income = int((base_income + building_bonus) * multiplier)
                total_income += territory_income
        
        return total_income
    
    def collect_income(self, player_index):
        """Collect income for a player and add to their gold"""
        income = self.calculate_player_income(player_index)
        self.player_gold[player_index] += income
        
        # Count territories for message
        territory_count = sum(1 for owner in self.territory_owners.values() if owner == player_index)
        
        if income > 0:
            self.add_message(f"Player {player_index + 1} earned {income} gold from {territory_count} territories")
    
    def get_territory_color(self, territory):
        """Get the color to display for a territory based on ownership"""
        owner = self.territory_owners[territory]
        return self.get_player_color(owner)
    
    def claim_territory(self, territory, player_index):
        """Claim a territory for a player during setup phase"""
        if self.phase != 'setup':
            return False
        
        if self.territory_owners[territory] != -1:
            return False  # Already claimed
        
        if self.territories_chosen[player_index] >= self.max_starting_territories:
            return False  # Player has claimed max territories
        
        self.territory_owners[territory] = player_index
        self.armies[territory] = 1  # Start with 1 army
        self.armies_unmoved[territory] = 1  # Can move immediately
        self.territories_chosen[player_index] += 1
        
        # Check if setup is complete
        if all(count >= self.max_starting_territories for count in self.territories_chosen):
            self.phase = 'playing'
            self.current_player = 0
        
        return True
    
    def next_player(self):
        """Move to the next player's turn (or execute orders/battles first)"""
        # If in planning phase with orders, execute them first
        if self.turn_phase == 'planning' and len(self.movement_orders) > 0:
            self.execute_all_orders()
            # If battles were created, stop here and wait for resolution
            if self.turn_phase == 'battles':
                return
            # Otherwise, continue to advance player (no battles)
        
        # If in battles phase, can't advance until battles are resolved
        if self.turn_phase == 'battles' and len(self.pending_battles) > 0:
            self.add_message("Resolve all battles before ending turn!")
            return
        
        # If we reach here, ready to advance to next player
        self._advance_to_next_player()
    
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
    
    def can_move_army(self, from_territory, to_territory):
        """Check if an army can move from one territory to another"""
        if self.phase != 'playing':
            return False
        
        # In testing mode, allow moving any player's armies
        if not self.testing_mode:
            # Must own the source territory
            if self.territory_owners[from_territory] != self.current_player:
                return False
        
        # Must have at least 1 unmoved army
        if self.armies_unmoved[from_territory] < 1:
            return False
        
        # Territories must be adjacent
        if not map_data.are_adjacent(from_territory, to_territory):
            return False
        
        return True
    
    def move_army(self, from_territory, to_territory, army_size):
        """Move armies from one territory to another (if owned) or attack"""
        if not self.can_move_army(from_territory, to_territory):
            return False
        
        to_owner = self.territory_owners[to_territory]
        
        # Can only move unmoved armies
        army_size = min(army_size, self.armies_unmoved[from_territory])
        if army_size == 0:
            return False
        
        # Remove from unmoved armies at source
        self.armies_unmoved[from_territory] -= army_size
        
        # Moving to own territory
        if to_owner == self.current_player:
            # Add to moved armies at destination (they've moved, can't move again)
            self.armies_moved[to_territory] += army_size
            self.add_message(f"Player {self.current_player + 1} moved {army_size} armies to {to_territory}")
            return True
        
        # Attacking enemy or neutral territory
        else:
            attacking_force = army_size
            defending_armies = self.armies_unmoved[to_territory] + self.armies_moved[to_territory]
            
            # Check for Fortress (Keep) - it provides defense but fights separately
            has_keep = self.has_fortress(to_territory)
            fortress_bonus = 2 if has_keep else 0
            
            # Add attack message
            defender_name = f"Player {to_owner + 1}" if to_owner >= 0 else "Neutral"
            self.add_message(f"Player {self.current_player + 1} attacks {to_territory}!")
            
            # Show combat forces
            if has_keep:
                self.add_message(f"  Attacker: {attacking_force} vs Defender: {defending_armies} armies (+{fortress_bonus} Fortress)")
            else:
                self.add_message(f"  Attacker: {attacking_force} vs Defender: {defending_armies}")
            
            # STAGE 1: Army vs Army combat
            army_combat_result = attacking_force - defending_armies
            
            # STAGE 2: If attacker wins Stage 1, check if they can overcome the Keep
            if army_combat_result > 0 and has_keep:
                # Attacker has survivors after destroying all armies
                # Now they must overcome the Keep's defense
                remaining_attackers = army_combat_result
                
                if remaining_attackers > fortress_bonus:
                    # Attacker has enough to destroy the Keep
                    final_survivors = remaining_attackers - fortress_bonus
                    self.add_message(f"  Armies eliminated! {remaining_attackers} attackers storm the Fortress...")
                    self.add_message(f"  Fortress destroyed! {final_survivors} attackers remain!")
                    
                    # Territory captured, Keep destroyed
                    self.destroy_all_buildings(to_territory)
                    self.territory_owners[to_territory] = self.current_player
                    self.armies_moved[to_territory] = final_survivors
                    self.armies_unmoved[to_territory] = 0
                    self.add_message(f"  Victory! {to_territory} captured!")
                    self.check_victory()
                    return True
                else:
                    # Not enough attackers to overcome the Keep
                    self.add_message(f"  Armies eliminated! {remaining_attackers} attackers assault the Fortress...")
                    self.add_message(f"  Fortress holds! Attack repelled!")
                    
                    # All attackers dead, all defenders dead, but Keep survives and territory holds
                    self.armies_unmoved[to_territory] = 0
                    self.armies_moved[to_territory] = 0
                    return True
            
            # STAGE 1 Resolution (no Keep, or attacker didn't win Stage 1)
            elif army_combat_result > 0:
                # Attacker wins (no Keep to worry about)
                self.destroy_all_buildings(to_territory)
                self.territory_owners[to_territory] = self.current_player
                survivors = army_combat_result
                self.armies_moved[to_territory] = survivors
                self.armies_unmoved[to_territory] = 0
                self.add_message(f"  Victory! {to_territory} captured!")
                self.check_victory()
                return True
            else:
                # Defender wins or tie (attacker didn't even get through the armies)
                remaining = -army_combat_result  # negative means defender wins
                
                # Keep same proportions of moved/unmoved for surviving defenders
                if defending_armies > 0:
                    ratio_unmoved = self.armies_unmoved[to_territory] / defending_armies
                    self.armies_unmoved[to_territory] = int(remaining * ratio_unmoved)
                    self.armies_moved[to_territory] = remaining - self.armies_unmoved[to_territory]
                else:
                    self.armies_unmoved[to_territory] = 0
                    self.armies_moved[to_territory] = 0
                
                if army_combat_result == 0:
                    self.add_message(f"  Draw! Both armies destroyed!")
                    if has_keep:
                        self.add_message(f"  Fortress stands untouched!")
                else:
                    self.add_message(f"  Defeat! Attack repelled!")
                    if has_keep:
                        self.add_message(f"  Fortress protected the defenders!")
                
                return True
    
    def start_construction(self, territory, plot_index, building_type):
        """Start construction of a building"""
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
                for plot_idx, (bldg_type, _) in self.under_construction[territory].items():
                    if bldg_type == 'Keep':
                        self.add_message("Already building a Fortress in this territory!")
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
            cost = self.building_types[building_type]['cost']
            if self.player_gold[self.current_player] < cost:
                self.add_message("Not enough Resources!")
                return False
        except (KeyError, IndexError) as e:
            self.log_error(f"Failed to check building cost for {building_type}", e)
            return False
        
        # Deduct gold
        self.player_gold[self.current_player] -= cost
        
        # Determine construction time (Keep takes 2 turns, others take 1 turn)
        if building_type == 'Keep':
            turns_to_build = 2  # Completes at START of 2nd turn (4 total turns in 2P)
        else:
            turns_to_build = 1
        
        # Add to construction queue
        if territory not in self.under_construction:
            self.under_construction[territory] = {}
        self.under_construction[territory][plot_index] = (building_type, turns_to_build)
        
        # Mark this territory as having started construction this turn
        self.buildings_started_this_turn.add(territory)
        
        if turns_to_build > 1:
            self.add_message(f"Player {self.current_player + 1} started building {building_type} ({cost} gold, {turns_to_build} turns)")
        else:
            self.add_message(f"Player {self.current_player + 1} started building {building_type} ({cost} gold)")
        return True
    
    def finish_constructions(self):
        """Finish all buildings that completed this turn (only counts owner's turns)"""
        completed = []
        
        for territory in list(self.under_construction.keys()):
            # Only count turns for buildings owned by current player
            if self.territory_owners[territory] != self.current_player:
                continue
                
            for plot_index in list(self.under_construction[territory].keys()):
                building_type, turns_remaining = self.under_construction[territory][plot_index]
                
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
                    
                    completed.append((territory, building_type))
                else:
                    # Update turns remaining
                    self.under_construction[territory][plot_index] = (building_type, turns_remaining)
        
        # Add messages for completed buildings
        for territory, building_type in completed:
            owner = self.territory_owners[territory]
            self.add_message(f"Player {owner + 1}: {building_type} completed in {territory}")
    
    def cancel_construction(self, territory, plot_index):
        """Cancel construction and refund 100%"""
        if territory not in self.under_construction:
            return False
        
        if plot_index not in self.under_construction[territory]:
            return False
        
        building_type, _ = self.under_construction[territory][plot_index]
        cost = self.building_types[building_type]['cost']
        owner = self.territory_owners[territory]
        
        # Refund 100%
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
        cost = self.building_types[building_type]['cost']
        refund = cost // 2
        owner = self.territory_owners[territory]
        
        # Refund 50%
        self.player_gold[owner] += refund
        
        # Remove building (delete the entry, don't set to None)
        del self.buildings[territory][plot_index]
        
        # If this was a Barracks, clear its training queue (no refund)
        if building_type == 'Barracks':
            self.clear_training_queue(territory, plot_index)
        
        # Note: Demolishing does NOT consume your building slot
        # You can still build one building this turn if you haven't already
        
        self.add_message(f"{building_type} destroyed, {refund} gold refunded")
        return True
    
    def destroy_all_buildings(self, territory):
        """Destroy all buildings in a territory (when conquered)"""
        # Remove completed buildings
        if territory in self.buildings:
            del self.buildings[territory]
        
        # Cancel constructions (no refund for enemy)
        if territory in self.under_construction:
            del self.under_construction[territory]
        
        # Clear all training queues (no refund for enemy)
        self.clear_training_queue(territory)
    
    def has_barracks(self, territory):
        """Check if territory has a completed Barracks building and return plot indices"""
        barracks_plots = []
        if territory not in self.buildings:
            return barracks_plots
        
        for plot_index, building_type in self.buildings[territory].items():
            if building_type == 'Barracks':
                barracks_plots.append(plot_index)
        return barracks_plots
    
    def start_training(self, territory, barracks_plot_index, unit_type='Swordsman'):
        """Start training a unit at a specific Barracks"""
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
        current_armies = self.armies.get(territory, 0)
        if current_armies >= self.MAX_ARMIES_PER_TERRITORY:
            self.add_message(f"Army limit reached in {territory}! (Max {self.MAX_ARMIES_PER_TERRITORY} per territory)")
            return False
        
        # Initialize training queue for this Barracks if needed
        if territory not in self.training_queue:
            self.training_queue[territory] = {}
        if barracks_plot_index not in self.training_queue[territory]:
            self.training_queue[territory][barracks_plot_index] = []
        
        # Check queue limit (5 units per Barracks)
        if len(self.training_queue[territory][barracks_plot_index]) >= 5:
            self.add_message("Training queue full! (Max 5 per Barracks)")
            return False
        
        # Get unit cost based on type (with error handling)
        try:
            unit_cost = self.UNIT_TYPES[unit_type]['cost']
            if self.player_gold[self.current_player] < unit_cost:
                self.add_message(f"Not enough gold to train {unit_type}! (Need {unit_cost} gold)")
                return False
        except (KeyError, IndexError) as e:
            self.log_error(f"Failed to get unit cost for {unit_type}", e)
            return False
        
        # Deduct gold
        self.player_gold[self.current_player] -= unit_cost
        
        # Add to queue (unit_type, turns_remaining)
        self.training_queue[territory][barracks_plot_index].append((unit_type, 1))
        
        self.add_message(f"Player {self.current_player + 1} started training {unit_type} in {territory} ({unit_cost} gold, 1 turn)")
        return True
    
    def cancel_training(self, territory, barracks_plot_index, queue_index):
        """Cancel training in queue for full refund"""
        if territory not in self.training_queue:
            return False
        if barracks_plot_index not in self.training_queue[territory]:
            return False
        if queue_index >= len(self.training_queue[territory][barracks_plot_index]):
            return False
        
        # Get unit info
        unit_type, turns_remaining = self.training_queue[territory][barracks_plot_index][queue_index]
        
        # Get correct cost for this unit type
        unit_cost = self.UNIT_TYPES.get(unit_type, {}).get('cost', 25)
        
        # Refund gold
        owner = self.territory_owners[territory]
        self.player_gold[owner] += unit_cost
        
        # Remove from queue
        self.training_queue[territory][barracks_plot_index].pop(queue_index)
        
        # Clean up empty structures
        if not self.training_queue[territory][barracks_plot_index]:
            del self.training_queue[territory][barracks_plot_index]
        if not self.training_queue[territory]:
            del self.training_queue[territory]
        
        self.add_message(f"Training canceled, {unit_cost} gold refunded")
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
                if queue:
                    unit_type, turns_remaining = queue[0]
                    turns_remaining -= 1
                    
                    if turns_remaining <= 0:
                        # Check army limit before spawning
                        current_armies = self.armies.get(territory, 0)
                        if current_armies >= self.MAX_ARMIES_PER_TERRITORY:
                            # At army limit - pause training (don't spawn, don't remove from queue)
                            self.add_message(f"{territory}: Training paused - army limit reached ({self.MAX_ARMIES_PER_TERRITORY}/{self.MAX_ARMIES_PER_TERRITORY})")
                            # Keep unit in queue with 0 turns (will check again next turn)
                            queue[0] = (unit_type, 0)
                            continue  # Skip to next Barracks
                        
                        # Training complete! Spawn unit
                        # Add army as "moved" (can't move this turn)
                        self.armies_moved[territory] += 1
                        self.armies[territory] = self.armies_moved[territory] + self.armies_unmoved[territory]
                        
                        # Add unit to army_units with correct type
                        if territory not in self.army_units:
                            self.army_units[territory] = []
                        
                        # Find next available ID
                        existing_ids = [u['id'] for u in self.army_units[territory]]
                        next_id = 0
                        while next_id in existing_ids:
                            next_id += 1
                        
                        # Add the new unit with its specific type
                        self.army_units[territory].append({
                            'id': next_id,
                            'status': 'moved',  # Just trained, exhausted
                            'order': None,
                            'type': unit_type  # Use the actual trained type
                        })
                        
                        self.add_message(f"Player {owner + 1}: {unit_type} trained in {territory}")
                        
                        # Remove from queue
                        queue.pop(0)
                        
                        # Update remaining items in queue (decrement their timers too if needed)
                        # Actually, only first item trains, others wait
                    else:
                        # Update timer
                        queue[0] = (unit_type, turns_remaining)
                
                # Clean up empty queue
                if not queue:
                    barracks_to_remove.append(barracks_plot_index)
            
            for barracks_plot_index in barracks_to_remove:
                del barracks_dict[barracks_plot_index]
            
            if not barracks_dict:
                territories_to_remove.append(territory)
        
        for territory in territories_to_remove:
            del self.training_queue[territory]
    
    def check_victory(self):
        """Check if any player has won"""
        # Count territories per player
        territory_counts = [0] * self.num_players
        for owner in self.territory_owners.values():
            if owner >= 0:
                territory_counts[owner] += 1
        
        # DEBUG: Print territory counts
        print(f"\n[DEBUG check_victory] Territory counts: {territory_counts}")
        print(f"[DEBUG check_victory] Victory threshold: {self.victory_territory_threshold}")
        
        # CURRENT VICTORY CONDITION: Control X territories
        victory_threshold = self.victory_territory_threshold
        
        for i, count in enumerate(territory_counts):
            print(f"[DEBUG check_victory] Player {i}: {count} territories (need {victory_threshold})")
            if count >= victory_threshold:
                print(f"[DEBUG check_victory] VICTORY TRIGGERED for Player {i}!")
                self.winner = i
                self.phase = 'ended'
                self.add_message(f"")
                self.add_message(f"============================")
                self.add_message(f"   PLAYER {i + 1} WINS!")
                self.add_message(f"   ({count} territories)")
                self.add_message(f"============================")
                return i  # Player i has won
        
        print(f"[DEBUG check_victory] No victory yet")
        
        # ALTERNATE VICTORY CONDITIONS (for future implementation):
        # 
        # Option 1: Total Conquest (original)
        # if count == len(self.territory_owners):
        #     self.winner = i
        #     ...
        #
        # Option 2: Majority Control
        # if count > len(self.territory_owners) // 2:
        #     self.winner = i
        #     ...
        #
        # Option 3: Control specific territories (capitals/strongholds)
        # key_territories = ["Orlais", "Amennia", "Azincourne"]
        # if all(self.territory_owners[t] == i for t in key_territories):
        #     self.winner = i
        #     ...
        
        return -1  # No winner yet
