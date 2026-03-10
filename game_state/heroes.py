# game_state/heroes.py
# Hero system mixin for GameState (Phase 7 decomposition)

"""
Hero system: training, abilities, hero queries, cooldowns.

Provides methods for hero training, ability activation/execution,
hero presence queries, and cooldown management.
"""

import random
import map_data
from utils.logger import get_logger

logger = get_logger(__name__)


class HeroMixin:
    """Mixin providing hero management methods for GameState."""

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

        # 9. Add to training queue — store paid cost for accurate refund on cancel (H1 fix)
        training_time = self.HERO_TYPES[hero_type]['training_time']
        if territory not in self.hero_training_queue:
            self.hero_training_queue[territory] = {}
        self.hero_training_queue[territory][keep_plot_index] = (hero_type, training_time, hero_cost)

        # 10. Mark as owned (prevents duplicate training)
        self.hero_ownership[self.current_player].add(hero_type)

        self.add_message(f"Player {self.current_player + 1} started training {hero_type} ({hero_cost} gold, {training_time} turns)")
        self._training_version += 1  # FPS OPT: Production glow sync
        return True

    def cancel_hero_training(self, territory, keep_plot_index):
        """Cancel hero training with 100% refund (vs 50% for units)."""
        # 1. Validate training exists
        if (territory not in self.hero_training_queue or
            keep_plot_index not in self.hero_training_queue[territory]):
            return False

        # 2. Get hero info — H1 fix: use stored paid_cost for accurate refund
        entry = self.hero_training_queue[territory][keep_plot_index]
        if len(entry) == 3:
            hero_type, _, paid_cost = entry
        else:
            # Backwards compat: old format without paid_cost
            hero_type, _ = entry
            owner = self.territory_owners[territory]
            paid_cost = self.get_hero_cost(hero_type, owner)
        owner = self.territory_owners[territory]

        # 3. 100% refund of what was actually paid (key difference!)
        hero_cost = paid_cost
        self.player_gold[owner] += hero_cost

        # 4. Remove from queue
        del self.hero_training_queue[territory][keep_plot_index]
        if not self.hero_training_queue[territory]:
            del self.hero_training_queue[territory]

        # 5. Remove from ownership (allow retraining)
        self.hero_ownership[owner].discard(hero_type)

        self.add_message(f"Hero training canceled, {hero_cost} gold refunded (100%)")
        self._training_version += 1  # FPS OPT: Production glow sync
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

            for keep_plot_index, entry in list(keeps_dict.items()):
                # H1 fix: queue entries are now (hero_type, turns, paid_cost) 3-tuples
                hero_type, turns_remaining = entry[0], entry[1]
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
                    # Player Level: award XP for training a hero
                    self._track_stat(owner, 'xp_earned', 4)
                    # Game logger: record hero training event with turn number
                    if self.game_logger:
                        self.game_logger.record_hero_trained(owner, hero_type, self.turn_number)

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
                    # Update timer — preserve paid_cost in 3rd slot (H1 fix)
                    paid_cost = entry[2] if len(entry) == 3 else 0
                    keeps_dict[keep_plot_index] = (hero_type, turns_remaining, paid_cost)

            # Clean up
            for keep_plot_index in keeps_to_remove:
                if keep_plot_index in keeps_dict:
                    del keeps_dict[keep_plot_index]

            if not keeps_dict:
                territories_to_remove.append(territory)

        for territory in territories_to_remove:
            del self.hero_training_queue[territory]

        # FPS OPT: Always bump version — called once per turn, negligible cost
        self._training_version += 1

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

        # Player Level: award XP for using an active hero ability (non-targeted path)
        self._track_stat(current_player, 'xp_earned', 2)

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
                #   - Player 2 turn starts: decrement 2->1, effect active during Player 2's turn
                #   - Player 1 turn starts: decrement 1->0, effect expires
                self.hero_silence_status[player_index] = self.num_players

        # M5 fix: Guard pygame import for headless (test) environments
        try:
            import pygame
            self.silence_activation_time = pygame.time.get_ticks()
        except Exception:
            self.silence_activation_time = 0

        # Play spell sound effect
        from global_sound import play_spell_sound
        play_spell_sound('VowOfSilence')

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

        # C2 fix: Guard pygame import for headless (test) environments
        try:
            import pygame
            self.master_negotiator_activation_time = pygame.time.get_ticks()
        except Exception:
            self.master_negotiator_activation_time = 0
        self.master_negotiator_active_player = player_index

        # Play spell sound only for the casting player (personal buff)
        should_play_sound = not self.player_is_ai[player_index]
        if self.network_mode and should_play_sound:
            should_play_sound = (player_index == self.local_player_index)
        if should_play_sound:
            from global_sound import play_spell_sound
            play_spell_sound('MasterNegotiator')

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

        # Play spell sound effect
        from global_sound import play_spell_sound
        play_spell_sound('Embargo')

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
        # Legacy counter fix: use get_territory_total_armies to account for allied garrisons
        current_armies = self.get_territory_total_armies(target_territory)
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

        # Cancel incoming orders that would now exceed army limit after spawning units
        cancelled = self._revalidate_incoming_orders(target_territory)
        if cancelled:
            self.add_message(f"Orders cancelled due to Relentless Charge: {', '.join(cancelled)}")

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Relentless Charge summoned {cavalry_spawned} Cavalry in {target_territory}{haste_msg}")

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

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
        # Legacy counter fix: use get_territory_total_armies to account for allied garrisons
        current_armies = self.get_territory_total_armies(keep_territory)
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

        # Cancel incoming orders that would now exceed army limit after spawning units
        cancelled = self._revalidate_incoming_orders(keep_territory)
        if cancelled:
            self.add_message(f"Orders cancelled due to Reinforce: {', '.join(cancelled)}")

        # Play spell sound only for the casting player (personal buff)
        should_play_sound = not self.player_is_ai[owner]
        if self.network_mode and should_play_sound:
            should_play_sound = (owner == self.local_player_index)
        if should_play_sound:
            from global_sound import play_spell_sound
            play_spell_sound('Reinforce')

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
        # Legacy counter fix: use get_territory_total_armies to account for allied garrisons
        current_armies = self.get_territory_total_armies(target_territory)
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
        # H1 fix: use = {} instead of del to keep key consistent with rest of codebase
        if target_territory in self.territory_garrisons:
            self.territory_garrisons[target_territory] = {}

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
        self._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
        self.invalidate_income_cache()  # FPS OPT: Ownership affects income
        self.invalidate_army_count_cache()  # FPS OPT: Army counts change
        self.invalidate_territorial_bonus_cache()  # Ownership changed — refresh bonuses

        # Campaign hook: notify territory conquered via Aggressive Diplomacy
        # This triggers quest checks and AI awakening (e.g. Mission 6 Blue activation)
        if self.tutorial_mission and current_owner != owner:
            self.tutorial_mission.notify_event(
                'territory_conquered',
                territory=target_territory,
                new_owner=owner
            )

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

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

        return (True, None)

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

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

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

        # Play spell sound only for the casting player (personal buff)
        should_play_sound = not self.player_is_ai[owner]
        if self.network_mode and should_play_sound:
            should_play_sound = (owner == self.local_player_index)
        if should_play_sound:
            from global_sound import play_spell_sound
            play_spell_sound('ExtortPopulace')

        # Add message to action log
        self.add_message(f"Player {owner + 1}: Extort Populace gained {gold_gained} Gold from {keeps_and_castles} Keep(s)/Castle(s)!")

        return (True, None)

    def execute_decisive_strike(self, target_territory, owner):
        """
        Execute Decisive Strike ability - remove half of the armies in target enemy territory.

        Args:
            target_territory: Territory name to target
            owner: Player index who owns Neil Hevilneu

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
        # Legacy counter fix: use get_territory_total_armies to account for allied garrisons
        army_count = self.get_territory_total_armies(target_territory)
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

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

        return (True, None)

    def execute_valorous_charge(self, target_territory, owner):
        """
        Execute Valorous Charge ability - move up to 15 units from Hevilneu's Keep to target allied territory.

        Args:
            target_territory: Territory name to move units to
            owner: Player index who owns Neil Hevilneu

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        # Find hero's Keep territory (works for Neil Hevilneu or Serthus Diarcess)
        if owner not in self.heroes:
            return (False, "Hero not found!")

        # Check for either Neil Hevilneu or Serthus Diarcess (both have Valorous Charge)
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

        # Cancel incoming orders that would now exceed army limit in target territory
        cancelled = self._revalidate_incoming_orders(target_territory)
        if cancelled:
            self.add_message(f"Orders cancelled due to Valorous Charge: {', '.join(cancelled)}")

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Valorous Charge moved {units_to_move} units from {keep_territory} to {target_territory}{haste_msg}")

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

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

        # Legacy counter fix: use get_territory_total_armies to account for allied garrisons
        narn_keep_units = self.get_territory_total_armies(narn_keep_territory)

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

        # Cancel incoming orders that would now exceed army limit in Narn's Keep
        cancelled = self._revalidate_incoming_orders(narn_keep_territory)
        if cancelled:
            self.add_message(f"Orders cancelled due to Royal Charisma: {', '.join(cancelled)}")

        # Add message to action log
        haste_msg = " (Haste - Ready to Move!)" if has_haste else ""
        self.add_message(f"Player {owner + 1}: Royal Charisma stole {units_to_steal} units from {target_territory} to {narn_keep_territory}{haste_msg}!")

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

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

        # Player Level: award XP for using active hero ability (targeted)
        self._track_stat(owner, 'xp_earned', 2)

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
        Check if a player has Neil Hevilneu or Serthus Diarcess trained.
        Both heroes share the Vanquish the Enemy passive ability.

        Args:
            player_index: Player index to check

        Returns:
            bool: True if player has Neil Hevilneu or Serthus Diarcess
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
