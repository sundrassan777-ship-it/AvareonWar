"""
Network configuration constants for multiplayer mode.

Defines all network-related settings including ports, timeouts, and protocol version.
"""

import enum

# Network Protocol Version
# L12: Version compatibility — increment MAJOR for breaking changes, MINOR for new message
# types, PATCH for bug fixes. Server rejects clients with mismatched MAJOR version.
# History: 1.0.0 = initial release (2-player + 4-player lobby, sequential + simultaneous)
NETWORK_VERSION = "1.0.0"

# Connection Settings
DEFAULT_PORT = 7777
MAX_CLIENTS = 3  # Support up to 4 players (host + 3 clients)
CONNECTION_TIMEOUT = 15.0  # seconds - no response triggers disconnect
RECONNECTION_TIMEOUT = 60.0  # seconds - window to reconnect after disconnect

# Message Settings
MAX_MESSAGE_SIZE = 1_000_000  # 1 MB (for full state sync)
MESSAGE_BUFFER_SIZE = 4096  # bytes per socket recv() call
MESSAGE_HEADER_SIZE = 4  # bytes for length prefix (uint32)

# Heartbeat Settings
# M31: Timeout relationship — HEARTBEAT_INTERVAL < HEARTBEAT_TIMEOUT < CONNECTION_TIMEOUT
# Server sends PING every HEARTBEAT_INTERVAL seconds. Client responds with PONG.
# If no PONG received within HEARTBEAT_TIMEOUT, connection is considered lost.
# CONNECTION_TIMEOUT is the outer boundary checked by both sides.
HEARTBEAT_INTERVAL = 5.0  # seconds between PING messages
HEARTBEAT_TIMEOUT = 15.0  # seconds - no PONG triggers connection timeout
assert HEARTBEAT_INTERVAL < HEARTBEAT_TIMEOUT <= CONNECTION_TIMEOUT, (
    "Must satisfy: HEARTBEAT_INTERVAL < HEARTBEAT_TIMEOUT <= CONNECTION_TIMEOUT")

# Turn Management
PLANNING_PHASE_TIMEOUT = 60.0  # seconds (matches game_state.py)
TURN_TIMEOUT = 300.0  # seconds - max time for entire turn

# State Synchronization
ENABLE_STATE_CHECKSUMS = True
CHECKSUM_FREQUENCY = 1  # validate state every N turns

# UPnP Settings (for internet play auto-configuration)
UPNP_DISCOVERY_TIMEOUT = 2000  # milliseconds for UPnP IGD device discovery
UPNP_DESCRIPTION = "AvareonWar"  # Description shown in router admin panel

# Message Types (Protocol Constants)
# Uses str mixin (str, enum.Enum) so that enum members compare equal to their
# string values. This preserves backward compatibility with code that compares
# decoded JSON message type strings against MessageType members, e.g.
# msg_type == MessageType.CONNECT_ACCEPT still works when msg_type is "CONNECT_ACCEPT".
# The str mixin also ensures json.dumps() serializes members as plain strings.
class MessageType(str, enum.Enum):
    """Network message type identifiers (str enum for JSON/comparison compatibility)."""
    # Connection
    CONNECT_REQUEST = "CONNECT_REQUEST"
    CONNECT_ACCEPT = "CONNECT_ACCEPT"
    CONNECT_REJECT = "CONNECT_REJECT"
    DISCONNECT = "DISCONNECT"
    PING = "PING"
    PONG = "PONG"

    # Setup Phase
    SETUP_CONFIG = "SETUP_CONFIG"
    TERRITORY_SELECT = "TERRITORY_SELECT"
    SETUP_COMPLETE = "SETUP_COMPLETE"

    # Lobby Phase (4-player multiplayer)
    LOBBY_STATE = "LOBBY_STATE"              # Full lobby state sync (host -> clients)
    LOBBY_JOIN = "LOBBY_JOIN"                # Player joined lobby (host -> clients)
    LOBBY_LEAVE = "LOBBY_LEAVE"              # Player left lobby (host -> clients)
    LOBBY_KICK = "LOBBY_KICK"                # Host kicked a player (host -> kicked client)
    LOBBY_SLOT_UPDATE = "LOBBY_SLOT_UPDATE"  # Slot configuration changed (bidirectional)
    LOBBY_COUNTDOWN = "LOBBY_COUNTDOWN"      # Launch countdown timer (host -> clients)
    LOBBY_LAUNCH = "LOBBY_LAUNCH"            # Game starting (host -> clients)

    # Loading Screen Sync
    GAME_READY = "GAME_READY"                # Player finished loading, ready to start (bidirectional)

    # Reconnection
    RECONNECT_REQUEST = "RECONNECT_REQUEST"  # Player attempting to reconnect (client -> host)
    RECONNECT_ACCEPT = "RECONNECT_ACCEPT"    # Reconnection successful (host -> client)
    RECONNECT_REJECT = "RECONNECT_REJECT"    # Reconnection failed (host -> client)

    # Player State
    PLAYER_DISCONNECT = "PLAYER_DISCONNECT"  # Player disconnected (host -> clients)
    AI_TAKEOVER = "AI_TAKEOVER"              # AI now controlling player slot (host -> clients)

    # Gameplay - Orders
    MOVEMENT_ORDER = "MOVEMENT_ORDER"
    BUILDING_ORDER = "BUILDING_ORDER"
    TRAINING_ORDER = "TRAINING_ORDER"
    ORDER_REMOVE = "ORDER_REMOVE"

    # Gameplay - Execution
    EXECUTE_ORDERS = "EXECUTE_ORDERS"
    BATTLE_RESOLVE = "BATTLE_RESOLVE"
    UNIT_COMPLETE = "UNIT_COMPLETE"
    BUILDING_COMPLETE = "BUILDING_COMPLETE"
    TURN_END = "TURN_END"
    CURRENT_PLAYER_CHANGED = "CURRENT_PLAYER_CHANGED"

    # Simultaneous Mode - Planning Phase
    SIM_ORDER_QUEUED = "SIM_ORDER_QUEUED"          # Player queued an order (not broadcast to others)
    SIM_PLAYER_READY = "SIM_PLAYER_READY"          # Player finished planning, ready to execute
    SIM_ALL_READY = "SIM_ALL_READY"                # All players ready, includes merged order list
    SIM_TIMER_UPDATE = "SIM_TIMER_UPDATE"          # Timer sync between host/client

    # Simultaneous Mode - Resolution Phase
    SIM_CROSSING_CONFLICT = "SIM_CROSSING_CONFLICT"  # Crossing army conflict detected
    SIM_FORCED_DEFEND = "SIM_FORCED_DEFEND"          # Player forced to defend (popup notification)
    SIM_BATTLE_RESULT = "SIM_BATTLE_RESULT"          # Battle outcome from resolver
    SIM_ALLIANCE_CHOICE = "SIM_ALLIANCE_CHOICE"      # Territory owner selection for allied capture
    SIM_ROUND_COMPLETE = "SIM_ROUND_COMPLETE"        # Round finished, start new planning phase
    SIM_HERO_ABILITY = "SIM_HERO_ABILITY"            # Hero ability used (sync effect to other players)

    # Chat
    CHAT_MESSAGE = "CHAT_MESSAGE"

    # Error & Sync
    STATE_CHECKSUM = "STATE_CHECKSUM"
    FULL_STATE_SYNC = "FULL_STATE_SYNC"
    ERROR = "ERROR"

    @classmethod
    def from_string(cls, value: str) -> "MessageType":
        """Convert a string value back to the corresponding enum member.

        Args:
            value: The string to look up (e.g. "CONNECT_REQUEST").

        Returns:
            The matching MessageType enum member.

        Raises:
            ValueError: If no member matches the given string.
        """
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Unknown MessageType: {value!r}")


# Error Codes
# Same str mixin pattern as MessageType for consistent enum behavior.
class ErrorCode(str, enum.Enum):
    """Network error codes (str enum for JSON/comparison compatibility)."""
    INVALID_MESSAGE = "INVALID_MESSAGE"
    INVALID_ACTION = "INVALID_ACTION"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    ALREADY_CONNECTED = "ALREADY_CONNECTED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    DESYNC_DETECTED = "DESYNC_DETECTED"

    @classmethod
    def from_string(cls, value: str) -> "ErrorCode":
        """Convert a string value back to the corresponding enum member.

        Args:
            value: The string to look up (e.g. "INVALID_MESSAGE").

        Returns:
            The matching ErrorCode enum member.

        Raises:
            ValueError: If no member matches the given string.
        """
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Unknown ErrorCode: {value!r}")
