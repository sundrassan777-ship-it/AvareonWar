"""
Network package for multiplayer functionality.

Provides client-server networking infrastructure for multiplayer mode (up to 4 players).
"""

from .protocol import NetworkProtocol
from .message_queue import NetworkMessageQueue
from .server import NetworkServer
from .client import NetworkClient
from .upnp import UPnPManager

__all__ = ['NetworkProtocol', 'NetworkMessageQueue', 'NetworkServer', 'NetworkClient', 'UPnPManager']
