# -*- coding: utf-8 -*-
"""
Whole-game state snapshots for multiplayer.

One format for every "this is the true state now" message that the host / turn owner
sends to the other PCs. It replaces hand-maintained field lists (FULL_STATE_SYNC,
SIM_ROUND_COMPLETE), which kept missing fields - turn number, tech limits, Captain
discount, player stats, ...

Built on the campaign save serializer (save_manager.serialize_game_state /
deserialize_game_state): a GameState field added there for saves reaches multiplayer
too, so the two can never drift apart. Differences from a save:
- chat_messages and messages (the Action Log) are left out - every PC keeps its own:
  chat is sent as it is typed, and the Action Log is filtered per viewer;
- player_is_ai is included - the AI takes over a disconnected player mid-game;
- applying a snapshot clears in-flight execution state (animations, arrivals, pending
  battles, the turn-advance flag) - snapshots are taken at quiet points - and refreshes
  every derived cache (income, army totals, territorial bonuses, overlays).

Simultaneous-mode round state (sim_state: round number, readiness, overflow
territories) is not part of GameState and travels separately.
"""

from save_manager import deserialize_game_state, serialize_game_state
from utils.logger import get_logger

logger = get_logger(__name__)

# Bump when the format changes in a way older code cannot read
SNAPSHOT_VERSION = 1

# Kept per PC, never overwritten by a snapshot
_PER_VIEWER_KEYS = ('chat_messages', 'messages')


def build_snapshot(gs):
    """
    The complete game state as a JSON-safe dict.

    Args:
        gs: GameState

    Returns:
        dict: snapshot (send it in a network message; apply with apply_snapshot)
    """
    data = serialize_game_state(gs)
    for key in _PER_VIEWER_KEYS:
        data.pop(key, None)
    data['player_is_ai'] = [bool(flag) for flag in gs.player_is_ai]
    data['snapshot_version'] = SNAPSHOT_VERSION
    return data


def apply_snapshot(gs, data):
    """
    Make `gs` exactly the state in `data` (from build_snapshot on another PC).

    Args:
        gs: GameState of the same game (same map and player count)
        data: snapshot dict

    Raises:
        ValueError: not a snapshot this version can read
    """
    if not isinstance(data, dict) or data.get('snapshot_version') != SNAPSHOT_VERSION:
        version = data.get('snapshot_version') if isinstance(data, dict) else None
        raise ValueError(f"Unsupported game state snapshot (version {version!r})")

    # Never let a snapshot replace this PC's chat / Action Log
    state = {key: value for key, value in data.items() if key not in _PER_VIEWER_KEYS}
    deserialize_game_state(gs, state)

    player_is_ai = data.get('player_is_ai')
    if isinstance(player_is_ai, list) and len(player_is_ai) == gs.num_players:
        gs.player_is_ai = [bool(flag) for flag in player_is_ai]

    # In-flight execution state belongs to the moment before the snapshot
    gs.active_animations = []
    gs.pending_arrivals = []
    gs.pending_battles = []
    gs.ready_to_advance_turn = False

    # The garrisons are the source of truth: rebuild the legacy army counters from them
    for territory in list(gs.territory_garrisons):
        gs.sync_legacy_garrison_data(territory)

    # Derived caches (deserialize_game_state refreshes the overlay versions and the
    # territorial bonus cache; income and army totals were left stale)
    gs.invalidate_income_cache()
    gs.invalidate_army_count_cache()
    gs.invalidate_territorial_bonus_cache()
    logger.debug(f"[SNAPSHOT] Applied state of turn {gs.turn_number} ({gs.turn_phase})")
