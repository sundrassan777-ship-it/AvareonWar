"""
AI Player Module
Main controller for AI opponent behavior in War of Avareon.

This module provides the AIPlayer class which orchestrates all AI decision-making
and action execution. It integrates with the strategic, economic, military, and
hero management subsystems to make intelligent decisions based on game state.

Architecture:
    AIPlayer (this file) - Main orchestration
    ├── StrategyEvaluator (ai_strategy.py) - Territory evaluation, threat detection
    ├── EconomyManager (ai_economy.py) - Building and tech decisions
    ├── MilitaryCommander (ai_military.py) - Combat and movement decisions
    └── HeroManager (ai_hero.py) - Hero training and abilities

Usage:
    ai_player = AIPlayer(player_index=1, difficulty=2)  # Hard difficulty
    ai_player.execute_turn(game_state)
"""

import threading
import time
import random
from threading import RLock, Lock, Event  # RLock for nested locking, Lock for turn flag, Event for animation sync
from concurrent.futures import ThreadPoolExecutor  # H6: Reuse thread pool instead of creating new Thread per turn

from utils.logger import get_logger
logger = get_logger(__name__)


class TurnCache:
    """
    Per-turn cache of commonly recomputed values.
    Built once at start of _plan_turn_actions() and passed to all subsystems.
    Values are immutable during planning (game state isn't mutated during AI planning).
    """
    __slots__ = ('territory_count', 'owned_territories', 'territory_armies',
                 'player_income', 'player_army_count', 'player_has_keep',
                 'threats')

    def __init__(self, game_state, player_index):
        # Owned territories list and count
        self.owned_territories = [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]
        self.territory_count = len(self.owned_territories)

        # Pre-compute army counts for ALL territories (avoids 500+ repeated lookups)
        self.territory_armies = {}
        for territory in game_state.territory_owners:
            self.territory_armies[territory] = game_state.get_territory_total_armies(territory)

        # Scalar values
        self.player_income = game_state.calculate_player_income(player_index)
        self.player_army_count = game_state.get_player_army_count(player_index)

        # Check if player has a Keep or Castle anywhere (completed buildings)
        self.player_has_keep = False
        for terr in self.owned_territories:
            if terr in game_state.buildings:
                for bt in game_state.buildings[terr].values():
                    if bt in ('Keep', 'Castle'):
                        self.player_has_keep = True
                        break
                if self.player_has_keep:
                    break

        # R4: Also check under-construction Keeps so AI doesn't redundantly
        # queue a second Keep while one is already being built
        if not self.player_has_keep:
            for terr in self.owned_territories:
                if terr in game_state.under_construction:
                    for building_tuple in game_state.under_construction[terr].values():
                        if building_tuple[0] == 'Keep':
                            self.player_has_keep = True
                            break
                if self.player_has_keep:
                    break

        # Threats (computed once with lowest threshold, filtered for higher thresholds)
        self.threats = None  # Set after construction by strategy module


class AIPlayer:
    """
    Main AI player controller that orchestrates decision-making and action execution.

    Attributes:
        player_index (int): Index of the player (0-3)
        difficulty (int): Difficulty level (0=Easy, 1=Medium, 2=Hard)
        config (dict): Difficulty configuration parameters
        turn_in_progress (bool): Whether AI is currently executing a turn

    Thread Safety:
        Two levels of locking are used:
        1. _game_state_lock (class-level RLock): Shared by all AI instances for
           thread-safe access to game state during action execution.
        2. _turn_lock (instance-level Lock): Prevents race condition in execute_turn()
           when the method is called rapidly (e.g., during game loop iteration).

        The class-level lock uses RLock (reentrant) to allow nested acquisition
        within the same thread, which is necessary for actions that trigger
        other game state operations.

        H6: A ThreadPoolExecutor (max_workers=1) is used instead of creating a new
        Thread per turn. This avoids thread creation overhead and ensures cleanup.

        H8: A threading.Event (_animation_done) replaces time.sleep() polling for
        animation completion. External code can call notify_animation_complete()
        to wake the waiting thread immediately.

    Difficulty System:
        Each difficulty level adjusts multiple parameters:
        - strategy_quality: Chance of choosing optimal vs. random action
        - decision_delay: Time AI "thinks" before acting (for human playability)
        - attack_aggression: Likelihood of offensive vs. defensive play
        - building_efficiency: How consistently AI builds structures
    """

    # Class-level lock shared by all AI instances for thread-safe game state access.
    # Using RLock (reentrant lock) allows the same thread to acquire the lock multiple
    # times, which is necessary when one locked operation triggers another.
    _game_state_lock = RLock()

    # Difficulty configurations
    DIFFICULTY_CONFIGS = {
        0: {  # Easy - Strengthened (+30-40% decision quality)
            'name': 'Easy',
            'income_multiplier': 0.75,  # Keep income the same
            'decision_delay_min': 5.0,
            'decision_delay_max': 8.0,
            'strategy_quality': 0.85,  # +42% from 0.6 - makes much better decisions
            'hero_ability_usage': 0.65,  # +63% from 0.4 - uses abilities frequently
            'tech_research_rate': 0.8,  # +60% from 0.5 - researches consistently
            'attack_aggression': 0.5,  # +67% from 0.3 - attacks much more
            'building_efficiency': 0.85  # +42% from 0.6 - builds consistently
        },
        1: {  # Medium - Strengthened (+15-30% decision quality)
            'name': 'Medium',
            'income_multiplier': 1.0,  # Keep income the same
            'decision_delay_min': 3.0,
            'decision_delay_max': 5.0,
            'strategy_quality': 0.95,  # +19% from 0.8 - near-optimal decisions
            'hero_ability_usage': 0.9,  # +29% from 0.7 - uses abilities aggressively
            'tech_research_rate': 0.95,  # +19% from 0.8 - researches almost always
            'attack_aggression': 0.8,  # +33% from 0.6 - much more aggressive
            'building_efficiency': 0.95  # +19% from 0.8 - builds almost always
        },
        2: {  # Hard - Strengthened (maxed out all rates)
            'name': 'Hard',
            'income_multiplier': 1.25,  # Keep income bonus
            'decision_delay_min': 2.0,
            'decision_delay_max': 3.0,
            'strategy_quality': 1.0,  # Already optimal
            'hero_ability_usage': 1.0,  # +5% from 0.95 - ALWAYS uses abilities
            'tech_research_rate': 1.0,  # Already maxed
            'attack_aggression': 1.0,  # Already maxed
            'building_efficiency': 1.0  # Already maxed
        }
    }

    def __init__(self, player_index, difficulty):
        """
        Initialize AI player.

        Args:
            player_index (int): Player index (0-3)
            difficulty (int): Difficulty level (0=Easy, 1=Medium, 2=Hard)
        """
        self.player_index = player_index
        self.difficulty = difficulty
        self.config = self.DIFFICULTY_CONFIGS[difficulty]

        # Initialize subsystems
        from ai_strategy import StrategyEvaluator
        from ai_economy import EconomyManager
        from ai_military import MilitaryCommander
        from ai_hero import HeroManager

        self.strategy = StrategyEvaluator(self)
        self.economy = EconomyManager(self)
        self.military = MilitaryCommander(self)
        self.hero_manager = HeroManager(self)

        # Turn state with lock for atomic check-and-set
        self._turn_lock = Lock()
        self.turn_in_progress = False
        self.actions_taken = []

        # H6: Thread pool for AI turn execution - reuses a single worker thread
        # instead of creating a new Thread() each time execute_turn() is called.
        # max_workers=1 ensures only one turn runs at a time per AI player.
        self._thread_pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f'ai_worker_p{player_index}'
        )

        # H8: Event-based animation waiting - replaces time.sleep() polling loop.
        # External code (e.g., game loop) can call notify_animation_complete() to
        # wake the AI thread immediately when animations finish, instead of the
        # thread blindly sleeping in 100ms intervals.
        self._animation_done = Event()

        logger.info(f"Created AI Player {player_index + 1} ({self.config['name']} difficulty)")

    def shutdown(self):
        """
        Shutdown the AI player's thread pool.

        Should be called when the game ends or the AI player is no longer needed
        to ensure the worker thread is properly cleaned up.
        """
        self._thread_pool.shutdown(wait=False)
        logger.info(f"AI Player {self.player_index + 1} thread pool shut down")

    def notify_animation_complete(self):
        """
        Notify the AI that animations have completed.

        Called by the game loop or animation system when all animations finish,
        allowing the AI's wait loop to wake up immediately instead of polling
        with time.sleep(). This reduces unnecessary CPU usage during the
        animation wait phase.
        """
        self._animation_done.set()

    def is_friendly_territory(self, territory_owner, game_state):
        """
        Check if a territory owner is friendly (owned by self or an ally).

        Args:
            territory_owner (int): Owner player index (-1 for neutral)
            game_state: GameState instance

        Returns:
            bool: True if territory is owned by self or an ally
        """
        if territory_owner == -1:
            return False  # Neutral is not friendly

        if territory_owner == self.player_index:
            return True  # Own territory

        # Check if ally
        return game_state.are_allies(self.player_index, territory_owner)

    def is_enemy_territory(self, territory_owner, game_state):
        """
        Check if a territory owner is an enemy (not self, not ally, not neutral).

        Args:
            territory_owner (int): Owner player index (-1 for neutral)
            game_state: GameState instance

        Returns:
            bool: True if territory is owned by an enemy
        """
        if territory_owner == -1:
            return False  # Neutral is not an enemy (it's neutral)

        if territory_owner == self.player_index:
            return False  # Own territory

        # Check if ally
        if game_state.are_allies(self.player_index, territory_owner):
            return False  # Ally is not an enemy

        return True  # Enemy player

    def execute_turn(self, game_state):
        """
        Execute AI player's turn with strategic decision-making.

        This is the main entry point called by the game loop. It:
        1. Marks turn as in progress (prevents multiple calls)
        2. Plans all actions for this turn
        3. Executes actions asynchronously with timing delays
        4. Ends turn automatically when complete

        Thread Safety:
            Uses _turn_lock to ensure atomic check-and-set of turn_in_progress flag,
            preventing race conditions when execute_turn is called rapidly.

        Args:
            game_state: GameState instance with current game state
        """
        # Tutorial hook: bypass normal AI and use scripted tutorial behavior
        if game_state.tutorial_mission and game_state.tutorial_mission.block_ai:
            game_state.tutorial_mission.execute_ai_turn_override()
            return

        logger.debug(f"execute_turn() called for player {self.player_index}, turn_in_progress={self.turn_in_progress}")

        # Atomic check-and-set to prevent race condition with rapid calls
        with self._turn_lock:
            if self.turn_in_progress:
                logger.debug(f"Turn already in progress for player {self.player_index}, returning")
                return
            self.turn_in_progress = True

        logger.debug(f"Starting async thread for player {self.player_index}")

        # H6: Submit to thread pool instead of creating a new Thread each turn.
        # The ThreadPoolExecutor reuses its worker thread, avoiding the overhead
        # of thread creation/destruction on every AI turn.
        self._thread_pool.submit(self._execute_turn_async, game_state)
        logger.debug(f"Async task submitted for player {self.player_index}")

    def _execute_turn_async(self, game_state):
        """
        Async turn execution with timing delays.

        This runs in a separate thread to avoid blocking the game loop.
        It implements the full AI decision-making pipeline with realistic
        timing delays between actions.

        Args:
            game_state: GameState instance
        """
        try:
            # Calculate thinking time based on difficulty
            delay = random.uniform(
                self.config['decision_delay_min'],
                self.config['decision_delay_max']
            )

            logger.info(f"Player {self.player_index + 1} thinking... ({delay:.1f}s)")
            time.sleep(delay)

            # C2 fix: Planning is read-only — no lock needed here.
            # Lock is held only around actual game state mutations:
            # _execute_action (line 527), next_player (line 372), battle resolution (line 824).
            self.actions_taken = []
            self._plan_turn_actions(game_state)

            logger.info(f"Player {self.player_index + 1} planned {len(self.actions_taken)} actions")

            # Execute each action with small delays
            # Track if we've hit command limit to skip remaining training actions
            command_limit_reached = False

            for i, (action_type, action_data) in enumerate(self.actions_taken):
                # Skip training actions if we already hit command limit
                if action_type == 'train' and command_limit_reached:
                    continue  # Silently skip to avoid log spam

                time.sleep(0.5)  # Small delay between actions

                try:
                    success = self._execute_action(game_state, action_type, action_data)
                    logger.debug(f"Executed action {i+1}/{len(self.actions_taken)}: {action_type}")

                    # Check if training failed due to command limit
                    if action_type == 'train' and not success:
                        # Check if it was due to command limit
                        with self._game_state_lock:
                            current_command = game_state.get_player_army_count(self.player_index)
                            command_limit = game_state.player_command_limit[self.player_index]
                            if current_command >= command_limit:
                                command_limit_reached = True
                                logger.info(f"Command limit reached ({current_command}/{command_limit}), skipping remaining training")
                except Exception as e:
                    logger.error(f"Failed to execute {action_type}: {e}")

            # Final pause before ending turn
            time.sleep(1.0)

            # End turn - this executes movement orders and starts animations
            # Thread-safe: Acquire lock before ending turn
            with self._game_state_lock:
                game_state.next_player()
                logger.info(f"Player {self.player_index + 1} ended turn")

            # H8: Wait for animations using Event-based signaling instead of time.sleep() polling.
            # The event is set by notify_animation_complete() (called from game loop when
            # animations finish), or times out after wait_interval for a fallback status check.
            # This is more CPU-efficient than the old time.sleep(0.1) polling loop.
            max_wait_time = 15.0  # Maximum time to wait for animations (seconds)
            wait_interval = 0.1   # Check interval (Event.wait timeout)
            total_waited = 0.0

            # Clear the event before starting the wait loop so we don't act on stale signals
            self._animation_done.clear()

            while total_waited < max_wait_time:
                # H8: Wait on event instead of time.sleep() - wakes immediately when
                # notify_animation_complete() is called, or falls through after timeout
                self._animation_done.wait(timeout=wait_interval)
                total_waited += wait_interval

                # Check if animations are still running
                with self._game_state_lock:
                    has_animations = len(game_state.active_animations) > 0
                    has_pending = len(game_state.pending_arrivals) > 0
                    in_execution = game_state.turn_phase == 'execution'

                if not has_animations and not has_pending and not in_execution:
                    logger.debug(f"Animations complete after {total_waited:.1f}s")
                    break

                # Clear the event for the next iteration (in case it was set but
                # animations haven't fully completed yet)
                self._animation_done.clear()

            # Auto-resolve any battles AFTER animations complete
            # (battles are created during _process_arrivals() when animations finish)
            time.sleep(0.3)
            self._auto_resolve_battles(game_state)

        except Exception as e:
            logger.error(f"Turn execution failed for player {self.player_index + 1}: {e}")
            # Try to end turn anyway to avoid getting stuck
            try:
                # H6 fix: protect exception-path next_player() with lock
                with self._game_state_lock:
                    game_state.next_player()
            except Exception:
                pass  # C3 fix: Last resort recovery to prevent AI from blocking game

        finally:
            # C1 fix: Reset flag under lock to prevent race with execute_turn() check-and-set
            with self._turn_lock:
                self.turn_in_progress = False

    def _plan_turn_actions(self, game_state):
        """
        Plan all actions for this turn based on game state analysis.

        Decision priority order:
        1. Hero abilities (high impact, limited cooldown)
        2. Building construction (long-term economy)
        3. Technology research (strategic advantages)
        4. Unit training (military power)
        5. Hero training (if affordable)
        6. Movement/attacks (territory expansion)

        Args:
            game_state: GameState instance
        """
        self.actions_taken = []

        try:
            # FPS OPTIMIZATION 5B: Build per-turn cache of commonly recomputed values
            # (territory count, owned territories, army counts, income, etc.)
            # This avoids hundreds of redundant lookups across subsystem calls.
            cache = TurnCache(game_state, self.player_index)

            # Analyze current game state (uses cache to avoid redundant computation)
            analysis = self.strategy.analyze_game_state(game_state, cache)
            strategic_priority = self.strategy.get_strategic_priority(game_state, cache)

            logger.info(f"Player {self.player_index + 1} analysis: "
                       f"Territories: {analysis['territory_count']}, "
                       f"Gold: {analysis['available_gold']}, "
                       f"Income: {analysis['total_income']}")
            logger.info(f"Player {self.player_index + 1} priority: {strategic_priority}")
            logger.debug(f"Player {self.player_index + 1} threats: {len(analysis['threats'])}, "
                        f"opportunities: {len(analysis['opportunities'])}")

            # 1. Hero actions (abilities + training)
            hero_actions = self.hero_manager.plan_hero_actions(game_state, cache)
            self.actions_taken.extend(hero_actions)

            # 2. Economic actions (buildings + tech)
            economic_actions = self.economy.plan_economic_actions(
                game_state, strategic_priority, cache
            )
            self.actions_taken.extend(economic_actions)

            # 3. Military actions (training + movement)
            # Calculate remaining budget after economic spending (use actual costs, not hardcoded)
            spent_on_economy = 0
            for action_type, action_data in economic_actions:
                if action_type == 'build':
                    building_type = action_data.get('building', '')
                    base_cost = game_state.building_types.get(building_type, {}).get('cost', 30)
                    spent_on_economy += game_state.get_effective_cost(
                        building_type, base_cost, self.player_index)
                elif action_type == 'upgrade_castle':
                    # H3 fix: actual Castle upgrade cost is 150, not 100
                    spent_on_economy += 150
                elif action_type == 'research':
                    tech_id = action_data.get('tech_id')
                    tech = next((t for t in game_state.technologies if t['id'] == tech_id), None)
                    if tech:
                        spent_on_economy += tech.get('cost', 0)
            military_budget = max(0, analysis['available_gold'] - spent_on_economy)

            military_actions = self.military.plan_military_actions(
                game_state,
                strategic_priority,
                military_budget,
                analysis['threats'],
                cache
            )
            self.actions_taken.extend(military_actions)

            # 4. Leftover gold tech research - invest remaining gold in tech
            # This happens AFTER training/building to ensure surplus gold goes to research
            # (no cache needed - just picks a random affordable tech)
            leftover_tech = self._try_leftover_tech_research(game_state, analysis['available_gold'])
            if leftover_tech:
                self.actions_taken.append(leftover_tech)

            logger.info(f"Player {self.player_index + 1} planned {len(self.actions_taken)} total actions")

        except Exception as e:
            logger.error(f"Planning failed for player {self.player_index + 1}: {e}", exc_info=True)
            # Continue with empty action list rather than crashing

    def _execute_action(self, game_state, action_type, action_data):
        """
        Execute a single planned action with thread-safe game state access.

        Thread Safety:
            Acquires _game_state_lock before modifying game state to prevent
            race conditions with other AI threads or UI updates.

        Args:
            game_state: GameState instance
            action_type (str): Type of action ('build', 'train', 'move', etc.)
            action_data (dict): Action-specific parameters

        Returns:
            bool: True if action succeeded, False otherwise
        """
        # Acquire lock before modifying game state
        with self._game_state_lock:
            return self._execute_action_internal(game_state, action_type, action_data)

    def _execute_action_internal(self, game_state, action_type, action_data):
        """
        Internal method for executing actions (called within lock).

        Args:
            game_state: GameState instance
            action_type (str): Type of action
            action_data (dict): Action parameters

        Returns:
            bool: True if action succeeded, False otherwise
        """
        success = False
        try:
            if action_type == 'upgrade_castle':
                territory = action_data['territory']
                plot_idx = action_data['plot']
                # Call game_state's Castle upgrade method
                success = game_state.start_castle_upgrade(territory, plot_idx)
                if success:
                    logger.info(f"Started Castle upgrade in {territory}")
                else:
                    logger.warning(f"Failed to start Castle upgrade in {territory} - may already be upgrading or not a Keep")

            elif action_type == 'demolish':
                territory = action_data['territory']
                plot_idx = action_data['plot']
                # Get building type before demolishing
                building_type = "Unknown"
                if territory in game_state.buildings and plot_idx in game_state.buildings[territory]:
                    building_type = game_state.buildings[territory][plot_idx]
                success = game_state.destroy_building(territory, plot_idx)
                if success:
                    logger.info(f"Demolished {building_type} in {territory} (making room for military buildings)")
                else:
                    logger.warning(f"Failed to demolish building in {territory} - may be invalid")

            elif action_type == 'build':
                territory = action_data['territory']
                plot_idx = action_data['plot']
                building_type = action_data['building']
                success = game_state.start_construction(territory, plot_idx, building_type)
                if success:
                    logger.info(f"Built {building_type} in {territory}")
                else:
                    logger.warning(f"Failed to build {building_type} in {territory} - may be invalid or unaffordable")

            elif action_type == 'train':
                territory = action_data['territory']
                barracks_plot = action_data['barracks_plot']
                unit_type = action_data['unit_type']
                success = game_state.start_training(territory, barracks_plot, unit_type)
                if success:
                    logger.debug(f"Training {unit_type} in {territory}")
                else:
                    logger.debug(f"Failed to train {unit_type} in {territory} - may be invalid, queue full, or unaffordable")

            elif action_type == 'research':
                tech_id = action_data['tech_id']
                # Find tech by ID
                tech = next((t for t in game_state.technologies if t['id'] == tech_id), None)
                tech_name = tech['name'] if tech else "Unknown Tech"
                success = game_state.start_research(tech_id)
                if success:
                    logger.info(f"Researching {tech_name}")
                else:
                    logger.warning(f"Failed to research {tech_name} - may be invalid, already researching, or unaffordable")

            elif action_type == 'move':
                from_territory = action_data['from']
                to_territory = action_data['to']
                army_count = action_data.get('army_count')  # Specific army count to move

                # Get available units in the AI player's garrison (not owner's legacy units)
                # IMPORTANT: AI can have garrisons in allied territories
                garrison = game_state.territory_garrisons.get(from_territory, {}).get(self.player_index)
                if garrison:
                    # Debug: Check unit statuses BEFORE fix
                    units_before = garrison.get('units', [])
                    statuses_before = [(u.get('id'), u.get('status'), u.get('order')) for u in units_before]

                    # Fix any stale 'ordered' statuses before checking availability
                    game_state.fix_unit_statuses(from_territory, self.player_index)

                    units = garrison.get('units', [])
                    available_units = [u for u in units if u['status'] == 'ready']

                    # Debug: Check unit statuses AFTER fix
                    statuses_after = [(u.get('id'), u.get('status'), u.get('order')) for u in units]
                else:
                    available_units = []

                if not available_units:
                    # Silently skip - AI often over-plans moves from same territory
                    # This is expected behavior when units are already ordered
                    pass
                elif army_count is not None and army_count <= 0:
                    # C1 fix: Only catch explicitly invalid counts (<=0).
                    # None means "move all" and is handled in the else branch below.
                    logger.warning(f"Invalid army count: {army_count}")
                else:
                    # Determine how many units to move
                    if army_count is None:
                        # Move all available units
                        units_to_move = available_units
                    else:
                        # Move specific number of units (for army splitting)
                        units_to_move = available_units[:min(army_count, len(available_units))]

                    if not units_to_move:
                        logger.warning(f"No units to move from {from_territory}")
                    else:
                        # Extract unit IDs
                        unit_ids = [u['id'] for u in units_to_move]

                        # Create unit-level movement order (allows army splitting)
                        # IMPORTANT: Pass player index for multi-garrison support
                        success = game_state.add_movement_order_for_units(
                            from_territory, to_territory, unit_ids, player=self.player_index
                        )
                        if success:
                            logger.info(f"Moving {len(unit_ids)} units from {from_territory} to {to_territory}")
                        else:
                            logger.warning(f"Failed to create movement order from {from_territory} to {to_territory}")

            elif action_type == 'train_hero':
                territory = action_data['territory']
                keep_plot = action_data['keep_plot']
                hero_type = action_data['hero_type']
                success = game_state.start_hero_training(territory, keep_plot, hero_type)
                if success:
                    logger.info(f"Training hero {hero_type} in {territory}")
                else:
                    logger.debug(f"Failed to train hero {hero_type} in {territory} - may be invalid, already owned, or unaffordable")

            elif action_type == 'hero_ability':
                hero_type = action_data['hero_type']
                ability_name = action_data['ability_name']
                target = action_data.get('target')

                # M1+M2 fix: Route all abilities through proper game_state execute_* methods
                # instead of duplicating logic inline. This ensures all abilities actually work.
                ability_success = False

                # Abilities that require a target territory
                if ability_name == 'Aggressive Diplomacy' and target:
                    result = game_state.execute_aggressive_diplomacy(target, self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Levy':
                    # H5 fix: Use scored target from planning, fall back to random owned territory
                    owned_terrs = [t for t, owner in game_state.territory_owners.items() if owner == self.player_index]
                    if owned_terrs:
                        target_terr = target if target and target in owned_terrs else random.choice(owned_terrs)
                        result = game_state.execute_levy(target_terr, self.player_index)
                        ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Extort Populace':
                    # M1 fix: no target needed — gains 50g per Keep/Castle owned
                    result = game_state.execute_extort_populace(self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Reinforce':
                    result = game_state.execute_reinforce(self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Relentless Charge' and target:
                    result = game_state.execute_relentless_charge(target, self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Decisive Strike' and target:
                    result = game_state.execute_decisive_strike(target, self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Valorous Charge' and target:
                    result = game_state.execute_valorous_charge(target, self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Royal Charisma' and target:
                    result = game_state.execute_royal_charisma(target, self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                elif ability_name == 'Regicide' and target:
                    result = game_state.execute_regicide(target, self.player_index)
                    ability_success = result[0] if isinstance(result, tuple) else bool(result)
                # Non-targeting abilities (state toggles)
                elif ability_name == 'Vow of Silence':
                    # Find the hero name and ability data for _activate_vow_of_silence
                    hero_info = game_state.HERO_TYPES.get(hero_type, {})
                    for ab in hero_info.get('abilities', []):
                        if ab.get('name') == 'Vow of Silence':
                            game_state._activate_vow_of_silence(hero_type, ab)
                            ability_success = True
                            break
                elif ability_name == 'Embargo':
                    game_state._activate_embargo(self.player_index)
                    ability_success = True
                elif ability_name == 'Master Negotiator':
                    game_state._activate_master_negotiator(self.player_index)
                    ability_success = True

                if ability_success:
                    # Set cooldown (mirrors activate_hero_ability logic)
                    hero_info = game_state.HERO_TYPES.get(hero_type, {})
                    for ab in hero_info.get('abilities', []):
                        if ab.get('name') == ability_name:
                            cooldown = ab.get('cooldown', 0)
                            if self.player_index not in game_state.hero_ability_cooldowns:
                                game_state.hero_ability_cooldowns[self.player_index] = {}
                            if hero_type not in game_state.hero_ability_cooldowns[self.player_index]:
                                game_state.hero_ability_cooldowns[self.player_index][hero_type] = {}
                            game_state.hero_ability_cooldowns[self.player_index][hero_type][ability_name] = cooldown
                            break
                    logger.info(f"AI used {ability_name} successfully")
                else:
                    logger.debug(f"AI ability {ability_name} failed or had no valid target")

                success = True  # Don't block turn on ability failure

        except Exception as e:
            logger.error(f"Failed to execute {action_type}: {e}")
            success = False

        return success

    def _try_leftover_tech_research(self, game_state, available_gold):
        """
        Try to research tech with leftover gold after training/building is planned.

        This ensures AI invests surplus gold in technology rather than hoarding it.
        Called at the END of planning after all training and building actions are decided.

        Args:
            game_state: GameState instance
            available_gold: Total gold available at start of turn

        Returns:
            tuple: ('research', {'tech_id': tech_id}) or None
        """
        # Check if already researching something
        if self.player_index in game_state.research_in_progress and game_state.research_in_progress[self.player_index]:
            return None

        # Check if we already planned a research action this turn
        for action_type, _ in self.actions_taken:
            if action_type == 'research':
                return None  # Already have research planned

        # Calculate estimated spending from planned actions
        estimated_spending = 0
        for action_type, action_data in self.actions_taken:
            if action_type == 'build':
                building_type = action_data.get('building', '')
                building_cost = game_state.building_types.get(building_type, {}).get('cost', 30)
                estimated_spending += game_state.get_effective_cost(building_type, building_cost, self.player_index)
            elif action_type == 'train':
                unit_type = action_data.get('unit_type', '')
                unit_cost = game_state.UNIT_TYPES.get(unit_type, {}).get('cost', 10)
                estimated_spending += game_state.get_effective_cost(unit_type, unit_cost, self.player_index)
            elif action_type == 'train_hero':
                # Hero training cost is ~200
                estimated_spending += 200
            elif action_type == 'upgrade_castle':
                estimated_spending += 150  # M3 fix: actual Castle upgrade cost is 150

        leftover_gold = available_gold - estimated_spending

        # Only try tech research if we have meaningful leftover gold (80+)
        if leftover_gold < 80:
            return None

        # Use tech researcher to find best tech to research
        tech_id = self.economy.tech_researcher.select_research_action(
            game_state, self.player_index, self.difficulty
        )

        if tech_id is None:
            return None

        # Check if we can afford this tech with leftover gold
        tech = next((t for t in game_state.technologies if t['id'] == tech_id), None)
        if tech and leftover_gold >= tech['cost']:
            logger.debug(f"Planning leftover gold tech research: {tech['name']} (leftover: {leftover_gold}g)")
            return ('research', {'tech_id': tech_id})

        return None

    def _auto_resolve_battles(self, game_state):
        """
        Automatically resolve all battles involving this AI player with thread-safe access.

        This is called after the AI's movement phase to immediately resolve
        any battles resulting from their movements, preventing the game from
        getting stuck waiting for manual battle resolution.

        Resolves ALL pending battles (not just those where AI is involved),
        since all battles during AI turn execution must be resolved before
        advancing to the next player.

        Thread Safety:
            Acquires _game_state_lock for each battle resolution to prevent
            race conditions during concurrent battle processing.

        Args:
            game_state: GameState instance
        """
        try:
            # Check if there are pending battles
            if not game_state.pending_battles:
                logger.debug(f"No pending battles to resolve")
                return

            # Resolve ALL pending battles during AI turn
            # (These were all created during AI's execution phase)
            num_battles = len(game_state.pending_battles)
            logger.info(f"Auto-resolving {num_battles} battle(s) from Player {self.player_index + 1}'s turn")

            # Resolve each battle (resolve in reverse order to maintain indices)
            for battle_idx in reversed(range(num_battles)):
                time.sleep(0.3)  # Small delay for visual feedback

                # Thread-safe: Acquire lock for battle resolution
                with self._game_state_lock:
                    # Get battle info BEFORE resolving (will be removed from list)
                    battle = game_state.pending_battles[battle_idx]
                    territory_name = battle.territory
                    players_involved = list(battle.armies.keys())

                    logger.info(f"Resolving battle in {territory_name} (Players: {[p+1 for p in players_involved]})")

                    success = game_state.resolve_battle(battle_idx)
                    if success:
                        logger.info(f"Resolved battle in {territory_name}")
                    else:
                        logger.error(f"Failed to resolve battle in {territory_name}")

            # After all battles are resolved, check if we need to advance to next player
            # Thread-safe: Acquire lock for player advancement
            with self._game_state_lock:
                if game_state.ready_to_advance_turn:
                    logger.info("All battles resolved, advancing to next player")
                    time.sleep(0.5)  # Brief pause before advancing
                    game_state._advance_to_next_player()

        except Exception as e:
            logger.error(f"Failed to auto-resolve battles: {e}", exc_info=True)

    def apply_difficulty_variation(self, candidates):
        """
        Apply difficulty-based randomization to decision quality.

        For Easy/Medium AI, sometimes chooses suboptimal options to make them
        beatable. Hard AI always chooses the optimal choice.

        Args:
            candidates (list): List of options sorted by score (best first)

        Returns:
            Selected candidate (optimal or randomized based on difficulty)
        """
        if not candidates:
            return None

        quality = self.config['strategy_quality']

        if random.random() < quality:
            # Choose optimal (highest scored)
            return candidates[0]
        else:
            # Choose randomly from top 50%
            mid_point = max(1, len(candidates) // 2)
            return random.choice(candidates[:mid_point])


# Test the AI player if run directly
if __name__ == '__main__':
    logger.info("AI Player Module Test")
    logger.info("=" * 60)

    # Create test AI players
    for difficulty in [0, 1, 2]:
        ai = AIPlayer(player_index=0, difficulty=difficulty)
        logger.info(f"Created: {ai.config['name']} AI")
        logger.info(f"  Decision time: {ai.config['decision_delay_min']}-{ai.config['decision_delay_max']}s")
        logger.info(f"  Strategy quality: {ai.config['strategy_quality']*100}%")
        logger.info(f"  Attack aggression: {ai.config['attack_aggression']*100}%")
        # Clean up thread pool
        ai.shutdown()
