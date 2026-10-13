"""
Steam bridge: multiplayer through Steam Datagram Relay (SDR), with the game's TCP code
left as it is.

    Steam peer --SDR--> [bridge thread] --127.0.0.1 TCP--> NetworkServer   (host)
    NetworkClient --127.0.0.1 TCP--> [bridge thread] --SDR--> host          (joiner)

The bridge copies raw bytes both ways, so the wire format, the server / client logic and
every multiplayer test stay unchanged. Players behind routers that block Direct IP (no
port forwarding, Wi-Fi peers kept apart) can still play: Steam relays the traffic.

One daemon thread per process carries every pair. It is also the only thread that
dispatches Steam's connection status callbacks: ISteamNetworkingSockets::RunCallbacks,
not SteamAPI_RunCallbacks, which does not deliver them (measured on real Steam).

Rules (see CODE_GUIDE.md "Steam joining (SDR bridge)"):
- Pieces: loopback bytes go out as reliable SDR messages of at most PIECE_SIZE. Reliable
  messages arrive complete and in order, so a game frame may straddle two pieces.
- Never drop: a full Steam send buffer (LimitExceeded) keeps the piece and stops reading
  that loopback until it went out (the server's sendall() then waits, as for a slow TCP
  peer). A slow local reader stops us pulling that peer's Steam messages above
  LOCAL_BACKLOG_LIMIT; Steam keeps them for later (lossless - it does not acknowledge
  what it could not queue).
- Closing: everything read is forwarded before Steam's lingering close. A loopback socket
  is closed with SHUT_WR + a short drain, never a plain close() with unread data: Windows
  then resets the connection and the other end loses our last message (a refusal reason,
  "Server closing").
- The host's Steam listen socket stays open from the first hosting until the game exits:
  CloseListenSocket drops every connection accepted on it at once (no lingering), and
  between lobbies an open one lets us tell a joiner "not hosting" straight away.
- A friend's connection request reaches the host only while its MAIN thread runs
  SteamAPI_RunCallbacks (steam_manager.run_callbacks()); this thread's RunCallbacks only
  hands over what that delivered. Every screen shown while hosting or joining pumps it
  each frame; _check_main_pump() logs a screen that does not.
"""

import select
import socket
import threading
import time
from collections import deque
from typing import Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import steam_networking as sn
from steam_networking import steam_net
from utils.logger import get_logger

logger = get_logger(__name__)

# Largest SDR message we send. Steam closes a connection on a message over its 512 KB
# receive limit, so stay well below it.
PIECE_SIZE = 256 * 1024

# Bytes from Steam waiting for a slow local reader before we stop pulling that peer's
# messages (Steam holds the rest; nothing is lost)
LOCAL_BACKLOG_LIMIT = 2 * 1024 * 1024

# Host: joins accepted per SteamID within the window (the server's per-IP limit cannot
# tell Steam peers apart - they all arrive from 127.0.0.1)
PEER_RATE_WINDOW = 10.0   # seconds
PEER_RATE_MAX = 5

# Our own end reasons (Steam reserves 1000-1999 for the game)
END_APP_MIN = 1000
END_APP_MAX = 1999
END_REFUSED_RATE = 1001        # too many attempts from this SteamID
END_LOCAL_FAILED = 1002        # the host's game server would not take the connection
END_NOT_HOSTING = 1003         # Steam listen socket open, but no lobby right now
END_GAME_CLOSED = 1004         # the game is exiting

# Steam's end reasons the player-facing texts tell apart (steamnetworkingtypes.h)
_END_LOCAL_OFFLINE = 3001
_END_LOCAL_RIGHTS = 3005
_END_LOCAL_MIN, _END_LOCAL_MAX = 3000, 3999
_END_REMOTE_MIN, _END_REMOTE_MAX = 4000, 4999
_END_TIMEOUT = 5003
_END_STEAM_CONNECTIVITY = 5005
_END_P2P_RENDEZVOUS = 5008
_END_P2P_NAT_FIREWALL = 5009

LOOP_INTERVAL = 0.005          # seconds between bridge passes when nothing is readable
INFO_CHECK_INTERVAL = 0.5      # backstop: re-read each connection's state this often
CLOSE_DRAIN_SECONDS = 1.0      # time a closing loopback gets to take / hand back data
FLUSH_TO_STEAM_SECONDS = 10.0  # time a closing pair gets to hand its last piece to Steam
LOCAL_CONNECT_TIMEOUT = 2.0    # host: connecting to our own game server
STOP_HOSTING_WAIT = 1.5        # stop_hosting(): wait for joined peers to finish
# Warn when the main thread has not run Steam's callbacks (steam_manager.run_callbacks())
# for this long while we host or carry a connection: a friend's Steam join waiting that
# long has timed out. Shorter stalls only delay a join - a slow PC spends ~7 s building
# the game before its loading screen pumps, which must not warn on every game start.
MAIN_PUMP_WARN_SECONDS = sn.CONNECT_TIMEOUT_MS / 1000
_RECEIVE_BATCH = 32            # Steam messages fetched per call
_DRAIN_READS_PER_PASS = 16     # closing loopback: reads per pass while we wait for its EOF

# Pair phases
_OPEN = 'open'                 # carrying data both ways
_FLUSH_TO_STEAM = 'flush_to_steam'   # loopback ended: last pieces to Steam, then close
_FLUSH_TO_LOCAL = 'flush_to_local'   # Steam ended: last bytes to the loopback, then SHUT_WR
_DRAIN_LOCAL = 'drain_local'   # SHUT_WR sent: read until the loopback closes too
_DONE = 'done'


class SteamJoinError(Exception):
    """A join through Steam could not even start; str(e) is the reason for the player."""


def _sentence(text):
    """First letter upper case ("the host is ..." at the start of a message)."""
    return text[:1].upper() + text[1:] if text else text


def describe_end(end_reason, connected, host_name='', hosting=None):
    """
    What to tell the player about a Steam connection that ended.

    Args:
        end_reason: Steam's ESteamNetConnectionEnd (or one of our END_* codes)
        connected: whether the connection had reached the host before it ended
        host_name: the host's Steam name ('' = unknown)
        hosting: whether the host's rich presence says it is hosting (None = unknown)

    Returns:
        A sentence, or None for an ordinary close (the game's own message - "Host
        disconnected", the host's refusal - says it better)
    """
    who = host_name or "the host"
    if END_APP_MIN <= end_reason <= END_APP_MAX:
        if end_reason == END_REFUSED_RATE:
            return (f"{_sentence(who)} turned the connection away (too many attempts) - "
                    f"wait 10 seconds and try again")
        if end_reason == END_NOT_HOSTING:
            return f"{_sentence(who)} is not hosting a game right now"
        if end_reason == END_LOCAL_FAILED:
            return f"{_sentence(who)}'s game could not take the connection"
        if end_reason == END_GAME_CLOSED:
            return f"{_sentence(who)} closed the game"
        return None
    if end_reason == _END_LOCAL_OFFLINE:
        return "Steam is in offline mode - go online in Steam to join through Steam"
    if end_reason == _END_LOCAL_RIGHTS:
        return "Steam did not allow the connection - check that you are signed in to Steam"
    if _END_LOCAL_MIN <= end_reason <= _END_LOCAL_MAX:
        return "Your PC could not reach Steam's network - check your internet connection"
    if _END_REMOTE_MIN <= end_reason <= _END_REMOTE_MAX:
        return (f"{_sentence(who)}'s connection to Steam has a problem - ask them to "
                f"check their internet connection")
    if end_reason == _END_TIMEOUT:
        if connected:
            return f"Lost the connection to {who} (Steam stopped hearing from them)"
        if hosting:
            return (f"Could not reach {who} through Steam (timed out) - check both PCs' "
                    f"internet connections")
        if hosting is False:
            # Their rich presence (set while their lobby is open) says no lobby - also
            # when their game is closed (Steam clears presence then)
            return f"{_sentence(who)} is not hosting a game right now"
        # Measured on real Steam: "not hosting" and "game closed" both end like this
        return (f"Could not reach {who} through Steam - they may not be hosting right "
                f"now, or their game is closed")
    if end_reason == _END_STEAM_CONNECTIVITY:
        return "Your PC lost its connection to Steam - check your internet connection"
    if end_reason in (_END_P2P_RENDEZVOUS, _END_P2P_NAT_FIREWALL):
        return f"Steam could not find a route to {who} - try again, or use Direct IP"
    if end_reason:
        return f"Steam connection problem with {who} (code {end_reason})"
    if connected:
        return f"Lost the connection to {who}"
    return f"Could not reach {who} through Steam"


class _Pair:
    """One Steam connection and the 127.0.0.1 socket its bytes are copied to / from."""

    def __init__(self, conn, steam_id, side, name=''):
        self.conn = conn                  # Steam connection handle
        self.steam_id = steam_id          # the other end's SteamID64
        self.side = side                  # 'host' (a peer joined us) / 'join' (we joined)
        self.name = name                  # the other end's Steam name ('' = unknown)
        self.sock = None                  # loopback socket (None until it exists)
        self.local_port = 0               # host: our end's port, as the server sees it
        self.listener = None              # join: listener the NetworkClient connects to
        self.listen_port = 0              # join: its port
        self.to_steam = deque()           # pieces Steam has not taken yet (LimitExceeded)
        self.to_local = bytearray()       # Steam bytes the loopback has not taken yet
        self.steam_connected = False      # Steam reported Connected (at some point)
        self.steam_closed = False         # the Steam side has ended
        self.end_reason = 0               # why it ended (ESteamNetConnectionEnd)
        self.end_debug = ''
        self.abandoned = False            # join: the client gave up on it
        self.phase = _OPEN
        self.deadline = 0.0               # end of the current closing phase
        self.next_info_check = 0.0        # backstop: next connection_info() read

    def label(self):
        return f"{self.steam_id} ({self.name})" if self.name else str(self.steam_id)


class SteamJoin:
    """
    One join attempt through Steam, as NetworkClient.connect_steam() sees it: the local
    port to connect to, whether Steam reached the host, and why it ended.
    """

    def __init__(self, bridge, pair):
        self._bridge = bridge
        self._pair = pair

    @property
    def local_port(self):
        """127.0.0.1 port of the bridge's listener (connect the NetworkClient here)."""
        return self._pair.listen_port

    @property
    def steam_id(self):
        return self._pair.steam_id

    @property
    def host_name(self):
        return self._pair.name

    @property
    def reached_host(self):
        """Steam got through to the host (its game accepted the Steam connection)."""
        return self._pair.steam_connected

    @property
    def ended(self):
        return self._pair.steam_closed

    @property
    def host_game_refused(self):
        """
        The host's game itself ended the attempt: "not hosting" (END_NOT_HOSTING) or
        "game closed" (END_GAME_CLOSED, its game exiting while we connected). That is
        final for the whole invite: the host's bridge stops hosting only when its game
        server stops (NetworkServer.stop()), so the host's IP addresses cannot answer
        either - no point spending 5 s on each of them (owner's two-PC test 5,
        2026-10-13).
        """
        return (self._pair.steam_closed and
                self._pair.end_reason in (END_NOT_HOSTING, END_GAME_CLOSED))

    @property
    def host_not_hosting(self):
        """
        Steam timed out without reaching the host, and the host's rich presence says they
        host no lobby (their lobby sets it while open; Steam clears it when their game
        closes): their IP addresses lead nowhere either - skip them (Phase 3 two-PC test
        4: 15 s of Steam, then 10 s of hopeless addresses). False while the presence is
        unknown: then the addresses are still worth a try.
        """
        pair = self._pair
        return (pair.steam_closed and not pair.steam_connected
                and pair.end_reason == _END_TIMEOUT
                and self._bridge.friend_is_hosting(pair.steam_id) is False)

    def failure_reason(self):
        """Why the Steam side ended, for the player; None while it is fine (or closed normally)."""
        pair = self._pair
        if not pair.steam_closed:
            return None
        hosting = None
        if not pair.steam_connected and pair.end_reason == _END_TIMEOUT:
            hosting = self._bridge.friend_is_hosting(pair.steam_id)
        return describe_end(pair.end_reason, pair.steam_connected, pair.name, hosting)

    def close(self):
        """The client is done with this attempt (gave up or failed): drop what is left."""
        self._bridge._abandon(self._pair)


class SteamBridge:
    """
    Copies the game's TCP byte stream over Steam connections (see the module docstring).
    One per process (steam_bridge); tests make their own with a fake Steam API.
    """

    def __init__(self, api=None):
        self._api = api if api is not None else steam_net
        # The thread holds this for a whole pass; other threads take it for a moment
        self._lock = threading.RLock()
        self._thread = None
        # Pairs being carried (pumped each pass), and the Steam handle -> pair routing for
        # status events. Separate on purpose: a pair whose Steam side closed has no handle
        # left but still has to hand its last bytes to the loopback.
        self._active = []
        self._by_conn = {}
        self._listen_socket = 0          # host: Steam P2P listen socket (0 = none)
        self._hosting = False             # host: a lobby / game is accepting Steam peers
        self._server_port = 0             # host: TCP port of our NetworkServer
        self._attempts = {}               # host: SteamID -> [monotonic times] (rate limit)
        self._labels = {}                 # host: our loopback port -> "Steam <id> (<name>)"
        self._pump_stalled_from = None    # last main pump before a stall we warned about

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def available(self):
        """Steam's relay is up on this PC (Steam running, signed in at start, not switched off)."""
        return bool(getattr(self._api, 'relay_enabled', False))

    @property
    def hosting(self):
        return self._hosting

    def host_steam_id(self):
        """Our SteamID64 while hosting through Steam (the "steam-<id>" invite target), else 0."""
        return self._api.own_steam_id() if self._hosting else 0

    def unavailable_reason(self):
        """Why we cannot join through Steam right now, or None if we can."""
        if not getattr(self._api, 'available', False):
            return "Steam is not running - start Steam to join through Steam"
        if not self.available:
            if getattr(self._api, 'relay_switched_off', False):
                return ("Joining through Steam is switched off on this PC "
                        "(--no-steam-relay / steam_relay in config.json)")
            return "Steam's relay network could not be started on this PC"
        if not self._api.logged_on():
            return "Steam is offline - go online in Steam to join through Steam"
        return None

    def friend_is_hosting(self, steam_id):
        """
        Whether the friend's rich presence "connect" invites to their Steam lobby: True /
        False, or None when presence cannot be read on this PC (unknown - not "no").
        """
        if not getattr(self._api, 'available', True):
            return None
        try:
            connect = self._api.get_friend_rich_presence(steam_id, 'connect')
        except Exception:
            return None
        return f"steam-{steam_id}" in (connect or '')

    def peer_label(self, address):
        """
        "Steam <id> (<name>) (local port N)" when a server-side connection from `address`
        is one of our Steam peers, else None (server logs).
        """
        if not address or address[0] not in ('127.0.0.1', '::1'):
            return None
        with self._lock:
            label = self._labels.get(address[1])
        return f"{label} (local port {address[1]})" if label else None

    # ------------------------------------------------------------------
    # Host side
    # ------------------------------------------------------------------

    def start_hosting(self, server_port):
        """
        Accept Steam peers and hand each to our game server at 127.0.0.1:server_port.

        Returns:
            True if Steam peers can join now
        """
        if not self.available:
            # Logged: the first thing to check when a friend cannot join through Steam
            logger.info("Not hosting through Steam (Steam not running, offline at start-up, "
                        "or --no-steam-relay) - players can join by IP only")
            return False
        with self._lock:
            if not self._listen_socket:
                self._listen_socket = self._api.listen(0)
                if not self._listen_socket:
                    logger.warning("Steam hosting unavailable: could not open a Steam listen socket")
                    return False
            self._server_port = server_port
            self._hosting = True
            self._ensure_thread()
        logger.info(f"Hosting through Steam as {self._api.own_steam_id()} "
                    f"(local server port {server_port})")
        return True

    def stop_hosting(self, wait=STOP_HOSTING_WAIT):
        """
        Stop taking Steam peers. Peers already joined end with their loopback (the server
        closes it); this waits briefly for their last bytes to reach Steam. The listen
        socket stays open (module docstring) and refuses joiners with "not hosting".
        """
        with self._lock:
            if not self._hosting:
                return
            self._hosting = False
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            with self._lock:
                if not any(p.side == 'host' for p in self._active):
                    break
            time.sleep(0.01)
        with self._lock:
            leftovers = [p for p in self._active if p.side == 'host']
            for pair in leftovers:
                logger.warning(f"Steam peer {pair.label()}: still open when hosting stopped, closing")
                self._close_steam(pair, sn.END_APP_GENERIC, 'Host stopped', linger=True)
                self._close_socket(pair)
                self._finish(pair)
        logger.info("Steam hosting stopped")

    def _on_incoming(self, event):
        """A Steam peer is connecting to our listen socket."""
        steam_id = event.remote_steam_id
        if not self._hosting:
            self._api.close(event.conn, END_NOT_HOSTING, 'Not hosting', False)
            logger.info(f"Steam peer {steam_id}: refused, not hosting right now")
            return
        now = time.monotonic()
        attempts = [t for t in self._attempts.get(steam_id, []) if now - t < PEER_RATE_WINDOW]
        if len(attempts) >= PEER_RATE_MAX:
            self._attempts[steam_id] = attempts
            self._api.close(event.conn, END_REFUSED_RATE, 'Too many connection attempts', False)
            logger.warning(f"Steam peer {steam_id}: refused, {len(attempts)} attempts in "
                           f"{PEER_RATE_WINDOW:.0f} s")
            return
        attempts.append(now)
        self._attempts[steam_id] = attempts
        if len(self._attempts) > 64:
            # Forget peers whose attempts are all old (keeps the table small)
            self._attempts = {k: v for k, v in self._attempts.items()
                              if v and now - v[-1] < PEER_RATE_WINDOW}

        result = self._api.accept(event.conn)
        if result != sn.RESULT_OK:
            logger.warning(f"Steam peer {steam_id}: accepting failed (EResult {result})")
            self._api.close(event.conn, 0, '', False)
            return
        pair = _Pair(event.conn, steam_id, 'host', self._name(steam_id))
        self._add(pair)
        logger.info(f"Steam peer {pair.label()} is connecting")

    def _open_local(self, pair):
        """Host: connect the newly arrived Steam peer to our game server."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port = 0
        try:
            # Bind first: the label must exist before the server can accept us
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            self._labels[port] = f"Steam {pair.label()}"
            sock.settimeout(LOCAL_CONNECT_TIMEOUT)
            sock.connect(('127.0.0.1', self._server_port))
            sock.setblocking(False)
        except OSError as e:
            logger.error(f"Steam peer {pair.label()}: could not reach our game server: {e}")
            self._labels.pop(port, None)
            try:
                sock.close()
            except OSError:
                pass
            self._close_steam(pair, END_LOCAL_FAILED, 'Host could not take the connection', linger=False)
            self._finish(pair)
            return
        pair.sock = sock
        pair.local_port = port
        logger.info(f"Steam peer {pair.label()} -> local port {port}")

    # ------------------------------------------------------------------
    # Joiner side
    # ------------------------------------------------------------------

    def open_join(self, steam_id):
        """
        Start a Steam connection to a host and open the 127.0.0.1 listener that a
        NetworkClient connects to (only the first connection is taken).

        Raises:
            SteamJoinError: Steam cannot connect at all (reason in the message)
        """
        problem = self.unavailable_reason()
        if problem:
            raise SteamJoinError(problem)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # 127.0.0.1 only: nothing outside this PC can use the bridge (and Windows
            # Firewall does not ask about loopback listeners)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.setblocking(False)
        except OSError as e:
            listener.close()
            raise SteamJoinError(f"Could not open the local Steam bridge: {e}")
        with self._lock:
            conn = self._api.connect(steam_id, 0)
            if not conn:
                listener.close()
                raise SteamJoinError("Steam could not start a connection to the host")
            pair = _Pair(conn, steam_id, 'join', self._name(steam_id))
            pair.listener = listener
            pair.listen_port = listener.getsockname()[1]
            self._add(pair)
            self._ensure_thread()
        logger.info(f"Joining Steam host {pair.label()} (local port {pair.listen_port}, "
                    f"{self._relay_text()})")
        return SteamJoin(self, pair)

    def _relay_text(self):
        """Steam's relay network state for the log: a join started before it is ready
        spends part of its 15 s waiting for it."""
        try:
            available, _ = self._api.relay_status()
        except Exception:
            return "relay state unknown"
        if available == sn.AVAILABILITY_CURRENT:
            return "relay ready"
        return f"relay {sn.AVAILABILITY_NAMES.get(available, available)}"

    def _abandon(self, pair):
        """
        The client gave up: if Steam never got through, stop trying now (an attempt
        would otherwise run on for up to 15 s). A connected pair ends through the EOF
        of the client's closed socket.
        """
        with self._lock:
            pair.abandoned = True
            if pair.phase == _OPEN and not pair.steam_connected:
                self._close_steam(pair, sn.END_APP_GENERIC, 'Join cancelled', linger=False)
                self._close_socket(pair)
                self._finish(pair)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def stop(self):
        """
        Close everything (game exit). Runs before steam_networking shuts down, while
        Steam can still flush the lingering closes.
        """
        with self._lock:
            for pair in list(self._active):
                self._close_steam(pair, END_GAME_CLOSED, 'Game closed', linger=True)
                self._close_socket(pair)
                self._finish(pair)
            if self._listen_socket:
                self._api.close_listen(self._listen_socket)
                self._listen_socket = 0
            self._hosting = False
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    # ------------------------------------------------------------------
    # The bridge thread
    # ------------------------------------------------------------------

    def _ensure_thread(self):
        """Start the bridge thread if it is not running (call with the lock held)."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name='steam-bridge', daemon=True)
            self._thread.start()

    def _run(self):
        while True:
            with self._lock:
                if not self._active and not self._listen_socket:
                    self._thread = None   # nothing left to carry: a new job starts a new thread
                    return
                try:
                    self._api.run_callbacks()
                    events = self._api.poll_status_events()
                except Exception as e:
                    logger.error(f"Steam bridge: reading status changes failed: {e}", exc_info=True)
                    events = []
                for event in events:
                    # One at a time: a failing event must not cost the others (a join, a close)
                    try:
                        self._on_status(event)
                    except Exception as e:
                        logger.error(f"Steam bridge: status change {event.state} of "
                                     f"connection {event.conn} failed: {e}", exc_info=True)
                now = time.monotonic()
                for pair in list(self._active):
                    if pair.phase == _DONE:
                        continue  # finished earlier in this pass
                    try:
                        self._pump(pair, now)
                    except Exception as e:
                        logger.error(f"Steam bridge: pair {pair.label()} failed: {e}", exc_info=True)
                        self._close_steam(pair, sn.END_APP_GENERIC, 'Bridge error', linger=True)
                        self._close_socket(pair)
                        self._finish(pair)
                self._check_main_pump(now)
                readable = self._wanted_readable()
            self._wait(readable)

    def _check_main_pump(self, now):
        """
        Log when the main thread stops running Steam's callbacks while we host or carry a
        connection, and when it resumes (call with the lock held). Friends' incoming Steam
        joins reach this PC only through that pump (steam_networking.note_main_pump), so
        a screen without steam_manager.run_callbacks() shows up here, not as a mystery
        timeout on the friend's PC.
        """
        last = getattr(self._api, 'main_pump_time', 0.0) or 0.0
        if not last or not (self._hosting or self._active):
            self._pump_stalled_from = None   # not pumped yet / nothing that needs it
            return
        age = now - last
        if age >= MAIN_PUMP_WARN_SECONDS:
            if self._pump_stalled_from is None:
                self._pump_stalled_from = last
                doing = "hosting" if self._hosting else "connected"
                logger.warning(f"Steam callbacks have not run for {age:.0f} s while {doing} "
                               f"through Steam - friends' Steam joins wait unseen until they do "
                               f"(a screen without steam_manager.run_callbacks()?)")
        elif self._pump_stalled_from is not None:
            logger.info(f"Steam callbacks running again after "
                        f"{last - self._pump_stalled_from:.1f} s")
            self._pump_stalled_from = None

    def _wanted_readable(self):
        """Loopback sockets / listeners the next pass would read (call with the lock held)."""
        sockets = []
        for pair in self._active:
            if pair.listener is not None:
                sockets.append(pair.listener)
            elif pair.sock is not None:
                if pair.phase == _DRAIN_LOCAL or (
                        pair.phase == _OPEN and pair.steam_connected and not pair.to_steam):
                    sockets.append(pair.sock)
        return sockets

    @staticmethod
    def _wait(sockets):
        """Sleep until a socket has data, at most LOOP_INTERVAL (Steam is polled)."""
        if sockets:
            try:
                select.select(sockets, [], [], LOOP_INTERVAL)
                return
            except (OSError, ValueError):
                pass  # a socket closed meanwhile - the next pass sorts it out
        time.sleep(LOOP_INTERVAL)

    def _on_status(self, event):
        pair = self._by_conn.get(event.conn)
        if pair is None:
            if (event.state == sn.STATE_CONNECTING and self._listen_socket
                    and event.listen_socket == self._listen_socket):
                self._on_incoming(event)
            return  # a connection we already let go of
        if event.state == sn.STATE_CONNECTED:
            self._on_connected(pair)
        elif event.state in (sn.STATE_CLOSED_BY_PEER, sn.STATE_PROBLEM_DETECTED_LOCALLY):
            self._on_steam_closed(pair, event.end_reason, event.end_debug)

    def _on_connected(self, pair):
        if pair.steam_connected or pair.steam_closed:
            return
        pair.steam_connected = True
        info = self._api.connection_info(pair.conn)
        route = 'relayed' if info and info.flags & sn.CONNECTION_FLAG_RELAYED else 'direct'
        logger.info(f"Steam connection {pair.label()} connected ({route})")
        status = self._api.detailed_status(pair.conn)
        if status:
            logger.info(f"Steam connection {pair.steam_id} status:\n{status.rstrip()}")
        if pair.side == 'host':
            self._open_local(pair)

    def _on_steam_closed(self, pair, end_reason, end_debug):
        """The Steam side ended: hand the loopback what arrived, then close it gracefully."""
        if pair.steam_closed or pair.phase == _DONE:
            return
        pair.steam_closed = True
        pair.end_reason, pair.end_debug = int(end_reason or 0), end_debug or ''
        logger.info(f"Steam connection {pair.label()} closed: {pair.end_reason} '{pair.end_debug}'")
        if pair.phase == _OPEN:
            # Messages that arrived before the close stay readable - take them all
            while True:
                messages = self._api.receive(pair.conn, _RECEIVE_BATCH)
                if not messages:
                    break
                for data in messages:
                    pair.to_local += data
        # Free Steam's handle (the peer is gone - nothing lingers)
        self._close_steam(pair, 0, '', linger=False)
        if pair.listener is not None:
            # A client already waiting on the listener is taken first: a pass runs the
            # status changes before the accept, and closing a listener resets the
            # connections still waiting on it - the client would see a reset, not an end
            self._accept_client(pair)
        if pair.listener is not None:
            # Joiner whose client never connected: refuse it from now on
            self._close_listener(pair)
        if pair.sock is None or pair.phase != _OPEN:
            self._close_socket(pair)
            self._finish(pair)
            return
        pair.phase = _FLUSH_TO_LOCAL
        pair.deadline = time.monotonic() + CLOSE_DRAIN_SECONDS

    # ------------------------------------------------------------------
    # Moving bytes
    # ------------------------------------------------------------------

    def _pump(self, pair, now):
        if pair.phase == _OPEN:
            self._pump_open(pair, now)
        elif pair.phase == _FLUSH_TO_STEAM:
            self._send_pending(pair)
            if pair.phase != _FLUSH_TO_STEAM:
                return
            if not pair.to_steam:
                self._finish_to_steam(pair)
            elif now > pair.deadline:
                logger.warning(f"Steam connection {pair.label()}: last data not taken by Steam, closing")
                self._close_steam(pair, sn.END_APP_GENERIC, 'Closed', linger=True)
                self._finish(pair)
        elif pair.phase == _FLUSH_TO_LOCAL:
            waiting = len(pair.to_local)
            if pair.to_local and not self._push_to_local(pair):
                return
            if len(pair.to_local) < waiting:
                # The reader is taking it: the deadline is for a reader that stopped
                pair.deadline = now + CLOSE_DRAIN_SECONDS
            if not pair.to_local:
                try:
                    pair.sock.shutdown(socket.SHUT_WR)
                except OSError:
                    self._close_socket(pair)
                    self._finish(pair)
                    return
                pair.phase = _DRAIN_LOCAL
                pair.deadline = now + CLOSE_DRAIN_SECONDS
            elif now > pair.deadline:
                logger.warning(f"Steam connection {pair.label()}: local side did not take "
                               f"the last {len(pair.to_local)} bytes, closing")
                self._close_socket(pair)
                self._finish(pair)
        elif pair.phase == _DRAIN_LOCAL:
            # Read (and drop) until the loopback closes too, so our close() never resets
            # it before it read our last bytes. A bounded number of reads per pass: a
            # writer that keeps sending must not hold the bridge (and every other pair)
            for _ in range(_DRAIN_READS_PER_PASS):
                try:
                    data = pair.sock.recv(65536)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    data = b''
                if not data:
                    self._close_socket(pair)
                    self._finish(pair)
                    return
            if now > pair.deadline:
                self._close_socket(pair)
                self._finish(pair)

    def _pump_open(self, pair, now):
        if pair.listener is not None:
            self._accept_client(pair)
        if pair.abandoned and not pair.steam_connected:
            # The client gave up before Steam got through: stop trying (once connected,
            # the client's closed socket ends the pair through the normal EOF path)
            self._close_steam(pair, sn.END_APP_GENERIC, 'Join cancelled', linger=False)
            self._close_socket(pair)
            self._finish(pair)
            return

        # Steam -> loopback
        if pair.steam_connected:
            if not self._pull_from_steam(pair):
                return
        if pair.sock is not None and pair.to_local:
            if not self._push_to_local(pair):
                return

        # Loopback -> Steam (only once Steam is connected: a joiner's CONNECT_REQUEST
        # waits in the socket until the host is reached)
        if pair.steam_connected and pair.sock is not None:
            if not self._send_pending(pair):
                return
            if not pair.to_steam:
                self._read_local(pair)
                if pair.phase != _OPEN:
                    return

        # Backstop for a missed status callback
        if now >= pair.next_info_check:
            pair.next_info_check = now + INFO_CHECK_INTERVAL
            info = self._api.connection_info(pair.conn)
            if info is None:
                self._on_steam_closed(pair, pair.end_reason, 'connection vanished')
            elif info.state in (sn.STATE_CLOSED_BY_PEER, sn.STATE_PROBLEM_DETECTED_LOCALLY):
                self._on_steam_closed(pair, info.end_reason, info.end_debug)
            elif info.state == sn.STATE_CONNECTED and not pair.steam_connected:
                self._on_connected(pair)

    def _accept_client(self, pair):
        """Joiner: take the NetworkClient's connection (the first one only)."""
        try:
            sock, _ = pair.listener.accept()
        except (BlockingIOError, InterruptedError):
            return
        except OSError as e:
            logger.warning(f"Steam join {pair.label()}: local listener failed: {e}")
            self._close_listener(pair)
            return
        sock.setblocking(False)
        pair.sock = sock
        self._close_listener(pair)

    def _pull_from_steam(self, pair):
        """Fetch Steam messages into to_local (up to the backlog limit). False = pair ended."""
        while len(pair.to_local) < LOCAL_BACKLOG_LIMIT:
            # Fetch no more than fits (messages are at most one piece each), so the
            # backlog never overshoots the limit by more than one piece
            room = LOCAL_BACKLOG_LIMIT - len(pair.to_local)
            batch = max(1, min(_RECEIVE_BATCH, room // PIECE_SIZE))
            messages = self._api.receive(pair.conn, batch)
            if messages is None:
                self._steam_gone(pair)
                return False
            for data in messages:
                pair.to_local += data
            if len(messages) < batch:
                break  # nothing more waiting
        return True

    def _push_to_local(self, pair):
        """Hand to_local to the loopback without blocking. False = loopback gone."""
        try:
            while pair.to_local:
                chunk = bytes(pair.to_local[:PIECE_SIZE])
                sent = pair.sock.send(chunk)
                del pair.to_local[:sent]
                if sent < len(chunk):
                    break  # its buffer is full - the rest next pass
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as e:
            if pair.phase == _OPEN:
                logger.info(f"Steam connection {pair.label()}: local side closed ({e})")
                self._local_ended(pair)
            else:
                self._close_socket(pair)
                self._finish(pair)
            return False
        return True

    def _read_local(self, pair):
        """Read up to one piece from the loopback and send it; an EOF starts the close."""
        buffer = bytearray()
        ended = False
        while len(buffer) < PIECE_SIZE:
            try:
                data = pair.sock.recv(PIECE_SIZE - len(buffer))
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                ended = True  # reset - nothing more will come
                break
            if not data:
                ended = True
                break
            buffer += data
        if buffer:
            pair.to_steam.append(bytes(buffer))
            if not self._send_pending(pair):
                return
        if ended:
            self._local_ended(pair)

    def _send_pending(self, pair):
        """Give Steam the waiting pieces, oldest first. False = the pair ended."""
        while pair.to_steam:
            result = self._api.send(pair.conn, pair.to_steam[0])
            if result == sn.RESULT_OK:
                pair.to_steam.popleft()
            elif result == sn.RESULT_LIMIT_EXCEEDED:
                return True  # Steam's send buffer is full: same piece next pass
            elif result in (sn.RESULT_NO_CONNECTION, sn.RESULT_INVALID_STATE):
                self._steam_gone(pair)
                return False
            else:
                logger.error(f"Steam connection {pair.label()}: send failed (EResult {result}), closing")
                self._close_steam(pair, sn.END_APP_GENERIC, 'Send failed', linger=False)
                self._close_socket(pair)
                self._finish(pair)
                return False
        return True

    def _local_ended(self, pair):
        """The loopback closed: forward the rest, then close Steam with linger."""
        pair.phase = _FLUSH_TO_STEAM
        pair.deadline = time.monotonic() + FLUSH_TO_STEAM_SECONDS
        self._close_socket(pair)  # nothing more to read; Steam bytes for it cannot be delivered
        pair.to_local.clear()
        if not pair.to_steam:
            self._finish_to_steam(pair)

    def _finish_to_steam(self, pair):
        self._close_steam(pair, sn.END_APP_GENERIC, 'Closed', linger=True)
        self._finish(pair)

    def _steam_gone(self, pair):
        """Steam says the connection is gone without a callback yet: read why, then close."""
        info = self._api.connection_info(pair.conn)
        if info is not None:
            self._on_steam_closed(pair, info.end_reason, info.end_debug)
        else:
            self._on_steam_closed(pair, pair.end_reason, 'connection vanished')

    # ------------------------------------------------------------------
    # Small helpers (lock held)
    # ------------------------------------------------------------------

    def _close_steam(self, pair, reason, debug, linger):
        if pair.conn:
            try:
                self._api.close(pair.conn, reason, debug, linger)
            except Exception as e:
                logger.warning(f"Steam connection {pair.label()}: close failed: {e}")
        # The handle is freed either way; forget it so events for it are ignored
        self._by_conn.pop(pair.conn, None)
        pair.conn = 0

    def _close_socket(self, pair):
        if pair.sock is not None:
            try:
                pair.sock.close()
            except OSError:
                pass
            pair.sock = None
        self._close_listener(pair)

    @staticmethod
    def _close_listener(pair):
        if pair.listener is not None:
            try:
                pair.listener.close()
            except OSError:
                pass
            pair.listener = None

    def _add(self, pair):
        self._active.append(pair)
        self._by_conn[pair.conn] = pair

    def _finish(self, pair):
        """The pair is over: drop it from every table."""
        pair.phase = _DONE
        if pair in self._active:
            self._active.remove(pair)
        if pair.conn:
            self._by_conn.pop(pair.conn, None)
        if pair.local_port:
            self._labels.pop(pair.local_port, None)

    def _name(self, steam_id):
        try:
            name = self._api.friend_name(steam_id)
        except Exception:
            return ''
        # Steam answers "[unknown]" for people it knows nothing about
        return '' if not name or name == '[unknown]' else name


# Module-level singleton - the game's one bridge (tests build their own)
steam_bridge = SteamBridge()
