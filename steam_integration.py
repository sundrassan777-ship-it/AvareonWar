# -*- coding: utf-8 -*-
# steam_integration.py
# Steamworks SDK integration — achievements, stats, rich presence, and persona
#
# Uses SteamworksPy (https://github.com/philippj/SteamworksPy) as the
# native wrapper around the Steamworks C SDK.  All calls are guarded so
# the game runs identically when Steam is unavailable (development, or
# non-Steam builds).
#
# Usage:
#   from steam_integration import steam_manager
#   steam_manager.initialize()          # Call once at startup after pygame.init()
#   steam_manager.pump_until_stats_ready()  # Wait for stats before syncing achievements
#   steam_manager.unlock_achievement("apprentice")
#   steam_manager.set_rich_presence("Playing Campaign - Mission 3")
#   steam_manager.shutdown()            # Call before sys.exit()

"""
Steam Integration Manager
==========================

Singleton that wraps all Steamworks SDK calls behind a safe interface.
If Steam is not running or the SDK fails to initialize, every method
becomes a silent no-op.  This keeps the game fully playable without Steam.

Requires (all gated behind Steamworks partner account):
  - steamworks/ Python folder from https://github.com/philippj/SteamworksPy (copy to project root)
  - SteamworksPy64.dll from SteamworksPy GitHub releases (copy to project root)
  - steam_api64.dll from Steamworks SDK redistributable_bin/win64/ (copy to project root)
  - steam_appid.txt in working directory (dev only — remove before Steam depot upload)
"""

import os
import time

from utils.logger import get_logger

logger = get_logger(__name__)

# Steam App ID — must match Steamworks partner dashboard
STEAM_APP_ID = 4518130


def _encode(s):
    """Encode a string to bytes for ctypes calls.
    SteamworksPy methods without explicit argtypes need bytes, not str."""
    if isinstance(s, str):
        return s.encode('utf-8')
    return s


class SteamManager:
    """Singleton wrapper for Steamworks SDK.  Safe to call even when Steam is unavailable."""

    def __init__(self):
        self._initialized = False
        self._steamworks = None
        # Whether RequestCurrentStats() callback has been processed —
        # required before SetAchievement/GetAchievement will work
        self._stats_ready = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_appid_file():
        """Ensure steam_appid.txt exists in CWD.
        SteamworksPy unconditionally requires this file in os.getcwd(),
        but PyInstaller frozen builds set CWD to _internal/ where it
        doesn't exist.  Create it on-the-fly with our known app ID."""
        appid_path = os.path.join(os.getcwd(), 'steam_appid.txt')
        if not os.path.isfile(appid_path):
            try:
                with open(appid_path, 'w') as f:
                    f.write(str(STEAM_APP_ID))
                logger.info(f"Created steam_appid.txt at {appid_path}")
            except OSError as e:
                logger.warning(f"Could not create steam_appid.txt: {e}")

    def initialize(self):
        """Initialize Steamworks SDK.  Returns True if Steam is available.
        After SteamInit(), requests current user stats so achievements work."""
        if self._initialized:
            return True

        try:
            # SteamworksPy requires steam_appid.txt in CWD — ensure it exists
            # for frozen (PyInstaller) builds where CWD is _internal/
            self._ensure_appid_file()

            import steamworks
            self._steamworks = steamworks.STEAMWORKS()
            self._steamworks.initialize()
            self._initialized = True
            logger.info("Steamworks SDK initialized successfully")

            # Request user stats from Steam servers — REQUIRED before
            # SetAchievement/GetAchievement/StoreStats will function.
            # The callback fires asynchronously via run_callbacks().
            try:
                self._steamworks.UserStats.RequestCurrentStats()
                logger.info("RequestCurrentStats() called — waiting for callback")
            except Exception as e:
                logger.warning(f"RequestCurrentStats() failed: {e}")

            return True
        except ImportError:
            logger.info("SteamworksPy not installed — running without Steam integration")
            return False
        except Exception as e:
            logger.warning(f"Steamworks SDK init failed (Steam not running?): {e}")
            self._steamworks = None
            return False

    def pump_until_stats_ready(self, max_wait=0.5):
        """Poll run_callbacks() until Steam user stats are loaded.
        Uses GetNumAchievements() > 0 as a readiness heuristic.
        Blocks up to max_wait seconds. Call once at startup before sync_to_steam()."""
        if not self._initialized:
            return False

        start = time.time()
        while time.time() - start < max_wait:
            try:
                self._steamworks.run_callbacks()
            except Exception:
                pass
            try:
                # GetNumAchievements returns 0 until stats are loaded
                if self._steamworks.UserStats.GetNumAchievements() > 0:
                    self._stats_ready = True
                    elapsed = time.time() - start
                    logger.info(f"Steam stats ready after {elapsed:.3f}s "
                                f"({self._steamworks.UserStats.GetNumAchievements()} achievements)")
                    return True
            except Exception:
                pass
            time.sleep(0.01)

        # Timed out — mark ready anyway (achievements earned during gameplay
        # will still work since run_callbacks is called every frame)
        self._stats_ready = True
        logger.warning(f"Steam stats readiness timed out after {max_wait}s — proceeding anyway")
        return False

    def shutdown(self):
        """Shut down Steamworks SDK.  Safe to call even if not initialized."""
        if self._initialized and self._steamworks is not None:
            try:
                self._steamworks.unload()
                logger.info("Steamworks SDK shut down")
            except Exception as e:
                logger.warning(f"Steamworks shutdown error: {e}")
        self._initialized = False
        self._steamworks = None

    @property
    def is_available(self):
        """True if Steam SDK initialized successfully."""
        return self._initialized

    @property
    def stats_ready(self):
        """True if Steam user stats have been loaded (or timed out)."""
        return self._stats_ready

    # ------------------------------------------------------------------
    # Achievements
    # ------------------------------------------------------------------

    def unlock_achievement(self, achievement_id):
        """Unlock a Steam achievement by its API name (same as achievement_manager id).
        Automatically stores stats to trigger the Steam overlay notification."""
        if not self._initialized:
            return False

        try:
            # Encode to bytes — SteamworksPy achievement methods lack argtypes
            self._steamworks.UserStats.SetAchievement(_encode(achievement_id))
            self._steamworks.UserStats.StoreStats()
            logger.info(f"Steam achievement unlocked: {achievement_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to unlock Steam achievement '{achievement_id}': {e}")
            return False

    def clear_achievement(self, achievement_id):
        """Clear a Steam achievement (dev/testing only)."""
        if not self._initialized:
            return False

        try:
            self._steamworks.UserStats.ClearAchievement(_encode(achievement_id))
            self._steamworks.UserStats.StoreStats()
            logger.info(f"Steam achievement cleared: {achievement_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to clear Steam achievement '{achievement_id}': {e}")
            return False

    def is_achievement_unlocked(self, achievement_id):
        """Check if a Steam achievement is already unlocked on the Steam side."""
        if not self._initialized:
            return False

        try:
            return self._steamworks.UserStats.GetAchievement(_encode(achievement_id))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Player Identity
    # ------------------------------------------------------------------

    def get_player_name(self):
        """Get the current user's Steam persona name.
        Returns None if Steam is unavailable."""
        if not self._initialized:
            return None

        try:
            name = self._steamworks.Friends.GetPlayerName()
            # GetPersonaName returns c_char_p (bytes in Python 3)
            if isinstance(name, bytes):
                return name.decode('utf-8')
            return name
        except Exception as e:
            logger.warning(f"Failed to get Steam persona name: {e}")
            return None

    # ------------------------------------------------------------------
    # Rich Presence
    # ------------------------------------------------------------------

    def set_rich_presence(self, status):
        """Set Steam rich presence string (shown in friends list)."""
        if not self._initialized:
            return

        try:
            self._steamworks.Friends.SetRichPresence("steam_display", "#Status")
            self._steamworks.Friends.SetRichPresence("status", status)
        except Exception as e:
            logger.warning(f"Failed to set rich presence: {e}")

    def clear_rich_presence(self):
        """Clear Steam rich presence."""
        if not self._initialized:
            return

        try:
            self._steamworks.Friends.ClearRichPresence()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Callbacks (call periodically from game loop)
    # ------------------------------------------------------------------

    def run_callbacks(self):
        """Process pending Steam callbacks.  Call once per frame from the game loop."""
        if not self._initialized:
            return

        try:
            self._steamworks.run_callbacks()
        except Exception:
            pass


# Module-level singleton — import this everywhere
steam_manager = SteamManager()
