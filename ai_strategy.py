"""
AI Strategy Module
Strategic evaluation and decision-making for AI opponents.

This module provides territory evaluation, threat detection, and opportunity
analysis. It's the "brain" that helps AI make strategic decisions about
where to expand, what to defend, and which territories are most valuable.

Classes:
    TerritoryScorer: Evaluates territory value based on income, position, buildings
    ThreatAnalyzer: Detects threats from enemy forces
    OpportunityDetector: Identifies expansion and attack opportunities
    StrategyEvaluator: Main strategic analysis coordinator
"""

import map_data

from utils.logger import get_logger
logger = get_logger(__name__)

# FPS OPTIMIZATION 5B: Dispatch dict replaces if/elif chain in _evaluate_buildings
_BUILDING_VALUES = {'Farm': 3.0, 'Mine': 4.0, 'Barracks': 5.0, 'Keep': 7.0, 'Square': 6.0}


class TerritoryScorer:
    """Evaluates territory strategic value (0-100 score)"""

    def calculate_territory_value(self, territory, game_state, player_index):
        """
        Calculate strategic value of a territory.

        Scoring factors:
        - Base income (0-15 points): Higher income territories worth more
        - Building potential (0-20 points): More plots = more development
        - Strategic position (0-15 points): More neighbors = more strategic
        - Existing buildings (0-30 points): Income/defense buildings add value
        - Adjacency to owned (0-20 points): Easier to defend/supply

        Args:
            territory (str): Territory name
            game_state: GameState instance
            player_index (int): Player evaluating the territory

        Returns:
            float: Territory value score (0-100)
        """
        score = 0.0

        # Factor 1: Base income (0-15 points)
        base_income = map_data.get_territory_income(territory)
        score += (base_income / 20.0) * 15.0

        # Factor 2: Building potential (0-20 points)
        plots = map_data.TERRITORY_PLOTS.get(territory, [])
        plot_count = len(plots)
        score += min(plot_count, 4) * 5.0  # Max 20 points for 4+ plots

        # Factor 3: Strategic position - centrality (0-15 points)
        neighbors = map_data.get_neighbors(territory)
        neighbor_count = len(neighbors)
        score += min(neighbor_count, 6) * 2.5  # Max 15 points for 6+ neighbors

        # Factor 4: Existing buildings value (0-30 points)
        building_value = self._evaluate_buildings(territory, game_state)
        score += building_value

        # Factor 5: Adjacency bonus - easier to defend (0-20 points)
        adjacency_bonus = self._calculate_adjacency_bonus(
            territory, game_state, player_index
        )
        score += adjacency_bonus

        return min(score, 100.0)

    def _evaluate_buildings(self, territory, game_state):
        """
        Evaluate value of buildings in a territory.

        Returns:
            float: Building value (0-30 points)
        """
        if territory not in game_state.buildings:
            return 0.0

        value = 0.0
        buildings = game_state.buildings[territory]

        for plot_idx, building_type in buildings.items():
            # FPS OPTIMIZATION 5B: Dict lookup replaces if/elif chain
            value += _BUILDING_VALUES.get(building_type, 0.0)

        return min(value, 30.0)

    def _calculate_adjacency_bonus(self, territory, game_state, player_index):
        """
        Calculate bonus for territories adjacent to owned territories.

        Territories connected to our empire are easier to defend and supply.

        Returns:
            float: Adjacency bonus (0-20 points)
        """
        neighbors = map_data.get_neighbors(territory)
        friendly_neighbors = 0

        for neighbor in neighbors:
            owner = game_state.territory_owners.get(neighbor, -1)
            if owner == player_index:
                friendly_neighbors += 1

        # Each friendly neighbor adds value (max 20 points for 4+ neighbors)
        return min(friendly_neighbors * 5.0, 20.0)


class ThreatAnalyzer:
    """Analyzes military threats to territories"""

    def calculate_territory_threat(self, territory, game_state, player_index, cache=None):
        """
        Calculate threat level to a territory.

        Threat factors:
        - Enemy armies at borders
        - Army strength comparison
        - Number of enemy neighbors
        - Undefended status

        Args:
            territory (str): Territory name
            game_state: GameState instance
            player_index (int): Player evaluating threat
            cache: Optional TurnCache with pre-computed values

        Returns:
            float: Threat level (0-100)
        """
        threat = 0.0

        owner = game_state.territory_owners.get(territory, -1)
        # FPS OPTIMIZATION 5B: Use cached territory armies when available
        # IMPORTANT: Use total armies (all garrisons) for threat assessment
        garrison = cache.territory_armies[territory] if cache else game_state.get_territory_total_armies(territory)
        neighbors = map_data.get_neighbors(territory)

        # M15 FIX: Account for keep defense bonus in threat calculation
        # Territories with a Keep get +10 effective defensive strength, reducing perceived threat
        effective_garrison = garrison
        if game_state.has_fortress(territory):
            effective_garrison += 10

        for neighbor in neighbors:
            neighbor_owner = game_state.territory_owners.get(neighbor, -1)

            # Enemy neighbor increases threat
            if neighbor_owner != owner and neighbor_owner != -1 and neighbor_owner != player_index:
                # FPS OPTIMIZATION 5B: Use cached territory armies when available
                # IMPORTANT: Use total armies (all garrisons) for threat assessment
                enemy_army = cache.territory_armies[neighbor] if cache else game_state.get_territory_total_armies(neighbor)

                # Undefended territory at enemy border = HIGH threat
                if effective_garrison == 0:
                    threat += 30.0
                else:
                    # Calculate enemy superiority (using effective garrison with keep bonus)
                    superiority = (enemy_army - effective_garrison) / max(effective_garrison, 1)
                    threat += max(0, superiority * 20.0)

                # Multiple enemy neighbors compound threat
                threat += 5.0

        return min(threat, 100.0)

    def find_threatened_territories(self, game_state, player_index, threshold=30.0, cache=None):
        """
        Find all owned territories under threat.

        Args:
            game_state: GameState instance
            player_index (int): Player to check
            threshold (float): Minimum threat level to include
            cache: Optional TurnCache with pre-computed values

        Returns:
            list: [(territory, threat_level), ...] sorted by threat (highest first)
        """
        threatened = []

        # FPS OPTIMIZATION 5B: Use cached owned territories when available
        if cache:
            owned_territories = cache.owned_territories
        else:
            owned_territories = [
                t for t, owner in game_state.territory_owners.items()
                if owner == player_index
            ]

        for territory in owned_territories:
            threat = self.calculate_territory_threat(territory, game_state, player_index, cache=cache)
            if threat >= threshold:
                threatened.append((territory, threat))

        # Sort by threat level (highest first)
        threatened.sort(key=lambda x: x[1], reverse=True)
        return threatened

    def is_capital_threatened(self, game_state, player_index):
        """
        Check if player's capital has enemy units nearby (Capital Assault mode).

        This method is specifically for Capital Assault victory condition, where
        defending the capital is critical. Returns True if enemy armies are in
        adjacent territories.

        Args:
            game_state: GameState instance
            player_index (int): Player to check

        Returns:
            bool: True if capital has enemy neighbors with armies
        """
        # Get player's capital territory
        capital = game_state.player_starting_territories.get(player_index)
        if not capital:
            return False

        # Check adjacent territories for enemies
        adjacent = map_data.get_neighbors(capital)
        for adj_terr in adjacent:
            owner = game_state.territory_owners.get(adj_terr, -1)
            # Check if territory is owned by enemy and has armies
            if owner >= 0 and owner != player_index:
                if game_state.get_territory_total_armies(adj_terr) > 0:
                    return True

        return False


class OpportunityDetector:
    """Identifies expansion and attack opportunities"""

    def __init__(self):
        # M23 FIX: Cache TerritoryScorer to avoid per-call instantiation
        self._scorer = TerritoryScorer()

    def find_expansion_targets(self, game_state, player_index, cache=None):
        """
        Find territories that are good expansion targets.

        Criteria for good targets:
        - Adjacent to owned territories
        - Neutral or weakly defended
        - High strategic value
        - Winnable with available forces

        Args:
            game_state: GameState instance
            player_index (int): Player evaluating opportunities
            cache: Optional TurnCache with pre-computed values

        Returns:
            list: [(territory, score), ...] sorted by score (best first)
        """
        # M23 FIX: Use cached scorer instead of creating per call
        scorer = self._scorer
        targets = []

        # FPS OPTIMIZATION 5B: Use cached owned territories when available
        owned_territories = cache.owned_territories if cache else [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]

        # FPS OPTIMIZATION 5B: Use set for O(1) duplicate check instead of O(n) linear scan
        seen_targets = set()

        # Check neighbors of owned territories
        for owned_terr in owned_territories:
            neighbors = map_data.get_neighbors(owned_terr)

            for neighbor in neighbors:
                neighbor_owner = game_state.territory_owners.get(neighbor, -1)

                # Skip if friendly (owned by self or ally)
                if neighbor_owner == player_index:
                    continue  # Own territory
                if neighbor_owner >= 0 and game_state.are_allies(player_index, neighbor_owner):
                    continue  # Ally territory

                # FPS OPTIMIZATION 5B: O(1) set lookup instead of O(n) list scan
                if neighbor in seen_targets:
                    continue
                seen_targets.add(neighbor)

                # Evaluate as target
                value_score = scorer.calculate_territory_value(
                    neighbor, game_state, player_index
                )
                # FPS OPTIMIZATION 5B: Use cached territory armies when available
                # IMPORTANT: Use total armies (all garrisons) to evaluate enemy strength
                enemy_garrison = cache.territory_armies[neighbor] if cache else game_state.get_territory_total_armies(neighbor)

                # CRITICAL: Check AI player's garrison, not owner's legacy array
                garrison = game_state.territory_garrisons.get(owned_terr, {}).get(player_index)
                available_army = garrison.get('unmoved', 0) if garrison else 0

                # Calculate winability (can we take it?)
                if available_army > enemy_garrison:
                    winability = 50.0  # We have advantage
                else:
                    winability = 20.0  # Harder target

                # Combine scores
                total_score = value_score * 0.6 + winability * 0.4

                targets.append((neighbor, total_score, owned_terr))  # Include source

        # Sort by score (best first)
        targets.sort(key=lambda x: x[1], reverse=True)
        return targets

    def find_weak_enemy_territories(self, game_state, player_index, cache=None):
        """
        Find enemy territories that are vulnerable to attack.

        Args:
            game_state: GameState instance
            player_index (int): Player evaluating targets
            cache: Optional TurnCache with pre-computed values

        Returns:
            list: [(territory, weakness_score), ...] sorted by weakness
        """
        weak_targets = []

        for territory, owner in game_state.territory_owners.items():
            # Skip neutral, owned, and ally territories
            if owner == -1 or owner == player_index:
                continue
            if owner >= 0 and game_state.are_allies(player_index, owner):
                continue  # Skip ally territories

            # Check if adjacent to our territories
            neighbors = map_data.get_neighbors(territory)
            adjacent_to_us = any(
                game_state.territory_owners.get(n, -1) == player_index
                for n in neighbors
            )

            if not adjacent_to_us:
                continue

            # FPS OPTIMIZATION 5B: Use cached territory armies when available
            # Calculate weakness (low garrison = more weak)
            # IMPORTANT: Use total armies (all garrisons) to assess enemy strength
            garrison = cache.territory_armies[territory] if cache else game_state.get_territory_total_armies(territory)
            weakness = max(0, 20 - garrison)  # Weaker if fewer armies

            if weakness > 0:
                weak_targets.append((territory, weakness))

        weak_targets.sort(key=lambda x: x[1], reverse=True)
        return weak_targets


class StrategyEvaluator:
    """Main strategic analysis coordinator"""

    def __init__(self, ai_player):
        """
        Initialize strategy evaluator.

        Args:
            ai_player: AIPlayer instance (parent)
        """
        self.ai_player = ai_player
        self.scorer = TerritoryScorer()
        self.threat_analyzer = ThreatAnalyzer()
        self.opportunity_detector = OpportunityDetector()

    def analyze_game_state(self, game_state, cache=None):
        """
        Perform complete strategic analysis of game state.

        Args:
            game_state: GameState instance
            cache: Optional TurnCache with pre-computed values

        Returns:
            dict: Analysis results with keys:
                - 'owned_territories': List of owned territory names
                - 'total_income': Expected income this turn
                - 'total_armies': Total army count
                - 'threats': List of threatened territories
                - 'opportunities': List of expansion targets
                - 'weak_enemies': List of vulnerable enemy territories
        """
        player_index = self.ai_player.player_index

        # FPS OPTIMIZATION 5B: Use cached values when available
        if cache:
            owned_territories = cache.owned_territories
            total_income = cache.player_income
            total_armies = cache.player_army_count
        else:
            owned_territories = [
                t for t, owner in game_state.territory_owners.items()
                if owner == player_index
            ]
            total_income = game_state.calculate_player_income(player_index)
            total_armies = game_state.get_player_army_count(player_index)

        # Strategic analysis
        threats = self.threat_analyzer.find_threatened_territories(game_state, player_index, cache=cache)
        opportunities = self.opportunity_detector.find_expansion_targets(game_state, player_index, cache=cache)
        weak_enemies = self.opportunity_detector.find_weak_enemy_territories(game_state, player_index, cache=cache)

        # Store threats in cache for reuse by get_strategic_priority
        if cache and cache.threats is None:
            cache.threats = threats

        return {
            'owned_territories': owned_territories,
            'territory_count': len(owned_territories),
            'total_income': total_income,
            'total_armies': total_armies,
            'threats': threats,
            'opportunities': opportunities,
            'weak_enemies': weak_enemies,
            'available_gold': game_state.player_gold[player_index]
        }

    def get_strategic_priority(self, game_state, cache=None):
        """
        Determine strategic priority for this turn.

        Args:
            game_state: GameState instance
            cache: Optional TurnCache with pre-computed values

        Returns:
            str: Priority mode - 'defense', 'economy', 'expansion', 'conquest_push', 'victory_push'
        """
        player_index = self.ai_player.player_index

        # FPS OPTIMIZATION 5B: Use cached territory count
        if cache:
            territory_count = cache.territory_count
        else:
            territory_count = sum(
                1 for owner in game_state.territory_owners.values()
                if owner == player_index
            )

        # FPS OPTIMIZATION 5B: Reuse threats from cache, filter by threshold
        if cache and cache.threats is not None:
            threats = [(t, s) for t, s in cache.threats if s >= 40.0]
        else:
            threats = self.threat_analyzer.find_threatened_territories(
                game_state, player_index, threshold=40.0
            )

        # Victory push (near 45 territories)
        if territory_count >= 40:
            return 'victory_push'

        # Defense (critical threats)
        if threats and threats[0][1] >= 50.0:
            return 'defense'

        # Conquest push: excess gold + sufficient armies = aggressive expansion
        # IMPORTANT: Check this BEFORE economy mode so excess gold triggers attacks
        # even in "early game" scenarios. This fixes late-game stagnation.
        player_gold = game_state.player_gold[player_index]
        # FPS OPTIMIZATION 5B: Use cached army count
        if cache:
            total_armies = cache.player_army_count
        else:
            total_armies = sum(
                g.get('unmoved', 0) + g.get('moved', 0)
                for garrisons in game_state.territory_garrisons.values()
                for p, g in garrisons.items() if p == player_index
            )
        # Trigger conquest mode with excess gold and 25+ armies, or very high gold regardless
        # Thresholds scaled to 10/15/20 income tiers
        if (player_gold >= 2400 and total_armies >= 25) or player_gold >= 4000:
            return 'conquest_push'

        # Early game economy (only if not in conquest mode)
        if territory_count < 16:
            return 'economy'

        # Mid/late game expansion
        return 'expansion'


# Test the strategy module if run directly
if __name__ == '__main__':
    from utils.logger import setup_logging
    setup_logging()
    logger.info("AI Strategy Module Test")
    logger.info("=" * 60)
    logger.info("Module loaded successfully")
    logger.info("Classes available:")
    logger.info("  - TerritoryScorer: Territory value evaluation")
    logger.info("  - ThreatAnalyzer: Threat detection")
    logger.info("  - OpportunityDetector: Target identification")
    logger.info("  - StrategyEvaluator: Strategic analysis coordinator")
