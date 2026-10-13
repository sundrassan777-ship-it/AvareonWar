# -*- coding: utf-8 -*-
"""
Steam bridge tests (network/steam_bridge.py): multiplayer through Steam Datagram Relay.

Steam is replaced by FakeSdr - an in-process stand-in with the same calls the bridge
makes on steam_networking.steam_net: reliable, ordered messages between connection
handles, status events dispatched by run_callbacks(), LimitExceeded on demand, a
connection attempt to nobody timing out with Steam's code 5003 (as measured on real
Steam). Everything else is real: the bridge thread, the 127.0.0.1 sockets and, in the
end-to-end tests, NetworkServer and NetworkClient.
"""

import logging
import os
import select
import socket
import sys
import threading
import time
from collections import deque

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import steam_networking as sn  # noqa: E402
import network.steam_bridge as steam_bridge_module  # noqa: E402
from network.client import NetworkClient, SteamTarget  # noqa: E402
from network.server import NetworkServer  # noqa: E402
from network.steam_bridge import (  # noqa: E402
    END_GAME_CLOSED, END_NOT_HOSTING, END_REFUSED_RATE, LOCAL_BACKLOG_LIMIT, PIECE_SIZE,
    PEER_RATE_MAX, SteamBridge, SteamJoinError, describe_end)
from network_config import MessageType  # noqa: E402

HOST_ID = 76561190000000001
JOINER_ID = 76561190000000002
OTHER_ID = 76561190000000003
NOBODY_ID = 76561190000000099     # no PC runs as this SteamID


# ---------------------------------------------------------------------------
# Fake Steam relay
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, handle, pc, remote_id, listen_socket=0):
        self.handle = handle
        self.pc = pc                      # the FakeSteam that owns this end
        self.remote_id = remote_id
        self.listen_socket = listen_socket
        self.peer = None                  # the other end (None = nobody answered)
        self.state = sn.STATE_CONNECTING
        self.inbox = deque()              # messages for this end, oldest first
        self.end_reason = 0
        self.end_debug = ''
        self.deadline = time.monotonic() + pc.sdr.connect_timeout


class FakeSdr:
    """Steam's relay network between fake PCs (one FakeSteam each)."""

    def __init__(self, connect_timeout=0.3):
        self.lock = threading.RLock()
        self.pcs = {}
        self.names = {}
        self.presence = {}                # SteamID -> {rich presence key: value}
        self.connect_timeout = connect_timeout   # stands in for Steam's 15 s
        self._next_handle = 1000

    def pc(self, steam_id, name):
        pc = FakeSteam(self, steam_id)
        self.pcs[steam_id] = pc
        self.names[steam_id] = name
        return pc

    def new_handle(self):
        self._next_handle += 1
        return self._next_handle


class FakeSteam:
    """One PC's steam_net, as far as the bridge uses it."""

    available = True
    relay_enabled = True
    relay_switched_off = False

    def __init__(self, sdr, steam_id):
        self.sdr = sdr
        self.steam_id = steam_id
        self.online = True
        self.conns = {}                   # handle -> _FakeConn
        self.listen_sockets = set()
        self.pending = []                 # status events not dispatched yet
        self.events = deque()             # dispatched, waiting for poll_status_events()
        self.limit_exceeded = 0           # the next N sends answer LimitExceeded
        self.ops = []                     # ('send', h, data, result) / ('close', h, reason, debug, linger)
        self.callback_threads = set()     # threads that ran run_callbacks()

    def _event(self, conn, old_state):
        self.pending.append(sn.StatusEvent(
            conn=conn.handle, state=conn.state, old_state=old_state,
            listen_socket=conn.listen_socket, end_reason=conn.end_reason,
            end_debug=conn.end_debug, description='fake', remote_steam_id=conn.remote_id,
            flags=sn.CONNECTION_FLAG_RELAYED, thread=threading.current_thread().name,
            time=time.monotonic()))

    @staticmethod
    def _set_state(conn, state, reason=0, debug=''):
        old = conn.state
        conn.state = state
        if reason or debug:
            conn.end_reason, conn.end_debug = reason, debug
        conn.pc._event(conn, old)

    # Identity / friends
    def own_steam_id(self):
        return self.steam_id

    def logged_on(self):
        return self.online

    def friend_name(self, steam_id):
        return self.sdr.names.get(steam_id, '')

    def get_friend_rich_presence(self, steam_id, key):
        return self.sdr.presence.get(steam_id, {}).get(key, '')

    # Sockets
    def listen(self, virtual_port=0):
        with self.sdr.lock:
            handle = self.sdr.new_handle()
            self.listen_sockets.add(handle)
            return handle

    def close_listen(self, listen_socket):
        with self.sdr.lock:
            if listen_socket not in self.listen_sockets:
                return False
            self.listen_sockets.discard(listen_socket)
            # Like Steam: connections accepted on it are dropped at once, no lingering
            for conn in [c for c in self.conns.values() if c.listen_socket == listen_socket]:
                self.close(conn.handle, 0, 'listen socket closed', False)
            return True

    def connect(self, steam_id, virtual_port=0):
        with self.sdr.lock:
            conn = _FakeConn(self.sdr.new_handle(), self, steam_id)
            self.conns[conn.handle] = conn
            self._event(conn, sn.STATE_NONE)
            remote = self.sdr.pcs.get(steam_id)
            if remote is not None and remote.online and remote.listen_sockets:
                listen = next(iter(remote.listen_sockets))
                other = _FakeConn(self.sdr.new_handle(), remote, self.steam_id, listen)
                remote.conns[other.handle] = other
                conn.peer, other.peer = other, conn
                remote._event(other, sn.STATE_NONE)
            return conn.handle

    def accept(self, conn_handle):
        with self.sdr.lock:
            conn = self.conns.get(conn_handle)
            if conn is None or conn.state != sn.STATE_CONNECTING or conn.peer is None:
                return sn.RESULT_INVALID_STATE
            self._set_state(conn, sn.STATE_CONNECTED)
            self._set_state(conn.peer, sn.STATE_CONNECTED)
            return sn.RESULT_OK

    def close(self, conn_handle, reason=0, debug='', linger=False):
        with self.sdr.lock:
            self.ops.append(('close', conn_handle, reason, debug, linger))
            conn = self.conns.pop(conn_handle, None)
            if conn is None:
                return False
            peer = conn.peer
            if peer is not None and peer.state in (sn.STATE_CONNECTING, sn.STATE_FINDING_ROUTE,
                                                   sn.STATE_CONNECTED):
                self._set_state(peer, sn.STATE_CLOSED_BY_PEER, reason, debug)
            return True

    def send(self, conn_handle, data, flags=sn.SEND_RELIABLE):
        with self.sdr.lock:
            data = bytes(data)
            conn = self.conns.get(conn_handle)
            if conn is None or conn.state in (sn.STATE_CLOSED_BY_PEER,
                                              sn.STATE_PROBLEM_DETECTED_LOCALLY):
                result = sn.RESULT_NO_CONNECTION
            elif conn.state != sn.STATE_CONNECTED:
                result = sn.RESULT_INVALID_STATE
            elif len(data) > sn.MAX_SEND_MESSAGE_SIZE:
                result = sn.RESULT_INVALID_PARAM
            elif self.limit_exceeded > 0:
                self.limit_exceeded -= 1
                result = sn.RESULT_LIMIT_EXCEEDED
            else:
                conn.peer.inbox.append(data)
                result = sn.RESULT_OK
            self.ops.append(('send', conn_handle, data, result))
            return result

    def receive(self, conn_handle, max_messages=32):
        with self.sdr.lock:
            conn = self.conns.get(conn_handle)
            if conn is None:
                return None
            messages = []
            while conn.inbox and len(messages) < max_messages:
                messages.append(conn.inbox.popleft())
            return messages

    def connection_info(self, conn_handle):
        with self.sdr.lock:
            conn = self.conns.get(conn_handle)
            if conn is None:
                return None
            return sn.ConnectionInfo(
                state=conn.state, listen_socket=conn.listen_socket, end_reason=conn.end_reason,
                end_debug=conn.end_debug, description='fake', remote_steam_id=conn.remote_id,
                flags=sn.CONNECTION_FLAG_RELAYED, pop_relay=0)

    def detailed_status(self, conn_handle):
        return 'Fake SDR\n  End-to-end connection: connected'

    def run_callbacks(self):
        with self.sdr.lock:
            self.callback_threads.add(threading.current_thread().name)
            now = time.monotonic()
            for conn in list(self.conns.values()):
                if conn.state == sn.STATE_CONNECTING and conn.peer is None and now > conn.deadline:
                    self._set_state(conn, sn.STATE_PROBLEM_DETECTED_LOCALLY, 5003,
                                    'Timed out attempting to connect')
            self.events.extend(self.pending)
            self.pending.clear()

    def poll_status_events(self):
        with self.sdr.lock:
            events = list(self.events)
            self.events.clear()
            return events

    # Test controls
    def drop(self, conn_handle, reason=5003, debug='Connection dropped'):
        """The route died: both ends see ProblemDetectedLocally (Steam's timeout)."""
        with self.sdr.lock:
            conn = self.conns[conn_handle]
            for end in (conn, conn.peer):
                if end is not None and end.state == sn.STATE_CONNECTED:
                    self._set_state(end, sn.STATE_PROBLEM_DETECTED_LOCALLY, reason, debug)

    def vanish(self, conn_handle):
        """The handle stops working with no status event at all (backstop paths)."""
        with self.sdr.lock:
            self.conns.pop(conn_handle, None)

    def sends(self, results=(sn.RESULT_OK,)):
        with self.sdr.lock:
            return [op for op in self.ops if op[0] == 'send' and op[3] in results]

    def closes(self):
        with self.sdr.lock:
            return [op for op in self.ops if op[0] == 'close']


# ---------------------------------------------------------------------------
# Helpers + fixtures
# ---------------------------------------------------------------------------

def wait_until(condition, timeout=5.0, what='condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"{what} not met within {timeout}s")


def recv_exactly(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(1 << 20, size - len(data)))
        if not chunk:
            break
        data += chunk
    return bytes(data)


def recv_until_eof(sock):
    data = bytearray()
    while True:
        chunk = sock.recv(1 << 20)
        if not chunk:
            return bytes(data)
        data += chunk


def payload(size, seed=0):
    """Bytes whose position is visible in them (a reorder or a drop changes them)."""
    block = bytes((i * 7 + seed) % 251 for i in range(251))
    return (block * (size // 251 + 1))[:size]


def wait_for_message(queue, msg_type, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = queue.get_incoming_message()
        if message is None:
            time.sleep(0.01)
        elif message.get('type') == msg_type:
            return message
    raise AssertionError(f"no {msg_type} within {timeout}s")


@pytest.fixture
def sdr():
    return FakeSdr()


@pytest.fixture
def make_bridge(sdr):
    """make_bridge(steam_id, name) -> (SteamBridge, FakeSteam); all stopped afterwards."""
    made = []

    def make(steam_id, name):
        fake = sdr.pc(steam_id, name)
        bridge = SteamBridge(api=fake)
        made.append(bridge)
        return bridge, fake

    yield make
    for bridge in made:
        bridge.stop()


@pytest.fixture
def local_server():
    """A plain TCP listener standing in for the host's NetworkServer."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(8)
    listener.settimeout(5)
    yield listener
    listener.close()


def join_through(join_bridge, local_server, steam_id=HOST_ID, receive_buffer=None):
    """Open a join and both loopback ends: (client socket, server-side socket, join)."""
    join = join_bridge.open_join(steam_id)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if receive_buffer:
        # Small, so Windows' loopback buffering cannot swallow what a slow reader leaves
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer)
    client.settimeout(5)
    client.connect(('127.0.0.1', join.local_port))
    server_side, _ = local_server.accept()
    client.settimeout(10)
    server_side.settimeout(10)
    return client, server_side, join


@pytest.fixture
def linked(make_bridge, local_server):
    """A joiner linked to the host through both bridges, over plain sockets."""
    host_bridge, host_fake = make_bridge(HOST_ID, 'Hosty')
    join_bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
    assert host_bridge.start_hosting(local_server.getsockname()[1])
    client, server_side, join = join_through(join_bridge, local_server)
    yield {'host_bridge': host_bridge, 'host_fake': host_fake, 'join_bridge': join_bridge,
           'join_fake': join_fake, 'client': client, 'server': server_side, 'join': join}
    for sock in (client, server_side):
        try:
            sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# The bridge on its own (plain sockets at both ends)
# ---------------------------------------------------------------------------

class TestBytes:

    def test_bytes_cross_both_ways_in_pieces(self, linked):
        up, down = payload(1_000_000, 1), payload(700_000, 2)
        linked['client'].sendall(up)
        assert recv_exactly(linked['server'], len(up)) == up
        linked['server'].sendall(down)
        assert recv_exactly(linked['client'], len(down)) == down

        sent = linked['join_fake'].sends()
        assert sent and all(len(op[2]) <= PIECE_SIZE for op in sent)
        assert len(sent) >= 4                       # 1 MB needs at least 4 pieces
        assert b''.join(op[2] for op in sent) == up  # frames may straddle pieces

    def test_full_send_buffer_loses_nothing(self, linked):
        fake = linked['join_fake']
        fake.limit_exceeded = 40                    # Steam's send buffer "full" 40 times
        data = payload(600_000, 3)
        linked['client'].sendall(data)
        assert recv_exactly(linked['server'], len(data)) == data   # no loss, dup, reorder

        # Every refused piece was offered again, unchanged, before anything else
        attempts = fake.sends(results=(sn.RESULT_OK, sn.RESULT_LIMIT_EXCEEDED))
        refused = [i for i, op in enumerate(attempts) if op[3] == sn.RESULT_LIMIT_EXCEEDED]
        assert len(refused) == 40
        for i in refused:
            assert attempts[i + 1][2] == attempts[i][2]

    def test_slow_local_reader_pauses_only_that_peer(self, make_bridge, local_server):
        host_bridge, _ = make_bridge(HOST_ID, 'Hosty')
        slow_bridge, slow_fake = make_bridge(JOINER_ID, 'Slow')
        fast_bridge, _ = make_bridge(OTHER_ID, 'Fast')
        assert host_bridge.start_hosting(local_server.getsockname()[1])
        slow_client, slow_server, _ = join_through(slow_bridge, local_server, receive_buffer=4096)
        fast_client, fast_server, _ = join_through(fast_bridge, local_server)
        try:
            big = payload(6_000_000, 4)
            writer = threading.Thread(target=slow_server.sendall, args=(big,), daemon=True)
            writer.start()

            # The slow client reads nothing: the bridge stops pulling at the backlog limit
            pair = slow_bridge._active[0]
            peak = 0
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                peak = max(peak, len(pair.to_local))
                time.sleep(0.002)
            assert LOCAL_BACKLOG_LIMIT <= peak <= LOCAL_BACKLOG_LIMIT + PIECE_SIZE
            with slow_fake.sdr.lock:
                waiting_in_steam = sum(len(m) for c in slow_fake.conns.values() for m in c.inbox)
            assert waiting_in_steam > 0             # Steam holds the rest

            # ...while the other peer's traffic flows
            fast_client.sendall(b'hello host')
            assert recv_exactly(fast_server, 10) == b'hello host'
            fast_server.sendall(b'hello fast')
            assert recv_exactly(fast_client, 10) == b'hello fast'

            # Once the slow client reads, everything arrives intact
            assert recv_exactly(slow_client, len(big)) == big
            writer.join(5)
        finally:
            for sock in (slow_client, slow_server, fast_client, fast_server):
                sock.close()


class TestClosing:

    def test_last_bytes_arrive_before_the_lingering_close(self, linked):
        data = payload(300_000, 5)
        linked['server'].sendall(data)
        linked['server'].close()                    # the game server closes after its last message
        assert recv_until_eof(linked['client']) == data   # all of it, then a clean EOF

        fake = linked['host_fake']
        wait_until(lambda: fake.closes(), what='host closed its Steam connection')
        ops = [op for op in fake.ops if op[0] in ('send', 'close')]
        close_at = next(i for i, op in enumerate(ops) if op[0] == 'close')
        assert ops[close_at][4] is True             # linger: Steam flushes what it holds
        assert ops[close_at][2] == sn.END_APP_GENERIC
        assert all(op[0] == 'send' for op in ops[:close_at])
        assert sum(len(op[2]) for op in ops[:close_at] if op[3] == sn.RESULT_OK) == len(data)

    def test_closing_never_resets_a_reader_with_unsent_data(self, linked):
        """Windows resets a socket closed with unread data, and the reader loses what
        was still waiting for it. The bridge sends SHUT_WR and drains instead."""
        client, server = linked['client'], linked['server']
        stop = threading.Event()

        def keep_writing():
            try:
                while not stop.is_set():
                    client.send(b'x' * 4096)
            except OSError:
                pass
        writer = threading.Thread(target=keep_writing, daemon=True)
        writer.start()
        try:
            time.sleep(0.1)
            server.sendall(b'BYE')
            server.shutdown(socket.SHUT_WR)         # the host side ends gracefully too
            received = bytearray()
            while True:
                chunk = client.recv(65536)          # a reset would raise here
                if not chunk:
                    break
                received += chunk
            assert received == b'BYE'
        finally:
            stop.set()
            writer.join(2)

    def test_lost_steam_connection_closes_the_local_sides(self, linked):
        join = linked['join']
        handle = linked['join_bridge']._active[0].conn
        linked['join_fake'].drop(handle)
        assert recv_until_eof(linked['client']) == b''
        assert recv_until_eof(linked['server']) == b''
        assert join.failure_reason() == "Lost the connection to Hosty (Steam stopped hearing from them)"

    def test_a_client_still_waiting_at_the_listener_gets_a_clean_end(self, make_bridge,
                                                                      local_server):
        """Steam ended before the bridge took the client off its listener: a pass runs
        the status changes before the accept, and closing a listener resets the
        connections still waiting on it - the client got WinError 10054 instead of an end
        (test_lost_steam_connection_closes_the_local_sides in a slow full run,
        2026-10-13). The bridge takes the waiting client first."""
        host_bridge, _ = make_bridge(HOST_ID, 'Hosty')
        join_bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        host_bridge.start_hosting(local_server.getsockname()[1])
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        try:
            with join_bridge._lock:                 # the bridge thread cannot accept meanwhile
                join = join_bridge.open_join(HOST_ID)
                pair = join._pair
                client.connect(('127.0.0.1', join.local_port))
                assert select.select([pair.listener], [], [], 2)[0]   # waiting, not taken
                join_bridge._on_steam_closed(pair, 5003, 'Connection dropped')
            assert recv_until_eof(client) == b''
        finally:
            client.close()

    def test_a_vanished_connection_is_noticed_without_a_callback(self, linked):
        handle = linked['join_bridge']._active[0].conn
        linked['join_fake'].vanish(handle)
        linked['client'].sendall(b'anyone there?')  # the send finds the handle gone
        assert recv_until_eof(linked['client']) == b''

    def test_bridge_stop_closes_everything(self, linked):
        host_bridge, host_fake = linked['host_bridge'], linked['host_fake']
        host_bridge.stop()
        closes = host_fake.closes()
        assert any(op[2] == END_GAME_CLOSED and op[4] is True for op in closes)
        assert not host_fake.listen_sockets
        assert recv_until_eof(linked['client']) == b''
        assert linked['join'].failure_reason() == "Hosty closed the game"
        wait_until(lambda: host_bridge._thread is None, what='bridge thread ended')


class TestJoinerSide:

    def test_listener_is_loopback_only_and_takes_one_client(self, make_bridge, local_server):
        host_bridge, _ = make_bridge(HOST_ID, 'Hosty')
        join_bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        host_bridge.start_hosting(local_server.getsockname()[1])
        join = join_bridge.open_join(HOST_ID)
        pair = join_bridge._active[0]
        assert pair.listener.getsockname()[0] == '127.0.0.1'
        first = socket.create_connection(('127.0.0.1', join.local_port), timeout=5)
        try:
            wait_until(lambda: pair.listener is None, what='listener closed after the first client')
            with pytest.raises(OSError):
                second = socket.create_connection(('127.0.0.1', join.local_port), timeout=5)
                second.close()
        finally:
            first.close()

    def test_nobody_answering_ends_with_steams_timeout(self, make_bridge):
        join_bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        join = join_bridge.open_join(NOBODY_ID)
        client = socket.create_connection(('127.0.0.1', join.local_port), timeout=5)
        try:
            client.sendall(b'CONNECT_REQUEST waits in the socket')
            client.settimeout(5)
            assert recv_until_eof(client) == b''    # closed gracefully, not reset
            assert not join.reached_host
            assert join.failure_reason().startswith("Could not reach the host through Steam - "
                                                    "they may not be hosting right now")
        finally:
            client.close()

    def test_timeout_wording_when_the_friend_is_hosting(self, make_bridge, sdr):
        join_bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        sdr.names[NOBODY_ID] = 'Ghost'
        sdr.presence[NOBODY_ID] = {'connect': f'+connect steam-{NOBODY_ID}'}
        join = join_bridge.open_join(NOBODY_ID)
        wait_until(lambda: join.ended, what='timeout')
        assert join.failure_reason() == ("Could not reach Ghost through Steam (timed out) - "
                                         "check both PCs' internet connections")

    def test_the_join_log_says_whether_the_relay_was_ready(self, make_bridge, caplog):
        # A join started right after launch may spend part of its 15 s on the relay
        caplog.set_level(logging.INFO, logger='network.steam_bridge')
        join_bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        join_bridge.open_join(NOBODY_ID).close()
        join_fake.relay_status = lambda: (sn.AVAILABILITY_CURRENT, '')
        join_bridge.open_join(NOBODY_ID).close()
        join_fake.relay_status = lambda: (3, 'Attempting')
        join_bridge.open_join(NOBODY_ID).close()
        assert "relay state unknown)" in caplog.text            # fake without the call
        assert "relay ready)" in caplog.text
        assert "relay Attempting)" in caplog.text

    def test_giving_up_stops_the_attempt_at_once(self, make_bridge):
        join_bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        join_fake.sdr.connect_timeout = 30          # Steam would keep trying
        join = join_bridge.open_join(NOBODY_ID)
        join.close()
        assert any(op[1] for op in join_fake.closes())
        assert not join_bridge._active
        wait_until(lambda: join_bridge._thread is None, what='bridge thread ended')

    def test_steam_unavailable_reasons(self, make_bridge):
        bridge, fake = make_bridge(JOINER_ID, 'Joiny')
        fake.online = False
        with pytest.raises(SteamJoinError, match="Steam is offline"):
            bridge.open_join(HOST_ID)
        fake.online = True
        fake.relay_enabled = False
        fake.relay_switched_off = True
        with pytest.raises(SteamJoinError, match="switched off"):
            bridge.open_join(HOST_ID)
        fake.relay_switched_off = False
        with pytest.raises(SteamJoinError, match="could not be started"):
            bridge.open_join(HOST_ID)
        fake.available = False
        with pytest.raises(SteamJoinError, match="Steam is not running"):
            bridge.open_join(HOST_ID)


class TestHostSide:

    def test_a_flood_from_one_steamid_is_turned_away(self, make_bridge, local_server):
        host_bridge, _ = make_bridge(HOST_ID, 'Hosty')
        join_bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        host_bridge.start_hosting(local_server.getsockname()[1])
        joins = [join_bridge.open_join(HOST_ID) for _ in range(PEER_RATE_MAX + 1)]
        wait_until(lambda: sum(j.reached_host for j in joins) == PEER_RATE_MAX and joins[-1].ended,
                   what='five accepted, the sixth refused')
        assert joins[-1].failure_reason().startswith("Hosty turned the connection away (too many attempts)")
        assert joins[-1]._pair.end_reason == END_REFUSED_RATE

    def test_not_hosting_is_said_at_once(self, make_bridge, local_server):
        host_bridge, _ = make_bridge(HOST_ID, 'Hosty')
        join_bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        host_bridge.start_hosting(local_server.getsockname()[1])
        host_bridge.stop_hosting()                  # the lobby closed; the game still runs
        started = time.monotonic()
        join = join_bridge.open_join(HOST_ID)
        wait_until(lambda: join.ended, what='refusal')
        assert time.monotonic() - started < 1.0     # not Steam's 15 s timeout
        assert join._pair.end_reason == END_NOT_HOSTING
        assert join.failure_reason() == "Hosty is not hosting a game right now"

    def test_a_failing_status_event_does_not_cost_the_others(self, make_bridge, local_server):
        host_bridge, host_fake = make_bridge(HOST_ID, 'Hosty')
        first_bridge, _ = make_bridge(JOINER_ID, 'First')
        second_bridge, _ = make_bridge(OTHER_ID, 'Second')
        host_bridge.start_hosting(local_server.getsockname()[1])
        real_accept = host_fake.accept
        calls = []

        def accept_failing_once(conn):
            calls.append(conn)
            if len(calls) == 1:
                raise RuntimeError("simulated failure")
            return real_accept(conn)
        host_fake.accept = accept_failing_once
        with host_bridge._lock:                     # both Connecting events land in one batch
            first = first_bridge.open_join(HOST_ID)
            second = second_bridge.open_join(HOST_ID)
            time.sleep(0.05)
        wait_until(lambda: second.reached_host, what='the second join got through')
        assert len(calls) == 2 and not first.reached_host

    def test_a_stalled_main_pump_is_logged(self, make_bridge, local_server, caplog, monkeypatch):
        # Two-PC test 2026-10-13: the lobby did not run Steam's main callbacks, so friends'
        # Steam joins waited unseen on the host. The log must point at that next time.
        caplog.set_level(logging.INFO, logger='network.steam_bridge')
        monkeypatch.setattr(steam_bridge_module, 'MAIN_PUMP_WARN_SECONDS', 0.2)
        host_bridge, host_fake = make_bridge(HOST_ID, 'Hosty')
        host_fake.main_pump_time = time.monotonic()
        host_bridge.start_hosting(local_server.getsockname()[1])
        wait_until(lambda: "Steam callbacks have not run" in caplog.text, what='stall warning')
        time.sleep(0.1)
        assert caplog.text.count("Steam callbacks have not run") == 1      # once per stall
        assert "while hosting through Steam" in caplog.text
        host_fake.main_pump_time = time.monotonic()                        # pumping again
        wait_until(lambda: "Steam callbacks running again after" in caplog.text, what='recovery')

    def test_no_pump_warning_when_nothing_needs_the_pump(self, make_bridge, local_server,
                                                         caplog, monkeypatch):
        caplog.set_level(logging.INFO, logger='network.steam_bridge')
        monkeypatch.setattr(steam_bridge_module, 'MAIN_PUMP_WARN_SECONDS', 0.2)
        host_bridge, host_fake = make_bridge(HOST_ID, 'Hosty')
        host_bridge.start_hosting(local_server.getsockname()[1])
        time.sleep(0.4)                     # never pumped yet (FakeSteam has no pump time)
        host_bridge.stop_hosting()
        host_fake.main_pump_time = time.monotonic() - 10
        time.sleep(0.4)                     # stale pump, but not hosting and nothing carried
        assert "Steam callbacks" not in caplog.text

    def test_status_callbacks_run_on_the_bridge_thread(self, linked):
        assert linked['host_fake'].callback_threads == {'steam-bridge'}
        assert linked['join_fake'].callback_threads == {'steam-bridge'}

    def test_log_lines_name_the_steam_peer(self, make_bridge, local_server, caplog):
        caplog.set_level(logging.INFO, logger='network.steam_bridge')
        host_bridge, _ = make_bridge(HOST_ID, 'Hosty')
        join_bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        host_bridge.start_hosting(local_server.getsockname()[1])
        client, server_side, join = join_through(join_bridge, local_server)
        try:
            label = host_bridge.peer_label(server_side.getpeername())
            assert label == f"Steam {JOINER_ID} (Joiny) (local port {server_side.getpeername()[1]})"
            join_fake.drop(join_bridge._active[0].conn)
            recv_until_eof(client)
            text = caplog.text
            assert f"Steam peer {JOINER_ID} (Joiny) -> local port {server_side.getpeername()[1]}" in text
            assert f"Steam connection {JOINER_ID} (Joiny) connected (relayed)" in text
            assert f"Steam connection {HOST_ID} (Hosty) closed: 5003 'Connection dropped'" in text
        finally:
            client.close()
            server_side.close()


class TestReasons:

    @pytest.mark.parametrize('code, connected, hosting, expected', [
        (1000, True, None, None),
        (3001, False, None, "Steam is in offline mode - go online in Steam to join through Steam"),
        (3005, False, None, "Steam did not allow the connection - check that you are signed in to Steam"),
        (3002, False, None, "Your PC could not reach Steam's network - check your internet connection"),
        (4001, False, None, "Ann's connection to Steam has a problem - ask them to check their internet connection"),
        (5003, True, None, "Lost the connection to Ann (Steam stopped hearing from them)"),
        (5003, False, True, "Could not reach Ann through Steam (timed out) - check both PCs' internet connections"),
        (5003, False, False, "Could not reach Ann through Steam - they may not be hosting right now, or their game is closed"),
        (5008, False, None, "Steam could not find a route to Ann - try again, or use Direct IP"),
        (5010, False, None, "Steam connection problem with Ann (code 5010)"),
        (0, True, None, "Lost the connection to Ann"),
    ])
    def test_end_reasons(self, code, connected, hosting, expected):
        assert describe_end(code, connected, 'Ann', hosting) == expected

    def test_an_unknown_host_is_called_the_host(self):
        assert describe_end(END_NOT_HOSTING, False) == "The host is not hosting a game right now"

    @pytest.mark.parametrize('code, refused', [
        (END_NOT_HOSTING, True),        # the host's game: no lobby open
        (END_GAME_CLOSED, True),        # the host's game: exiting
        (5003, False),                  # nobody answered: the IP addresses may still work
        (END_REFUSED_RATE, False),
        (1000, False),
    ])
    def test_which_endings_rule_out_the_hosts_addresses(self, code, refused):
        """connect_any() skips an invite's IP addresses after these (host_game_refused)."""
        pair = steam_bridge_module._Pair(conn=1, steam_id=HOST_ID, side='join')
        join = steam_bridge_module.SteamJoin(None, pair)
        assert not join.host_game_refused       # still running
        pair.steam_closed, pair.end_reason = True, code
        assert join.host_game_refused is refused


# ---------------------------------------------------------------------------
# End to end: real NetworkServer / NetworkClient over the fake relay
# ---------------------------------------------------------------------------

@pytest.fixture
def host(make_bridge):
    bridge, fake = make_bridge(HOST_ID, 'Hosty')
    server = NetworkServer(port=0)
    server.steam_bridge = bridge
    assert server.start()
    assert server.setup_steam()
    assert server.steam_host_id() == HOST_ID
    yield server
    server.stop()


def steam_client(bridge):
    client = NetworkClient()
    client.steam_bridge = bridge
    return client


def tcp_port(server):
    return server.socket.getsockname()[1]


class TestEndToEnd:

    def test_join_and_talk_both_ways(self, host, make_bridge, caplog):
        caplog.set_level(logging.INFO)
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_steam(HOST_ID, player_name='Joiny')
            assert client.player_index == 1
            joined = wait_for_message(host.message_queue, MessageType.LOBBY_JOIN)
            assert joined['data']['player_name'] == 'Joiny'
            assert f"Client connected from Steam {JOINER_ID} (Joiny) (local port" in caplog.text

            client.send_message(client.protocol.encode_message(MessageType.CHAT_MESSAGE, {
                'player_index': 1, 'message': 'hi host', 'channel': 'all'}))
            assert wait_for_message(host.message_queue, MessageType.CHAT_MESSAGE)['data']['message'] == 'hi host'
            host.send_message(host.protocol.encode_message(MessageType.CHAT_MESSAGE, {
                'player_index': 0, 'message': 'hi joiner', 'channel': 'all'}))
            assert wait_for_message(client.message_queue, MessageType.CHAT_MESSAGE)['data']['message'] == 'hi joiner'
        finally:
            client.disconnect()

    def test_a_megabyte_each_way_with_full_send_buffers(self, host, make_bridge):
        bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_steam(HOST_ID, player_name='Joiny')
            host_fake = host.steam_bridge._api
            host_fake.limit_exceeded = join_fake.limit_exceeded = 30
            blob = {'blob': 'x' * 900_000}          # near MAX_MESSAGE_SIZE (1,000,000)
            host.send_message(host.protocol.encode_message(MessageType.FULL_STATE_SYNC, blob))
            assert wait_for_message(client.message_queue, MessageType.FULL_STATE_SYNC)['data'] == blob
            client.send_message(client.protocol.encode_message(MessageType.TURN_END, blob))
            received = wait_for_message(host.message_queue, MessageType.TURN_END)
            # (the server stamps the sender's player_index onto a client's message)
            assert received['data']['blob'] == blob['blob'] and received['from_player_index'] == 1
            assert host_fake.limit_exceeded == join_fake.limit_exceeded == 0
            assert client.is_connected() and 1 in host.clients
        finally:
            client.disconnect()

    @pytest.mark.parametrize('setup, reason', [
        (lambda server: setattr(server, 'reserved_slots', {1, 2, 3}), "No slots available"),
        (lambda server: server.set_game_started(True), "The game has already started"),
    ])
    def test_the_hosts_refusal_reaches_the_joiner(self, host, make_bridge, setup, reason):
        setup(host)
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        tried = []
        real_connect = client.connect

        def counting_connect(*args, **kwargs):
            tried.append(args[0])
            return real_connect(*args, **kwargs)
        client.connect = counting_connect
        assert not client.connect_any([SteamTarget(HOST_ID), ('127.0.0.1', 1)], player_name='Late')
        assert client.disconnect_reason == reason
        # Only connect_steam()'s bridge port: the address after it was not tried
        assert tried == ['127.0.0.1']

    def test_version_mismatch_reason_reaches_the_joiner(self, host, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        client.protocol.create_connect_request = lambda name: client.protocol.encode_message(
            MessageType.CONNECT_REQUEST, {'version': '0.0.1', 'player_name': name})
        assert not client.connect_steam(HOST_ID, player_name='Old')
        assert client.disconnect_reason.startswith("Version mismatch")

    def test_mixed_lobby_then_full(self, host, make_bridge):
        clients = []
        try:
            for steam_id, name in ((JOINER_ID, 'Joiny'), (OTHER_ID, 'Other')):
                bridge, _ = make_bridge(steam_id, name)
                clients.append(steam_client(bridge))
                assert clients[-1].connect_steam(HOST_ID, player_name=name)
            clients.append(NetworkClient())
            assert clients[-1].connect('127.0.0.1', tcp_port(host), player_name='Direct')
            assert sorted(c.player_index for c in clients) == [1, 2, 3]

            host.send_message(host.protocol.encode_message(MessageType.CHAT_MESSAGE, {
                'player_index': 0, 'message': 'all here?', 'channel': 'all'}))
            for client in clients:
                assert wait_for_message(client.message_queue, MessageType.CHAT_MESSAGE)['data']['message'] == 'all here?'

            late_bridge, _ = make_bridge(NOBODY_ID - 1, 'Late')
            late = steam_client(late_bridge)
            assert not late.connect_steam(HOST_ID, player_name='Late')
            assert late.disconnect_reason == "Lobby is full"
        finally:
            for client in clients:
                client.disconnect()

    def test_kick_reason_reaches_the_joiner(self, host, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_steam(HOST_ID, player_name='Joiny')
            host.kick_player(1, "Kicked by host")
            kick = wait_for_message(client.message_queue, MessageType.LOBBY_KICK)
            assert kick['data']['reason'] == "Kicked by host"
        finally:
            client.disconnect()

    def test_host_leaving_reaches_the_joiner(self, host, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_steam(HOST_ID, player_name='Joiny')
            host.stop()
            wait_until(lambda: client.disconnected, what='client saw the host leave')
            assert client.disconnect_reason == "Host disconnected"
        finally:
            client.disconnect()

    def test_joiner_leaving_is_announced(self, host, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        assert client.connect_steam(HOST_ID, player_name='Joiny')
        wait_for_message(host.message_queue, MessageType.LOBBY_JOIN)
        client.disconnect()
        left = wait_for_message(host.message_queue, MessageType.LOBBY_LEAVE)
        assert left['data']['player_index'] == 1
        wait_until(lambda: not host.steam_bridge._active, what='host bridge pair finished')

    def test_lost_steam_connection_is_named_in_game(self, host, make_bridge):
        bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_steam(HOST_ID, player_name='Joiny')
            join_fake.drop(bridge._active[0].conn)
            wait_until(lambda: client.disconnected, what='client noticed')
            assert client.disconnect_reason == "Lost the connection to Hosty (Steam stopped hearing from them)"
            wait_for_message(host.message_queue, MessageType.LOBBY_LEAVE)
        finally:
            client.disconnect()

    def test_host_game_exit_is_named(self, host, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_steam(HOST_ID, player_name='Joiny')
            host.steam_bridge.stop()                # steam_integration.shutdown() at game exit
            wait_until(lambda: client.disconnected, what='client noticed')
            assert client.disconnect_reason == "Hosty closed the game"
        finally:
            client.disconnect()

    def test_steam_failure_then_the_address_works(self, host, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        try:
            assert client.connect_any([SteamTarget(NOBODY_ID), ('127.0.0.1', tcp_port(host))],
                                      player_name='Joiny')
            assert client.server_address == ('127.0.0.1', tcp_port(host))
        finally:
            client.disconnect()

    def test_steam_and_address_failing_lead_with_steams_reason(self, make_bridge):
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        client = steam_client(bridge)
        assert not client.connect_any([SteamTarget(NOBODY_ID), ('127.0.0.1', dead_port)],
                                      player_name='Joiny')
        steam_part, _, rest = client.disconnect_reason.partition(" (a direct connection to ")
        assert steam_part == ("Could not reach the host through Steam - they may not be "
                              "hosting right now, or their game is closed")
        assert rest == "127.0.0.1 failed too)"
        assert '127.0.0.1' not in steam_part        # never the bridge's own address

    def test_steam_offline_falls_back_to_the_address(self, host, make_bridge):
        bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        join_fake.online = False
        client = steam_client(bridge)
        try:
            assert not client.connect_steam(HOST_ID, player_name='Joiny')
            assert client.disconnect_reason.startswith("Steam is offline")
            assert client.connect_any([SteamTarget(HOST_ID), ('127.0.0.1', tcp_port(host))],
                                      player_name='Joiny')
        finally:
            client.disconnect()

    def test_six_steam_joins_within_ten_seconds(self, host, make_bridge):
        """The server's per-IP limit (5 in 10 s) would refuse the sixth: every Steam peer
        arrives from 127.0.0.1. Steam peers are limited per SteamID by the bridge."""
        bridges = [make_bridge(JOINER_ID + i, f'P{i}')[0] for i in range(3)]
        started = time.monotonic()
        for round_ in range(2):
            for i, bridge in enumerate(bridges):
                client = steam_client(bridge)
                assert client.connect_steam(HOST_ID, player_name=f'P{i}'), client.disconnect_reason
                client.disconnect()
                wait_until(lambda: not host.clients, what='slot freed')
        assert time.monotonic() - started < 10.0

    def test_cancel_stops_a_steam_join_at_once(self, make_bridge, sdr):
        """The "Connecting..." screen's Cancel: no waiting out Steam's 15 s, and the
        Steam attempt is dropped (not left running)."""
        sdr.connect_timeout = 30                    # Steam would keep looking
        bridge, join_fake = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        outcome = {}
        worker = threading.Thread(target=lambda: outcome.update(
            ok=client.connect_any([SteamTarget(NOBODY_ID)], player_name='Joiny')))
        worker.start()
        wait_until(lambda: bridge._active, what='join started')
        started = time.monotonic()
        client.cancel_connect()
        worker.join(5)
        assert time.monotonic() - started < 1.0
        assert outcome['ok'] is False and client.disconnect_reason == "Cancelled"
        wait_until(lambda: not bridge._active, what='Steam attempt dropped')
        assert any(op[3] == 'Join cancelled' for op in join_fake.closes())

    def test_not_hosting_after_the_lobby_closed(self, host, make_bridge):
        host.stop()
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        started = time.monotonic()
        assert not client.connect_steam(HOST_ID, player_name='Joiny')
        # Not Steam's 15 s timeout. Up to ~2 s more when the fake relay's instant refusal
        # beats the client to the bridge's listener: Windows takes ~2 s to refuse a
        # connect to a closed local port (measured 2026-10-13; real Steam's refusal takes
        # a relay round trip, long after the client connected)
        assert time.monotonic() - started < 5.0
        assert client.disconnect_reason == "Hosty is not hosting a game right now"

    def test_not_hosting_skips_the_invites_addresses(self, host, make_bridge):
        """Owner's two-PC test 5 (2026-10-13): after the host's "not hosting" the invite's
        IP addresses were still tried (5 s each) - they lead to the same stopped server."""
        address = ('127.0.0.1', tcp_port(host))
        host.stop()
        bridge, _ = make_bridge(JOINER_ID, 'Joiny')
        client = steam_client(bridge)
        tried = []
        real_connect = client.connect

        def connect(host_, port=7777, player_name="Player", **kwargs):
            if '_steam_join' not in kwargs:         # connect_steam()'s own loopback leg
                tried.append((host_, port))
            return real_connect(host_, port=port, player_name=player_name, **kwargs)
        client.connect = connect
        assert not client.connect_any([SteamTarget(HOST_ID), address], player_name='Joiny')
        assert tried == []
        assert client.disconnect_reason == "Hosty is not hosting a game right now"
