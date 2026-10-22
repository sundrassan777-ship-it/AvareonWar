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
#   steam_manager.set_hosting_presence("+connect steam-<id>,ip:port")  # lobby open
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

# The full game's App ID (STEAM_APP_ID above is the Playtest the open beta runs as). Its
# store page is where players wishlist the game (wishlist.py); at full release
# STEAM_APP_ID becomes this, which tests/test_release_readiness.py uses to demand that
# the open-beta-only parts are gone.
MAIN_GAME_APP_ID = 4518100

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
# A request for the same host as the invite this game was launched with is that invite
# again - not a second join - if it arrived while the start-up join was still running,
# or within the grace seconds after it ended. One that arrives later is the host
# inviting again (two-PC test 2026-10-13: re-invites after the player left the host's
# lobby were dropped by the old fixed 2-minute window). The 2 minutes remain the cap
# for a start-up join that never reports its end.
JOIN_REQUEST_LAUNCH_DEDUPE_SECONDS = 120
JOIN_REQUEST_LAUNCH_GRACE_SECONDS = 5
# A request older than this is dropped: the host's lobby is most likely gone by now
JOIN_REQUEST_MAX_AGE_SECONDS = 600

# Hosting presence (Steam rich presence), set by the host's lobby while it is open and
# read by friends' Join screens - Steam shares rich presence between friends playing the
# same game (isteamfriends.h):
#   "connect" - the invite's "+connect steam-<id>,ip:port,...": Steam's "Join Game" on
#               the host passes it to the friend's game (launch / callback 337)
#   "status"  - shown in Steam's "view game info" dialog and on our Join screen
#   "steam_display" - what Steam friends lists show next to the game: a localization
#               token whose text lives in docs/steam/rich_presence.vdf, uploaded in
#               Steamworks (Community -> Rich Presence). A token Steam does not know shows
#               nothing (Valve's ISteamFriends docs), so it is safe before the upload.
HOSTING_STATUS = "Hosting a lobby"
HOSTING_DISPLAY_TOKEN = "#Status_Hosting"


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

    # Say which switch did it: a launch option left over from testing turned joining
    # through Steam off for a whole two-PC round (2026-10-13), and the log could not say
    # whether it was the launch option or config.json
    for feature, flag, key, on in (("Joining through Steam (relay)", NO_RELAY_FLAG, 'steam_relay', relay),
                                   ("Steam join requests", NO_JOIN_HOOK_FLAG, 'steam_join_hook', join_hook)):
        if not on:
            sources = []
            if flag in argv:
                sources.append(f"the launch option {flag}")
            if not setting_on(key):
                sources.append(f'"{key}": false in config.json')
            logger.info(f"{feature} switched off by {' and '.join(sources)}")
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
        # When joining that target ended (connected, failed or cancelled); None = not yet
        self._launch_join_done = None
        # Our hosting presence as last set: (connect, status), None = not hosting
        self._hosting_presence = None
        # Hosting friends as last logged (get_hosting_friends logs changes only)
        self._hosting_friends_logged = None
        # Friend count as last logged (get_online_friends logs changes only)
        self._online_friends_logged = None

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
    # Store page in the Steam overlay (wishlist.py)
    # ------------------------------------------------------------------

    def open_store_overlay(self, app_id):
        """Show an app's store page in the Steam overlay. Returns True only when the
        overlay is hooked into the game (IsOverlayEnabled); False when Steam is
        unavailable or the overlay is not there - a Pygame window is not always hooked
        (the same reason F12 screenshots may not work), and asking an unhooked overlay
        does nothing visible, so the caller must open the page another way."""
        if not self._initialized:
            return False
        try:
            if not self._steamworks.Utils.IsOverlayEnabled():
                logger.info("Steam overlay not hooked into the game; store page opens another way")
                return False
            self._steamworks.Friends.ActivateGameOverlayToStore(int(app_id))
            logger.info(f"Opened store page {app_id} in the Steam overlay")
            return True
        except Exception as e:
            logger.warning(f"Steam overlay store page failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Hosting presence (Steam rich presence; HOSTING_STATUS above). Through the flat
    # API (steam_networking): SteamworksPy has no rich presence calls.
    # ------------------------------------------------------------------

    def set_hosting_presence(self, connect_string, status=HOSTING_STATUS):
        """
        Tell friends we host a lobby: rich presence "connect" (Steam shows "Join Game" on
        us, friends' Join screens list us), "status" and "steam_display" (the friends
        list's "Hosting a lobby"). The host's lobby calls this while it is open
        (network/territory_selector.py) and clear_hosting_presence() when it closes or
        launches.

        Returns:
            True if Steam took it
        """
        if not self._initialized:
            return False
        try:
            from steam_networking import steam_net
            ok = steam_net.set_rich_presence('connect', connect_string or '')
            ok = steam_net.set_rich_presence('status', status or '') and ok
            ok = steam_net.set_rich_presence('steam_display', HOSTING_DISPLAY_TOKEN) and ok
        except Exception as e:
            logger.warning(f"Could not set the Steam hosting presence: {e}")
            return False
        self._hosting_presence = (connect_string, status)
        logger.info(f"Steam presence: hosting - friends join with '{connect_string}'"
                    + ("" if ok else " (Steam did not take it)"))
        return ok

    def clear_hosting_presence(self):
        """Friends stop seeing us as hosting (lobby closed or launched). Safe to repeat."""
        if not self._initialized or self._hosting_presence is None:
            return
        self._hosting_presence = None
        try:
            from steam_networking import steam_net
            for key in ('connect', 'status', 'steam_display'):
                steam_net.set_rich_presence(key, '')
        except Exception as e:
            logger.warning(f"Could not clear the Steam hosting presence: {e}")
            return
        logger.info("Steam presence: not hosting")

    def get_hosting_friends(self):
        """
        Friends hosting a lobby now, by name: [{'steam_id', 'name', 'connect', 'status'}]
        - 'connect' without its "+connect" (targets for parse_connect_targets()). Read
        from their rich presence (set_hosting_presence), which Steam shares between friends
        playing the same game. [] without Steam.

        Quiet: the Join screen asks every 2 s, so a line is logged only when the list
        changes (not the "Found N Steam friends" of get_online_friends()).
        """
        if not self._initialized:
            return []
        from network.client import parse_connect_targets
        try:
            from steam_networking import steam_net
            if not steam_net.available:
                return []
            hosting = []
            for steam_id in self._friend_ids():
                connect = connect_target_from_command_line(
                    steam_net.get_friend_rich_presence(steam_id, 'connect'))
                if not parse_connect_targets(connect):
                    continue  # not hosting (or nothing we could join)
                hosting.append({
                    'steam_id': steam_id,
                    'name': self.friend_name(steam_id) or str(steam_id),
                    'connect': connect,
                    'status': steam_net.get_friend_rich_presence(steam_id, 'status'),
                })
        except Exception as e:
            logger.warning(f"Could not read which friends are hosting: {e}")
            return []
        hosting.sort(key=lambda f: f['name'].lower())
        summary = [(f['steam_id'], f['connect']) for f in hosting]
        if summary != self._hosting_friends_logged:
            self._hosting_friends_logged = summary
            listed = ', '.join(f"{f['name']} ('{f['connect']}')" for f in hosting)
            logger.info(f"Friends hosting (Steam presence): {listed or 'none'}")
        return hosting

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
        self._launch_join_done = None
        return target

    def launch_join_finished(self):
        """
        The join of the start-up "+connect" target has ended (connected, failed or
        cancelled): a request for that host arriving from now on (after a short grace) is
        the host inviting again, not the start-up invite a second time. Only the first
        call counts - main.py calls it after every Steam invite join.
        """
        if self._launch_connect_target and self._launch_join_done is None:
            self._launch_join_done = time.monotonic()

    def _is_launch_invite_again(self, join):
        """Whether a join request is the invite this game was launched with, again."""
        if not self._launch_connect_target:
            return False
        window_end = self._launch_time + JOIN_REQUEST_LAUNCH_DEDUPE_SECONDS
        if self._launch_join_done is not None:
            window_end = min(window_end, self._launch_join_done + JOIN_REQUEST_LAUNCH_GRACE_SECONDS)
        return (join.received < window_end
                and same_join_host(join.connect, self._launch_connect_target))

    def _join_request_problem(self, join, now=None):
        """Why a join request is not acted on (a short text for the log), None if it is."""
        now = time.monotonic() if now is None else now
        if not join.connect:
            return "it carries no game to join"
        if now - join.received > JOIN_REQUEST_MAX_AGE_SECONDS:
            return f"older than {JOIN_REQUEST_MAX_AGE_SECONDS // 60} minutes"
        if self._is_launch_invite_again(join):
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

    def drop_join_requests_for(self, connect):
        """
        A join to `connect`'s host just went through: a join request for that same host
        still waiting is dropped (Steam's "Join Game" pressed twice, an invite accepted
        again) - the next menu would otherwise join them a second time, up to
        JOIN_REQUEST_MAX_AGE_SECONDS later (two-PC test 2026-10-13: two presses).
        """
        try:
            from steam_networking import steam_net
            join = steam_net.take_join_request_if(lambda j: same_join_host(j.connect, connect))
        except Exception:
            return
        if join is not None:
            logger.info(f"Steam join request '{join.connect}' dropped: already joined that host")

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
            friends = []
            for steam_id in self._friend_ids():
                name = self._steamworks.Friends.GetFriendPersonaName(steam_id)
                # GetFriendPersonaName returns c_char_p (bytes in Python 3)
                if isinstance(name, bytes):
                    name = name.decode('utf-8')
                if name:
                    friends.append({'steam_id': steam_id, 'name': name})
            # Sort alphabetically by name for consistent display
            friends.sort(key=lambda f: f['name'].lower())
            # Logged when the count changes only - the --sdr-test tool asks every 15 s
            # (its log was mostly this line); the lobby's friend picker on every open
            if len(friends) != self._online_friends_logged:
                self._online_friends_logged = len(friends)
                logger.info(f"Found {len(friends)} Steam friends")
            return friends
        except Exception as e:
            logger.warning(f"Failed to get Steam friends list: {e}")
            return []

    def _friend_ids(self):
        """SteamID64s of our Steam friends (regular friends, online or not)."""
        from steamworks.enums import FriendFlags
        friends = self._steamworks.Friends
        count = friends.GetFriendCount(FriendFlags.IMMEDIATE)
        ids = (friends.GetFriendByIndex(i, FriendFlags.IMMEDIATE) for i in range(count))
        return [steam_id for steam_id in ids if steam_id]

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
        """
        Process pending Steam callbacks. Call once per frame from EVERY screen loop -
        a screen shown while hosting or joining that skips it keeps friends' Steam
        joins from reaching this PC (steam_networking.note_main_pump()).
        """
        if not self._initialized:
            return

        try:
            self._steamworks.run_callbacks()
        except Exception:
            pass
        try:
            # Recorded for the Steam bridge's "pump stopped" warning
            from steam_networking import steam_net
            steam_net.note_main_pump()
        except Exception:
            pass


# Module-level singleton — import this everywhere
steam_manager = SteamManager()
