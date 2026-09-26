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
# Phase 7: Data definitions and mixin imports for decomposed GameState
# R12: All data defs imported here and set as instance attrs in __init__ for consistency
from game_state.data_definitions import (
    HERO_TYPES as _HERO_TYPES,
    BUILDING_TYPES as _BUILDING_TYPES,
    BONUS_TYPES as _BONUS_TYPES,
    build_technologies
)
from game_state.garrison import GarrisonMixin
from game_state.heroes import HeroMixin
from game_state.buildings import BuildingMixin
from game_state.economy import EconomyMixin
from game_state.military import MilitaryMixin
from game_state.victory import VictoryMixin

# Public API of the game_state package
__all__ = ['GameState', 'MovementOrder', 'ArmyAnimation', 'Battle']

logger = get_logger(__name__)

class MovementOrder:
    """Represents a planned army movement order"""
    def __init__(self, from_territory, to_territory, army_count, player, unit_ids=None, intermediate_territory=None):
        self.from_territory = from_territory
        self.to_territory = to_territory
        self.army_count = army_count
        self.player = player
        self.unit_ids = unit_ids or []  # List of specific unit IDs (Phase 3)
        self.order_id = id(self)  # Unique ID for this order
        self.intermediate_territory = intermediate_territory  # For Captain 2-hop movement through allied territory

class ArmyAnimation:
    """Represents an animated army movement"""
    def __init__(self, from_territory, to_territory, army_count, player, unit_ids, composition, from_pos=None, to_pos=None, units=None, intermediate_territory=None):
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
        # Captain 2-hop movement: intermediate allied territory for bent animation path
        self.intermediate_territory = intermediate_territory

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

class GameState(GarrisonMixin, HeroMixin, BuildingMixin, EconomyMixin, MilitaryMixin, VictoryMixin):
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
    TRAINING_GROUNDS_UNIT_XP_PER_TURN = 15  # XP awarded to units in territory with Training Grounds

    # Unit type definitions (TIER 3: Multiple Unit Types)
    # 'strength': base strength multiplier (default 1.0; Captain = 0.25 — weaker than even a countered unit at 0.5)
    UNIT_TYPES = {
        'Swordsman': {
            'cost': 25,
            'letter': 'S',
            'name': 'Swordsman',
            'strength': 1.0,
            'counters': 'Pikeman',      # Swordsman > Pikeman
            'countered_by': 'Archer'    # Archer > Swordsman
        },
        'Archer': {
            'cost': 20,
            'letter': 'A',
            'name': 'Archer',
            'strength': 1.0,
            'counters': 'Swordsman',    # Archer > Swordsman
            'countered_by': 'Cavalry'   # Cavalry > Archer
        },
        'Pikeman': {
            'cost': 30,
            'letter': 'P',
            'name': 'Pikeman',
            'strength': 1.0,
            'counters': 'Cavalry',      # Pikeman > Cavalry
            'countered_by': 'Swordsman' # Swordsman > Pikeman
        },
        'Cavalry': {
            'cost': 40,
            'letter': 'C',
            'name': 'Cavalry',
            'strength': 1.0,
            'counters': 'Archer',       # Cavalry > Archer
            'countered_by': 'Pikeman'   # Pikeman > Cavalry
        },
        'Captain': {
            'cost': 75,
            'letter': 'T',
            'name': 'Captain',
            'strength': 0.25,           # Weak combatant — support unit
            'counters': None,           # No counter relationships
            'countered_by': None,
            'army_bonus': 0.12,         # +12% strength to all other units in army (non-stacking)
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
        # FPS OPT: Version counter for territory overlay cache invalidation
        # Incremented whenever territory_owners is modified (capture, elimination, etc.)
        self._territory_owners_version = 0
        # FPS OPT: Version counter for production glow sync (training queue changes)
        self._training_version = 0

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

        # Gold transfer feature
        # gold_transfer_pct is set by Game.initialize_game() from setup_config:
        # 0 = disabled, 25/50/75/100 = per-recipient percentage cap of sender's current gold.
        self.gold_transfer_pct = 0
        # Tracks (sender_index, recipient_index) pairs that have already transferred this turn
        # (sequential mode). One transfer per pair per turn. Cleared in _advance_to_next_player.
        self.gold_transfers_this_turn = set()

        # Eliminated players tracking (universal — players with 0 territories)
        # Updated by check_victory() and eliminate_player_disconnect()
        # Synced via FULL_STATE_SYNC and SIM_ROUND_COMPLETE
        self.eliminated_players = set()

        # Players eliminated specifically via multiplayer disconnect timeout
        # Used by anti-win-farming XP check (player_level.py)
        self.disconnect_eliminations = set()

        # Post-game statistics tracking (cumulative counters per player for recap screen)
        self.player_stats = {}
        for i in range(num_players):
            self.player_stats[i] = {
                'units_trained': 0, 'units_killed': 0,
                'pikemen_trained': 0, 'archers_trained': 0,
                'swordsmen_trained': 0, 'cavalry_trained': 0,
                'captains_trained': 0,
                'heroes_trained': 0, 'heroes_killed': 0,
                'gold_acquired': 0, 'gold_spent': 0,
                'gold_lost_to_taxation': 0, 'max_income_per_turn': 0,
                'economy_buildings_built': 0, 'barracks_built': 0,
                'keeps_built': 0, 'buildings_destroyed': 0,
                'xp_earned': 0,  # Player Level system: accumulated XP from gameplay actions
            }

        # Building system
        # buildings: {territory: {plot_index: building_type}} or {plot_index: None} for empty
        self.buildings = {}  # Completed buildings
        # under_construction: {territory: {plot_index: (building_type, turns_remaining, cost)}}
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
        # training_queue: {territory: {barracks_plot_index: [(unit_type, turns_remaining, cost_paid), ...]}}
        self.training_queue = {}  # Unit training queues

        # Hero system
        # Active heroes: {player_index: {hero_type: hero_data}}
        self.heroes = {i: {} for i in range(num_players)}

        # Hero training queue: {territory: {keep_plot_index: (hero_type, turns_remaining, paid_cost)}}
        # Single tuple per Keep (not list) - only ONE hero trains per Keep
        self.hero_training_queue = {}

        # Global uniqueness tracker: {player_index: set(hero_type_names)}
        # Includes both active AND training heroes
        self.hero_ownership = {i: set() for i in range(num_players)}

        # Game logger reference (set by main.py for custom/multiplayer games)
        # When active, hooks in heroes/buildings/military call record_* methods
        self.game_logger = None

        # Replay recorder reference (set by main.py for custom/multiplayer games)
        # Records full state snapshots at turn boundaries for replay playback
        self.replay_recorder = None

        # Sync logger reference (set by main.py for multiplayer games)
        # Records actions, state snapshots, and desync diffs for diagnosis
        self.sync_logger = None

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

        # Heroic Fortitude cost reduction (percentage) for Captains (75g → 50g at 33%)
        self.player_captain_cost_discount = [0] * num_players

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

        # Building costs and definitions (extracted to data_definitions.py)
        self.building_types = _BUILDING_TYPES

        # Hero type definitions (extracted to data_definitions.py)
        self.HERO_TYPES = _HERO_TYPES

        # R12: Territory bonus definitions — moved from EconomyMixin class attribute
        # to instance attribute for consistency with building_types / HERO_TYPES pattern
        self.BONUS_TYPES = _BONUS_TYPES

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

        # Last action error category — set by start_training/start_construction/etc. on failure,
        # read and cleared by main.py to show user-facing feedback (sound + floating notification).
        # Every action method resets it to None on entry, so a code left by an earlier call
        # (AI, remote order) can never be reported for a later, unrelated failure.
        # Values: None or a code from config/action_error_messages.ACTION_ERROR_MESSAGES
        # (the player-facing texts live there).
        self.last_action_error = None
        # Optional dict of values for that message's {placeholders}, e.g. {'territory': 'X'}
        self.last_action_error_args = None

        # Hero deaths not yet announced: (owner, hero_type, territory). Filled by battles and
        # Regicide (HeroMixin._record_hero_death), drained every frame by main.py, which
        # shows the local player a "hero slain" toast. Not saved (transient UI news).
        self.hero_death_events = []
        # Heroes killed by the battle currently being resolved: (owner, hero_type, territory).
        # Reset at the top of every resolve_battle(); copied into that battle's Battle Report
        # ('heroes_slain') so a defending multiplayer client — which applies BATTLE_RESOLVE
        # instead of running the battle — still learns its hero died.
        self._battle_hero_deaths = []
        
        # Winner tracking
        self.winner = -1  # -1 = no winner, 0-3 = player index

        # Victory condition settings
        # NOTE: victory_condition is set from parameter at line 217, not here
        # Options: 'Domination (45+)', 'Capital Assault', 'Total Conquest'
        # Domination threshold: ~79% of total territories (45/57 on Avareon), scales with map size
        import math
        total_territories = len(map_data.get_all_territories())
        self.victory_territory_threshold = math.ceil(total_territories * 0.79)
        
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

        # Battle Reports: transient per-defender summaries of battles they did not watch.
        # Purpose: a defender gets no feedback today beyond the map changing colour, so we
        # snapshot the outcome at resolution time and surface it on their next turn.
        # Both lists are deliberately EXCLUDED from save_manager, calculate_state_checksum()
        # and _send_full_state_sync(): this is per-viewer UI state that legitimately differs
        # between host and client, and including it would cause false desyncs.
        # last_battle_reports - reset at the top of every resolve_battle(); holds only that
        #   battle's snapshots so the network send sites can attach them to BATTLE_RESOLVE.
        # battle_report_inbox - append-only; main.py drains it every frame. This is what
        #   catches AI-resolved battles, which have no main.py call site at all.
        self.last_battle_reports = []
        self.battle_report_inbox = []

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

        # Technology tree system (extracted to data_definitions.py)
        # 3 columns x 7 rows = 21 technologies
        self.technologies = build_technologies()

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

        # Clear gold transfer tracking — each player gets a fresh set of (sender, recipient)
        # allowances at the start of their turn.
        self.gold_transfers_this_turn.clear()

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

        # DEBUG: Track who called _advance_to_next_player and the state at the time
        import traceback
        caller = traceback.extract_stack()[-2]
        logger.info(f"[TURN_DEBUG] _advance_to_next_player called from {caller.filename}:{caller.lineno} ({caller.name})")
        logger.info(f"[TURN_DEBUG]   current_player: {self.current_player} -> {(self.current_player + 1) % self.num_players}, "
                     f"turn_number: {self.turn_number}, pending_battles: {len(self.pending_battles)}")

        # Switch to next player, skipping eliminated players (0 territories)
        self.current_player = (self.current_player + 1) % self.num_players
        attempts = 0
        while (self.current_player in self.eliminated_players
               and attempts < self.num_players):
            self.current_player = (self.current_player + 1) % self.num_players
            attempts += 1
        self.selected_territory = None
        self.selected_army = None  # Clear army selection

        # Increment turn_number when a full round completes (all players acted once)
        # and record a game log snapshot for the completed round
        if self.current_player == 0 and self.phase == 'playing':
            self.turn_number += 1
            if self.game_logger:
                self.game_logger.record_round_snapshot(self.turn_number)

        # Replay recorder: snapshot after every player turn for rich replay granularity
        if self.phase == 'playing' and self.replay_recorder:
            self.replay_recorder.record_snapshot()

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

            # Award XP to units in territories with Training Grounds (+15 XP/turn)
            self._tick_training_grounds_xp()

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
            # R2 fix: player_teams is a list indexed by player_index, not a dict
            if hasattr(self, 'player_teams') and self.player_teams:
                sender_team = self.player_teams[sender_id] if sender_id < len(self.player_teams) else sender_id
                viewer_team = self.player_teams[viewer_player_id] if viewer_player_id < len(self.player_teams) else viewer_player_id
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
            # L2 fix: Include heroes, research, and building XP in checksum
            'heroes': {str(k): sorted(v.keys()) for k, v in self.heroes.items() if v},
            'tech_researched': {str(k): sorted(list(v)) for k, v in self.player_tech_researched.items() if v},
            'building_xp': {t: dict(sorted(plots.items())) for t, plots in sorted(self.building_xp.items()) if plots},
            # Sync fix: include construction/training/upgrade state to catch more divergence types
            'under_construction': {t: dict(sorted(plots.items())) for t, plots in sorted(self.under_construction.items()) if plots},
            'training_queue': {t: {str(p): q for p, q in sorted(plots.items())} for t, plots in sorted(self.training_queue.items()) if plots},
            'castle_upgrades': {t: dict(sorted(plots.items())) for t, plots in sorted(self.castle_upgrades.items()) if plots},
            'castle_upgrades_in_progress': {t: dict(sorted(plots.items())) for t, plots in sorted(self.castle_upgrades_in_progress.items()) if plots},
            # Sync logger enhancement: include garrison system (authoritative army data)
            # Strip 'order' field from unit dicts — not JSON-serializable (MovementOrder objects)
            'territory_garrisons': {
                territory: {
                    str(pid): {
                        **gdata,
                        'units': [
                            {k: (None if k == 'order' else v) for k, v in u.items()}
                            for u in gdata.get('units', [])
                        ]
                    } if 'units' in gdata else dict(gdata)
                    for pid, gdata in sorted(pgarrisons.items(), key=lambda x: str(x[0]))
                }
                for territory, pgarrisons in sorted(self.territory_garrisons.items())
            },
            # Sync logger enhancement: hero state (training, cooldowns, ownership)
            'hero_training_queue': {
                t: {str(p): list(e) for p, e in sorted(plots.items())}
                for t, plots in sorted(self.hero_training_queue.items()) if plots
            },
            'hero_ability_cooldowns': {
                str(pid): dict(cds) for pid, cds in sorted(self.hero_ability_cooldowns.items()) if cds
            },
            'hero_silence_status': {
                str(pid): status for pid, status in sorted(self.hero_silence_status.items()) if status
            },
            'hero_ownership': {
                str(pid): sorted(list(owned)) for pid, owned in sorted(self.hero_ownership.items()) if owned
            },
            # Sync logger enhancement: elimination tracking
            'eliminated_players': sorted(list(self.eliminated_players)),
            'disconnect_eliminations': sorted(list(self.disconnect_eliminations)),
            # Sync logger enhancement: transient hero ability state
            'embargo_blocked_players': list(self.embargo_blocked_players),
            'player_master_negotiator_active': list(self.player_master_negotiator_active),
            # Sync logger enhancement: tech effect arrays (derived from researched techs)
            'tech_effects': {
                'royal_decree_discount': list(self.player_royal_decree_discount),
                'training_cost_discount': list(self.player_training_cost_discount),
                'cavalry_cost_discount': list(self.player_cavalry_cost_discount),
                'captain_cost_discount': list(self.player_captain_cost_discount),
                'archer_keep_strength_bonus': list(self.player_archer_keep_strength_bonus),
                'farm_destruction_gold_bonus': list(self.player_farm_destruction_gold_bonus),
                'cavalry_strength_bonus': list(self.player_cavalry_strength_bonus),
                'divide_conquer_bonus': list(self.player_divide_conquer_bonus),
                'barracks_cost_discount': list(self.player_barracks_cost_discount),
                'barracks_full_refund': list(self.player_barracks_full_refund),
            },
            # Note: We don't include chat, messages, or UI state
        }

        # Serialize to JSON and calculate hash
        state_json = json.dumps(critical_state, sort_keys=True)
        checksum = hashlib.md5(state_json.encode()).hexdigest()

        return checksum

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
        self._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
        self.invalidate_income_cache()  # FPS OPT: Ownership affects income
        self.invalidate_army_count_cache()  # FPS OPT: Army counts change
        self.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses
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
        # DEBUG: Log when timer actually fires
        remaining = self.get_remaining_planning_time()
        if remaining is not None and remaining <= 0:
            logger.info(f"[TURN_DEBUG] Planning timer expired! player={self.current_player}, turn_phase={self.turn_phase}, "
                        f"pending_battles={len(self.pending_battles)}, ready_to_advance={self.ready_to_advance_turn}")

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

