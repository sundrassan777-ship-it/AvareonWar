# -*- coding: utf-8 -*-
# simultaneous/sim_debug.py
# Debug Logging System for Simultaneous Multiplayer Mode

"""
SimDebug - Centralized Debug Logging for Simultaneous Mode
===========================================================

Provides configurable logging levels and formatted output for debugging
multiplayer synchronization issues in simultaneous turn mode.

Usage:
    from .sim_debug import sim_log, SimDebugLevel, set_debug_level

    # Log at different levels
    sim_log.state("Player 1 marked ready")
    sim_log.phase("Entering execution phase")
    sim_log.sync("Gold synced: 50 -> 55")
    sim_log.network("Received SIM_ALL_READY")
    sim_log.battle("Battle at Riverdale: 3 players")
    sim_log.detail("Unit composition: {Swordsman: 3, Archer: 2}")

    # Change log level
    set_debug_level(SimDebugLevel.SYNC)  # Only show sync-related issues

Log Levels (from most to least verbose):
    ALL     - Everything (very verbose)
    DETAIL  - Detailed execution info
    PHASE   - Phase transitions
    STATE   - State changes (ready, orders)
    SYNC    - Sync-related messages (critical for multiplayer debugging)
    BATTLE  - Battle resolution
    NETWORK - Network messages
    ERROR   - Errors only
    NONE    - Disabled
"""

from enum import IntEnum
from typing import Optional, Any
import time

from utils.logger import get_logger

logger = get_logger(__name__)


class SimDebugLevel(IntEnum):
    """Debug verbosity levels."""
    NONE = 0      # No output
    ERROR = 1     # Errors only
    NETWORK = 2   # Network messages
    SYNC = 3      # Sync-critical messages
    BATTLE = 4    # Battle resolution
    STATE = 5     # State changes
    PHASE = 6     # Phase transitions
    DETAIL = 7    # Detailed info
    ALL = 8       # Everything


class SimDebugConfig:
    """Configuration for debug logging."""

    # Current log level
    level: SimDebugLevel = SimDebugLevel.ALL

    # Enable specific categories regardless of level
    force_categories: set = set()

    # Disable specific categories regardless of level
    mute_categories: set = set()

    # Show timestamps
    show_timestamps: bool = False

    # Show round numbers
    show_round: bool = True

    # Current round number (updated by sim_state)
    current_round: int = 0

    # Is multiplayer mode
    is_multiplayer: bool = False

    # Is host (vs client)
    is_host: bool = False


# Global config instance
_config = SimDebugConfig()


def set_debug_level(level: SimDebugLevel):
    """Set the global debug level."""
    _config.level = level


def get_debug_level() -> SimDebugLevel:
    """Get the current debug level."""
    return _config.level


def set_multiplayer_context(is_multiplayer: bool, is_host: bool):
    """Set multiplayer context for log prefixes."""
    _config.is_multiplayer = is_multiplayer
    _config.is_host = is_host


def set_round(round_number: int):
    """Update current round number for log context."""
    _config.current_round = round_number


def force_category(category: str):
    """Force a category to always log regardless of level."""
    _config.force_categories.add(category)


def mute_category(category: str):
    """Mute a category so it never logs."""
    _config.mute_categories.add(category)


def unmute_category(category: str):
    """Unmute a previously muted category."""
    _config.mute_categories.discard(category)


def enable_timestamps(enabled: bool = True):
    """Enable or disable timestamps in output."""
    _config.show_timestamps = enabled


class SimLogger:
    """
    Logger class with category-specific methods.

    Each method corresponds to a log category and level.
    """

    def _log(self, category: str, level: SimDebugLevel, message: str,
             data: Optional[Any] = None, indent: int = 0):
        """
        Internal log method.

        Args:
            category: Log category (STATE, PHASE, etc.)
            level: Required level to show this message
            message: Log message
            data: Optional data to include
            indent: Indentation level (for nested output)
        """
        # Check if muted
        if category in _config.mute_categories:
            return

        # Check level (or if category is forced)
        if category not in _config.force_categories:
            if _config.level < level:
                return

        # Build prefix
        prefix_parts = []

        # Timestamp
        if _config.show_timestamps:
            prefix_parts.append(f"[{time.strftime('%H:%M:%S')}]")

        # Round number
        if _config.show_round and _config.current_round > 0:
            prefix_parts.append(f"[R{_config.current_round}]")

        # Multiplayer context
        if _config.is_multiplayer:
            role = "HOST" if _config.is_host else "CLIENT"
            prefix_parts.append(f"[{role}]")

        # Category
        prefix_parts.append(f"[SIM_{category}]")

        # Build full prefix
        prefix = " ".join(prefix_parts)

        # Indentation
        indent_str = "  " * indent

        # Format message
        if data is not None:
            logger.debug(f"{prefix}{indent_str} {message}: {data}")
        else:
            logger.debug(f"{prefix}{indent_str} {message}")

    # === Category-specific log methods ===

    def error(self, message: str, data: Optional[Any] = None):
        """Log errors (always shown unless NONE level)."""
        self._log("ERROR", SimDebugLevel.ERROR, f"ERROR: {message}", data)

    def network(self, message: str, data: Optional[Any] = None):
        """Log network messages (sent/received)."""
        self._log("NETWORK", SimDebugLevel.NETWORK, message, data)

    def network_send(self, msg_type: str, data: Optional[Any] = None):
        """Log outgoing network message."""
        self._log("NETWORK", SimDebugLevel.NETWORK, f">> SEND {msg_type}", data)

    def network_recv(self, msg_type: str, data: Optional[Any] = None):
        """Log incoming network message."""
        self._log("NETWORK", SimDebugLevel.NETWORK, f"<< RECV {msg_type}", data)

    def sync(self, message: str, data: Optional[Any] = None):
        """Log sync-critical messages (state corrections, authoritative updates)."""
        self._log("SYNC", SimDebugLevel.SYNC, message, data)

    def sync_correction(self, field: str, player: int, old_val: Any, new_val: Any):
        """Log a sync correction being applied."""
        self._log("SYNC", SimDebugLevel.SYNC,
                 f"CORRECTION Player {player} {field}: {old_val} -> {new_val}")

    def sync_match(self, field: str, player: int, value: Any):
        """Log when a sync value matches (no correction needed)."""
        self._log("SYNC", SimDebugLevel.DETAIL,
                 f"MATCH Player {player} {field}: {value}")

    def battle(self, message: str, data: Optional[Any] = None):
        """Log battle resolution."""
        self._log("BATTLE", SimDebugLevel.BATTLE, message, data)

    def battle_result(self, territory: str, winner: int, survivors: int,
                      compositions: Optional[dict] = None):
        """Log battle result with details."""
        msg = f"Battle at {territory}: Winner=P{winner}, Survivors={survivors}"
        self._log("BATTLE", SimDebugLevel.BATTLE, msg, compositions)

    def state(self, message: str, data: Optional[Any] = None):
        """Log state changes (ready flags, orders, etc.)."""
        self._log("STATE", SimDebugLevel.STATE, message, data)

    def ready(self, player_id: int, ready_flags: dict):
        """Log player ready state change."""
        waiting = [p for p, r in ready_flags.items() if not r]
        self._log("STATE", SimDebugLevel.STATE,
                 f"Player {player_id} marked ready. Waiting on: {waiting}")

    def order(self, player_id: int, order_type: str, details: str):
        """Log order added/executed."""
        self._log("STATE", SimDebugLevel.STATE,
                 f"Player {player_id} order: {order_type} - {details}")

    def phase(self, message: str, data: Optional[Any] = None):
        """Log phase transitions."""
        self._log("PHASE", SimDebugLevel.PHASE, message, data)

    def phase_change(self, old_phase: str, new_phase: str):
        """Log phase transition."""
        self._log("PHASE", SimDebugLevel.PHASE,
                 f"Phase: {old_phase} -> {new_phase}")

    def detail(self, message: str, data: Optional[Any] = None, indent: int = 0):
        """Log detailed execution info (verbose)."""
        self._log("DETAIL", SimDebugLevel.DETAIL, message, data, indent)

    def ai(self, player_id: int, message: str, data: Optional[Any] = None):
        """Log AI decisions."""
        self._log("AI", SimDebugLevel.DETAIL, f"AI P{player_id}: {message}", data)

    def conflict(self, message: str, data: Optional[Any] = None):
        """Log conflict resolution (crossing armies, etc.)."""
        self._log("CONFLICT", SimDebugLevel.BATTLE, message, data)

    def alliance(self, message: str, data: Optional[Any] = None):
        """Log alliance handler actions."""
        self._log("ALLIANCE", SimDebugLevel.STATE, message, data)

    # === Summary/diagnostic methods ===

    def state_summary(self, sim_state):
        """Log a summary of current state (for debugging sync issues)."""
        self._log("SYNC", SimDebugLevel.SYNC, "=== STATE SUMMARY ===")

        # Round and phase
        self._log("SYNC", SimDebugLevel.SYNC,
                 f"Round: {sim_state.round_number}, Phase: {sim_state.sim_phase}")

        # Ready states
        waiting = [p for p, r in sim_state.players_ready.items() if not r]
        self._log("SYNC", SimDebugLevel.SYNC, f"Waiting players: {waiting}")

        # Gold
        gold_str = ", ".join([f"P{p}:{g}" for p, g in enumerate(sim_state.gs.player_gold)])
        self._log("SYNC", SimDebugLevel.SYNC, f"Gold: {gold_str}")

        # Eliminated
        if sim_state.eliminated_players:
            self._log("SYNC", SimDebugLevel.SYNC,
                     f"Eliminated: {sim_state.eliminated_players}")

    def order_summary(self, player_orders: dict):
        """Log a summary of all queued orders."""
        self._log("STATE", SimDebugLevel.STATE, "=== ORDER SUMMARY ===")

        for player_id, orders in player_orders.items():
            if not orders:
                continue

            order_types = {}
            for order in orders:
                otype = order.get('type', 'unknown')
                order_types[otype] = order_types.get(otype, 0) + 1

            types_str = ", ".join([f"{t}:{c}" for t, c in order_types.items()])
            self._log("STATE", SimDebugLevel.STATE, f"Player {player_id}: {types_str}")


# Global logger instance
sim_log = SimLogger()


# === Convenience functions for quick enable/disable ===

def enable_verbose():
    """Enable all debug output."""
    set_debug_level(SimDebugLevel.ALL)


def enable_sync_only():
    """Only show sync-related messages (for debugging multiplayer issues)."""
    set_debug_level(SimDebugLevel.SYNC)


def enable_network_only():
    """Only show network messages."""
    set_debug_level(SimDebugLevel.NETWORK)


def disable_debug():
    """Disable all debug output."""
    set_debug_level(SimDebugLevel.NONE)


def enable_minimal():
    """Show only errors and sync corrections."""
    set_debug_level(SimDebugLevel.ERROR)
    force_category("SYNC")


# === Default: Enable all output (can be changed by calling set_debug_level) ===
# For production, call disable_debug() or enable_minimal()
