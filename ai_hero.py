"""
AI Hero Module
Hero training and ability management for AI opponents.

This module handles:
- Hero selection (which heroes to train)
- Hero ability usage (when and how to use abilities)
- Hero placement strategy

For the initial implementation, we focus on:
- Training economically valuable heroes (Nextroy, Nithieln)
- Basic ability usage for high-impact abilities
- Simple hero placement logic

Classes:
    HeroSelector: Chooses which heroes to train
    AbilityExecutor: Decides when to use hero abilities
    HeroManager: Main hero management coordinator
"""

import random

from utils.logger import get_logger
logger = get_logger(__name__)


class HeroSelector:
    """Chooses which heroes to train"""

    # Hero priorities by difficulty
    HERO_PRIORITIES = {
        0: {  # Easy - Economic focus
            'Halon Nextroy': 90,     # +4 gold per territory
            'Evain Nithieln': 85,    # Economic bonuses
            'Darius Brennhen': 70,   # Simple/cheap
            'Seledra Rennervail': 60,  # Building preservation
        },
        1: {  # Medium - Balanced
            'Halon Nextroy': 85,
            'Aidam Narn': 80,        # Income boost
            'Evain Nithieln': 75,
            'Neil Hévilneu': 70,     # Combat bonus
        },
        2: {  # Hard - Strategic mix
            'Aidam Narn': 90,        # Strong income
            'Neil Hévilneu': 85,     # Combat advantage
            'Halon Nextroy': 80,
            'Erec Silvyr': 75,       # Resource generation
        }
    }

    def select_hero_to_train(self, game_state, player_index, difficulty):
        """
        Select best hero to train.

        Args:
            game_state: GameState instance
            player_index (int): Player index
            difficulty (int): AI difficulty level

        Returns:
            tuple: (hero_type, territory, keep_plot) or None
        """
        # Check hero limit
        current_heroes = len(game_state.heroes[player_index])
        training_heroes = self._count_training_heroes(game_state, player_index)
        hero_limit = game_state.player_hero_limit[player_index]

        if current_heroes + training_heroes >= hero_limit:
            return None

        # Find available heroes
        owned_heroes = set(game_state.heroes[player_index].keys())
        training_hero_types = self._get_training_hero_types(game_state, player_index)

        available_heroes = []
        priorities = self.HERO_PRIORITIES.get(difficulty, {})

        for hero_type, priority in priorities.items():
            # Check if already owned or training
            if hero_type in owned_heroes or hero_type in training_hero_types:
                continue

            # Check affordability
            cost = game_state.HERO_TYPES[hero_type]['cost']
            if game_state.player_gold[player_index] < cost:
                continue

            available_heroes.append((hero_type, priority))

        if not available_heroes:
            return None

        # Sort by priority
        available_heroes.sort(key=lambda x: x[1], reverse=True)
        selected_hero = available_heroes[0][0]

        # Find a Keep/Castle to train in
        keep_location = self._find_keep_for_training(game_state, player_index)
        if not keep_location:
            return None

        territory, keep_plot = keep_location
        return (selected_hero, territory, keep_plot)

    def _count_training_heroes(self, game_state, player_index):
        """Count heroes currently in training for this player.

        hero_training_queue structure: {territory_name: {plot_index: (hero_type, time)}}
        We count entries in territories owned by this player.
        """
        count = 0
        for territory, keeps_dict in game_state.hero_training_queue.items():
            if game_state.territory_owners.get(territory) == player_index:
                count += len(keeps_dict)
        return count

    def _get_training_hero_types(self, game_state, player_index):
        """Get set of hero types currently in training for this player.

        hero_training_queue structure: {territory_name: {plot_index: (hero_type, time)}}
        """
        training_types = set()
        for territory, keeps_dict in game_state.hero_training_queue.items():
            if game_state.territory_owners.get(territory) == player_index:
                for plot_idx, (hero_type, _) in keeps_dict.items():
                    training_types.add(hero_type)
        return training_types

    def _find_keep_for_training(self, game_state, player_index):
        """
        Find a Keep/Castle available for hero training.

        hero_training_queue structure: {territory_name: {plot_index: (hero_type, time)}}

        Returns:
            tuple: (territory, keep_plot_index) or None
        """
        for territory, owner in game_state.territory_owners.items():
            if owner != player_index:
                continue

            if territory not in game_state.buildings:
                continue

            for plot_idx, building_type in game_state.buildings[territory].items():
                if building_type == 'Keep':
                    # Check if Keep is free (not already training a hero)
                    is_training = (
                        territory in game_state.hero_training_queue and
                        plot_idx in game_state.hero_training_queue[territory]
                    )

                    if not is_training:
                        return (territory, plot_idx)

        return None


class AbilityExecutor:
    """Decides when to use hero abilities - aggressive usage philosophy"""

    # Minimum threshold to use an ability (lowered for aggressive usage)
    MIN_ABILITY_THRESHOLD = 15.0

    def __init__(self):
        """Initialize ability executor with cached scorer and dispatch dict.

        M23 FIX: Cache TerritoryScorer to avoid per-call instantiation in ability scoring.
        The _ability_scorers dict maps ability names to their scoring functions,
        replacing the if-elif chain in _score_ability. Each entry is a tuple of
        (scoring_function, needs_hero_data) where needs_hero_data indicates
        whether the scorer requires the hero_data parameter.
        """
        # M23 FIX: Cache TerritoryScorer for reuse across ability evaluations
        from ai_strategy import TerritoryScorer
        self._scorer = TerritoryScorer()

        # Dispatch dict: ability_name -> (scorer_function, needs_hero_data)
        # Replaces the 50-line if-elif chain in _score_ability with a single dict lookup
        self._ability_scorers = {
            # Halon Nextroy
            'Aggressive Diplomacy': (self._score_aggressive_diplomacy, False),
            'Levy':                 (self._score_levy, False),
            # Aidam Narn
            'Royal Charisma':       (self._score_royal_charisma, True),
            'Regicide':             (self._score_regicide, False),
            # Erec Silvyr
            'Extort Populace':      (self._score_extort_populace, False),
            # Darius Brennhen
            'Reinforce':            (self._score_reinforce, True),
            # Neil Hevilneu
            'Decisive Strike':      (self._score_decisive_strike, False),
            'Valorous Charge':      (self._score_valorous_charge, True),
            # Seledra Rennervail
            'Vow of Silence':       (self._score_vow_of_silence, False),
            # Evain Nithieln
            'Embargo':              (self._score_embargo, False),
            'Master Negotiator':    (self._score_master_negotiator, False),
            # Varian Ashford (8th hero)
            'Relentless Charge':    (self._score_relentless_charge, True),
        }

    # M30 FIX: Difficulty multipliers for ability scoring
    # Easy AI uses abilities less optimally (lower scores = fewer abilities pass threshold)
    # Hard AI uses abilities at full effectiveness (unchanged from original)
    DIFFICULTY_ABILITY_MULTIPLIERS = {
        0: 0.5,   # Easy: multiply scores by 0.5 (less optimal ability usage)
        1: 0.8,   # Normal: multiply scores by 0.8
        2: 1.0,   # Hard: multiply scores by 1.0 (unchanged)
    }

    def evaluate_ability_usage(self, game_state, player_index, difficulty=2):
        """
        Evaluate all available hero abilities and select best to use.

        Philosophy: Use abilities aggressively when cooldown is ready.
        Most abilities should be used ASAP unless there's a specific reason not to.

        M30 FIX: Ability scores are now multiplied by a difficulty modifier so that
        Easy AI uses abilities less effectively (some marginal abilities won't pass
        the minimum threshold).

        Args:
            game_state: GameState instance
            player_index (int): Player index
            difficulty (int): AI difficulty level (0=Easy, 1=Normal, 2=Hard)

        Returns:
            tuple: (hero_type, ability_name, target_params) or None
        """
        if player_index not in game_state.heroes:
            return None

        active_heroes = game_state.heroes[player_index]
        candidates = []

        # M30 FIX: Get difficulty multiplier for ability scoring
        difficulty_multiplier = self.DIFFICULTY_ABILITY_MULTIPLIERS.get(difficulty, 1.0)

        for hero_type, hero_data in active_heroes.items():
            hero_def = game_state.HERO_TYPES[hero_type]

            for ability in hero_def['abilities']:
                if ability['type'] != 'active':
                    continue

                ability_name = ability['name']

                # Check cooldown using the correct structure
                # Cooldowns: {player_index: {hero_type: {ability_name: turns_remaining}}}
                if player_index in game_state.hero_ability_cooldowns:
                    hero_cooldowns = game_state.hero_ability_cooldowns[player_index].get(hero_type, {})
                    if isinstance(hero_cooldowns, dict):
                        if hero_cooldowns.get(ability_name, 0) > 0:
                            continue  # Still on cooldown

                # Evaluate specific abilities
                score, target = self._score_ability(
                    hero_type, ability_name, game_state, player_index, hero_data
                )

                # M30 FIX: Apply difficulty multiplier to ability scores
                # Easy AI (0.5x) will have fewer abilities pass the threshold,
                # resulting in less optimal ability usage
                score *= difficulty_multiplier

                if score >= self.MIN_ABILITY_THRESHOLD:
                    candidates.append((hero_type, ability_name, target, score))

        if not candidates:
            return None

        # Sort by score
        candidates.sort(key=lambda x: x[3], reverse=True)
        return candidates[0][:3]  # Return (hero_type, ability_name, target)

    def _score_ability(self, hero_type, ability_name, game_state, player_index, hero_data):
        """
        Score an ability usage opportunity using dispatch dict lookup.
        Base score of 60+ means "use when ready".

        Uses self._ability_scorers dict to map ability names to scoring functions,
        replacing the previous if-elif chain. Each scorer is a (function, needs_hero_data)
        tuple. Functions that need hero_data receive it as an extra argument.

        Returns:
            tuple: (score, target_params)
        """
        scorer_entry = self._ability_scorers.get(ability_name)
        if scorer_entry is None:
            return (0.0, None)

        scorer_fn, needs_hero_data = scorer_entry
        if needs_hero_data:
            return scorer_fn(game_state, player_index, hero_data)
        else:
            return scorer_fn(game_state, player_index)

    # ==================== HALON NEXTROY ====================

    def _score_aggressive_diplomacy(self, game_state, player_index):
        """
        Aggressive Diplomacy: Claim neutral/enemy territory with ≤1 armies, no Keep.
        Very powerful for expansion - high priority.
        """
        import map_data

        # M23 FIX: Use cached scorer instead of creating per call
        scorer = self._scorer
        best_score = 0.0
        best_target = None

        owned_territories = [
            t for t, owner in game_state.territory_owners.items()
            if owner == player_index
        ]

        for territory in owned_territories:
            neighbors = map_data.get_neighbors(territory)

            for neighbor in neighbors:
                owner = game_state.territory_owners.get(neighbor, -1)

                # Can target neutral OR enemy territories
                if owner == player_index:
                    continue  # Can't target own territory

                # Check army count (must be ≤1)
                # H11 FIX: Use get_territory_total_armies() for enemy/neutral defense assessment
                # This includes all garrisons (owner + allies) which is the true defensive strength
                armies = game_state.get_territory_total_armies(neighbor)
                if armies > 1:
                    continue

                # Check for Keep (must have no Keep)
                has_keep = game_state.has_fortress(neighbor)
                if has_keep:
                    continue

                # Score this target - higher for enemy territories
                value = scorer.calculate_territory_value(neighbor, game_state, player_index)
                if owner != -1:  # Enemy territory - bonus!
                    value += 30.0

                if value > best_score:
                    best_score = value
                    best_target = neighbor

        # Base score of 60 if valid target found
        if best_target:
            return (60.0 + best_score * 0.5, best_target)
        return (0.0, None)

    def _score_levy(self, game_state, player_index):
        """
        Levy: Collect full income from a territory.
        Always useful - use whenever ready. Find best territory to levy.
        """
        territory_count = sum(
            1 for owner in game_state.territory_owners.values()
            if owner == player_index
        )

        # Find the highest-income territory to target
        best_income = 0
        best_territory = None

        for territory, owner in game_state.territory_owners.items():
            if owner != player_index:
                continue
            income = game_state.calculate_territory_income(territory)
            if income > best_income:
                best_income = income
                best_territory = territory

        # High base score - always use when ready
        # More territories = more valuable (Nextroy gives +4g per territory passive)
        score = 70.0 + min(territory_count * 2.0, 30.0)

        return (score, best_territory)

    # ==================== AIDAM NARN ====================

    def _score_royal_charisma(self, game_state, player_index, hero_data):
        """
        Royal Charisma: Steal up to 5 units from enemy territory to Narn's Keep.
        Very powerful - use when enemy has armies to steal.
        """
        import map_data

        keep_territory = hero_data.get('keep_territory')
        if not keep_territory:
            return (0.0, None)

        # Check if Keep territory has room (must have < 15 units)
        # H11 FIX: Use get_territory_total_armies() to check total capacity (all garrisons)
        keep_armies = game_state.get_territory_total_armies(keep_territory)
        if keep_armies >= 15:
            return (0.0, None)  # No room

        # Find enemy territory with most armies to steal from
        best_target = None
        best_steal = 0

        for territory, owner in game_state.territory_owners.items():
            if owner == player_index or owner == -1:
                continue  # Must be enemy

            # H11 FIX: Use get_territory_total_armies() for enemy strength assessment
            armies = game_state.get_territory_total_armies(territory)
            if armies <= 0:
                continue

            # Can steal up to 5, limited by room in Keep
            can_steal = min(5, armies, 15 - keep_armies)
            if can_steal > best_steal:
                best_steal = can_steal
                best_target = territory

        if best_target and best_steal > 0:
            # High value - stealing units is very powerful
            return (70.0 + best_steal * 10.0, best_target)
        return (0.0, None)

    def _score_regicide(self, game_state, player_index):
        """
        Regicide: Kill enemy hero at their Keep.
        Devastating if enemy has valuable heroes - check for targets.
        """
        # Find enemy Keeps with heroes
        for enemy_player in range(game_state.num_players):
            if enemy_player == player_index:
                continue

            # Check if enemy has heroes
            enemy_heroes = game_state.heroes.get(enemy_player, {})
            if not enemy_heroes:
                continue

            # Find their Keeps
            for territory, owner in game_state.territory_owners.items():
                if owner != enemy_player:
                    continue

                # Check if this territory has a Keep with a hero
                for hero_type, hero_data in enemy_heroes.items():
                    if hero_data.get('keep_territory') == territory:
                        # Found a valid target - very high priority!
                        return (90.0, territory)

        return (0.0, None)

    # ==================== EREC SILVYR ====================

    def _score_extort_populace(self, game_state, player_index):
        """
        Extort Populace: Gain 50 gold per Keep/Castle.
        Simple gold generation - use when you have Keeps.
        """
        # Count player's Keeps and Castles
        keep_count = 0
        for territory, owner in game_state.territory_owners.items():
            if owner != player_index:
                continue
            if territory in game_state.buildings:
                for building_type in game_state.buildings[territory].values():
                    if building_type in ['Keep', 'Castle']:
                        keep_count += 1

        if keep_count <= 0:
            return (0.0, None)

        # 50 gold per Keep - good value
        gold_gained = keep_count * 50
        score = 60.0 + min(gold_gained * 0.3, 30.0)
        return (score, None)

    # ==================== DARIUS BRENNHEN ====================

    def _score_reinforce(self, game_state, player_index, hero_data):
        """
        Reinforce: Summon 2 Swordsmen at Brennhen's Keep (must have ≤13 units).
        Free units - always use when possible.
        """
        keep_territory = hero_data.get('keep_territory')
        if not keep_territory:
            return (0.0, None)

        # Check if Keep territory has room (must have ≤13 units)
        # H11 FIX: Use get_territory_total_armies() to check total capacity (all garrisons)
        keep_armies = game_state.get_territory_total_armies(keep_territory)
        if keep_armies > 13:
            return (0.0, None)

        # Free units are always good - high priority
        return (80.0, keep_territory)

    # ==================== NEIL HÉVILNEU ====================

    def _score_decisive_strike(self, game_state, player_index):
        """
        Decisive Strike: Remove half armies from enemy territory (needs ≥2 units).
        Very powerful for weakening enemy positions before attack.
        """
        best_target = None
        best_value = 0

        for territory, owner in game_state.territory_owners.items():
            if owner == player_index or owner == -1:
                continue  # Must be enemy

            # H11 FIX: Use get_territory_total_armies() for enemy strength assessment
            armies = game_state.get_territory_total_armies(territory)
            if armies < 2:
                continue  # Needs at least 2 units

            # Value = armies that would be removed
            removed = armies // 2
            if removed > best_value:
                best_value = removed
                best_target = territory

        if best_target and best_value > 0:
            # Removing enemy units is very powerful
            return (65.0 + best_value * 8.0, best_target)
        return (0.0, None)

    def _score_valorous_charge(self, game_state, player_index, hero_data):
        """
        Valorous Charge: Move up to 15 units from Hévilneu's Keep to allied territory.
        Useful for rapid reinforcement - use when Keep has excess units.
        """
        import map_data

        keep_territory = hero_data.get('keep_territory')
        if not keep_territory:
            return (0.0, None)

        # H11 FIX: Use get_territory_total_armies() for capacity/availability checks
        keep_armies = game_state.get_territory_total_armies(keep_territory)
        if keep_armies < 5:
            return (0.0, None)  # Not worth moving small amounts

        # Find friendly territory that needs reinforcement (threatened, low armies)
        best_target = None
        best_need = 0

        for territory, owner in game_state.territory_owners.items():
            if owner != player_index or territory == keep_territory:
                continue

            # Check if territory is on the front line
            neighbors = map_data.get_neighbors(territory)
            enemy_adjacent = any(
                game_state.territory_owners.get(n, -1) not in [-1, player_index]
                for n in neighbors
            )

            if not enemy_adjacent:
                continue  # Only reinforce front lines

            # H11 FIX: Use get_territory_total_armies() for defense assessment
            current_armies = game_state.get_territory_total_armies(territory)
            if current_armies >= 10:
                continue  # Already well-defended

            need = 10 - current_armies
            if need > best_need:
                best_need = need
                best_target = territory

        if best_target:
            return (60.0 + best_need * 3.0, best_target)
        return (0.0, None)

    # ==================== SELEDRA RENNERVAIL ====================

    def _score_vow_of_silence(self, game_state, player_index):
        """
        Vow of Silence: Block all enemy hero abilities until end of next turn.
        Use when enemies have dangerous heroes with abilities ready.
        """
        # Count enemy heroes that might use abilities
        enemy_hero_threat = 0
        for enemy_player in range(game_state.num_players):
            if enemy_player == player_index:
                continue

            enemy_heroes = game_state.heroes.get(enemy_player, {})
            enemy_hero_threat += len(enemy_heroes)

        if enemy_hero_threat <= 0:
            return (0.0, None)

        # More enemy heroes = more valuable to silence
        score = 50.0 + enemy_hero_threat * 15.0
        return (score, None)

    # ==================== EVAIN NITHIELN ====================

    def _score_embargo(self, game_state, player_index):
        """
        Embargo: Block all enemy income next turn.
        Devastating economic attack - use against wealthy enemies.
        """
        # Calculate total enemy income
        total_enemy_income = 0
        for enemy_player in range(game_state.num_players):
            if enemy_player == player_index:
                continue
            total_enemy_income += game_state.calculate_player_income(enemy_player)

        if total_enemy_income < 100:
            return (0.0, None)  # Not worth it for small income

        # Very powerful - blocking hundreds of gold
        score = 60.0 + min(total_enemy_income * 0.1, 40.0)
        return (score, None)

    def _score_master_negotiator(self, game_state, player_index):
        """
        Master Negotiator: 75% discount on buildings this turn.
        Use when planning to build multiple buildings.
        """
        # Check if we have gold to build multiple buildings
        player_gold = game_state.player_gold[player_index]
        if player_gold < 100:
            return (0.0, None)  # Not enough to benefit

        # Check if there are open building plots
        open_plots = 0
        for territory, owner in game_state.territory_owners.items():
            if owner != player_index:
                continue
            if territory not in game_state.buildings:
                open_plots += 3  # Assume 3 plots per territory
            else:
                built = len(game_state.buildings[territory])
                open_plots += max(0, 3 - built)

        if open_plots < 2:
            return (0.0, None)  # No space to build

        # More gold and more plots = better value
        score = 55.0 + min(player_gold * 0.03, 25.0) + min(open_plots * 2.0, 20.0)
        return (score, None)

    # ==================== VARIAN ASHFORD (8th hero) ====================

    def _score_relentless_charge(self, game_state, player_index, hero_data):
        """
        Relentless Charge: Summon 4 Cavalry in target friendly territory (≤11 units).
        Free cavalry is extremely powerful - high priority.
        """
        import map_data

        best_target = None
        best_score = 0

        for territory, owner in game_state.territory_owners.items():
            if owner != player_index:
                continue

            # H11 FIX: Use get_territory_total_armies() for capacity check (all garrisons)
            armies = game_state.get_territory_total_armies(territory)
            if armies > 11:
                continue  # Must have ≤11 units

            # Prefer front-line territories
            neighbors = map_data.get_neighbors(territory)
            enemy_adjacent = sum(
                1 for n in neighbors
                if game_state.territory_owners.get(n, -1) not in [-1, player_index]
            )

            value = 50.0 + enemy_adjacent * 10.0
            if value > best_score:
                best_score = value
                best_target = territory

        if best_target:
            # 4 free Cavalry is very powerful
            return (85.0, best_target)
        return (0.0, None)


class HeroManager:
    """Main hero management coordinator"""

    def __init__(self, ai_player):
        """
        Initialize hero manager.

        Args:
            ai_player: AIPlayer instance (parent)
        """
        self.ai_player = ai_player
        self.selector = HeroSelector()
        self.executor = AbilityExecutor()

    def plan_hero_actions(self, game_state):
        """
        Plan all hero-related actions for this turn.

        Args:
            game_state: GameState instance

        Returns:
            list: List of hero actions
        """
        actions = []
        player_index = self.ai_player.player_index

        # 1. Hero abilities (always try, apply difficulty after finding good ability)
        # M30 FIX: Pass difficulty so ability scores are scaled by difficulty level
        ability_action = self.executor.evaluate_ability_usage(
            game_state, player_index, self.ai_player.difficulty
        )
        if ability_action:
            # Apply usage rate, but with minimum 30% chance even for Easy AI
            use_chance = max(0.3, self.ai_player.config['hero_ability_usage'])
            if random.random() < use_chance:
                hero_type, ability_name, target = ability_action
                actions.append(('hero_ability', {
                    'hero_type': hero_type,
                    'ability_name': ability_name,
                    'target': target
                }))

        # 2. Hero training (if affordable)
        hero_training = self.selector.select_hero_to_train(
            game_state, player_index, self.ai_player.difficulty
        )
        if hero_training:
            hero_type, territory, keep_plot = hero_training
            actions.append(('train_hero', {
                'hero_type': hero_type,
                'territory': territory,
                'keep_plot': keep_plot
            }))

        return actions


# Test the hero module if run directly
if __name__ == '__main__':
    logger.info("AI Hero Module Test")
    logger.info("=" * 60)
    logger.info("Module loaded successfully")
    logger.info("Classes available:")
    logger.info("  - HeroSelector: Hero training selection")
    logger.info("  - AbilityExecutor: Hero ability usage decisions")
    logger.info("  - HeroManager: Hero management coordinator")
