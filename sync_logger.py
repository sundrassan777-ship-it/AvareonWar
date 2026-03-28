"""
Sync Logger - Multiplayer state synchronization verification logging for AvareonWar.

Records every gameplay action, per-turn state snapshots, checksum comparisons,
and field-level desync diffs for multiplayer games. Each participant (host + clients)
writes their own log file so logs can be compared post-game.

Output: Logs/sync/{game_id}_P{player_index}_{host|client}_{date}.json

Architecture:
    - Actions appended to in-memory list (O(1) per action, no per-action I/O)
    - State snapshots captured at turn boundaries (same frequency as FULL_STATE_SYNC)
    - Checksum comparisons logged on both host and client
    - Desync diffs computed by host, sent back to client via DESYNC_DIFF message
    - Single file write at game end (same pattern as game_logger.py)

Hook points:
    - main.py _send_action_to_remote(): outgoing action logging
    - main.py _handle_network_message(): incoming action logging
    - main.py _send_full_state_sync() sites: turn boundary snapshots (host)
    - main.py STATE_CHECKSUM send sites: turn boundary snapshots (client)
    - main.py STATE_CHECKSUM handler: checksum comparison + desync detection (host)
    - main.py STATE_DETAIL_REQUEST/RESPONSE/DESYNC_DIFF: desync diff exchange
    - simultaneous/sim_state.py _advance_round(): sim mode turn snapshots
    - main.py show_recap_if_ended(): finalize and save
"""

import json
import os
import tempfile
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)

# Gameplay action types that should be logged (orders, execution, turn flow)
LOGGED_ACTION_TYPES = frozenset({
    'MOVEMENT_ORDER', 'BUILDING_ORDER', 'TRAINING_ORDER', 'ORDER_REMOVE',
    'RESEARCH_ORDER', 'HERO_TRAINING_ORDER',
    'EXECUTE_ORDERS', 'BATTLE_RESOLVE', 'TURN_END',
    'UNIT_COMPLETE', 'BUILDING_COMPLETE',
    'SIM_PLAYER_READY', 'SIM_ALL_READY', 'SIM_ALLIANCE_CHOICE',
    'SIM_HERO_ABILITY', 'SIM_BATTLE_RESULT', 'SIM_ROUND_COMPLETE',
})


class SyncLogger:
    """
    Records multiplayer action history, state snapshots, and desync events.

    Usage:
        sync_logger = SyncLogger(game_state, local_player_index, is_host, game_id)
        # ... game plays, hooks call record_* methods ...
        sync_logger.finalize_and_save()
    """

    def __init__(self, game_state, local_player_index, is_host, game_id=None):
        """
        Initialize the sync logger.

        Args:
            game_state: The GameState instance to snapshot state from
            local_player_index: This participant's player index
            is_host: True if this participant is the host
            game_id: Shared game ID (from GameLogger) for log file correlation
        """
        self.gs = game_state
        self.local_player_index = local_player_index
        self.is_host = is_host
        self.game_id = game_id or "00000000"
        self.start_time = datetime.now()

        # Sequential action counter for ordering
        self._action_seq = 0

        # Buffered data (written to file at game end)
        self.actions = []           # All gameplay actions this session
        self.turn_snapshots = {}    # {turn_number: state_snapshot_dict}
        self.checksum_log = []      # All checksum comparisons
        self.desync_events = []     # Desync diff records

        logger.info(f"SyncLogger initialized: game_id={self.game_id}, "
                     f"player={local_player_index}, host={is_host}")

    # ========== Action Recording ==========

    def record_action(self, action_type, player_index, turn_number, data, source):
        """
        Record a gameplay action (outgoing or incoming).

        Args:
            action_type: MessageType string (e.g. 'MOVEMENT_ORDER')
            player_index: Player who performed the action
            turn_number: Current turn/round number
            data: Raw message payload dict
            source: 'local' for outgoing, 'remote' for incoming
        """
        # Sync logger action recording for multiplayer state verification
        action_type_str = str(action_type)
        if action_type_str not in LOGGED_ACTION_TYPES:
            return

        elapsed = (datetime.now() - self.start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = elapsed % 60

        self.actions.append({
            'seq': self._action_seq,
            'timestamp': f"{minutes:02d}:{seconds:06.3f}",
            'turn': turn_number,
            'type': action_type_str,
            'player': player_index,
            'source': source,
            'data': _sanitize_data(data),
        })
        self._action_seq += 1

    # ========== Turn Snapshots ==========

    def record_turn_snapshot(self, turn_number):
        """
        Record comprehensive state snapshot at a turn boundary.

        Called at the same points as FULL_STATE_SYNC (host) or STATE_CHECKSUM (client).
        """
        # Sync logger turn snapshot for multiplayer state verification
        snapshot = self.build_state_detail()
        # Also compute checksum for quick comparison
        snapshot['_checksum'] = self.gs.calculate_state_checksum()
        self.turn_snapshots[str(turn_number)] = snapshot
        logger.debug(f"SyncLogger: recorded turn snapshot for turn {turn_number}")

    # ========== Checksum Logging ==========

    def record_checksum(self, turn_number, local_checksum, remote_checksum=None, match=None):
        """
        Record a checksum comparison event.

        Args:
            turn_number: Turn when checksum was computed
            local_checksum: This participant's checksum
            remote_checksum: Other participant's checksum (if known)
            match: True/False/None if comparison result is known
        """
        self.checksum_log.append({
            'turn': turn_number,
            'local': local_checksum,
            'remote': remote_checksum,
            'match': match,
        })

    # ========== Desync Recording ==========

    def record_desync(self, turn_number, diff):
        """
        Record a desync event with field-level diff.

        Args:
            turn_number: Turn when desync was detected
            diff: Dict of divergent fields {field: {host: val, client: val}}
        """
        # Sync logger desync event for multiplayer state verification
        self.desync_events.append({
            'turn': turn_number,
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'diff': diff,
        })
        logger.warning(f"SyncLogger: desync recorded at turn {turn_number}, "
                       f"{len(diff)} divergent fields")

    # ========== State Detail / Diff ==========

    def build_state_detail(self):
        """
        Build a JSON-serializable dict of ALL critical game state.

        Used for desync diff computation. Covers all fields from FULL_STATE_SYNC
        plus fields the checksum covers. Matches the serialization patterns
        from _send_full_state_sync() in main.py.

        Returns:
            dict: Complete critical state snapshot
        """
        gs = self.gs
        return {
            'current_player': gs.current_player,
            'turn_number': gs.turn_number,
            'turn_phase': gs.turn_phase,
            'player_gold': list(gs.player_gold),
            'territory_owners': dict(sorted(gs.territory_owners.items())),
            # Garrisons: strip 'order' field from unit dicts (not JSON-serializable)
            'territory_garrisons': _serialize_garrisons(gs.territory_garrisons),
            # Legacy army counters (kept for checksum compatibility)
            'armies': dict(sorted(gs.armies.items())),
            'armies_moved': dict(sorted(gs.armies_moved.items())),
            'armies_unmoved': dict(sorted(gs.armies_unmoved.items())),
            # Buildings
            'buildings': {t: dict(sorted(plots.items()))
                          for t, plots in sorted(gs.buildings.items())},
            'under_construction': {t: {str(p): list(e) for p, e in sorted(plots.items())}
                                   for t, plots in sorted(gs.under_construction.items()) if plots},
            'castle_upgrades': {t: dict(sorted(plots.items()))
                                for t, plots in sorted(gs.castle_upgrades.items()) if plots},
            'castle_upgrades_in_progress': {t: dict(sorted(plots.items()))
                                            for t, plots in sorted(gs.castle_upgrades_in_progress.items()) if plots},
            'building_xp': {t: dict(sorted(plots.items()))
                            for t, plots in sorted(gs.building_xp.items()) if plots},
            # Training
            'training_queue': {t: {str(p): [list(e) for e in q] for p, q in sorted(plots.items())}
                               for t, plots in sorted(gs.training_queue.items()) if plots},
            # Heroes
            'heroes': {str(k): _serialize_hero_data(v) for k, v in sorted(gs.heroes.items()) if v},
            'hero_training_queue': {t: {str(p): list(e) for p, e in sorted(plots.items())}
                                    for t, plots in sorted(gs.hero_training_queue.items()) if plots},
            'hero_ability_cooldowns': {str(pid): dict(cds)
                                       for pid, cds in sorted(gs.hero_ability_cooldowns.items()) if cds},
            'hero_silence_status': {str(pid): status
                                    for pid, status in sorted(gs.hero_silence_status.items()) if status},
            'hero_ownership': {str(pid): sorted(list(owned))
                               for pid, owned in sorted(gs.hero_ownership.items()) if owned},
            # Technology
            'tech_researched': {str(pid): sorted(list(techs))
                                for pid, techs in sorted(gs.player_tech_researched.items()) if techs},
            'research_in_progress': {str(pid): research
                                     for pid, research in sorted(gs.research_in_progress.items()) if research},
            'tech_available': {str(pid): sorted(list(techs))
                               for pid, techs in sorted(gs.player_tech_available.items()) if techs},
            # Tech effect arrays
            'tech_effects': {
                'royal_decree_discount': list(gs.player_royal_decree_discount),
                'training_cost_discount': list(gs.player_training_cost_discount),
                'cavalry_cost_discount': list(gs.player_cavalry_cost_discount),
                'captain_cost_discount': list(gs.player_captain_cost_discount),
                'archer_keep_strength_bonus': list(gs.player_archer_keep_strength_bonus),
                'farm_destruction_gold_bonus': list(gs.player_farm_destruction_gold_bonus),
                'cavalry_strength_bonus': list(gs.player_cavalry_strength_bonus),
                'divide_conquer_bonus': list(gs.player_divide_conquer_bonus),
                'barracks_cost_discount': list(gs.player_barracks_cost_discount),
                'barracks_full_refund': list(gs.player_barracks_full_refund),
                'hero_keep_defense_bonus': list(gs.player_hero_keep_defense_bonus),
            },
            # Elimination
            'eliminated_players': sorted(list(gs.eliminated_players)),
            'disconnect_eliminations': sorted(list(gs.disconnect_eliminations)),
            # Transient hero ability state
            'embargo_blocked_players': list(gs.embargo_blocked_players),
            'player_master_negotiator_active': list(gs.player_master_negotiator_active),
        }

    @staticmethod
    def compute_state_diff(state_a, state_b):
        """
        Compute field-level diff between two state detail dicts.

        Args:
            state_a: Host's state detail dict
            state_b: Client's state detail dict

        Returns:
            dict: {field_path: {'host': val_a, 'client': val_b}} for divergent fields only.
                  Empty dict if states match.
        """
        diff = {}
        _diff_recursive(state_a, state_b, '', diff)
        return diff

    # ========== Finalization ==========

    def finalize_and_save(self):
        """
        Build the final JSON log and save to Logs/sync/ folder.

        Called from show_recap_if_ended() in main.py after the game ends.
        Uses atomic file writes (tempfile + os.replace) for safety.
        """
        try:
            role = 'host' if self.is_host else 'client'

            # Build metadata
            meta = {
                'game_id': self.game_id,
                'participant': role,
                'player_index': self.local_player_index,
                'player_name': self.gs.get_player_name(self.local_player_index),
                'date': self.start_time.strftime('%Y-%m-%d'),
                'start_time': self.start_time.strftime('%H:%M:%S'),
                'num_players': self.gs.num_players,
                'game_mode': self.gs.game_mode,
                'total_turns': self.gs.turn_number,
            }

            # Build final log structure
            log_data = {
                'meta': meta,
                'actions': self.actions,
                'turn_snapshots': self.turn_snapshots,
                'checksum_log': self.checksum_log,
                'desync_events': self.desync_events,
            }

            self._write_log_file(log_data, role)

        except Exception as e:
            logger.error(f"SyncLogger: failed to finalize and save: {e}")

    def _write_log_file(self, log_data, role):
        """Write log JSON to Logs/sync/ folder with atomic file write."""
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        logs_dir = os.path.join(base_dir, 'Logs', 'sync')
        os.makedirs(logs_dir, exist_ok=True)

        date_str = self.start_time.strftime('%Y-%m-%d')
        filename = f"{self.game_id}_P{self.local_player_index}_{role}_{date_str}.json"
        filepath = os.path.join(logs_dir, filename)

        # Atomic write: write to temp file then rename
        try:
            fd, tmp_path = tempfile.mkstemp(dir=logs_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, filepath)
                logger.info(f"SyncLogger: log saved to {filepath}")
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        except Exception as e:
            logger.error(f"SyncLogger: failed to write log file: {e}")


# ========== Helper Functions ==========

def _sanitize_data(data):
    """
    Sanitize message data for JSON serialization.

    Strips non-serializable fields and truncates very large values
    to keep log files manageable.
    """
    if not isinstance(data, dict):
        return data
    sanitized = {}
    for key, value in data.items():
        # Skip 'order' fields (contain MovementOrder objects)
        if key == 'order':
            continue
        # Truncate very large nested structures (e.g. full state payloads)
        if isinstance(value, dict) and len(str(value)) > 5000:
            sanitized[key] = f"<truncated dict, {len(value)} keys>"
        elif isinstance(value, list) and len(str(value)) > 5000:
            sanitized[key] = f"<truncated list, {len(value)} items>"
        else:
            sanitized[key] = value
    return sanitized


def _serialize_garrisons(territory_garrisons):
    """Serialize garrisons, stripping non-serializable 'order' fields from unit dicts."""
    result = {}
    for territory, player_garrisons in sorted(territory_garrisons.items()):
        result[territory] = {}
        for player_id, garrison_data in sorted(player_garrisons.items(),
                                                key=lambda x: str(x[0])):
            if 'units' in garrison_data:
                result[territory][str(player_id)] = {
                    **garrison_data,
                    'units': [
                        {k: (None if k == 'order' else v) for k, v in unit.items()}
                        for unit in garrison_data.get('units', [])
                    ]
                }
            else:
                result[territory][str(player_id)] = dict(garrison_data)
    return result


def _serialize_hero_data(hero_dict):
    """Serialize hero data dict, converting any non-serializable values."""
    result = {}
    for hero_type, hero_data in sorted(hero_dict.items()):
        if isinstance(hero_data, dict):
            # Strip any non-serializable fields from hero data
            result[hero_type] = {k: v for k, v in hero_data.items()
                                 if not callable(v)}
        else:
            result[hero_type] = hero_data
    return result


def _diff_recursive(a, b, path, diff):
    """
    Recursively compare two values and record differences.

    Args:
        a: Value from state A (host)
        b: Value from state B (client)
        path: Dot-separated field path for human-readable output
        diff: Dict to accumulate differences into
    """
    if type(a) != type(b):
        diff[path or '<root>'] = {'host': a, 'client': b}
        return

    if isinstance(a, dict):
        all_keys = set(list(a.keys()) + list(b.keys()))
        for key in sorted(all_keys, key=str):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in a:
                diff[child_path] = {'host': '<missing>', 'client': b[key]}
            elif key not in b:
                diff[child_path] = {'host': a[key], 'client': '<missing>'}
            else:
                _diff_recursive(a[key], b[key], child_path, diff)
    elif isinstance(a, list):
        if a != b:
            # For short lists, show full values; for long lists, show element diffs
            if len(a) <= 10 and len(b) <= 10:
                diff[path or '<root>'] = {'host': a, 'client': b}
            else:
                # Compare element by element
                max_len = max(len(a), len(b))
                for i in range(max_len):
                    child_path = f"{path}[{i}]"
                    if i >= len(a):
                        diff[child_path] = {'host': '<missing>', 'client': b[i]}
                    elif i >= len(b):
                        diff[child_path] = {'host': a[i], 'client': '<missing>'}
                    elif a[i] != b[i]:
                        _diff_recursive(a[i], b[i], child_path, diff)
    else:
        if a != b:
            diff[path or '<root>'] = {'host': a, 'client': b}
