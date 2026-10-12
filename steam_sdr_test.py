# -*- coding: utf-8 -*-
# steam_sdr_test.py
# Steam networking diagnostics window, started with the launch option --sdr-test
# (main.py). Checks the Steam Datagram Relay binding (steam_networking.py) on real Steam:
# a single-PC self-test, and host / join / invite between two PCs. Kept in shipped builds
# as a support tool: players never see it unless they set the launch option.
#
# Everything it finds goes to logs/sdr_test.log (next to avareonwar.log) - the frozen
# game has no console window.

"""
Steam SDR test (launch option --sdr-test)
=========================================

Keys:
    S       single-PC self-test (socket pair: struct layout, transfers, callback threads)
    H       start/stop hosting (listen + rich presence "connect"; echoes what it receives)
    I       while hosting: Steam-invite the selected friend
    J       join the selected friend (1 KB / 100 KB / 1 MB echo round trips)
    R       join the host named in the last join request (callback 337)
    Up/Down select a friend     F5 refresh friends     C clear the screen log
    Esc     quit

Two-PC round (each PC: Steam > Library > War of Avareon Playtest > Properties > Launch
Options: --sdr-test): A presses H; B selects A and presses J. With B's game running, A
selects B and presses I - B's window lists the join request. Then repeat with B's game
closed (A invites, B accepts): the log shows whether the request came on the command line,
as callback 337, or both.
"""

import logging
import os
import queue
import socket
import threading
import time
from collections import deque

import pygame

import steam_networking as sn
from steam_networking import steam_net
from steam_integration import steam_manager
from utils.logger import get_logger, LOG_DIR

logger = get_logger('sdr_test')

# Window size (windowed, so the Steam friends list fits beside it)
WINDOW_SIZE = (1100, 700)
# Payload sizes for the echo round trips: small, medium, and a full-size game frame
PAYLOAD_SIZES = (1024, 100 * 1024, 1024 * 1024)
# Bytes per SDR message, as the real bridge will use (Steam's limit is 512 KB)
PIECE_BYTES = 256 * 1024
# How long a join may take before we call it failed (Steam's own limit is CONNECT_TIMEOUT_MS)
JOIN_TIMEOUT = 25.0
# How long one echo round trip may take
ECHO_TIMEOUT = 30.0
# Friends list refresh (the friends call logs a line, so not too often); rich presence poll
FRIENDS_REFRESH_SECONDS = 15.0
PRESENCE_REFRESH_SECONDS = 2.0
# Lines kept for the on-screen log
SCREEN_LOG_LINES = 400

_BACKGROUND = (18, 20, 26)
_TEXT = (220, 220, 210)
_DIM = (140, 140, 135)
_GOOD = (120, 210, 120)
_BAD = (235, 110, 100)
_ACCENT = (230, 190, 90)


def _attach_file_log():
    """Also write this tool's lines (and the binding's) to logs/sdr_test.log."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.FileHandler(os.path.join(LOG_DIR, 'sdr_test.log'), encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)-18s %(message)s',
                                               '%Y-%m-%d %H:%M:%S'))
        handler.setLevel(logging.DEBUG)
        for name in ('sdr_test', 'steam_networking', 'steam_integration'):
            logging.getLogger(name).addHandler(handler)
        return handler
    except OSError as e:
        logger.warning(f"Could not open sdr_test.log: {e}")
        return None


class SdrTest:
    """The --sdr-test window: UI on the main thread, Steam work on worker threads."""

    def __init__(self, screen, connect_target=None):
        self.screen = screen
        self.connect_target = connect_target
        self.running = True
        self.mode = 'idle'                  # 'idle' | 'self-test' | 'host' | 'join'
        self.lines = deque(maxlen=SCREEN_LOG_LINES)
        self._lines_lock = threading.Lock()
        self.font = pygame.font.SysFont('consolas,couriernew,monospace', 15)
        self._text_cache = {}

        # Callback pumping switches (the self-test turns each off once to see who dispatches)
        self.main_pump_enabled = True
        self.worker_pump_enabled = True

        # Status events for the running script, filled by the pump thread
        self._events = queue.Queue()
        self._script = None

        self.friends = []                   # [{'steam_id', 'name', 'connect'}]
        self.selected = 0
        self._friends_time = 0.0
        self._presence_time = 0.0
        self._status_time = 0.0
        self.relay_text = ''
        self.auth_text = ''
        self.hosting_listen = sn.INVALID_HANDLE

        self._pump_thread = threading.Thread(target=self._pump_loop, name='sdr-pump', daemon=True)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, text, color=_TEXT):
        """One line to the screen and to sdr_test.log / avareonwar.log."""
        logger.info(text)
        with self._lines_lock:
            self.lines.append((text, color))

    def check(self, results, name, ok, detail=''):
        """Record and show one PASS/FAIL line of a test script."""
        results.append((name, bool(ok)))
        self.log(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ''),
                 _GOOD if ok else _BAD)

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def _pump_loop(self):
        """Dispatch networking callbacks on this thread and hand events to the script."""
        while self.running:
            try:
                if self.worker_pump_enabled:
                    steam_net.run_callbacks()
                for event in steam_net.poll_status_events():
                    self.log(f"  status: conn {event.conn} {sn.STATE_NAMES.get(event.old_state, event.old_state)}"
                             f" -> {sn.STATE_NAMES.get(event.state, event.state)} "
                             f"(end {event.end_reason} '{event.end_debug}', thread {event.thread})", _DIM)
                    self._events.put(event)
            except Exception as e:
                self.log(f"pump error: {e}", _BAD)
            time.sleep(0.005)

    def _start_script(self, mode, target, *args):
        """Run one test script on its own thread (one at a time)."""
        if self._script is not None and self._script.is_alive():
            self.log(f"Busy ({self.mode}) - wait or stop it first", _ACCENT)
            return
        # Forget events from an earlier script
        while not self._events.empty():
            self._events.get_nowait()
        self.mode = mode

        def wrapper():
            try:
                target(*args)
            except Exception as e:
                logger.exception("SDR test script failed")
                self.log(f"{mode} crashed: {e}", _BAD)
            finally:
                self.mode = 'idle'

        self._script = threading.Thread(target=wrapper, name=f'sdr-{mode}', daemon=True)
        self._script.start()

    def _wait_event(self, predicate, timeout):
        """The first status event matching predicate within timeout seconds, else None."""
        deadline = time.monotonic() + timeout
        while self.running and time.monotonic() < deadline:
            try:
                event = self._events.get(timeout=0.05)
            except queue.Empty:
                continue
            if predicate(event):
                return event
        return None

    def _send_all(self, conn, payload, timeout=10.0):
        """Send payload in PIECE_BYTES messages, retrying while Steam's buffer is full."""
        deadline = time.monotonic() + timeout
        for start in range(0, len(payload), PIECE_BYTES):
            piece = payload[start:start + PIECE_BYTES]
            while True:
                result = steam_net.send(conn, piece)
                if result == sn.RESULT_OK:
                    break
                if result != sn.RESULT_LIMIT_EXCEEDED or time.monotonic() > deadline:
                    return result
                time.sleep(0.005)  # buffer full - Steam drains it as the peer acks
        return sn.RESULT_OK

    def _receive_exactly(self, conn, size, timeout):
        """(bytes, sizes_ok, handles_ok) once `size` bytes arrived on conn, or None on timeout."""
        received = bytearray()
        sizes_ok = handles_ok = True
        deadline = time.monotonic() + timeout
        while self.running and len(received) < size and time.monotonic() < deadline:
            messages = steam_net.receive_messages(conn, 64)
            if messages is None:
                return None
            for message in messages:
                received += message.data
                sizes_ok = sizes_ok and message.size == len(message.data)
                handles_ok = handles_ok and message.conn == conn
            if not messages:
                time.sleep(0.002)
        if len(received) < size:
            return None
        return bytes(received), sizes_ok, handles_ok

    def _log_connection(self, conn):
        """Direct or relayed, plus Steam's detailed report (first lines)."""
        info = steam_net.connection_info(conn)
        if info is None:
            self.log("  (no connection info)", _BAD)
            return
        relayed = bool(info.flags & sn.CONNECTION_FLAG_RELAYED)
        self.log(f"  route: {'RELAYED (SDR)' if relayed else 'DIRECT'} flags={info.flags} "
                 f"pop_relay={info.pop_relay} '{info.description}'", _ACCENT)
        for line in steam_net.detailed_status(conn).splitlines()[:14]:
            self.log(f"    {line}", _DIM)

    # ------------------------------------------------------------------
    # Scripts
    # ------------------------------------------------------------------

    def _self_test(self):
        """Single-PC check of the binding against the real DLL (open items O1/O2)."""
        self.log("=== Self-test (single PC) ===", _ACCENT)
        results = []

        own = steam_net.own_steam_id()
        self.check(results, "own SteamID known", own != 0, str(own))
        self.check(results, "identity round trip (layout)", steam_net.identity_round_trip(own) == own)
        socket_id = steam_net.socket_identity_steam_id()
        self.check(results, "networking identity == own SteamID", socket_id == own, str(socket_id))

        pair = steam_net.create_socket_pair(network_loopback=True)
        self.check(results, "socket pair created", pair is not None, str(pair))
        if pair is None:
            self._summary(results)
            return
        a, b = pair
        info_a, info_b = steam_net.connection_info(a), steam_net.connection_info(b)
        self.check(results, "connection info reads Connected (layout sentinel)",
                   info_a is not None and info_b is not None
                   and info_a.state == sn.STATE_CONNECTED and info_b.state == sn.STATE_CONNECTED,
                   f"{info_a.state if info_a else None}/{info_b.state if info_b else None}")

        for size in PAYLOAD_SIZES:
            payload = os.urandom(size)
            started = time.monotonic()
            sent = self._send_all(a, payload)
            got = self._receive_exactly(b, size, ECHO_TIMEOUT) if sent == sn.RESULT_OK else None
            ms = (time.monotonic() - started) * 1000
            self.check(results, f"{size // 1024 or size} {'KB' if size >= 1024 else 'B'} arrives identical",
                       got is not None and got[0] == payload,
                       f"send={sent}, {ms:.0f} ms, {(size + PIECE_BYTES - 1) // PIECE_BYTES} piece(s)")
            if got is not None:
                self.check(results, "  message size/handle fields (layout sentinel)", got[1] and got[2])
        back = os.urandom(1024)
        self._send_all(b, back)
        got = self._receive_exactly(a, len(back), 5.0)
        self.check(results, "reverse direction 1 KB", got is not None and got[0] == back)

        # O1: the worker thread alone dispatches the status callback (main pump paused)
        self.main_pump_enabled = False
        time.sleep(0.2)
        steam_net.close(a, sn.END_APP_GENERIC, 'self-test close', linger=False)
        event = self._wait_event(lambda e: e.conn == b and e.state in (
            sn.STATE_CLOSED_BY_PEER, sn.STATE_PROBLEM_DETECTED_LOCALLY), 5.0)
        self.check(results, "status callback dispatched by the worker thread (main pump paused)",
                   event is not None and event.thread == 'sdr-pump',
                   f"thread={event.thread if event else 'none in 5 s'}")
        steam_net.close(b)
        self.main_pump_enabled = True

        # Informative: does SteamAPI_RunCallbacks (main thread) dispatch them as well?
        self.worker_pump_enabled = False
        pair = steam_net.create_socket_pair(network_loopback=True)
        if pair is not None:
            steam_net.close(pair[0], sn.END_APP_GENERIC, 'self-test close 2')
            event = self._wait_event(lambda e: e.conn == pair[1], 3.0)
            self.log(f"  info: with only SteamAPI_RunCallbacks pumping, the event came "
                     f"{'on thread ' + event.thread if event else 'NOT within 3 s'}", _DIM)
            self.worker_pump_enabled = True
            steam_net.close(pair[1])
        self.worker_pump_enabled = True

        self.log(f"  join hook registered: {steam_net.join_hook_enabled}", _DIM)
        self._summary(results)

    def _summary(self, results):
        passed = sum(1 for _, ok in results if ok)
        ok = passed == len(results)
        self.log(f"=== Self-test {'PASSED' if ok else 'FAILED'} ({passed}/{len(results)}) ===",
                 _GOOD if ok else _BAD)

    def _host(self):
        """Listen, advertise via rich presence, echo every message back."""
        listen = steam_net.listen(0)
        if not listen:
            self.log("[FAIL] could not create the P2P listen socket", _BAD)
            return
        self.hosting_listen = listen
        own = steam_net.own_steam_id()
        steam_net.set_rich_presence('connect', f'+connect steam-{own}')
        steam_net.set_rich_presence('status', 'SDR test: hosting')
        self.log(f"=== Hosting as {own} (listen socket {listen}); press H again to stop ===", _ACCENT)
        peers = {}       # conn -> remote SteamID
        pending = {}     # conn -> deque of bytes waiting to be echoed
        try:
            while self.running and self.mode == 'host':
                try:
                    event = self._events.get(timeout=0.005)
                except queue.Empty:
                    event = None
                if event is not None:
                    if event.listen_socket == listen and event.state == sn.STATE_CONNECTING \
                            and event.conn not in peers:
                        result = steam_net.accept(event.conn)
                        self.log(f"Incoming from {event.remote_steam_id} "
                                 f"({steam_net.friend_name(event.remote_steam_id)}): accept -> {result}")
                        peers[event.conn] = event.remote_steam_id
                        pending[event.conn] = deque()
                    elif event.conn in peers and event.state == sn.STATE_CONNECTED:
                        self.log(f"Peer {peers[event.conn]} connected", _GOOD)
                        self._log_connection(event.conn)
                    elif event.conn in peers and event.state in (
                            sn.STATE_CLOSED_BY_PEER, sn.STATE_PROBLEM_DETECTED_LOCALLY):
                        self.log(f"Peer {peers[event.conn]} left: end {event.end_reason} "
                                 f"'{event.end_debug}'")
                        steam_net.close(event.conn)
                        peers.pop(event.conn, None)
                        pending.pop(event.conn, None)
                for conn in list(peers):
                    for data in steam_net.receive(conn, 64) or []:
                        pending[conn].append(data)
                    while pending[conn]:
                        result = steam_net.send(conn, pending[conn][0])
                        if result == sn.RESULT_OK:
                            pending[conn].popleft()
                        else:
                            break  # buffer full: retry next loop, never drop
        finally:
            for conn in list(peers):
                steam_net.close(conn, sn.END_APP_GENERIC, 'host stopped', linger=True)
            steam_net.close_listen(listen)
            steam_net.set_rich_presence('connect', '')
            steam_net.set_rich_presence('status', '')
            self.hosting_listen = sn.INVALID_HANDLE
            self.log("=== Hosting stopped ===", _ACCENT)

    def _join(self, steam_id, name):
        """Connect to a host, run the echo round trips, report route + timings (O5/O6)."""
        self.log(f"=== Join {name} ({steam_id}) ===", _ACCENT)
        # O6: open the loopback listener exactly as the real bridge will - note any
        # Windows Firewall prompt now
        loopback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        loopback.bind(('127.0.0.1', 0))
        loopback.listen(1)
        self.log(f"  loopback listener open on 127.0.0.1:{loopback.getsockname()[1]} "
                 f"- note any firewall prompt", _DIM)
        started = time.monotonic()
        conn = steam_net.connect(steam_id, 0)
        try:
            if not conn:
                self.log("[FAIL] ConnectP2P returned no handle", _BAD)
                return
            event = self._wait_event(lambda e: e.conn == conn and e.state in (
                sn.STATE_CONNECTED, sn.STATE_CLOSED_BY_PEER, sn.STATE_PROBLEM_DETECTED_LOCALLY),
                JOIN_TIMEOUT)
            elapsed = time.monotonic() - started
            if event is None or event.state != sn.STATE_CONNECTED:
                info = steam_net.connection_info(conn)
                reason = (event.end_reason, event.end_debug) if event else (
                    (info.end_reason, info.end_debug) if info else (None, 'no info'))
                self.log(f"[FAIL] not connected after {elapsed:.1f} s: end reason {reason[0]} "
                         f"'{reason[1]}'", _BAD)
                return
            self.log(f"[PASS] connected in {elapsed:.1f} s", _GOOD)
            self._log_connection(conn)
            for size in PAYLOAD_SIZES:
                payload = os.urandom(size)
                t0 = time.monotonic()
                sent = self._send_all(conn, payload)
                got = self._receive_exactly(conn, size, ECHO_TIMEOUT) if sent == sn.RESULT_OK else None
                ok = got is not None and got[0] == payload
                self.log(f"[{'PASS' if ok else 'FAIL'}] echo {size} bytes: "
                         f"{(time.monotonic() - t0) * 1000:.0f} ms (send={sent})",
                         _GOOD if ok else _BAD)
        finally:
            if conn:
                steam_net.close(conn, sn.END_APP_GENERIC, 'join test done', linger=True)
            loopback.close()
            self.log("=== Join finished ===", _ACCENT)

    # ------------------------------------------------------------------
    # Friends and status (main thread)
    # ------------------------------------------------------------------

    def _refresh(self, now, force=False):
        if force or now - self._friends_time > FRIENDS_REFRESH_SECONDS:
            self._friends_time = now
            selected_id = (self._selected_friend() or {}).get('steam_id')
            self.friends = [dict(f, connect='') for f in steam_manager.get_online_friends()]
            ids = [f['steam_id'] for f in self.friends]
            self.selected = ids.index(selected_id) if selected_id in ids else 0
            self._presence_time = 0.0
        if now - self._presence_time > PRESENCE_REFRESH_SECONDS:
            self._presence_time = now
            selected_id = (self._selected_friend() or {}).get('steam_id')
            for friend in self.friends:
                friend['connect'] = steam_net.get_friend_rich_presence(friend['steam_id'], 'connect')
            # Hosting friends first (then by name), keeping the same friend selected
            self.friends.sort(key=lambda f: ('steam-' not in f['connect'], f['name'].lower()))
            ids = [f['steam_id'] for f in self.friends]
            self.selected = ids.index(selected_id) if selected_id in ids else 0
        if now - self._status_time > 1.0:
            self._status_time = now
            relay, relay_debug = steam_net.relay_status()
            auth, auth_debug = steam_net.auth_status()
            self.relay_text = f"relay {sn.AVAILABILITY_NAMES.get(relay, relay)} {relay_debug}"
            self.auth_text = f"auth {sn.AVAILABILITY_NAMES.get(auth, auth)} {auth_debug}"

    def _selected_friend(self):
        if not self.friends:
            return None
        return self.friends[max(0, min(self.selected, len(self.friends) - 1))]

    # ------------------------------------------------------------------
    # Input + drawing
    # ------------------------------------------------------------------

    def _handle_key(self, key):
        friend = self._selected_friend()
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif key == pygame.K_DOWN:
            self.selected = min(len(self.friends) - 1, self.selected + 1)
        elif key == pygame.K_F5:
            self._refresh(time.monotonic(), force=True)
        elif key == pygame.K_c:
            with self._lines_lock:
                self.lines.clear()
        elif key == pygame.K_s:
            self._start_script('self-test', self._self_test)
        elif key == pygame.K_h:
            if self.mode == 'host':
                self.mode = 'stopping'      # the host loop sees it and cleans up
            else:
                self._start_script('host', self._host)
        elif key == pygame.K_i:
            if self.mode != 'host' or friend is None:
                self.log("Invite: start hosting (H) and select a friend first", _ACCENT)
            else:
                text = f"+connect steam-{steam_net.own_steam_id()}"
                ok = steam_manager.invite_friend(friend['steam_id'], text)
                self.log(f"Invite to {friend['name']} with '{text}': {'sent' if ok else 'FAILED'}")
        elif key == pygame.K_j:
            if friend is not None:
                self._start_script('join', self._join, friend['steam_id'], friend['name'])
        elif key == pygame.K_r:
            history = steam_net.join_history()
            target = _steam_target(history[-1].connect) if history else None
            if target:
                self._start_script('join', self._join, target, 'host from join request')
            else:
                self.log("No join request with a steam- target received yet", _ACCENT)

    def _render(self, text, color):
        key = (text, color)
        surface = self._text_cache.get(key)
        if surface is None:
            if len(self._text_cache) > 600:
                self._text_cache.clear()
            surface = self.font.render(text, True, color)
            self._text_cache[key] = surface
        return surface

    def _draw(self):
        self.screen.fill(_BACKGROUND)
        width, height = self.screen.get_size()
        line_h = self.font.get_linesize()
        y = 8
        own = steam_net.own_steam_id()
        header = [
            (f"War of Avareon - Steam networking test   App ID {steam_net.app_id()}   "
             f"SteamID {own}   logged on {steam_net.logged_on()}", _ACCENT),
            (f"relay enabled {steam_net.relay_enabled}   join hook {steam_net.join_hook_enabled}   "
             f"mode {self.mode}   launch +connect: {self.connect_target or '-'}", _TEXT),
            (self.relay_text[:150], _DIM),
            (self.auth_text[:150], _DIM),
            ("S self-test  H host/stop  I invite  J join  R join from request  "
             "Up/Down select  F5 friends  C clear  Esc quit", _DIM),
        ]
        for text, color in header:
            self.screen.blit(self._render(text, color), (10, y))
            y += line_h
        # Join requests received (callback 337)
        for join in steam_net.join_history()[-3:]:
            self.screen.blit(self._render(
                f"join request from {join.friend_steam_id}: '{join.connect}'", _GOOD), (10, y))
            y += line_h
        y += 4

        # Friends (left column) and log (right)
        list_w = 330
        top = y
        # Friends: a window that follows the selection, so long lists stay usable
        rows = max(1, (height - top - 8) // line_h)
        first = max(0, min(self.selected - rows // 2, len(self.friends) - rows))
        for index, friend in enumerate(self.friends[first:first + rows], start=first):
            hosting = 'steam-' in friend.get('connect', '')
            marker = '>' if index == self.selected else ' '
            text = f"{marker} {friend['name'][:22]:22} {'HOSTING' if hosting else ''}"
            self.screen.blit(self._render(text, _GOOD if hosting else _TEXT), (10, y))
            y += line_h
            if y > height - line_h:
                break
        with self._lines_lock:
            lines = list(self.lines)
        visible = max(1, (height - top - 8) // line_h)
        y = top
        for text, color in lines[-visible:]:
            self.screen.blit(self._render(text[:110], color), (list_w + 20, y))
            y += line_h
        pygame.display.flip()

    def run(self):
        steam_ok = steam_manager.is_available and steam_net.available
        self.log(f"--sdr-test started. Steam available: {steam_manager.is_available}, "
                 f"networking: {steam_net.available}, launch +connect: {self.connect_target or '-'}")
        if steam_ok:
            self.log(f"App ID {steam_net.app_id()}, SteamID {steam_net.own_steam_id()}, "
                     f"relay {steam_net.relay_enabled}, join hook {steam_net.join_hook_enabled}")
            self._pump_thread.start()
            self._refresh(time.monotonic(), force=True)
        else:
            self.log("Steam networking is not available - start the game through Steam "
                     "(or with Steam running). Esc to quit.", _BAD)
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and steam_ok:
                    self._handle_key(event.key)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
            if steam_ok:
                if self.main_pump_enabled:
                    steam_manager.run_callbacks()   # join requests (337) arrive here
                self._refresh(time.monotonic())
            self._draw()
            clock.tick(30)
        # Let a running script see running=False and clean up (closes, rich presence), and
        # stop the pump: Steam shuts down right after we return (atexit), and a thread
        # still inside a Steam call at that moment would crash the exit
        if self._script is not None:
            self._script.join(timeout=3.0)
        if self._pump_thread.is_alive():
            self._pump_thread.join(timeout=1.0)
        self.log("--sdr-test closed")


def _steam_target(connect):
    """The SteamID64 in a connect string's 'steam-<id>' part, else None."""
    for part in connect.split(','):
        part = part.strip()
        if part.startswith('steam-') and part[len('steam-'):].isdigit():
            return int(part[len('steam-'):])
    return None


def run(screen, connect_target=None):
    """Entry point from main.py (launch option --sdr-test). Returns when the window closes."""
    from display_utils import set_display_mode
    handler = _attach_file_log()
    try:
        screen, _ = set_display_mode(WINDOW_SIZE, False, False)
        pygame.display.set_caption("War of Avareon - Steam networking test")
        pygame.mouse.set_visible(True)
        SdrTest(screen, connect_target).run()
    finally:
        if handler is not None:
            for name in ('sdr_test', 'steam_networking', 'steam_integration'):
                logging.getLogger(name).removeHandler(handler)
            handler.close()
