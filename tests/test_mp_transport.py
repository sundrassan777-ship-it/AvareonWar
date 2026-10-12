# -*- coding: utf-8 -*-
"""
Multiplayer transport tests (pre-launch multiplayer audit).

The server and client logic is real (network/server.py, network/client.py); only the
sockets are replaced by tests/mp_harness.py's in-memory frames.

Tests marked xfail(strict=True) reproduce a confirmed audit finding (ID in the
reason). The phase that fixes it removes the marker; strict=True turns an unexpected
pass into a failure, so a fixed bug can never keep its marker by accident.
"""

import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from network.client import (NetworkClient, format_connect_targets,  # noqa: E402
                            parse_connect_targets, unreachable_reason)
from network.message_queue import NetworkMessageQueue  # noqa: E402
from network.protocol import MessageBuffer, NetworkProtocol  # noqa: E402
from network.server import NetworkServer  # noqa: E402
from network_config import MessageType  # noqa: E402


def drain(queue):
    """Every message currently waiting in a NetworkMessageQueue's incoming side."""
    messages = []
    while True:
        message = queue.get_incoming_message()
        if message is None:
            return messages
        messages.append(message)


def chat(client, text, player_index=None):
    """Queue a chat message on the client's game-loop side (main thread)."""
    index = client.player_index if player_index is None else player_index
    client.send_message(client.protocol.encode_message(MessageType.CHAT_MESSAGE, {
        'player_index': index, 'message': text, 'channel': 'all'}))


class TestHarness:

    def test_client_message_reaches_host_and_other_clients(self):
        """Sanity: the harness delivers like the real server relay."""
        net = h.Network()
        first, second = net.add_client(1), net.add_client(2)
        chat(first, "hello")
        net.flush()
        assert [m['type'] for m in drain(net.server.message_queue)] == [MessageType.CHAT_MESSAGE]
        assert [m['type'] for m in drain(second.message_queue)] == [MessageType.CHAT_MESSAGE]


class TestSequenceNumbers:

    def test_pong_does_not_swallow_a_queued_game_message(self):
        net = h.Network()
        client = net.add_client(1)
        chat(client, "queued before the PING")              # seq N, still in the queue
        net.server.clients[1].socket.sendall(net.server.protocol.create_ping())  # PONG N+1 goes out now
        net.flush()                                          # the network thread sends seq N
        types = [m['type'] for m in drain(net.server.message_queue)]
        assert MessageType.CHAT_MESSAGE in types

    def test_new_client_can_take_a_vacated_slot(self):
        net = h.Network()
        first = net.add_client(1)
        for i in range(3):
            chat(first, f"message {i}")
        net.flush()
        net.server._disconnect_client(1, "left the lobby")

        newcomer = net.add_client(1)             # fresh NetworkClient: seq restarts at 0
        newcomer.player_index = None             # waiting for CONNECT_ACCEPT
        newcomer.socket.sendall(newcomer.protocol.create_connect_request("Newcomer"))
        assert newcomer.player_index == 1


    def test_disconnect_is_not_dropped_as_a_replay(self):
        """DISCONNECT goes out straight from the closing thread, so like PONG it may
        carry an older number than what the queue already sent."""
        net = h.Network()
        client = net.add_client(1)
        farewell = client.protocol.create_disconnect("bye")     # seq 0
        chat(client, "still here")                              # seq 1
        net.flush()
        client.socket.sendall(farewell)
        assert 1 not in net.server.clients

    def test_sequence_numbers_are_unique_across_threads(self):
        """Game loop and network thread encode through one protocol."""
        protocol = NetworkProtocol()
        seqs = []

        def encode_many():
            mine = [protocol.decode_message(protocol.encode_message(MessageType.PING, {}))['seq']
                    for _ in range(2000)]
            seqs.extend(mine)
        threads = [threading.Thread(target=encode_many) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(set(seqs)) == 8000


class TestDisconnectNotices:
    """Every way a client can vanish is announced - to the host AND the other clients."""

    def test_in_game_disconnect_reaches_host_and_other_clients(self):
        net = h.Network()
        net.add_client(1)
        other = net.add_client(2)
        net.server.set_game_started(True)
        net.server._disconnect_client(1, "crashed")
        host_view = drain(net.server.message_queue)
        assert [(m['type'], m['data']['player_index']) for m in host_view] == \
            [(MessageType.PLAYER_DISCONNECT, 1)]
        assert [m['type'] for m in drain(other.message_queue)] == [MessageType.PLAYER_DISCONNECT]
        # Rejoining is switched off: nothing kept, so no elimination timer either
        assert net.server.disconnected_players == {}

    def test_lobby_leave_reaches_host_and_other_clients(self):
        net = h.Network()
        net.add_client(1)
        other = net.add_client(2)
        net.server._disconnect_client(1, "left")
        assert [m['type'] for m in drain(net.server.message_queue)] == [MessageType.LOBBY_LEAVE]
        assert [m['type'] for m in drain(other.message_queue)] == [MessageType.LOBBY_LEAVE]

    def test_client_dropped_by_a_send_error_is_announced(self):
        net = h.Network()
        net.add_client(1)
        other = net.add_client(2)
        net.server.set_game_started(True)
        net.server.clients[1].socket.closed = True              # its connection died
        net.server.send_message(net.server.protocol.encode_message(
            MessageType.CHAT_MESSAGE, {'player_index': 0, 'message': 'hello', 'channel': 'all'}))
        net.flush()
        assert 1 not in net.server.clients
        assert MessageType.PLAYER_DISCONNECT in [m['type'] for m in drain(net.server.message_queue)]
        assert MessageType.PLAYER_DISCONNECT in [m['type'] for m in drain(other.message_queue)]

    def test_a_disconnect_is_announced_once(self):
        net = h.Network()
        net.add_client(1)
        net.server.set_game_started(True)
        net.server._disconnect_client(1, "crashed")
        net.server._disconnect_client(1, "crashed")
        assert len(drain(net.server.message_queue)) == 1

    def test_rejoining_a_running_game_is_refused(self):
        net = h.Network()
        client = net.add_client(1)
        net.server.set_game_started(True)
        client.socket.sendall(client.protocol.create_reconnect_request("P2", "secret"))
        assert MessageType.RECONNECT_REJECT in [m['type'] for m in drain(client.message_queue)]


class TestHostOnlyMessages:

    @pytest.mark.parametrize('msg_type', [MessageType.SIM_ROUND_COMPLETE, MessageType.SIM_ALL_READY,
                                          MessageType.SIM_READY_STATE, MessageType.SIM_TIMER_UPDATE])
    def test_a_client_cannot_send_host_messages(self, msg_type):
        """A fake round end from a client would make the host run the client-side path."""
        net = h.Network()
        client = net.add_client(1)
        other = net.add_client(2)
        client.send_message(client.protocol.encode_message(msg_type, {'round_number': 9}))
        net.flush()
        assert drain(net.server.message_queue) == []
        assert drain(other.message_queue) == []


class TestMessageQueue:

    def test_requeued_messages_go_back_in_front_in_order(self):
        queue = NetworkMessageQueue()
        queue.receive_message({'type': 'C'})                    # arrived later
        queue.requeue_front([{'type': 'A'}, {'type': 'B'}])
        assert [m['type'] for m in drain(queue)] == ['A', 'B', 'C']


def _wait_for(queue, msg_type, timeout=10.0):
    """First message of `msg_type` arriving on `queue` (others are skipped)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = queue.get_incoming_message()
        if message is None:
            time.sleep(0.01)
        elif message.get('type') == msg_type:
            return message
    raise AssertionError(f"no {msg_type} within {timeout}s")


class TestRealSockets:
    """Real localhost TCP between a real NetworkServer and NetworkClient threads."""

    @pytest.fixture
    def server(self):
        server = NetworkServer(port=0)
        assert server.start()
        yield server
        server.stop()

    @staticmethod
    def _port(server):
        return server.socket.getsockname()[1]

    def test_large_messages_cross_intact_both_ways(self, server):
        """L4: a frame larger than the socket buffers (state snapshots) must not cut the
        connection - non-blocking sendall() failed half-way through such frames."""
        client = NetworkClient()
        try:
            assert client.connect('127.0.0.1', self._port(server), player_name="Big")
            payload = {'blob': 'x' * 600_000}
            server.send_message(server.protocol.encode_message(MessageType.FULL_STATE_SYNC, payload))
            received = _wait_for(client.message_queue, MessageType.FULL_STATE_SYNC)
            assert received['data']['blob'] == payload['blob']

            # A client's large message: TURN_END, which carries its state snapshot (a
            # client may not send FULL_STATE_SYNC - the server drops host-only types)
            client.send_message(client.protocol.encode_message(MessageType.TURN_END, payload))
            received = _wait_for(server.message_queue, MessageType.TURN_END)
            assert received['data']['blob'] == payload['blob']
            assert received['from_player_index'] == 1
            assert client.is_connected() and 1 in server.clients
        finally:
            client.disconnect()

    def test_large_frames_reach_a_slow_reader(self, server):
        """L4 repro: a peer that reads slowly (a real internet link) fills the socket
        buffers. The old non-blocking sendall() then failed half-way through a frame and
        the server dropped the player; it must wait for the reader instead. (Windows
        takes one big send whole, so it takes several frames in a row - e.g. snapshots
        of consecutive turns - to fill it.)"""
        protocol = NetworkProtocol()
        buffer = MessageBuffer()
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        raw.settimeout(10)
        try:
            raw.connect(('127.0.0.1', self._port(server)))
            raw.sendall(protocol.create_connect_request("Slow"))

            def next_message():
                while True:
                    frame = buffer.extract_message()
                    if frame:
                        message = protocol.decode_message(frame)
                        if message['type'] != MessageType.PING:
                            return message
                        continue
                    chunk = raw.recv(4096)
                    if not chunk:
                        return None
                    buffer.add_data(chunk)
                    time.sleep(0.002)                           # slow reader

            assert next_message()['type'] == MessageType.CONNECT_ACCEPT
            for turn in range(4):
                server.send_message(server.protocol.encode_message(
                    MessageType.FULL_STATE_SYNC, {'turn': turn, 'blob': 'x' * 400_000}))
            for turn in range(4):
                message = next_message()
                assert message is not None and message['type'] == MessageType.FULL_STATE_SYNC
                assert message['data']['turn'] == turn
                assert len(message['data']['blob']) == 400_000
            assert 1 in server.clients
        finally:
            raw.close()

    def test_refused_join_reports_the_reason_at_once(self, server):
        """M8: the host's reason reaches the joining player (and connect() does not sit
        out its 5 s timeout first)."""
        server.reserved_slots = {1, 2, 3}                       # every seat taken by AIs
        client = NetworkClient()
        started = time.monotonic()
        assert not client.connect('127.0.0.1', self._port(server), player_name="Late")
        assert time.monotonic() - started < 3.0
        assert client.disconnect_reason == "No slots available"

    def test_nobody_can_join_a_running_game(self, server):
        server.set_game_started(True)
        client = NetworkClient()
        assert not client.connect('127.0.0.1', self._port(server), player_name="Stranger")
        assert client.disconnect_reason == "The game has already started"
        assert server.clients == {}

    def test_connect_any_skips_a_dead_address(self, server):
        """A Steam invite lists several host addresses; one that nobody answers on must
        not stop the join - the next one is tried."""
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        dead_port = probe.getsockname()[1]
        probe.close()                                           # nothing listens there now
        client = NetworkClient()
        try:
            assert client.connect_any([('127.0.0.1', dead_port),
                                       ('127.0.0.1', self._port(server))], player_name="Two")
            assert client.server_address == ('127.0.0.1', self._port(server))
            assert client.player_index == 1
        finally:
            client.disconnect()

    def test_connect_any_stops_when_the_host_refuses(self, server):
        """A refusal means we reached the host: its reason is shown, and the other
        addresses (the same host) are not tried."""
        server.reserved_slots = {1, 2, 3}
        client = NetworkClient()
        tried = []
        real_connect = client.connect

        def counting_connect(host, port=7777, player_name="Player"):
            tried.append((host, port))
            return real_connect(host, port=port, player_name=player_name)
        client.connect = counting_connect
        assert not client.connect_any([('127.0.0.1', self._port(server)),
                                       ('127.0.0.1', 1)], player_name="Late")
        assert tried == [('127.0.0.1', self._port(server))]
        assert client.disconnect_reason == "No slots available"


class TestJoinAddresses:
    """Steam invite address lists and the "could not reach the host" reasons."""

    def test_connect_string_round_trip(self):
        text = format_connect_targets(['212.20.115.148', '192.168.18.5', None], 7777)
        assert text == '212.20.115.148:7777,192.168.18.5:7777'
        assert parse_connect_targets(text) == [('212.20.115.148', 7777), ('192.168.18.5', 7777)]

    def test_old_single_address_invites_still_parse(self):
        assert parse_connect_targets('192.168.0.103:7777') == [('192.168.0.103', 7777)]
        assert parse_connect_targets('10.0.0.2') == [('10.0.0.2', 7777)]
        assert parse_connect_targets('10.0.0.2:abc') == [('10.0.0.2', 7777)]

    def test_blank_and_duplicate_entries_are_dropped(self):
        assert parse_connect_targets(' 1.2.3.4:7777 ,, 1.2.3.4:7777,') == [('1.2.3.4', 7777)]
        assert parse_connect_targets('') == []
        assert parse_connect_targets(None) == []

    def test_timeout_reason_points_at_the_home_network_for_lan_addresses(self):
        reason = unreachable_reason('192.168.18.5')
        assert 'home network' in reason and 'VPN' in reason

    def test_timeout_reason_points_at_port_forwarding_for_public_addresses(self):
        reason = unreachable_reason('212.20.115.148')
        assert 'forward TCP port 7777' in reason

    def test_every_address_failing_covers_both_cases(self):
        client = NetworkClient()

        def unreachable(host, port=7777, player_name="Player"):
            client._host_answered = False
            client.disconnect_reason = unreachable_reason(host)
            return False
        client.connect = unreachable
        assert not client.connect_any([('192.168.18.5', 7777), ('212.20.115.148', 7777)])
        reason = client.disconnect_reason
        assert '192.168.18.5 or 212.20.115.148' in reason
        assert 'same network' in reason.lower() and 'forward TCP port 7777' in reason

    def test_one_failing_address_keeps_its_own_reason(self):
        client = NetworkClient()

        def unreachable(host, port=7777, player_name="Player"):
            client._host_answered = False
            client.disconnect_reason = unreachable_reason(host)
            return False
        client.connect = unreachable
        assert not client.connect_any([('192.168.18.5', 7777)])
        assert client.disconnect_reason == unreachable_reason('192.168.18.5')

    def test_server_lists_the_public_address_when_known(self):
        server = NetworkServer(port=0)
        server.get_local_ip = lambda: '192.168.18.5'
        assert server.get_join_addresses() == ['192.168.18.5']   # no UPnP set up
        from network.upnp import UPnPManager
        server.upnp_manager = UPnPManager()
        server.upnp_manager.status = 'failed'
        server.upnp_manager.public_ip = '212.20.115.148'
        assert server.get_join_addresses() == ['192.168.18.5', '212.20.115.148']


class TestSenderIdentity:

    def test_server_drops_spoofed_player_index(self):
        net = h.Network()
        liar, victim = net.add_client(1), net.add_client(2)
        chat(liar, "I am player 3", player_index=2)
        net.flush()
        assert drain(net.server.message_queue) == []
        assert drain(victim.message_queue) == []


class TestClientDisconnectReporting:

    def test_connect_reject_is_reported(self):
        client = NetworkClient()
        client.socket = h._FrameSocket(lambda frame: None)
        client.connected = True
        client._handle_received_message({'type': MessageType.CONNECT_REJECT, 'seq': 0,
                                         'data': {'reason': 'Lobby is full'}})
        assert client.disconnected
        assert 'Lobby is full' in client.disconnect_reason

    def test_send_failure_is_reported(self):
        client = NetworkClient()
        broken = h._FrameSocket(lambda frame: None)
        broken.closed = True                      # sendall raises OSError
        client.socket = broken
        client.connected = True
        client.send_message(b'\x00\x00\x00\x02{}')
        client._send_to_server()
        assert client.disconnected
        assert client.disconnect_reason


class TestSyncLogger:

    def test_sync_logger_records_enum_action_types(self):
        from game_state import GameState
        from sync_logger import SyncLogger
        gs = GameState(num_players=2, skip_setup_phase=True)
        sync = SyncLogger(gs, 0, True)
        sync.record_action(MessageType.MOVEMENT_ORDER, 0, 1, {}, source='local')
        assert len(sync.actions) == 1
