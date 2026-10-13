"""
Network client implementation for multiplayer client.

Client player uses this to connect to a host server.
"""

import ipaddress
import select
import socket
import threading
import time
from collections import namedtuple
from typing import Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network_config import (
    DEFAULT_PORT, MESSAGE_BUFFER_SIZE, HEARTBEAT_INTERVAL,
    CONNECTION_TIMEOUT, SEND_TIMEOUT, MessageType
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

# recv() calls per network-loop iteration while data keeps arriving (the loop sleeps
# 10 ms between iterations; one read per iteration made big messages crawl in)
_MAX_READS_PER_LOOP = 16

# Time allowed for the farewell DISCONNECT when we leave on purpose
_FAREWELL_SEND_TIMEOUT = 1.0  # seconds


# Joining through Steam: time for Steam to reach the host (its own limit is 15 s) and for
# the host to answer our CONNECT_REQUEST
STEAM_CONNECT_TIMEOUT = 20.0  # seconds

# Connect-string token of a host reached through Steam's relay: "steam-<SteamID64>".
# No colon on purpose: older builds read "steam:<id>" as host "steam" + a huge port and
# crashed (OverflowError); "steam-<id>" is just an unknown host name to them.
STEAM_TARGET_PREFIX = "steam-"


class SteamTarget(namedtuple('SteamTarget', ['steam_id'])):
    """A host to join through Steam's relay network (connect token "steam-<SteamID64>")."""

    def __str__(self):
        return f"{STEAM_TARGET_PREFIX}{self.steam_id}"


def target_label(target) -> str:
    """A connect target for logs and messages: "steam-<id>" or "host:port"."""
    if isinstance(target, SteamTarget):
        return str(target)
    return f"{target[0]}:{target[1]}"


def format_connect_targets(hosts, port: int = DEFAULT_PORT, steam_id: int = 0) -> str:
    """
    The address part of a Steam invite: "steam-<id>,ip1:port,ip2:port" (no spaces, so
    Steam keeps it one launch argument). The Steam target comes first - it works on any
    network; the addresses are the fallback. parse_connect_targets() reads it back.
    """
    parts = [f"{STEAM_TARGET_PREFIX}{steam_id}"] if steam_id else []
    parts += [f"{host}:{port}" for host in hosts if host]
    return ",".join(parts)


def _parse_steam_target(part: str):
    """SteamTarget for a "steam-<SteamID64>" token, else None."""
    if not part.lower().startswith(STEAM_TARGET_PREFIX):
        return None
    digits = part[len(STEAM_TARGET_PREFIX):].strip()
    if not digits.isdigit():
        return None
    steam_id = int(digits)
    return SteamTarget(steam_id) if 0 < steam_id < 2 ** 64 else None


def parse_connect_targets(text: str):
    """
    Read the target list of a "+connect" launch argument: "ip:port", "steam-<id>", or
    several comma-separated (Steam invites carry the host's SteamID, LAN and public
    address). A missing, broken or out-of-range port means DEFAULT_PORT.

    Returns:
        [SteamTarget(id) or (host, port), ...] in the given order, duplicates dropped.
        Tell them apart with isinstance(target, SteamTarget); a (host, port) is a plain
        tuple, as before.
    """
    targets = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        steam_target = _parse_steam_target(part)
        if steam_target is not None:
            if steam_target not in targets:
                targets.append(steam_target)
            continue
        host, port = part, DEFAULT_PORT
        if ":" in part:
            host, port_str = part.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = DEFAULT_PORT
            if not 1 <= port <= 65535:
                port = DEFAULT_PORT  # a huge port crashed socket.connect (OverflowError)
        host = host.strip()
        if host and (host, port) not in targets:
            targets.append((host, port))
    return targets


def unreachable_reason(host: str) -> str:
    """
    What to tell the player when the host's PC never answered (connect timed out).

    A home-network address (192.168.x.x, 10.x.x.x, ...) that does not answer means the
    two PCs cannot see each other on that network; a public address that does not
    answer usually means the host's router does not forward the game port.
    """
    try:
        is_private = ipaddress.ip_address(host).is_private
    except ValueError:
        is_private = False  # a host name - treat like an internet address
    if is_private:
        return (f"Could not reach {host} on your home network - check that both PCs are "
                f"on the same network (not a guest Wi-Fi), that the router does not keep "
                f"Wi-Fi devices apart, and that no VPN is on")
    return (f"Could not reach {host} - the host's router must forward TCP port "
            f"{DEFAULT_PORT} to the host's PC, and the host's firewall must allow the game")


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
        self._host_answered = False  # Last connect() reached a host (see connect_any)

        # Joining through Steam (connect_steam): the bridge (None = the game's; tests set
        # their own) and the current join, whose reason beats our "Host disconnected"
        self.steam_bridge = None
        self._steam_join = None

        # Joining in the background (multiplayer_setup.connect_with_progress): the target
        # being tried now (what the "Connecting..." screen shows) and the player's Cancel.
        # A cancelled client is not reused - make a new one for the next attempt.
        self.current_target = None
        self._cancel_connect = threading.Event()

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

    def connect(self, host: str, port: int = DEFAULT_PORT, player_name: str = "Player",
                accept_timeout: float = 5.0, _steam_join=None) -> bool:
        """
        Connect to a host server.

        Args:
            host: Host IP address or hostname
            port: Port number
            player_name: Player name to send in connection request
            accept_timeout: seconds to wait for the host's answer once connected
                (connect_steam() waits longer: Steam may still be finding the host)
            _steam_join: connect_steam()'s join (its reason replaces ours if the link drops)

        Returns:
            True if connection successful, False otherwise
        """
        # A fresh attempt: forget why the previous connection ended
        with self._state_lock:
            self.disconnected = False
        self.disconnect_reason = ""
        # Whether a game host took the TCP connection (connect_any() stops trying other
        # addresses once one reached the host, even if it then refused us)
        self._host_answered = False
        self._steam_join = _steam_join
        if self._cancel_connect.is_set():
            self.disconnect_reason = "Cancelled"
            return False

        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5 second timeout for connect

            # Connect to server
            logger.info(f"Connecting to {host}:{port}...")
            self.socket.connect((host, port))
            self._host_answered = True

            # Blocking sends with a time limit (SEND_TIMEOUT). A non-blocking sendall()
            # fails mid-frame when the kernel buffer fills (large messages); reads stay
            # non-blocking in effect because recv() only runs after select() (see
            # _receive_from_server).
            self.socket.settimeout(SEND_TIMEOUT)

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
            timeout = accept_timeout
            # C6: Use monotonic clock -- immune to NTP sync / daylight saving shifts
            start_time = time.monotonic()
            while self.player_index is None:
                if self.disconnected:
                    # The host refused us (CONNECT_REJECT: lobby full, version mismatch,
                    # ...) or the link died. Stop waiting at once; disconnect_reason
                    # survives disconnect() so the join screen can show it.
                    logger.warning(f"Connection refused: {self.disconnect_reason}")
                    self.disconnect()
                    return False
                if self._cancel_connect.is_set():
                    # The player pressed Cancel on the "Connecting..." screen
                    logger.info(f"Connecting to {host}:{port} cancelled")
                    self.disconnect()
                    self.disconnect_reason = "Cancelled"
                    return False
                if time.monotonic() - start_time > timeout:
                    logger.warning("Connection timeout - no response from server")
                    self.disconnect_reason = "The host did not answer"
                    self.disconnect()
                    return False
                time.sleep(0.1)

            # Update message queue state
            self.message_queue.set_connected(True)

            logger.info(f"Connection accepted - assigned as Player {self.player_index + 1}")
            return True

        except socket.timeout:
            logger.warning(f"Connection to {host}:{port} timed out")
            # Say what to check - "check the address and the host's firewall" sent
            # players hunting the firewall when the two PCs could not see each other
            self.disconnect_reason = unreachable_reason(host)
            self.disconnect()
            return False
        except ConnectionRefusedError:
            logger.warning("Connection refused - server not available")
            self.disconnect_reason = "No game is being hosted at that address"
            self.disconnect()
            return False
        except OSError as e:
            logger.error(f"Connection error: {e}")
            self.disconnect_reason = f"Connection error: {e}"
            self.disconnect()
            return False
        except (OverflowError, ValueError) as e:
            # A broken address (port out of range, ...) - say so instead of crashing
            logger.error(f"Invalid address {host}:{port}: {e}")
            self.disconnect_reason = f"Not a valid address: {host}:{port}"
            self.disconnect()
            return False

    def connect_steam(self, steam_id: int, player_name: str = "Player",
                      timeout: float = STEAM_CONNECT_TIMEOUT) -> bool:
        """
        Join a host through Steam's relay network (network/steam_bridge.py): no port
        forwarding, works where the two PCs cannot reach each other directly.

        The bridge gives us a 127.0.0.1 port that leads to the host over Steam, so the
        rest is an ordinary connect(). Failure reasons name Steam and the host, never
        the 127.0.0.1 address.

        Args:
            steam_id: the host's SteamID64
            player_name: Player name to send in connection request
            timeout: seconds for Steam to reach the host plus the host's answer

        Returns:
            True if connected; otherwise disconnect_reason says why
        """
        from network.steam_bridge import SteamJoinError
        with self._state_lock:
            self.disconnected = False
        self._host_answered = False
        if self._cancel_connect.is_set():
            self.disconnect_reason = "Cancelled"
            return False
        bridge = self._get_steam_bridge()
        try:
            join = bridge.open_join(steam_id)
        except SteamJoinError as e:
            logger.warning(f"Cannot join steam-{steam_id} through Steam: {e}")
            self.disconnect_reason = str(e)
            return False

        if self.connect('127.0.0.1', port=join.local_port, player_name=player_name,
                        accept_timeout=timeout, _steam_join=join):
            logger.info(f"Joined steam-{steam_id} through Steam")
            return True

        # Failed. Whose reason counts: the host's refusal ("Lobby is full") if Steam got
        # through, otherwise Steam's - unless the player cancelled
        host_reason = self.disconnect_reason
        join.close()
        if self._cancel_connect.is_set():
            self.disconnect_reason = "Cancelled"
            return False
        steam_reason = join.failure_reason()
        self._host_answered = join.reached_host
        if not join.reached_host:
            self.disconnect_reason = (steam_reason or
                                      f"Could not reach {join.host_name or 'the host'} through Steam")
        elif steam_reason and (not host_reason or self._is_link_reason(host_reason)):
            self.disconnect_reason = steam_reason
        logger.warning(f"Joining steam-{steam_id} failed: {self.disconnect_reason}")
        return False

    def _get_steam_bridge(self):
        if self.steam_bridge is not None:
            return self.steam_bridge
        from network.steam_bridge import steam_bridge
        return steam_bridge

    def cancel_connect(self):
        """
        The player gave up on joining (Cancel / Esc on the "Connecting..." screen; any
        thread). The connect running on the worker thread returns False with reason
        "Cancelled": at once while it waits for the host's answer or for Steam, after
        the current attempt for an address that is still being reached (at most 5 s).
        """
        if not self._cancel_connect.is_set():
            logger.info("Joining cancelled by the player")
        self._cancel_connect.set()

    @property
    def connect_cancelled(self) -> bool:
        return self._cancel_connect.is_set()

    @staticmethod
    def _is_link_reason(reason: str) -> bool:
        """
        A reason that only says the connection to our end dropped. Through Steam that
        connection is the local bridge, so the bridge's own reason says more.
        """
        return reason in ("Host disconnected", "Connection timeout", "The host did not answer") \
            or reason.startswith("Connection error")

    def connect_any(self, targets, player_name: str = "Player") -> bool:
        """
        Connect to the first host address that answers (Steam invites carry several:
        the host's LAN address and its public one - which one works depends on where
        the joining PC is).

        Stops early when a host turned us away (CONNECT_REJECT: lobby full, version
        mismatch, ...) - we reached the host, another address would reach the same one.

        Args:
            targets: [SteamTarget or (host, port), ...] in the order to try (from
                parse_connect_targets: the Steam target first - it works on any network)
            player_name: Player name to send in connection request

        Returns:
            True if connected; otherwise disconnect_reason holds the most useful reason
            (a host's refusal, else Steam's reason, else the addresses' failure)
        """
        steam_failures = []  # reasons of Steam attempts that did not reach the host
        failed = []          # (host, reason) of every address that did not answer
        for target in targets:
            if self._cancel_connect.is_set():
                self.disconnect_reason = "Cancelled"
                return False
            self.current_target = target    # shown by the "Connecting..." screen
            if isinstance(target, SteamTarget):
                connected = self.connect_steam(target.steam_id, player_name=player_name)
            else:
                connected = self.connect(target[0], port=target[1], player_name=player_name)
            if connected:
                return True
            if self._host_answered:
                return False  # the host refused us - its reason is the one to show
            if isinstance(target, SteamTarget):
                steam_failures.append(self.disconnect_reason)
                logger.info(f"Could not reach {target} through Steam, trying the next address")
            else:
                failed.append((target[0], self.disconnect_reason))
                logger.info(f"Could not reach {target_label(target)}, trying the next address")

        if self._cancel_connect.is_set():
            self.disconnect_reason = "Cancelled"
            return False
        if not failed and not steam_failures:
            self.disconnect_reason = "No address to connect to"
            return False
        if len(failed) == 1:
            address_reason = failed[0][1]
        elif failed:
            # Which address should have worked depends on where this PC is - cover both
            hosts = " or ".join(host for host, _ in failed)
            address_reason = (
                f"Could not reach the host at {hosts}. On the same network: check both PCs "
                f"use the same Wi-Fi (not a guest one), the router does not keep devices "
                f"apart, and no VPN is on. Over the internet: the host's router must "
                f"forward TCP port {DEFAULT_PORT}")
        else:
            address_reason = ""
        if steam_failures:
            # Steam is the way that works on any network, so its reason leads
            self.disconnect_reason = steam_failures[0]
            if failed:
                hosts = " or ".join(host for host, _ in failed)
                self.disconnect_reason += f" (a direct connection to {hosts} failed too)"
        else:
            self.disconnect_reason = address_reason
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
                sock.settimeout(_FAREWELL_SEND_TIMEOUT)  # never hang on leaving
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
                self._connection_failed(f"Network error: {e}")
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
            # Read everything that is waiting (up to _MAX_READS_PER_LOOP chunks). The
            # socket blocks on sends (with a timeout), so only recv() once select()
            # reports data - otherwise recv() would stall the loop.
            for _ in range(_MAX_READS_PER_LOOP):
                # A handler may have closed the connection (CONNECT_REJECT, DISCONNECT)
                with self._state_lock:
                    if not self.connected:
                        return
                readable, _, _ = select.select([sock], [], [], 0)
                if not readable:
                    return

                data = sock.recv(MESSAGE_BUFFER_SIZE)

                if not data:
                    # Connection closed - host disconnected
                    logger.warning("Server disconnected")
                    self._connection_failed("Host disconnected")
                    return

                # H13 fix: check buffer overflow and disconnect on overflow
                if not self.recv_buffer.add_data(data):
                    logger.warning("Buffer overflow from server, disconnecting")
                    self._connection_failed("Buffer overflow")
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

        except (BlockingIOError, socket.timeout):
            # No data available after all
            pass
        except ConnectionResetError:
            logger.warning("Connection reset by server")
            self._connection_failed("Host disconnected")
        except Exception as e:
            logger.error(f"Receive error: {e}")
            self._connection_failed(f"Connection error: {e}")

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
                # Report it: the game shows "Connection Lost" from these flags. A send
                # error used to stop the network loop silently - the client then sat
                # in a game that no longer heard anything.
                self._connection_failed(f"Connection lost: {e}")
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
        # Security: never log the password -- it's a credential
        reconnect_password = data.get('reconnect_password', '')
        if reconnect_password:
            self.reconnect_password = reconnect_password
        logger.info(f"Connection accepted - Player {player_index + 1}")

    def _handle_connect_reject(self, message: dict):
        """Handle connection rejection from server"""
        data = message.get('data', {})
        reason = data.get('reason', 'Unknown reason')
        logger.warning(f"Connection rejected: {reason}")
        # Keep the host's reason ("Lobby is full", "Version mismatch: ...") for the join
        # screen; connect() stops waiting as soon as it sees `disconnected`
        self._connection_failed(reason)

    def _handle_disconnect_message(self, message: dict):
        """Handle DISCONNECT message from server (M11: extracted from if-elif chain)"""
        logger.warning("Server disconnected")
        # Host disconnected - set disconnected flag so game loop can detect it
        self._connection_failed("Host disconnected")

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
            self._connection_failed("Connection timeout")

    def _connection_failed(self, reason: str):
        """
        The connection ended without us asking: flag it for the game loop / lobby (they
        show "Connection Lost" with the reason) and close the socket.

        The FIRST reason wins. After a CONNECT_REJECT the host also closes its end, and
        the follow-up read error used to overwrite "Lobby is full" with a socket error.
        """
        # Through Steam, "Host disconnected" only means the local bridge closed; the
        # bridge knows the real reason ("Lost the connection to X", ...)
        join = self._steam_join
        if join is not None and self._is_link_reason(reason):
            reason = join.failure_reason() or reason
        # H7: Lock around shared state writes -- called from network thread
        with self._state_lock:
            if not self.disconnected:
                self.disconnected = True
                self.disconnect_reason = reason
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
        """Get assigned player index (0-3)"""
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

            # Blocking sends with a time limit, reads after select() (as in connect())
            self.socket.settimeout(SEND_TIMEOUT)

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
