# -*- coding: utf-8 -*-
# input/keyboard_handler.py
# Keyboard input handling for shortcuts, menus, and chat

"""
Keyboard Handler
================

This module handles all keyboard input for the game:
- Menu navigation (ESC to close)
- Chat input (ENTER, text entry)
- Building shortcuts (F, M, B, K, Q)
- Training shortcuts (S, A, P, C)

Extracted from main.py during Phase 3 of refactoring.
"""

import pygame

from utils.logger import get_logger

logger = get_logger(__name__)

# Phase 6C: Dispatch dicts for keyboard shortcuts (replaces if/elif chains)
_BUILDING_SHORTCUTS = {
    pygame.K_f: 'Farm',
    pygame.K_m: 'Mine',
    pygame.K_b: 'Barracks',
    pygame.K_k: 'Keep',
    pygame.K_q: 'Square',
    pygame.K_t: 'Training Grounds',
}

_TRAINING_SHORTCUTS = {
    pygame.K_s: 'Swordsman',
    pygame.K_a: 'Archer',
    pygame.K_p: 'Pikeman',
    pygame.K_c: 'Cavalry',
    pygame.K_t: 'Captain',
}


class KeyboardHandler:
    """
    Handles all keyboard input and shortcuts.

    This class processes keyboard events and delegates actions to the
    appropriate systems (menus, chat, building, training).

    Keyboard Shortcuts:
        Building: F=Farm, M=Mine, B=Barracks, K=Keep, Q=Square
        Training: S=Swordsman, A=Archer, P=Pikeman, C=Cavalry
        Menu: ESC=Close menu/dialog
        Chat: ENTER=Open/send, ESC=Cancel, BACKSPACE=Delete
    """

    def __init__(self):
        """Initialize keyboard handler."""
        pass

    def handle_keyboard_event(self, event, game_state, ui_state):
        """
        Handle a keyboard event.

        Args:
            event: pygame.KEYDOWN event
            game_state: GameState instance
            ui_state: dict with UI state variables:
                - options_menu_visible
                - game_menu_visible
                - chat_input_active
                - chat_input_text
                - selected_plot
                - selected_barracks
                - resolution_dropdown_open
                - temp_resolution
                - current_resolution
                - temp_fullscreen
                - is_fullscreen

        Returns:
            tuple: (handled, updated_ui_state)
                handled: bool - True if key was handled
                updated_ui_state: dict with any updated UI state
        """
        updates = {}

        # ========================================
        # OPTIONS MENU HANDLING (highest priority)
        # ========================================
        if ui_state.get('options_menu_visible'):
            if event.key == pygame.K_ESCAPE:
                # Close options menu and return to game menu
                updates['options_menu_visible'] = False
                updates['game_menu_visible'] = True
                updates['resolution_dropdown_open'] = False
                # Reset temp settings
                updates['temp_resolution'] = ui_state.get('current_resolution')
                updates['temp_fullscreen'] = ui_state.get('is_fullscreen')
                return (True, updates)
            # Block all other keyboard input when options menu is open
            return (True, {})

        # ========================================
        # GAME MENU HANDLING (second highest priority)
        # ========================================
        if ui_state.get('game_menu_visible'):
            if event.key == pygame.K_ESCAPE:
                # Close game menu
                updates['game_menu_visible'] = False
                return (True, updates)
            # Block all other keyboard input when menu is open
            return (True, {})

        # ========================================
        # SIDEBAR COLLAPSE / EXPAND (F2)
        # ========================================
        # Local UI only (never a game action). Ahead of ability targeting, which
        # swallows every key; not while typing chat. Game._handle_sidebar_hotkey()
        # applies the remaining gates (modal popups, tutorial).
        if event.key == pygame.K_F2 and not ui_state.get('chat_input_active'):
            updates['toggle_sidebar'] = True
            return (True, updates)

        # ========================================
        # ABILITY TARGETING HANDLING (high priority)
        # ========================================
        if ui_state.get('ability_targeting_active'):
            if event.key == pygame.K_ESCAPE:
                # Cancel ability targeting
                updates['ability_targeting_active'] = False
                updates['ability_targeting_hero'] = None
                updates['ability_targeting_ability_index'] = None
                updates['ability_targeting_ability_name'] = None
                return (True, updates)
            # Block all other keyboard input when targeting
            return (True, {})

        # ========================================
        # CHAT INPUT HANDLING (second highest priority)
        # ========================================
        if ui_state.get('chat_input_active'):
            if event.key == pygame.K_RETURN:
                # Send message
                chat_text = ui_state.get('chat_input_text', '')
                if chat_text.strip():  # Don't send empty messages
                    # ========================================
                    # CHEAT CODE HANDLING
                    # ========================================
                    # Check for cheat codes before sending as chat
                    cheat_handled = self._handle_cheat_code(chat_text, game_state, ui_state)
                    if cheat_handled:
                        # Close chat input without sending message
                        updates['chat_input_active'] = False
                        updates['chat_input_text'] = ""
                        return (True, updates)

                    # MULTIPLAYER: Use local_player_index instead of current_player
                    multiplayer_mode = ui_state.get('multiplayer_mode', False)
                    if multiplayer_mode:
                        player_index = ui_state.get('local_player_index', 0)
                    else:
                        player_index = game_state.current_player

                    # VALIDATION: Check if player_index is valid
                    if player_index is None or player_index < 0 or player_index >= game_state.num_players:
                        logger.error(f"Invalid chat player_index: {player_index}")
                        updates['chat_input_active'] = False
                        updates['chat_input_text'] = ""
                        return (True, updates)

                    # Get chat channel (default to 'all')
                    chat_channel = ui_state.get('chat_channel', 'all')

                    # Add message locally with channel
                    game_state.add_chat_message(player_index, chat_text, chat_channel)

                    # MULTIPLAYER: Send to remote players
                    if multiplayer_mode:
                        game_instance = ui_state.get('game_instance')
                        if game_instance:
                            from network_config import MessageType
                            game_instance._send_action_to_remote(MessageType.CHAT_MESSAGE, {
                                'player_index': player_index,
                                'message': chat_text,
                                'channel': chat_channel
                            })

                # Close chat input
                updates['chat_input_active'] = False
                updates['chat_input_text'] = ""
                return (True, updates)

            elif event.key == pygame.K_TAB:
                # Toggle between 'all' and 'team' chat channels
                current_channel = ui_state.get('chat_channel', 'all')
                new_channel = 'team' if current_channel == 'all' else 'all'
                updates['chat_channel'] = new_channel
                logger.info(f"Chat switched to {new_channel.upper()} channel")
                return (True, updates)

            elif event.key == pygame.K_ESCAPE:
                # Cancel chat input
                updates['chat_input_active'] = False
                updates['chat_input_text'] = ""
                return (True, updates)

            elif event.key == pygame.K_BACKSPACE:
                # Delete last character
                current_text = ui_state.get('chat_input_text', '')
                updates['chat_input_text'] = current_text[:-1]
                return (True, updates)

            else:
                # Add character to chat input
                # Only accept printable characters (exclude TAB)
                if event.unicode and event.unicode != '\t':
                    current_text = ui_state.get('chat_input_text', '')
                    if len(current_text) < 100:  # Max 100 chars
                        updates['chat_input_text'] = current_text + event.unicode
                return (True, updates)

        # ========================================
        # CHAT OPEN (when not already typing)
        # ========================================
        if event.key == pygame.K_RETURN and not ui_state.get('chat_input_active'):
            updates['chat_input_active'] = True
            updates['chat_input_text'] = ""
            return (True, updates)

        # ========================================
        # BUILDING SHORTCUTS (when plot is selected)
        # ========================================
        selected_plot = ui_state.get('selected_plot')
        if (selected_plot and
            game_state.phase == 'playing' and
            game_state.turn_phase == 'planning' and
            not game_state.is_ai_player()):

            # Block shortcuts if spectating / already marked Ready (multiplayer and
            # simultaneous mode) — same gate as the bottom-panel buttons
            game_instance = ui_state.get('game_instance')
            if game_instance and not game_instance.is_local_player_active():
                return (False, {})

            territory, plot_index = selected_plot

            # Phase 6C: Use dispatch dict for building shortcuts
            building_name = _BUILDING_SHORTCUTS.get(event.key)

            if building_name:
                # Route through the same path as a click: sim-resolving gate, sim order /
                # network sync and failure feedback. Calling game_state directly skipped
                # all of that, so a shortcut build never reached other players.
                if game_instance:
                    started = game_instance._try_start_construction(territory, plot_index, building_name)
                else:
                    started = game_state.start_construction(territory, plot_index, building_name)
                if started:
                    updates['selected_plot'] = None
                    updates['clear_button_tooltip'] = True
                return (True, updates)

        # ========================================
        # TRAINING SHORTCUTS (when Barracks is selected)
        # ========================================
        selected_barracks = ui_state.get('selected_barracks')
        if (selected_barracks and
            game_state.phase == 'playing' and
            game_state.turn_phase == 'planning' and
            not game_state.is_ai_player()):

            # Block shortcuts if spectating / already marked Ready (see building shortcuts)
            game_instance = ui_state.get('game_instance')
            if game_instance and not game_instance.is_local_player_active():
                return (False, {})

            territory, barracks_plot_index = selected_barracks

            # Phase 6C: Use dispatch dict for training shortcuts
            unit_type = _TRAINING_SHORTCUTS.get(event.key)

            if unit_type:
                # Same path as a click (sim-resolving gate, sync, failure feedback)
                if game_instance:
                    game_instance._try_start_training(territory, barracks_plot_index, unit_type)
                else:
                    game_state.start_training(territory, barracks_plot_index, unit_type)
                updates['clear_button_tooltip'] = True
                return (True, updates)

        return (False, {})

    def _handle_cheat_code(self, chat_text, game_state, ui_state):
        """
        Handle cheat codes entered in chat.

        Cheat codes:
            - youhavemysword1-4: Add 1 swordsman to selected territory for player 1-4
            - youhavemykeep1-4: Instantly build Keep in selected plot for player 1-4
            - ilearn: Award 50 XP to all units in selected territory (current player)

        Args:
            chat_text: The text entered in chat
            game_state: GameState instance
            ui_state: UI state dict

        Returns:
            bool: True if cheat code was handled, False otherwise
        """
        # C5: Block cheats in multiplayer games - cheats could desync game state
        game_instance = ui_state.get('game_instance')
        if game_instance:
            if hasattr(game_instance, 'network_client') and game_instance.network_client:
                return False
            if hasattr(game_instance, 'network_server') and game_instance.network_server:
                return False

        chat_text_original = chat_text.strip()
        chat_text = chat_text_original.lower()

        logger.debug(f"Checking chat text for cheat code: '{chat_text_original}'")

        # Check for "youhavemysword[1-4]" cheat
        if chat_text.startswith("youhavemysword"):
            logger.debug(f"Detected youhavemysword cheat")
            # Extract player number
            try:
                player_num = int(chat_text[-1])  # Get last character
                logger.debug(f"Player number: {player_num}")
                if player_num < 1 or player_num > 4:
                    logger.debug(f"Invalid player number: {player_num}")
                    return False
                player_index = player_num - 1  # Convert to 0-indexed

                # Get territory - try multiple sources with L16 validation
                territory = ui_state.get('selected_territory')
                logger.debug(f"selected_territory: {territory}")

                # L16: Validate territory still exists in game state before using it
                if territory and territory not in game_state.territory_owners:
                    logger.debug(f"selected_territory '{territory}' no longer valid, skipping")
                    territory = None

                if not territory:
                    selected_plot = ui_state.get('selected_plot')
                    logger.debug(f"selected_plot: {selected_plot}")
                    if selected_plot:
                        t, _ = selected_plot
                        # L16: Validate territory from plot still exists
                        if t in game_state.territory_owners:
                            territory = t

                if not territory:
                    # Try hovered territory as last resort
                    territory = ui_state.get('hovered_territory')
                    logger.debug(f"hovered_territory: {territory}")
                    # L16: Validate hovered territory exists
                    if territory and territory not in game_state.territory_owners:
                        territory = None

                if not territory:
                    logger.warning("Cheat failed: no territory found. Hover over or click a territory first.")
                    game_state.add_message(f"[CHEAT] Hover over or click a territory first!")
                    return True  # Still handled, just show error

                logger.debug(f"Using territory: {territory}")

                # Set territory owner if not already owned
                if game_state.territory_owners.get(territory, -1) == -1:
                    game_state.territory_owners[territory] = player_index
                    game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    game_state.invalidate_territorial_bonus_cache()  # Ownership changed
                    logger.info(f"Cheat: Claimed {territory} for Player {player_num}")

                # Create a swordsman unit (health=10)
                swordsman_unit = {'type': 'Swordsman', 'health': 10}

                # Use the proper add_garrison method
                game_state.add_garrison(territory, player_index, unmoved=1, moved=0, units=[swordsman_unit])

                logger.info(f"Cheat: Added 1 Swordsman to {territory} for Player {player_num}")
                game_state.add_message(f"[CHEAT] Player {player_num} spawned a Swordsman in {territory}")
                return True

            except (ValueError, IndexError) as e:
                logger.debug(f"Cheat code parsing error: {e}")
                return False

        # Check for "youhavemykeep[1-4]" cheat
        elif chat_text.startswith("youhavemykeep"):
            logger.debug(f"Detected youhavemykeep cheat")
            # Extract player number
            try:
                player_num = int(chat_text[-1])  # Get last character
                logger.debug(f"Player number: {player_num}")
                if player_num < 1 or player_num > 4:
                    logger.debug(f"Invalid player number: {player_num}")
                    return False
                player_index = player_num - 1  # Convert to 0-indexed

                # Get territory - try multiple sources with L16 validation
                territory = ui_state.get('selected_territory')
                plot_index = None
                logger.debug(f"selected_territory: {territory}")

                # L16: Validate territory still exists in game state
                if territory and territory not in game_state.territory_owners:
                    logger.debug(f"selected_territory '{territory}' no longer valid, skipping")
                    territory = None

                if not territory:
                    selected_plot = ui_state.get('selected_plot')
                    logger.debug(f"selected_plot: {selected_plot}")
                    if selected_plot:
                        t, pi = selected_plot
                        # L16: Validate territory from plot still exists
                        if t in game_state.territory_owners:
                            territory, plot_index = t, pi

                if not territory:
                    # Try hovered territory as last resort
                    territory = ui_state.get('hovered_territory')
                    logger.debug(f"hovered_territory: {territory}")
                    # L16: Validate hovered territory exists
                    if territory and territory not in game_state.territory_owners:
                        territory = None

                if not territory:
                    logger.warning("Cheat failed: no territory found. Hover over or click a territory first.")
                    game_state.add_message(f"[CHEAT] Hover over or click a territory first!")
                    return True  # Still handled, just show error

                logger.debug(f"Using territory: {territory}")

                # If no specific plot selected, use plot 0 (first plot)
                # Find first available plot if none selected
                if plot_index is None:
                    # Most territories have 5 plots (0-4), iterate to find first empty one
                    plot_index = None
                    for i in range(5):
                        is_occupied = False

                        # Check if plot has completed building
                        if territory in game_state.buildings:
                            if i in game_state.buildings[territory]:
                                is_occupied = True

                        # Check if plot has building under construction
                        if territory in game_state.under_construction:
                            if i in game_state.under_construction[territory]:
                                is_occupied = True

                        if not is_occupied:
                            plot_index = i
                            logger.debug(f"Found empty plot at index {i}")
                            break

                    if plot_index is None:
                        logger.warning(f"Cheat failed: no available plots in {territory}")
                        game_state.add_message(f"[CHEAT] No available plots in {territory}!")
                        return True
                else:
                    # Check if manually selected plot is already occupied
                    if territory in game_state.buildings:
                        if plot_index in game_state.buildings[territory]:
                            logger.warning(f"Cheat failed: plot {plot_index} already has a completed building")
                            game_state.add_message(f"[CHEAT] Plot already occupied!")
                            return True

                    if territory in game_state.under_construction:
                        if plot_index in game_state.under_construction[territory]:
                            logger.warning(f"Cheat failed: plot {plot_index} already has a building under construction")
                            game_state.add_message(f"[CHEAT] Plot already occupied!")
                            return True

                logger.debug(f"Territory: {territory}, Plot: {plot_index}")

                # Set territory owner if not already owned (for testing purposes)
                current_owner = game_state.territory_owners.get(territory, -1)
                if current_owner != player_index:
                    logger.info(f"Cheat: Claiming {territory} for Player {player_num} (was Player {current_owner + 1 if current_owner >= 0 else 'neutral'})")
                    game_state.territory_owners[territory] = player_index
                    game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    game_state.invalidate_territorial_bonus_cache()  # Ownership changed

                # Instantly build a Keep (add to completed buildings)
                if territory not in game_state.buildings:
                    game_state.buildings[territory] = {}

                game_state.buildings[territory][plot_index] = 'Keep'

                logger.info(f"Cheat: Built Keep in {territory} plot {plot_index} for Player {player_num}")
                game_state.add_message(f"[CHEAT] Player {player_num} built a Keep in {territory}")
                return True

            except (ValueError, IndexError) as e:
                logger.debug(f"Cheat code parsing error: {e}")
                return False

        # Check for "ilearn" cheat - awards 50 XP to all units in selected territory
        elif chat_text == "ilearn":
            logger.debug(f"Detected ilearn cheat")
            # Get selected territory
            territory = ui_state.get('selected_territory')
            if territory and territory not in game_state.territory_owners:
                territory = None
            if not territory:
                selected_plot = ui_state.get('selected_plot')
                if selected_plot:
                    t, _ = selected_plot
                    if t in game_state.territory_owners:
                        territory = t
            if not territory:
                territory = ui_state.get('hovered_territory')
                if territory and territory not in game_state.territory_owners:
                    territory = None

            if not territory:
                game_state.add_message(f"[CHEAT] Hover over or click a territory first!")
                return True

            # Award 50 XP to all units in this territory for the current player
            player = game_state.current_player
            awarded_any = False

            # Award unit XP
            garrison = game_state.territory_garrisons.get(territory, {}).get(player)
            if garrison and garrison.get('units'):
                units = garrison['units']
                for unit in units:
                    game_state.award_unit_xp(unit, 50)
                game_state.add_message(f"[CHEAT] Awarded 50 XP to {len(units)} units in {territory}")
                logger.info(f"Cheat: Awarded 50 XP to {len(units)} units in {territory} for Player {player + 1}")
                awarded_any = True

            # Award building XP to Farms/Mines in the territory
            bldg_count = 0
            if territory in game_state.buildings:
                for plot_idx, bldg_type in game_state.buildings[territory].items():
                    if bldg_type in ('Farm', 'Mine'):
                        game_state.award_building_xp(territory, plot_idx, 50)
                        bldg_count += 1
            if bldg_count > 0:
                game_state.add_message(f"[CHEAT] Awarded 50 XP to {bldg_count} building{'s' if bldg_count > 1 else ''} in {territory}")
                logger.info(f"Cheat: Awarded 50 XP to {bldg_count} buildings in {territory}")
                awarded_any = True

            if not awarded_any:
                game_state.add_message(f"[CHEAT] No units or buildings found in {territory}!")
            return True

        logger.debug(f"Not a cheat code: '{chat_text_original}'")
        return False
