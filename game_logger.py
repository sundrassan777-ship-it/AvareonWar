"""
Game Logger - Per-game logging system for AvareonWar.

Creates a JSON log file for each custom/multiplayer game with:
- Game metadata (version, player count, turns, duration, win condition)
- Per-player per-turn data (heroes, tech, units, buildings, losses, territory control, battles)

Logs are saved to a Logs/ folder with naming: {8-digit-ID}_{YYYY-MM-DD}.json

Architecture:
    Hybrid data collection:
    - Snapshot-based: At each round boundary, compute deltas of cumulative player_stats
      for units built/lost. Snapshot territory_owners for regions controlled.
    - Event-based: Hero completion, tech completion, building completion, battle resolution
      are recorded as events with turn numbers.

Hook points:
    - game_state/__init__.py _advance_to_next_player(): round snapshot on full round
    - game_state/heroes.py finish_hero_training(): hero trained event
    - game_state/buildings.py finish_constructions(): building completed event
    - game_state/buildings.py finish_research(): tech researched event
    - game_state/military.py _update_battle_results(): battle resolved event
    - simultaneous/sim_state.py _advance_round(): round snapshot in sim mode
    - main.py: create logger at game start, finalize at game end
"""

import json
import os
import random
import tempfile
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)

# Stat keys in player_stats used for per-turn delta computation
_UNIT_STAT_KEYS = ['pikemen_trained', 'archers_trained', 'swordsmen_trained', 'cavalry_trained']
_LOSS_STAT_KEY = 'units_killed'


class GameLogger:
    """
    Records per-game data and writes a JSON log file at game end.

    Usage:
        logger = GameLogger(game_state)
        # ... game plays, hooks call record_* methods ...
        logger.finalize_and_save()
    """

    def __init__(self, game_state):
        """
        Initialize the game logger.

        Args:
            game_state: The GameState instance to log data from
        """
        self.gs = game_state

        # 8-digit random game ID
        self.game_id = f"{random.randint(10000000, 99999999)}"
        self.start_time = datetime.now()

        # Per-turn aggregated data: {turn_number: {player_index: {...}}}
        self.turn_data = {}

        # Event buffers (accumulated between round snapshots, flushed each snapshot)
        self._hero_events = []       # (player, hero_type, turn)
        self._tech_events = []       # (player, tech_id, turn)
        self._building_events = []   # (player, building_type, territory, turn)
        self._battle_events = []     # (territory, participants_dict, winner, turn)

        # All-time hero/tech event lists (for the final per-player summary)
        self._all_hero_events = []
        self._all_tech_events = []

        # Previous snapshot of player_stats for delta computation
        self._prev_stats = self._snapshot_stats()

        logger.info(f"GameLogger initialized: game_id={self.game_id}")

    def _snapshot_stats(self):
        """Take a snapshot of relevant cumulative player_stats for delta computation."""
        snapshot = {}
        for p in range(self.gs.num_players):
            stats = self.gs.player_stats.get(p, {})
            snapshot[p] = {
                key: stats.get(key, 0)
                for key in _UNIT_STAT_KEYS + [_LOSS_STAT_KEY]
            }
        return snapshot

    def _count_territories(self):
        """Count territories controlled per player."""
        counts = {p: 0 for p in range(self.gs.num_players)}
        for owner in self.gs.territory_owners.values():
            if 0 <= owner < self.gs.num_players:
                counts[owner] += 1
        return counts

    # ========== Event Recording Methods ==========

    def record_round_snapshot(self, turn_number):
        """
        Record a snapshot at the end of a full round (all players acted once).

        Computes stat deltas, territory counts, and merges buffered events
        for the completed turn. Called from _advance_to_next_player() when
        current_player wraps to 0, or from sim_state._advance_round().
        """
        # Compute deltas from previous snapshot
        current_stats = self._snapshot_stats()
        territory_counts = self._count_territories()

        # Build per-player turn record
        turn_record = {}
        for p in range(self.gs.num_players):
            prev = self._prev_stats.get(p, {})
            curr = current_stats.get(p, {})

            # Units built this turn (delta of trained counters)
            units_built = {}
            for key in _UNIT_STAT_KEYS:
                delta = curr.get(key, 0) - prev.get(key, 0)
                if delta > 0:
                    # Convert stat key to display name: 'pikemen_trained' -> 'Pikeman'
                    unit_name = key.replace('_trained', '').capitalize()
                    # Fix plural -> singular display names
                    if unit_name == 'Pikemen':
                        unit_name = 'Pikeman'
                    elif unit_name == 'Archers':
                        unit_name = 'Archer'
                    elif unit_name == 'Swordsmen':
                        unit_name = 'Swordsman'
                    elif unit_name == 'Cavalry':
                        unit_name = 'Cavalry'
                    units_built[unit_name] = delta

            # Buildings built this turn (from buffered events)
            buildings_built = {}
            for bp, btype, _terr, bturn in self._building_events:
                if bp == p and bturn == turn_number:
                    buildings_built[btype] = buildings_built.get(btype, 0) + 1

            # Units lost this turn (delta)
            units_lost = curr.get(_LOSS_STAT_KEY, 0) - prev.get(_LOSS_STAT_KEY, 0)

            # Battles this turn (from buffered events)
            battles = []
            for b_terr, b_participants, b_winner, b_turn in self._battle_events:
                if b_turn == turn_number and p in b_participants:
                    # Find opponent(s)
                    opponents = [op for op in b_participants if op != p]
                    battles.append({
                        'territory': b_terr,
                        'opponent': opponents[0] if len(opponents) == 1 else opponents,
                        'won': b_winner == p
                    })

            turn_record[p] = {
                'units_built': units_built,
                'buildings_built': buildings_built,
                'units_lost': max(0, units_lost),
                'regions_controlled': territory_counts.get(p, 0),
                'battles': battles
            }

        self.turn_data[turn_number] = turn_record

        # Update previous snapshot for next delta
        self._prev_stats = current_stats

        # Clear per-turn event buffers (keep all-time lists)
        self._building_events.clear()
        self._battle_events.clear()

        logger.debug(f"GameLogger: recorded round snapshot for turn {turn_number}")

    def record_hero_trained(self, player_index, hero_type, turn_number):
        """Record a hero training completion event."""
        self._hero_events.append((player_index, hero_type, turn_number))
        self._all_hero_events.append((player_index, hero_type, turn_number))
        logger.debug(f"GameLogger: hero trained - Player {player_index + 1} "
                     f"trained {hero_type} on turn {turn_number}")

    def record_tech_researched(self, player_index, tech_id, turn_number):
        """Record a technology research completion event."""
        self._tech_events.append((player_index, tech_id, turn_number))
        self._all_tech_events.append((player_index, tech_id, turn_number))
        logger.debug(f"GameLogger: tech researched - Player {player_index + 1} "
                     f"researched {tech_id} on turn {turn_number}")

    def record_building_completed(self, player_index, building_type, territory, turn_number):
        """Record a building construction completion event (individual type: Farm, Mine, etc.)."""
        self._building_events.append((player_index, building_type, territory, turn_number))
        logger.debug(f"GameLogger: building completed - Player {player_index + 1} "
                     f"built {building_type} in {territory} on turn {turn_number}")

    def record_battle(self, territory, participants, winner, turn_number):
        """
        Record a battle resolution event.

        Args:
            territory: Territory name where battle occurred
            participants: Dict of {player_index: army_count} or list of player indices
            winner: Winning player index
            turn_number: Current turn/round number
        """
        # Normalize participants to a dict if it's a list
        if isinstance(participants, (list, set)):
            participants = {p: 0 for p in participants}
        self._battle_events.append((territory, participants, winner, turn_number))
        logger.debug(f"GameLogger: battle resolved - {territory}, "
                     f"winner=Player {winner + 1}, turn {turn_number}")

    # ========== Finalization ==========

    def finalize_and_save(self):
        """
        Build the final JSON log and save to Logs/ folder.

        Called from show_recap_if_ended() in main.py after the game ends.
        Uses atomic file writes (tempfile + os.replace) for safety.
        """
        try:
            duration_minutes = round(
                (datetime.now() - self.start_time).total_seconds() / 60, 1
            )

            # Determine turn count from game state
            # In sequential mode: turn_number. In sim mode: sim_state.round_number.
            total_turns = self.gs.turn_number
            if total_turns == 0 and self.turn_data:
                # Fallback: use highest recorded turn number
                total_turns = max(self.turn_data.keys())

            # Get winner name
            winner_name = None
            if self.gs.winner is not None and self.gs.winner >= 0:
                winner_name = self.gs.get_player_name(self.gs.winner)

            # Build game metadata
            from network_config import NETWORK_VERSION
            game_meta = {
                'game_id': self.game_id,
                'version': NETWORK_VERSION,
                'date': self.start_time.strftime('%Y-%m-%d'),
                'player_count': self.gs.num_players,
                'total_turns': total_turns,
                'duration_minutes': duration_minutes,
                'win_condition': self.gs.victory_condition,
                'winner': winner_name
            }

            # Build per-player data
            players = {}
            for p in range(self.gs.num_players):
                # Hero events for this player, sorted by turn
                hero_list = []
                player_hero_events = sorted(
                    [(ht, tn) for pi, ht, tn in self._all_hero_events if pi == p],
                    key=lambda x: x[1]
                )
                for idx, (hero_type, turn) in enumerate(player_hero_events):
                    hero_list.append({
                        'hero_type': hero_type,
                        'turn_trained': turn,
                        'first': idx == 0
                    })

                # Tech events for this player, sorted by turn
                tech_list = sorted(
                    [{'tech_id': tid, 'turn': tn}
                     for pi, tid, tn in self._all_tech_events if pi == p],
                    key=lambda x: x['turn']
                )

                # Per-turn data for this player
                per_turn = {}
                for turn_num, turn_record in sorted(self.turn_data.items()):
                    player_turn = turn_record.get(p, {})
                    per_turn[str(turn_num)] = player_turn

                players[str(p)] = {
                    'name': self.gs.get_player_name(p),
                    'is_ai': self.gs.player_is_ai[p],
                    'heroes': hero_list,
                    'tech_researched': tech_list,
                    'per_turn': per_turn
                }

            # Build final log
            log_data = {
                'game': game_meta,
                'players': players
            }

            # Save to Logs/ folder
            self._write_log_file(log_data)

        except Exception as e:
            logger.error(f"GameLogger: failed to finalize and save: {e}")

    def _write_log_file(self, log_data):
        """Write log JSON to Logs/ folder with atomic file write."""
        # Determine logs directory (relative to game root)
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        logs_dir = os.path.join(base_dir, 'Logs')
        os.makedirs(logs_dir, exist_ok=True)

        date_str = self.start_time.strftime('%Y-%m-%d')
        filename = f"{self.game_id}_{date_str}.json"
        filepath = os.path.join(logs_dir, filename)

        # Atomic write: write to temp file then rename (matches settings_manager pattern)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=logs_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, filepath)
                logger.info(f"GameLogger: log saved to {filepath}")
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        except Exception as e:
            logger.error(f"GameLogger: failed to write log file: {e}")
