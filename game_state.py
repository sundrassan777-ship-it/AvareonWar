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
    7. Phase Management: Setup â†’ Planning â†’ Execution â†’ Battles

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
        - Victory condition met (45+ territories or total conquest)
        - Victory screen displayed

Economic System:
    - Base Income: Each territory generates 5-20 gold/turn
    - Buildings: Farms (+10), Mines (+15), Squares (Ã—1.5 multiplier)
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
    - Training Queue: Up to 4 units per Barracks

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

import time
import map_data
from config.constants import PLAYER_COLORS
from utils.logger import get_logger

logger = get_logger(__name__)

class MovementOrder:
    """Represents a planned army movement order"""
    def __init__(self, from_territory, to_territory, army_count, player, unit_ids=None):
        self.from_territory = from_territory
        self.to_territory = to_territory
        self.army_count = army_count
        self.player = player
        self.unit_ids = unit_ids or []  # List of specific unit IDs (Phase 3)
        self.order_id = id(self)  # Unique ID for this order

class ArmyAnimation:
    """Represents an animated army movement"""
    def __init__(self, from_territory, to_territory, army_count, player, unit_ids, composition, from_pos=None, to_pos=None, units=None):
        self.from_territory = from_territory
        self.to_territory = to_territory
        self.army_count = army_count
        self.player = player
        self.unit_ids = unit_ids or []
        self.composition = composition or {}  # {unit_type: count}
        self.units = units or []  # Actual unit dicts (preserves xp/level through movement)
        self.progress = 0.0  # 0.0 to 1.0
        self.duration = 0.5  # 0.5 seconds
        self.elapsed = 0.0
        self.completed = False
        # Optional: specific start/end positions (for multi-garrison flag positions)
        # If None, will use territory centers
        self.from_pos = from_pos  # (x, y) in world coordinates
        self.to_pos = to_pos      # (x, y) in world coordinates

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
        self.army_compositions = {}  # {player_index: {unit_type: count}}
        self.allied_defenders = []  # List of player indices who are allied defenders (not owner)
    
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

    # Veterancy/Experience system constants
    LEVEL_XP_PER_LEVEL = [30, 45, 50, 55, 60]      # XP needed at each level (per-level increments)
    LEVEL_XP_CUMULATIVE = [30, 75, 125, 180, 240]   # Cumulative thresholds for levels 1-5
    MAX_LEVEL = 5
    UNIT_LEVEL_STRENGTH_BONUS = 0.15    # +15% effective strength per unit level
    BUILDING_LEVEL_INCOME_BONUS = 0.10  # +10% income per building level
    BUILDING_XP_PER_TURN = 20           # XP awarded to Farms/Mines each turn
    BATTLE_XP_PER_KILL = 10             # Base XP per enemy unit killed (+1 per enemy level)
    HERO_KEEP_DESTROY_XP = 100          # Flat XP when destroying a Keep with a Hero

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
    
    def __init__(self, num_players=2, player_is_ai=None, player_ai_difficulty=None, player_teams=None, skip_setup_phase=False, network_mode=False, local_player_index=None, taxation_level=0, victory_condition='Domination (45+)', game_mode='sequential'):
        self.num_players = num_players
        self.current_player = 0  # Index of current player (0 to num_players-1)
        # L3: Use canonical PLAYER_COLORS from config/constants.py (single source of truth)
        self.player_colors = list(PLAYER_COLORS)

        # Taxation configuration (0=0%, 1=25%, 2=50%, 3=75%, 4=100%)
        # Applied at turn end BEFORE income collection
        self.taxation_level = taxation_level

        # Victory condition configuration ("Domination (45+)", "Capital Assault", "Total Conquest")
        self.victory_condition = victory_condition

        # Turn mode configuration ('sequential' or 'simultaneous')
        # Sequential: Players take turns one at a time (classic mode)
        # Simultaneous: All players plan at once, then orders execute together
        self.game_mode = game_mode

        # AI player configuration
        # player_is_ai[player_index] = True if AI, False if human
        self.player_is_ai = player_is_ai if player_is_ai is not None else [False] * num_players
        # AI difficulty levels per player (0=Easy, 1=Medium, 2=Hard)
        self.player_ai_difficulty = player_ai_difficulty if player_ai_difficulty is not None else [1] * num_players
        # AI decision timers (used by AI execution system)
        self.ai_decision_timer = {}

        # Player display names (will be set during territory selection for AI players)
        # Format: "Human" for human players, "Empire of [Territory]" for AI players
        self.player_names = [None] * num_players

        # Team configuration (for team-based gameplay)
        # player_teams[player_index] = team_index (0-3)
        # Players on the same team are allies (cannot attack each other)
        # Default: Each player on their own team (FFA mode)
        self.player_teams = player_teams if player_teams is not None else list(range(num_players))

        # Store skip_setup_phase flag for later use
        self.skip_setup_phase = skip_setup_phase

        # Multiplayer networking
        self.network_mode = network_mode
        self.local_player_index = local_player_index  # 0=host, 1=client

        # Reference to map_renderer for triggering visual effects
        self.map_renderer = None

        # Reference to main game instance (for accessing scaled_centers, etc.)
        self.game = None

        # Tutorial mission reference (set when launching campaign tutorial)
        # When active, gates player actions and overrides AI behavior
        self.tutorial_mission = None
        
        # Territory ownership: territory_name -> player_index (-1 = neutral)
        self.territory_owners = {territory: -1 for territory in map_data.get_all_territories()}

        # Track starting territories for Capital Assault victory condition
        # Format: {player_index: territory_name}
        self.player_starting_territories = {}
        
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

        # Multi-Garrison System (for Allied Reinforcement)
        # Tracks garrisons per player in each territory
        # Format: {territory: {player_index: {'unmoved': int, 'moved': int, 'units': [...]}}}
        # - unmoved: armies that can still move this turn
        # - moved: armies that already moved this turn
        # - units: list of unit dicts (same format as army_units)
        # Only the original owner (territory_owners[territory]) gets income and control
        # Allies can reinforce but don't get benefits
        # Total armies across all garrisons limited to MAX_ARMIES_PER_TERRITORY (15)
        self.territory_garrisons = {territory: {} for territory in map_data.get_all_territories()}

        # Garrison position assignments (for stable flag positions during animations)
        # Format: {territory: {player_index: position_index}}
        # Tracks which position index (0, 1, 2, etc.) each garrison occupies
        # This prevents existing garrisons from "jumping" when new garrisons arrive
        self.garrison_positions = {territory: {} for territory in map_data.get_all_territories()}

        # Resource system - gold per player
        self.player_gold = [0] * num_players  # Gold for each player
        self.starting_gold = 100  # Starting gold for each player
        for i in range(num_players):
            self.player_gold[i] = self.starting_gold

        # Post-game statistics tracking (cumulative counters per player for recap screen)
        self.player_stats = {}
        for i in range(num_players):
            self.player_stats[i] = {
                'units_trained': 0, 'units_killed': 0,
                'pikemen_trained': 0, 'archers_trained': 0,
                'swordsmen_trained': 0, 'cavalry_trained': 0,
                'heroes_trained': 0, 'heroes_killed': 0,
                'gold_acquired': 0, 'gold_spent': 0,
                'gold_lost_to_taxation': 0, 'max_income_per_turn': 0,
                'economy_buildings_built': 0, 'barracks_built': 0,
                'keeps_built': 0, 'buildings_destroyed': 0,
            }

        # Building system
        # buildings: {territory: {plot_index: building_type}} or {plot_index: None} for empty
        self.buildings = {}  # Completed buildings
        # under_construction: {territory: {plot_index: (building_type, turns_remaining)}}
        self.under_construction = {}  # Buildings being built
        
        # Track buildings started this turn (one per territory per turn limit)
        self.buildings_started_this_turn = set()  # Set of territory names

        # Castle upgrade system
        # castle_upgrades: {territory: {plot_index: True}} - Completed Castle upgrades
        self.castle_upgrades = {}
        # castle_upgrades_in_progress: {territory: {plot_index: turns_remaining}}
        self.castle_upgrades_in_progress = {}

        # Building experience/veterancy system
        # building_xp: {territory: {plot_index: {'xp': int, 'level': int}}}
        # Tracks XP and level for Farms and Mines (+20 XP/turn, +10% income/level)
        self.building_xp = {}

        # Training system (for Barracks)
        # training_queue: {territory: {barracks_plot_index: [(unit_type, turns_remaining), ...]}}
        self.training_queue = {}  # Unit training queues

        # Hero system
        # Active heroes: {player_index: {hero_type: hero_data}}
        self.heroes = {i: {} for i in range(num_players)}

        # Hero training queue: {territory: {keep_plot_index: (hero_type, turns_remaining)}}
        # Single tuple per Keep (not list) - only ONE hero trains per Keep
        self.hero_training_queue = {}

        # Global uniqueness tracker: {player_index: set(hero_type_names)}
        # Includes both active AND training heroes
        self.hero_ownership = {i: set() for i in range(num_players)}

        # Hero limit per player (can be modified by Technology research)
        # Default: 3 heroes max (active + training)
        self.player_hero_limit = [3] * num_players

        # Command limit per player (can be modified by Technology research)
        # Default: 75 armies max across entire map
        self.player_command_limit = [75] * num_players

        # Planning phase timer per player (in seconds, can be modified by Technology research)
        # Default: 60 seconds (1 minute) per turn
        self.player_planning_time_limit = [60.0] * num_players

        # Royal Decree cost reduction (percentage) for Heroes and Keeps
        self.player_royal_decree_discount = [0] * num_players

        # Improved Training cost reduction (percentage) for Swordsmen and Pikemen
        self.player_training_cost_discount = [0] * num_players

        # Animal Handling cost reduction (percentage) for Cavalry
        self.player_cavalry_cost_discount = [0] * num_players

        # Battlement Archery strength bonus (percentage) for Archers in territories with friendly Keep/Castle
        self.player_archer_keep_strength_bonus = [0] * num_players

        # Raze the Countryside gold bonus when destroying enemy Farms
        self.player_farm_destruction_gold_bonus = [0] * num_players

        # Cavalry Tactics strength bonus (percentage) for Cavalry units
        self.player_cavalry_strength_bonus = [0] * num_players

        # Divide and Conquer: Bonus strength when attacking Keeps (Phase 2 only)
        # Flag: True = bonus active, False = no bonus
        self.player_divide_conquer_bonus = [False] * num_players

        # Makeshift Barracks cost reduction (percentage) for Barracks
        self.player_barracks_cost_discount = [0] * num_players

        # Makeshift Barracks full refund flag (True = 100% refund, False = 50% refund)
        self.player_barracks_full_refund = [False] * num_players

        # Hero Keep defense bonus (additional defense for Keeps/Castles with heroes)
        # Default: 0 (no bonus), can be increased by Improved Last Resort technology
        self.player_hero_keep_defense_bonus = [0] * num_players

        # Current planning phase timer (timestamp when planning phase started)
        # None when not in planning phase
        self.planning_phase_start_time = None

        # Hero ability state tracking
        # Cooldowns: {player_index: {hero_type: {ability_name: turns_remaining}}}
        self.hero_ability_cooldowns = {i: {} for i in range(num_players)}

        # Silence status: {player_index: turns_remaining}
        # When > 0, player's heroes cannot use active abilities
        self.hero_silence_status = {i: 0 for i in range(num_players)}

        # Track when silence was activated for visual effects (timestamp in ms)
        self.silence_activation_time = None

        # Master Negotiator (Evain Nithieln): Active flag for 75% discount on Farms/Mines/Squares
        # True = active this turn, False = not active
        self.player_master_negotiator_active = [False] * num_players

        # Track when Master Negotiator was activated for visual effects (timestamp in ms)
        self.master_negotiator_activation_time = None
        self.master_negotiator_active_player = None

        # Embargo (Evain Nithieln): Tracks which players will have income blocked on their next turn
        # List of player indices that will have income blocked
        self.embargo_blocked_players = []

        # Building costs and definitions
        self.building_types = {
            'Farm': {'cost': 30, 'letter': 'F', 'effect': 'income', 'value': 10, 'time': 1},
            'Mine': {'cost': 40, 'letter': 'M', 'effect': 'income', 'value': 15, 'time': 1},
            'Barracks': {'cost': 50, 'letter': 'B', 'effect': 'recruitment', 'value': True, 'time': 1},
            'Keep': {'cost': 100, 'letter': 'K', 'effect': 'defense', 'value': 2, 'time': 2},
            'Square': {'cost': 60, 'letter': 'S', 'effect': 'multiplier', 'value': 1.5, 'time': 1}
        }

        # Hero type definitions
        self.HERO_TYPES = {
            'Halon Nextroy': {
                'cost': 400,
                'letter': 'H',
                'name': 'Halon Nextroy',
                'training_time': 4,  # Player turns
                'abilities': [
                    {
                        'name': 'Aggressive Diplomacy',
                        'type': 'active',
                        'cooldown': 5,
                        'description': 'Target a neutral or enemy territory with 1 or fewer armies and no Keep. Destroy all armies and buildings, claiming the territory. Seledra\'s Champion of the People can save Farms and Mines.',
                        'icon': 'assets/heroes/abilities/AggressiveDiplomacyIcon.png'
                    },
                    {
                        'name': 'Levy',
                        'type': 'active',
                        'cooldown': 3,
                        'description': 'Target one of your territories to immediately collect its full income (base income + buildings + multipliers).',
                        'icon': 'assets/heroes/abilities/LevyIcon.png'
                    },
                    {
                        'name': 'Extensive Connections',
                        'type': 'passive',
                        'description': 'Gain 4 Gold per territory owned at the end of your turn.',
                        'icon': 'assets/heroes/abilities/ExtensiveConnectionsIcon.png'
                    }
                ],
                'description': ['Lord of Rossenburg'],
                'icon': 'assets/heroes/nextroy.png'
            },
            'Aidam Narn': {
                'cost': 600,
                'letter': 'A',
                'name': 'Aidam Narn',
                'training_time': 5,
                'abilities': [
                    {
                        'name': 'Royal Charisma',
                        'type': 'active',
                        'cooldown': 7,
                        'description': 'Steal up to 5 units from target enemy territory and move them to Narn\'s Keep (respects 15 unit limit). Cannot be used if Narn\'s Keep has 15 units.',
                        'icon': 'assets/heroes/abilities/RoyalCharismaIcon.png'
                    },
                    {
                        'name': 'Regicide',
                        'type': 'active',
                        'cooldown': 6,
                        'description': 'Target an enemy Keep. If a hero resides there, instantly kill that hero. If no hero is present, the ability is wasted.',
                        'icon': 'assets/heroes/abilities/RegicideIcon.png'
                    },
                    {
                        'name': 'Legacy of the Empire',
                        'type': 'passive',
                        'description': 'All your territories generate 50% more base income (does not affect Farms, Mines, or Squares).',
                        'icon': 'assets/heroes/abilities/LegacyOfTheEmpireIcon.png'
                    }
                ],
                'description': ['King of Azincourne'],
                'icon': 'assets/heroes/narn.png'
            },
            'Erec Silvyr': {
                'cost': 250,
                'letter': 'E',
                'name': 'Erec Silvyr',
                'training_time': 2,
                'abilities': [
                    {
                        'name': 'Extort Populace',
                        'type': 'active',
                        'cooldown': 3,
                        'description': 'Gain 50 Gold for each of your Keeps or Castles.',
                        'icon': 'assets/heroes/abilities/ExtortPopulaceIcon.png'
                    },
                    {
                        'name': 'Confiscate',
                        'type': 'passive',
                        'description': 'When you demolish a Farm or Mine, gain 175% of the cost back instead of 50%.',
                        'icon': 'assets/heroes/abilities/Confiscate.png'
                    },
                    {
                        'name': 'Ruthless Ingenuity',
                        'type': 'passive',
                        'description': 'Technology research takes 1 less turn but costs 33% more Gold.',
                        'icon': 'assets/heroes/abilities/RuthlessIngenuity.png'
                    }
                ],
                'description': ['Lord of Generax'],
                'icon': 'assets/heroes/silvyr.png'
            },
            'Darius Brennhen': {
                'cost': 150,
                'letter': 'D',
                'name': 'Darius Brennhen',
                'training_time': 2,
                'abilities': [
                    {
                        'name': 'Reinforce',
                        'type': 'active',
                        'cooldown': 4,
                        'description': 'Summon 2 Swordsmen battalions in the territory of Brennhen\'s Keep (must have 13 or fewer units).',
                        'icon': 'assets/heroes/abilities/ReinforcementIcon.png'
                    },
                    {
                        'name': 'Safe Haven',
                        'type': 'passive',
                        'description': 'When losing a battle in a territory adjacent to Brennhen\'s Keep, one random unit retreats to the Keep\'s territory instead of being destroyed.',
                        'icon': 'assets/heroes/abilities/SafeHavenIcon.png'
                    },
                    {
                        'name': 'Scavenge the Fallen',
                        'type': 'passive',
                        'description': 'Gain 30 Gold whenever you lose a battle (does not trigger when an empty territory is captured).',
                        'icon': 'assets/heroes/abilities/ScavengeTheFallenIcon.png'
                    }
                ],
                'description': ['Lord of Noxefort'],
                'icon': 'assets/heroes/brennhen.png'
            },
            'Neil Hévilneu': {
                'cost': 500,
                'letter': 'N',
                'name': 'Neil Hévilneu',
                'training_time': 5,
                'abilities': [
                    {
                        'name': 'Decisive Strike',
                        'type': 'active',
                        'cooldown': 6,
                        'description': 'Target an enemy territory with at least 2 units. Half of the armies (rounded down) are randomly removed.',
                        'icon': 'assets/heroes/abilities/DecisiveStrikeIcon.png'
                    },
                    {
                        'name': 'Valorous Charge',
                        'type': 'active',
                        'cooldown': 4,
                        'description': 'Move up to 15 units from Hévilneu\'s Keep territory to target allied territory (respects 15 unit limit). Units are marked as Moved on arrival.',
                        'icon': 'assets/heroes/abilities/ValorousChargeIcon.png'
                    },
                    {
                        'name': 'Vanquish the Enemy',
                        'type': 'passive',
                        'description': 'All your Swordsmen, Pikemen, Archers, and Cavalry gain +20% strength.',
                        'icon': 'assets/heroes/abilities/VanquishTheEnemyIcon.png'
                    }
                ],
                'description': ['Supreme Commander of', 'Northern Powers'],
                'icon': 'assets/heroes/hevilneu.png'
            },
            # Serthus Diarcess - Campaign-only hero (not trainable in standard games)
            # Copy of Neil Hévilneu with different icon/name for Campaign Mission 3
            'Serthus Diarcess': {
                'cost': 500,
                'letter': 'Z',  # Z for Zjoals
                'name': 'Serthus Diarcess',
                'training_time': 5,
                'trainable': False,  # Campaign-only hero, not available in training menu
                'abilities': [
                    {
                        'name': 'Decisive Strike',
                        'type': 'active',
                        'cooldown': 6,
                        'description': 'Target an enemy territory with at least 2 units. Half of the armies (rounded down) are randomly removed.',
                        'icon': 'assets/heroes/abilities/DecisiveStrikeIcon.png'
                    },
                    {
                        'name': 'Valorous Charge',
                        'type': 'active',
                        'cooldown': 4,
                        'description': 'Move up to 15 units from Diarcess\'s Keep territory to target allied territory (respects 15 unit limit). Units are marked as Moved on arrival.',
                        'icon': 'assets/heroes/abilities/ValorousChargeIcon.png'
                    },
                    {
                        'name': 'Vanquish the Enemy',
                        'type': 'passive',
                        'description': 'All your Swordsmen, Pikemen, Archers, and Cavalry gain +20% strength.',
                        'icon': 'assets/heroes/abilities/VanquishTheEnemyIcon.png'
                    }
                ],
                'description': ['The Emperor of Zjoals'],
                'icon': 'assets/heroes/serthus.png'
            },
            'Seledra Rennervail': {
                'cost': 350,
                'letter': 'S',
                'name': 'Seledra Rennervail',
                'training_time': 4,
                'abilities': [
                    {
                        'name': 'Vow of Silence',
                        'type': 'active',
                        'cooldown': 5,  # Turns
                        'description': 'Prevents all enemy heroes from using active abilities until the end of your next turn.',
                        'icon': 'assets/heroes/abilities/VowOfSilenceIcon.png'
                    },
                    {
                        'name': 'Defiance',
                        'type': 'passive',
                        'description': 'Protects the Keep\'s territory and adjacent friendly territories from enemy hero abilities.',
                        'icon': 'assets/heroes/abilities/DefianceIcon.png'
                    },
                    {
                        'name': 'Champion of the People',
                        'type': 'passive',
                        'description': 'When conquering territories, Farms and Mines are preserved and change ownership instead of being destroyed.',
                        'icon': 'assets/heroes/abilities/ChampionOfThePeople.png'
                    }
                ],
                'description': ['Princess of Arcburg'],
                'icon': 'assets/heroes/rennervail.png'
            },
            'Evain Nithieln': {
                'cost': 550,
                'letter': 'V',
                'name': 'Evain Nithieln',
                'training_time': 6,
                'abilities': [
                    {
                        'name': 'Embargo',
                        'type': 'active',
                        'cooldown': 6,
                        'description': 'At the start of your enemies\' next turn, they receive no income from territories, Farms, Mines, or Squares.',
                        'icon': 'assets/heroes/abilities/EmbargoIcon.png'
                    },
                    {
                        'name': 'Master Negotiator',
                        'type': 'active',
                        'cooldown': 5,
                        'description': 'For this turn, all Farms, Mines, and Squares cost 75% less gold.',
                        'icon': 'assets/heroes/abilities/MasterNegotiatorIcon.png'
                    },
                    {
                        'name': 'Farmer Subsidies',
                        'type': 'passive',
                        'description': 'All your Farms generate 50% more income.',
                        'icon': 'assets/heroes/abilities/FarmerSubsidiesIcon.png'
                    }
                ],
                'description': ['High Commander of', 'Affrancian Union'],
                'icon': 'assets/heroes/asten.png'
            },
            'Vearen Asford': {
                'cost': 300,
                'letter': 'F',
                'name': 'Vearen Asford',
                'training_time': 2,
                'abilities': [
                    {
                        'name': 'Relentless Charge',
                        'type': 'active',
                        'cooldown': 6,
                        'description': 'Summon 4 Cavalry battalions in target friendly territory (must have 11 or fewer units).',
                        'icon': 'assets/heroes/abilities/RelentlessChargeIcon.png'
                    },
                    {
                        'name': 'Haste',
                        'type': 'passive',
                        'description': 'Units trained in territories adjacent to Asford\'s Keep or in the Keep\'s territory are immediately ready to move.',
                        'icon': 'assets/heroes/abilities/HasteIcon.png'
                    },
                    {
                        'name': 'Pillage',
                        'type': 'passive',
                        'description': 'Gain 200 Gold whenever you destroy an enemy Keep.',
                        'icon': 'assets/heroes/abilities/PillageIcon.png'
                    }
                ],
                'description': ['Grand General of', 'Naragonthid'],
                'icon': 'assets/heroes/asford.png'
            },
            # Regnus Aevencourne - Campaign-only hero (not trainable in standard games)
            # Clone of Darius Brennhen with different icon/name for Campaign Mission 4
            'Regnus Aevencourne': {
                'cost': 150,
                'letter': 'R',
                'name': 'Regnus Aevencourne',
                'training_time': 2,
                'trainable': False,  # Campaign-only hero, not available in training menu
                'abilities': [
                    {
                        'name': 'Reinforce',
                        'type': 'active',
                        'cooldown': 4,
                        'description': 'Summon 2 Swordsmen battalions in the territory of Aevencourne\'s Keep (must have 13 or fewer units).',
                        'icon': 'assets/heroes/abilities/ReinforcementIcon.png'
                    },
                    {
                        'name': 'Safe Haven',
                        'type': 'passive',
                        'description': 'When losing a battle in a territory adjacent to Aevencourne\'s Keep, one random unit retreats to the Keep\'s territory instead of being destroyed.',
                        'icon': 'assets/heroes/abilities/SafeHavenIcon.png'
                    },
                    {
                        'name': 'Scavenge the Fallen',
                        'type': 'passive',
                        'description': 'Gain 30 Gold whenever you lose a battle (does not trigger when an empty territory is captured).',
                        'icon': 'assets/heroes/abilities/ScavengeTheFallenIcon.png'
                    }
                ],
                'description': ['The Emperor of Azincourne'],
                'icon': 'assets/heroes/regnus.png'
            }
        }

        # Game phase: 'setup', 'playing', 'ended'
        if skip_setup_phase:
            self.phase = 'playing'
            self.turn_phase = 'planning'
        else:
            self.phase = 'setup'

        # For setup phase: track how many territories each player has chosen
        self.territories_chosen = [0] * num_players
        self.max_starting_territories = 1  # Each player chooses 1 starting territory
        
        # Selected territory (for UI interaction)
        self.selected_territory = None
        
        # Message log for combat and actions
        self.messages = []
        # No message limit - keep entire game history for scrolling
        
        # Winner tracking
        self.winner = -1  # -1 = no winner, 0-3 = player index

        # Victory condition settings
        # NOTE: victory_condition is set from parameter at line 217, not here
        # Options: 'Domination (45+)', 'Capital Assault', 'Total Conquest'
        self.victory_territory_threshold = 45  # For 'Domination (45+)' mode
        
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
        self.ready_to_advance_turn = False  # Flag to advance turn after battle popup closes

        # Army movement animations
        self.active_animations = []  # List of ArmyAnimation objects
        self.pending_arrivals = []   # Armies waiting to arrive after animations complete
        self.cancelling_arrows = []  # Visual-only: cancelled arrow animations [{from_territory, to_territory, army_count, start_time}]
        
        # UI preferences
        self.sidebar_expanded = True # Collapsible sidebar state (True = expanded, False = collapsed)

        # Turn announcement effect system
        self.turn_announcement_active = False  # Blocks input during turn announcement
        self.deferred_turn_start_actions = False  # Flag to execute turn start effects after announcement

        # Phase B: Exclusive tab system state
        self.active_sidebar_tab = 'action_queue'  # Default active tab
        self.sidebar_tabs = ['technology', 'heroes', 'action_queue', 'action_log', 'quests', 'chat']  # Available tabs (Chat added)
        
        # Chat system
        self.chat_messages = []  # List of (timestamp, player_id, message) tuples

        # Technology tree system
        # 3 columns x 7 rows = 21 technologies
        self.technologies = []
        for col in range(3):
            for row in range(7):
                tech_id = f"tech_{col}_{row}"

                # Define specific technologies
                if col == 0 and row == 0:  # Column 1, Row 1 - Efficient Farming I
                    tech_data = {
                        'id': tech_id,
                        'name': 'Efficient Farming I',
                        'column': col,
                        'row': row,
                        'description': 'All your Farms generate 20% more income.',
                        'cost': 100,
                        'turns': 2,
                        'icon': 'assets/upgrades/EfficientFarming1Icon.png',
                        'effect_type': 'farm_income_bonus',
                        'effect_value': 20
                    }
                elif col == 0 and row == 1:  # Column 1, Row 2 - Efficient Mining I
                    tech_data = {
                        'id': tech_id,
                        'name': 'Efficient Mining I',
                        'column': col,
                        'row': row,
                        'description': 'All your Mines generate 20% more income.',
                        'cost': 150,
                        'turns': 2,
                        'icon': 'assets/upgrades/EfficientMining1Icon.png',
                        'effect_type': 'mine_income_bonus',
                        'effect_value': 20
                    }
                elif col == 0 and row == 2:  # Column 1, Row 3 - Leave Nothing Behind
                    tech_data = {
                        'id': tech_id,
                        'name': 'Leave Nothing Behind',
                        'column': col,
                        'row': row,
                        'description': 'Recover 50% of the cost when your Farms and Mines are destroyed.',
                        'cost': 150,
                        'turns': 3,
                        'icon': 'assets/upgrades/LeaveNothingBehindIcon.png',
                        'effect_type': 'building_destruction_recovery',
                        'effect_value': 50
                    }
                elif col == 0 and row == 3:  # Column 1, Row 4 - Supply and Demand
                    tech_data = {
                        'id': tech_id,
                        'name': 'Supply and Demand',
                        'column': col,
                        'row': row,
                        'description': 'Squares multiply territory income by 2.5× instead of 1.5×.',
                        'cost': 250,
                        'turns': 3,
                        'icon': 'assets/upgrades/SupplyAndDemandIcon.png',
                        'effect_type': 'square_multiplier_bonus',
                        'effect_value': 2.5,
                        'requires_castle': True
                    }
                elif col == 0 and row == 4:  # Column 1, Row 5 - Efficient Farming II
                    tech_data = {
                        'id': tech_id,
                        'name': 'Efficient Farming II',
                        'column': col,
                        'row': row,
                        'description': 'All your Farms generate an additional 20% more income.',
                        'cost': 300,
                        'turns': 2,
                        'icon': 'assets/upgrades/EfficientFarming2Icon.png',
                        'effect_type': 'farm_income_bonus_2',
                        'effect_value': 20,
                        'requires_castle': True
                    }
                elif col == 0 and row == 5:  # Column 1, Row 6 - Efficient Mining II
                    tech_data = {
                        'id': tech_id,
                        'name': 'Efficient Mining II',
                        'column': col,
                        'row': row,
                        'description': 'All your Mines generate an additional 20% more income.',
                        'cost': 350,
                        'turns': 3,
                        'icon': 'assets/upgrades/EfficientMining2Icon.png',
                        'effect_type': 'mine_income_bonus_2',
                        'effect_value': 20,
                        'requires_castle': True
                    }
                elif col == 0 and row == 6:  # Column 1, Row 7 - Laws of Trade
                    tech_data = {
                        'id': tech_id,
                        'name': 'Laws of Trade',
                        'column': col,
                        'row': row,
                        'description': 'Farms and Mines generate +15% income if in or adjacent to a territory with a Keep.',
                        'cost': 400,
                        'turns': 3,
                        'icon': 'assets/upgrades/LawsOfTradeIcon.png',
                        'effect_type': 'keep_proximity_bonus',
                        'effect_value': 15,
                        'requires_castle': True
                    }
                elif col == 1 and row == 0:  # Column 2, Row 1 - Improved Training
                    tech_data = {
                        'id': tech_id,
                        'name': 'Improved Training',
                        'column': col,
                        'row': row,
                        'description': 'Reduces cost of Swordsmen and Pikemen by 20%.',
                        'cost': 100,
                        'turns': 2,
                        'icon': 'assets/upgrades/ImprovedTrainingIcon.png',
                        'effect_type': 'unit_cost_reduction',
                        'effect_value': 20
                    }
                elif col == 1 and row == 1:  # Column 2, Row 2 - Makeshift Barracks
                    tech_data = {
                        'id': tech_id,
                        'name': 'Makeshift Barracks',
                        'column': col,
                        'row': row,
                        'description': 'Reduces Barracks cost by 25%. \nDemolishing a Barracks now returns 100% of gold spent.',
                        'cost': 200,
                        'turns': 2,
                        'icon': 'assets/upgrades/MakeshiftBarracks.png',
                        'effect_type': 'barracks_upgrade',
                        'effect_value': 25
                    }
                elif col == 1 and row == 2:  # Column 2, Row 3 - Animal Handling
                    tech_data = {
                        'id': tech_id,
                        'name': 'Animal Handling',
                        'column': col,
                        'row': row,
                        'description': 'Reduces cost of Cavalry by 25%.',
                        'cost': 200,
                        'turns': 3,
                        'icon': 'assets/upgrades/AnimalHandlingIcon.png',
                        'effect_type': 'cavalry_cost_reduction',
                        'effect_value': 25
                    }
                elif col == 1 and row == 3:  # Column 2, Row 4 - Battlement Archery
                    tech_data = {
                        'id': tech_id,
                        'name': 'Battlement Archery',
                        'column': col,
                        'row': row,
                        'description': 'Archers gain +50% strength in territories \nwith friendly Keep or Castle.',
                        'cost': 250,
                        'turns': 2,
                        'icon': 'assets/upgrades/BattlementArcheryIcon.png',
                        'effect_type': 'archer_keep_strength',
                        'effect_value': 50,
                        'requires_castle': True
                    }
                elif col == 1 and row == 4:  # Column 2, Row 5 - Raze the Countryside
                    tech_data = {
                        'id': tech_id,
                        'name': 'Raze the Countryside',
                        'column': col,
                        'row': row,
                        'description': 'Gain 30 Gold whenever you destroy an enemy Farm.',
                        'cost': 200,
                        'turns': 3,
                        'icon': 'assets/upgrades/RazeTheCountrysideIcon.png',
                        'effect_type': 'farm_destruction_bonus',
                        'effect_value': 30,
                        'requires_castle': True
                    }
                elif col == 1 and row == 5:  # Column 2, Row 6 - Cavalry Tactics
                    tech_data = {
                        'id': tech_id,
                        'name': 'Cavalry Tactics',
                        'column': col,
                        'row': row,
                        'description': 'Cavalry units gain +33% strength in battles.',
                        'cost': 250,
                        'turns': 2,
                        'icon': 'assets/upgrades/CavalryTacticsIcon.png',
                        'effect_type': 'cavalry_strength_bonus',
                        'effect_value': 33,
                        'requires_castle': True
                    }
                elif col == 1 and row == 6:  # Column 2, Row 7 - Divide and Conquer
                    tech_data = {
                        'id': tech_id,
                        'name': 'Divide and Conquer',
                        'column': col,
                        'row': row,
                        'description': 'Pikemen and Swordsmen gain +20% strength in battles. \nArchers gain +50% strength when sieging Keeps.',
                        'cost': 400,
                        'turns': 3,
                        'icon': 'assets/upgrades/DivideAndConquerIcon.png',
                        'effect_type': 'keep_siege_bonus',
                        'effect_value': 1,  # Flag: 1 = enabled
                        'requires_castle': True
                    }
                elif col == 2 and row == 0:  # Column 3, Row 1 - Master Planner I
                    tech_data = {
                        'id': tech_id,
                        'name': 'Master Planner I',
                        'column': col,
                        'row': row,
                        'description': 'Increases planning time limit by 30 seconds.',
                        'cost': 100,
                        'turns': 2,
                        'icon': 'assets/upgrades/MasterPlanner1Icon.png',
                        'effect_type': 'time_limit',
                        'effect_value': 30
                    }
                elif col == 2 and row == 1:  # Column 3, Row 2 - Improved Command I
                    tech_data = {
                        'id': tech_id,
                        'name': 'Improved Command I',
                        'column': col,
                        'row': row,
                        'description': 'Increases command limit by 35.',
                        'cost': 150,
                        'turns': 2,
                        'icon': 'assets/upgrades/ImprovedCommand1Icon.png',
                        'effect_type': 'command_limit',
                        'effect_value': 35
                    }
                elif col == 2 and row == 2:  # Column 3, Row 3 - Royal Decree
                    tech_data = {
                        'id': tech_id,
                        'name': 'Royal Decree',
                        'column': col,
                        'row': row,
                        'description': 'Reduces cost of Heroes and Keeps by 15%.',
                        'cost': 175,
                        'turns': 3,
                        'icon': 'assets/upgrades/RoyalDecreeIcon.png',
                        'effect_type': 'cost_reduction',
                        'effect_value': 15
                    }
                elif col == 2 and row == 3:  # Column 3, Row 4 - Master Planner II
                    tech_data = {
                        'id': tech_id,
                        'name': 'Master Planner II',
                        'column': col,
                        'row': row,
                        'description': 'Increases planning time limit by 30 seconds.',
                        'cost': 200,
                        'turns': 2,
                        'icon': 'assets/upgrades/MasterPlanner2Icon.png',
                        'effect_type': 'time_limit',
                        'effect_value': 30,
                        'requires_castle': True  # Special requirement
                    }
                elif col == 2 and row == 4:  # Column 3, Row 5 - Heroic Fortitude
                    tech_data = {
                        'id': tech_id,
                        'name': 'Heroic Fortitude',
                        'column': col,
                        'row': row,
                        'description': 'Increases hero limit to 4.',
                        'cost': 250,
                        'turns': 3,
                        'icon': 'assets/upgrades/HeroicFortitudeIcon.png',
                        'effect_type': 'hero_limit',
                        'effect_value': 4,
                        'requires_castle': True  # Special requirement
                    }
                elif col == 2 and row == 5:  # Column 3, Row 6 - Improved Command II
                    tech_data = {
                        'id': tech_id,
                        'name': 'Improved Command II',
                        'column': col,
                        'row': row,
                        'description': 'Increases command limit by 35.',
                        'cost': 300,
                        'turns': 2,
                        'icon': 'assets/upgrades/ImprovedCommand2Icon.png',
                        'effect_type': 'command_limit',
                        'effect_value': 35,
                        'requires_castle': True  # Special requirement
                    }
                elif col == 2 and row == 6:  # Column 3, Row 7 - Last Resort
                    tech_data = {
                        'id': tech_id,
                        'name': 'Last Resort',
                        'column': col,
                        'row': row,
                        'description': 'Keeps and Castles with Heroes gain +100% defense bonus.',
                        'cost': 350,
                        'turns': 3,
                        'icon': 'assets/upgrades/LastResortIcon.png',
                        'effect_type': 'hero_keep_defense',
                        'effect_value': 2,
                        'requires_castle': True  # Special requirement
                    }
                else:
                    # Placeholder for other technologies
                    tech_data = {
                        'id': tech_id,
                        'name': f"Tech {col+1}-{row+1}",
                        'column': col,
                        'row': row,
                        'description': f"Placeholder technology in column {col+1}, row {row+1}",
                        'cost': 0,
                        'turns': 0,
                        'icon': None,
                        'effect_type': None,
                        'effect_value': None
                    }

                self.technologies.append(tech_data)

        # Per-player technology research state
        # player_tech_researched[player_id] = set of tech_ids that are researched
        # player_tech_available[player_id] = set of tech_ids that are available to research
        self.player_tech_researched = {}
        self.player_tech_available = {}
        for player_id in range(num_players):
            self.player_tech_researched[player_id] = set()
            # Row 0 technologies start available
            self.player_tech_available[player_id] = {f"tech_{col}_0" for col in range(3)}

        # Research tracking per player
        # research_in_progress: {player_id: {'tech_id': tech_id, 'turns_remaining': turns}}
        self.research_in_progress = {}

        # Testing mode - allows controlling all players for testing
        self.testing_mode = False  # Disabled for normal gameplay
        
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

        logger.error(error_msg)

        # Store in error list
        self.errors.append(error_msg)
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)  # Remove oldest error

    def are_allies(self, player1_index, player2_index):
        """
        Check if two players are on the same team (allies).

        Players on the same team cannot attack each other, but CAN
        reinforce each other's territories with allied garrisons.

        Args:
            player1_index: Index of first player (0-3)
            player2_index: Index of second player (0-3)

        Returns:
            bool: True if both players are on the same team, False otherwise

        Notes:
            - Returns False if either player index is invalid
            - Returns False if player_teams is not configured (defaults to FFA)
            - Returns True only if both players have the same team number
            - Allies can reinforce territories without changing ownership
        """
        # Validate player indices
        if player1_index < 0 or player1_index >= self.num_players:
            return False
        if player2_index < 0 or player2_index >= self.num_players:
            return False

        # Same player is not considered an ally (but also shouldn't attack themselves)
        if player1_index == player2_index:
            return False

        # Check if team data exists
        if not hasattr(self, 'player_teams') or self.player_teams is None:
            return False  # No teams configured, everyone is FFA

        # Check if both players are on the same team
        return self.player_teams[player1_index] == self.player_teams[player2_index]

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
        import math

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

    def get_player_name(self, player_index, include_title=True):
        """
        Get the display name for a specific player.
        Returns the custom name if set, otherwise generates a default name.
        For human players with a selected title, appends "the Title".

        Args:
            player_index: Index of the player (0-based)
            include_title: If True (default), append selected title for human players

        Returns:
            str: Display name for the player
        """
        if player_index == -1:
            return "Neutral"

        # Return custom name if set (e.g. multiplayer names)
        if self.player_names[player_index] is not None:
            return self.player_names[player_index]

        # Generate default name based on player type
        if self.player_is_ai[player_index]:
            difficulty_names = ['Easy', 'Medium', 'Hard']
            difficulty = self.player_ai_difficulty[player_index]
            difficulty_name = difficulty_names[difficulty] if 0 <= difficulty < len(difficulty_names) else 'Medium'
            return f"AI ({difficulty_name})"
        else:
            # For human players, use profile name + optional title from settings
            from settings_manager import settings
            base_name = settings.get_player_name()
            if include_title:
                title = settings.get_selected_title()
                if title:
                    return f"{base_name} the {title}"
            return base_name

    def _track_stat(self, player_index, stat_name, amount=1):
        """Increment a cumulative player stat for post-game recap screen."""
        if player_index is None or player_index < 0 or player_index >= self.num_players:
            return
        if stat_name in self.player_stats.get(player_index, {}):
            self.player_stats[player_index][stat_name] += amount

    def get_end_game_stats(self):
        """Get all player stats for post-game recap screen, including territories owned."""
        stats = {}
        for i in range(self.num_players):
            player_data = dict(self.player_stats.get(i, {}))
            # Calculate territories owned at game end
            player_data['territories_owned'] = sum(
                1 for owner in self.territory_owners.values() if owner == i
            )
            stats[i] = player_data
        return stats

    def is_ai_player(self, player_index=None):
        """
        Check if a player is AI-controlled.

        Args:
            player_index: Index of player to check. If None, checks current player.

        Returns:
            bool: True if player is AI, False if human
        """
        if player_index is None:
            player_index = self.current_player
        return self.player_is_ai[player_index]

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
        if item_type in ['Farm', 'Mine', 'Barracks', 'Keep', 'Square']:
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

    # Territory Bonus System - each territory provides global bonuses to its owner
    BONUS_TYPES = {
        'income_bonus': {'display': 'Income', 'value': 3, 'format': '+{}%'},
        'tech_cost': {'display': 'Technology Research Cost', 'value': -5, 'format': '{}%'},
        'unit_cost': {'display': 'Unit Training Cost', 'value': -5, 'format': '{}%'},
        'hero_cost': {'display': 'Hero Training Cost', 'value': -3, 'format': '{}%'},
        'pikeman_str': {'display': 'Pikeman Strength', 'value': 10, 'format': '+{}%'},
        'archer_str': {'display': 'Archer Strength', 'value': 10, 'format': '+{}%'},
        'swordsman_str': {'display': 'Swordsman Strength', 'value': 10, 'format': '+{}%'},
        'cavalry_str': {'display': 'Cavalry Strength', 'value': 10, 'format': '+{}%'},
        'building_cost': {'display': 'Building Cost', 'value': -15, 'format': '{}%'}
    }

    def calculate_player_territorial_bonuses(self, player_index):
        """
        Calculate summed territorial bonuses from all owned territories.

        Args:
            player_index: Index of the player (0-based)

        Returns:
            dict: {bonus_type: total_percent} mapping (e.g., {'income_bonus': 6, 'unit_cost': -10})
        """
        bonuses = {}
        for territory, owner in self.territory_owners.items():
            if owner == player_index:
                bonus_type = map_data.get_territory_bonus(territory)
                if bonus_type:
                    bonuses[bonus_type] = bonuses.get(bonus_type, 0) + self.BONUS_TYPES[bonus_type]['value']
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

    def get_player_army_count(self, player_index):
        """
        Get total number of armies controlled by a player across the entire map.
        This includes armies in territories and armies in training.

        Args:
            player_index: The player index to count armies for

        Returns:
            int: Total number of armies for the player
        """
        total = 0

        # Count armies in territories owned by the player
        for territory, owner in self.territory_owners.items():
            if owner == player_index:
                # Add armies in territory
                total += self.armies.get(territory, 0)

        # Count armies currently being trained
        for territory, training_data in self.training_queue.items():
            if self.territory_owners.get(territory, -1) == player_index:
                for unit_type, turns_left in training_data.items():
                    # Each entry represents one unit being trained
                    total += len(turns_left)

        return total

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
        # Check if current player has a garrison in this territory (can be allied territory)
        garrison = self.territory_garrisons.get(territory, {}).get(self.current_player)

        if not garrison or garrison.get('unmoved', 0) <= 0:
            # In testing mode, allow selecting even without garrison
            if self.testing_mode and self.territory_owners.get(territory, -1) == self.current_player:
                # Use legacy system for testing mode
                if self.armies_unmoved.get(territory, 0) <= 0:
                    self.add_message("No armies available to move in this territory")
                    return False
                self.selected_army = (territory, self.armies_unmoved.get(territory, 0))
                return True
            else:
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

        total_strength = 0.0
        for unit_type, count in composition.items():
            effectiveness = self.calculate_unit_effectiveness(unit_type, enemy_composition)

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

            total_strength += count * effectiveness * base_multiplier * level_bonus

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

        all_sorted = sorted(units, key=lambda u: (u.get('level', 0), tier_map.get(id(u), 1)))

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
        # Get current totals from garrison system (source of truth)
        # NOTE: For backward compatibility, we use the territory owner's garrison
        # In multi-garrison scenarios, this represents the owner's units only
        owner = self.territory_owners.get(territory, -1)
        if owner >= 0:
            garrison = self.territory_garrisons.get(territory, {}).get(owner)
            if garrison:
                unmoved = garrison.get('unmoved', 0)
                moved = garrison.get('moved', 0)
            else:
                unmoved = 0
                moved = 0
        else:
            # Neutral territory
            unmoved = 0
            moved = 0
        total = unmoved + moved
        
        # Check if we need to recreate
        needs_recreation = False
        if territory not in self.army_units:
            needs_recreation = True
        else:
            # Check if count matches LIVE total
            if len(self.army_units[territory]) != total:
                # COUNT MISMATCH - recreate
                logger.debug(f"Recreating army units for {territory}: cached {len(self.army_units[territory])}, actual {total}")
                needs_recreation = True
            else:
                # Count matches, but check if STATUS distribution matches
                # Note: 'ordered' units are still part of 'ready/unmoved', so we count them together
                cached_ready = sum(1 for u in self.army_units[territory] if u['status'] in ['ready', 'ordered'])
                cached_moved = sum(1 for u in self.army_units[territory] if u['status'] == 'moved')
                if cached_ready != unmoved or cached_moved != moved:
                    # STATUS MISMATCH - recreate
                    logger.debug(f"Recreating army units for {territory}: status mismatch")
                    logger.debug(f"  Cached: {cached_ready} ready/ordered, {cached_moved} moved")
                    logger.debug(f"  Actual: {unmoved} unmoved, {moved} moved")
                    needs_recreation = True
        
        if needs_recreation:
            # Preserve existing unit data (type, xp, level) if we have them
            existing_data = {}
            if territory in self.army_units:
                for unit in self.army_units[territory]:
                    existing_data[unit['id']] = {
                        'type': unit.get('type', 'Swordsman'),
                        'xp': unit.get('xp', 0),
                        'level': unit.get('level', 0)
                    }

            units = []
            # Add ready units first (can be commanded)
            for i in range(unmoved):
                prev = existing_data.get(i, {})
                units.append({
                    'id': i,
                    'status': 'ready',
                    'order': None,
                    'type': prev.get('type', 'Swordsman'),
                    'xp': prev.get('xp', 0),
                    'level': prev.get('level', 0)
                })
            # Add moved units (exhausted this turn)
            for i in range(moved):
                unit_id = unmoved + i
                prev = existing_data.get(unit_id, {})
                units.append({
                    'id': unit_id,
                    'status': 'moved',
                    'order': None,
                    'type': prev.get('type', 'Swordsman'),
                    'xp': prev.get('xp', 0),
                    'level': prev.get('level', 0)
                })
            
            self.army_units[territory] = units
        
        return self.army_units[territory]
    
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

                    # Cancel training
                    if (territory in self.hero_training_queue and
                        plot_index in self.hero_training_queue[territory]):
                        hero_type, _ = self.hero_training_queue[territory][plot_index]
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
                    # Calculate recovery (50% of building costs)
                    farm_recovery = destroyed_farms * 15  # 50% of 30 gold Farm cost
                    mine_recovery = destroyed_mines * 20  # 50% of 40 gold Mine cost
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
        
        # Validate: territories must be adjacent
        if not map_data.are_adjacent(from_territory, to_territory):
            self.add_message("Territories are not adjacent!")
            return False
        
        # Validate: must have unmoved armies (check current player's garrison)
        from_owner = self.territory_owners.get(from_territory, -1)
        garrison = self.territory_garrisons.get(from_territory, {}).get(from_owner)
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
        # In testing mode, use the actual owner of the territory
        order_player = self.territory_owners[from_territory] if self.testing_mode else self.current_player
        
        order = MovementOrder(
            from_territory=from_territory,
            to_territory=to_territory,
            army_count=army_count,
            player=order_player
        )
        
        self.movement_orders.append(order)
        self.add_message(f"Order created: {army_count} armies {from_territory} ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ {to_territory}")
        
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

        # Validate: territories must be adjacent (with error handling)
        try:
            if not map_data.are_adjacent(from_territory, to_territory):
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
        
        self.add_message(f"Order created: {len(unit_ids)} armies {from_territory} Ã¢â€ â€™ {to_territory}")
        
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
            self.add_message(f"Order cancelled: {order.from_territory} ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ {order.to_territory}")
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
                current_garrison = self.armies.get(to_terr, 0)
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

                    # Update garrison counts (use actual removed count)
                    garrison['unmoved'] -= actual_removed

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
                units=extracted_units
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
            self.add_message(f"  Player {player + 1}: {comp_str} (Effective Strength: {effective_strength:.1f})")
        
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
            # No new owner (becomes neutral), so Champion of the People doesn't apply
            self.destroy_buildings(territory, battle.original_owner, new_owner=-1)

            self.territory_owners[territory] = -1  # Neutral
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
                    current_keep_armies = self.armies.get(keep_territory, 0)
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

                        # Update army counters for Keep territory
                        self.armies_moved[keep_territory] += 1
                        self.armies[keep_territory] = self.armies_moved[keep_territory] + self.armies_unmoved[keep_territory]

                        # Log the retreat
                        self.add_message(f"  Safe Haven: 1 {retreating_unit_type} from Player {loser_player + 1} retreats to {keep_territory}!")

        # Set territory ownership
        self.territory_owners[territory] = winner

        # Tutorial hook: notify territory conquered (only if ownership changed)
        if self.tutorial_mission and battle.original_owner != winner:
            self.tutorial_mission.notify_event(
                'territory_conquered',
                territory=territory,
                new_owner=winner
            )

        # Capital Assault: Check if conquered territory is enemy's capital
        # Note: Allies cannot eliminate each other - only enemies can capture capitals
        if self.victory_condition == "Capital Assault":
            for player_index, capital in self.player_starting_territories.items():
                # Check: capital matches, not self, and not an ally (enemies only)
                if capital == territory and player_index != winner and not self.are_allies(winner, player_index):
                    # Capital conquered - eliminate the player
                    logger.info(f"[CAPITAL ASSAULT] Player {winner + 1} conquered Player {player_index + 1}'s capital!")
                    self.eliminate_player(player_index)
                    # Note: check_victory() is called at end of _update_battle_results() at line 3701

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
                logger.warning(f"[UNIT_TYPE_DIAG] _update_battle_results fallback: no survivor units found "
                               f"for Player {winner + 1} at {territory} ({surviving_armies} should survive). "
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

        return True
    
    def _advance_to_next_player(self):
        """Internal method to advance to the next player (called after battle resolution)"""
        # Block turn advancement if game has ended (victory/defeat detected)
        if self.phase == 'ended':
            logger.info("Turn advancement blocked - game has ended")
            return

        # Tutorial hook: block turn advancement when game is frozen (victory sequence)
        if self.tutorial_mission and getattr(self.tutorial_mission, 'game_frozen', False):
            logger.info("Turn advancement blocked - tutorial game_frozen")
            return

        # Clear building limit tracking for new turn
        self.buildings_started_this_turn.clear()

        # Clear Master Negotiator effect for the player whose turn is ending
        if self.player_master_negotiator_active[self.current_player]:
            self.player_master_negotiator_active[self.current_player] = False
            if self.master_negotiator_active_player == self.current_player:
                self.master_negotiator_activation_time = None
                self.master_negotiator_active_player = None

        # Apply taxation to leftover gold BEFORE collecting new income
        if self.phase == 'playing':
            self.apply_taxation(self.current_player)

        # Collect income for the player whose turn is ending
        if self.phase == 'playing':
            self.collect_income(self.current_player)

        # Reset all armies to 'ready' status at turn start using garrison system
        logger.debug(f"Turn advance - current player BEFORE switch: {self.current_player}")
        for territory in map_data.get_all_territories():
            # Reset garrison statuses (handles multi-garrison correctly)
            self.reset_garrison_moved_status(territory)

            # Also handle legacy army_units for backward compatibility
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

        # Set turn phase to planning for the NEW player (before switching players)
        self.turn_phase = 'planning'

        # Clear the ready_to_advance_turn flag
        self.ready_to_advance_turn = False

        # Switch to next player
        self.current_player = (self.current_player + 1) % self.num_players
        self.selected_territory = None
        self.selected_army = None  # Clear army selection

        # NEW: Set turn announcement blocking flag (only during playing phase)
        # Turn start effects will execute after animation completes
        if self.phase == 'playing':
            self.turn_announcement_active = True
            self.deferred_turn_start_actions = True
        # During setup phase, no announcement needed - just a message
        # (turn start effects like building completion are handled in _complete_turn_announcement)

    def _complete_turn_announcement(self):
        """Called when turn announcement animation completes - executes turn start effects"""
        # Only execute turn start logic during playing phase
        if self.phase == 'playing':
            # Add turn message
            self.add_message(f"--- Player {self.current_player + 1}'s Turn ---")

            # Turn phase is 'planning' (set in _advance_to_next_player)
            # Start the planning phase timer for this player
            import time
            self.planning_phase_start_time = time.time()

            # Decrement hero ability cooldowns and silence status for current player
            self._decrement_hero_cooldowns_and_silence()

            # Finish any buildings that complete at the START of this player's turn
            self.last_completed_buildings = self.finish_constructions()  # Store for network sync
            self.last_completed_units = self.finish_training()  # Store for network sync
            # Sound priority order: Research > Castle > Hero
            self.finish_research()  # Finish research FIRST (highest priority sound)
            self.finish_castle_upgrades()  # Then castle upgrades (medium priority sound)
            self.finish_hero_training()  # Then hero training (lowest priority sound)

            # Award XP to Farms and Mines owned by current player (+20 XP/turn)
            self._tick_building_xp()

            # IMPORTANT: Cleanup empty garrisons at turn start (belt & suspenders)
            # This catches any ghost garrisons that might have been missed
            for territory in list(self.territory_garrisons.keys()):
                self.cleanup_empty_garrisons(territory)

        # Unblock game (always do this, even during setup)
        self.turn_announcement_active = False
        self.deferred_turn_start_actions = False

        # Call turn start callback if set (for multiplayer sync)
        if hasattr(self, 'on_turn_start_callback') and self.on_turn_start_callback:
            self.on_turn_start_callback()

        # Tutorial hook: notify that turn announcement completed
        if self.tutorial_mission:
            self.tutorial_mission.notify_event('turn_announcement_done',
                                               player_index=self.current_player)

    def add_message(self, message):
        """Add a message to the message log (keeps entire game history)"""
        self.messages.append(message)
        # No limit - keep all messages for full game history
        logger.info(f"{message}")
    
    def add_chat_message(self, player_id, message, channel="all"):
        """Add a chat message with timestamp, player info, and channel.

        Args:
            player_id: The player who sent the message
            message: The chat message text
            channel: 'all' for everyone, 'team' for allies only
        """
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        # Store as (timestamp, player_id, message, channel) - 4-tuple
        self.chat_messages.append((timestamp, player_id, message, channel))
        channel_tag = "[TEAM]" if channel == "team" else "[ALL]"
        logger.info(f"[CHAT] {channel_tag} [{timestamp}] Player {player_id + 1}: {message}")

        # Check for cheat code
        if message.strip().lower() == "jurvikisrichboi":
            self.player_gold[player_id] += 3000
            self.add_message(f"Player {player_id + 1} used cheat code: +3000 Gold!")
            logger.info(f"[CHEAT] Player {player_id + 1} gained 3000 gold!")

    def is_chat_visible_to_player(self, chat_msg, viewer_player_id):
        """Check if a chat message should be visible to a specific player.

        Args:
            chat_msg: Chat message tuple (timestamp, sender_id, message, channel)
                      or legacy 3-tuple (timestamp, sender_id, message)
            viewer_player_id: The player viewing chat

        Returns:
            True if message should be visible to viewer
        """
        # Handle legacy 3-tuple format (no channel = all)
        if len(chat_msg) == 3:
            return True

        timestamp, sender_id, message, channel = chat_msg

        # All-chat is visible to everyone
        if channel == "all":
            return True

        # Team chat is visible to sender and their allies
        if channel == "team":
            # Sender always sees their own messages
            if sender_id == viewer_player_id:
                return True

            # Check if viewer is on same team as sender
            if hasattr(self, 'player_teams') and self.player_teams:
                sender_team = self.player_teams.get(sender_id, sender_id)
                viewer_team = self.player_teams.get(viewer_player_id, viewer_player_id)
                return sender_team == viewer_team

            # No team system - team chat not visible to others
            return False

        return True  # Unknown channel - show by default

    def get_visible_chat_messages(self, viewer_player_id):
        """Get chat messages visible to a specific player (filters team chat).

        Args:
            viewer_player_id: The player viewing chat

        Returns:
            List of visible chat message tuples
        """
        return [msg for msg in self.chat_messages
                if self.is_chat_visible_to_player(msg, viewer_player_id)]

    def calculate_state_checksum(self):
        """
        Calculate a checksum of critical game state for desync detection.

        Returns:
            str: MD5 hash of critical game state
        """
        import hashlib
        import json

        # Collect critical state that should be identical on both clients
        critical_state = {
            'current_player': self.current_player,
            'turn_number': self.turn_number,
            'turn_phase': self.turn_phase,
            'territory_owners': dict(sorted(self.territory_owners.items())),
            'armies': dict(sorted(self.armies.items())),
            'armies_moved': dict(sorted(self.armies_moved.items())),
            'armies_unmoved': dict(sorted(self.armies_unmoved.items())),
            'player_gold': self.player_gold.copy(),
            'buildings': {t: dict(sorted(plots.items())) for t, plots in sorted(self.buildings.items())},
            # Note: We don't include chat, messages, or UI state
        }

        # Serialize to JSON and calculate hash
        state_json = json.dumps(critical_state, sort_keys=True)
        checksum = hashlib.md5(state_json.encode()).hexdigest()

        return checksum

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

        # Tax rates for each level
        tax_rates = [0.0, 0.25, 0.5, 0.75, 1.0]
        rate = tax_rates[self.taxation_level]

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
        self.armies[territory] = 3  # Start with 3 armies
        self.armies_unmoved[territory] = 3  # All can move immediately

        # Create army units: 1 Swordsman, 1 Archer, 1 Pikeman
        # Phase 2E: Use _make_unit() factory for consistent unit dict creation
        army_units = [
            self._make_unit('Swordsman', 0, 'ready'),
            self._make_unit('Archer', 1, 'ready'),
            self._make_unit('Pikeman', 2, 'ready'),
        ]
        self.army_units[territory] = army_units

        # Initialize garrison in multi-garrison system
        self.add_garrison(territory, player_index, unmoved=3, moved=0, units=army_units.copy())

        self.territories_chosen[player_index] += 1
        
        # Check if setup is complete
        if all(count >= self.max_starting_territories for count in self.territories_chosen):
            self.phase = 'playing'
            self.current_player = 0
            # Start the planning phase timer for the first player
            import time
            self.planning_phase_start_time = time.time()

        return True

    def get_remaining_planning_time(self):
        """Get the remaining planning time in seconds for the current player."""
        if self.planning_phase_start_time is None or self.turn_phase != 'planning':
            return None

        import time
        elapsed = time.time() - self.planning_phase_start_time
        time_limit = self.player_planning_time_limit[self.current_player]
        remaining = time_limit - elapsed
        return max(0.0, remaining)

    def check_planning_timer_expired(self):
        """Check if planning timer has expired and auto-execute if so."""
        if self.turn_phase != 'planning':
            return False

        # Check if mission allows timer expiry (tutorial disables, Mission 2 enables)
        if self.tutorial_mission:
            # If mission has allow_timer_expiry attribute, use it; otherwise disable
            if not getattr(self.tutorial_mission, 'allow_timer_expiry', False):
                return False

        remaining = self.get_remaining_planning_time()
        if remaining is not None and remaining <= 0:
            # Timer expired - auto execute turn
            self.add_message(f"Planning time expired! Executing turn...")
            self.next_player()
            return True
        return False

    def next_player(self):
        """Move to the next player's turn (or execute orders/battles first)"""
        # Clear planning timer when leaving planning phase
        if self.turn_phase == 'planning':
            self.planning_phase_start_time = None

        # If in planning phase with orders, execute them first
        if self.turn_phase == 'planning' and len(self.movement_orders) > 0:
            self.execute_all_orders()
            # Animations are now playing - stop here and wait for them to complete
            # Battles will be detected in _process_arrivals() after animations finish
            return

        # If in execution phase, animations are still playing - can't advance yet
        if self.turn_phase == 'execution':
            self.add_message("Animations are still playing! Wait for them to complete.")
            return

        # If in battles phase, can't advance until battles are resolved
        if self.turn_phase == 'battles' and len(self.pending_battles) > 0:
            self.add_message("Resolve all battles before ending turn!")
            return

        # If we reach here, ready to advance to next player
        self._advance_to_next_player()

    def update_animations(self, delta_time):
        """
        Update all active army movement animations.

        Args:
            delta_time: Time elapsed since last frame (in seconds)

        This method is called every frame to progress animations and trigger
        battles when animations complete.
        """
        if not self.active_animations:
            return

        # Update all animations
        animations_to_remove = []
        for anim in self.active_animations:
            anim.elapsed += delta_time
            anim.progress = min(1.0, anim.elapsed / anim.duration)

            if anim.progress >= 1.0:
                anim.completed = True
                animations_to_remove.append(anim)

        # Remove completed animations and process arrivals
        for anim in animations_to_remove:
            self.active_animations.remove(anim)
            # Store arrival data for batch processing
            self.pending_arrivals.append(anim)

        # If all animations complete, process arrivals and detect battles
        # In simultaneous mode, SimPhaseManager handles arrival processing instead
        if not self.active_animations and self.pending_arrivals:
            if self.game_mode == 'simultaneous':
                # Simultaneous mode: clear pending_arrivals, let SimPhaseManager handle it
                self.pending_arrivals = []
            else:
                self._process_arrivals()

    def _process_arrivals(self):
        """
        Process all pending army arrivals after animations complete.
        This handles the actual army movement and battle detection.
        """
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

            # Add defender's forces (garrison + Keep) ONLY if there will be a battle
            # Check if there will be a battle (multiple players arriving)
            # We need to check this before adding defender's forces
            potential_battle = len(incoming_armies[territory]) > 1 or (
                len(incoming_armies[territory]) == 1 and
                current_owner != -1 and
                current_owner not in incoming_armies[territory]
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
                                # Check for victory after elimination
                                self.check_victory()

                    # Add conqueror's garrison (use actual unit count)
                    self.add_garrison(territory, winner, moved=len(units), units=units)

                    # Sync garrison counts with actual unit list after add
                    self._sync_garrison_counts(territory, winner)

                    # Sync legacy data
                    self.sync_legacy_garrison_data(territory)

                    self.add_message(f"Player {winner + 1} conquers {territory} ({winner_armies} armies)")

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
                            # If player is owner and defending, their garrison was added at line 3933
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
        else:
            # No battles - animations complete, advance to next player immediately
            if self.turn_phase == 'execution':
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

        # TEAM CHECK: Cannot attack allies, but CAN reinforce them
        is_ally = (to_owner >= 0 and self.are_allies(self.current_player, to_owner))

        if is_ally:
            # Allied reinforcement - check total army limit
            total_at_dest = self.get_territory_total_armies(to_territory)
            if total_at_dest + army_size > self.MAX_ARMIES_PER_TERRITORY:
                self.add_message(f"Cannot reinforce {to_territory}: would exceed army limit of {self.MAX_ARMIES_PER_TERRITORY}!")
                return False

        # Can only move unmoved armies
        army_size = min(army_size, self.armies_unmoved[from_territory])
        if army_size == 0:
            return False

        # Get source garrison to extract units
        source_garrison = self.territory_garrisons.get(from_territory, {}).get(self.current_player)
        units_to_move = []

        if not source_garrison:
            # Fallback: No garrison exists, just use old system
            self.armies_unmoved[from_territory] -= army_size
        else:
            # Extract units from source garrison (take first army_size unmoved units)
            remaining_units = []
            units_moved_count = 0

            for unit in source_garrison['units']:
                if units_moved_count < army_size and unit['status'] == 'ready':
                    # Mark unit as moved and transfer it
                    unit['status'] = 'moved'
                    units_to_move.append(unit.copy())
                    units_moved_count += 1
                else:
                    remaining_units.append(unit)

            # Validate we got enough units
            if units_moved_count < army_size:
                logger.warning(f"[TOOLTIP MISMATCH] {from_territory} Player {self.current_player}: "
                      f"Requested {army_size} units but only found {units_moved_count} ready units. "
                      f"Garrison claims unmoved={source_garrison.get('unmoved', 0)} but units list mismatch.")

            # Update garrison count with actual moved count
            source_garrison['unmoved'] -= units_moved_count
            source_garrison['units'] = remaining_units

            # Sync legacy data for source territory after removing units
            self.sync_legacy_garrison_data(from_territory)

        # Moving to own territory or ally territory (reinforcement)
        if to_owner == self.current_player or is_ally:
            if is_ally:
                # Allied reinforcement - add garrison for current player at destination
                # Units arrive as "moved" (can't move again this turn)
                self.add_garrison(to_territory, self.current_player, unmoved=0, moved=army_size, units=units_to_move if units_to_move else None)
                # Sync legacy data for destination (shows owner's garrison in legacy arrays)
                self.sync_legacy_garrison_data(to_territory)
                self.add_message(f"Player {self.current_player + 1} reinforced ally {to_territory} with {army_size} armies")
            else:
                # Moving to own territory - use garrison system
                self.add_garrison(to_territory, self.current_player, unmoved=0, moved=army_size, units=units_to_move if units_to_move else None)
                self.sync_legacy_garrison_data(to_territory)
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
                    # Check for Pillage ability (trigger BEFORE changing ownership)
                    previous_owner = to_owner
                    keep_was_destroyed = has_keep

                    self.destroy_all_buildings(to_territory)
                    self.territory_owners[to_territory] = self.current_player

                    # Capital Assault: Check if conquered territory is enemy's capital
                    logger.debug(f"Conquered {to_territory} (with Keep), Victory Condition: {self.victory_condition}")
                    logger.debug(f"Starting territories: {self.player_starting_territories}")
                    logger.debug(f"Current player: {self.current_player}")

                    if self.victory_condition == "Capital Assault":
                        for player_index, capital in self.player_starting_territories.items():
                            logger.debug(f"Checking player {player_index}'s capital {capital} vs conquered {to_territory}")
                            # Check: capital matches, not self, and not an ally (enemies only)
                            if capital == to_territory and player_index != self.current_player and not self.are_allies(self.current_player, player_index):
                                # Capital conquered - eliminate the player
                                logger.info(f"[CAPITAL ASSAULT] Player {self.current_player + 1} conquered Player {player_index + 1}'s capital!")
                                self.eliminate_player(player_index)

                    # Pillage: Award gold if attacker has Vearen Asford and destroyed enemy Keep
                    if keep_was_destroyed and previous_owner >= 0 and previous_owner != self.current_player:
                        if self.player_has_asford(self.current_player):
                            self.player_gold[self.current_player] += 200
                            self.add_message(f"  Pillage! Vearen Asford plunders 200 Gold from the ruins!")

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
                # Check for Pillage ability (trigger BEFORE changing ownership)
                previous_owner = to_owner
                keep_existed = self.has_fortress(to_territory)

                self.destroy_all_buildings(to_territory)
                self.territory_owners[to_territory] = self.current_player

                # Capital Assault: Check if conquered territory is enemy's capital
                logger.debug(f"Conquered {to_territory}, Victory Condition: {self.victory_condition}")
                logger.debug(f"Starting territories: {self.player_starting_territories}")
                logger.debug(f"Current player: {self.current_player}")

                if self.victory_condition == "Capital Assault":
                    for player_index, capital in self.player_starting_territories.items():
                        logger.debug(f"Checking player {player_index}'s capital {capital} vs conquered {to_territory}")
                        # Check: capital matches, not self, and not an ally (enemies only)
                        if capital == to_territory and player_index != self.current_player and not self.are_allies(self.current_player, player_index):
                            # Capital conquered - eliminate the player
                            logger.info(f"[CAPITAL ASSAULT] Player {self.current_player + 1} conquered Player {player_index + 1}'s capital!")
                            self.eliminate_player(player_index)

                # Pillage: Award gold if attacker has Vearen Asford and destroyed enemy Keep
                if keep_existed and previous_owner >= 0 and previous_owner != self.current_player:
                    if self.player_has_asford(self.current_player):
                        self.player_gold[self.current_player] += 200
                        self.add_message(f"  Pillage! Vearen Asford plunders 200 Gold from the ruins!")

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
        elif building_type == 'Barracks':
            self._track_stat(self.current_player, 'barracks_built')
        elif building_type == 'Keep':
            self._track_stat(self.current_player, 'keeps_built')

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

        # Tutorial hook: notify that construction started
        if self.tutorial_mission:
            self.tutorial_mission.notify_event('build_started', building_type=building_type, territory=territory)

        return True
    
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
                    
                    completed.append((territory, building_type, plot_index))
                else:
                    # Update turns remaining
                    self.under_construction[territory][plot_index] = (building_type, turns_remaining)

        # Add messages for completed buildings (stats tracked at start_construction time)
        for territory, building_type, plot_index in completed:
            owner = self.territory_owners[territory]
            self.add_message(f"Player {owner + 1}: {building_type} completed in {territory}")

        # Return completed buildings for network synchronization
        return completed
    
    def cancel_construction(self, territory, plot_index):
        """Cancel construction and refund 100%"""
        if territory not in self.under_construction:
            return False

        if plot_index not in self.under_construction[territory]:
            return False

        building_type, _ = self.under_construction[territory][plot_index]
        owner = self.territory_owners[territory]

        # Get effective cost with all discounts applied (what was actually paid)
        cost = self.get_building_cost(building_type, owner)

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
                hero_type, _ = self.hero_training_queue[territory][plot_index]
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
    
    def destroy_all_buildings(self, territory):
        """Destroy all buildings in a territory (when conquered)"""
        # Remove completed buildings
        if territory in self.buildings:
            del self.buildings[territory]

        # Veterancy: Remove all building XP data
        if territory in self.building_xp:
            del self.building_xp[territory]
        
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
        current_armies = self.armies.get(territory, 0)
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
                          'Swordsman': 'swordsmen_trained', 'Cavalry': 'cavalry_trained'}
        if unit_type in _unit_stat_map:
            self._track_stat(self.current_player, _unit_stat_map[unit_type])

        # Add to queue (unit_type, turns_remaining)
        self.training_queue[territory][barracks_plot_index].append((unit_type, 1))
        
        self.add_message(f"Player {self.current_player + 1} started training {unit_type} in {territory} ({unit_cost} gold, 1 turn)")

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
        
        # Get unit info
        unit_type, turns_remaining = self.training_queue[territory][barracks_plot_index][queue_index]

        # Get correct cost for this unit type (apply discounts)
        base_cost = self.UNIT_TYPES.get(unit_type, {}).get('cost', 25)
        owner = self.territory_owners[territory]
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
        return True

    def start_hero_training(self, territory, keep_plot_index, hero_type):
        """
        Start training a Hero at a specific Keep.

        Heroes have special rules:
        - Only ONE hero can train per Keep at a time (no queue)
        - Only ONE hero of each type per player globally
        - Training time is in player turns (not game turns)
        - 100% refund on cancellation
        """
        # 1. Validate hero type
        if hero_type not in self.HERO_TYPES:
            self.add_message(f"Invalid hero type: {hero_type}")
            return False

        # 2. Check ownership
        if self.territory_owners.get(territory, -1) != self.current_player:
            self.add_message("You don't own this territory!")
            return False

        # 3. Verify this is a Keep
        if (territory not in self.buildings or
            keep_plot_index not in self.buildings[territory] or
            self.buildings[territory][keep_plot_index] != 'Keep'):
            self.add_message("This is not a Keep!")
            return False

        # 4. Check if Keep is upgrading to Castle (blocks new training)
        if self.is_upgrading_to_castle(territory, keep_plot_index):
            self.add_message("Cannot train hero while Keep is upgrading to Castle!")
            return False

        # 5. Check if Keep already training
        if (territory in self.hero_training_queue and
            keep_plot_index in self.hero_training_queue[territory]):
            self.add_message("This Keep is already training a hero!")
            return False

        # 5b. Check if Keep already has a trained hero residing in it
        if self.current_player in self.heroes:
            for hero_name, hero_data in self.heroes[self.current_player].items():
                if (hero_data['keep_territory'] == territory and
                    hero_data['keep_plot'] == keep_plot_index):
                    self.add_message(f"This Keep already has {hero_name}!")
                    return False

        # 6. Check global uniqueness
        if hero_type in self.hero_ownership[self.current_player]:
            self.add_message(f"You already have {hero_type}!")
            return False

        # 6b. Check hero limit
        current_hero_count = len(self.hero_ownership[self.current_player])
        hero_limit = self.player_hero_limit[self.current_player]
        if current_hero_count >= hero_limit:
            self.add_message(f"Hero limit reached! ({current_hero_count}/{hero_limit})")
            return False

        # 7. Check gold
        hero_cost = self.HERO_TYPES[hero_type]['cost']

        # Apply Royal Decree discount for Heroes
        discount_percent = self.player_royal_decree_discount[self.current_player]
        if discount_percent > 0:
            hero_cost = int(hero_cost * (100 - discount_percent) / 100)

        if self.player_gold[self.current_player] < hero_cost:
            self.add_message(f"Not enough gold! (Need {hero_cost})")
            return False

        # 8. Deduct gold and track spending for recap screen
        self.player_gold[self.current_player] -= hero_cost
        self._track_stat(self.current_player, 'gold_spent', hero_cost)

        # 9. Add to training queue
        training_time = self.HERO_TYPES[hero_type]['training_time']
        if territory not in self.hero_training_queue:
            self.hero_training_queue[territory] = {}
        self.hero_training_queue[territory][keep_plot_index] = (hero_type, training_time)

        # 10. Mark as owned (prevents duplicate training)
        self.hero_ownership[self.current_player].add(hero_type)

        self.add_message(f"Player {self.current_player + 1} started training {hero_type} ({hero_cost} gold, {training_time} turns)")
        return True

    def cancel_hero_training(self, territory, keep_plot_index):
        """Cancel hero training with 100% refund (vs 50% for units)."""
        # 1. Validate training exists
        if (territory not in self.hero_training_queue or
            keep_plot_index not in self.hero_training_queue[territory]):
            return False

        # 2. Get hero info and calculate refund (must match what was paid)
        hero_type, _ = self.hero_training_queue[territory][keep_plot_index]
        owner = self.territory_owners[territory]
        hero_cost = self.get_hero_cost(hero_type, owner)

        # 3. 100% refund (key difference!)
        self.player_gold[owner] += hero_cost

        # 4. Remove from queue
        del self.hero_training_queue[territory][keep_plot_index]
        if not self.hero_training_queue[territory]:
            del self.hero_training_queue[territory]

        # 5. Remove from ownership (allow retraining)
        self.hero_ownership[owner].discard(hero_type)

        self.add_message(f"Hero training canceled, {hero_cost} gold refunded (100%)")
        return True

    def finish_hero_training(self):
        """Complete hero training (called at start of player's turn)."""
        if not hasattr(self, 'hero_training_queue'):
            self.hero_training_queue = {}
            return

        territories_to_remove = []

        for territory, keeps_dict in list(self.hero_training_queue.items()):
            # Only process current player's territories
            owner = self.territory_owners.get(territory, -1)
            if owner != self.current_player:
                continue

            keeps_to_remove = []

            for keep_plot_index, (hero_type, turns_remaining) in list(keeps_dict.items()):
                # Verify Keep still exists
                keep_exists = (territory in self.buildings and
                              keep_plot_index in self.buildings[territory] and
                              self.buildings[territory][keep_plot_index] == 'Keep')

                if not keep_exists:
                    # Keep destroyed - lose training (no refund)
                    keeps_to_remove.append(keep_plot_index)
                    self.hero_ownership[owner].discard(hero_type)
                    self.add_message(f"{territory}: {hero_type} training lost (Keep destroyed)")
                    continue

                # Decrement timer
                turns_remaining -= 1

                if turns_remaining <= 0:
                    # Training complete!
                    if owner not in self.heroes:
                        self.heroes[owner] = {}

                    self.heroes[owner][hero_type] = {
                        'keep_territory': territory,
                        'keep_plot': keep_plot_index,
                        'status': 'active'
                    }

                    self.add_message(f"Player {owner + 1}: {hero_type} trained in {territory}!")
                    # Track hero trained for recap screen
                    self._track_stat(owner, 'heroes_trained')

                    # Play hero recruitment sound for human player only
                    # FIX: Check if owner is human (not AI) - sounds should never play for AI actions
                    should_play_sound = not self.player_is_ai[owner]
                    if self.network_mode and should_play_sound:
                        # Additional check: only play if this is the local player's hero
                        should_play_sound = (owner == self.local_player_index)

                    if should_play_sound:
                        from global_sound import play_hero_recruit_sound, sound_manager
                        # Check if a sound is currently playing (likely research completion)
                        is_sound_playing = any(
                            channel and channel.get_busy()
                            for channel in sound_manager.currently_playing.values()
                        )
                        # Queue if something is playing, otherwise play immediately
                        play_hero_recruit_sound(hero_type, use_queue=is_sound_playing)

                    keeps_to_remove.append(keep_plot_index)
                    # NOTE: Keep in hero_ownership - hero is owned!
                else:
                    # Update timer
                    keeps_dict[keep_plot_index] = (hero_type, turns_remaining)

            # Clean up
            for keep_plot_index in keeps_to_remove:
                if keep_plot_index in keeps_dict:
                    del keeps_dict[keep_plot_index]

            if not keeps_dict:
                territories_to_remove.append(territory)

        for territory in territories_to_remove:
            del self.hero_training_queue[territory]

    def kill_heroes_in_keep(self, territory, keep_plot_index, previous_owner):
        """
        Kill all heroes residing in a destroyed Keep.

        Args:
            territory: Territory name
            keep_plot_index: Keep plot index
            previous_owner: Player who owned the Keep

        Returns:
            int: Number of heroes killed
        """
        if previous_owner < 0 or previous_owner >= self.num_players:
            return 0

        if previous_owner not in self.heroes:
            return 0

        # Find heroes in this Keep
        heroes_to_remove = []
        for hero_type, hero_data in self.heroes[previous_owner].items():
            if (hero_data['keep_territory'] == territory and
                hero_data['keep_plot'] == keep_plot_index):
                heroes_to_remove.append(hero_type)

        # Remove heroes
        for hero_type in heroes_to_remove:
            del self.heroes[previous_owner][hero_type]
            self.hero_ownership[previous_owner].discard(hero_type)
            self.add_message(f"Player {previous_owner + 1}: {hero_type} has died!")

        return len(heroes_to_remove)

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

        # Trigger visual effects for completed upgrades
        if self.map_renderer:
            for territory, plot_index in completed_with_plots:
                self.map_renderer.trigger_castle_upgrade_effect(territory, plot_index)

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
        self.research_in_progress[self.current_player] = {
            'tech_id': tech_id,
            'turns_remaining': turns
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

        # Find the technology to get cost
        tech = None
        for t in self.technologies:
            if t['id'] == tech_id:
                tech = t
                break

        if not tech:
            return False

        # Refund the cost (must match what was actually paid, including all modifiers)
        base_cost = tech.get('cost', 0)
        cost = self.get_effective_tech_cost(base_cost, player_id)

        if cost > 0:
            self.player_gold[player_id] += cost

        # Remove from research tracking
        del self.research_in_progress[player_id]

        self.add_message(f"Research cancelled: {tech['name']}, {cost} gold refunded (100%)")
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
                    # Set hero limit to the new value
                    self.player_hero_limit[self.current_player] = effect_value
                    self.add_message(f"Research complete: {tech['name']}! Hero limit increased to {effect_value}")
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
        else:
            # Update turns remaining
            self.research_in_progress[self.current_player]['turns_remaining'] = turns_remaining

    def activate_hero_ability(self, hero_name, ability_index):
        """
        Activate a hero ability.

        Args:
            hero_name: Name of the hero
            ability_index: Index of the ability (0, 1, or 2)

        Returns:
            bool: True if ability was activated, False otherwise
        """
        current_player = self.current_player

        # Validate hero exists and belongs to current player
        if current_player not in self.heroes:
            return False
        if hero_name not in self.heroes[current_player]:
            return False

        # Get hero and ability info
        hero_info = self.HERO_TYPES.get(hero_name)
        if not hero_info:
            return False

        abilities = hero_info.get('abilities', [])
        if ability_index >= len(abilities):
            return False

        ability = abilities[ability_index]
        ability_name = ability.get('name', 'Unknown')
        ability_type = ability.get('type', 'active')

        # Only active abilities can be activated
        if ability_type != 'active':
            return False

        # Check if already on cooldown
        if hero_name in self.hero_ability_cooldowns.get(current_player, {}):
            if ability_name in self.hero_ability_cooldowns[current_player][hero_name]:
                if self.hero_ability_cooldowns[current_player][hero_name][ability_name] > 0:
                    return False

        # Check if silenced
        if self.hero_silence_status.get(current_player, 0) > 0:
            return False

        # Activate ability based on ability name
        if ability_name == 'Vow of Silence':
            self._activate_vow_of_silence(hero_name, ability)
        elif ability_name == 'Reinforce':
            # Reinforce spawns units in Brennhen's Keep territory
            # No targeting required - execute immediately
            success, error_msg = self.execute_reinforce(current_player)
            if not success:
                # Return error message to be displayed by UI
                return error_msg
        elif ability_name == 'Relentless Charge':
            # Relentless Charge requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_relentless_charge()
            return 'requires_targeting'
        elif ability_name == 'Aggressive Diplomacy':
            # Aggressive Diplomacy requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_aggressive_diplomacy()
            return 'requires_targeting'
        elif ability_name == 'Levy':
            # Levy requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_levy()
            return 'requires_targeting'
        elif ability_name == 'Royal Charisma':
            # Royal Charisma requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_royal_charisma()
            return 'requires_targeting'
        elif ability_name == 'Regicide':
            # Regicide requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_regicide()
            return 'requires_targeting'
        elif ability_name == 'Extort Populace':
            # Extort Populace gains gold for each Keep/Castle owned
            # No targeting required - execute immediately
            success, error_msg = self.execute_extort_populace(current_player)
            if not success:
                # Return error message to be displayed by UI
                return error_msg
        elif ability_name == 'Decisive Strike':
            # Decisive Strike requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_decisive_strike()
            return 'requires_targeting'
        elif ability_name == 'Valorous Charge':
            # Valorous Charge requires targeting - handled by UI layer
            # This return value signals the UI to enter targeting mode
            # The actual execution happens in execute_valorous_charge()
            return 'requires_targeting'
        elif ability_name == 'Embargo':
            # Embargo blocks all income for enemies on their next turn
            # No targeting required - execute immediately
            self._activate_embargo(current_player)
        elif ability_name == 'Master Negotiator':
            # Master Negotiator activates 75% discount for this turn
            # No targeting required - execute immediately
            self._activate_master_negotiator(current_player)
        else:
            # Unknown ability - just add to action log
            self.add_message(f"Player {current_player + 1}: {hero_name} used {ability_name}!")

        # Note: Defiance protection checking will be added here for territory-targeted abilities
        # when such abilities are implemented. Defiance blocks enemy abilities on protected territories.

        # Put ability on cooldown
        cooldown = ability.get('cooldown', 0)
        if current_player not in self.hero_ability_cooldowns:
            self.hero_ability_cooldowns[current_player] = {}
        if hero_name not in self.hero_ability_cooldowns[current_player]:
            self.hero_ability_cooldowns[current_player][hero_name] = {}
        self.hero_ability_cooldowns[current_player][hero_name][ability_name] = cooldown

        return True

    def _activate_vow_of_silence(self, caster_hero_name, ability):
        """
        Activate Vow of Silence ability - silences all enemy heroes until end of your next turn.

        Args:
            caster_hero_name: Name of hero casting the ability
            ability: Ability data dict
        """
        current_player = self.current_player

        # Silence all enemy players
        for player_index in range(self.num_players):
            if player_index != current_player:
                # Silence lasts until start of caster's next turn
                # Set to num_players because decrement happens at START of each turn
                # Example (2 players):
                #   - Player 1 casts: Player 2 silence = 2
                #   - Player 2 turn starts: decrement 2→1, effect active during Player 2's turn
                #   - Player 1 turn starts: decrement 1→0, effect expires
                self.hero_silence_status[player_index] = self.num_players

        # Record activation time for visual effects
        import pygame
        self.silence_activation_time = pygame.time.get_ticks()

        # Add message to action log
        self.add_message(f"Player {current_player + 1}: {caster_hero_name} casts Vow of Silence!")
        self.add_message("All enemy heroes are silenced until next turn!")

    def _activate_master_negotiator(self, player_index):
        """
        Activate Master Negotiator ability - grants 75% discount on Farms, Mines, and Squares for this turn.

        Args:
            player_index: Player index activating the ability
        """
        # Activate the discount for this turn
        self.player_master_negotiator_active[player_index] = True

        # Record activation time for visual effects
        import pygame
        self.master_negotiator_activation_time = pygame.time.get_ticks()
        self.master_negotiator_active_player = player_index

        # Add message to action log
        self.add_message(f"Player {player_index + 1}: Master Negotiator activated!")
        self.add_message("Farms, Mines, and Squares cost 75% less this turn!")

    def _activate_embargo(self, player_index):
        """
        Activate Embargo ability - blocks all income for enemy players on their next turn.

        Args:
            player_index: Player index activating the ability
        """
        # Mark all enemy players to have income blocked on their next turn
        for i in range(self.num_players):
            if i != player_index:
                if i not in self.embargo_blocked_players:
                    self.embargo_blocked_players.append(i)

        # Add message to action log
        self.add_message(f"Player {player_index + 1}: Embargo activated!")
        self.add_message("All enemies will receive no income at the start of their next turn!")

    def execute_relentless_charge(self, target_territory, owner):
        """
        Execute Relentless Charge ability - spawn 4 Cavalry in target territory.

        Args:
            target_territory: Territory name to spawn cavalry in
            owner: Player index who owns Vearen Asford

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Validate territory is owned by player
        if self.territory_owners.get(target_territory) != owner:
            return (False, "Territory not owned by you!")

        # Check army limit (need room for 4 cavalry)
        current_armies = self.armies.get(target_territory, 0)
        if current_armies > 11:
            return (False, f"Territory has too many units! ({current_armies}/15)\nNeed 11 or fewer to summon 4 Cavalry.")

        # Check if territory has Haste effect
        haste_affected_territories = self.get_haste_affected_territories(owner)
        has_haste = target_territory in haste_affected_territories

        # Spawn 4 Cavalry units using multi-garrison system
        # Get owner's garrison
        if target_territory not in self.territory_garrisons:
            self.territory_garrisons[target_territory] = {}
        if owner not in self.territory_garrisons[target_territory]:
            self.territory_garrisons[target_territory][owner] = {
                'unmoved': 0,
                'moved': 0,
                'units': []
            }

        garrison = self.territory_garrisons[target_territory][owner]
        cavalry_spawned = 0

        for i in range(4):
            # Check if we've hit the army limit (total across all garrisons)
            total_armies = sum(len(g['units']) for g in self.territory_garrisons.get(target_territory, {}).values())
            if total_armies >= self.MAX_ARMIES_PER_TERRITORY:
                break

            # Find next available ID within this garrison
            existing_ids = [u['id'] for u in garrison['units']]
            next_id = 0
            while next_id in existing_ids:
                next_id += 1

            # Add cavalry unit to garrison (Daradelle's Bounty - spawned fresh, no XP)
            # Haste makes units ready immediately, otherwise they're moved (exhausted)
            # Phase 2E: Use _make_unit() factory for consistent unit dict creation
            garrison['units'].append(self._make_unit('Cavalry', next_id, 'ready' if has_haste else 'moved'))

            # Update garrison counters
            if has_haste:
                garrison['unmoved'] += 1
            else:
                garrison['moved'] += 1

            cavalry_spawned += 1

        # Sync to legacy system
        self.sync_legacy_garrison_data(target_territory)

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Relentless Charge summoned {cavalry_spawned} Cavalry in {target_territory}{haste_msg}")

        return (True, None)

    def execute_reinforce(self, owner):
        """
        Execute Reinforce ability - spawn 2 Swordsmen in hero's Keep territory.
        Works for both Darius Brennhen and Regnus Aevencourne (campaign clone).

        Args:
            owner: Player index who owns Darius Brennhen or Regnus Aevencourne

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Find Brennhen/Regnus Keep territory
        if owner not in self.heroes:
            return (False, "Hero not found!")

        # Check for either Darius Brennhen or Regnus Aevencourne (campaign clone)
        hero_name = None
        if 'Darius Brennhen' in self.heroes[owner]:
            hero_name = 'Darius Brennhen'
        elif 'Regnus Aevencourne' in self.heroes[owner]:
            hero_name = 'Regnus Aevencourne'
        else:
            return (False, "Hero with Reinforce not found!")

        hero_data = self.heroes[owner][hero_name]
        keep_territory = hero_data['keep_territory']

        # Check army limit (need room for 2 swordsmen)
        current_armies = self.armies.get(keep_territory, 0)
        if current_armies > 13:
            return (False, f"Territory has too many units! ({current_armies}/15)\nNeed 13 or fewer to summon 2 Swordsmen.")

        # Check if territory has Haste effect
        haste_affected_territories = self.get_haste_affected_territories(owner)
        has_haste = keep_territory in haste_affected_territories

        # Spawn 2 Swordsmen units using multi-garrison system
        # Get owner's garrison
        if keep_territory not in self.territory_garrisons:
            self.territory_garrisons[keep_territory] = {}
        if owner not in self.territory_garrisons[keep_territory]:
            self.territory_garrisons[keep_territory][owner] = {
                'unmoved': 0,
                'moved': 0,
                'units': []
            }

        garrison = self.territory_garrisons[keep_territory][owner]
        swordsmen_spawned = 0

        for i in range(2):
            # Check if we've hit the army limit (total across all garrisons)
            total_armies = sum(len(g['units']) for g in self.territory_garrisons.get(keep_territory, {}).values())
            if total_armies >= self.MAX_ARMIES_PER_TERRITORY:
                break

            # Find next available ID within this garrison
            existing_ids = [u['id'] for u in garrison['units']]
            next_id = 0
            while next_id in existing_ids:
                next_id += 1

            # Add swordsman unit to garrison (Valorian's Valor - spawned fresh, no XP)
            # Haste makes units ready immediately, otherwise they're moved (exhausted)
            # Phase 2E: Use _make_unit() factory for consistent unit dict creation
            garrison['units'].append(self._make_unit('Swordsman', next_id, 'ready' if has_haste else 'moved'))

            # Update garrison counters
            if has_haste:
                garrison['unmoved'] += 1
            else:
                garrison['moved'] += 1

            swordsmen_spawned += 1

        # Sync to legacy system
        self.sync_legacy_garrison_data(keep_territory)

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Reinforce summoned {swordsmen_spawned} Swordsmen in {keep_territory}{haste_msg}")

        return (True, None)

    def execute_aggressive_diplomacy(self, target_territory, owner):
        """
        Execute Aggressive Diplomacy ability - destroy armies and buildings, claim territory.

        Args:
            target_territory: Territory name to target
            owner: Player index who owns Halon Nextroy

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Validate territory is NOT owned by player (must be neutral or enemy)
        current_owner = self.territory_owners.get(target_territory, -1)
        if current_owner == owner:
            return (False, "Cannot target your own territory!")

        # Check if territory is protected by Defiance
        if self.is_territory_protected_by_defiance(target_territory, owner):
            return (False, "Territory is protected by Defiance!")

        # Check army count (must have 1 or fewer)
        current_armies = self.armies.get(target_territory, 0)
        if current_armies > 1:
            return (False, f"Territory has too many armies! ({current_armies})\nNeed 1 or fewer to target.")

        # Check if territory has a Keep
        if target_territory in self.buildings:
            for plot_index, building_type in self.buildings[target_territory].items():
                if building_type == 'Keep':
                    return (False, "Cannot target territories with Keeps!")

        # Check if Seledra's Champion of the People is active for Nextroy's owner
        has_seledra = self.player_has_seledra(owner)

        # Track what gets destroyed vs saved
        farms_destroyed = 0
        mines_destroyed = 0
        farms_saved = 0
        mines_saved = 0
        armies_destroyed = current_armies

        # Destroy all armies from all garrisons
        if target_territory in self.territory_garrisons:
            del self.territory_garrisons[target_territory]

        # Sync to legacy system (which will set legacy counts to 0)
        self.sync_legacy_garrison_data(target_territory)

        # Handle buildings
        if target_territory in self.buildings:
            plots_to_remove = []
            for plot_index, building_type in list(self.buildings[target_territory].items()):
                if building_type == 'Farm':
                    if has_seledra:
                        farms_saved += 1
                    else:
                        farms_destroyed += 1
                        plots_to_remove.append(plot_index)
                elif building_type == 'Mine':
                    if has_seledra:
                        mines_saved += 1
                    else:
                        mines_destroyed += 1
                        plots_to_remove.append(plot_index)
                else:
                    # Destroy all other buildings (Barracks, Fortifications, etc.)
                    plots_to_remove.append(plot_index)

            # Remove destroyed buildings
            for plot_index in plots_to_remove:
                del self.buildings[target_territory][plot_index]

            # Clean up empty buildings dict
            if not self.buildings[target_territory]:
                del self.buildings[target_territory]

        # Claim the territory
        self.territory_owners[target_territory] = owner

        # Build message
        message = f"Player {owner + 1}: Aggressive Diplomacy conquers {target_territory}!"
        self.add_message(message)

        if armies_destroyed > 0:
            self.add_message(f"  {armies_destroyed} army unit(s) destroyed.")

        # Raze the Countryside: Award gold for destroyed Farms
        if farms_destroyed > 0:
            gold_bonus = self.player_farm_destruction_gold_bonus[owner]
            if gold_bonus > 0:
                total_gold = gold_bonus * farms_destroyed
                self.player_gold[owner] += total_gold
                self.add_message(f"  Raze the Countryside! Gained {total_gold} Gold from destroying {farms_destroyed} Farm(s)!")

        if farms_destroyed > 0 or mines_destroyed > 0:
            destroyed_msg = []
            if farms_destroyed > 0:
                destroyed_msg.append(f"{farms_destroyed} Farm(s)")
            if mines_destroyed > 0:
                destroyed_msg.append(f"{mines_destroyed} Mine(s)")
            self.add_message(f"  {' and '.join(destroyed_msg)} destroyed.")

        if farms_saved > 0 or mines_saved > 0:
            saved_msg = []
            if farms_saved > 0:
                saved_msg.append(f"{farms_saved} Farm(s)")
            if mines_saved > 0:
                saved_msg.append(f"{mines_saved} Mine(s)")
            self.add_message(f"  {' and '.join(saved_msg)} saved by Champion of the People!")

        return (True, None)

    # Phase 2F: Income calculation dedup — this is now the single source of truth for
    # territory income calculation. calculate_player_income() delegates to this method.
    # When player_index is provided, hero bonuses (Narn, Nithieln) are also applied.
    # When called without player_index (e.g., from Levy or AI), only base + tech bonuses apply.
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
                        # Supply and Demand: Squares multiply by 2.5× instead of 1.5×
                        if building_type == 'Square' and owner >= 0 and 'tech_0_3' in self.player_tech_researched.get(owner, set()):
                            multiplier = 2.5
                        else:
                            multiplier = value
                except (KeyError, TypeError) as e:
                    self.log_error(f"Invalid building data for {building_type} in {territory}", e)
                    continue

        # Apply formula: (base + bonuses) * multiplier
        territory_income = int((base_income + building_bonus) * multiplier)
        return territory_income

    def execute_levy(self, target_territory, owner):
        """
        Execute Levy ability - collect immediate income from target territory.

        Args:
            target_territory: Territory name to levy
            owner: Player index who owns Halon Nextroy

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Validate territory is owned by player
        current_owner = self.territory_owners.get(target_territory, -1)
        if current_owner != owner:
            return (False, "You can only levy your own territories!")

        # Calculate territory income
        income = self.calculate_territory_income(target_territory)

        # Add income to player's gold
        self.player_gold[owner] += income

        # Add message to action log
        self.add_message(f"Player {owner + 1}: Levy collected {income} Gold from {target_territory}!")

        return (True, None)

    def execute_extort_populace(self, owner):
        """
        Execute Extort Populace ability - gain 50 Gold for each Keep or Castle owned.

        Args:
            owner: Player index who owns Erec Silvyr

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Count Keeps and Castles owned by the player
        keeps_and_castles = 0

        for territory, buildings in self.buildings.items():
            # Check if territory is owned by the player
            if self.territory_owners.get(territory, -1) != owner:
                continue

            # Count Keeps and Castles in this territory
            for plot_index, building_type in buildings.items():
                if building_type in ['Keep', 'Castle']:
                    keeps_and_castles += 1

        # Calculate gold gained (50 per Keep/Castle)
        gold_gained = keeps_and_castles * 50

        # Add gold to player
        self.player_gold[owner] += gold_gained

        # Add message to action log
        self.add_message(f"Player {owner + 1}: Extort Populace gained {gold_gained} Gold from {keeps_and_castles} Keep(s)/Castle(s)!")

        return (True, None)

    def execute_decisive_strike(self, target_territory, owner):
        """
        Execute Decisive Strike ability - remove half of the armies in target enemy territory.

        Args:
            target_territory: Territory name to target
            owner: Player index who owns Neil Hévilneu

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Validate territory exists
        if target_territory not in self.territory_owners:
            return (False, "Invalid territory!")

        # Get territory owner
        territory_owner = self.territory_owners.get(target_territory, -1)

        # Check that it's an enemy territory (not owned by current player)
        if territory_owner == owner:
            return (False, "Cannot target your own territory!")

        # Check that it's not neutral
        if territory_owner == -1:
            return (False, "Cannot target neutral territory!")

        # Check if territory is protected by Defiance
        if self.is_territory_protected_by_defiance(target_territory, owner):
            return (False, "Territory is protected by Defiance!")

        # Check that territory has at least 2 armies
        army_count = self.armies.get(target_territory, 0)
        if army_count < 2:
            return (False, f"Territory must have at least 2 units! (has {army_count})")

        # Calculate how many armies to remove (half, rounded down)
        armies_to_remove = army_count // 2

        # Get all units from all garrisons in the territory
        if target_territory not in self.territory_garrisons:
            return (False, "No armies found in territory!")

        all_garrisons = self.territory_garrisons[target_territory]
        if not all_garrisons:
            return (False, "No armies found in territory!")

        # Collect all units from all garrisons
        all_units = []
        garrison_owners = []
        for garrison_owner, garrison in all_garrisons.items():
            for unit in garrison['units']:
                all_units.append((garrison_owner, unit))
                garrison_owners.append(garrison_owner)

        if len(all_units) < armies_to_remove:
            return (False, "Not enough units in territory!")

        # Randomly select units to remove from all garrisons combined
        import random
        units_to_remove = random.sample(all_units, armies_to_remove)

        # Remove the selected units from their respective garrisons
        for garrison_owner, unit in units_to_remove:
            garrison = all_garrisons[garrison_owner]
            garrison['units'].remove(unit)

            # Update garrison counters based on unit status
            if unit['status'] == 'ready':
                garrison['unmoved'] = max(0, garrison['unmoved'] - 1)
            else:
                garrison['moved'] = max(0, garrison['moved'] - 1)

        # Sync to legacy system
        self.sync_legacy_garrison_data(target_territory)

        # Add message to action log
        self.add_message(f"Player {owner + 1}: Decisive Strike removed {armies_to_remove} armies from {target_territory}!")

        return (True, None)

    def execute_valorous_charge(self, target_territory, owner):
        """
        Execute Valorous Charge ability - move up to 15 units from Hévilneu's Keep to target allied territory.

        Args:
            target_territory: Territory name to move units to
            owner: Player index who owns Neil Hévilneu

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Find hero's Keep territory (works for Neil Hévilneu or Serthus Diarcess)
        if owner not in self.heroes:
            return (False, "Hero not found!")

        # Check for either Neil Hévilneu or Serthus Diarcess (both have Valorous Charge)
        hero_name = None
        if 'Neil Hévilneu' in self.heroes[owner]:
            hero_name = 'Neil Hévilneu'
        elif 'Serthus Diarcess' in self.heroes[owner]:
            hero_name = 'Serthus Diarcess'
        else:
            return (False, "No hero with Valorous Charge found!")

        hero_data = self.heroes[owner][hero_name]
        keep_territory = hero_data['keep_territory']

        # Validate target territory is owned by player
        if self.territory_owners.get(target_territory, -1) != owner:
            return (False, "Can only target your own territories!")

        # Can't target the same territory
        if target_territory == keep_territory:
            return (False, "Cannot target hero's own Keep territory!")

        # Check if origin territory has owner's garrison with units
        if keep_territory not in self.territory_garrisons or owner not in self.territory_garrisons[keep_territory]:
            return (False, f"No units in {keep_territory} to move!")

        origin_garrison = self.territory_garrisons[keep_territory][owner]
        origin_units = origin_garrison['units']

        if not origin_units:
            return (False, f"No units in {keep_territory} to move!")

        # Calculate how many units can be moved
        origin_count = len(origin_units)

        # Calculate total units in target territory across all garrisons
        target_count = sum(len(g['units']) for g in self.territory_garrisons.get(target_territory, {}).values())

        # Maximum we can move is 15 total
        max_can_move = min(15, origin_count)

        # But we must respect target territory limit (15 units max)
        space_available = self.MAX_ARMIES_PER_TERRITORY - target_count

        if space_available <= 0:
            return (False, f"{target_territory} is full! ({target_count}/15)")

        # Actual number to move is the minimum of these constraints
        units_to_move = min(max_can_move, space_available)

        if units_to_move == 0:
            return (False, "No units can be moved!")

        # Check if target has Haste effect
        haste_affected_territories = self.get_haste_affected_territories(owner)
        has_haste = target_territory in haste_affected_territories

        # Randomly select units to move from owner's garrison only
        import random
        units_to_transfer = random.sample(origin_units, units_to_move)

        # Get or create owner's garrison in target territory
        if target_territory not in self.territory_garrisons:
            self.territory_garrisons[target_territory] = {}
        if owner not in self.territory_garrisons[target_territory]:
            self.territory_garrisons[target_territory][owner] = {
                'unmoved': 0,
                'moved': 0,
                'units': []
            }

        target_garrison = self.territory_garrisons[target_territory][owner]

        # Move units from origin garrison to target garrison
        for unit in units_to_transfer:
            # Remove from origin garrison
            origin_units.remove(unit)

            # Update origin garrison counters
            if unit['status'] == 'ready':
                origin_garrison['unmoved'] = max(0, origin_garrison['unmoved'] - 1)
            else:
                origin_garrison['moved'] = max(0, origin_garrison['moved'] - 1)

            # Find next available ID in target garrison
            existing_ids = [u['id'] for u in target_garrison['units']]
            next_id = 0
            while next_id in existing_ids:
                next_id += 1

            # Add to target garrison with new ID (Caedmon's Curse - preserve XP from stolen unit)
            # Units are marked as moved unless target has Haste
            target_garrison['units'].append({
                'id': next_id,
                'status': 'ready' if has_haste else 'moved',
                'order': None,
                'type': unit['type'],
                'xp': unit.get('xp', 0),
                'level': unit.get('level', 0)
            })

            # Update target garrison counters
            if has_haste:
                target_garrison['unmoved'] += 1
            else:
                target_garrison['moved'] += 1

        # Sync both territories to legacy system
        self.sync_legacy_garrison_data(keep_territory)
        self.sync_legacy_garrison_data(target_territory)

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Valorous Charge moved {units_to_move} units from {keep_territory} to {target_territory}{haste_msg}")

        return (True, None)

    def execute_royal_charisma(self, target_territory, owner):
        """
        Execute Royal Charisma ability - steal up to 5 units from target enemy territory
        and move them to Narn's Keep territory (respects 15 unit limit).

        Args:
            target_territory: Territory to steal units from (must be enemy-owned)
            owner: Player index who owns Aidam Narn

        Returns:
            tuple: (success: bool, error_msg: str or None)
        """
        # Validate territory exists and is enemy-owned
        if target_territory not in self.territory_owners:
            return (False, "Invalid territory!")

        territory_owner = self.territory_owners.get(target_territory, -1)

        # Check that it's an enemy territory
        if territory_owner == owner:
            return (False, "Cannot target your own territory!")

        # Check that it's not neutral
        if territory_owner == -1:
            return (False, "Cannot target neutral territory!")

        # Check if territory is protected by Defiance
        if self.is_territory_protected_by_defiance(target_territory, owner):
            return (False, "Territory is protected by Defiance!")

        # Get Narn's Keep territory
        if owner not in self.heroes or 'Aidam Narn' not in self.heroes[owner]:
            return (False, "Aidam Narn not found!")

        narn_data = self.heroes[owner]['Aidam Narn']
        narn_keep_territory = narn_data.get('keep_territory')

        if not narn_keep_territory:
            return (False, "Narn's Keep territory not found!")

        # Check if Narn's Keep territory still belongs to the player
        if self.territory_owners.get(narn_keep_territory, -1) != owner:
            return (False, "You no longer own Narn's Keep territory!")

        # Get current unit count in Narn's Keep territory
        narn_keep_units = self.armies.get(narn_keep_territory, 0)

        # Check if Narn's Keep already has 15 units (cannot use ability)
        if narn_keep_units >= 15:
            return (False, "Narn's Keep already has 15 units! Cannot use Royal Charisma.")

        # Calculate how many units can be stolen (respects 15 unit limit)
        max_units_to_steal = min(5, 15 - narn_keep_units)

        # Get all units from all garrisons in target territory
        if target_territory not in self.territory_garrisons:
            return (False, "Target territory has no units!")

        all_garrisons = self.territory_garrisons[target_territory]
        if not all_garrisons:
            return (False, "Target territory has no units!")

        # Collect all units from all garrisons
        all_units = []
        for garrison_owner, garrison in all_garrisons.items():
            for unit in garrison['units']:
                all_units.append((garrison_owner, unit))

        if len(all_units) == 0:
            return (False, "Target territory has no units!")

        # Calculate actual number of units to steal (minimum of max allowed and available)
        units_to_steal = min(max_units_to_steal, len(all_units))

        # Randomly select units to steal from all garrisons combined
        import random
        stolen_units = random.sample(all_units, units_to_steal)

        # Remove stolen units from their respective garrisons
        for garrison_owner, unit in stolen_units:
            garrison = all_garrisons[garrison_owner]
            garrison['units'].remove(unit)

            # Update garrison counters
            if unit['status'] == 'ready':
                garrison['unmoved'] = max(0, garrison['unmoved'] - 1)
            else:
                garrison['moved'] = max(0, garrison['moved'] - 1)

        # Check if Narn's Keep has Haste effect
        haste_affected_territories = self.get_haste_affected_territories(owner)
        has_haste = narn_keep_territory in haste_affected_territories

        # Get or create owner's garrison in Narn's Keep territory
        if narn_keep_territory not in self.territory_garrisons:
            self.territory_garrisons[narn_keep_territory] = {}
        if owner not in self.territory_garrisons[narn_keep_territory]:
            self.territory_garrisons[narn_keep_territory][owner] = {
                'unmoved': 0,
                'moved': 0,
                'units': []
            }

        narn_garrison = self.territory_garrisons[narn_keep_territory][owner]

        # Add stolen units to owner's garrison in Narn's Keep
        for garrison_owner, unit in stolen_units:
            # Find next available ID in owner's garrison
            existing_ids = [u['id'] for u in narn_garrison['units']]
            next_id = 0
            while next_id in existing_ids:
                next_id += 1

            # Add to owner's garrison with new ID (Narn's Dominion - preserve XP from stolen unit)
            # Units are marked as moved unless Narn's Keep has Haste
            narn_garrison['units'].append({
                'id': next_id,
                'status': 'ready' if has_haste else 'moved',
                'order': None,
                'type': unit['type'],
                'xp': unit.get('xp', 0),
                'level': unit.get('level', 0)
            })

            # Update garrison counters
            if has_haste:
                narn_garrison['unmoved'] += 1
            else:
                narn_garrison['moved'] += 1

        # Sync both territories to legacy system
        self.sync_legacy_garrison_data(target_territory)
        self.sync_legacy_garrison_data(narn_keep_territory)

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Royal Charisma stole {units_to_steal} units from {target_territory} to {narn_keep_territory}{haste_msg}!")

        return (True, None)

    def execute_regicide(self, target_territory, owner):
        """
        Execute Regicide ability - instantly kill a hero in target enemy Keep.

        Args:
            target_territory: Territory with Keep to target (must be enemy-owned)
            owner: Player index who owns Aidam Narn

        Returns:
            tuple: (success: bool, error_msg: str or None)
        """
        # Validate territory exists and is enemy-owned
        if target_territory not in self.territory_owners:
            return (False, "Invalid territory!")

        territory_owner = self.territory_owners.get(target_territory, -1)

        # Check that it's an enemy territory
        if territory_owner == owner:
            return (False, "Cannot target your own territory!")

        # Check that it's not neutral
        if territory_owner == -1:
            return (False, "Cannot target neutral territory!")

        # Check if territory is protected by Defiance
        if self.is_territory_protected_by_defiance(target_territory, owner):
            return (False, "Territory is protected by Defiance!")

        # Check if territory has a Keep
        has_keep = False
        keep_plot_index = None
        if target_territory in self.buildings:
            for plot_idx, building_type in self.buildings[target_territory].items():
                if building_type == 'Keep':
                    has_keep = True
                    keep_plot_index = plot_idx
                    break

        if not has_keep:
            return (False, "Target territory must have a Keep!")

        # Check if there's a hero in this Keep
        hero_found = None
        if territory_owner in self.heroes:
            for hero_type, hero_data in self.heroes[territory_owner].items():
                if (hero_data['keep_territory'] == target_territory and
                    hero_data['keep_plot'] == keep_plot_index):
                    hero_found = hero_type
                    break

        # Execute the ability (always succeeds even if no hero found)
        if hero_found:
            # Kill the hero
            del self.heroes[territory_owner][hero_found]
            self.hero_ownership[territory_owner].discard(hero_found)
            self.add_message(f"Player {owner + 1}: Regicide killed {hero_found} in {target_territory}!")
            self.add_message(f"Player {territory_owner + 1}: {hero_found} has died!")
        else:
            # No hero found - ability is wasted
            self.add_message(f"Player {owner + 1}: Regicide targeted {target_territory}, but no hero was found!")

        return (True, None)

    def player_has_seledra(self, player_index):
        """
        Check if a player has Seledra Rennervail active.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Seledra active
        """
        if player_index not in self.heroes:
            return False
        return 'Seledra Rennervail' in self.heroes[player_index]

    def player_has_asford(self, player_index):
        """
        Check if a player has Vearen Asford active.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Vearen Asford active
        """
        if player_index not in self.heroes:
            return False
        return 'Vearen Asford' in self.heroes[player_index]

    def player_has_nextroy(self, player_index):
        """
        Check if a player has Halon Nextroy active.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Halon Nextroy active
        """
        if player_index not in self.heroes:
            return False
        return 'Halon Nextroy' in self.heroes[player_index]

    def get_defiance_protected_territories(self, player_index):
        """
        Get territories protected by Seledra Rennervail's Defiance ability.

        Defiance protects territories that are:
        1. Owned by the player
        2. Adjacent to the territory containing Seledra's Keep

        Args:
            player_index: Player index to check

        Returns:
            set: Set of territory names protected by Defiance
        """
        protected_territories = set()

        # Check if player has Seledra Rennervail
        if player_index not in self.heroes:
            return protected_territories

        if 'Seledra Rennervail' not in self.heroes[player_index]:
            return protected_territories

        # Get Seledra's Keep territory
        seledra_data = self.heroes[player_index]['Seledra Rennervail']
        keep_territory = seledra_data['keep_territory']

        # Protect the Keep's territory itself (if owned by this player)
        if self.territory_owners.get(keep_territory) == player_index:
            protected_territories.add(keep_territory)

        # Get all territories adjacent to Seledra's Keep territory
        import map_data
        adjacent_territories = map_data.get_neighbors(keep_territory)

        # Only include territories owned by this player
        for territory in adjacent_territories:
            if self.territory_owners.get(territory) == player_index:
                protected_territories.add(territory)

        return protected_territories

    def is_territory_protected_by_defiance(self, territory, target_player):
        """
        Check if a territory is protected by Defiance from a specific player.

        Args:
            territory: Territory name to check
            target_player: Player trying to use ability on this territory

        Returns:
            bool: True if territory is protected from this player
        """
        # Check all players except the target player
        for player_index in range(self.num_players):
            if player_index != target_player:
                protected = self.get_defiance_protected_territories(player_index)
                if territory in protected:
                    return True
        return False

    def get_haste_affected_territories(self, player_index):
        """
        Get territories affected by Vearen Asford's Haste ability.

        Haste affects territories that are:
        1. Owned by the player
        2. Either the territory containing Asford's Keep OR adjacent to it

        Args:
            player_index: Player index to check

        Returns:
            set: Set of territory names affected by Haste
        """
        affected_territories = set()

        # Check if player has Vearen Asford
        if player_index not in self.heroes:
            return affected_territories

        if 'Vearen Asford' not in self.heroes[player_index]:
            return affected_territories

        # Get Asford's Keep territory
        asford_data = self.heroes[player_index]['Vearen Asford']
        keep_territory = asford_data['keep_territory']

        # Affect the Keep's territory itself (if owned by this player)
        if self.territory_owners.get(keep_territory) == player_index:
            affected_territories.add(keep_territory)

        # Get all territories adjacent to Asford's Keep territory
        import map_data
        adjacent_territories = map_data.get_neighbors(keep_territory)

        # Only include territories owned by this player
        for territory in adjacent_territories:
            if self.territory_owners.get(territory) == player_index:
                affected_territories.add(territory)

        return affected_territories

    def player_has_darius_brennhen(self, player_index):
        """
        Check if a player has Darius Brennhen or Regnus Aevencourne trained.
        Both heroes share the same abilities (Reinforce, Safe Haven, Scavenge the Fallen).

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Darius Brennhen or Regnus Aevencourne
        """
        if player_index not in self.heroes:
            return False
        return 'Darius Brennhen' in self.heroes[player_index] or 'Regnus Aevencourne' in self.heroes[player_index]

    def player_has_silvyr(self, player_index):
        """
        Check if a player has Erec Silvyr trained.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Erec Silvyr
        """
        if player_index not in self.heroes:
            return False
        return 'Erec Silvyr' in self.heroes[player_index]

    def player_has_hevilneu(self, player_index):
        """
        Check if a player has Neil Hévilneu or Serthus Diarcess trained.
        Both heroes share the Vanquish the Enemy passive ability.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Neil Hévilneu or Serthus Diarcess
        """
        if player_index not in self.heroes:
            return False
        return 'Neil Hévilneu' in self.heroes[player_index] or 'Serthus Diarcess' in self.heroes[player_index]

    def player_has_nithieln(self, player_index):
        """
        Check if a player has Evain Nithieln trained.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Evain Nithieln
        """
        if player_index not in self.heroes:
            return False
        return 'Evain Nithieln' in self.heroes[player_index]

    def player_has_narn(self, player_index):
        """
        Check if a player has Aidam Narn trained.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Aidam Narn
        """
        if player_index not in self.heroes:
            return False
        return 'Aidam Narn' in self.heroes[player_index]

    def get_safe_haven_territories(self, player_index):
        """
        Get territories protected by Darius Brennhen's Safe Haven ability.

        Safe Haven protects territories that are:
        1. Owned by the player
        2. Adjacent to Brennhen's Keep territory

        Args:
            player_index: Player index to check

        Returns:
            set: Set of territory names protected by Safe Haven
        """
        protected_territories = set()

        # Check if player has Darius Brennhen or Regnus Aevencourne
        if not self.player_has_darius_brennhen(player_index):
            return protected_territories

        # Get hero's Keep territory (check both Brennhen and Regnus)
        if 'Darius Brennhen' in self.heroes[player_index]:
            brennhen_data = self.heroes[player_index]['Darius Brennhen']
        else:
            brennhen_data = self.heroes[player_index]['Regnus Aevencourne']
        keep_territory = brennhen_data['keep_territory']

        # Get all territories adjacent to Brennhen's Keep territory
        import map_data
        adjacent_territories = map_data.get_neighbors(keep_territory)

        # Only include territories owned by this player
        for territory in adjacent_territories:
            if self.territory_owners.get(territory) == player_index:
                protected_territories.add(territory)

        return protected_territories

    def _decrement_hero_cooldowns_and_silence(self):
        """
        Decrement hero ability cooldowns and silence status at the start of current player's turn.

        Called in _advance_to_next_player() after switching to the new current player.
        """
        current_player = self.current_player

        # Decrement ability cooldowns for current player's heroes
        if current_player in self.hero_ability_cooldowns:
            for hero_name in list(self.hero_ability_cooldowns[current_player].keys()):
                for ability_name in list(self.hero_ability_cooldowns[current_player][hero_name].keys()):
                    if self.hero_ability_cooldowns[current_player][hero_name][ability_name] > 0:
                        self.hero_ability_cooldowns[current_player][hero_name][ability_name] -= 1

                        # If cooldown reaches 0, notify player
                        if self.hero_ability_cooldowns[current_player][hero_name][ability_name] == 0:
                            self.add_message(f"Player {current_player + 1}: {hero_name}'s {ability_name} is ready!")

                        # Clean up zero cooldowns
                        if self.hero_ability_cooldowns[current_player][hero_name][ability_name] == 0:
                            del self.hero_ability_cooldowns[current_player][hero_name][ability_name]

                # Clean up empty hero cooldown dicts
                if not self.hero_ability_cooldowns[current_player][hero_name]:
                    del self.hero_ability_cooldowns[current_player][hero_name]

        # Decrement silence status for current player
        if current_player in self.hero_silence_status:
            if self.hero_silence_status[current_player] > 0:
                self.hero_silence_status[current_player] -= 1

                # If silence expires, notify player and clear activation time
                if self.hero_silence_status[current_player] == 0:
                    self.add_message(f"Player {current_player + 1}: Your heroes are no longer silenced!")

                    # Check if all players are no longer silenced
                    all_clear = all(self.hero_silence_status.get(i, 0) == 0 for i in range(self.num_players))
                    if all_clear:
                        self.silence_activation_time = None

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

                        # Find next available ID
                        existing_ids = [u['id'] for u in self.army_units[territory]]
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

                        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
                        self.add_message(f"Player {owner + 1}: {unit_type} trained in {territory}{haste_msg}")

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

        # Return completed units for network synchronization
        return completed_units

    def check_victory(self):
        """
        Check if any player has won based on the selected victory condition.

        Returns:
            int: Winner player index, or -1 if no winner yet
        """
        # Count territories per player
        territory_counts = [0] * self.num_players
        for owner in self.territory_owners.values():
            if owner >= 0:
                territory_counts[owner] += 1

        # DEBUG: Print territory counts
        logger.debug(f"check_victory: Victory Condition: {self.victory_condition}")
        logger.debug(f"check_victory: Territory counts: {territory_counts}")

        # Route to appropriate victory check based on victory_condition
        if self.victory_condition == "Domination (45+)":
            return self._check_domination_victory(territory_counts)
        elif self.victory_condition == "Capital Assault":
            return self._check_capital_assault_victory(territory_counts)
        elif self.victory_condition == "Total Conquest":
            return self._check_total_conquest_victory(territory_counts)

        # Fallback to Domination if unknown victory condition
        logger.warning(f"Unknown victory condition '{self.victory_condition}', defaulting to Domination")
        return self._check_domination_victory(territory_counts)

    def _check_domination_victory(self, territory_counts):
        """
        Check Domination victory (45+ territories).

        Works team-wise: aggregates territory counts for all players on the same team.
        A team wins when their combined territory count reaches the threshold.

        Args:
            territory_counts (list): Territory count per player

        Returns:
            int: Winner player index (representative of winning team), or -1 if no winner
        """
        victory_threshold = self.victory_territory_threshold

        # Check if teams are active - aggregate by team if so
        if hasattr(self, 'player_teams') and self.player_teams:
            # Build team territory counts
            team_counts = {}  # team_id -> total territories
            team_members = {}  # team_id -> list of player indices

            for player_id, count in enumerate(territory_counts):
                team_id = self.player_teams[player_id]
                if team_id not in team_counts:
                    team_counts[team_id] = 0
                    team_members[team_id] = []
                team_counts[team_id] += count
                team_members[team_id].append(player_id)

            # Check if any team meets threshold
            for team_id, total_count in team_counts.items():
                logger.debug(f"Team {team_id + 1}: {total_count} territories (need {victory_threshold})")
                if total_count >= victory_threshold:
                    # Use first active team member as winner representative
                    winner = team_members[team_id][0]
                    for member in team_members[team_id]:
                        if territory_counts[member] > 0:
                            winner = member
                            break

                    logger.info(f"DOMINATION TEAM VICTORY for Team {team_id + 1}!")
                    self.winner = winner
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   TEAM {team_id + 1} WINS!")
                    self.add_message(f"   ({total_count} territories)")
                    self.add_message(f"============================")
                    return winner
        else:
            # No teams - check per-player (original behavior)
            for i, count in enumerate(territory_counts):
                logger.debug(f"Player {i}: {count} territories (need {victory_threshold})")
                if count >= victory_threshold:
                    logger.info(f"DOMINATION VICTORY for Player {i}!")
                    self.winner = i
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   PLAYER {i + 1} WINS!")
                    self.add_message(f"   ({count} territories)")
                    self.add_message(f"============================")
                    return i

        logger.debug(f"No domination victory yet")
        return -1

    def _check_capital_assault_victory(self, territory_counts):
        """
        Check Capital Assault victory (last team/player standing).

        In Capital Assault mode, players are eliminated when their capital is captured.
        Victory is achieved when only one team (or player, if no teams) remains.

        Args:
            territory_counts (list): Territory count per player

        Returns:
            int: Winner player index, or -1 if no winner
        """
        # Get active players (those with at least one territory)
        active_players = [i for i, count in enumerate(territory_counts) if count > 0]

        logger.debug(f"Active players: {active_players}")

        # Check if only one team remains (team-based victory)
        if hasattr(self, 'player_teams') and self.player_teams:
            active_teams = set(self.player_teams[i] for i in active_players)
            logger.debug(f"Active teams: {active_teams}")

            if len(active_teams) == 1:
                # All remaining players are on same team - team wins
                winner = active_players[0]  # Use first active player as winner representative
                self.winner = winner
                self.phase = 'ended'
                team_num = self.player_teams[winner]
                self.add_message(f"")
                self.add_message(f"============================")
                self.add_message(f"   TEAM {team_num + 1} WINS!")
                self.add_message(f"   (Last team standing)")
                self.add_message(f"============================")
                logger.info(f"CAPITAL ASSAULT TEAM VICTORY for Team {team_num + 1}!")
                return winner
        else:
            # No teams - check for last player standing
            if len(active_players) == 1:
                winner = active_players[0]
                self.winner = winner
                self.phase = 'ended'
                self.add_message(f"")
                self.add_message(f"============================")
                self.add_message(f"   PLAYER {winner + 1} WINS!")
                self.add_message(f"   (Last player standing)")
                self.add_message(f"============================")
                logger.info(f"CAPITAL ASSAULT VICTORY for Player {winner + 1}!")
                return winner

        logger.debug(f"No capital assault victory yet - {len(active_players)} players/teams remaining")
        return -1

    def _check_total_conquest_victory(self, territory_counts):
        """
        Check Total Conquest victory (all territories on the map).

        Works team-wise: aggregates territory counts for all players on the same team.
        A team wins when their combined territory count equals all territories.

        Args:
            territory_counts (list): Territory count per player

        Returns:
            int: Winner player index (representative of winning team), or -1 if no winner
        """
        total_territories = len(self.territory_owners)  # Total territories on map

        # Check if teams are active - aggregate by team if so
        if hasattr(self, 'player_teams') and self.player_teams:
            # Build team territory counts
            team_counts = {}  # team_id -> total territories
            team_members = {}  # team_id -> list of player indices

            for player_id, count in enumerate(territory_counts):
                team_id = self.player_teams[player_id]
                if team_id not in team_counts:
                    team_counts[team_id] = 0
                    team_members[team_id] = []
                team_counts[team_id] += count
                team_members[team_id].append(player_id)

            # Check if any team owns all territories
            for team_id, total_count in team_counts.items():
                logger.debug(f"Team {team_id + 1}: {total_count}/{total_territories} territories")
                if total_count == total_territories:
                    # Use first active team member as winner representative
                    winner = team_members[team_id][0]
                    for member in team_members[team_id]:
                        if territory_counts[member] > 0:
                            winner = member
                            break

                    logger.info(f"TOTAL CONQUEST TEAM VICTORY for Team {team_id + 1}!")
                    self.winner = winner
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   TEAM {team_id + 1} WINS!")
                    self.add_message(f"   (Total conquest - all territories)")
                    self.add_message(f"============================")
                    return winner
        else:
            # No teams - check per-player (original behavior)
            for i, count in enumerate(territory_counts):
                logger.debug(f"Player {i}: {count}/{total_territories} territories")
                if count == total_territories:
                    logger.info(f"TOTAL CONQUEST VICTORY for Player {i}!")
                    self.winner = i
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   PLAYER {i + 1} WINS!")
                    self.add_message(f"   (Total conquest - all territories)")
                    self.add_message(f"============================")
                    return i

        logger.debug(f"No total conquest victory yet")
        return -1

    def eliminate_player(self, player_index):
        """
        Eliminate player and neutralize their territories (Capital Assault mode).

        Called when a player's capital is captured. All territories owned by the eliminated
        player become neutral, and all units and buildings are destroyed.

        Args:
            player_index (int): Index of the player to eliminate
        """
        # Get all territories owned by eliminated player
        player_territories = [t for t, owner in self.territory_owners.items()
                             if owner == player_index]

        logger.info(f"[CAPITAL ASSAULT] Eliminating Player {player_index + 1}")
        logger.info(f"[CAPITAL ASSAULT] Neutralizing {len(player_territories)} territories")

        for territory in player_territories:
            # 1. Destroy all buildings (uses existing method line 2343-2450+)
            self.destroy_buildings(territory, player_index, new_owner=-1)

            # 2. Remove all units
            # Clear garrison system (multi-player garrison dict)
            self.territory_garrisons[territory] = {}

            # Clear army unit tracking list
            if territory in self.army_units:
                self.army_units[territory] = []

            # Clear simple army counters
            self.armies[territory] = 0
            self.armies_unmoved[territory] = 0
            self.armies_moved[territory] = 0

            # 3. Convert to neutral
            self.territory_owners[territory] = -1

            # 4. Cancel training queues
            if territory in self.training_queue:
                del self.training_queue[territory]
            if territory in self.hero_training_queue:
                del self.hero_training_queue[territory]

        # Add message log
        self.add_message(f"")
        self.add_message(f"============================")
        self.add_message(f"Player {player_index + 1} ELIMINATED!")
        self.add_message(f"Capital conquered - all territories neutralized")
        self.add_message(f"============================")
        self.add_message(f"")