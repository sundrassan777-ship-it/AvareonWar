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

# Kill switches for the Steam networking features (steam_networking.py), so a build where
# one misbehaves stays playable: a Steam launch option, or the matching config.json key
# set to false. Join hook = "join game" requests while the game runs (callback 337);
# relay = joining/hosting through Steam Datagram Relay.
NO_JOIN_HOOK_FLAG = '--no-steam-join-hook'
NO_RELAY_FLAG = '--no-steam-relay'

# The Steam networking diagnostics launch option (steam_sdr_test.py, started from main.py)
SDR_TEST_FLAG = '--sdr-test'

# Join requests (Steam callback 337: the player accepted an invite or chose "Join Game"
# on a friend while our game runs). The main menu acts on them; in a game or another
# screen they wait for the main menu (in a game, with a toast).
# A request for the same host as the invite this game was launched with, within this
# many seconds of the launch, is that invite again - not a second join.
JOIN_REQUEST_LAUNCH_DEDUPE_SECONDS = 120
# A request older than this is dropped: the host's lobby is most likely gone by now
JOIN_REQUEST_MAX_AGE_SECONDS = 600


def steam_feature_switches(argv=None, settings_obj=None):
    """
    Which Steam networking features may run: (join_hook, relay).

    A feature is off when its launch option is given OR its config.json key is false.

    Args:
        argv: command line (default sys.argv)
        settings_obj: settings source with .get() (default settings_manager.settings)
    """
    import sys
    argv = sys.argv if argv is None else argv
    if settings_obj is None:
        try:
            from settings_manager import settings as settings_obj
        except Exception:
            settings_obj = None

    def setting_on(key):
        if settings_obj is None:
            return True
        try:
            return settings_obj.get(key, True) is not False
        except Exception:
            return True

    join_hook = NO_JOIN_HOOK_FLAG not in argv and setting_on('steam_join_hook')
    relay = NO_RELAY_FLAG not in argv and setting_on('steam_relay')
    return join_hook, relay


def _encode(s):
    """Encode a string to bytes for ctypes calls.
    SteamworksPy methods without explicit argtypes need bytes, not str."""
    if isinstance(s, str):
        return s.encode('utf-8')
    return s


def connect_target_from_args(args):
    """
    The target of a "+connect <target>" launch argument, '' if none. Steam passes it as
    two arguments or as one "+connect <target>" depending on platform; both work (the
    last one given wins).
    """
    args = list(args or [])
    target = ''
    for i, arg in enumerate(args):
        if arg == '+connect' and i + 1 < len(args):
            target = args[i + 1]
        elif arg.startswith('+connect '):
            target = arg[len('+connect '):]
    return target.strip().strip('"').strip()


def connect_target_from_command_line(text):
    """connect_target_from_args() for a whole command line string (ISteamApps's)."""
    return connect_target_from_args((text or '').split())


def same_join_host(first, second):
    """
    Whether two connect strings lead to the same host: the same Steam host when both
    name one ("steam-<id>"), else the same address list.
    """
    from network.client import SteamTarget, parse_connect_targets
    a, b = parse_connect_targets(first), parse_connect_targets(second)
    steam_a = next((t for t in a if isinstance(t, SteamTarget)), None)
    steam_b = next((t for t in b if isinstance(t, SteamTarget)), None)
    if steam_a is not None and steam_b is not None:
        return steam_a == steam_b
    return bool(a) and a == b


class SteamManager:
    """Singleton wrapper for Steamworks SDK.  Safe to call even when Steam is unavailable."""

    def __init__(self):
        self._initialized = False
        self._steamworks = None
        # Whether RequestCurrentStats() callback has been processed —
        # required before SetAchievement/GetAchievement will work
        self._stats_ready = False
        # The "+connect" target this launch came with, and when (join request dedupe)
        self._launch_connect_target = ''
        self._launch_time = time.monotonic()

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

            # Steam networking (relay joining, rich presence, join requests) binds to the
            # DLL SteamworksPy just initialised - so only after SteamInit succeeded
            self._init_networking()

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

    def _init_networking(self):
        """
        Bind steam_networking to the initialised DLL, honouring the kill switches
        (steam_feature_switches). Never fails Steam initialisation: without it,
        multiplayer simply stays TCP-only.

        (Until the two-PC test of 2026-10-13 confirmed the binding on real Steam, only
        --sdr-test bound it; regular play now does too - joining through Steam needs it.)
        """
        try:
            from steam_networking import steam_net
            join_hook, relay = steam_feature_switches()
            steam_net.init(join_hook=join_hook, relay=relay)
        except Exception as e:
            logger.warning(f"Steam networking setup failed: {e}")

    def shutdown(self):
        """Shut down Steamworks SDK.  Safe to call even if not initialized."""
        # The Steam bridge first: it closes its Steam connections (lingering, so a last
        # "Server closing" still goes out) while the networking interface is alive
        try:
            from network.steam_bridge import steam_bridge
            steam_bridge.stop()
        except Exception as e:
            logger.warning(f"Steam bridge shutdown error: {e}")
        # Steam networking next: it unregisters the callbacks Steam would otherwise call
        # into Python during/after SteamShutdown (crash on exit)
        try:
            from steam_networking import steam_net
            steam_net.shutdown()
        except Exception as e:
            logger.warning(f"Steam networking shutdown error: {e}")
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
    # Joining a friend's game: the launch "+connect", join requests (337)
    # ------------------------------------------------------------------

    def launch_connect_target(self, argv=None):
        """
        The "+connect" target this launch came with, '' if none: from Steam's own launch
        command line first (no "launching with arguments" warning once the app's Steam
        configuration sends joins that way), else the OS command line (invites before
        that, older Steam setups). Remembered, so a join request for the same host right
        after start-up is not acted on a second time.

        Call once at start-up, after initialize().
        """
        import sys
        source, target = "Steam's launch command line", ''
        try:
            from steam_networking import steam_net
            target = connect_target_from_command_line(steam_net.launch_command_line())
        except Exception as e:
            logger.warning(f"Could not read Steam's launch command line: {e}")
        if not target:
            source = "the command line"
            target = connect_target_from_args(sys.argv if argv is None else argv)
        if target:
            logger.info(f"Steam invite detected ({source}): will auto-connect to {target}")
        self._launch_connect_target = target
        self._launch_time = time.monotonic()
        return target

    def _join_request_problem(self, join, now=None):
        """Why a join request is not acted on (a short text for the log), None if it is."""
        now = time.monotonic() if now is None else now
        if not join.connect:
            return "it carries no game to join"
        if now - join.received > JOIN_REQUEST_MAX_AGE_SECONDS:
            return f"older than {JOIN_REQUEST_MAX_AGE_SECONDS // 60} minutes"
        if (self._launch_connect_target
                and join.received - self._launch_time < JOIN_REQUEST_LAUNCH_DEDUPE_SECONDS
                and same_join_host(join.connect, self._launch_connect_target)):
            return "it is the invite this game was launched with"
        return None

    def peek_join_request(self):
        """
        The join request waiting for the main menu, None if none (or one that will be
        dropped). Left in place - for the in-game toast; the main menu takes it.
        """
        try:
            from steam_networking import steam_net
            join = steam_net.peek_join_request()
        except Exception:
            return None
        if join is None or self._join_request_problem(join) is not None:
            return None
        return join

    def take_join_request(self):
        """
        The join request to act on now (the main menu calls this every frame), or None.
        Taken: each is acted on once; the newest wins if several arrived.
        """
        try:
            from steam_networking import steam_net
            join = steam_net.take_join_request()
        except Exception:
            return None
        if join is None:
            return None
        problem = self._join_request_problem(join)
        if problem:
            logger.info(f"Steam join request '{join.connect}' ignored: {problem}")
            return None
        logger.info(f"Steam join request: joining '{join.connect}'")
        return join

    def friend_name(self, steam_id):
        """A Steam friend's name, '' if unknown or Steam is unavailable."""
        if not steam_id:
            return ''
        try:
            from steam_networking import steam_net
            name = steam_net.friend_name(steam_id)
        except Exception:
            return ''
        # Steam answers "[unknown]" for people it knows nothing about
        return '' if not name or name == '[unknown]' else name

    def join_request_host_name(self, join):
        """The Steam name of the host a join request leads to, '' if unknown."""
        from network.client import SteamTarget, parse_connect_targets
        for target in parse_connect_targets(join.connect):
            if isinstance(target, SteamTarget):
                name = self.friend_name(target.steam_id)
                if name:
                    return name
        return self.friend_name(join.friend_steam_id)

    # ------------------------------------------------------------------
    # Friend Invites
    # ------------------------------------------------------------------

    def can_invite(self):
        """True if Steam is initialized and friend invite is possible."""
        return self._initialized

    def get_online_friends(self):
        """Return list of online Steam friends as dicts: [{steam_id, name}, ...].
        Returns empty list if Steam is unavailable or on error."""
        if not self._initialized:
            return []

        try:
            from steamworks.enums import FriendFlags
            count = self._steamworks.Friends.GetFriendCount(FriendFlags.IMMEDIATE)
            friends = []
            for i in range(count):
                steam_id = self._steamworks.Friends.GetFriendByIndex(i, FriendFlags.IMMEDIATE)
                if not steam_id:
                    continue
                name = self._steamworks.Friends.GetFriendPersonaName(steam_id)
                # GetFriendPersonaName returns c_char_p (bytes in Python 3)
                if isinstance(name, bytes):
                    name = name.decode('utf-8')
                if name:
                    friends.append({'steam_id': steam_id, 'name': name})
            # Sort alphabetically by name for consistent display
            friends.sort(key=lambda f: f['name'].lower())
            logger.info(f"Found {len(friends)} Steam friends")
            return friends
        except Exception as e:
            logger.warning(f"Failed to get Steam friends list: {e}")
            return []

    def invite_friend(self, steam_id, connect_string):
        """Send a game invite to a Steam friend with a connection string.
        The friend receives a Steam notification; accepting launches the game
        with +connect <connect_string> as a command-line argument (or, if their game
        already runs, sends it a join request - take_join_request()).
        Returns True if the invite was sent successfully."""
        if not self._initialized:
            return False

        try:
            self._steamworks.Friends.InviteFriend(steam_id, _encode(connect_string))
            logger.info(f"Steam invite sent to {steam_id} with connect string '{connect_string}'")
            return True
        except Exception as e:
            logger.warning(f"Failed to send Steam invite to {steam_id}: {e}")
            return False

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
