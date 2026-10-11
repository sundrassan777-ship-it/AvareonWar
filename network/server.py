"""
Network server implementation for multiplayer host.

Host player runs this server to accept multiple client connections (up to 3 clients for 4-player games).
Uses TCP sockets with length-prefix framing for reliable message delivery.

Key Features:
- Multi-client support (up to MAX_CLIENTS connections)
- Non-blocking I/O with select() for multiple sockets
- Heartbeat mechanism for connection health monitoring
- Automatic timeout detection using monotonic clock
- Thread-safe message queuing between game loop and network thread
- Broadcast and targeted messaging

Architecture:
    Game Loop <---> NetworkMessageQueue <---> NetworkServer <---> Clients (1-3)
                    (thread-safe queues)     (network thread)

Time Handling:
    Uses time.monotonic() for all timeout calculations to ensure reliability
    even if system clock changes (e.g., NTP sync, daylight saving).
"""

import socket
import threading
import time
import select
import hashlib
import hmac
import secrets
from typing import Optional, Dict, List
from dataclasses import dataclass, field

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network_config import (
    DEFAULT_PORT, MESSAGE_BUFFER_SIZE, HEARTBEAT_INTERVAL,
    CONNECTION_TIMEOUT, MAX_CLIENTS, RECONNECTION_TIMEOUT, RECONNECT_ENABLED,
    SEND_TIMEOUT, MessageType
)
from network.protocol import NetworkProtocol, MessageBuffer
from network.message_queue import NetworkMessageQueue
from utils.logger import get_logger

logger = get_logger(__name__)

# Message types that should be relayed from one client to OTHER clients.
# Enables 3+ player multiplayer where clients need to see each other's actions.
# Host still receives these via message_queue as before.
# NOT relayed: connection/lobby/reconnect, host-originated broadcasts
# (FULL_STATE_SYNC, SIM_ALL_READY, SIM_ROUND_COMPLETE, SIM_TIMER_UPDATE),
# STATE_CHECKSUM, SIM_PLAYER_READY (host manages ready state).
_RELAY_MESSAGE_TYPES = frozenset({
    # Sequential mode gameplay
    MessageType.MOVEMENT_ORDER,
    MessageType.BUILDING_ORDER,
    MessageType.TRAINING_ORDER,
    MessageType.ORDER_REMOVE,
    MessageType.RESEARCH_ORDER,
    MessageType.HERO_TRAINING_ORDER,
    MessageType.EXECUTE_ORDERS,
    MessageType.BATTLE_RESOLVE,
    MessageType.TURN_END,
    MessageType.UNIT_COMPLETE,
    MessageType.BUILDING_COMPLETE,
    # Both modes
    MessageType.CHAT_MESSAGE,
    MessageType.SIM_HERO_ABILITY,
    MessageType.GOLD_TRANSFER,
    # Simultaneous mode
    MessageType.SIM_ALLIANCE_CHOICE,
})

# Message types the anti-replay sequence check ignores (and which do not advance the
# accepted counter). The client's network thread answers a PING the instant it arrives,
# so its PONG can carry a NEWER sequence number than game messages still waiting in the
# client's send queue; checking PONG made the server drop those game messages as
# "replays" (lost END TURN / READY / battle results -> hung games). DISCONNECT is sent
# straight from the closing thread for the same reason.
_SEQ_EXEMPT_TYPES = frozenset({
    MessageType.PONG,
    MessageType.DISCONNECT,
})

# Time allowed for the tiny reject / farewell messages to peers we are dropping anyway
_FAREWELL_SEND_TIMEOUT = 1.0  # seconds

# Messages only the HOST sends. One arriving from a client (a modified client or a bug)
# is dropped: the host would otherwise run the client-side handling of e.g. a round end.
_HOST_ONLY_TYPES = frozenset({
    MessageType.SIM_ALL_READY,
    MessageType.SIM_ROUND_COMPLETE,
    MessageType.SIM_READY_STATE,
    MessageType.SIM_TIMER_UPDATE,
})


@dataclass
class ClientConnection:
    """Represents a connected client's state."""
    socket: socket.socket
    address: tuple
    player_index: int
    player_name: str = ""
    password_hash: str = ""  # For reconnection
    recv_buffer: MessageBuffer = field(default_factory=MessageBuffer)
    last_pong_time: float = 0.0
    ping_sent_time: float = 0.0
    connected: bool = True
    # Highest sequence number accepted on THIS connection (anti-replay). Kept per
    # connection, not per slot index, so a new player taking a vacated slot starts
    # fresh - a per-index counter rejected every message of the newcomer.
    last_seq: int = -1


@dataclass
class DisconnectedPlayer:
    """Stores info for players who can reconnect."""
    player_index: int
    player_name: str
    password_hash: str
    disconnect_time: float  # monotonic time when disconnected


class NetworkServer:
    """
    Network server for hosting multiplayer games.

    Accepts up to MAX_CLIENTS client connections and relays messages between host and clients.
    Runs a background thread for non-blocking network I/O.

    Attributes:
        port (int): Port number the server listens on
        socket: Server socket for accepting connections
        clients (dict): Connected clients {player_index: ClientConnection}
        disconnected (bool): Set to True when any client disconnects unexpectedly
        disconnect_reason (str): Human-readable reason for disconnection

    Thread Safety:
        The server runs in a separate daemon thread. Communication with
        the game loop happens through NetworkMessageQueue, which provides
        thread-safe queues for bidirectional message passing.

    Backward Compatibility:
        For 1v1 games, is_client_connected() returns True when at least one client
        is connected, matching the original behavior.
    """

    def __init__(self, port: int = DEFAULT_PORT):
        """
        Initialize network server.

        Args:
            port: Port to listen on
        """
        self.port = port
        self.socket = None

        # Multi-client support: {player_index: ClientConnection}
        # Host is always player_index 0, clients are 1, 2, 3
        self.clients: Dict[int, ClientConnection] = {}
        self.next_player_index = 1  # Next index to assign (1, 2, or 3)

        # Reserved slots (for AI players) - clients cannot be assigned to these
        # When host configures a slot as AI, that slot is reserved
        self.reserved_slots: set = set()

        # Disconnected players who can reconnect: {player_index: DisconnectedPlayer}
        self.disconnected_players: Dict[int, DisconnectedPlayer] = {}
        # Use canonical timeout from network_config (was hardcoded 300s, should match config)
        self.reconnect_timeout = RECONNECTION_TIMEOUT

        # Whether we're in-game (affects disconnect handling)
        self.game_started = False

        # Protocol handler
        self.protocol = NetworkProtocol()

        # Message queues
        self.message_queue = NetworkMessageQueue()

        # Network thread
        self.network_thread = None
        self.running = False

        # Connection state
        self.last_ping_time = 0
        self.disconnected = False  # Set to True when any client disconnects unexpectedly
        self.disconnect_reason = ""  # Reason for disconnection

        # Lock for thread-safe client dict access
        # M3→H fix: use RLock (reentrant) — _handle_new_connection holds lock
        # and calls _get_next_player_index which also acquires it
        self._clients_lock = threading.RLock()

        # Phase 6A: Connection rate limiting (anti-DoS)
        # Tracks recent connection attempts per IP to prevent abuse
        self._connection_attempts = {}  # {ip: [timestamp, ...]}
        self._rate_limit_window = 10.0  # seconds
        self._rate_limit_max = 5  # max connections per window per IP
        self._last_rate_limit_cleanup = 0  # monotonic time of last stale-entry pruning

        # Security: reconnection rate limiting (H2 fix — anti-brute-force)
        self._reconnect_attempts = {}  # {ip: [timestamp, ...]}
        self._reconnect_rate_limit_window = 30.0  # seconds
        self._reconnect_rate_limit_max = 5  # max reconnect attempts per window per IP

        # Security (H1 anti-replay): the last accepted sequence number now lives on each
        # ClientConnection (last_seq), so it resets with the connection.

        # UPnP port forwarding manager (created on demand via setup_upnp())
        self.upnp_manager = None

    def start(self) -> bool:
        """
        Start the server and listen for connections.

        Returns:
            True if server started successfully, False otherwise
        """
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to port
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(MAX_CLIENTS)

            # Set non-blocking for select()
            self.socket.setblocking(False)

            # Start network thread
            self.running = True
            self.network_thread = threading.Thread(target=self._network_loop, daemon=True)
            self.network_thread.start()

            logger.info(f"Server started on port {self.port} (max {MAX_CLIENTS} clients)")
            return True

        except OSError as e:
            logger.error(f"Failed to start server: {e}")
            return False

    def stop(self):
        """Stop the server and close all connections"""
        self.running = False

        # Clean up UPnP port mapping before closing connections
        if self.upnp_manager:
            self.upnp_manager.cleanup()

        # Send disconnect message to all clients
        with self._clients_lock:
            for player_index, client in list(self.clients.items()):
                try:
                    disconnect_msg = self.protocol.create_disconnect("Server closing")
                    # Short timeout: a dead peer must not hold up quitting
                    client.socket.settimeout(_FAREWELL_SEND_TIMEOUT)
                    client.socket.sendall(disconnect_msg)
                except (OSError, BrokenPipeError, ConnectionResetError, AttributeError):
                    pass
                try:
                    client.socket.close()
                except OSError:
                    pass
            self.clients.clear()

        # Close server socket
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

        # Wait for network thread to finish
        if self.network_thread and self.network_thread.is_alive():
            self.network_thread.join(timeout=2.0)

        # Clear message queues
        self.message_queue.clear()

        logger.info("Server stopped")

    def _network_loop(self):
        """Main network loop (runs in separate thread) using select for multi-socket I/O"""
        while self.running:
            try:
                # Build list of sockets to monitor
                read_sockets = [self.socket]  # Server socket for new connections
                with self._clients_lock:
                    for client in self.clients.values():
                        if client.connected:
                            read_sockets.append(client.socket)

                # Use select with 0.1s timeout
                try:
                    readable, _, _ = select.select(read_sockets, [], [], 0.1)
                except (ValueError, OSError):
                    # Socket closed or invalid
                    continue

                for sock in readable:
                    if sock == self.socket:
                        # New connection attempt
                        self._accept_client()
                    else:
                        # Data from existing client
                        self._receive_from_client_socket(sock)

                # Send queued messages to clients
                self._send_to_clients()

                # Send heartbeat if needed
                self._send_heartbeat()

                # Check for connection timeouts
                self._check_timeouts()

            except Exception as e:
                logger.error(f"Network loop error: {e}", exc_info=True)

    def _accept_client(self):
        """Accept incoming client connection"""
        try:
            # Accept connection first, then validate
            client_socket, client_address = self.socket.accept()
            # Whether an accepted socket inherits non-blocking mode is OS-dependent; the
            # reject replies below are tiny, so a short timeout is plenty
            client_socket.settimeout(_FAREWELL_SEND_TIMEOUT)

            # Phase 6A: Rate limit connections per IP
            # Prevents a single IP from flooding the server with connection attempts
            client_ip = client_address[0]
            now = time.monotonic()
            attempts = self._connection_attempts.get(client_ip, [])
            # Remove expired attempts outside the rate limit window
            attempts = [t for t in attempts if now - t < self._rate_limit_window]
            if len(attempts) >= self._rate_limit_max:
                logger.warning(f"Rate limited connection from {client_ip} "
                               f"({len(attempts)} attempts in {self._rate_limit_window}s)")
                self._reject_connection(client_socket, "Too many connection attempts")
                return
            attempts.append(now)
            self._connection_attempts[client_ip] = attempts

            if self.game_started and not RECONNECT_ENABLED:
                # Nobody can join a running game (rejoining is switched off). Accepting
                # used to hand a stranger a free slot whose messages were relayed to
                # every player.
                logger.warning(f"Rejected connection from {client_address} - game in progress")
                self._reject_connection(client_socket, "The game has already started")
                return

            # M13 fix: Hold lock across check + insert to prevent TOCTOU race
            reject_reason = None
            with self._clients_lock:
                if len(self.clients) >= MAX_CLIENTS:
                    reject_reason = "Lobby is full"
                else:
                    # Find next available player index
                    player_index = self._get_next_player_index()
                    if player_index is None:
                        reject_reason = "No slots available"
                    else:
                        # Blocking sends with a time limit (L4). A non-blocking sendall()
                        # fails as soon as the kernel buffer is full, after an unknown
                        # part of the frame went out, so a large message (state snapshot)
                        # cut the connection. Reads stay non-blocking in effect: recv()
                        # only runs after select() reported the socket readable.
                        client_socket.settimeout(SEND_TIMEOUT)

                        # Create client connection object
                        client = ClientConnection(
                            socket=client_socket,
                            address=client_address,
                            player_index=player_index,
                            last_pong_time=time.monotonic()
                        )

                        self.clients[player_index] = client

            if reject_reason:
                # Outside the lock: the reject waits briefly for the peer (see
                # _reject_connection) and must not hold up the lobby meanwhile
                logger.warning(f"Rejected connection from {client_address} - {reject_reason}")
                self._reject_connection(client_socket, reject_reason)
                return

            logger.info(f"Client connected from {client_address} as Player {player_index + 1}")

            # Update message queue state (at least one client connected)
            self.message_queue.set_connected(True)

        except BlockingIOError:
            # No connection pending
            pass
        except OSError as e:
            logger.error(f"Accept error: {e}")

    def _reject_connection(self, client_socket, reason: str):
        """
        Turn a new connection away with a reason the joining player gets to see.

        The peer's CONNECT_REQUEST is usually already waiting, unread, when we reject.
        Closing a socket with unread data makes Windows reset the connection, and the
        reset throws away our CONNECT_REJECT before the client reads it - the player
        saw no reason at all. So: send, close our sending side, read what is waiting
        (briefly), then close.
        """
        try:
            client_socket.settimeout(_FAREWELL_SEND_TIMEOUT)
            client_socket.sendall(self.protocol.create_connect_reject(reason))
            client_socket.shutdown(socket.SHUT_WR)
            client_socket.settimeout(0.2)
            for _ in range(8):
                if not client_socket.recv(MESSAGE_BUFFER_SIZE):
                    break  # the client closed its end after reading the reject
        except Exception:
            pass  # best effort - the connection is being dropped anyway
        finally:
            try:
                client_socket.close()
            except OSError:
                pass

    def _get_next_player_index(self) -> Optional[int]:
        """
        Get the next available player index (1, 2, or 3).

        Skips slots that are:
        - Already occupied by a client
        - Reserved for AI players
        """
        with self._clients_lock:
            for i in range(1, MAX_CLIENTS + 1):
                if i not in self.clients and i not in self.reserved_slots:
                    return i
        return None

    def reserve_slot(self, slot_idx: int) -> None:
        """
        Reserve a slot for AI (prevents human clients from joining that slot).

        Called by TerritorySelector when host configures a slot as AI.

        Args:
            slot_idx: The slot index to reserve (1, 2, or 3)
        """
        if 1 <= slot_idx <= MAX_CLIENTS:
            self.reserved_slots.add(slot_idx)
            logger.debug(f"Reserved slot {slot_idx} for AI")

    def unreserve_slot(self, slot_idx: int) -> None:
        """
        Unreserve a slot (allows human clients to join that slot).

        Called by TerritorySelector when host changes a slot from AI to empty.

        Args:
            slot_idx: The slot index to unreserve (1, 2, or 3)
        """
        self.reserved_slots.discard(slot_idx)
        logger.debug(f"Unreserved slot {slot_idx}")

    def _receive_from_client_socket(self, sock: socket.socket):
        """Receive data from a specific client socket"""
        # Find client by socket
        client = None
        player_index = None
        with self._clients_lock:
            for idx, c in self.clients.items():
                if c.socket == sock:
                    client = c
                    player_index = idx
                    break

        if not client:
            return

        try:
            data = sock.recv(MESSAGE_BUFFER_SIZE)

            if not data:
                # Connection closed
                logger.info(f"Player {player_index + 1} disconnected")
                self._disconnect_client(player_index)
                return

            # H13 fix: check buffer overflow return value and disconnect on overflow
            if not client.recv_buffer.add_data(data):
                logger.warning(f"Buffer overflow for Player {player_index + 1}, disconnecting")
                self._disconnect_client(player_index)
                return

            # Extract and process complete messages
            while True:
                message_bytes = client.recv_buffer.extract_message()
                if not message_bytes:
                    break

                # Decode message
                message = self.protocol.decode_message(message_bytes)
                if message:
                    self._handle_received_message(message, player_index, message_bytes)

        except (BlockingIOError, socket.timeout):
            # No data available (select() said readable, but nothing came after all)
            pass
        except ConnectionResetError:
            logger.warning(f"Connection reset by Player {player_index + 1}")
            self._disconnect_client(player_index)
        except Exception as e:
            logger.error(f"Receive error from Player {player_index + 1}: {e}")
            self._disconnect_client(player_index)

    def _send_to_clients(self):
        """Send queued messages to all clients"""
        # Get all queued messages
        while self.message_queue.has_outgoing_messages():
            message = self.message_queue.get_outgoing_message(timeout=0)
            if not message:
                break

            # Broadcast to all connected clients
            self._broadcast_raw(message)

    def _broadcast_raw(self, message: bytes, exclude: Optional[int] = None):
        """Send raw message bytes to all connected clients except excluded player"""
        with self._clients_lock:
            for player_index, client in list(self.clients.items()):
                if player_index == exclude:
                    continue
                if not client.connected:
                    continue
                try:
                    client.socket.sendall(message)
                except Exception as e:
                    logger.error(f"Send error to Player {player_index + 1}: {e}")
                    # Mark for disconnection (don't modify dict while iterating)
                    client.connected = False

        # Clean up disconnected clients
        self._cleanup_disconnected()

    def _relay_to_other_clients(self, raw_bytes: bytes, from_player_index: int):
        """Relay raw message bytes to all clients except the sender.

        Used for 3+ player games so client actions are visible to other clients.
        The host receives the message separately via message_queue.
        """
        with self._clients_lock:
            for player_index, client in list(self.clients.items()):
                if player_index == from_player_index:
                    continue  # Don't echo back to sender
                if not client.connected:
                    continue
                try:
                    client.socket.sendall(raw_bytes)
                except Exception as e:
                    logger.error(f"Relay error to Player {player_index + 1}: {e}")
                    client.connected = False

        self._cleanup_disconnected()

    def _cleanup_disconnected(self):
        """Drop clients whose socket failed (marked connected=False by a send error).

        Goes through _disconnect_client() so the drop is announced like any other
        disconnect - LOBBY_LEAVE in the lobby, PLAYER_DISCONNECT in game, to the other
        clients and to the host. These used to be removed silently: a ghost slot in the
        lobby, or a player in game whose seat nobody took over.
        """
        with self._clients_lock:
            dead = [idx for idx, c in self.clients.items() if not c.connected]
        for idx in dead:
            # A nested cleanup (from the leave broadcast) may already have removed it;
            # _disconnect_client() is a no-op then
            self._disconnect_client(idx, "Connection lost")

        # Update connection state
        with self._clients_lock:
            if not self.clients:
                self.message_queue.set_connected(False)

    def _handle_received_message(self, message: dict, from_player_index: int,
                                 raw_bytes: bytes = None):
        """
        Handle a received message from a client.

        Args:
            message: Decoded message dict
            from_player_index: Player index who sent the message
            raw_bytes: Original encoded message bytes for relay to other clients
        """
        # Phase 6A: Validate message schema before processing
        # Ensures message has required fields (type, seq, data) and known type
        if not self.protocol.validate_message(message):
            logger.warning(f"Received invalid message from player {from_player_index}, "
                           f"ignoring")
            return

        # Security (H3): Validate data fields (ranges, types, lengths)
        if not self.protocol.validate_message_data(message):
            logger.warning(f"Message data validation failed from player "
                           f"{from_player_index}, ignoring")
            return

        msg_type = message.get('type')

        if msg_type in _HOST_ONLY_TYPES:
            logger.warning(f"Dropped host-only {msg_type} sent by player {from_player_index}")
            return

        # Security (H1): Sequence number validation to prevent replay attacks.
        # Reject messages with seq <= the last seq accepted on this connection.
        # Exempt types (PONG, DISCONNECT) are neither checked nor counted - see
        # _SEQ_EXEMPT_TYPES for why checking them dropped real game messages.
        msg_seq = message.get('seq')
        if isinstance(msg_seq, int) and msg_type not in _SEQ_EXEMPT_TYPES:
            with self._clients_lock:
                connection = self.clients.get(from_player_index)
                if connection is not None:
                    if msg_seq <= connection.last_seq:
                        logger.warning(f"Replay/duplicate detected from player "
                                       f"{from_player_index}: seq {msg_seq} <= "
                                       f"{connection.last_seq} (msg_type={msg_type})")
                        return
                    connection.last_seq = msg_seq

        # 3+ player relay: forward gameplay messages to other clients so they
        # can see each other's actions in real-time. The host still receives
        # the message via message_queue below. The sender is excluded.
        if raw_bytes is not None and msg_type in _RELAY_MESSAGE_TYPES:
            self._relay_to_other_clients(raw_bytes, from_player_index)

        # Handle connection messages
        if msg_type == MessageType.CONNECT_REQUEST:
            self._handle_connect_request(message, from_player_index)
        elif msg_type == MessageType.PONG:
            # Update last pong time for this client
            with self._clients_lock:
                if from_player_index in self.clients:
                    client = self.clients[from_player_index]
                    current_time = time.monotonic()
                    client.last_pong_time = current_time
        elif msg_type == MessageType.DISCONNECT:
            logger.info(f"Player {from_player_index + 1} disconnected gracefully")
            self._disconnect_client(from_player_index, "Player disconnected")
        elif msg_type == MessageType.RECONNECT_REQUEST:
            self._handle_reconnect_request(message, from_player_index)
        else:
            # Add player_index to message for game loop to know who sent it
            message['from_player_index'] = from_player_index
            # Forward to game loop
            logger.debug(f"[SERVER] Forwarding {msg_type} from player {from_player_index} to game loop (seq={msg_seq})")
            self.message_queue.receive_message(message)

    @staticmethod
    def _sanitize_player_name(name: str, fallback: str = "Player") -> str:
        """Sanitize player name: strip control chars, limit length, ensure non-empty.

        Security: prevents null bytes, control characters, and oversized names
        that could cause display/logging issues or downstream crashes.
        """
        import unicodedata
        if not isinstance(name, str):
            return fallback
        # Strip control characters (Unicode category C) and null bytes
        name = ''.join(
            ch for ch in name
            if unicodedata.category(ch)[0] != 'C'
        )
        # Truncate and strip whitespace
        name = name[:32].strip()
        return name if name else fallback

    def _handle_connect_request(self, message: dict, player_index: int):
        """Handle connection request from client"""
        data = message.get('data', {})
        client_version = data.get('version')
        # Security: sanitize player name (strip control chars, limit length)
        player_name = self._sanitize_player_name(
            data.get('player_name', ''),
            fallback=f"Player {player_index + 1}"
        )

        # Check version compatibility
        from network_config import NETWORK_VERSION
        if client_version != NETWORK_VERSION:
            # Version mismatch - reject
            with self._clients_lock:
                if player_index in self.clients:
                    reject_msg = self.protocol.create_connect_reject(
                        f"Version mismatch: server={NETWORK_VERSION}, client={client_version}"
                    )
                    try:
                        self.clients[player_index].socket.sendall(reject_msg)
                    except (OSError, BrokenPipeError):
                        pass  # C3 fix: Client may disconnect before receiving rejection
            self._disconnect_client(player_index)
            return

        # Generate reconnection password (16 chars for stronger entropy)
        password = secrets.token_urlsafe(16)[:16]
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Update client info
        with self._clients_lock:
            if player_index in self.clients:
                self.clients[player_index].player_name = player_name
                self.clients[player_index].password_hash = password_hash

        # Accept connection with player_index and password
        accept_msg = self.protocol.create_connect_accept(
            player_index=player_index,
            reconnect_password=password  # Send plain password to client
        )

        with self._clients_lock:
            if player_index in self.clients:
                try:
                    self.clients[player_index].socket.sendall(accept_msg)
                except Exception as e:
                    logger.error(f"Failed to send accept to Player {player_index + 1}: {e}")
                    self._disconnect_client(player_index)
                    return

        logger.info(f"Connection accepted: Player {player_index + 1} ({player_name}, version {client_version})")

        # Notify host (game loop) that a player joined so TerritorySelector can update
        self.message_queue.receive_message({
            'type': MessageType.LOBBY_JOIN,
            'data': {'player_index': player_index, 'player_name': player_name}
        })

        # Notify other clients that a new player joined
        join_msg = self.protocol.encode_message(MessageType.LOBBY_JOIN, {
            'player_index': player_index,
            'player_name': player_name
        })
        self._broadcast_raw(join_msg, exclude=player_index)

    def _handle_reconnect_request(self, message: dict, from_socket_player_index: int):
        """
        Handle reconnection request from client.

        Finds matching disconnected player by name and verifies password.
        If valid, restores the player to their original slot.
        """
        if not RECONNECT_ENABLED:
            # Rejoining a running game is switched off for launch (network_config):
            # refuse cleanly instead of half-restoring a seat the game cannot hand back
            with self._clients_lock:
                if from_socket_player_index in self.clients:
                    try:
                        reject_msg = self.protocol.encode_message(
                            MessageType.RECONNECT_REJECT,
                            {'reason': 'Rejoining a game in progress is not supported'})
                        self.clients[from_socket_player_index].socket.sendall(reject_msg)
                    except Exception:
                        pass
            return

        data = message.get('data', {})
        player_name = data.get('player_name', '')
        password = data.get('password', '')
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Security (H2): Rate-limit reconnection attempts to prevent brute-force
        client_ip = None
        with self._clients_lock:
            if from_socket_player_index in self.clients:
                sock = self.clients[from_socket_player_index].socket
                try:
                    client_ip = sock.getpeername()[0]
                except Exception:
                    pass
        if client_ip:
            now = time.monotonic()
            attempts = self._reconnect_attempts.get(client_ip, [])
            attempts = [t for t in attempts if now - t < self._reconnect_rate_limit_window]
            if len(attempts) >= self._reconnect_rate_limit_max:
                logger.warning(f"Reconnect rate limited for {client_ip} "
                               f"({len(attempts)} attempts in "
                               f"{self._reconnect_rate_limit_window}s)")
                with self._clients_lock:
                    if from_socket_player_index in self.clients:
                        try:
                            reject_msg = self.protocol.encode_message(
                                MessageType.RECONNECT_REJECT,
                                {'reason': 'Too many reconnection attempts'})
                            self.clients[from_socket_player_index].socket.sendall(reject_msg)
                        except Exception:
                            pass
                return
            attempts.append(now)
            self._reconnect_attempts[client_ip] = attempts

        # Clean up expired reconnection entries
        self._cleanup_expired_reconnects()

        # Find disconnected player with matching name and password
        matching_player = None
        original_player_index = None

        with self._clients_lock:
            for idx, disconnected in self.disconnected_players.items():
                # Security: use hmac.compare_digest for constant-time comparison
                # to prevent timing attacks on password hash
                if (disconnected.player_name.lower() == player_name.lower() and
                    hmac.compare_digest(disconnected.password_hash, password_hash)):
                    matching_player = disconnected
                    original_player_index = idx
                    break

        if matching_player is None:
            # No match found - reject
            with self._clients_lock:
                if from_socket_player_index in self.clients:
                    reject_msg = self.protocol.encode_message(MessageType.RECONNECT_REJECT, {
                        'reason': 'Invalid name or password'
                    })
                    try:
                        self.clients[from_socket_player_index].socket.sendall(reject_msg)
                    except (OSError, BrokenPipeError):
                        pass  # C3 fix: Client may disconnect before receiving rejection
            return

        # Valid reconnection - reassign the socket to the original player index
        with self._clients_lock:
            # Get the current connection (temporary slot)
            if from_socket_player_index not in self.clients:
                return

            old_client = self.clients[from_socket_player_index]

            # Create new client connection with original player index
            new_client = ClientConnection(
                socket=old_client.socket,
                address=old_client.address,
                player_index=original_player_index,
                player_name=matching_player.player_name,
                password_hash=matching_player.password_hash,
                recv_buffer=old_client.recv_buffer,
                last_pong_time=time.monotonic()
            )

            # Remove from temporary slot and add to original slot
            del self.clients[from_socket_player_index]
            self.clients[original_player_index] = new_client

            # Remove from disconnected list
            del self.disconnected_players[original_player_index]

        logger.info(f"Player {original_player_index + 1} ({player_name}) reconnected successfully")

        # Send reconnection accept with game state
        # The game loop will provide the full state via the message queue
        accept_msg = self.protocol.encode_message(MessageType.RECONNECT_ACCEPT, {
            'player_index': original_player_index,
            'game_state': {}  # Game loop will send full state sync
        })

        with self._clients_lock:
            if original_player_index in self.clients:
                try:
                    self.clients[original_player_index].socket.sendall(accept_msg)
                except Exception as e:
                    logger.error(f"Failed to send reconnect accept: {e}")
                    return

        # Notify game loop about reconnection
        self.message_queue.receive_message({
            'type': MessageType.RECONNECT_ACCEPT,
            'data': {'player_index': original_player_index}
        })

        # Notify other clients that player reconnected
        reconnect_msg = self.protocol.encode_message(MessageType.LOBBY_JOIN, {
            'player_index': original_player_index,
            'player_name': player_name,
            'reconnected': True
        })
        self._broadcast_raw(reconnect_msg, exclude=original_player_index)

    def _cleanup_expired_reconnects(self):
        """Remove expired reconnection entries and trigger disconnect elimination."""
        current_time = time.monotonic()
        expired = []

        with self._clients_lock:
            for idx, disconnected in self.disconnected_players.items():
                if current_time - disconnected.disconnect_time > self.reconnect_timeout:
                    expired.append(idx)

            for idx in expired:
                logger.warning(f"Reconnection timeout for Player {idx + 1} — triggering disconnect elimination")
                del self.disconnected_players[idx]

        # Broadcast DISCONNECT_ELIMINATION for each expired player (outside lock)
        # Both clients and host game loop process this to eliminate the player
        for idx in expired:
            elim_msg = self.protocol.encode_message(MessageType.DISCONNECT_ELIMINATION, {
                'player_index': idx
            })
            self._broadcast_raw(elim_msg)
            # Also notify host game loop via message queue
            self.message_queue.receive_message({
                'type': MessageType.DISCONNECT_ELIMINATION,
                'data': {'player_index': idx}
            })

    def _send_heartbeat(self):
        """Send heartbeat PING to all clients"""
        current_time = time.monotonic()

        # Send PING every HEARTBEAT_INTERVAL seconds
        if current_time - self.last_ping_time >= HEARTBEAT_INTERVAL:
            ping_msg = self.protocol.create_ping()

            with self._clients_lock:
                for player_index, client in self.clients.items():
                    if not client.connected:
                        continue
                    try:
                        client.socket.sendall(ping_msg)
                        client.ping_sent_time = current_time
                    except (OSError, BrokenPipeError, ConnectionResetError, AttributeError):
                        # Mark for cleanup
                        client.connected = False

            self.last_ping_time = current_time

        self._cleanup_disconnected()

    def _check_timeouts(self):
        """Check for connection timeouts using monotonic clock"""
        current_time = time.monotonic()

        # Collect timed-out players (don't call _disconnect_client while holding lock)
        timed_out = []

        with self._clients_lock:
            for player_index, client in list(self.clients.items()):
                if not client.connected:
                    continue
                # Check if we've received PONG recently
                if current_time - client.last_pong_time > CONNECTION_TIMEOUT:
                    logger.warning(f"Player {player_index + 1} connection timeout")
                    timed_out.append(player_index)

        # Handle disconnections outside the lock (proper AI takeover, reconnection support)
        # Note: _disconnect_client will only set self.disconnected when ALL clients are gone
        for player_index in timed_out:
            self._disconnect_client(player_index, f"Player {player_index + 1} timeout")

        # Check for expired reconnection entries (triggers DISCONNECT_ELIMINATION)
        self._cleanup_expired_reconnects()

        # R10: Periodically prune stale rate limit entries to prevent memory leak
        if current_time - self._last_rate_limit_cleanup > 60.0:
            self._last_rate_limit_cleanup = current_time
            stale_ips = [ip for ip, attempts in self._connection_attempts.items()
                         if not attempts or current_time - attempts[-1] > self._rate_limit_window]
            for ip in stale_ips:
                del self._connection_attempts[ip]

    def _disconnect_client(self, player_index: int, reason: str = "", allow_reconnect: bool = True):
        """
        Disconnect a specific client.

        The socket close is performed OUTSIDE the lock to avoid holding
        the lock during a potentially blocking I/O operation.

        Args:
            player_index: Player index to disconnect
            reason: Reason for disconnection
            allow_reconnect: If True and game started, player can reconnect
        """
        leave_msg = None
        host_notice = None
        player_name = ""
        socket_to_close = None  # Collect socket ref to close outside lock

        with self._clients_lock:
            client = self.clients.pop(player_index, None)
            if client is not None:
                client.connected = False
                player_name = client.player_name

                if self.game_started:
                    # In game: the player's seat is handed to the AI. Reconnecting is
                    # switched off for launch (RECONNECT_ENABLED), so normally no
                    # reconnect entry is kept - and so no DISCONNECT_ELIMINATION later.
                    if RECONNECT_ENABLED and allow_reconnect and client.password_hash:
                        self.disconnected_players[player_index] = DisconnectedPlayer(
                            player_index=player_index,
                            player_name=client.player_name,
                            password_hash=client.password_hash,
                            disconnect_time=time.monotonic()
                        )
                        logger.info(f"Player {player_index + 1} ({player_name}) saved for reconnection")
                    notice = {'player_index': player_index, 'ai_takeover': True}
                    leave_msg = self.protocol.encode_message(MessageType.PLAYER_DISCONNECT, notice)
                    host_notice = {'type': MessageType.PLAYER_DISCONNECT, 'data': notice}
                else:
                    # Lobby phase - player just leaves. The host's lobby must hear it too:
                    # it used to go to the other clients only, so the host kept a ghost
                    # player, launched with them and hung on the loading screen.
                    notice = {'player_index': player_index, 'reason': reason}
                    leave_msg = self.protocol.encode_message(MessageType.LOBBY_LEAVE, notice)
                    host_notice = {'type': MessageType.LOBBY_LEAVE, 'data': notice}

                # Save socket reference for closing outside the lock
                socket_to_close = client.socket
                logger.info(f"Player {player_index + 1} disconnected: {reason}")

        # Close the socket OUTSIDE the lock to avoid holding _clients_lock
        # during a potentially blocking I/O operation
        if socket_to_close:
            try:
                socket_to_close.close()
            except OSError:
                pass

        # Tell the host's game loop / lobby first (in game: AI takeover), then the other
        # clients. Only when a client was actually removed - calling this twice for the
        # same player must not announce the disconnect twice.
        if host_notice:
            self.message_queue.receive_message(host_notice)
        if leave_msg:
            self._broadcast_raw(leave_msg)

        # Update connection state
        # Note: We do NOT set self.disconnected = True when clients disconnect
        # Host continues playing with AI taking over disconnected players
        # The disconnected flag is only for clients to detect host disconnect
        with self._clients_lock:
            if not self.clients:
                self.message_queue.set_connected(False)
                # Don't end the game - AI takes over disconnected players
                logger.info("All clients disconnected - AI will control their slots")

    # --- Public API ---

    def send_message(self, message: bytes):
        """
        Queue a message to broadcast to all clients.

        Args:
            message: Encoded message bytes

        Called by game loop to send messages.
        """
        self.message_queue.send_message(message)

    def broadcast_message(self, message: bytes, exclude: Optional[int] = None):
        """
        Broadcast a message to all connected clients.

        Args:
            message: Encoded message bytes
            exclude: Player index to exclude from broadcast (optional)
        """
        self._broadcast_raw(message, exclude)

    def send_to_player(self, player_index: int, message: bytes):
        """
        Send a message to a specific player.

        Args:
            player_index: Target player index
            message: Encoded message bytes
        """
        with self._clients_lock:
            if player_index in self.clients and self.clients[player_index].connected:
                try:
                    self.clients[player_index].socket.sendall(message)
                except Exception as e:
                    logger.error(f"Failed to send to Player {player_index + 1}: {e}")
                    self.clients[player_index].connected = False

        self._cleanup_disconnected()

    def kick_player(self, player_index: int, reason: str = "Kicked by host"):
        """
        Kick a player from the game.

        Args:
            player_index: Player index to kick
            reason: Reason for kick
        """
        with self._clients_lock:
            if player_index in self.clients:
                # Send kick message before disconnecting
                kick_msg = self.protocol.encode_message(MessageType.LOBBY_KICK, {
                    'player_index': player_index,
                    'reason': reason
                })
                try:
                    self.clients[player_index].socket.sendall(kick_msg)
                except (OSError, BrokenPipeError):
                    pass  # C3 fix: Client may already be disconnected

        # Give client time to receive and process the kick message before disconnecting
        time.sleep(0.2)

        # Don't allow reconnection for kicked players (lobby phase)
        self._disconnect_client(player_index, reason, allow_reconnect=False)

    def is_client_connected(self) -> bool:
        """
        Check if at least one client is connected.

        Returns:
            True if any client is connected

        Note: For backward compatibility with 1v1 code.
        """
        with self._clients_lock:
            return len(self.clients) > 0

    def get_connected_count(self) -> int:
        """
        Get the number of connected clients.

        Returns:
            Number of connected clients (0-3)
        """
        with self._clients_lock:
            return len(self.clients)

    def get_connected_players(self) -> List[int]:
        """
        Get list of connected player indices.

        Returns:
            List of player indices (1, 2, 3)
        """
        with self._clients_lock:
            return list(self.clients.keys())

    def get_player_name(self, player_index: int) -> str:
        """
        Get a player's name.

        Args:
            player_index: Player index

        Returns:
            Player name or empty string if not found
        """
        with self._clients_lock:
            if player_index in self.clients:
                return self.clients[player_index].player_name
        return ""

    def get_local_ip(self) -> str:
        """
        Get local IP address for LAN connections.

        Returns:
            Local IP address string
        """
        try:
            # Create a socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Google DNS (doesn't actually send data)
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except OSError:
            # Network unreachable or other socket error - fall back to localhost
            return "127.0.0.1"

    def setup_upnp(self) -> None:
        """
        Start UPnP port forwarding in background thread.
        Call after start() succeeds. Non-blocking — UI polls for status.
        """
        from network.upnp import UPnPManager
        local_ip = self.get_local_ip()
        self.upnp_manager = UPnPManager()
        self.upnp_manager.setup_async(self.port, local_ip)
        logger.info(f"UPnP setup started for port {self.port}")

    def get_display_ip(self) -> str:
        """Get best IP to show user (public if UPnP succeeded, else local)."""
        local_ip = self.get_local_ip()
        if self.upnp_manager:
            return self.upnp_manager.get_display_ip(local_ip)
        return local_ip

    def get_upnp_status_text(self) -> str:
        """Get UPnP status text for UI display."""
        if self.upnp_manager:
            return self.upnp_manager.get_status_text()
        return ""

    def is_upnp_complete(self) -> bool:
        """Check if UPnP setup has finished (success or failure)."""
        if self.upnp_manager:
            return self.upnp_manager.is_complete()
        return True

    def set_game_started(self, started: bool = True):
        """
        Mark the game as started (called by the lobby at launch). From then on a client
        that drops is reported as PLAYER_DISCONNECT (the host hands the seat to the AI)
        instead of a lobby leave. It was never called before, so in-game disconnects
        were handled as lobby leaves the game ignored.

        Args:
            started: Whether the game has started
        """
        self.game_started = started
        if started:
            logger.info("Game started - disconnects are now in-game disconnects "
                        f"(reconnect {'enabled' if RECONNECT_ENABLED else 'disabled'})")

    def is_player_disconnected(self, player_index: int) -> bool:
        """
        Check if a player is in the reconnectable disconnected state.

        Args:
            player_index: Player index to check

        Returns:
            True if player is disconnected but can reconnect
        """
        with self._clients_lock:
            return player_index in self.disconnected_players

    def get_disconnected_players(self) -> List[int]:
        """
        Get list of player indices who are disconnected but can reconnect.

        Returns:
            List of player indices
        """
        self._cleanup_expired_reconnects()
        with self._clients_lock:
            return list(self.disconnected_players.keys())
