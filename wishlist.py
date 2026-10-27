# -*- coding: utf-8 -*-
# wishlist.py
# OPEN BETA ONLY - "Wishlist the full game": the main menu's Wishlist button and the
# one-time prompt on a campaign victory recap.
#
# REMOVE AT FULL RELEASE (owner, 2026-10-22: "It is very important that it is removed
# once the game hits full release"): this file, OPEN_BETA in config/constants.py, the
# Wishlist button in main_menu.py, the prompt in recap_screen.py + main.py
# (show_recap_if_ended), the 'wishlist_prompt_shown' setting and tests/test_wishlist.py.
# Checklist: CODE_GUIDE "Open beta only: remove at full release";
# tests/test_release_readiness.py fails while any of it is left in a full-game build.

"""
Wishlist (open beta only)
=========================

open_wishlist_page() shows the full game's Steam store page, where a logged-in player
wishlists it with one click:
  1. the Steam overlay, when it is hooked into the game (a Pygame window is not always
     hooked - the same reason F12 screenshots may not work),
  2. otherwise the store page in the Steam client (steam://store/<app id>),
  3. otherwise the store page in the web browser.
Always the FULL game's app id (MAIN_GAME_APP_ID 4518100), never the Playtest's
(STEAM_APP_ID 4518130) - the Playtest's own store page is empty.

The prompt: once ever, on the recap after a campaign or Book of Tales victory, once the
player has won WISHLIST_PROMPT_AFTER different missions (owner: "only once, after the
player finishes about 2 or 3 missions, and thats it, no more").
"""

import os
import webbrowser

from config.constants import OPEN_BETA
from steam_integration import MAIN_GAME_APP_ID
from utils.logger import get_logger

logger = get_logger(__name__)

# Store page of the full game: in the Steam client, and on the web as the last resort
STEAM_STORE_URL = f"steam://store/{MAIN_GAME_APP_ID}"
WEB_STORE_URL = f"https://store.steampowered.com/app/{MAIN_GAME_APP_ID}/"

# The main menu button (bottom-left corner): the owner's icon (2026-10-27), a scroll with
# the Steam seal. main_menu.py draws a fallback tile if it ever fails to load. The name is
# matched exactly (case too): Windows forgives a wrong case, a build may not
WISHLIST_ICON_PATH = "assets/wishlisticon.png"
WISHLIST_TOOLTIP = "Wishlist the full game on Steam"

# The one-time prompt: shown after this many different missions won (campaign chapters
# and Book of Tales scenarios alike; the first-time-win list player_level.py keeps)
WISHLIST_PROMPT_AFTER = 3
PROMPT_TITLE = "Enjoying War of Avareon?"
PROMPT_TEXT = "Wishlist the full game"
PROMPT_WISHLIST_LABEL = "Wishlist"
PROMPT_LATER_LABEL = "Not now"


def open_wishlist_page(steam=None):
    """Open the full game's store page so the player can wishlist it. Returns how it
    was opened: 'overlay', 'steam' (the Steam client), 'browser', or 'failed'. Never
    raises - a click on the button must not break the menu."""
    if steam is None:
        from steam_integration import steam_manager
        steam = steam_manager
    # 1. The overlay, only when it is hooked into the game (otherwise the call does nothing)
    try:
        if steam.open_store_overlay(MAIN_GAME_APP_ID):
            return 'overlay'
    except Exception as e:
        logger.warning(f"Wishlist: Steam overlay failed: {e}")
    # 2. The Steam client: Windows hands the steam:// link to it, where the player is logged in
    try:
        os.startfile(STEAM_STORE_URL)
        logger.info(f"Wishlist: opened {STEAM_STORE_URL} in the Steam client")
        return 'steam'
    except Exception as e:  # no Steam client, or not Windows (no os.startfile)
        logger.info(f"Wishlist: Steam client link failed ({e}); opening the web store page")
    # 3. The web browser
    try:
        if webbrowser.open(WEB_STORE_URL):
            return 'browser'
    except Exception as e:
        logger.warning(f"Wishlist: web browser failed: {e}")
    logger.warning("Wishlist: could not open the store page")
    return 'failed'


def missions_won(settings_obj=None):
    """How many different missions (campaign chapters + Book of Tales) the player has
    won at least once."""
    if settings_obj is None:
        from settings_manager import settings as settings_obj
    return len(set(settings_obj.get('campaign_missions_xp_claimed', []) or []))


def prompt_due(game, settings_obj=None):
    """True when the one-time prompt belongs on this game's recap: open beta, a campaign
    or Book of Tales game the local player won, enough missions won, never shown before.
    Call after player_level has recorded the game (it adds a first win to the list)."""
    if not OPEN_BETA:
        return False
    if settings_obj is None:
        from settings_manager import settings as settings_obj
    if settings_obj.get('wishlist_prompt_shown', False):
        return False
    gs = getattr(game, 'game_state', None)
    mission = getattr(game, 'tutorial_mission', None)
    if gs is None or mission is None or not getattr(mission, 'mission_id', None):
        return False                            # Custom Game / multiplayer: never
    if getattr(gs, 'phase', None) != 'ended':
        return False                            # left early: no victory screen
    from player_level import local_human_index
    human = local_human_index(game)
    if human is None or not gs.is_winner(human):
        return False                            # defeats: never
    return missions_won(settings_obj) >= WISHLIST_PROMPT_AFTER


def mark_prompt_shown(settings_obj=None):
    """Remember that the prompt was shown - it never comes back, whatever was clicked."""
    if settings_obj is None:
        from settings_manager import settings as settings_obj
    settings_obj.set('wishlist_prompt_shown', True)
    settings_obj.save()
    logger.info("Wishlist: one-time prompt shown")
