# -*- coding: utf-8 -*-
# steam_networking.py
# Steam networking through the Steamworks flat API (ctypes): Steam Datagram Relay (SDR)
# connections, relay warm-up, rich presence and the "join game" request callback -
# the Steam calls SteamworksPy does not wrap.
#
# Usage:
#   from steam_networking import steam_net
#   steam_net.init(join_hook=True, relay=True)   # steam_integration does this after SteamInit
#   conn = steam_net.connect(host_steam_id)       # ISteamNetworkingSockets::ConnectP2P
#   steam_net.run_callbacks()                     # dispatch connection status callbacks
#   for event in steam_net.poll_status_events(): ...
#   steam_net.shutdown()                          # steam_integration does this before SteamShutdown

"""
Steam Networking (flat API via ctypes)
=====================================

Why this module exists
----------------------
SteamworksPy (steam_integration.py) has no networking interface, no rich presence and no
way to receive GameRichPresenceJoinRequested_t (Steam callback 337). steam_api64.dll
exports all of them as a flat C API, and SteamworksPy has already loaded AND initialised
that DLL in this process - so we call it directly with ctypes on the SAME module instance
(found with GetModuleHandleW; never a second copy of the DLL).

Everything is a silent no-op when Steam is unavailable (development without Steam, or a
non-Steam build), matching steam_integration.py.

Facts this module relies on (Steamworks SDK 1.63, Win64 - see docs/CODE_GUIDE.md
"Steam joining (SDR bridge)"):
- Structs use #pragma pack(8) except SteamNetworkingIdentity / SteamNetworkingIPAddr,
  which are pack(1). Sizes are asserted at import - a wrong layout must fail loudly,
  never corrupt memory. Output structs get extra slack bytes on top.
- Connection status callbacks are a GLOBAL function pointer, installed once before any
  socket exists. Steam queues them and runs them on whichever thread calls RunCallbacks
  (our run_callbacks(), or SteamAPI_RunCallbacks on the main thread). The handler only
  appends to a locked queue, so either thread is fine.
- A friend's incoming connection request (Steam's P2P rendezvous) reaches this PC only
  while the MAIN thread runs SteamAPI_RunCallbacks (steam_manager.run_callbacks()) - our
  run_callbacks() alone is not enough (two-PC test, 2026-10-13). So every screen shown
  while hosting or joining calls steam_manager.run_callbacks() each frame; the bridge
  logs a warning when that pump stops for long (note_main_pump()).
- Callback 337 is a classic Steam callback (CCallbackBase object + SteamAPI_RegisterCallback).
  SteamworksPy owns callback dispatch, so manual dispatch is not an option; we emulate the
  16-byte C++ object (vtable pointer, uint8 flags, int id) from Python. It runs inside
  SteamAPI_RunCallbacks (steam_manager.run_callbacks(), main thread).
- Every received message is copied and released at once (Release() in finally) - Steam
  leaks it otherwise.
"""

import ctypes
import threading
import time
from collections import deque, namedtuple

from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants (values copied from the SDK 1.63 headers - see the header named on each)
# ---------------------------------------------------------------------------

# Flat-API accessors for the interfaces we use (steam_api_flat.h). The version suffix only
# changes when Valve changes the interface; init() probes the listed versions in order.
_SOCKETS_ACCESSORS = ('SteamAPI_SteamNetworkingSockets_SteamAPI_v012',)
_UTILS_ACCESSORS = ('SteamAPI_SteamNetworkingUtils_SteamAPI_v004',)
_FRIENDS_ACCESSORS = ('SteamAPI_SteamFriends_v018',)
_USER_ACCESSORS = ('SteamAPI_SteamUser_v023',)
_STEAM_UTILS_ACCESSORS = ('SteamAPI_SteamUtils_v010',)
_APPS_ACCESSORS = ('SteamAPI_SteamApps_v008',)

# Buffer for ISteamApps::GetLaunchCommandLine (our "+connect ..." strings are ~100 bytes)
_LAUNCH_COMMAND_LINE_BYTES = 1024

# Invalid handles (steamnetworkingtypes.h)
INVALID_HANDLE = 0

# ESteamNetworkingConnectionState (steamnetworkingtypes.h)
STATE_NONE = 0
STATE_CONNECTING = 1
STATE_FINDING_ROUTE = 2
STATE_CONNECTED = 3
STATE_CLOSED_BY_PEER = 4
STATE_PROBLEM_DETECTED_LOCALLY = 5

STATE_NAMES = {
    STATE_NONE: 'None', STATE_CONNECTING: 'Connecting', STATE_FINDING_ROUTE: 'FindingRoute',
    STATE_CONNECTED: 'Connected', STATE_CLOSED_BY_PEER: 'ClosedByPeer',
    STATE_PROBLEM_DETECTED_LOCALLY: 'ProblemDetectedLocally',
}

# EResult (steamclientpublic.h) - the values the networking calls return
RESULT_OK = 1
RESULT_FAIL = 2
RESULT_NO_CONNECTION = 3
RESULT_INVALID_PARAM = 8
RESULT_INVALID_STATE = 11
RESULT_LIMIT_EXCEEDED = 25
RESULT_IGNORED = 41

# Send flags (steamnetworkingtypes.h): reliable, ordered, may be up to 512 KB
SEND_RELIABLE = 8
# Largest message Steam lets us send (k_cbMaxSteamNetworkingSocketsMessageSizeSend)
MAX_SEND_MESSAGE_SIZE = 512 * 1024

# SteamNetConnectionInfo_t::m_nFlags (steamnetworkingtypes.h)
CONNECTION_FLAG_RELAYED = 16

# ESteamNetConnectionEnd (steamnetworkingtypes.h): application codes are 1000-1999
END_APP_GENERIC = 1000

# ESteamNetworkingAvailability (steamnetworkingtypes.h)
AVAILABILITY_NAMES = {
    -102: 'CannotTry', -101: 'Failed', -100: 'Previously', -10: 'Retrying',
    0: 'Unknown', 1: 'NeverTried', 2: 'Waiting', 3: 'Attempting', 100: 'Current',
}
AVAILABILITY_CURRENT = 100

# ESteamNetworkingIdentityType_SteamID (steamnetworkingtypes.h)
_IDENTITY_TYPE_STEAMID = 16

# Configuration (steamnetworkingtypes.h): value ids, scope, data type
_CONFIG_SEND_BUFFER_SIZE = 9
_CONFIG_TIMEOUT_INITIAL = 24
_CONFIG_SCOPE_GLOBAL = 1
_CONFIG_TYPE_INT32 = 1

# Our global connection defaults. The default send buffer (512 KB) is smaller than one
# game frame can be (MAX_MESSAGE_SIZE 1 MB) - a full buffer makes sends fail with
# k_EResultLimitExceeded. The connect timeout gets more room for relay rendezvous.
SEND_BUFFER_BYTES = 4 * 1024 * 1024
CONNECT_TIMEOUT_MS = 15000

# Callback ids (steam_api.json / isteamfriends.h)
CALLBACK_ID_JOIN_REQUESTED = 337          # GameRichPresenceJoinRequested_t
_CALLBACK_FLAG_REGISTERED = 0x01          # CCallbackBase::k_ECallbackFlagsRegistered

# Extra bytes after every struct Steam writes into (output parameters): if our layout were
# ever short, Steam's write lands in the slack instead of the Python heap
_SLACK_BYTES = 256

# Received join requests kept for diagnostics (the --sdr-test window lists them)
_JOIN_HISTORY_LENGTH = 10


# ---------------------------------------------------------------------------
# Structs (field order from steam_api.json, packing from the headers)
# ---------------------------------------------------------------------------

class SteamNetworkingIPAddr(ctypes.Structure):
    """IPv6 (or IPv4-mapped) address + port. pack(1): 18 bytes."""
    _pack_ = 1
    _fields_ = [('m_ipv6', ctypes.c_uint8 * 16),
                ('m_port', ctypes.c_uint16)]


class SteamNetworkingIdentity(ctypes.Structure):
    """
    Who is on the other end. pack(1): int type, int size, then a 128-byte union whose
    first member (for a SteamID) is the uint64 SteamID64 - split here as uint64 + 120 bytes.
    """
    _pack_ = 1
    _fields_ = [('m_eType', ctypes.c_int),
                ('m_cbSize', ctypes.c_int),
                ('m_steamID64', ctypes.c_uint64),
                ('_union_rest', ctypes.c_uint8 * 120)]


class SteamNetConnectionInfo_t(ctypes.Structure):
    """GetConnectionInfo() output and the core of the status callback. 696 bytes."""
    _pack_ = 8
    _fields_ = [('m_identityRemote', SteamNetworkingIdentity),
                ('m_nUserData', ctypes.c_int64),
                ('m_hListenSocket', ctypes.c_uint32),
                ('m_addrRemote', SteamNetworkingIPAddr),
                ('m__pad1', ctypes.c_uint16),
                ('m_idPOPRemote', ctypes.c_uint32),
                ('m_idPOPRelay', ctypes.c_uint32),
                ('m_eState', ctypes.c_int),
                ('m_eEndReason', ctypes.c_int),
                ('m_szEndDebug', ctypes.c_char * 128),
                ('m_szConnectionDescription', ctypes.c_char * 128),
                ('m_nFlags', ctypes.c_int),
                ('reserved', ctypes.c_uint32 * 63)]


class SteamNetConnectionStatusChangedCallback_t(ctypes.Structure):
    """Passed to the global status callback. 712 bytes, m_info at offset 8."""
    _pack_ = 8
    _fields_ = [('m_hConn', ctypes.c_uint32),
                ('m_info', SteamNetConnectionInfo_t),
                ('m_eOldState', ctypes.c_int)]


class SteamNetworkingMessage_t(ctypes.Structure):
    """A received message (allocated by Steam - we only read it, then Release()). 216 bytes."""
    _pack_ = 8
    _fields_ = [('m_pData', ctypes.c_void_p),
                ('m_cbSize', ctypes.c_int),
                ('m_conn', ctypes.c_uint32),
                ('m_identityPeer', SteamNetworkingIdentity),
                ('m_nConnUserData', ctypes.c_int64),
                ('m_usecTimeReceived', ctypes.c_int64),
                ('m_nMessageNumber', ctypes.c_int64),
                ('m_pfnFreeData', ctypes.c_void_p),
                ('m_pfnRelease', ctypes.c_void_p),
                ('m_nChannel', ctypes.c_int),
                ('m_nFlags', ctypes.c_int),
                ('m_nUserData', ctypes.c_int64),
                ('m_idxLane', ctypes.c_uint16),
                ('_pad1__', ctypes.c_uint16)]


class GameRichPresenceJoinRequested_t(ctypes.Structure):
    """Callback 337: a friend's invite was accepted / "Join Game" clicked while we run. 264 bytes."""
    _pack_ = 8
    _fields_ = [('m_steamIDFriend', ctypes.c_uint64),
                ('m_rgchConnect', ctypes.c_char * 256)]


class SteamRelayNetworkStatus_t(ctypes.Structure):
    """GetRelayNetworkStatus() output (isteamnetworkingutils.h). 272 bytes."""
    _fields_ = [('m_eAvail', ctypes.c_int),
                ('m_bPingMeasurementInProgress', ctypes.c_int),
                ('m_eAvailNetworkConfig', ctypes.c_int),
                ('m_eAvailAnyRelay', ctypes.c_int),
                ('m_debugMsg', ctypes.c_char * 256)]


class SteamNetAuthenticationStatus_t(ctypes.Structure):
    """GetAuthenticationStatus() output (isteamnetworkingsockets.h). 260 bytes."""
    _pack_ = 8
    _fields_ = [('m_eAvail', ctypes.c_int),
                ('m_debugMsg', ctypes.c_char * 256)]


class CCallbackBase(ctypes.Structure):
    """
    Python stand-in for the C++ CCallbackBase (steam_api.h): a vtable pointer, uint8 flags,
    int callback id - 16 bytes, no virtual destructor. Steam keeps a pointer to it while
    registered and calls through the vtable. Slack bytes follow (only the first 16 matter).
    """
    _fields_ = [('vtable', ctypes.c_void_p),
                ('m_nCallbackFlags', ctypes.c_uint8),
                ('m_iCallback', ctypes.c_int),
                ('_slack', ctypes.c_uint8 * 48)]


def _with_slack(struct_type):
    """A struct type followed by _SLACK_BYTES spare bytes, for output parameters."""
    return type(f'{struct_type.__name__}_Slack', (ctypes.Structure,), {
        '_fields_': [('value', struct_type), ('_slack', ctypes.c_uint8 * _SLACK_BYTES)]})


_IdentityOut = _with_slack(SteamNetworkingIdentity)
_ConnectionInfoOut = _with_slack(SteamNetConnectionInfo_t)
_RelayStatusOut = _with_slack(SteamRelayNetworkStatus_t)
_AuthStatusOut = _with_slack(SteamNetAuthenticationStatus_t)

# Sizes/offsets the SDK 1.63 headers give on Win64 (pack rules applied by hand, reproduced
# by ctypes). Checked at import - tests/test_steam_networking.py checks them too.
STRUCT_SIZES = {
    SteamNetworkingIPAddr: 18,
    SteamNetworkingIdentity: 136,
    SteamNetConnectionInfo_t: 696,
    SteamNetConnectionStatusChangedCallback_t: 712,
    SteamNetworkingMessage_t: 216,
    GameRichPresenceJoinRequested_t: 264,
    SteamRelayNetworkStatus_t: 272,
    SteamNetAuthenticationStatus_t: 260,
}
for _struct, _size in STRUCT_SIZES.items():
    assert ctypes.sizeof(_struct) == _size, f"{_struct.__name__}: {ctypes.sizeof(_struct)} != {_size}"
assert SteamNetConnectionStatusChangedCallback_t.m_info.offset == 8
assert CCallbackBase.m_nCallbackFlags.offset == 8 and CCallbackBase.m_iCallback.offset == 12


# ---------------------------------------------------------------------------
# Function signatures (steam_api_flat.h). Handles are uint32, EResult/enums int,
# CSteamID passed by value as uint64, references passed as pointers.
# ---------------------------------------------------------------------------

_P = ctypes.c_void_p
_FUNCTIONS = {
    # Interface accessors
    'SteamAPI_SteamNetworkingSockets_SteamAPI_v012': (_P, []),
    'SteamAPI_SteamNetworkingUtils_SteamAPI_v004': (_P, []),
    'SteamAPI_SteamFriends_v018': (_P, []),
    'SteamAPI_SteamUser_v023': (_P, []),
    'SteamAPI_SteamUtils_v010': (_P, []),
    'SteamAPI_SteamApps_v008': (_P, []),
    # ISteamApps (isteamapps.h: the connect string of a Steam launch, without the OS
    # command line - see launch_command_line())
    'SteamAPI_ISteamApps_GetLaunchCommandLine': (ctypes.c_int, [_P, ctypes.c_char_p, ctypes.c_int]),
    # ISteamNetworkingSockets
    'SteamAPI_ISteamNetworkingSockets_CreateListenSocketP2P': (ctypes.c_uint32, [_P, ctypes.c_int, ctypes.c_int, _P]),
    'SteamAPI_ISteamNetworkingSockets_ConnectP2P': (ctypes.c_uint32, [_P, _P, ctypes.c_int, ctypes.c_int, _P]),
    'SteamAPI_ISteamNetworkingSockets_AcceptConnection': (ctypes.c_int, [_P, ctypes.c_uint32]),
    'SteamAPI_ISteamNetworkingSockets_CloseConnection': (ctypes.c_bool, [_P, ctypes.c_uint32, ctypes.c_int, ctypes.c_char_p, ctypes.c_bool]),
    'SteamAPI_ISteamNetworkingSockets_CloseListenSocket': (ctypes.c_bool, [_P, ctypes.c_uint32]),
    'SteamAPI_ISteamNetworkingSockets_SendMessageToConnection': (ctypes.c_int, [_P, ctypes.c_uint32, _P, ctypes.c_uint32, ctypes.c_int, _P]),
    'SteamAPI_ISteamNetworkingSockets_ReceiveMessagesOnConnection': (ctypes.c_int, [_P, ctypes.c_uint32, _P, ctypes.c_int]),
    'SteamAPI_ISteamNetworkingSockets_GetConnectionInfo': (ctypes.c_bool, [_P, ctypes.c_uint32, _P]),
    'SteamAPI_ISteamNetworkingSockets_GetDetailedConnectionStatus': (ctypes.c_int, [_P, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_int]),
    'SteamAPI_ISteamNetworkingSockets_CreateSocketPair': (ctypes.c_bool, [_P, _P, _P, ctypes.c_bool, _P, _P]),
    'SteamAPI_ISteamNetworkingSockets_GetAuthenticationStatus': (ctypes.c_int, [_P, _P]),
    'SteamAPI_ISteamNetworkingSockets_InitAuthentication': (ctypes.c_int, [_P]),
    'SteamAPI_ISteamNetworkingSockets_RunCallbacks': (None, [_P]),
    'SteamAPI_ISteamNetworkingSockets_GetIdentity': (ctypes.c_bool, [_P, _P]),
    # ISteamNetworkingUtils
    'SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess': (None, [_P]),
    'SteamAPI_ISteamNetworkingUtils_GetRelayNetworkStatus': (ctypes.c_int, [_P, _P]),
    'SteamAPI_ISteamNetworkingUtils_SetConfigValue': (ctypes.c_bool, [_P, ctypes.c_int, ctypes.c_int, ctypes.c_ssize_t, ctypes.c_int, _P]),
    'SteamAPI_ISteamNetworkingUtils_SetGlobalCallback_SteamNetConnectionStatusChanged': (ctypes.c_bool, [_P, _P]),
    # SteamNetworkingIdentity / SteamNetworkingMessage_t helpers
    'SteamAPI_SteamNetworkingIdentity_SetSteamID64': (None, [_P, ctypes.c_uint64]),
    'SteamAPI_SteamNetworkingIdentity_GetSteamID64': (ctypes.c_uint64, [_P]),
    'SteamAPI_SteamNetworkingMessage_t_Release': (None, [_P]),
    # ISteamFriends
    'SteamAPI_ISteamFriends_SetRichPresence': (ctypes.c_bool, [_P, ctypes.c_char_p, ctypes.c_char_p]),
    'SteamAPI_ISteamFriends_ClearRichPresence': (None, [_P]),
    'SteamAPI_ISteamFriends_GetFriendRichPresence': (ctypes.c_char_p, [_P, ctypes.c_uint64, ctypes.c_char_p]),
    'SteamAPI_ISteamFriends_GetFriendPersonaName': (ctypes.c_char_p, [_P, ctypes.c_uint64]),
    'SteamAPI_ISteamFriends_InviteUserToGame': (ctypes.c_bool, [_P, ctypes.c_uint64, ctypes.c_char_p]),
    # ISteamUser / ISteamUtils
    'SteamAPI_ISteamUser_GetSteamID': (ctypes.c_uint64, [_P]),
    'SteamAPI_ISteamUser_BLoggedOn': (ctypes.c_bool, [_P]),
    'SteamAPI_ISteamUtils_GetAppID': (ctypes.c_uint32, [_P]),
    # Classic callbacks (steam_api_internal.h)
    'SteamAPI_RegisterCallback': (None, [_P, ctypes.c_int]),
    'SteamAPI_UnregisterCallback': (None, [_P]),
}

# C function pointer types. x64 Windows has one calling convention, so CFUNCTYPE fits the
# global status callback, and the C++ virtual methods too ('this' arrives as argument 1).
_STATUS_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
# Both CCallbackBase::Run overloads point at ONE function with the longer signature: MSVC
# orders overloaded virtuals in reverse, so whichever slot Steam uses lands here. A call
# with fewer arguments just leaves the unused registers as garbage, which we ignore.
_CALLBACK_RUN_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool, ctypes.c_uint64)
_CALLBACK_SIZE_TYPE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)


# ---------------------------------------------------------------------------
# Python-side records
# ---------------------------------------------------------------------------

# One connection status change, copied out of Steam's callback struct.
# Fields: conn, state, old_state, listen_socket, end_reason, end_debug, description,
#         remote_steam_id, flags, thread (name of the thread that ran the callback), time
StatusEvent = namedtuple('StatusEvent', [
    'conn', 'state', 'old_state', 'listen_socket', 'end_reason', 'end_debug',
    'description', 'remote_steam_id', 'flags', 'thread', 'time'])

# GetConnectionInfo() snapshot (same field meanings as StatusEvent)
ConnectionInfo = namedtuple('ConnectionInfo', [
    'state', 'listen_socket', 'end_reason', 'end_debug', 'description',
    'remote_steam_id', 'flags', 'pop_relay'])

# A received message: its bytes plus the connection/size Steam reported (layout sentinels)
ReceivedMessage = namedtuple('ReceivedMessage', ['data', 'conn', 'size'])

# A "join game" request (callback 337): connect string WITHOUT the "+connect " prefix,
# the friend it came through (0 if none), monotonic time it arrived
JoinRequest = namedtuple('JoinRequest', ['connect', 'friend_steam_id', 'received'])


def _text(raw):
    """C char array / bytes -> str (UTF-8, never raises)."""
    if raw is None:
        return ''
    if isinstance(raw, str):
        return raw
    return bytes(raw).split(b'\0', 1)[0].decode('utf-8', errors='replace')


def parse_join_connect_string(raw):
    """
    The connect string of a join request without the launch-argument prefix.

    Steam hands over exactly what was given to InviteUserToGame / rich presence "connect" -
    which our game writes as "+connect <targets>" (so a game started by Steam sees
    +connect on its command line). Accepts bytes or str; returns '' when empty.
    """
    text = _text(raw).strip()
    if text.startswith('+connect'):
        text = text[len('+connect'):].strip()
    return text


def _identity_steam_id(identity):
    """SteamID64 of an identity, or 0 when it is not a SteamID identity."""
    return identity.m_steamID64 if identity.m_eType == _IDENTITY_TYPE_STEAMID else 0


# ---------------------------------------------------------------------------
# The binding
# ---------------------------------------------------------------------------

class SteamNetworking:
    """
    Steam networking + the Steam calls SteamworksPy lacks. One per process (steam_net).

    The socket methods form the small API the Steam bridge (network/steam_bridge.py)
    uses; tests replace the whole object with a fake that has the same methods.
    """

    def __init__(self):
        self._api = None                  # resolved DLL functions (or a test fake)
        self._sockets = None              # ISteamNetworkingSockets*
        self._utils = None                # ISteamNetworkingUtils*
        self._friends = None              # ISteamFriends*
        self._user = None                 # ISteamUser*
        self._steam_utils = None          # ISteamUtils*
        self._apps = None                 # ISteamApps* (optional: launch command line)
        self.relay_enabled = False        # SDR usable (switch on + init succeeded)
        self.relay_switched_off = False   # the player turned SDR off (--no-steam-relay)
        self.join_hook_enabled = False    # callback 337 registered and layout-checked

        # Connection status events, filled by the status callback (any thread)
        self._events = deque()
        self._events_lock = threading.Lock()

        # When the main thread last ran SteamAPI_RunCallbacks (steam_manager.run_callbacks();
        # 0.0 = not yet). A friend's connection request reaches this PC only through that
        # pump - the bridge warns when it stops for long while we host or carry a connection.
        self.main_pump_time = 0.0

        # Join requests (callback 337): the newest pending one + a short history
        self._join_lock = threading.Lock()
        self._join_pending = None
        self._join_history = deque(maxlen=_JOIN_HISTORY_LENGTH)

        # C-callable objects - kept on the instance for the process lifetime: Steam holds
        # raw pointers to them, and a garbage-collected one would crash the game
        self._status_callback = _STATUS_CALLBACK_TYPE(self._on_status_changed)
        self._join_run = _CALLBACK_RUN_TYPE(self._on_join_requested)
        self._join_size = _CALLBACK_SIZE_TYPE(self._join_struct_size)
        self._join_vtable = None
        self._join_object = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def available(self):
        """True once the Steam DLL and its interfaces were found."""
        return self._api is not None and bool(self._sockets)

    def init(self, join_hook=True, relay=True, api=None):
        """
        Bind to the initialised steam_api64.dll. Call once, after SteamworksPy's SteamInit
        succeeded (steam_integration.SteamManager.initialize()).

        Args:
            join_hook: register callback 337 ("join game" while running). False = kill
                switch (--no-steam-join-hook): invites then only work with the game closed.
            relay: set up Steam Datagram Relay. False = kill switch (--no-steam-relay):
                multiplayer stays TCP-only, as before.
            api: tests pass a fake with the same function attributes instead of the DLL

        Returns:
            True if the DLL and interfaces were found (even with both switches off)
        """
        if self.available:
            return True
        self._api = api if api is not None else self._load_dll()
        if self._api is None:
            return False

        try:
            self._sockets = self._accessor(_SOCKETS_ACCESSORS)
            self._utils = self._accessor(_UTILS_ACCESSORS)
            self._friends = self._accessor(_FRIENDS_ACCESSORS)
            self._user = self._accessor(_USER_ACCESSORS)
            self._steam_utils = self._accessor(_STEAM_UTILS_ACCESSORS)
        except Exception as e:
            logger.warning(f"Steam networking unavailable: interface lookup failed ({e})")
            self._api = None
            return False
        try:
            # Optional: only the launch command line needs it - joining works without
            self._apps = self._accessor(_APPS_ACCESSORS)
        except Exception as e:
            logger.info(f"Steam launch command line unavailable ({e})")
            self._apps = None
        if not (self._sockets and self._utils and self._friends and self._user):
            logger.warning("Steam networking unavailable: Steam returned no interface "
                           "(SteamInit not done?)")
            self._api = None
            return False

        if relay:
            self.relay_enabled = self._init_relay()
        else:
            # Remembered so a join attempt can say "switched off" rather than "failed"
            self.relay_switched_off = True
            logger.info("Steam relay switched off (--no-steam-relay / steam_relay: false)")
        if join_hook:
            self.join_hook_enabled = self._register_join_hook()
        else:
            logger.info("Steam join-request hook switched off "
                        "(--no-steam-join-hook / steam_join_hook: false)")
        logger.info(f"Steam networking ready (relay={self.relay_enabled}, "
                    f"join_hook={self.join_hook_enabled})")
        return True

    def shutdown(self):
        """
        Undo init(). Must run BEFORE SteamAPI_Shutdown (steam_integration does that):
        afterwards Steam would call into Python objects that are about to disappear.
        Callers stop any bridge (open connections) before this.
        """
        if self._api is None:
            return
        if self.join_hook_enabled and self._join_object is not None:
            try:
                self._api.SteamAPI_UnregisterCallback(ctypes.byref(self._join_object))
            except Exception as e:
                logger.warning(f"Could not unregister the join-request hook: {e}")
        if self.relay_enabled:
            try:
                self._api.SteamAPI_ISteamNetworkingUtils_SetGlobalCallback_SteamNetConnectionStatusChanged(
                    self._utils, None)
            except Exception as e:
                logger.warning(f"Could not clear the Steam status callback: {e}")
        self.relay_enabled = False
        self.join_hook_enabled = False
        self._api = None
        self._sockets = self._utils = self._friends = self._user = self._steam_utils = None
        self._apps = None
        logger.info("Steam networking shut down")

    @staticmethod
    def _load_dll():
        """
        The steam_api64.dll instance SteamworksPy loaded (and initialised), with every
        function we use typed. None if it is not loaded or a function is missing.
        """
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
            handle = kernel32.GetModuleHandleW('steam_api64.dll')
        except (AttributeError, OSError) as e:
            logger.info(f"Steam networking unavailable: {e}")
            return None
        if not handle:
            logger.info("Steam networking unavailable: steam_api64.dll is not loaded")
            return None
        try:
            dll = ctypes.CDLL('steam_api64.dll', handle=handle)
            for name, (restype, argtypes) in _FUNCTIONS.items():
                function = getattr(dll, name)
                function.restype = restype
                function.argtypes = argtypes
        except (AttributeError, OSError) as e:
            # An older/newer DLL without one of our functions: stay TCP-only, never crash
            logger.warning(f"Steam networking unavailable: {e}")
            return None
        return dll

    def _accessor(self, names):
        """Call the first available interface accessor of `names` (versioned flat API)."""
        for name in names:
            function = getattr(self._api, name, None)
            if function is not None:
                return function()
        raise AttributeError(f"none of {names} found")

    def _init_relay(self):
        """
        Global status callback first (header rule: callbacks must be in effect before a
        listen socket / connection is created), then our connection defaults, then warm up
        relay pings and our certificate so the first connection does not wait for them.
        """
        api, utils = self._api, self._utils
        try:
            if not api.SteamAPI_ISteamNetworkingUtils_SetGlobalCallback_SteamNetConnectionStatusChanged(
                    utils, ctypes.cast(self._status_callback, ctypes.c_void_p)):
                logger.warning("Steam relay off: Steam refused the status callback")
                return False
            for value_id, value, label in (
                    (_CONFIG_SEND_BUFFER_SIZE, SEND_BUFFER_BYTES, 'send buffer'),
                    (_CONFIG_TIMEOUT_INITIAL, CONNECT_TIMEOUT_MS, 'connect timeout')):
                setting = ctypes.c_int32(value)
                if not api.SteamAPI_ISteamNetworkingUtils_SetConfigValue(
                        utils, value_id, _CONFIG_SCOPE_GLOBAL, 0, _CONFIG_TYPE_INT32,
                        ctypes.byref(setting)):
                    logger.warning(f"Steam relay: could not set the {label} ({value})")
            api.SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess(utils)
            api.SteamAPI_ISteamNetworkingSockets_InitAuthentication(self._sockets)
        except Exception as e:
            logger.warning(f"Steam relay off: setup failed ({e})")
            return False
        return True

    # ------------------------------------------------------------------
    # Join requests (callback 337)
    # ------------------------------------------------------------------

    def _register_join_hook(self):
        """
        Register our emulated CCallbackBase for callback 337, then check Steam's own write:
        SteamAPI_RegisterCallback sets the "registered" flag at offset 8. If that flag is
        not where we expect it, our object layout is wrong - unregister and stay off rather
        than risk a crash later.
        """
        try:
            run = ctypes.cast(self._join_run, ctypes.c_void_p).value
            size = ctypes.cast(self._join_size, ctypes.c_void_p).value
            self._join_vtable = (ctypes.c_void_p * 3)(run, run, size)
            self._join_object = CCallbackBase()
            self._join_object.vtable = ctypes.cast(self._join_vtable, ctypes.c_void_p).value
            self._api.SteamAPI_RegisterCallback(ctypes.byref(self._join_object),
                                                CALLBACK_ID_JOIN_REQUESTED)
        except Exception as e:
            logger.warning(f"Join-request hook off: registration failed ({e})")
            return False
        if not self._join_object.m_nCallbackFlags & _CALLBACK_FLAG_REGISTERED:
            logger.error("Join-request hook off: Steam did not mark it registered "
                         f"(flags={self._join_object.m_nCallbackFlags}) - layout mismatch")
            try:
                self._api.SteamAPI_UnregisterCallback(ctypes.byref(self._join_object))
            except Exception:
                pass
            return False
        logger.info(f"Join-request hook registered (callback id field "
                    f"{self._join_object.m_iCallback})")
        return True

    @staticmethod
    def _join_struct_size(_this):
        """CCallbackBase::GetCallbackSizeBytes - Steam checks it against the payload size."""
        return ctypes.sizeof(GameRichPresenceJoinRequested_t)

    def _on_join_requested(self, _this, param, _io_failure, _api_call):
        """
        CCallbackBase::Run for callback 337 (main thread, inside SteamAPI_RunCallbacks).
        Never lets an exception reach C.
        """
        try:
            request = ctypes.cast(param, ctypes.POINTER(GameRichPresenceJoinRequested_t)).contents
            join = JoinRequest(parse_join_connect_string(request.m_rgchConnect),
                               int(request.m_steamIDFriend), time.monotonic())
            with self._join_lock:
                self._join_pending = join
                self._join_history.append(join)
            logger.info(f"Steam join request from {join.friend_steam_id}: '{join.connect}'")
        except Exception as e:
            logger.warning(f"Could not read a Steam join request: {e}")

    def take_join_request(self):
        """The newest join request not yet handled (then cleared), or None."""
        with self._join_lock:
            join, self._join_pending = self._join_pending, None
        return join

    def peek_join_request(self):
        """The newest join request not yet handled, left in place (the in-game toast)."""
        with self._join_lock:
            return self._join_pending

    def join_history(self):
        """Recent join requests, oldest first (diagnostics)."""
        with self._join_lock:
            return list(self._join_history)

    # ------------------------------------------------------------------
    # Connection status events
    # ------------------------------------------------------------------

    def _on_status_changed(self, pointer):
        """
        Global connection status callback (runs on whichever thread called RunCallbacks).
        Copies what we need and queues it - must stay fast and never raise into C.
        """
        try:
            data = ctypes.cast(pointer, ctypes.POINTER(SteamNetConnectionStatusChangedCallback_t)).contents
            info = data.m_info
            event = StatusEvent(
                conn=int(data.m_hConn), state=int(info.m_eState), old_state=int(data.m_eOldState),
                listen_socket=int(info.m_hListenSocket), end_reason=int(info.m_eEndReason),
                end_debug=_text(info.m_szEndDebug), description=_text(info.m_szConnectionDescription),
                remote_steam_id=_identity_steam_id(info.m_identityRemote), flags=int(info.m_nFlags),
                thread=threading.current_thread().name, time=time.monotonic())
            with self._events_lock:
                self._events.append(event)
        except Exception as e:
            logger.warning(f"Could not read a Steam connection status change: {e}")

    def poll_status_events(self):
        """Every queued status event, oldest first (and clears the queue)."""
        with self._events_lock:
            events = list(self._events)
            self._events.clear()
        return events

    def run_callbacks(self):
        """
        Dispatch queued connection status callbacks on THIS thread
        (ISteamNetworkingSockets::RunCallbacks - not SteamAPI_RunCallbacks, which belongs
        to the main thread).
        """
        if self.relay_enabled:
            self._api.SteamAPI_ISteamNetworkingSockets_RunCallbacks(self._sockets)

    def note_main_pump(self):
        """
        The main thread just ran SteamAPI_RunCallbacks (steam_manager.run_callbacks()).

        That pump - not our run_callbacks() - is what delivers a friend's incoming
        connection request (Steam's P2P rendezvous) to this PC. Measured 2026-10-13 on
        two PCs: while the lobby screen did not pump, a friend's Steam join waited
        unseen on the host and timed out after 15 s; both waiting requests surfaced at
        once when the host reached the main menu, which pumps.
        """
        self.main_pump_time = time.monotonic()

    # ------------------------------------------------------------------
    # Sockets (the bridge's API)
    # ------------------------------------------------------------------

    def listen(self, virtual_port=0):
        """Listen for P2P connections; returns the listen socket handle (0 = failed)."""
        if not self.relay_enabled:
            return INVALID_HANDLE
        return int(self._api.SteamAPI_ISteamNetworkingSockets_CreateListenSocketP2P(
            self._sockets, virtual_port, 0, None))

    def close_listen(self, listen_socket):
        """Stop listening (handle from listen())."""
        if not self.relay_enabled or not listen_socket:
            return False
        return bool(self._api.SteamAPI_ISteamNetworkingSockets_CloseListenSocket(
            self._sockets, listen_socket))

    def connect(self, steam_id, virtual_port=0):
        """Start a P2P connection to a SteamID64; returns the connection handle (0 = failed)."""
        if not self.relay_enabled or not steam_id:
            return INVALID_HANDLE
        identity = _IdentityOut()
        self._api.SteamAPI_SteamNetworkingIdentity_SetSteamID64(ctypes.byref(identity), int(steam_id))
        return int(self._api.SteamAPI_ISteamNetworkingSockets_ConnectP2P(
            self._sockets, ctypes.byref(identity), virtual_port, 0, None))

    def accept(self, conn):
        """Accept an incoming connection (must happen within a second or two); EResult."""
        if not self.relay_enabled:
            return RESULT_NO_CONNECTION
        return int(self._api.SteamAPI_ISteamNetworkingSockets_AcceptConnection(self._sockets, conn))

    def close(self, conn, reason=0, debug='', linger=False):
        """
        Close a connection and free its handle. Unread received data is discarded, and
        sent data is only flushed with linger=True.
        """
        if not self.relay_enabled or not conn:
            return False
        return bool(self._api.SteamAPI_ISteamNetworkingSockets_CloseConnection(
            self._sockets, conn, int(reason), debug.encode('utf-8')[:120] if debug else None,
            bool(linger)))

    def send(self, conn, data, flags=SEND_RELIABLE):
        """
        Send one message (bytes, at most MAX_SEND_MESSAGE_SIZE). Returns the EResult:
        RESULT_LIMIT_EXCEEDED means "buffer full, retry later" - nothing was sent.
        """
        if not self.relay_enabled:
            return RESULT_NO_CONNECTION
        data = bytes(data)
        return int(self._api.SteamAPI_ISteamNetworkingSockets_SendMessageToConnection(
            self._sockets, conn, data, len(data), flags, None))

    def receive_messages(self, conn, max_messages=32):
        """
        Up to max_messages received messages (oldest first), each copied and released at
        once. None if the handle is invalid.
        """
        if not self.relay_enabled:
            return None
        pointers = (ctypes.c_void_p * max_messages)()
        count = self._api.SteamAPI_ISteamNetworkingSockets_ReceiveMessagesOnConnection(
            self._sockets, conn, pointers, max_messages)
        if count < 0:
            return None
        messages = []
        for i in range(min(count, max_messages)):
            pointer = pointers[i]
            if not pointer:
                logger.error(f"Steam returned an empty message slot ({i} of {count})")
                continue  # nothing to read or release
            try:
                message = ctypes.cast(pointer, ctypes.POINTER(SteamNetworkingMessage_t)).contents
                size = int(message.m_cbSize)
                data = ctypes.string_at(message.m_pData, size) if size > 0 else b''
                messages.append(ReceivedMessage(data, int(message.m_conn), size))
            except Exception as e:
                logger.error(f"Could not read a received Steam message: {e}")
            finally:
                # Always: an unreleased message leaks inside Steam
                self._api.SteamAPI_SteamNetworkingMessage_t_Release(pointer)
        return messages

    def receive(self, conn, max_messages=32):
        """Payloads of up to max_messages received messages (see receive_messages())."""
        messages = self.receive_messages(conn, max_messages)
        return None if messages is None else [m.data for m in messages]

    def connection_info(self, conn):
        """ConnectionInfo snapshot of a connection, or None for a bad handle."""
        if not self.relay_enabled:
            return None
        out = _ConnectionInfoOut()
        if not self._api.SteamAPI_ISteamNetworkingSockets_GetConnectionInfo(
                self._sockets, conn, ctypes.byref(out)):
            return None
        info = out.value
        return ConnectionInfo(
            state=int(info.m_eState), listen_socket=int(info.m_hListenSocket),
            end_reason=int(info.m_eEndReason), end_debug=_text(info.m_szEndDebug),
            description=_text(info.m_szConnectionDescription),
            remote_steam_id=_identity_steam_id(info.m_identityRemote),
            flags=int(info.m_nFlags), pop_relay=int(info.m_idPOPRelay))

    def detailed_status(self, conn):
        """Steam's multi-line connection report (for the log); '' for a bad handle."""
        if not self.relay_enabled:
            return ''
        size = 4096
        for _ in range(2):
            buffer = ctypes.create_string_buffer(size)
            result = self._api.SteamAPI_ISteamNetworkingSockets_GetDetailedConnectionStatus(
                self._sockets, conn, buffer, size)
            if result < 0:
                return ''
            if result == 0:
                return _text(buffer.value)
            size = int(result)  # too small: Steam told us how much it needs
        return _text(buffer.value)

    def create_socket_pair(self, network_loopback=True):
        """
        Two connected connections talking to each other (self-test). With
        network_loopback=True the bytes really go through 127.0.0.1 and encryption.
        Returns (conn1, conn2) or None. Close BOTH when done.
        """
        if not self.relay_enabled:
            return None
        first, second = ctypes.c_uint32(0), ctypes.c_uint32(0)
        if not self._api.SteamAPI_ISteamNetworkingSockets_CreateSocketPair(
                self._sockets, ctypes.byref(first), ctypes.byref(second),
                bool(network_loopback), None, None):
            return None
        return int(first.value), int(second.value)

    # ------------------------------------------------------------------
    # Status of the Steam networking services
    # ------------------------------------------------------------------

    def relay_status(self):
        """(availability, debug text) of the relay network (100 = Current)."""
        if not self.relay_enabled:
            return 0, 'relay off'
        out = _RelayStatusOut()
        available = self._api.SteamAPI_ISteamNetworkingUtils_GetRelayNetworkStatus(
            self._utils, ctypes.byref(out))
        return int(available), _text(out.value.m_debugMsg)

    def auth_status(self):
        """(availability, debug text) of our certificate for authenticated connections."""
        if not self.relay_enabled:
            return 0, 'relay off'
        out = _AuthStatusOut()
        available = self._api.SteamAPI_ISteamNetworkingSockets_GetAuthenticationStatus(
            self._sockets, ctypes.byref(out))
        return int(available), _text(out.value.m_debugMsg)

    def retry_authentication(self):
        """Ask Steam to try again for a certificate (it does not retry by itself)."""
        if self.relay_enabled:
            return int(self._api.SteamAPI_ISteamNetworkingSockets_InitAuthentication(self._sockets))
        return 0

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def own_steam_id(self):
        """Our SteamID64 (ISteamUser), 0 if unavailable."""
        if not self.available:
            return 0
        return int(self._api.SteamAPI_ISteamUser_GetSteamID(self._user))

    def logged_on(self):
        """Whether Steam has a live connection to the Steam servers."""
        return bool(self.available and self._api.SteamAPI_ISteamUser_BLoggedOn(self._user))

    def socket_identity_steam_id(self):
        """Our SteamID as ISteamNetworkingSockets sees it (should equal own_steam_id())."""
        if not self.relay_enabled:
            return 0
        out = _IdentityOut()
        if not self._api.SteamAPI_ISteamNetworkingSockets_GetIdentity(self._sockets, ctypes.byref(out)):
            return 0
        return _identity_steam_id(out.value)

    def identity_round_trip(self, steam_id):
        """Write a SteamID64 into an identity with Steam's own setter and read it back (layout check)."""
        if not self.available:
            return 0
        out = _IdentityOut()
        self._api.SteamAPI_SteamNetworkingIdentity_SetSteamID64(ctypes.byref(out), int(steam_id))
        return int(self._api.SteamAPI_SteamNetworkingIdentity_GetSteamID64(ctypes.byref(out)))

    def app_id(self):
        """The App ID Steam runs us as (4518130 for the playtest), 0 if unavailable."""
        if not self.available or not self._steam_utils:
            return 0
        return int(self._api.SteamAPI_ISteamUtils_GetAppID(self._steam_utils))

    def launch_command_line(self):
        """
        The command line Steam started us with when it did not put it on the OS command
        line: steam://run/<appid>//<command line>, or an invite / "Join Game" once the
        app's Steam configuration sends rich presence joins this way (Valve's
        isteamapps.h calls the OS command line a security risk, and Steam warns the
        player about launch arguments). '' if none or unavailable.
        """
        if not self.available or not self._apps:
            return ''
        try:
            buffer = ctypes.create_string_buffer(_LAUNCH_COMMAND_LINE_BYTES)
            length = self._api.SteamAPI_ISteamApps_GetLaunchCommandLine(
                self._apps, buffer, _LAUNCH_COMMAND_LINE_BYTES)
        except Exception as e:
            logger.warning(f"Could not read Steam's launch command line: {e}")
            return ''
        return _text(buffer.value) if length > 0 else ''

    # ------------------------------------------------------------------
    # Friends: rich presence, invites, names
    # ------------------------------------------------------------------

    def set_rich_presence(self, key, value):
        """Set (or with value '' delete) one rich presence key. "connect" enables Join Game."""
        if not self.available:
            return False
        return bool(self._api.SteamAPI_ISteamFriends_SetRichPresence(
            self._friends, key.encode('utf-8'), (value or '').encode('utf-8')))

    def clear_rich_presence(self):
        """Delete all of our rich presence keys."""
        if self.available:
            self._api.SteamAPI_ISteamFriends_ClearRichPresence(self._friends)

    def get_friend_rich_presence(self, steam_id, key):
        """A friend's rich presence value ('' if unset); shared between friends in the same game."""
        if not self.available:
            return ''
        return _text(self._api.SteamAPI_ISteamFriends_GetFriendRichPresence(
            self._friends, int(steam_id), key.encode('utf-8')))

    def friend_name(self, steam_id):
        """A friend's Steam name ('' if unknown)."""
        if not self.available:
            return ''
        return _text(self._api.SteamAPI_ISteamFriends_GetFriendPersonaName(self._friends, int(steam_id)))

    def invite_user_to_game(self, steam_id, connect_string):
        """Steam game invite with a connect string (same call SteamworksPy's InviteFriend makes)."""
        if not self.available:
            return False
        return bool(self._api.SteamAPI_ISteamFriends_InviteUserToGame(
            self._friends, int(steam_id), connect_string.encode('utf-8')))


# Module-level singleton - import this everywhere
steam_net = SteamNetworking()
