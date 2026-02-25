"""
Tests for network/protocol.py

These tests cover the NetworkProtocol and MessageBuffer classes.
"""

import pytest
import struct
import json

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network.protocol import NetworkProtocol, MessageBuffer
from network_config import MessageType, MESSAGE_HEADER_SIZE, MAX_MESSAGE_SIZE


class TestNetworkProtocol:
    """Tests for NetworkProtocol class"""

    @pytest.fixture
    def protocol(self):
        return NetworkProtocol()

    def test_encode_message_basic(self, protocol):
        """Encode basic message with type and data"""
        message = protocol.encode_message(MessageType.PING, {"test": "data"})

        # Should have 4-byte header + JSON payload
        assert len(message) > MESSAGE_HEADER_SIZE

        # Extract length from header
        length = struct.unpack('!I', message[:MESSAGE_HEADER_SIZE])[0]
        assert length == len(message) - MESSAGE_HEADER_SIZE

    def test_encode_decode_roundtrip(self, protocol):
        """Message survives encode/decode roundtrip"""
        original_data = {"key": "value", "number": 42}
        encoded = protocol.encode_message(MessageType.PING, original_data)
        decoded = protocol.decode_message(encoded)

        assert decoded is not None
        assert decoded['type'] == MessageType.PING
        assert decoded['data'] == original_data

    def test_decode_message_invalid_too_short(self, protocol):
        """Decode returns None for too-short message"""
        result = protocol.decode_message(b"abc")
        assert result is None

    def test_decode_message_invalid_json(self, protocol):
        """Decode returns None for invalid JSON"""
        # Create message with invalid JSON payload
        invalid_json = b"not valid json"
        length_prefix = struct.pack('!I', len(invalid_json))
        message = length_prefix + invalid_json

        result = protocol.decode_message(message)
        assert result is None

    def test_decode_message_missing_type(self, protocol):
        """Decode returns None for message without type"""
        payload = json.dumps({"data": "no type field"}).encode('utf-8')
        length_prefix = struct.pack('!I', len(payload))
        message = length_prefix + payload

        result = protocol.decode_message(message)
        assert result is None

    def test_encode_message_too_large(self, protocol):
        """Encode raises error for oversized message"""
        huge_data = {"data": "x" * (MAX_MESSAGE_SIZE + 1000)}

        with pytest.raises(ValueError, match="too large"):
            protocol.encode_message(MessageType.PING, huge_data)

    def test_sequence_number_increments(self, protocol):
        """Sequence number increments with each message"""
        msg1 = protocol.encode_message(MessageType.PING)
        msg2 = protocol.encode_message(MessageType.PING)

        decoded1 = protocol.decode_message(msg1)
        decoded2 = protocol.decode_message(msg2)

        assert decoded2['seq'] == decoded1['seq'] + 1

    def test_create_connect_request(self, protocol):
        """Create valid connect request"""
        message = protocol.create_connect_request("TestPlayer")
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.CONNECT_REQUEST
        assert 'version' in decoded['data']
        assert decoded['data']['player_name'] == "TestPlayer"

    def test_create_connect_accept(self, protocol):
        """Create valid connect accept"""
        message = protocol.create_connect_accept(player_index=1)
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.CONNECT_ACCEPT
        assert decoded['data']['player_index'] == 1

    def test_create_connect_reject(self, protocol):
        """Create valid connect reject"""
        message = protocol.create_connect_reject("Version mismatch")
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.CONNECT_REJECT
        assert "Version mismatch" in decoded['data']['reason']

    def test_create_ping_pong(self, protocol):
        """Create valid ping and pong messages"""
        ping = protocol.create_ping()
        pong = protocol.create_pong()

        ping_decoded = protocol.decode_message(ping)
        pong_decoded = protocol.decode_message(pong)

        assert ping_decoded['type'] == MessageType.PING
        assert pong_decoded['type'] == MessageType.PONG

    def test_create_disconnect(self, protocol):
        """Create valid disconnect message"""
        message = protocol.create_disconnect("User quit")
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.DISCONNECT
        assert decoded['data']['reason'] == "User quit"

    def test_create_movement_order(self, protocol):
        """Create valid movement order"""
        message = protocol.create_movement_order(
            from_territory="TerritoryA",
            to_territory="TerritoryB",
            army_count=5,
            unit_ids=[1, 2, 3]
        )
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.MOVEMENT_ORDER
        assert decoded['data']['from_territory'] == "TerritoryA"
        assert decoded['data']['to_territory'] == "TerritoryB"
        assert decoded['data']['army_count'] == 5
        assert decoded['data']['unit_ids'] == [1, 2, 3]

    def test_create_building_order(self, protocol):
        """Create valid building order"""
        message = protocol.create_building_order(
            territory="TestTerritory",
            plot_index=2,
            building_type="Barracks"
        )
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.BUILDING_ORDER
        assert decoded['data']['territory'] == "TestTerritory"
        assert decoded['data']['plot_index'] == 2
        assert decoded['data']['building_type'] == "Barracks"

    def test_create_training_order(self, protocol):
        """Create valid training order"""
        message = protocol.create_training_order(
            territory="TestTerritory",
            barracks_plot=1,
            unit_type="Swordsman"
        )
        decoded = protocol.decode_message(message)

        assert decoded['type'] == MessageType.TRAINING_ORDER
        assert decoded['data']['territory'] == "TestTerritory"
        assert decoded['data']['barracks_plot'] == 1
        assert decoded['data']['unit_type'] == "Swordsman"

    def test_validate_message_valid(self, protocol):
        """Validate accepts properly structured message"""
        message = {
            'type': MessageType.PING,
            'seq': 0,
            'data': {}
        }
        assert protocol.validate_message(message) is True

    def test_validate_message_missing_type(self, protocol):
        """Validate rejects message without type"""
        message = {'seq': 0, 'data': {}}
        assert protocol.validate_message(message) is False

    def test_validate_message_missing_seq(self, protocol):
        """Validate rejects message without seq"""
        message = {'type': MessageType.PING, 'data': {}}
        assert protocol.validate_message(message) is False

    def test_validate_message_not_dict(self, protocol):
        """Validate rejects non-dict message"""
        assert protocol.validate_message("not a dict") is False
        assert protocol.validate_message(None) is False
        assert protocol.validate_message([]) is False


class TestMessageBuffer:
    """Tests for MessageBuffer class"""

    @pytest.fixture
    def buffer(self):
        return MessageBuffer()

    @pytest.fixture
    def protocol(self):
        return NetworkProtocol()

    def test_empty_buffer(self, buffer):
        """Empty buffer returns None"""
        result = buffer.extract_message()
        assert result is None
        assert len(buffer) == 0

    def test_add_and_extract_complete_message(self, buffer, protocol):
        """Add complete message and extract it"""
        message = protocol.encode_message(MessageType.PING)
        buffer.add_data(message)

        extracted = buffer.extract_message()

        assert extracted is not None
        assert extracted == message
        assert len(buffer) == 0

    def test_partial_message_waits(self, buffer, protocol):
        """Partial message returns None until complete"""
        message = protocol.encode_message(MessageType.PING, {"data": "test"})

        # Add only first half
        buffer.add_data(message[:len(message)//2])
        result = buffer.extract_message()
        assert result is None

        # Add second half
        buffer.add_data(message[len(message)//2:])
        result = buffer.extract_message()
        assert result is not None
        assert result == message

    def test_multiple_messages(self, buffer, protocol):
        """Multiple messages extracted in order"""
        msg1 = protocol.encode_message(MessageType.PING, {"id": 1})
        msg2 = protocol.encode_message(MessageType.PONG, {"id": 2})

        buffer.add_data(msg1 + msg2)

        extracted1 = buffer.extract_message()
        extracted2 = buffer.extract_message()
        extracted3 = buffer.extract_message()

        assert extracted1 == msg1
        assert extracted2 == msg2
        assert extracted3 is None

    def test_clear_buffer(self, buffer):
        """Clear empties the buffer"""
        buffer.add_data(b"some data")
        assert len(buffer) > 0

        buffer.clear()
        assert len(buffer) == 0

    def test_invalid_length_clears_buffer(self, buffer):
        """Invalid message length clears buffer to recover"""
        # Create message with length exceeding MAX_MESSAGE_SIZE
        invalid_length = struct.pack('!I', MAX_MESSAGE_SIZE + 1000)
        buffer.add_data(invalid_length + b"garbage")

        result = buffer.extract_message()

        assert result is None
        assert len(buffer) == 0  # Buffer should be cleared

    def test_header_only_waits(self, buffer):
        """Header without payload returns None"""
        # Just the 4-byte length header indicating 100 bytes payload
        buffer.add_data(struct.pack('!I', 100))

        result = buffer.extract_message()
        assert result is None
        assert len(buffer) == 4  # Header still in buffer

    def test_len_returns_buffer_size(self, buffer):
        """__len__ returns current buffer size"""
        assert len(buffer) == 0

        buffer.add_data(b"12345")
        assert len(buffer) == 5

        buffer.add_data(b"67890")
        assert len(buffer) == 10

    def test_fragmented_receive_simulation(self, buffer, protocol):
        """Simulate fragmented network receives"""
        message = protocol.encode_message(MessageType.PING, {"key": "value" * 100})

        # Simulate receiving in small chunks (like real network)
        chunk_size = 10
        for i in range(0, len(message), chunk_size):
            chunk = message[i:i+chunk_size]
            buffer.add_data(chunk)

            # Try to extract (should only succeed on last chunk)
            if i + chunk_size >= len(message):
                extracted = buffer.extract_message()
                assert extracted == message
            else:
                extracted = buffer.extract_message()
                assert extracted is None
