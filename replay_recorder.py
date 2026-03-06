"""
Replay Recorder - Records game state snapshots for replay playback.

Records full GameState snapshots at each player turn boundary (sequential mode)
or each round boundary (simultaneous mode). Snapshots are stored in memory and
saved to disk on demand from the Recap screen via "Save Replay" button.

Replay files are saved to a Replays/ folder with naming: {game_id}_{date}.replay.json

Architecture:
    State Snapshot approach (not action replay):
    - Records full game state at each turn boundary
    - Avoids RNG determinism issues (records outcomes, not inputs)
    - Enables arbitrary seeking in the replay viewer
    - No need to replay game logic — just load the snapshot

Hook points:
    - game_state/__init__.py _advance_to_next_player(): per-player-turn snapshot
    - simultaneous/sim_state.py _advance_round(): per-round snapshot in sim mode
    - recap_screen.py: "Save Replay" button triggers finalize_and_save()
    - main.py: create recorder at game start
"""

import json
import gzip
import os
import random
import tempfile
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)


class ReplayRecorder:
    """
    Records game state snapshots in memory during gameplay.

    Usage:
        recorder = ReplayRecorder(game_state)
        # ... game plays, hooks call record_snapshot() ...
        recorder.finalize_and_save()  # Called from Recap screen
    """

    def __init__(self, game_state):
        """
        Initialize the replay recorder.

        Args:
            game_state: The GameState instance to record from
        """
        self.gs = game_state

        # 8-digit random game ID
        self.game_id = f"{random.randint(10000000, 99999999)}"
        self.start_time = datetime.now()

        # In-memory snapshot storage: list of snapshot dicts
        self.snapshots = []

        # Per-snapshot event buffer (flushed into snapshot on record)
        self._event_buffer = []

        # Per-snapshot order buffer (movement orders active during this turn)
        self._order_buffer = []

        # Flag to track if replay was already saved
        self.saved = False

        # Record initial state (turn 0, before any actions)
        self._record_initial_snapshot()

        logger.info(f"ReplayRecorder initialized: game_id={self.game_id}")

    def _record_initial_snapshot(self):
        """Record the initial game state before any player acts."""
        snapshot = {
            'turn': 0,
            'current_player': self.gs.current_player,
            'state': self._serialize_state(),
            'events': [],
            'orders': [],
            'messages': list(self.gs.messages),
        }
        self.snapshots.append(snapshot)

    # ========== Event Recording Methods ==========

    def buffer_event(self, event_type, **kwargs):
        """
        Buffer a game event to be included in the next snapshot.

        Args:
            event_type: Event type string (e.g., 'battle', 'building_started',
                        'hero_trained', 'tech_researched', 'movement')
            **kwargs: Event-specific data
        """
        event = {'type': event_type}
        event.update(kwargs)
        self._event_buffer.append(event)

    def buffer_order(self, from_territory, to_territory, army_count, player,
                     intermediate_territory=None):
        """
        Buffer a movement order to be included in the next snapshot.

        Args:
            from_territory: Source territory name
            to_territory: Destination territory name
            army_count: Number of armies moving
            player: Player index issuing the order
            intermediate_territory: For 2-hop Captain movement (optional)
        """
        order = {
            'from': from_territory,
            'to': to_territory,
            'army_count': army_count,
            'player': player,
        }
        if intermediate_territory:
            order['intermediate'] = intermediate_territory
        self._order_buffer.append(order)

    def record_snapshot(self):
        """
        Record a full game state snapshot at a turn boundary.

        Called from _advance_to_next_player() (sequential) or
        _advance_round() (simultaneous). Captures state AFTER the
        turn's actions have resolved (income collected, buildings advanced, etc.).
        """
        snapshot = {
            'turn': self.gs.turn_number,
            'current_player': self.gs.current_player,
            'state': self._serialize_state(),
            'events': list(self._event_buffer),
            'orders': list(self._order_buffer),
            'messages': list(self.gs.messages),
        }
        self.snapshots.append(snapshot)

        # Clear event/order buffers for next turn
        self._event_buffer.clear()
        self._order_buffer.clear()

        logger.debug(f"ReplayRecorder: snapshot #{len(self.snapshots)} "
                     f"(turn {self.gs.turn_number}, player {self.gs.current_player})")

    # ========== State Serialization ==========

    def _serialize_state(self):
        """
        Serialize the full GameState to a JSON-compatible dict.

        Returns:
            dict: Complete game state snapshot
        """
        gs = self.gs
        state = {}

        # --- Territory ownership & armies ---
        state['territory_owners'] = dict(gs.territory_owners)
        state['armies'] = dict(gs.armies)
        state['armies_unmoved'] = dict(gs.armies_unmoved)
        state['armies_moved'] = dict(gs.armies_moved)

        # --- Multi-garrison system (deep copy with unit dicts) ---
        state['territory_garrisons'] = self._serialize_garrisons()

        # --- Economy ---
        state['player_gold'] = list(gs.player_gold)

        # --- Buildings ---
        # buildings: {territory: {plot_index: building_type}}
        state['buildings'] = {
            t: {str(k): v for k, v in plots.items()}
            for t, plots in gs.buildings.items()
        }

        # under_construction: {territory: {plot_index: (type, turns, cost)}}
        state['under_construction'] = {
            t: {str(k): list(v) for k, v in plots.items()}
            for t, plots in gs.under_construction.items()
        }

        # castle_upgrades: {territory: {plot_index: True}}
        state['castle_upgrades'] = {
            t: {str(k): v for k, v in plots.items()}
            for t, plots in gs.castle_upgrades.items()
        }

        # castle_upgrades_in_progress: {territory: {plot_index: turns_remaining}}
        state['castle_upgrades_in_progress'] = {
            t: {str(k): v for k, v in plots.items()}
            for t, plots in gs.castle_upgrades_in_progress.items()
        }

        # building_xp: {territory: {plot_index: {'xp': int, 'level': int}}}
        state['building_xp'] = {
            t: {str(k): dict(v) for k, v in plots.items()}
            for t, plots in gs.building_xp.items()
            if plots  # Skip empty
        }

        # --- Training ---
        # training_queue: {territory: {barracks_plot: [(unit_type, turns, cost), ...]}}
        state['training_queue'] = {
            t: {
                str(k): [list(entry) for entry in queue]
                for k, queue in plots.items()
            }
            for t, plots in gs.training_queue.items()
        }

        # hero_training_queue: {territory: {keep_plot: (hero_type, turns, cost)}}
        state['hero_training_queue'] = {
            t: {str(k): list(v) for k, v in plots.items()}
            for t, plots in gs.hero_training_queue.items()
        }

        # --- Heroes ---
        # heroes: {player_index: {hero_type: hero_data_dict}}
        state['heroes'] = {
            str(p): {ht: dict(hd) for ht, hd in heroes.items()}
            for p, heroes in gs.heroes.items()
        }

        # hero_ownership: {player_index: set(hero_types)} -> serialize sets as lists
        state['hero_ownership'] = {
            str(p): sorted(list(s)) for p, s in gs.hero_ownership.items()
        }

        # hero_ability_cooldowns: {player: {hero_type: {ability: turns_remaining}}}
        state['hero_ability_cooldowns'] = {
            str(p): {
                ht: dict(abilities)
                for ht, abilities in hero_cds.items()
            }
            for p, hero_cds in gs.hero_ability_cooldowns.items()
        }

        # hero_silence_status: {player: turns_remaining}
        state['hero_silence_status'] = {
            str(p): turns for p, turns in gs.hero_silence_status.items()
        }

        # --- Technology ---
        # player_tech_researched: {player: set(tech_ids)} -> serialize sets as lists
        state['player_tech_researched'] = {
            str(p): sorted(list(s)) for p, s in gs.player_tech_researched.items()
        }

        # player_tech_available: {player: set(tech_ids)} -> serialize sets as lists
        state['player_tech_available'] = {
            str(p): sorted(list(s)) for p, s in gs.player_tech_available.items()
        }

        # research_in_progress: {player: {'tech_id': str, 'turns_remaining': int, ...}}
        state['research_in_progress'] = {
            str(p): dict(r) for p, r in gs.research_in_progress.items()
            if r  # Skip empty/None
        }

        # --- Tech effect arrays (all per-player lists) ---
        state['player_hero_limit'] = list(gs.player_hero_limit)
        state['player_command_limit'] = list(gs.player_command_limit)
        state['player_royal_decree_discount'] = list(gs.player_royal_decree_discount)
        state['player_training_cost_discount'] = list(gs.player_training_cost_discount)
        state['player_cavalry_cost_discount'] = list(gs.player_cavalry_cost_discount)
        state['player_captain_cost_discount'] = list(gs.player_captain_cost_discount)
        state['player_archer_keep_strength_bonus'] = list(gs.player_archer_keep_strength_bonus)
        state['player_farm_destruction_gold_bonus'] = list(gs.player_farm_destruction_gold_bonus)
        state['player_cavalry_strength_bonus'] = list(gs.player_cavalry_strength_bonus)
        state['player_divide_conquer_bonus'] = list(gs.player_divide_conquer_bonus)
        state['player_barracks_cost_discount'] = list(gs.player_barracks_cost_discount)
        state['player_barracks_full_refund'] = list(gs.player_barracks_full_refund)
        state['player_hero_keep_defense_bonus'] = list(gs.player_hero_keep_defense_bonus)

        # --- Movement orders (serialize MovementOrder objects to dicts) ---
        state['movement_orders'] = [
            {
                'from': o.from_territory,
                'to': o.to_territory,
                'army_count': o.army_count,
                'player': o.player,
                'unit_ids': list(o.unit_ids) if o.unit_ids else [],
                'intermediate': o.intermediate_territory,
            }
            for o in gs.movement_orders
        ]

        # --- Game flow ---
        state['turn_number'] = gs.turn_number
        state['turn_phase'] = gs.turn_phase
        state['winner'] = gs.winner

        # --- Player stats ---
        state['player_stats'] = {
            str(p): dict(s) for p, s in gs.player_stats.items()
        }

        # --- Master Negotiator state ---
        state['player_master_negotiator_active'] = list(gs.player_master_negotiator_active)

        # --- Embargo state ---
        state['embargo_blocked_players'] = list(gs.embargo_blocked_players)

        return state

    def _serialize_garrisons(self):
        """
        Serialize territory_garrisons with deep copy of unit dicts.

        Format: {territory: {player_str: {unmoved, moved, units: [...]}}}
        """
        result = {}
        for territory, garrisons in self.gs.territory_garrisons.items():
            if not garrisons:
                continue  # Skip empty garrison dicts to save space
            terr_data = {}
            for player, garrison in garrisons.items():
                terr_data[str(player)] = {
                    'unmoved': garrison.get('unmoved', 0),
                    'moved': garrison.get('moved', 0),
                    'units': [
                        {k: v for k, v in unit.items() if k != 'order'}
                        for unit in garrison.get('units', [])
                    ],
                }
            result[territory] = terr_data
        return result

    # ========== Finalization ==========

    def finalize_and_save(self):
        """
        Build the final replay JSON and save to Replays/ folder.

        Called from the Recap screen "Save Replay" button.
        Uses atomic file writes (tempfile + os.replace) for safety.

        Returns:
            str or None: Path to saved replay file, or None on failure
        """
        if self.saved:
            logger.warning("ReplayRecorder: replay already saved, skipping")
            return None

        try:
            duration_minutes = round(
                (datetime.now() - self.start_time).total_seconds() / 60, 1
            )

            # Determine total turns from game state
            total_turns = self.gs.turn_number
            if total_turns == 0 and self.snapshots:
                total_turns = max(s['turn'] for s in self.snapshots)

            # Get winner name
            winner_name = None
            winner_index = None
            if self.gs.winner is not None and self.gs.winner >= 0:
                winner_name = self.gs.get_player_name(self.gs.winner)
                winner_index = self.gs.winner

            # Build player info for metadata
            player_info = []
            for p in range(self.gs.num_players):
                player_info.append({
                    'name': self.gs.get_player_name(p),
                    'is_ai': self.gs.player_is_ai[p],
                    'ai_difficulty': self.gs.player_ai_difficulty[p] if self.gs.player_is_ai[p] else None,
                    'color': list(self.gs.player_colors[p]) if p < len(self.gs.player_colors) else None,
                    'team': self.gs.player_teams[p] if p < len(self.gs.player_teams) else p,
                })

            # Build replay data
            replay_data = {
                'version': 1,
                'metadata': {
                    'game_id': self.game_id,
                    'date': self.start_time.strftime('%Y-%m-%d %H:%M'),
                    'num_players': self.gs.num_players,
                    'players': player_info,
                    'victory_condition': self.gs.victory_condition,
                    'taxation_level': self.gs.taxation_level,
                    'game_mode': self.gs.game_mode,
                    'total_turns': total_turns,
                    'total_snapshots': len(self.snapshots),
                    'winner_name': winner_name,
                    'winner_index': winner_index,
                    'duration_minutes': duration_minutes,
                },
                'setup': {
                    'player_starting_territories': {
                        str(p): t for p, t in self.gs.player_starting_territories.items()
                    },
                    'starting_gold': self.gs.starting_gold,
                },
                'snapshots': self.snapshots,
            }

            # Save to Replays/ folder
            filepath = self._write_replay_file(replay_data)
            if filepath:
                self.saved = True
            return filepath

        except Exception as e:
            logger.error(f"ReplayRecorder: failed to finalize and save: {e}")
            return None

    def _write_replay_file(self, replay_data):
        """
        Write replay JSON to Replays/ folder with atomic file write.

        Uses gzip compression to reduce file size (~5-10x smaller).

        Returns:
            str or None: Path to saved file, or None on failure
        """
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        replays_dir = os.path.join(base_dir, 'Replays')
        os.makedirs(replays_dir, exist_ok=True)

        date_str = self.start_time.strftime('%Y-%m-%d')
        filename = f"{self.game_id}_{date_str}.replay.json.gz"
        filepath = os.path.join(replays_dir, filename)

        # Atomic write: write to temp file then rename
        try:
            fd, tmp_path = tempfile.mkstemp(dir=replays_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'wb') as f:
                    # Gzip-compressed JSON for smaller replay files
                    json_bytes = json.dumps(replay_data, ensure_ascii=False,
                                            separators=(',', ':')).encode('utf-8')
                    compressed = gzip.compress(json_bytes, compresslevel=6)
                    f.write(compressed)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, filepath)
                logger.info(f"ReplayRecorder: replay saved to {filepath} "
                            f"({len(compressed)} bytes compressed, "
                            f"{len(json_bytes)} bytes raw)")
                return filepath
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        except Exception as e:
            logger.error(f"ReplayRecorder: failed to write replay file: {e}")
            return None

    # ========== Static Loading ==========

    @staticmethod
    def load_replay(filepath):
        """
        Load a replay file from disk.

        Args:
            filepath: Path to .replay.json.gz or .replay.json file

        Returns:
            dict: Replay data dict, or None on failure
        """
        try:
            if filepath.endswith('.gz'):
                with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                    return json.load(f)
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"ReplayRecorder: failed to load replay from {filepath}: {e}")
            return None
