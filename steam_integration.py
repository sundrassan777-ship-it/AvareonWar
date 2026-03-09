# -*- coding: utf-8 -*-
# steam_integration.py
# Steamworks SDK integration — achievements, stats, and rich presence
#
# Uses SteamworksPy (https://github.com/philippj/SteamworksPy) as the
# native wrapper around the Steamworks C SDK.  All calls are guarded so
# the game runs identically when Steam is unavailable (development, or
# non-Steam builds).
#
# Usage:
#   from steam_integration import steam_manager
#   steam_manager.initialize()          # Call once at startup after pygame.init()
#   steam_manager.unlock_achievement("apprentice")
#   steam_manager.set_rich_presence("Playing Campaign - Mission 3")
#   steam_manager.shutdown()            # Call before sys.exit()

"""
Steam Integration Manager
==========================

Singleton that wraps all Steamworks SDK calls behind a safe interface.
If Steam is not running or the SDK fails to initialize, every method
becomes a silent no-op.  This keeps the game fully playable without Steam.

Requires:
  - SteamworksPy installed (pip install steamworkspy)
  - steam_api64.dll in the game directory (bundled via PyInstaller)
  - steam_appid.txt in working directory (dev only — remove before depot upload)
"""

from utils.logger import get_logger

logger = get_logger(__name__)


class SteamManager:
    """Singleton wrapper for Steamworks SDK.  Safe to call even when Steam is unavailable."""

    def __init__(self):
        self._initialized = False
        self._steamworks = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self):
        """Initialize Steamworks SDK.  Returns True if Steam is available."""
        if self._initialized:
            return True

        try:
            import steamworks
            self._steamworks = steamworks.STEAMWORKS()
            self._steamworks.initialize()
            self._initialized = True
            logger.info("Steamworks SDK initialized successfully")
            return True
        except ImportError:
            logger.info("SteamworksPy not installed — running without Steam integration")
            return False
        except Exception as e:
            logger.warning(f"Steamworks SDK init failed (Steam not running?): {e}")
            self._steamworks = None
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

    # ------------------------------------------------------------------
    # Achievements
    # ------------------------------------------------------------------

    def unlock_achievement(self, achievement_id):
        """Unlock a Steam achievement by its API name (same as achievement_manager id).
        Automatically stores stats to trigger the Steam overlay notification."""
        if not self._initialized:
            return False

        try:
            self._steamworks.UserStats.SetAchievement(achievement_id)
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
            self._steamworks.UserStats.ClearAchievement(achievement_id)
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
            return self._steamworks.UserStats.GetAchievement(achievement_id)
        except Exception:
            return False

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
