"""
Test script for network connection.

Tests basic server-client connection and message exchange.
Usage:
  python test_network.py server    # Run as server
  python test_network.py client    # Run as client (connects to 127.0.0.1)
"""

import sys
import time

from network.server import NetworkServer
from network.client import NetworkClient
from network.protocol import NetworkProtocol
from network_config import MessageType


def test_server():
    """Test server mode"""
    print("=" * 60)
    print("NETWORK TEST - SERVER MODE")
    print("=" * 60)

    # Create and start server
    server = NetworkServer()
    if not server.start():
        print("Failed to start server")
        return

    print(f"Server listening on port {server.port}")
    print(f"Local IP: {server.get_local_ip()}")
    print("\nWaiting for client to connect...")
    print("Press Ctrl+C to stop")

    try:
        # Wait for client connection
        while not server.is_client_connected():
            time.sleep(0.1)

        print("\n✓ Client connected!")

        # Test message exchange
        protocol = NetworkProtocol()

        # Send a test message to client
        print("\nSending test message to client...")
        test_msg = protocol.encode_message("TEST_MESSAGE", {"content": "Hello from server!"})
        server.send_message(test_msg)

        # Wait for messages from client
        print("Waiting for messages from client...")
        message_count = 0
        while message_count < 3:  # Wait for 3 messages
            msg = server.message_queue.get_incoming_message()
            if msg:
                message_count += 1
                print(f"  Received message {message_count}: {msg}")

            time.sleep(0.1)

        print("\n✓ Test complete!")
        print("Press Ctrl+C to stop server")

        # Keep running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nStopping server...")
    finally:
        server.stop()


def test_client(host="127.0.0.1"):
    """Test client mode"""
    print("=" * 60)
    print("NETWORK TEST - CLIENT MODE")
    print("=" * 60)

    # Create client
    client = NetworkClient()

    print(f"Connecting to {host}...")

    # Connect to server
    if not client.connect(host, player_name="TestPlayer"):
        print("Failed to connect to server")
        return

    print(f"✓ Connected as Player {client.get_player_index() + 1}")

    try:
        # Test message exchange
        protocol = NetworkProtocol()

        # Wait a moment for server's test message
        time.sleep(0.5)

        # Check for messages from server
        print("\nChecking for messages from server...")
        msg = client.message_queue.get_incoming_message()
        if msg:
            print(f"  Received: {msg}")
        else:
            print("  No messages yet")

        # Send test messages to server
        print("\nSending test messages to server...")
        for i in range(3):
            test_msg = protocol.encode_message("TEST_MESSAGE", {
                "content": f"Hello from client! (message {i+1})"
            })
            client.send_message(test_msg)
            print(f"  Sent message {i+1}")
            time.sleep(0.5)

        print("\n✓ Test complete!")
        print("Press Ctrl+C to disconnect")

        # Keep running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nDisconnecting...")
    finally:
        client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_network.py server")
        print("  python test_network.py client [host]")
        print("\nExample:")
        print("  Terminal 1: python test_network.py server")
        print("  Terminal 2: python test_network.py client 127.0.0.1")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "server":
        test_server()
    elif mode == "client":
        host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        test_client(host)
    else:
        print(f"Unknown mode: {mode}")
        print("Use 'server' or 'client'")
        sys.exit(1)
