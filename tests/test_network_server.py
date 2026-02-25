"""
Tests for network/server.py

These tests cover the NetworkServer class, particularly focusing on:
- Server lifecycle (start/stop)
- Multi-client connection handling
- Error handling in areas that previously had bare except clauses
- Message processing with player_index routing

Updated for multi-client architecture where:
- Clients live in server.clients: Dict[int, ClientConnection]
- All methods take player_index or socket args (no single-client assumptions)
- Each ClientConnection has its own recv_buffer, socket, address
"""

import pytest
import socket
import threading
import time
from unittest.mock import Mock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network.server import NetworkServer, ClientConnection
from network.protocol import NetworkProtocol, MessageBuffer
from network.message_queue import NetworkMessageQueue
from network_config import DEFAULT_PORT, MessageType, NETWORK_VERSION


def _make_client(player_index, mock_socket=None, address=("127.0.0.1", 12345)):
    """Helper: create a ClientConnection with a mock socket for testing."""
    if mock_socket is None:
        mock_socket = Mock()
    return ClientConnection(
        socket=mock_socket,
        address=address,
        player_index=player_index,
        last_pong_time=time.monotonic(),
        connected=True,
    )


class TestNetworkServerInit:
    """Tests for NetworkServer initialization"""

    def test_init_default_port(self):
        """Server initializes with default port and empty clients dict"""
        server = NetworkServer()
        assert server.port == DEFAULT_PORT
        assert server.socket is None
        # Multi-client: no client_socket attr; clients dict starts empty
        assert server.clients == {}
        assert server.running is False

    def test_init_custom_port(self):
        """Server initializes with custom port"""
        server = NetworkServer(port=9999)
        assert server.port == 9999

    def test_init_creates_protocol(self):
        """Server creates protocol handler"""
        server = NetworkServer()
        assert isinstance(server.protocol, NetworkProtocol)

    def test_init_creates_message_queue(self):
        """Server creates message queue"""
        server = NetworkServer()
        assert isinstance(server.message_queue, NetworkMessageQueue)

    def test_init_client_connection_has_recv_buffer(self):
        """Each ClientConnection has its own MessageBuffer (no server-level recv_buffer)"""
        # Server no longer has a top-level recv_buffer; each ClientConnection does
        client = _make_client(player_index=1)
        assert isinstance(client.recv_buffer, MessageBuffer)


class TestNetworkServerStartStop:
    """Tests for server start/stop lifecycle"""

    def test_start_success(self):
        """Server starts successfully on available port"""
        server = NetworkServer(port=0)  # Port 0 = OS assigns available port
        try:
            result = server.start()
            assert result is True
            assert server.running is True
            assert server.socket is not None
        finally:
            server.stop()

    def test_start_port_in_use(self):
        """Server returns False when port is in use"""
        import socket as sock
        # Bind a socket directly to ensure port is truly in use
        blocking_socket = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
        blocking_socket.setsockopt(sock.SOL_SOCKET, sock.SO_REUSEADDR, 1)
        blocking_socket.bind(('127.0.0.1', 0))
        blocking_socket.listen(1)
        actual_port = blocking_socket.getsockname()[1]

        # Server tries same port
        server = NetworkServer(port=actual_port)
        try:
            result = server.start()
            # On Windows with SO_REUSEADDR, this might succeed, so we just
            # verify the test doesn't crash - the behavior varies by OS
            # L9 fix: Assert type rather than trivially-true membership
            assert isinstance(result, bool), f"start() should return bool, got {type(result)}"
        finally:
            server.stop()
            blocking_socket.close()

    def test_stop_cleans_up(self):
        """Server stop cleans up resources"""
        server = NetworkServer(port=0)
        server.start()
        server.stop()

        assert server.running is False
        assert server.socket is None

    def test_stop_without_start(self):
        """Server stop is safe without start"""
        server = NetworkServer()
        server.stop()  # Should not raise
        assert server.running is False

    def test_stop_clears_message_queue(self):
        """Server stop clears message queue"""
        server = NetworkServer(port=0)
        server.start()
        server.message_queue.send_message(b"test")
        server.stop()

        assert not server.message_queue.has_outgoing_messages()


class TestNetworkServerStop:
    """Tests specifically for stop() method error handling

    These tests verify that the stop() method handles errors gracefully
    in the areas that previously had bare except clauses.
    """

    def test_stop_handles_disconnect_send_error(self):
        """stop() handles errors when sending disconnect message to a client"""
        server = NetworkServer(port=0)
        server.start()

        # Add a mock client whose socket errors on sendall
        mock_sock = Mock()
        mock_sock.sendall.side_effect = OSError("Connection refused")
        server.clients[1] = _make_client(1, mock_socket=mock_sock)

        # Should not raise - error should be handled gracefully
        server.stop()
        assert server.running is False

    def test_stop_handles_client_socket_close_error(self):
        """stop() handles errors when closing a client socket"""
        server = NetworkServer(port=0)
        server.start()

        # Add a mock client whose socket errors on close
        mock_sock = Mock()
        mock_sock.close.side_effect = OSError("Socket already closed")
        server.clients[1] = _make_client(1, mock_socket=mock_sock)

        # Should not raise; clients dict should be cleared
        server.stop()
        assert server.clients == {}

    def test_stop_handles_server_socket_close_error(self):
        """stop() handles errors when closing server socket"""
        server = NetworkServer(port=0)
        server.start()

        # Replace socket with mock that errors on close
        original_socket = server.socket
        mock_socket = Mock()
        mock_socket.close.side_effect = OSError("Socket error")
        server.socket = mock_socket

        # Should not raise
        server.stop()
        assert server.socket is None

        # Clean up original socket
        try:
            original_socket.close()
        except OSError:
            pass


class TestNetworkServerHeartbeat:
    """Tests for heartbeat functionality

    Tests the _send_heartbeat() method which sends PINGs to all clients.
    """

    def test_send_heartbeat_success(self):
        """Heartbeat sends PING to connected client"""
        server = NetworkServer(port=0)
        server.last_ping_time = 0  # Force heartbeat to send

        # Add a mock client to receive the heartbeat
        mock_sock = Mock()
        server.clients[1] = _make_client(1, mock_socket=mock_sock)

        server._send_heartbeat()

        # The client's socket should have received the PING
        assert mock_sock.sendall.called
        assert server.last_ping_time > 0

    def test_send_heartbeat_handles_socket_error(self):
        """Heartbeat handles socket errors by marking client disconnected"""
        server = NetworkServer(port=0)
        server.last_ping_time = 0

        # Add a mock client whose socket errors on sendall
        mock_sock = Mock()
        mock_sock.sendall.side_effect = OSError("Connection reset")
        server.clients[1] = _make_client(1, mock_socket=mock_sock)

        # Should not raise
        server._send_heartbeat()

        # Ping time IS updated (the server iterates all clients, updates time
        # after the loop regardless of per-client errors)
        assert server.last_ping_time > 0

    def test_send_heartbeat_handles_broken_pipe(self):
        """Heartbeat handles BrokenPipeError without crashing"""
        server = NetworkServer(port=0)
        server.last_ping_time = 0

        # Add a mock client whose socket raises BrokenPipeError
        mock_sock = Mock()
        mock_sock.sendall.side_effect = BrokenPipeError("Broken pipe")
        server.clients[1] = _make_client(1, mock_socket=mock_sock)

        # Should not raise
        server._send_heartbeat()


class TestNetworkServerDisconnect:
    """Tests for _disconnect_client(player_index) method

    Tests the disconnect handling for the multi-client architecture.
    """

    def test_disconnect_client_success(self):
        """Disconnect removes client from server.clients and closes socket"""
        server = NetworkServer(port=0)

        mock_sock = Mock()
        client = _make_client(1, mock_socket=mock_sock)
        client.recv_buffer.add_data(b"test data")
        server.clients[1] = client

        server._disconnect_client(1)

        # Client should be removed from dict
        assert 1 not in server.clients
        # Socket should have been closed
        assert mock_sock.close.called

    def test_disconnect_handles_close_error(self):
        """Disconnect handles socket close errors gracefully"""
        server = NetworkServer(port=0)

        mock_sock = Mock()
        mock_sock.close.side_effect = OSError("Already closed")
        server.clients[1] = _make_client(1, mock_socket=mock_sock)

        # Should not raise
        server._disconnect_client(1)

        # Client removed even though close errored
        assert 1 not in server.clients

    def test_disconnect_with_no_client(self):
        """Disconnect is safe when player_index not in clients dict"""
        server = NetworkServer(port=0)

        # No clients present - calling with a missing index should not raise
        server._disconnect_client(1)


class TestNetworkServerGetLocalIP:
    """Tests for get_local_ip() method

    Tests the IP detection which had a bare except clause.
    """

    def test_get_local_ip_success(self):
        """get_local_ip returns valid IP"""
        server = NetworkServer()
        ip = server.get_local_ip()

        # Should return an IP address format
        parts = ip.split('.')
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_get_local_ip_fallback_on_error(self):
        """get_local_ip returns localhost on error"""
        server = NetworkServer()

        with patch('socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket.connect.side_effect = OSError("Network unreachable")
            mock_socket_class.return_value = mock_socket

            ip = server.get_local_ip()
            assert ip == "127.0.0.1"


class TestNetworkServerMessageHandling:
    """Tests for message handling with player_index routing"""

    def test_handle_connect_request_valid(self):
        """Handle valid connection request sends accept to the client"""
        server = NetworkServer()

        # Set up a mock client in the clients dict
        mock_sock = Mock()
        player_index = 1
        server.clients[player_index] = _make_client(player_index, mock_socket=mock_sock)

        message = {
            'type': MessageType.CONNECT_REQUEST,
            'data': {'version': NETWORK_VERSION}
        }

        server._handle_connect_request(message, player_index)

        # Should send accept message to the client's socket
        assert mock_sock.sendall.called

    def test_handle_connect_request_version_mismatch(self):
        """Handle connection request with version mismatch sends reject"""
        server = NetworkServer()

        mock_sock = Mock()
        player_index = 1
        server.clients[player_index] = _make_client(player_index, mock_socket=mock_sock)

        message = {
            'type': MessageType.CONNECT_REQUEST,
            'data': {'version': 'wrong_version'}
        }

        server._handle_connect_request(message, player_index)

        # Should have sent reject message before disconnecting
        assert mock_sock.sendall.called

    def test_handle_pong_updates_time(self):
        """Handle PONG updates last_pong_time on the correct client"""
        server = NetworkServer()

        player_index = 1
        client = _make_client(player_index)
        client.last_pong_time = 0  # Old pong time
        server.clients[player_index] = client

        # Message must include 'seq' and 'data' to pass validate_message()
        message = {'type': MessageType.PONG, 'seq': 0, 'data': {}}
        server._handle_received_message(message, player_index)

        # Client's last_pong_time should be updated
        assert server.clients[player_index].last_pong_time > 0

    def test_handle_disconnect_message(self):
        """Handle DISCONNECT message from a specific client"""
        server = NetworkServer()

        mock_sock = Mock()
        player_index = 1
        server.clients[player_index] = _make_client(player_index, mock_socket=mock_sock)

        # Message must include 'seq' and 'data' to pass validate_message()
        message = {'type': MessageType.DISCONNECT, 'seq': 0, 'data': {}}
        server._handle_received_message(message, player_index)

        # Client should be removed from the dict
        assert player_index not in server.clients


class TestNetworkServerReceive:
    """Tests for _receive_from_client_socket(sock)"""

    def test_receive_no_matching_client(self):
        """Receive returns early if socket doesn't match any client"""
        server = NetworkServer()

        # Pass an unknown socket - should not raise
        unknown_sock = Mock()
        server._receive_from_client_socket(unknown_sock)

    def test_receive_blocking_io_error(self):
        """Receive handles BlockingIOError (no data available yet)"""
        server = NetworkServer()

        mock_sock = Mock()
        mock_sock.recv.side_effect = BlockingIOError()
        player_index = 1
        server.clients[player_index] = _make_client(player_index, mock_socket=mock_sock)

        # Should not raise or disconnect the client
        server._receive_from_client_socket(mock_sock)
        assert player_index in server.clients

    def test_receive_connection_reset(self):
        """Receive handles ConnectionResetError by disconnecting client"""
        server = NetworkServer()

        mock_sock = Mock()
        mock_sock.recv.side_effect = ConnectionResetError()
        player_index = 1
        server.clients[player_index] = _make_client(player_index, mock_socket=mock_sock)

        server._receive_from_client_socket(mock_sock)

        # Client should be disconnected (removed from dict)
        assert player_index not in server.clients


class TestNetworkServerSend:
    """Tests for _send_to_clients()"""

    def test_send_no_clients(self):
        """Send does nothing with no connected clients"""
        server = NetworkServer()
        server.message_queue.send_message(b"test")

        # Should not raise (broadcasts to empty clients dict)
        server._send_to_clients()

    def test_send_success(self):
        """Send queued messages to all connected clients"""
        server = NetworkServer()

        mock_sock = Mock()
        server.clients[1] = _make_client(1, mock_socket=mock_sock)
        server.message_queue.send_message(b"test message")

        server._send_to_clients()

        # Client's socket should have received the message
        mock_sock.sendall.assert_called_with(b"test message")

    def test_send_handles_error(self):
        """Send handles socket errors by marking client disconnected"""
        server = NetworkServer()

        mock_sock = Mock()
        mock_sock.sendall.side_effect = OSError("Connection refused")
        server.clients[1] = _make_client(1, mock_socket=mock_sock)
        server.message_queue.send_message(b"test")

        server._send_to_clients()

        # Client should be cleaned up after send error
        assert 1 not in server.clients


class TestNetworkServerTimeout:
    """Tests for connection timeout checking"""

    def test_check_timeouts_no_timeout(self):
        """No timeout when recent pong received"""
        server = NetworkServer()

        # Client with recent pong time
        client = _make_client(1)
        client.last_pong_time = time.monotonic()
        server.clients[1] = client

        server._check_timeouts()

        # Client should still be connected
        assert 1 in server.clients
        assert server.disconnected is False

    def test_check_timeouts_triggers_disconnect(self):
        """Timeout triggers disconnect for stale client"""
        server = NetworkServer()

        # Client with very old pong time
        mock_sock = Mock()
        client = _make_client(1, mock_socket=mock_sock)
        client.last_pong_time = 0  # Very old — will exceed CONNECTION_TIMEOUT
        server.clients[1] = client

        server._check_timeouts()

        # Client should be disconnected (removed from dict)
        assert 1 not in server.clients


class TestNetworkServerIntegration:
    """Integration tests for server behavior"""

    def test_full_lifecycle(self):
        """Test complete server lifecycle"""
        server = NetworkServer(port=0)

        # Start
        assert server.start() is True
        assert server.running is True

        # Stop
        server.stop()
        assert server.running is False
        assert server.socket is None

    def test_send_message_api(self):
        """Test public send_message API queues messages"""
        server = NetworkServer()
        server.send_message(b"test message")

        assert server.message_queue.has_outgoing_messages()

    def test_is_client_connected_api(self):
        """Test public is_client_connected checks clients dict"""
        server = NetworkServer()

        # No clients — not connected
        assert server.is_client_connected() is False

        # Add a client — now connected
        server.clients[1] = _make_client(1)
        assert server.is_client_connected() is True
