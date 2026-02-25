"""
Network package for multiplayer functionality.

Provides client-server networking infrastructure for 1v1 multiplayer mode.
"""

from .protocol import NetworkProtocol
from .message_queue import NetworkMessageQueue
from .server import NetworkServer
from .client import NetworkClient
from .upnp import UPnPManager

__all__ = ['NetworkProtocol', 'NetworkMessageQueue', 'NetworkServer', 'NetworkClient', 'UPnPManager']
