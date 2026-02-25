"""
Thread-safe message queues for network communication.

Provides bidirectional queues between game loop thread and network I/O thread.
"""

import queue
import threading
from typing import Dict, Any, Optional

from utils.logger import get_logger
logger = get_logger(__name__)


class NetworkMessageQueue:
    """
    Thread-safe message queue system for network communication.

    Provides two queues:
    - send_queue: Game loop -> Network thread (outgoing messages)
    - recv_queue: Network thread -> Game loop (incoming messages)
    """

    # Maximum queue size to prevent memory exhaustion from message flooding
    MAX_QUEUE_SIZE = 1000

    def __init__(self):
        # Queue for outgoing messages (game loop -> network thread)
        # Size-limited to prevent memory exhaustion from flooding
        self.send_queue = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)

        # Queue for incoming messages (network thread -> game loop)
        # Size-limited to prevent memory exhaustion from flooding
        self.recv_queue = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)

        # Lock for thread-safe operations
        self.lock = threading.Lock()

        # Connection state
        self._connected = False
        self._error = None

    def send_message(self, message: bytes):
        """
        Add a message to the send queue (non-blocking).

        If the queue is full, the message is dropped to prevent memory
        exhaustion from flooding. A warning is logged when this occurs.

        Args:
            message: Encoded message bytes to send

        Called by game loop thread to send messages.
        """
        try:
            self.send_queue.put_nowait(message)
        except queue.Full:
            logger.warning("Send queue full (maxsize=%d) - dropping outgoing message", self.MAX_QUEUE_SIZE)

    def get_outgoing_message(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Get next outgoing message from send queue (blocking with timeout).

        Args:
            timeout: Maximum time to wait in seconds (None = block indefinitely)

        Returns:
            Message bytes, or None if timeout

        Called by network thread to get messages to send.
        """
        try:
            return self.send_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def receive_message(self, message: Dict[str, Any]):
        """
        Add a decoded message to the receive queue (non-blocking).

        If the queue is full, the message is dropped to prevent memory
        exhaustion from flooding. A warning is logged when this occurs.

        Args:
            message: Decoded message dict

        Called by network thread when message is received.
        """
        try:
            self.recv_queue.put_nowait(message)
        except queue.Full:
            logger.warning("Receive queue full (maxsize=%d) - dropping incoming message", self.MAX_QUEUE_SIZE)

    def get_incoming_message(self) -> Optional[Dict[str, Any]]:
        """
        Get next incoming message from receive queue (non-blocking).

        Returns:
            Decoded message dict, or None if queue is empty

        Called by game loop thread to process incoming messages.
        """
        try:
            return self.recv_queue.get_nowait()
        except queue.Empty:
            return None

    def set_connected(self, connected: bool):
        """Set connection state (thread-safe)"""
        with self.lock:
            self._connected = connected

    def is_connected(self) -> bool:
        """Check if connected (thread-safe)"""
        with self.lock:
            return self._connected

    def set_error(self, error: str):
        """Set error state (thread-safe)"""
        with self.lock:
            self._error = error

    def get_error(self) -> Optional[str]:
        """Get error state (thread-safe)"""
        with self.lock:
            return self._error

    def clear(self):
        """Clear all queues and reset state"""
        with self.lock:
            # Clear send queue
            while not self.send_queue.empty():
                try:
                    self.send_queue.get_nowait()
                except queue.Empty:
                    break

            # Clear receive queue
            while not self.recv_queue.empty():
                try:
                    self.recv_queue.get_nowait()
                except queue.Empty:
                    break

            self._connected = False
            self._error = None

    def has_outgoing_messages(self) -> bool:
        """Check if send queue has messages waiting"""
        return not self.send_queue.empty()

    def has_incoming_messages(self) -> bool:
        """Check if receive queue has messages waiting"""
        return not self.recv_queue.empty()

    def send_queue_size(self) -> int:
        """Get send queue size"""
        return self.send_queue.qsize()

    def recv_queue_size(self) -> int:
        """Get receive queue size"""
        return self.recv_queue.qsize()
