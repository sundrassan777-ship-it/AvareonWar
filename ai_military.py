"""
AI Military Module
Military strategy and tactical decision-making for AI opponents.

This module handles all military decisions including:
- Unit composition (counter system)
- Attack target selection
- Army movement orders
- Defense coordination
- Training decisions

Classes:
    ArmyComposer: Calculates optimal unit composition
    AttackPlanner: Selects attack targets and plans movements
    DefenseCoordinator: Manages defensive reinforcements
    TrainingPlanner: Decides what units to train
    MilitaryCommander: Main military decision coordinator
"""

import random
from collections import deque
import map_data

from utils.logger import get_logger
logger = get_logger(__name__)


class ArmyComposer:
    """
    Calculates optimal unit composition based on the rock-paper-scissors counter system.

    The counter system forms a cycle: Swordsman > Pikeman > Cavalry > Archer > Swordsman
    Each unit type has a 2x damage bonus against its counter target.
    """

    # Counter system: S > P > C > A > S (each unit beats the next in the chain)
    # Swordsman defeats Pikeman, Pikeman defeats Cavalry, etc.
    COUNTERS = {
        'Swordsman': 'Pikeman',
        'Pikeman': 'Cavalry',
        'Cavalry': 'Archer',
        'Archer': 'Swordsman'
    }

    # Reverse lookup: what unit type counters each unit
    COUNTERED_BY = {
        'Swordsman': 'Archer',
        'Pikeman': 'Swordsman',
        'Cavalry': 'Pikeman',
        'Archer': 'Cavalry'
    }

    def calculate_counter_composition(self, enemy_composition, game_state):
        """
        Calculate optimal unit composition to counter enemy.

        Strategy: 60% counter to their strongest unit, 40% balanced

        Args:
            enemy_composition (dict): {unit_type: count}
            game_state: GameState instance

        Returns:
            dict: {unit_type: percentage} - composition ratios
        """
        if not enemy_composition or sum(enemy_composition.values()) == 0:
            # Default balanced composition
            return {
                'Swordsman': 0.25,
                'Archer': 0.25,
                'Pikeman': 0.25,
                'Cavalry': 0.25
            }

        # Find enemy's strongest unit type
        total_enemy = sum(enemy_composition.values())
        strongest_type = max(enemy_composition.items(), key=lambda x: x[1])[0]

        # Get counter unit
        counter_unit = self.COUNTERS.get(strongest_type, 'Swordsman')

        # Build composition: 60% counter, ~13.33% each for the other 3 unit types
        # This ensures the total sums to exactly 1.0 (100%)
        other_ratio = 0.40 / 3  # ~0.1333 for each non-counter unit
        composition = {
            'Swordsman': other_ratio,
            'Archer': other_ratio,
            'Pikeman': other_ratio,
            'Cavalry': other_ratio
        }
        composition[counter_unit] = 0.60

        return composition

    def get_enemy_composition(self, territory, game_state):
        """
        Get unit composition of armies in a territory.

        Args:
            territory (str): Territory name
            game_state: GameState instance

        Returns:
            dict: {unit_type: count}
        """
        # Get all units from all garrisons in the territory
        all_units = []
        garrisons = game_state.territory_garrisons.get(territory, {})
        for player_index, garrison_data in garrisons.items():
            units = garrison_data.get('units', [])
            all_units.extend(units)

        if not all_units:
            # No detailed composition data, estimate based on total garrison size
            garrison = game_state.get_territory_total_armies(territory)
            if garrison == 0:
                return {}

            # Assume balanced composition
            per_type = garrison // 4
            return {
                'Swordsman': per_type,
                'Archer': per_type,
                'Pikeman': per_type,
                'Cavalry': garrison - (per_type * 3)  # Remainder
            }

        # Count actual units from all garrisons
        composition = {'Swordsman': 0, 'Archer': 0, 'Pikeman': 0, 'Cavalry': 0}
        for unit in all_units:
            unit_type = unit.get('type', 'Swordsman')
            composition[unit_type] = composition.get(unit_type, 0) + 1

        return composition


class AttackPlanner:
    """Selects attack targets and plans movements"""

    def __init__(self, ai_player):
        self.ai_player = ai_player
        self.composer = ArmyComposer()
        # M23 FIX: Cache TerritoryScorer to avoid per-call instantiation in _score_attack_target
        from ai_strategy import TerritoryScorer
        self._scorer = TerritoryScorer()

    def find_reachable_enemies(self, game_state, from_territory, max_distance=3):
        """
        Find all enemy/neutral territories reachable from a starting territory.
        Can path through allied territories to reach distant enemies.

        Args:
            game_state: GameState instance
            from_territory: Starting territory
            max_distance: Maximum path length through allied territory (default 3)

        Returns:
            dict: {target_territory: path_length} for all reachable enemies
        """
        player_index = self.ai_player.player_index
        reachable = {}  # {territory: distance}
        visited = set()
        # FPS OPTIMIZATION 5B: deque for O(1) popleft instead of O(n) list.pop(0)
        queue = deque([(from_territory, 0)])  # (territory, distance)

        while queue:
            current, distance = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            # Check neighbors
            neighbors = map_data.get_neighbors(current)
            for neighbor in neighbors:
                if neighbor in visited:
                    continue

                neighbor_owner = game_state.territory_owners.get(neighbor, -1)

                # Check if neighbor is allied (owned by player or their ally)
                is_allied = (neighbor_owner == player_index or
                           (neighbor_owner >= 0 and game_state.are_allies(player_index, neighbor_owner)))

                if is_allied:
                    # Can pass through allied territory if within max distance
                    if distance + 1 < max_distance:
                        queue.append((neighbor, distance + 1))
                else:
                    # Found an enemy/neutral territory - this is a potential target
                    if neighbor not in reachable or distance + 1 < reachable[neighbor]:
                        reachable[neighbor] = distance + 1

        return reachable

    def select_attack_targets(self, game_state, max_attacks=3, cache=None):
        """
        Select best territories to attack.

        Args:
            game_state: GameState instance
            max_attacks (int): Maximum number of attacks to plan
            cache: Optional TurnCache with pre-computed values for performance

        Returns:
            list: [(from_territory, to_territory, army_count), ...]
        """
        player_index = self.ai_player.player_index
        attacks = []

        # Find all territories where AI has a garrison (owned OR allied territories)
        # AI should be able to move from any territory where it has units
        territories_with_garrison = []
        for territory, garrisons in game_state.territory_garrisons.items():
            if player_index in garrisons:
                garrison = garrisons[player_index]
                if garrison.get('unmoved', 0) + garrison.get('moved', 0) > 0:
                    territories_with_garrison.append(territory)

        attack_candidates = []

        # H5 Performance: Pre-compute BFS reachability for all garrison territories once,
        # instead of re-running BFS inside the scoring loop. This avoids O(n^3) complexity
        # when many territories each trigger a full BFS traversal.
        precomputed_reachability = {}
        for territory in territories_with_garrison:
            precomputed_reachability[territory] = self.find_reachable_enemies(
                game_state, territory, max_distance=3
            )

        for territory in territories_with_garrison:
            # Get AI player's garrison
            garrison = game_state.territory_garrisons.get(territory, {}).get(player_index)
            available_army = garrison.get('unmoved', 0) if garrison else 0

            if available_army < 1:  # Need at least 1 to attack (changed from 2 for early game)
                continue

            # Look up pre-computed reachable enemies (no BFS re-computation needed)
            reachable_enemies = precomputed_reachability[territory]

            for target_territory, path_distance in reachable_enemies.items():
                # Check if target is directly adjacent OR reachable through 1 friendly hop
                is_adjacent = map_data.are_adjacent(territory, target_territory)

                # Also allow attacks through 1 friendly intermediate territory
                # This enables attacking enemies that are adjacent to our allied neighbors
                can_reach_through_ally = False
                if not is_adjacent and path_distance <= 2:
                    # Check if any friendly neighbor is adjacent to the target
                    for neighbor in map_data.get_neighbors(territory):
                        neighbor_owner = game_state.territory_owners.get(neighbor, -1)
                        if self.ai_player.is_friendly_territory(neighbor_owner, game_state):
                            if map_data.are_adjacent(neighbor, target_territory):
                                can_reach_through_ally = True
                                break

                if not is_adjacent and not can_reach_through_ally:
                    continue  # Target not reachable in 1-2 hops

                # Score this attack
                score = self._score_attack_target(
                    territory, target_territory, available_army, game_state, player_index, cache=cache
                )

                # Reduce score for distant targets (prefer adjacent over through-ally)
                if not is_adjacent:
                    score -= 15.0  # Penalty for indirect attacks
                distance_penalty = (path_distance - 1) * 10
                score -= distance_penalty

                # Lower threshold to allow more attacks (was 30.0)
                if score > 20.0:
                    attack_candidates.append((territory, target_territory, available_army, score))

        if not attack_candidates:
            return []

        # Sort by score (best first)
        attack_candidates.sort(key=lambda x: x[3], reverse=True)

        # Select top attacks (up to max_attacks)
        # Track armies used per territory to enable army splitting
        armies_allocated = {}  # {territory: armies_used}

        # Check if early game (allows using ALL armies for expansion)
        # TurnCache: use cached territory_count to avoid re-scanning territory_owners
        territory_count = cache.territory_count if cache else sum(
            1 for owner in game_state.territory_owners.values()
            if owner == player_index
        )
        is_early_game = territory_count < 16  # Changed from 10 to 16 for extended aggressive early expansion

        for i in range(min(max_attacks, len(attack_candidates))):
            from_terr, to_terr, army_count, score = attack_candidates[i]

            # Calculate armies remaining in this territory
            already_allocated = armies_allocated.get(from_terr, 0)
            remaining_armies = army_count - already_allocated

            # Check if target is empty neutral
            target_owner = game_state.territory_owners.get(to_terr, -1)
            # IMPORTANT: Use total armies (all garrisons) to check if truly empty
            # TurnCache: use cached territory_armies to avoid per-territory garrison scan
            target_garrison = cache.territory_armies.get(to_terr, 0) if cache else game_state.get_territory_total_armies(to_terr)
            is_empty_neutral = (target_owner == -1 and target_garrison == 0)

            # Assess safety of source territory (how many armies to keep)
            # EARLY GAME OVERRIDE: Ignore garrison requirements for empty neutral expansion
            if is_early_game and is_empty_neutral:
                garrison_needed = 0  # Send everything in early game expansion!
            else:
                garrison_needed = self._calculate_garrison_needed(from_terr, game_state, player_index)

            # Determine minimum armies needed to continue splitting
            # Can send armies as long as we'll still meet garrison requirements
            min_armies_needed = garrison_needed + 1  # Need garrison + at least 1 to send

            if remaining_armies < min_armies_needed:
                continue

            # Determine how many to send
            if from_terr not in armies_allocated:
                # First attack from this territory
                if is_early_game or is_empty_neutral:
                    # Early game/empty neutral: send 1 army to maximize splits (1-1-1 possible)
                    attack_with = 1
                else:
                    # Normal: send all except required garrison
                    attack_with = max(1, remaining_armies - garrison_needed)
            else:
                # Additional attack from same territory
                if is_early_game or is_empty_neutral:
                    # Send 1 army at a time to maximize territory conquest
                    attack_with = 1
                else:
                    # Send remaining armies beyond garrison requirement
                    can_send = remaining_armies - garrison_needed
                    attack_with = max(1, can_send)

            attacks.append((from_terr, to_terr, attack_with))

            # Track allocated armies
            armies_allocated[from_terr] = already_allocated + attack_with

        return attacks

    def _calculate_garrison_needed(self, territory, game_state, player_index):
        """
        Calculate how many armies should be kept as garrison in a territory.

        Returns 0-3 armies based on danger level and difficulty:
        - 0: Completely safe (all neighbors friendly)
        - 1: Low danger (deep in friendly territory, 2+ territories from enemy)
        - 2: Medium danger (1 territory from enemy)
        - 3: High danger (adjacent to enemy territory)

        Hard AI reduces garrison requirements by 1 (minimum 0) for aggressive play.

        Args:
            territory (str): Territory to evaluate
            game_state: GameState instance
            player_index (int): Player index

        Returns:
            int: Number of armies to keep as garrison (0-3)
        """
        neighbors = map_data.get_neighbors(territory)

        # Check immediate neighbors
        has_enemy_neighbor = False
        has_neutral_neighbor = False
        all_friendly = True

        for neighbor in neighbors:
            neighbor_owner = game_state.territory_owners.get(neighbor, -1)

            if self.ai_player.is_friendly_territory(neighbor_owner, game_state):
                continue  # Friendly (owned by self or ally)
            elif neighbor_owner == -1:
                has_neutral_neighbor = True
                all_friendly = False
            else:
                has_enemy_neighbor = True
                all_friendly = False

        # Completely safe: all neighbors are friendly
        if all_friendly:
            garrison = 0
        # High danger: adjacent to enemy
        elif has_enemy_neighbor:
            # Medium danger if mixed: has both enemy AND friendly neighbors
            # (Less dangerous than enemy-only frontier)
            friendly_count = sum(
                1 for n in neighbors
                if self.ai_player.is_friendly_territory(game_state.territory_owners.get(n, -1), game_state)
            )
            if friendly_count >= len(neighbors) // 2:
                # At least half neighbors are friendly - medium danger
                garrison = 2
            else:
                # Mostly surrounded by enemies/neutrals - high danger
                garrison = 3
        # Has neutral neighbors - check if enemies are nearby
        elif has_neutral_neighbor:
            # Check 2 territories out (through neutral neighbors)
            enemy_nearby = False
            for neutral_neighbor in neighbors:
                neighbor_owner = game_state.territory_owners.get(neutral_neighbor, -1)
                if neighbor_owner != -1:  # Not neutral, skip
                    continue

                # Check neighbors of this neutral territory
                second_level = map_data.get_neighbors(neutral_neighbor)
                for second_neighbor in second_level:
                    second_owner = game_state.territory_owners.get(second_neighbor, -1)
                    if second_owner not in [-1, player_index]:
                        # Enemy is 2 territories away (through neutral)
                        enemy_nearby = True
                        break
                if enemy_nearby:
                    break

            garrison = 1 if enemy_nearby else 0  # Low danger if enemy nearby, safe if not
        else:
            # Default: keep 1 army
            garrison = 1

        # Hard AI: Reduce garrison by 1 (more aggressive, willing to take risks)
        if self.ai_player.difficulty == 2:  # Hard difficulty
            garrison = max(0, garrison - 1)

        # Tiered war economy: More excess gold = lower garrison (can replace units fast)
        # Thresholds scaled to 10/15/20 income tiers
        player_gold = game_state.player_gold[player_index]
        if player_gold >= 4000:
            garrison = max(0, garrison - 3)   # Tier 3: very aggressive
        elif player_gold >= 2400:
            garrison = max(0, garrison - 2)   # Tier 2: aggressive
        elif player_gold >= 1200:
            garrison = max(0, garrison - 1)   # Tier 1: slightly aggressive

        # Capital Assault: Ensure capital always has minimum garrison
        if game_state.victory_condition == "Capital Assault":
            capital = game_state.player_starting_territories.get(player_index)
            if territory == capital:
                # Capital should always have at least 5 armies for defense
                garrison = max(garrison, 5)
                logger.debug(f"Capital Defense: Player {player_index + 1} capital {territory} garrison: {garrison}")

        return garrison

    def _score_attack_target(self, from_territory, to_territory, available_army, game_state, player_index, cache=None):
        """
        Score an attack target.

        Factors:
        - Win probability (army strength comparison)
        - Territory value
        - Strategic position
        - Expansion progress (toward victory)
        - Risk assessment

        Args:
            cache: Optional TurnCache with pre-computed values for performance

        Returns:
            float: Attack score (0-100)
        """
        score = 0.0

        # TurnCache: compute territory_count ONCE at top (was computed twice at ~493 and ~562)
        territory_count = cache.territory_count if cache else sum(
            1 for owner in game_state.territory_owners.values()
            if owner == self.ai_player.player_index
        )

        # Enemy garrison - IMPORTANT: Use total armies (all garrisons)
        # TurnCache: use cached territory_armies to avoid per-territory garrison scan
        enemy_garrison = cache.territory_armies.get(to_territory, 0) if cache else game_state.get_territory_total_armies(to_territory)
        has_keep = self._territory_has_keep(to_territory, game_state)
        is_neutral = game_state.territory_owners.get(to_territory, -1) == -1

        # Calculate strength (simple comparison for now)
        our_strength = available_army
        # M15 FIX: Keep defense bonus adds +10 to defender's effective strength
        # instead of a percentage multiplier, making keeps consistently valuable
        enemy_strength = enemy_garrison + (10 if has_keep else 0)

        # Win probability - allow attacks with equal or slightly fewer forces
        # The difficulty-based checks below will filter appropriately
        # Only skip if we're significantly outnumbered (< 60% of enemy strength)
        if our_strength < enemy_strength * 0.6:
            return 0.0  # Don't attack if severely outmatched

        # Neutral territories are easy targets - always allow if we have 1+ army
        if is_neutral:
            if available_army < 1:
                return 0.0

            if enemy_garrison == 0:
                # Empty neutral - FREE REAL ESTATE! RAMPAGE MODE ACTIVATED!
                strength_ratio = 100.0
                score += 120.0  # MASSIVE priority - go on a rampage claiming free territories!

                # EARLY GAME BONUS - At game start, neutral conquest is EVERYTHING
                # territory_count already computed once at top of method
                if territory_count < 16:
                    # Early game - add HUGE bonus for neutral expansion
                    # This ensures AI uses ALL armies for expansion until 16 territories
                    score += 100.0  # Total: 220+ points for empty neutrals in early game!
            else:
                # Neutral with garrison - still easier than enemy
                strength_ratio = our_strength / max(enemy_strength, 1)
                if strength_ratio < 1.5:  # Need at least 1.5x strength for neutrals with garrison
                    return 0.0
                score += min(strength_ratio * 20.0, 40.0)
        else:
            # Enemy territory
            strength_ratio = our_strength / max(enemy_strength, 1)

            # Difficulty-based aggression for enemy territories
            # Tiered gold thresholds: More gold = more reckless attacks
            difficulty = self.ai_player.difficulty
            player_gold = game_state.player_gold[player_index]

            # Base minimum ratios
            # Easy=1.0 (equal forces), Medium=0.7 (slight disadvantage ok), Hard=0.5 (attacks even outnumbered)
            base_min_ratio = [1.0, 0.7, 0.5][difficulty]

            # Tiered gold aggression: higher gold = willing to attack with worse odds
            # Thresholds scaled to 10/15/20 income tiers
            if player_gold >= 4000:
                min_ratio = max(0.3, base_min_ratio - 0.5)   # Tier 3: very reckless
            elif player_gold >= 2400:
                min_ratio = max(0.35, base_min_ratio - 0.4)  # Tier 2: aggressive
            elif player_gold >= 1200:
                min_ratio = max(0.5, base_min_ratio - 0.2)   # Tier 1: somewhat aggressive
            else:
                min_ratio = base_min_ratio

            if strength_ratio < min_ratio:
                return 0.0  # Not aggressive enough for this difficulty

            # Score based on strength ratio (lower threshold = more attack candidates)
            score += min(strength_ratio * 25.0, 50.0)  # Increased from 20/40 to 25/50

        # Territory value
        # M23 FIX: Use cached scorer instead of creating per call
        territory_value = self._scorer.calculate_territory_value(to_territory, game_state, player_index)
        score += territory_value * 0.3

        # Strategic position (neighbor count)
        neighbors = map_data.get_neighbors(to_territory)
        score += min(len(neighbors), 6) * 3.0

        # Extra bonus for neutral territories (encourage expansion)
        if is_neutral:
            score += 50.0  # Neutrals are EXTREMELY attractive - rampage mode!

        # LARGE ARMY BONUS - Use big armies for offense, not defense!
        # If we have a large concentrated force (10+ armies), heavily prioritize attacking
        if available_army >= 10:
            # Massive bonus for using large armies offensively
            # 10 armies = +30, 15 armies = +45, 20 armies = +60, etc.
            large_army_bonus = (available_army - 9) * 3.0
            score += min(large_army_bonus, 60.0)  # Cap at +60 bonus
        elif available_army >= 5:
            # Medium bonus for decent-sized armies
            score += (available_army - 4) * 2.0

        # Expansion progress bonus (territory_count already computed once at top of method)
        if territory_count >= 25:
            score += 30.0  # Victory push bonus

        # Risk: Check for counterattack potential
        will_trigger_counterattack = self._check_counterattack_risk(
            from_territory, to_territory, game_state, player_index
        )
        if will_trigger_counterattack:
            score -= 20.0

        return max(score, 0.0)

    def _territory_has_keep(self, territory, game_state):
        """Check if territory has a Keep"""
        if territory not in game_state.buildings:
            return False
        return 'Keep' in game_state.buildings[territory].values()

    def _check_counterattack_risk(self, from_territory, to_territory, game_state, player_index):
        """Check if attacking will expose us to counterattack"""
        # After attacking, from_territory will be weakened
        # IMPORTANT: Check AI player's garrison specifically
        garrison = game_state.territory_garrisons.get(from_territory, {}).get(player_index)
        if garrison:
            # Calculate: moved armies will leave, unmoved stay (minus what we're attacking with)
            remaining_garrison = garrison.get('moved', 0) + 1  # Keep at least 1
        else:
            remaining_garrison = 0

        # Check for strong enemy neighbors
        neighbors = map_data.get_neighbors(from_territory)
        for neighbor in neighbors:
            if neighbor == to_territory:
                continue

            owner = game_state.territory_owners.get(neighbor, -1)
            if owner != player_index and owner != -1:
                # IMPORTANT: Use total armies (all garrisons) for threat assessment
                enemy_army = game_state.get_territory_total_armies(neighbor)
                if enemy_army > remaining_garrison * 1.5:
                    return True  # Risky!

        return False


class DefenseCoordinator:
    """Manages defensive reinforcements and army consolidation"""

    def __init__(self, ai_player):
        """Initialize defense coordinator.

        Args:
            ai_player: AIPlayer instance for accessing helper methods
        """
        self.ai_player = ai_player
        # Create attack planner for pathfinding utilities
        self.attack_planner = AttackPlanner(ai_player)

    # ---- Shared garrison-check and order-queuing helpers ----

    def _get_territories_with_available_garrison(self, game_state, player_index, min_available=1):
        """
        Find all territories where the AI player has unmoved armies available to move.

        Extracts the common garrison-discovery + availability-check pattern shared by
        plan_reinforcement_moves and plan_strategic_repositioning. Both methods need
        to iterate territories with garrison and check for unmoved armies >= min_available.

        Args:
            game_state: GameState instance
            player_index (int): Player index
            min_available (int): Minimum unmoved armies required (default 1)

        Returns:
            list: [(territory, available_unmoved_count), ...] for territories with
                  enough unmoved armies. Only includes territories where the player
                  has total garrison (unmoved + moved) > 0 AND unmoved >= min_available.
        """
        result = []
        for territory, garrisons in game_state.territory_garrisons.items():
            if player_index in garrisons:
                garrison = garrisons[player_index]
                # First check: territory must have any garrison (unmoved + moved > 0)
                if garrison.get('unmoved', 0) + garrison.get('moved', 0) > 0:
                    # Second check: must have enough unmoved armies
                    available = garrison.get('unmoved', 0)
                    if available >= min_available:
                        result.append((territory, available))
        return result

    def _get_territory_available_garrison(self, game_state, player_index, territory):
        """
        Get the unmoved army count for a specific territory's garrison.

        Extracts the garrison-check pattern used in plan_defensive_moves where
        we check a specific neighbor territory for available armies.

        Args:
            game_state: GameState instance
            player_index (int): Player index
            territory (str): Territory to check

        Returns:
            int: Number of unmoved armies the player has in this territory
        """
        # CRITICAL: Check AI player's garrison, not owner's legacy array
        garrison = game_state.territory_garrisons.get(territory, {}).get(player_index)
        return garrison.get('unmoved', 0) if garrison else 0

    def _try_queue_move(self, moves_list, from_territory, to_territory, send_count, game_state, max_send=None):
        """
        Attempt to queue a movement order, checking destination army limit.

        Extracts the common order-queuing pattern: check space at destination,
        cap send_count by available space (and optional max_send), append to moves list.

        Args:
            moves_list (list): List to append (from, to, count) tuple to
            from_territory (str): Source territory
            to_territory (str): Destination territory
            send_count (int): Desired number of armies to send
            game_state: GameState instance
            max_send (int): Optional cap on armies to send (e.g. 3 for repositioning)

        Returns:
            bool: True if a move was queued, False if destination was full or no armies to send
        """
        # Check army limit at destination - IMPORTANT: Use total armies (all garrisons)
        current_at_dest = game_state.get_territory_total_armies(to_territory)
        space_available = game_state.MAX_ARMIES_PER_TERRITORY - current_at_dest

        if space_available <= 0:
            return False  # Destination is full

        # Cap by space available and optional max_send
        actual_send = min(send_count, space_available)
        if max_send is not None:
            actual_send = min(actual_send, max_send)

        if actual_send > 0:
            moves_list.append((from_territory, to_territory, actual_send))
            return True
        return False

    # ---- Movement planning methods (use shared helpers) ----

    def plan_reinforcement_moves(self, game_state, player_index):
        """
        Plan reinforcement moves for territories with excess armies.

        This aggressively consolidates armies from safe interior territories to frontier
        territories. Safe interior = surrounded entirely by friendly territories.
        These territories need ZERO garrison since they face no threat.

        Args:
            game_state: GameState instance
            player_index (int): Player index

        Returns:
            list: [(from_territory, to_territory, army_count), ...] reinforcement moves
        """
        reinforcement_moves = []

        # Find territories with available unmoved garrison (uses shared helper)
        territories_with_garrison = self._get_territories_with_available_garrison(
            game_state, player_index, min_available=1
        )

        for territory, available in territories_with_garrison:
            # Only send from safe interior territories (all neighbors friendly, including allies)
            neighbors = map_data.get_neighbors(territory)
            all_friendly = all(
                self.ai_player.is_friendly_territory(game_state.territory_owners.get(n, -1), game_state)
                for n in neighbors
            )

            if not all_friendly:
                continue  # Not safe interior, don't send reinforcements

            # Find a frontier territory to reinforce (friendly neighbor with enemy/neutral neighbors)
            for neighbor in neighbors:
                neighbor_owner = game_state.territory_owners.get(neighbor, -1)

                # Skip non-friendly territories (only reinforce self or allies)
                if not self.ai_player.is_friendly_territory(neighbor_owner, game_state):
                    continue

                # Check if this neighbor is on the frontier (has expansion opportunities)
                neighbor_neighbors = map_data.get_neighbors(neighbor)
                has_expansion_opportunity = any(
                    not self.ai_player.is_friendly_territory(game_state.territory_owners.get(nn, -1), game_state)
                    for nn in neighbor_neighbors
                )

                if has_expansion_opportunity:
                    # Queue move using shared helper (checks destination capacity)
                    if self._try_queue_move(reinforcement_moves, territory, neighbor, available, game_state):
                        break  # Only one reinforcement per source territory

        return reinforcement_moves

    def plan_strategic_repositioning(self, game_state, player_index, max_moves=2, cache=None):
        """
        Move armies from deep interior (surrounded by allies) toward the frontier.
        This helps AI unstick armies that are trapped behind allied lines.

        Args:
            game_state: GameState instance
            player_index (int): Player index
            max_moves (int): Maximum repositioning moves to plan
            cache: Optional TurnCache with pre-computed values for performance

        Returns:
            list: [(from_territory, to_territory, army_count), ...] repositioning moves
        """
        repositioning_moves = []

        # Find territories with available unmoved garrison (uses shared helper)
        territories_with_garrison = self._get_territories_with_available_garrison(
            game_state, player_index, min_available=1
        )

        for territory, available in territories_with_garrison:
            # Check if surrounded by allies (no adjacent enemies)
            neighbors = map_data.get_neighbors(territory)
            has_adjacent_enemy = any(
                not self.ai_player.is_friendly_territory(game_state.territory_owners.get(n, -1), game_state)
                for n in neighbors
            )

            if has_adjacent_enemy:
                continue  # Already at frontier, no need to reposition

            # Find path to frontier through allied territory
            reachable_enemies = self.attack_planner.find_reachable_enemies(
                game_state, territory, max_distance=4
            )

            if not reachable_enemies:
                continue  # No reachable enemies, stay put

            # Move toward the closest frontier (allied neighbor closer to enemies)
            best_neighbor = None
            best_distance = float('inf')

            for neighbor in neighbors:
                neighbor_owner = game_state.territory_owners.get(neighbor, -1)

                # Only move to allied territories
                if not self.ai_player.is_friendly_territory(neighbor_owner, game_state):
                    continue

                # Check how close this neighbor is to enemies
                neighbor_reachable = self.attack_planner.find_reachable_enemies(
                    game_state, neighbor, max_distance=4
                )

                if neighbor_reachable:
                    min_distance = min(neighbor_reachable.values())
                    if min_distance < best_distance:
                        best_distance = min_distance
                        best_neighbor = neighbor

            if best_neighbor:
                # Queue move using shared helper (checks destination capacity, caps at 3 armies)
                self._try_queue_move(repositioning_moves, territory, best_neighbor, available, game_state, max_send=3)

                if len(repositioning_moves) >= max_moves:
                    break

        return repositioning_moves

    def plan_defensive_moves(self, game_state, player_index, threatened_territories):
        """
        Plan defensive reinforcements for threatened territories.

        Args:
            game_state: GameState instance
            player_index (int): Player index
            threatened_territories (list): [(territory, threat_level), ...]

        Returns:
            list: [(from_territory, to_territory, army_count), ...] defensive moves
        """
        defensive_moves = []

        for territory, threat_level in threatened_territories[:3]:  # Top 3 threats
            # Find nearby territories with spare armies
            neighbors = map_data.get_neighbors(territory)

            for neighbor in neighbors:
                owner = game_state.territory_owners.get(neighbor, -1)
                if owner != player_index:
                    continue

                # Get available garrison using shared helper
                available = self._get_territory_available_garrison(game_state, player_index, neighbor)

                # Send half of available armies (keep some for defense)
                if available >= 2:
                    # Queue move: send at most half, shared helper checks destination capacity
                    send_count = available // 2
                    if self._try_queue_move(defensive_moves, neighbor, territory, send_count, game_state):
                        break  # One reinforcement per threatened territory

        return defensive_moves


class TrainingPlanner:
    """Decides what units to train"""

    def __init__(self, ai_player):
        self.ai_player = ai_player
        self.composer = ArmyComposer()

    def plan_training(self, game_state, available_budget, cache=None):
        """
        Plan unit training for all Barracks.

        Args:
            game_state: GameState instance
            available_budget (int): Gold available for training
            cache: Optional TurnCache with pre-computed values for performance

        Returns:
            list: [('train', {territory, barracks_plot, unit_type}), ...]
        """
        player_index = self.ai_player.player_index
        training_actions = []
        spent = 0

        # Check command limit before planning any training
        # TurnCache: use cached army count to avoid re-scanning all garrisons
        current_command = cache.player_army_count if cache else game_state.get_player_army_count(player_index)
        command_limit = game_state.player_command_limit[player_index]
        if current_command >= command_limit:
            # Already at command limit, don't plan any training
            return training_actions

        # Track how many units we're planning to train (to not exceed command limit)
        planned_units = 0
        available_command = command_limit - current_command

        # Find all owned territories with Barracks
        # TurnCache: use cached owned_territories list to avoid re-scanning territory_owners
        owned_territories = cache.owned_territories if cache else [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]

        for territory in owned_territories:
            if territory not in game_state.buildings:
                continue

            # Skip territory if already at army cap (units would have nowhere to go)
            # TurnCache: use cached territory_armies to avoid per-territory garrison scan
            territory_armies = cache.territory_armies.get(territory, 0) if cache else game_state.get_territory_total_armies(territory)
            if territory_armies >= game_state.MAX_ARMIES_PER_TERRITORY:
                continue

            # Find Barracks in this territory
            for plot_idx, building_type in game_state.buildings[territory].items():
                if building_type != 'Barracks':
                    continue

                # Try to fill the training queue (up to 4 units)
                queue_size = 0
                if territory in game_state.training_queue:
                    if plot_idx in game_state.training_queue[territory]:
                        queue_size = len(game_state.training_queue[territory][plot_idx])

                # Train multiple units to fill the queue
                while queue_size < 4:
                    # Check if we would exceed command limit with planned training
                    if planned_units >= available_command:
                        break  # Would exceed command limit
                    # Decide what unit to train
                    unit_type = self._select_unit_type(territory, game_state, player_index)

                    # Check cost
                    unit_costs = {'Swordsman': 25, 'Archer': 20, 'Pikeman': 30, 'Cavalry': 40}
                    cost = game_state.get_effective_cost(unit_type, unit_costs[unit_type], player_index)

                    if spent + cost > available_budget:
                        break  # Can't afford more units

                    # Add training action
                    training_actions.append(('train', {
                        'territory': territory,
                        'barracks_plot': plot_idx,
                        'unit_type': unit_type
                    }))
                    spent += cost
                    queue_size += 1  # Track simulated queue size
                    planned_units += 1  # Track planned units against command limit

                    # Continue training until budget is exhausted or command limit reached
                    if spent >= available_budget or planned_units >= available_command:
                        break

                # Check if we've exhausted the budget or command limit
                if spent >= available_budget or planned_units >= available_command:
                    break

            if spent >= available_budget or planned_units >= available_command:
                break

        return training_actions

    def _select_unit_type(self, territory, game_state, player_index):
        """
        Select which unit type to train.

        Considers:
        - Enemy composition (counter system)
        - Current army balance
        - Cost efficiency

        Returns:
            str: Unit type to train
        """
        # Check enemy neighbors
        neighbors = map_data.get_neighbors(territory)
        enemy_neighbors = [
            n for n in neighbors
            if game_state.territory_owners.get(n, -1) not in [-1, player_index]
        ]

        if enemy_neighbors:
            # Get enemy composition
            enemy_comp = {}
            for enemy_terr in enemy_neighbors:
                comp = self.composer.get_enemy_composition(enemy_terr, game_state)
                for unit_type, count in comp.items():
                    enemy_comp[unit_type] = enemy_comp.get(unit_type, 0) + count

            # Get counter composition
            ideal_comp = self.composer.calculate_counter_composition(enemy_comp, game_state)

            # Pick unit type with highest ratio
            unit_type = max(ideal_comp.items(), key=lambda x: x[1])[0]
            return unit_type

        # No enemies nearby - balanced mix (weighted random)
        units = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
        weights = [0.25, 0.25, 0.25, 0.25]

        return random.choices(units, weights=weights)[0]


class MilitaryCommander:
    """Main military decision coordinator"""

    def __init__(self, ai_player):
        """
        Initialize military commander.

        Args:
            ai_player: AIPlayer instance (parent)
        """
        self.ai_player = ai_player
        self.composer = ArmyComposer()
        self.attack_planner = AttackPlanner(ai_player)
        self.defense_coordinator = DefenseCoordinator(ai_player)
        self.training_planner = TrainingPlanner(ai_player)

    def plan_military_actions(self, game_state, strategic_priority, budget, threats, cache=None):
        """
        Plan all military actions for this turn.

        Args:
            game_state: GameState instance
            strategic_priority (str): Strategic mode
            budget (int): Gold available for military spending
            threats (list): Threatened territories
            cache: Optional TurnCache with pre-computed values for performance

        Returns:
            list: List of military actions
        """
        actions = []
        player_index = self.ai_player.player_index

        # 1. Training (allocate ~60% of military budget)
        training_budget = int(budget * 0.6)
        training_actions = self.training_planner.plan_training(game_state, training_budget, cache=cache)
        actions.extend(training_actions)

        # 2. Movement orders based on strategy
        if strategic_priority == 'defense':
            # Defensive moves (threatened territories)
            defensive_moves = self.defense_coordinator.plan_defensive_moves(
                game_state, player_index, threats
            )
            for from_terr, to_terr, army_count in defensive_moves:
                actions.append(('move', {'from': from_terr, 'to': to_terr, 'army_count': army_count}))

        # 3. Consolidate interior armies to frontier (always do this)
        reinforcement_moves = self.defense_coordinator.plan_reinforcement_moves(
            game_state, player_index
        )
        for from_terr, to_terr, army_count in reinforcement_moves:
            actions.append(('move', {'from': from_terr, 'to': to_terr, 'army_count': army_count}))

        # 3b. Strategic repositioning (move armies stuck behind ally lines toward frontier)
        repositioning_moves = self.defense_coordinator.plan_strategic_repositioning(
            game_state, player_index, max_moves=2, cache=cache
        )
        for from_terr, to_terr, army_count in repositioning_moves:
            actions.append(('move', {'from': from_terr, 'to': to_terr, 'army_count': army_count}))

        # 4. Offensive moves (always check, use aggression to scale)
        # Check territory count for early game aggression
        # TurnCache: use cached territory_count to avoid re-scanning territory_owners
        territory_count = cache.territory_count if cache else sum(
            1 for owner in game_state.territory_owners.values()
            if owner == player_index
        )
        is_early_game = territory_count < 16

        # Check if we have any large army concentrations (10+ armies)
        # FIX: Check TOTAL armies (unmoved + moved), not just unmoved
        has_large_army = any(
            (game_state.territory_garrisons.get(t, {}).get(player_index, {}).get('unmoved', 0) +
             game_state.territory_garrisons.get(t, {}).get(player_index, {}).get('moved', 0)) >= 10
            for t, owner in game_state.territory_owners.items()
            if owner == player_index
        )

        # Tiered gold aggression: More gold = more attacks launched
        # Thresholds scaled to 10/15/20 income tiers
        player_gold = game_state.player_gold[player_index]
        if player_gold >= 4000:
            gold_tier = 3
        elif player_gold >= 2400:
            gold_tier = 2
        elif player_gold >= 1200:
            gold_tier = 1
        else:
            gold_tier = 0
        has_excess_gold = gold_tier >= 1

        # Check if in conquest_push mode (triggered by excess resources)
        is_conquest_mode = strategic_priority == 'conquest_push'

        # Determine attack behavior:
        # - Early game, large armies, excess gold, or conquest mode = ALWAYS attack
        # - Otherwise use difficulty-scaled aggression
        should_always_attack = is_early_game or has_large_army or has_excess_gold or is_conquest_mode

        if should_always_attack:
            attack_chance = 1.0  # 100% attack chance
            # Tiered max attacks: higher gold = more simultaneous attacks
            if is_conquest_mode:
                max_attacks = 5
            elif gold_tier >= 3:
                max_attacks = 7   # Tier 3: all-out offensive
            elif gold_tier >= 2:
                max_attacks = 5   # Tier 2: strong offensive
            elif gold_tier >= 1:
                max_attacks = 4   # Tier 1: moderate push
            else:
                max_attacks = 3
        else:
            base_attack_chance = 0.3  # 30% base chance even for defensive AI
            attack_chance = max(base_attack_chance, self.ai_player.config['attack_aggression'])
            max_attacks = 3

        attack_roll = random.random()
        if attack_roll < attack_chance:
            attacks = self.attack_planner.select_attack_targets(game_state, max_attacks=max_attacks, cache=cache)
            for from_terr, to_terr, army_count in attacks:
                actions.append(('move', {'from': from_terr, 'to': to_terr, 'army_count': army_count}))

        return actions


# Test the military module if run directly
if __name__ == '__main__':
    logger.info("AI Military Module Test")
    logger.info("=" * 60)
    logger.info("Module loaded successfully")
    logger.info("Classes available:")
    logger.info("  - ArmyComposer: Unit composition calculations")
    logger.info("  - AttackPlanner: Attack target selection")
    logger.info("  - DefenseCoordinator: Defensive reinforcement planning")
    logger.info("  - TrainingPlanner: Unit training decisions")
    logger.info("  - MilitaryCommander: Military decision coordinator")
