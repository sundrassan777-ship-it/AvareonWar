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
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from network.client import NetworkClient  # noqa: E402
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

    @pytest.mark.xfail(strict=True, reason="C4: a PONG sent straight from the client network "
                       "thread overtakes game messages already queued with lower sequence "
                       "numbers; the server then drops them as replays")
    def test_pong_does_not_swallow_a_queued_game_message(self):
        net = h.Network()
        client = net.add_client(1)
        chat(client, "queued before the PING")              # seq N, still in the queue
        net.server.clients[1].socket.sendall(net.server.protocol.create_ping())  # PONG N+1 goes out now
        net.flush()                                          # the network thread sends seq N
        types = [m['type'] for m in drain(net.server.message_queue)]
        assert MessageType.CHAT_MESSAGE in types

    @pytest.mark.xfail(strict=True, reason="H7: the server keeps the departed client's last "
                       "sequence number, so a new client in the same slot is rejected as a replay")
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


class TestSenderIdentity:

    @pytest.mark.xfail(strict=True, reason="L5: the server accepts and relays payloads whose "
                       "player_index is not the sender")
    def test_server_drops_spoofed_player_index(self):
        net = h.Network()
        liar, victim = net.add_client(1), net.add_client(2)
        chat(liar, "I am player 3", player_index=2)
        net.flush()
        assert drain(net.server.message_queue) == []
        assert drain(victim.message_queue) == []


class TestClientDisconnectReporting:

    @pytest.mark.xfail(strict=True, reason="M8: CONNECT_REJECT closes the socket but never sets "
                       "disconnected, and the reason is lost")
    def test_connect_reject_is_reported(self):
        client = NetworkClient()
        client.socket = h._FrameSocket(lambda frame: None)
        client.connected = True
        client._handle_received_message({'type': MessageType.CONNECT_REJECT, 'seq': 0,
                                         'data': {'reason': 'Lobby is full'}})
        assert client.disconnected
        assert 'Lobby is full' in client.disconnect_reason

    @pytest.mark.xfail(strict=True, reason="M8: a send error stops the client network loop "
                       "without setting disconnected, so no 'Connection Lost' dialog appears")
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

    @pytest.mark.xfail(strict=True, reason="L1: str(MessageType.X) is 'MessageType.X' on Python "
                       "3.11+, so actions sent with enum types are never logged")
    def test_sync_logger_records_enum_action_types(self):
        from game_state import GameState
        from sync_logger import SyncLogger
        gs = GameState(num_players=2, skip_setup_phase=True)
        sync = SyncLogger(gs, 0, True)
        sync.record_action(MessageType.MOVEMENT_ORDER, 0, 1, {}, source='local')
        assert len(sync.actions) == 1
