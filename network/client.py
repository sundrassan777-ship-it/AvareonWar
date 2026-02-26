"""
Network client implementation for multiplayer client.

Client player uses this to connect to a host server.
"""

import socket
import threading
import time
from typing import Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network_config import (
    DEFAULT_PORT, MESSAGE_BUFFER_SIZE, HEARTBEAT_INTERVAL,
    CONNECTION_TIMEOUT, MessageType
)
from network.protocol import NetworkProtocol, MessageBuffer
from network.message_queue import NetworkMessageQueue
from utils.logger import get_logger

logger = get_logger(__name__)

# M29: Build set of all known MessageType values for validation at import time.
# This allows _handle_received_message to reject messages with unknown types.
_KNOWN_MESSAGE_TYPES = {
    v for k, v in vars(MessageType).items()
    if not k.startswith('_') and isinstance(v, str)
}


class NetworkClient:
    """
    Network client for joining multiplayer games.

    Connects to a host server and communicates via message queue.
    """

    def __init__(self):
        """Initialize network client"""
        self.socket = None
        self.server_address = None

        # Protocol handler
        self.protocol = NetworkProtocol()

        # Message queues
        self.message_queue = NetworkMessageQueue()

        # Network thread
        self.network_thread = None
        self.running = False

        # H7: Lock for shared state accessed by both main thread and network thread.
        # Protects: connected, socket, running, disconnected, player_index
        self._state_lock = threading.Lock()

        # Connection state
        self.connected = False
        self.player_index = None  # Assigned by server
        self.last_ping_time = 0
        self.last_pong_time = 0
        self.disconnected = False  # Set to True when disconnected
        self.disconnect_reason = ""  # Reason for disconnection

        # Reconnection support
        self.reconnect_password = ""  # Password for reconnection (received on connect)
        self.player_name = ""  # Store name for reconnection
        self.last_server_address = None  # Store for reconnection

        # Message buffer for receiving
        self.recv_buffer = MessageBuffer()

        # M11: Dispatch table for message handlers -- replaces if-elif chain.
        # PING is handled inline in _handle_received_message (needs direct socket access).
        # Unregistered types fall through to message_queue.receive_message().
        self._message_handlers = {
            MessageType.CONNECT_ACCEPT: self._handle_connect_accept,
            MessageType.CONNECT_REJECT: self._handle_connect_reject,
            MessageType.DISCONNECT: self._handle_disconnect_message,
            MessageType.RECONNECT_ACCEPT: self._handle_reconnect_accept,
            MessageType.RECONNECT_REJECT: self._handle_reconnect_reject,
        }

    def connect(self, host: str, port: int = DEFAULT_PORT, player_name: str = "Player") -> bool:
        """
        Connect to a host server.

        Args:
            host: Host IP address or hostname
            port: Port number
            player_name: Player name to send in connection request

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5 second timeout for connect

            # Connect to server
            logger.info(f"Connecting to {host}:{port}...")
            self.socket.connect((host, port))

            # Set non-blocking after connection established
            self.socket.setblocking(False)

            self.server_address = (host, port)
            self.last_server_address = (host, port)
            self.player_name = player_name
            # H7: Lock around shared state write (main thread, read by network thread)
            with self._state_lock:
                self.connected = True

            logger.info(f"Connected to server at {host}:{port}")

            # Send connection request
            connect_msg = self.protocol.create_connect_request(player_name)
            self.socket.sendall(connect_msg)

            # Start network thread
            self.running = True
            self.network_thread = threading.Thread(target=self._network_loop, daemon=True)
            self.network_thread.start()

            # Wait for connection acceptance (with timeout)
            timeout = 5.0
            # C6: Use monotonic clock -- immune to NTP sync / daylight saving shifts
            start_time = time.monotonic()
            while self.player_index is None:
                if time.monotonic() - start_time > timeout:
                    logger.warning("Connection timeout - no response from server")
                    self.disconnect()
                    return False
                time.sleep(0.1)

            # Update message queue state
            self.message_queue.set_connected(True)

            logger.info(f"Connection accepted - assigned as Player {self.player_index + 1}")
            return True

        except socket.timeout:
            logger.warning("Connection timeout")
            self.disconnect()
            return False
        except ConnectionRefusedError:
            logger.warning("Connection refused - server not available")
            self.disconnect()
            return False
        except OSError as e:
            logger.error(f"Connection error: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        """Disconnect from server (called from main thread)"""
        self.running = False

        # H7: Lock around shared state reads (main thread accessing cross-thread state)
        with self._state_lock:
            is_connected = self.connected
            sock = self.socket

        # Send disconnect message if connected (outside lock -- no lock around socket I/O)
        if is_connected and sock:
            try:
                disconnect_msg = self.protocol.create_disconnect("Client disconnecting")
                sock.sendall(disconnect_msg)
            except (OSError, BrokenPipeError):
                pass  # C3 fix: Socket may already be closed

        # H7: Lock around socket close and state clear
        with self._state_lock:
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass  # C3 fix: Socket close can fail if already closed
                self.socket = None

        # Wait for network thread to finish
        if self.network_thread and self.network_thread.is_alive():
            self.network_thread.join(timeout=2.0)

        # H7: Lock around final state clear
        with self._state_lock:
            self.connected = False
            self.disconnected = False
            self.player_index = None
        self.server_address = None
        self.recv_buffer.clear()
        self.message_queue.clear()

        logger.info("Disconnected from server")

    def _network_loop(self):
        """Main network loop (runs in separate thread)"""
        # H7: Lock around condition check for cross-thread shared state
        while True:
            with self._state_lock:
                if not self.running or not self.connected:
                    break
            try:
                # Receive data from server
                self._receive_from_server()

                # Send queued messages to server
                self._send_to_server()

                # Check for connection timeout
                self._check_timeout()

            except Exception as e:
                logger.error(f"Network error: {e}")
                # H7: Lock around shared state writes from network thread
                with self._state_lock:
                    self.disconnected = True
                    self.disconnect_reason = f"Network error: {e}"
                self._disconnect()
                break

            # Small sleep to avoid busy-waiting
            time.sleep(0.01)

    def _receive_from_server(self):
        """Receive data from server and process messages"""
        # H7: Snapshot socket ref under lock; do I/O outside lock (fine-grained)
        with self._state_lock:
            sock = self.socket
        if not sock:
            return

        try:
            # Receive data (non-blocking)
            data = sock.recv(MESSAGE_BUFFER_SIZE)

            if not data:
                # Connection closed - host disconnected
                logger.warning("Server disconnected")
                with self._state_lock:
                    self.disconnected = True
                    self.disconnect_reason = "Host disconnected"
                self._disconnect()
                return

            # H13 fix: check buffer overflow and disconnect on overflow
            if not self.recv_buffer.add_data(data):
                logger.warning("Buffer overflow from server, disconnecting")
                # H10 fix: acquire lock for thread-safe state update
                with self._state_lock:
                    self.disconnected = True
                    self.disconnect_reason = "Buffer overflow"
                self._disconnect()
                return

            # Extract and process complete messages
            while True:
                message_bytes = self.recv_buffer.extract_message()
                if not message_bytes:
                    break

                # Decode and validate message (mirror server-side validation)
                message = self.protocol.decode_message(message_bytes)
                if message and self.protocol.validate_message(message):
                    self._handle_received_message(message)

        except BlockingIOError:
            # No data available (non-blocking socket)
            pass
        except ConnectionResetError:
            logger.warning("Connection reset by server")
            with self._state_lock:
                self.disconnected = True
                self.disconnect_reason = "Host disconnected"
            self._disconnect()
        except Exception as e:
            logger.error(f"Receive error: {e}")
            with self._state_lock:
                self.disconnected = True
                self.disconnect_reason = f"Connection error: {e}"
            self._disconnect()

    def _send_to_server(self):
        """Send queued messages to server"""
        # H7: Snapshot socket ref under lock; do I/O outside lock (fine-grained)
        with self._state_lock:
            sock = self.socket
        if not sock:
            return

        # Send all queued messages
        while self.message_queue.has_outgoing_messages():
            message = self.message_queue.get_outgoing_message(timeout=0)
            if not message:
                break

            try:
                sock.sendall(message)
            except Exception as e:
                logger.error(f"Send error: {e}")
                self._disconnect()
                break

    def _handle_received_message(self, message: dict):
        """
        Handle a received message from server.

        Validates message structure (M29), then dispatches to the appropriate
        handler via dispatch table (M11), or forwards to the message queue
        for unregistered types.

        Args:
            message: Decoded message dict
        """
        # M29: Validate message has a 'type' key with a known MessageType value
        msg_type = message.get('type')
        if msg_type is None:
            logger.warning("Received message with no 'type' key, ignoring")
            return
        if msg_type not in _KNOWN_MESSAGE_TYPES:
            logger.warning(f"Received message with unknown type '{msg_type}', ignoring")
            return

        # PING handled inline -- needs direct socket access for immediate pong response
        if msg_type == MessageType.PING:
            pong_msg = self.protocol.create_pong()
            # H7: Snapshot socket ref under lock for thread-safe access
            with self._state_lock:
                sock = self.socket
            if sock:
                try:
                    sock.sendall(pong_msg)
                except (OSError, BrokenPipeError):
                    pass  # Socket may have closed between check and send
            # C6: Use monotonic clock for pong timestamp
            self.last_pong_time = time.monotonic()
            return

        # M11: Look up handler from dispatch table, fall back to message queue
        handler = self._message_handlers.get(msg_type)
        if handler:
            handler(message)
        else:
            # Forward all other valid messages to game loop
            self.message_queue.receive_message(message)

    def _handle_connect_accept(self, message: dict):
        """Handle connection acceptance from server"""
        data = message.get('data', {})
        # H7: Lock around player_index write (network thread, read by main thread)
        with self._state_lock:
            self.player_index = data.get('player_index', 1)
            player_index = self.player_index

        # Store reconnection password if provided
        reconnect_password = data.get('reconnect_password', '')
        if reconnect_password:
            self.reconnect_password = reconnect_password
            logger.info(f"Connection accepted - Player {player_index + 1}")
            logger.debug(f"Reconnection password: {reconnect_password}")
        else:
            logger.info(f"Connection accepted - Player {player_index + 1}")

    def _handle_connect_reject(self, message: dict):
        """Handle connection rejection from server"""
        data = message.get('data', {})
        reason = data.get('reason', 'Unknown reason')
        logger.warning(f"Connection rejected: {reason}")
        self._disconnect()

    def _handle_disconnect_message(self, message: dict):
        """Handle DISCONNECT message from server (M11: extracted from if-elif chain)"""
        logger.warning("Server disconnected")
        # Host disconnected - set disconnected flag so game loop can detect it
        with self._state_lock:
            self.disconnected = True
            self.disconnect_reason = "Host disconnected"
        self._disconnect()

    def _handle_reconnect_accept(self, message: dict):
        """Handle reconnection acceptance from server"""
        data = message.get('data', {})
        # H7: Lock around player_index write (network thread, read by main thread)
        with self._state_lock:
            self.player_index = data.get('player_index', self.player_index)
            player_index = self.player_index
        logger.info(f"Reconnection successful - restored as Player {player_index + 1}")

        # Forward to game loop for state sync
        self.message_queue.receive_message(message)

    def _handle_reconnect_reject(self, message: dict):
        """Handle reconnection rejection from server"""
        data = message.get('data', {})
        reason = data.get('reason', 'Invalid credentials')
        logger.warning(f"Reconnection rejected: {reason}")

        # Forward to game loop to show error
        self.message_queue.receive_message(message)
        self._disconnect()

    def _check_timeout(self):
        """Check for connection timeout"""
        # C6: Use monotonic clock -- immune to NTP sync / daylight saving shifts
        current_time = time.monotonic()

        # Check if we've received PING recently
        if self.last_pong_time > 0 and current_time - self.last_pong_time > CONNECTION_TIMEOUT:
            logger.warning(f"Connection timeout (no ping for {CONNECTION_TIMEOUT}s)")
            # H7: Lock around shared state writes from network thread
            with self._state_lock:
                self.disconnect_reason = "Connection timeout"
                self.disconnected = True
            self._disconnect()

    def _disconnect(self):
        """Internal disconnect (from network thread)"""
        # H7: Lock around shared state writes -- called from network thread
        with self._state_lock:
            self.connected = False
            sock = self.socket
        self.message_queue.set_connected(False)

        if sock:
            try:
                sock.close()
            except OSError:
                pass  # C3 fix: Socket close can fail if already closed

    def send_message(self, message: bytes):
        """
        Queue a message to send to server.

        Args:
            message: Encoded message bytes

        Called by game loop to send messages.
        """
        self.message_queue.send_message(message)

    def is_connected(self) -> bool:
        """Check if connected to server"""
        # H7: Lock around shared state read (called from main thread)
        with self._state_lock:
            return self.connected

    def get_player_index(self) -> Optional[int]:
        """Get assigned player index (0 or 1)"""
        return self.player_index

    def get_reconnect_password(self) -> str:
        """Get the reconnection password (display to user for safekeeping)"""
        return self.reconnect_password

    def reconnect(self, host: str = None, port: int = None, player_name: str = None,
                  password: str = None) -> bool:
        """
        Attempt to reconnect to the server after disconnection.

        Args:
            host: Server host (uses last connected if not specified)
            port: Server port (uses last connected if not specified)
            player_name: Player name (uses stored name if not specified)
            password: Reconnection password (uses stored if not specified)

        Returns:
            True if reconnection request was sent, False if unable to connect
        """
        # Guard against concurrent reconnection attempts
        with self._state_lock:
            if self.connected:
                logger.warning("Already connected, skipping reconnection")
                return False

        # Use stored values if not specified
        if host is None or port is None:
            if self.last_server_address:
                host = host or self.last_server_address[0]
                port = port or self.last_server_address[1]
            else:
                logger.warning("No server address available for reconnection")
                return False

        player_name = player_name or self.player_name
        password = password or self.reconnect_password

        if not player_name or not password:
            logger.warning("Missing player name or password for reconnection")
            return False

        try:
            # Create new socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)

            # Connect to server
            logger.info(f"Reconnecting to {host}:{port}...")
            self.socket.connect((host, port))

            # Set non-blocking after connection established
            self.socket.setblocking(False)

            self.server_address = (host, port)
            # H7: Lock around shared state writes (main thread, read by network thread)
            with self._state_lock:
                self.connected = True
                self.disconnected = False
            self.disconnect_reason = ""

            logger.info("Connected to server, sending reconnect request...")

            # Send reconnect request
            reconnect_msg = self.protocol.create_reconnect_request(player_name, password)
            self.socket.sendall(reconnect_msg)

            # Start network thread
            self.running = True
            self.recv_buffer.clear()
            self.network_thread = threading.Thread(target=self._network_loop, daemon=True)
            self.network_thread.start()

            # Wait for reconnection response (with timeout)
            timeout = 5.0
            # C6: Use monotonic clock -- immune to NTP sync / daylight saving shifts
            start_time = time.monotonic()
            # L7 fix: player_index is always None or valid int, never negative
            while self.player_index is None:
                if time.monotonic() - start_time > timeout:
                    logger.warning("Reconnection timeout - no response from server")
                    self.disconnect()
                    return False
                if self.disconnected:
                    logger.warning("Reconnection failed")
                    return False
                time.sleep(0.1)

            # Update message queue state
            self.message_queue.set_connected(True)

            logger.info(f"Reconnection successful - restored as Player {self.player_index + 1}")
            return True

        except socket.timeout:
            logger.warning("Reconnection timeout")
            self.disconnect()
            return False
        except ConnectionRefusedError:
            logger.warning("Reconnection refused - server not available")
            self.disconnect()
            return False
        except OSError as e:
            logger.error(f"Reconnection error: {e}")
            self.disconnect()
            return False
