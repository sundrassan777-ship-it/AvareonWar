"""
Network protocol implementation for multiplayer communication.

Handles message serialization, deserialization, and length-prefix framing.
"""

import json
import struct
from typing import Dict, Any, List, Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network_config import MessageType, ErrorCode, MESSAGE_HEADER_SIZE, MAX_MESSAGE_SIZE
from utils.logger import get_logger

logger = get_logger(__name__)


class NetworkProtocol:
    """
    Handles network message encoding/decoding with length-prefix framing.

    Message Format:
    - 4 bytes: message length (uint32, big-endian)
    - N bytes: JSON payload
    """

    def __init__(self) -> None:
        # Counter for outgoing message sequence numbers (out-of-order/duplicate detection)
        self._sequence_number: int = 0

    def encode_message(self, message_type: str, data: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Encode a message to bytes with length-prefix framing.

        Args:
            message_type: Type of message (from MessageType class)
            data: Optional message payload data

        Returns:
            Encoded message bytes (4-byte length prefix + JSON payload)

        Raises:
            ValueError: If message is too large
        """
        # Build message structure with sequence number for out-of-order/duplicate detection
        message = {
            "type": message_type,
            "seq": self._sequence_number,
            "data": data or {}
        }

        # Increment sequence number after embedding it in the message
        self._sequence_number += 1

        # Serialize to JSON
        json_data = json.dumps(message).encode('utf-8')

        # Check message size
        if len(json_data) > MAX_MESSAGE_SIZE:
            raise ValueError(f"Message too large: {len(json_data)} bytes (max {MAX_MESSAGE_SIZE})")

        # Add length prefix (4 bytes, big-endian uint32)
        length_prefix = struct.pack('!I', len(json_data))

        return length_prefix + json_data

    def decode_message(self, data: bytes) -> Optional[Dict[str, Any]]:
        """
        Decode a complete message from bytes.

        Args:
            data: Complete message bytes (including length prefix)

        Returns:
            Decoded message dict, or None if decoding fails
        """
        try:
            # Check minimum size (4-byte header + at least 2 bytes "{}")
            if len(data) < MESSAGE_HEADER_SIZE + 2:
                return None

            # Extract length from header
            message_length = struct.unpack('!I', data[:MESSAGE_HEADER_SIZE])[0]

            # Validate length
            if message_length > MAX_MESSAGE_SIZE:
                return None

            # Extract JSON payload
            json_data = data[MESSAGE_HEADER_SIZE:MESSAGE_HEADER_SIZE + message_length]

            # Deserialize JSON
            message = json.loads(json_data.decode('utf-8'))

            # Validate message structure
            if not isinstance(message, dict):
                return None
            if 'type' not in message:
                return None

            return message

        except (struct.error, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def create_connect_request(self, player_name: str = "Player") -> bytes:
        """Create a connection request message"""
        from network_config import NETWORK_VERSION
        return self.encode_message(MessageType.CONNECT_REQUEST, {
            "version": NETWORK_VERSION,
            "player_name": player_name
        })

    def create_connect_accept(self, player_index: int, reconnect_password: str = "") -> bytes:
        """Create a connection accept message.

        Args:
            player_index: Assigned player slot index (0-3)
            reconnect_password: Password for reconnection (plain text, shown to client)
        """
        data = {"player_index": player_index}
        if reconnect_password:
            data["reconnect_password"] = reconnect_password
        return self.encode_message(MessageType.CONNECT_ACCEPT, data)

    def create_connect_reject(self, reason: str) -> bytes:
        """Create a connection reject message"""
        return self.encode_message(MessageType.CONNECT_REJECT, {
            "reason": reason
        })

    def create_ping(self) -> bytes:
        """Create a ping heartbeat message"""
        return self.encode_message(MessageType.PING, {})

    def create_pong(self) -> bytes:
        """Create a pong heartbeat response"""
        return self.encode_message(MessageType.PONG, {})

    def create_error(self, code: str, message: str) -> bytes:
        """Create an error message"""
        return self.encode_message(MessageType.ERROR, {
            "code": code,
            "message": message
        })

    def create_disconnect(self, reason: str = "User disconnect") -> bytes:
        """Create a disconnect notification"""
        return self.encode_message(MessageType.DISCONNECT, {
            "reason": reason
        })

    def create_setup_config(self, config: Dict[str, Any]) -> bytes:
        """Create a setup configuration message"""
        return self.encode_message(MessageType.SETUP_CONFIG, config)

    def create_territory_select(self, player_index: int, territory_name: str) -> bytes:
        """Create a territory selection message"""
        return self.encode_message(MessageType.TERRITORY_SELECT, {
            "player_index": player_index,
            "territory_name": territory_name
        })

    def create_setup_complete(self, player1_territory: str, player2_territory: str,
                              victory_condition: int = 0, taxation_level: int = 0,
                              turn_mode: int = 0) -> bytes:
        """Create a setup complete message (sent by host to start game).

        Args:
            player1_territory: Host's selected territory
            player2_territory: Client's selected territory
            victory_condition: Victory condition index (0=Domination, 1=Capital Assault, 2=Total Conquest)
            taxation_level: Taxation level index (0-4, representing 0% to 100%)
            turn_mode: Turn mode index (0=Sequential, 1=Simultaneous)
        """
        return self.encode_message(MessageType.SETUP_COMPLETE, {
            "player1_territory": player1_territory,
            "player2_territory": player2_territory,
            "victory_condition": victory_condition,
            "taxation_level": taxation_level,
            "turn_mode": turn_mode
        })

    # ========== Lobby Phase Messages (4-player multiplayer) ==========

    def create_lobby_state(self, slots: List[Dict[str, Any]], settings: Dict[str, Any]) -> bytes:
        """Create a full lobby state sync message.

        Args:
            slots: List of LobbySlot data dicts for all 4 slots
            settings: Game settings (victory_condition, taxation_level, turn_mode)
        """
        return self.encode_message(MessageType.LOBBY_STATE, {
            "slots": slots,
            "settings": settings
        })

    def create_lobby_join(self, player_index: int, player_name: str) -> bytes:
        """Create a player joined lobby message.

        Args:
            player_index: Slot index the player joined (0-3)
            player_name: Name of the joining player
        """
        return self.encode_message(MessageType.LOBBY_JOIN, {
            "player_index": player_index,
            "player_name": player_name
        })

    def create_lobby_leave(self, player_index: int, reason: str = "") -> bytes:
        """Create a player left lobby message.

        Args:
            player_index: Slot index the player left (0-3)
            reason: Optional reason for leaving
        """
        return self.encode_message(MessageType.LOBBY_LEAVE, {
            "player_index": player_index,
            "reason": reason
        })

    def create_lobby_kick(self, player_index: int, reason: str = "Kicked by host") -> bytes:
        """Create a kick notification message.

        Args:
            player_index: Slot index being kicked (0-3)
            reason: Reason for kick
        """
        return self.encode_message(MessageType.LOBBY_KICK, {
            "player_index": player_index,
            "reason": reason
        })

    def create_lobby_slot_update(self, player_index: int, slot_data: Dict[str, Any]) -> bytes:
        """Create a slot configuration update message.

        Args:
            player_index: Slot index being updated (0-3)
            slot_data: Dict with updated fields (state, color, team, ai_difficulty, territory)
        """
        return self.encode_message(MessageType.LOBBY_SLOT_UPDATE, {
            "player_index": player_index,
            **slot_data
        })

    def create_lobby_countdown(self, seconds_remaining: int) -> bytes:
        """Create a launch countdown timer message.

        Args:
            seconds_remaining: Seconds until game launch
        """
        return self.encode_message(MessageType.LOBBY_COUNTDOWN, {
            "seconds_remaining": seconds_remaining
        })

    def create_lobby_launch(self, final_slots: List[Dict[str, Any]], settings: Dict[str, Any]) -> bytes:
        """Create a game starting message.

        Args:
            final_slots: Final slot configuration for all players
            settings: Final game settings
        """
        return self.encode_message(MessageType.LOBBY_LAUNCH, {
            "slots": final_slots,
            "settings": settings
        })

    # ========== Loading Screen Sync ==========

    def create_game_ready(self, player_index: int) -> bytes:
        """Create a game-ready message indicating this player finished loading.

        Args:
            player_index: Index of the player that finished loading
        """
        return self.encode_message(MessageType.GAME_READY, {
            "player_index": player_index
        })

    # ========== Reconnection Messages ==========

    def create_reconnect_request(self, player_name: str, password: str) -> bytes:
        """Create a reconnection request message.

        Args:
            player_name: Name of the player attempting to reconnect
            password: Reconnection password (received at initial connect)
        """
        from network_config import NETWORK_VERSION
        return self.encode_message(MessageType.RECONNECT_REQUEST, {
            "version": NETWORK_VERSION,
            "player_name": player_name,
            "password": password
        })

    def create_reconnect_accept(self, player_index: int, game_state: Dict[str, Any]) -> bytes:
        """Create a reconnection accept message with full game state.

        Args:
            player_index: Restored player slot index (0-3)
            game_state: Full serialized game state for sync
        """
        return self.encode_message(MessageType.RECONNECT_ACCEPT, {
            "player_index": player_index,
            "game_state": game_state
        })

    def create_reconnect_reject(self, reason: str = "Invalid credentials") -> bytes:
        """Create a reconnection reject message.

        Args:
            reason: Why reconnection was rejected
        """
        return self.encode_message(MessageType.RECONNECT_REJECT, {
            "reason": reason
        })

    # ========== Player State Messages ==========

    def create_player_disconnect(self, player_index: int, ai_takeover: bool = True) -> bytes:
        """Create a player disconnected notification.

        Args:
            player_index: Slot index of disconnected player (0-3)
            ai_takeover: Whether AI is taking over the slot
        """
        return self.encode_message(MessageType.PLAYER_DISCONNECT, {
            "player_index": player_index,
            "ai_takeover": ai_takeover
        })

    def create_ai_takeover(self, player_index: int, ai_difficulty: int = 1) -> bytes:
        """Create an AI takeover notification.

        Args:
            player_index: Slot index AI is controlling (0-3)
            ai_difficulty: AI difficulty level (0=Easy, 1=Medium, 2=Hard)
        """
        return self.encode_message(MessageType.AI_TAKEOVER, {
            "player_index": player_index,
            "ai_difficulty": ai_difficulty
        })

    # ========== Chat Message (Extended) ==========

    # Security: maximum chat message length to prevent memory exhaustion / DoS
    MAX_CHAT_LENGTH = 500

    def create_chat_message(self, player_index: int, message: str,
                            channel: str = "all") -> bytes:
        """Create a chat message.

        Args:
            player_index: Sender's slot index (0-3)
            message: Chat message text (truncated to MAX_CHAT_LENGTH)
            channel: 'all' for everyone, 'team' for allies only
        """
        # Security: cap chat length to prevent oversized messages
        if len(message) > self.MAX_CHAT_LENGTH:
            message = message[:self.MAX_CHAT_LENGTH]
        return self.encode_message(MessageType.CHAT_MESSAGE, {
            "player_index": player_index,
            "message": message,
            "channel": channel
        })

    def create_movement_order(self, from_territory: str, to_territory: str,
                             army_count: int, unit_ids: List[int]) -> bytes:
        """Create a movement order message"""
        return self.encode_message(MessageType.MOVEMENT_ORDER, {
            "from_territory": from_territory,
            "to_territory": to_territory,
            "army_count": army_count,
            "unit_ids": unit_ids
        })

    def create_building_order(self, territory: str, plot_index: int,
                             building_type: str) -> bytes:
        """Create a building order message"""
        return self.encode_message(MessageType.BUILDING_ORDER, {
            "territory": territory,
            "plot_index": plot_index,
            "building_type": building_type
        })

    def create_training_order(self, territory: str, barracks_plot: int,
                             unit_type: str) -> bytes:
        """Create a training order message"""
        return self.encode_message(MessageType.TRAINING_ORDER, {
            "territory": territory,
            "barracks_plot": barracks_plot,
            "unit_type": unit_type
        })

    def create_execute_orders(self) -> bytes:
        """Create an execute orders message"""
        return self.encode_message(MessageType.EXECUTE_ORDERS, {})

    def create_battle_resolve(self, battle_index: int, result: Dict[str, Any]) -> bytes:
        """Create a battle resolution message"""
        data = {
            "battle_index": battle_index,
            **result
        }
        return self.encode_message(MessageType.BATTLE_RESOLVE, data)

    def create_turn_end(self) -> bytes:
        """Create a turn end message"""
        return self.encode_message(MessageType.TURN_END, {})

    # ========== Simultaneous Mode Messages ==========

    def create_sim_player_ready(self, player_id: int) -> bytes:
        """Create a player ready message for simultaneous mode.

        Sent when a player clicks End Turn during planning phase.
        """
        return self.encode_message(MessageType.SIM_PLAYER_READY, {
            "player_id": player_id
        })

    def create_sim_all_ready(self, merged_orders: List[Dict[str, Any]]) -> bytes:
        """Create an all-ready message with merged orders.

        Sent by host when all players are ready to execute.
        """
        return self.encode_message(MessageType.SIM_ALL_READY, {
            "orders": merged_orders
        })

    def create_sim_timer_update(self, player_timers: Dict[int, float]) -> bytes:
        """Create a timer sync message.

        Sent periodically by host to keep client timers in sync.
        """
        return self.encode_message(MessageType.SIM_TIMER_UPDATE, {
            "timers": player_timers
        })

    def create_sim_battle_result(self, territory: str, result: Dict[str, Any]) -> bytes:
        """Create a battle result message for simultaneous mode.

        Sent by the player who resolved the battle.
        """
        return self.encode_message(MessageType.SIM_BATTLE_RESULT, {
            "territory": territory,
            "result": result
        })

    def create_sim_alliance_choice(self, territory: str, new_owner: int) -> bytes:
        """Create an alliance territory choice message.

        Sent when the choosing player assigns territory ownership.
        """
        return self.encode_message(MessageType.SIM_ALLIANCE_CHOICE, {
            "territory": territory,
            "new_owner": new_owner
        })

    def create_sim_round_complete(self, round_number: int) -> bytes:
        """Create a round complete message.

        Signals end of resolution phase, start of new planning phase.
        """
        return self.encode_message(MessageType.SIM_ROUND_COMPLETE, {
            "round_number": round_number
        })

    # Sync logger: desync diagnosis messages (v1.3.0)

    def create_state_detail_request(self, turn_number: int) -> bytes:
        """Create a state detail request (host -> client on checksum mismatch)."""
        return self.encode_message(MessageType.STATE_DETAIL_REQUEST, {
            "turn_number": turn_number
        })

    def create_state_detail_response(self, turn_number: int, state_detail: Dict[str, Any]) -> bytes:
        """Create a state detail response (client -> host with full state for diff)."""
        return self.encode_message(MessageType.STATE_DETAIL_RESPONSE, {
            "turn_number": turn_number,
            "state_detail": state_detail
        })

    def create_desync_diff(self, turn_number: int, diff: Dict[str, Any]) -> bytes:
        """Create a desync diff message (host -> client with field-level diff)."""
        return self.encode_message(MessageType.DESYNC_DIFF, {
            "turn_number": turn_number,
            "diff": diff
        })

    def validate_message(self, message: Dict[str, Any]) -> bool:
        """
        Validate message structure and required fields.

        Checks that the message is a dict with 'type', 'seq', and 'data' keys,
        and that 'type' is a recognized MessageType enum value.

        Args:
            message: Decoded message dict

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(message, dict):
            return False

        # Check required fields
        if 'type' not in message:
            return False
        if 'seq' not in message:
            return False
        if 'data' not in message:
            return False

        # Phase 6A: Also validate that type is a known MessageType
        # Rejects messages with fabricated or unknown type strings
        try:
            MessageType(message.get('type'))
        except ValueError:
            logger.warning(f"Unknown message type: {message.get('type')}")
            return False

        return True

    def validate_message_data(self, message: Dict[str, Any]) -> bool:
        """
        Validate data fields of an incoming message based on its type.

        Security: prevents malicious clients from sending out-of-range player
        indices, negative army counts, oversized chat messages, etc.
        Checks numeric ranges and string lengths for known message types.

        Args:
            message: Decoded message dict (must pass validate_message() first)

        Returns:
            True if data fields are valid, False if any field fails validation
        """
        msg_type = message.get('type')
        data = message.get('data', {})
        if not isinstance(data, dict):
            logger.warning(f"Message data is not a dict: {type(data)}")
            return False

        def _valid_player_index(val):
            """Player index must be int 0-3"""
            return isinstance(val, int) and 0 <= val <= 3

        def _valid_string(val, max_len=256):
            """String field must be str within length limit"""
            return isinstance(val, str) and len(val) <= max_len

        # Per-type data field validation
        try:
            if msg_type in (MessageType.TERRITORY_SELECT, MessageType.LOBBY_JOIN,
                            MessageType.LOBBY_LEAVE, MessageType.LOBBY_KICK,
                            MessageType.PLAYER_DISCONNECT, MessageType.GAME_READY,
                            MessageType.SIM_PLAYER_READY):
                pi = data.get('player_index')
                if pi is not None and not _valid_player_index(pi):
                    logger.warning(f"Invalid player_index {pi} in {msg_type}")
                    return False

            elif msg_type == MessageType.LOBBY_SLOT_UPDATE:
                pi = data.get('player_index')
                if pi is not None and not _valid_player_index(pi):
                    logger.warning(f"Invalid player_index {pi} in LOBBY_SLOT_UPDATE")
                    return False
                diff = data.get('ai_difficulty')
                if diff is not None and not (isinstance(diff, int) and 0 <= diff <= 2):
                    logger.warning(f"Invalid ai_difficulty {diff}")
                    return False
                team = data.get('team')
                if team is not None and not (isinstance(team, int) and 0 <= team <= 3):
                    logger.warning(f"Invalid team {team}")
                    return False

            elif msg_type == MessageType.AI_TAKEOVER:
                pi = data.get('player_index')
                if pi is not None and not _valid_player_index(pi):
                    logger.warning(f"Invalid player_index {pi} in AI_TAKEOVER")
                    return False
                diff = data.get('ai_difficulty')
                if diff is not None and not (isinstance(diff, int) and 0 <= diff <= 2):
                    logger.warning(f"Invalid ai_difficulty {diff}")
                    return False

            elif msg_type == MessageType.CHAT_MESSAGE:
                pi = data.get('player_index')
                if pi is not None and not _valid_player_index(pi):
                    logger.warning(f"Invalid player_index {pi} in CHAT_MESSAGE")
                    return False
                msg_text = data.get('message', '')
                if not _valid_string(msg_text, self.MAX_CHAT_LENGTH):
                    logger.warning(f"Chat message too long or invalid type")
                    return False
                channel = data.get('channel', 'all')
                if channel not in ('all', 'team'):
                    logger.warning(f"Invalid chat channel: {channel}")
                    return False

            elif msg_type == MessageType.MOVEMENT_ORDER:
                count = data.get('army_count')
                if count is not None and not (isinstance(count, int) and 1 <= count <= 999):
                    logger.warning(f"Invalid army_count {count} in MOVEMENT_ORDER")
                    return False
                for field in ('from_territory', 'to_territory'):
                    val = data.get(field)
                    if val is not None and not _valid_string(val, 64):
                        logger.warning(f"Invalid {field} in MOVEMENT_ORDER")
                        return False

            elif msg_type == MessageType.BUILDING_ORDER:
                plot_idx = data.get('plot_index')
                if plot_idx is not None and not (isinstance(plot_idx, int) and 0 <= plot_idx <= 10):
                    logger.warning(f"Invalid plot_index {plot_idx}")
                    return False
                for field in ('territory', 'building_type'):
                    val = data.get(field)
                    if val is not None and not _valid_string(val, 64):
                        logger.warning(f"Invalid {field} in BUILDING_ORDER")
                        return False

            elif msg_type == MessageType.TRAINING_ORDER:
                plot_idx = data.get('barracks_plot')
                if plot_idx is not None and not (isinstance(plot_idx, int) and 0 <= plot_idx <= 10):
                    logger.warning(f"Invalid barracks_plot {plot_idx}")
                    return False
                for field in ('territory', 'unit_type'):
                    val = data.get(field)
                    if val is not None and not _valid_string(val, 64):
                        logger.warning(f"Invalid {field} in TRAINING_ORDER")
                        return False

            elif msg_type == MessageType.SETUP_COMPLETE:
                vc = data.get('victory_condition')
                if vc is not None and not (isinstance(vc, int) and 0 <= vc <= 2):
                    logger.warning(f"Invalid victory_condition {vc}")
                    return False
                tl = data.get('taxation_level')
                if tl is not None and not (isinstance(tl, int) and 0 <= tl <= 4):
                    logger.warning(f"Invalid taxation_level {tl}")
                    return False
                tm = data.get('turn_mode')
                if tm is not None and not (isinstance(tm, int) and 0 <= tm <= 1):
                    logger.warning(f"Invalid turn_mode {tm}")
                    return False

            elif msg_type == MessageType.SIM_ALLIANCE_CHOICE:
                owner = data.get('new_owner')
                if owner is not None and not _valid_player_index(owner):
                    logger.warning(f"Invalid new_owner {owner}")
                    return False

            elif msg_type in (MessageType.STATE_DETAIL_REQUEST, MessageType.STATE_DETAIL_RESPONSE,
                              MessageType.DESYNC_DIFF):
                # Sync logger messages: validate turn_number is a non-negative int
                tn = data.get('turn_number')
                if tn is not None and not (isinstance(tn, int) and tn >= 0):
                    logger.warning(f"Invalid turn_number {tn} in {msg_type}")
                    return False

        except Exception as e:
            logger.warning(f"Data validation error for {msg_type}: {e}")
            return False

        return True


class MessageBuffer:
    """
    Buffers incoming socket data and extracts complete messages.

    Handles partial receives and message boundaries using length-prefix framing.
    """

    def __init__(self) -> None:
        self.buffer: bytes = b''

    # Maximum total buffer size to prevent memory exhaustion from partial messages
    MAX_BUFFER_SIZE = 2 * MAX_MESSAGE_SIZE  # 2 MB

    def add_data(self, data: bytes) -> bool:
        """Add received data to buffer, with overflow protection.

        Returns:
            True if data was added, False if buffer overflow (caller should disconnect).
        """
        if len(self.buffer) + len(data) > self.MAX_BUFFER_SIZE:
            # M12 fix: Return False so caller can disconnect instead of silently desyncing
            logger.warning(f"Buffer overflow: {len(self.buffer) + len(data)} > {self.MAX_BUFFER_SIZE}")
            self.buffer = b''
            return False
        self.buffer += data
        return True

    def extract_message(self) -> Optional[bytes]:
        """
        Extract one complete message from buffer if available.

        Returns:
            Complete message bytes (including length prefix), or None if incomplete
        """
        # Need at least 4 bytes for length header
        if len(self.buffer) < MESSAGE_HEADER_SIZE:
            return None

        # Read message length from header
        message_length = struct.unpack('!I', self.buffer[:MESSAGE_HEADER_SIZE])[0]

        # Check if message length is valid
        if message_length > MAX_MESSAGE_SIZE:
            # Invalid length - clear buffer to recover
            self.buffer = b''
            return None

        # Total message size = header + payload
        total_size = MESSAGE_HEADER_SIZE + message_length

        # Check if complete message is available
        if len(self.buffer) < total_size:
            return None  # Incomplete, wait for more data

        # Extract complete message
        message = self.buffer[:total_size]

        # Remove from buffer
        self.buffer = self.buffer[total_size:]

        return message

    def clear(self) -> None:
        """Clear buffer (e.g., on connection reset)"""
        self.buffer = b''

    def __len__(self) -> int:
        """Return buffer size"""
        return len(self.buffer)
