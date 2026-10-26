# -*- coding: utf-8 -*-
# tests/test_release_readiness.py
# Checks for a full-release build. Keep this file at release: it guards against
# open-beta-only parts shipping in the full game (CODE_GUIDE "Open beta only: remove at
# full release").

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _open_beta_leftovers():
    """The open-beta-only parts still in the code (owner, 2026-10-22: the Wishlist
    button and the one-time wishlist prompt must go at full release)."""
    import config.constants as constants
    from settings_manager import SETTING_TYPES
    leftovers = []
    if hasattr(constants, 'OPEN_BETA'):
        leftovers.append('OPEN_BETA in config/constants.py')
    for name in ('wishlist.py', os.path.join('tests', 'test_wishlist.py')):
        if os.path.exists(os.path.join(PROJECT_ROOT, name)):
            leftovers.append(name)
    if 'wishlist_prompt_shown' in SETTING_TYPES:
        leftovers.append("the 'wishlist_prompt_shown' setting (settings_manager.py)")
    return leftovers


def test_no_open_beta_parts_in_a_full_game_build():
    """The open beta runs as the Playtest app (4518130); the full release as the main
    game (4518100). Once STEAM_APP_ID is the main game's, every open-beta-only part
    must be gone - this fails until they are."""
    from steam_integration import MAIN_GAME_APP_ID, STEAM_APP_ID
    leftovers = _open_beta_leftovers()
    if STEAM_APP_ID == MAIN_GAME_APP_ID:
        assert not leftovers, ('Full release build: remove the open-beta-only parts '
                               '(CODE_GUIDE "Open beta only: remove at full release"): '
                               + ', '.join(leftovers))
    else:
        # Open beta (Playtest app id): the beta parts belong here, and they are all
        # listed by the check above, so the release check will see every one of them
        assert len(leftovers) == 4, leftovers
