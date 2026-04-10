"""
Save Manager - Campaign save/load system.

Handles serialization/deserialization of full game state plus campaign mission
state. Saves stored as gzip-compressed JSON in Saves/ directory.

Save format:
    {
        "version": 1,
        "metadata": { mission_id, mission_text, save_name, datetime, turn_number },
        "game_config": { num_players, player_is_ai, player_ai_difficulty, ... },
        "game_state": { ... full serialized GameState ... },
        "mission_state": { ... from mission.get_save_state() ... }
    }

Architecture:
    - serialize_game_state() replicates replay_recorder._serialize_state() pattern
      plus additional fields not captured by replays (eliminated_players, config, etc.)
    - deserialize_game_state() reverses the process, handling type conversions
    - Each campaign mission implements get_save_state() / restore_save_state()
"""

import json
import gzip
import os
import re
import tempfile
from datetime import datetime

import map_data
from utils.logger import get_logger

logger = get_logger(__name__)

SAVE_DIR = 'Saves'
SAVE_EXTENSION = '.save.json.gz'
SAVE_VERSION = 1


def serialize_game_state(gs):
    """
    Serialize full GameState to a JSON-compatible dict.

    Replicates replay_recorder._serialize_state() pattern, plus captures
    additional fields needed for save/load (config, eliminated players, etc.).

    Args:
        gs: GameState instance

    Returns:
        dict: Complete serialized game state
    """
    state = {}

    # --- Territory ownership & armies ---
    state['territory_owners'] = dict(gs.territory_owners)
    state['armies'] = dict(gs.armies)
    state['armies_unmoved'] = dict(gs.armies_unmoved)
    state['armies_moved'] = dict(gs.armies_moved)

    # --- Multi-garrison system (deep copy with unit dicts) ---
    state['territory_garrisons'] = _serialize_garrisons(gs)

    # --- Garrison positions (for stable flag placement) ---
    state['garrison_positions'] = {
        t: {str(p): idx for p, idx in positions.items()}
        for t, positions in gs.garrison_positions.items()
        if positions
    }

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
        if plots
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

    # hero_ownership: {player_index: set(hero_types)} -> serialize sets as sorted lists
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
    # player_tech_researched: {player: set(tech_ids)} -> serialize sets as sorted lists
    state['player_tech_researched'] = {
        str(p): sorted(list(s)) for p, s in gs.player_tech_researched.items()
    }

    # player_tech_available: {player: set(tech_ids)} -> serialize sets as sorted lists
    state['player_tech_available'] = {
        str(p): sorted(list(s)) for p, s in gs.player_tech_available.items()
    }

    # research_in_progress: {player: {'tech_id': str, 'turns_remaining': int, ...}}
    state['research_in_progress'] = {
        str(p): dict(r) for p, r in gs.research_in_progress.items()
        if r
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
    state['player_planning_time_limit'] = list(gs.player_planning_time_limit)

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
    state['phase'] = gs.phase
    state['current_player'] = gs.current_player
    state['winner'] = gs.winner

    # --- Player stats ---
    state['player_stats'] = {
        str(p): dict(s) for p, s in gs.player_stats.items()
    }

    # --- Master Negotiator state ---
    state['player_master_negotiator_active'] = list(gs.player_master_negotiator_active)

    # --- Embargo state ---
    state['embargo_blocked_players'] = list(gs.embargo_blocked_players)

    # --- Eliminated players (sets -> sorted lists) ---
    state['eliminated_players'] = sorted(list(gs.eliminated_players))
    state['disconnect_eliminations'] = sorted(list(gs.disconnect_eliminations))

    # --- Buildings started this turn ---
    state['buildings_started_this_turn'] = sorted(list(gs.buildings_started_this_turn))

    # --- Chat & action log ---
    state['chat_messages'] = list(gs.chat_messages)
    state['messages'] = list(gs.messages)

    # --- Starting territories (for Capital Assault) ---
    state['player_starting_territories'] = {
        str(p): t for p, t in gs.player_starting_territories.items()
    }

    return state


def _serialize_garrisons(gs):
    """
    Serialize territory_garrisons with deep copy of unit dicts.

    Format: {territory: {player_str: {unmoved, moved, units: [...]}}}
    Strips 'order' field from unit dicts (not serializable).
    """
    result = {}
    for territory, garrisons in gs.territory_garrisons.items():
        if not garrisons:
            continue
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


def deserialize_game_state(gs, data):
    """
    Restore all serialized fields back into a live GameState instance.

    Handles type conversions: string keys -> int keys, lists -> sets, etc.
    Must be called AFTER game.initialize_game() has set up the base structure.

    Args:
        gs: GameState instance (already initialized with correct player count)
        data: dict from serialize_game_state()
    """
    from game_state import MovementOrder

    # --- Territory ownership & armies ---
    gs.territory_owners.update(data.get('territory_owners', {}))
    gs.armies.update(data.get('armies', {}))
    gs.armies_unmoved.update(data.get('armies_unmoved', {}))
    gs.armies_moved.update(data.get('armies_moved', {}))

    # --- Multi-garrison system ---
    _deserialize_garrisons(gs, data.get('territory_garrisons', {}))

    # --- Garrison positions ---
    saved_positions = data.get('garrison_positions', {})
    for t, positions in saved_positions.items():
        gs.garrison_positions[t] = {int(p): idx for p, idx in positions.items()}

    # --- Economy ---
    if 'player_gold' in data:
        gs.player_gold = list(data['player_gold'])

    # --- Buildings ---
    gs.buildings = {
        t: {int(k): v for k, v in plots.items()}
        for t, plots in data.get('buildings', {}).items()
    }

    gs.under_construction = {
        t: {int(k): tuple(v) for k, v in plots.items()}
        for t, plots in data.get('under_construction', {}).items()
    }

    gs.castle_upgrades = {
        t: {int(k): v for k, v in plots.items()}
        for t, plots in data.get('castle_upgrades', {}).items()
    }

    gs.castle_upgrades_in_progress = {
        t: {int(k): v for k, v in plots.items()}
        for t, plots in data.get('castle_upgrades_in_progress', {}).items()
    }

    gs.building_xp = {
        t: {int(k): dict(v) for k, v in plots.items()}
        for t, plots in data.get('building_xp', {}).items()
    }

    # --- Training ---
    gs.training_queue = {
        t: {
            int(k): [tuple(entry) for entry in queue]
            for k, queue in plots.items()
        }
        for t, plots in data.get('training_queue', {}).items()
    }

    gs.hero_training_queue = {
        t: {int(k): tuple(v) for k, v in plots.items()}
        for t, plots in data.get('hero_training_queue', {}).items()
    }

    # --- Heroes ---
    gs.heroes = {
        int(p): {ht: dict(hd) for ht, hd in heroes.items()}
        for p, heroes in data.get('heroes', {}).items()
    }

    gs.hero_ownership = {
        int(p): set(s) for p, s in data.get('hero_ownership', {}).items()
    }

    gs.hero_ability_cooldowns = {
        int(p): {
            ht: dict(abilities)
            for ht, abilities in hero_cds.items()
        }
        for p, hero_cds in data.get('hero_ability_cooldowns', {}).items()
    }

    gs.hero_silence_status = {
        int(p): turns for p, turns in data.get('hero_silence_status', {}).items()
    }

    # --- Technology ---
    gs.player_tech_researched = {
        int(p): set(s) for p, s in data.get('player_tech_researched', {}).items()
    }

    gs.player_tech_available = {
        int(p): set(s) for p, s in data.get('player_tech_available', {}).items()
    }

    gs.research_in_progress = {
        int(p): dict(r) for p, r in data.get('research_in_progress', {}).items()
    }

    # --- Tech effect arrays ---
    tech_arrays = [
        'player_hero_limit', 'player_command_limit', 'player_royal_decree_discount',
        'player_training_cost_discount', 'player_cavalry_cost_discount',
        'player_captain_cost_discount', 'player_archer_keep_strength_bonus',
        'player_farm_destruction_gold_bonus', 'player_cavalry_strength_bonus',
        'player_divide_conquer_bonus', 'player_barracks_cost_discount',
        'player_barracks_full_refund', 'player_hero_keep_defense_bonus',
        'player_planning_time_limit',
    ]
    for arr_name in tech_arrays:
        if arr_name in data:
            setattr(gs, arr_name, list(data[arr_name]))

    # --- Movement orders (reconstruct MovementOrder objects from dicts) ---
    gs.movement_orders = [
        MovementOrder(
            from_territory=o['from'],
            to_territory=o['to'],
            army_count=o['army_count'],
            player=o['player'],
            unit_ids=o.get('unit_ids', []),
            intermediate_territory=o.get('intermediate'),
        )
        for o in data.get('movement_orders', [])
    ]

    # --- Game flow ---
    gs.turn_number = data.get('turn_number', 0)
    gs.turn_phase = data.get('turn_phase', 'planning')
    gs.phase = data.get('phase', 'playing')
    gs.current_player = data.get('current_player', 0)
    gs.winner = data.get('winner', -1)

    # --- Player stats ---
    for p_str, stats in data.get('player_stats', {}).items():
        gs.player_stats[int(p_str)] = dict(stats)

    # --- Master Negotiator state ---
    if 'player_master_negotiator_active' in data:
        gs.player_master_negotiator_active = list(data['player_master_negotiator_active'])

    # --- Embargo state ---
    if 'embargo_blocked_players' in data:
        gs.embargo_blocked_players = list(data['embargo_blocked_players'])

    # --- Eliminated players (lists -> sets) ---
    gs.eliminated_players = set(data.get('eliminated_players', []))
    gs.disconnect_eliminations = set(data.get('disconnect_eliminations', []))

    # --- Buildings started this turn (list -> set) ---
    gs.buildings_started_this_turn = set(data.get('buildings_started_this_turn', []))

    # --- Chat & action log ---
    if 'chat_messages' in data:
        gs.chat_messages = list(data['chat_messages'])
    if 'messages' in data:
        gs.messages = list(data['messages'])

    # --- Starting territories ---
    gs.player_starting_territories = {
        int(p): t for p, t in data.get('player_starting_territories', {}).items()
    }

    # --- Player config (names, colors, teams, AI) ---
    # These are in game_config, not game_state, but restore if present
    if 'player_names' in data:
        gs.player_names = list(data['player_names'])
    if 'player_colors' in data:
        # Convert inner lists back to tuples (JSON deserializes tuples as lists)
        gs.player_colors = [tuple(c) for c in data['player_colors']]

    # --- Invalidate caches so rendering picks up restored state ---
    gs._territory_owners_version += 1
    gs._training_version += 1
    if hasattr(gs, 'invalidate_territorial_bonus_cache'):
        gs.invalidate_territorial_bonus_cache()


def _deserialize_garrisons(gs, garrisons_data):
    """
    Restore territory_garrisons from serialized data.

    Converts string player keys back to int keys.
    """
    for territory in gs.territory_garrisons:
        gs.territory_garrisons[territory] = {}

    for territory, players in garrisons_data.items():
        gs.territory_garrisons[territory] = {
            int(p): {
                'unmoved': g.get('unmoved', 0),
                'moved': g.get('moved', 0),
                'units': [dict(u) for u in g.get('units', [])],
            }
            for p, g in players.items()
        }


def _sanitize_filename(name):
    """Strip filesystem-unsafe characters from save name for use in filename."""
    # Replace unsafe chars with underscore, collapse multiple underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_ ')
    return sanitized or 'Unnamed'


def _resolve_duplicate_name(save_name, existing_saves):
    """
    Handle duplicate save names by appending (1), (2), etc.

    Args:
        save_name: Desired save name
        existing_saves: List of save metadata dicts from scan_saves()

    Returns:
        str: Unique save name (possibly with numeric suffix)
    """
    existing_names = {s['save_name'] for s in existing_saves}
    if save_name not in existing_names:
        return save_name

    # Strip existing suffix like " (N)" before incrementing
    base_name = re.sub(r'\s*\(\d+\)$', '', save_name)
    counter = 1
    while True:
        candidate = f"{base_name} ({counter})"
        if candidate not in existing_names:
            return candidate
        counter += 1


# Mission text lookup for metadata (maps mission_id to display name)
_MISSION_TEXTS = {
    'mission_1': 'Chapter 1: Rise of Affrancia',
    'mission_2': 'Chapter 2: Early Eastern Conquests',
    'mission_3': 'Chapter 3: Storms above the West',
    'mission_4': 'Chapter 4: Domination',
    'mission_5': 'Chapter 5: The First War',
    'mission_6': 'Chapter 6: The Second War',
    'mission_7': 'Chapter 7: The Fall',
}


def save_game(gs, mission_obj, save_name):
    """
    Save full game state + campaign mission state to disk.

    Args:
        gs: GameState instance
        mission_obj: Campaign mission instance (must implement get_save_state())
        save_name: User-provided save name

    Returns:
        str or None: Path to saved file, or None on failure
    """
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)

        # Resolve duplicate names
        existing = scan_saves()
        save_name = _resolve_duplicate_name(save_name, existing)

        mission_id = getattr(mission_obj, 'mission_id', 'unknown')
        now = datetime.now()

        # Build save data
        save_data = {
            'version': SAVE_VERSION,
            'metadata': {
                'mission_id': mission_id,
                'mission_text': _MISSION_TEXTS.get(mission_id, mission_id),
                'save_name': save_name,
                'datetime': now.strftime('%Y-%m-%d %H:%M:%S'),
                'turn_number': gs.turn_number,
            },
            'game_config': {
                'num_players': gs.num_players,
                'player_is_ai': list(gs.player_is_ai),
                'player_ai_difficulty': list(gs.player_ai_difficulty),
                'player_teams': list(gs.player_teams),
                'victory_condition': gs.victory_condition,
                'taxation_level': gs.taxation_level,
                'game_mode': gs.game_mode,
                'starting_gold': gs.starting_gold,
                'player_names': list(gs.player_names),
                'player_colors': list(gs.player_colors),
                'map_id': map_data.get_current_map_id() or 'avareon',  # Multi-map support
            },
            'game_state': serialize_game_state(gs),
            'mission_state': mission_obj.get_save_state(),
        }

        # Build filename: {mission_id}_{sanitized_name}_{datetime}.save.json.gz
        safe_name = _sanitize_filename(save_name)
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        filename = f"{mission_id}_{safe_name}_{timestamp}{SAVE_EXTENSION}"
        filepath = os.path.join(SAVE_DIR, filename)

        # Atomic write: write to temp file then rename
        json_str = json.dumps(save_data, ensure_ascii=False)
        compressed = gzip.compress(json_str.encode('utf-8'))

        fd, tmp_path = tempfile.mkstemp(dir=SAVE_DIR, suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(compressed)
            os.replace(tmp_path, filepath)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.info(f"Game saved: {filepath} (name: {save_name})")
        return filepath

    except Exception as e:
        logger.error(f"Failed to save game: {e}")
        return None


def load_save_file(path):
    """
    Load and parse a save file.

    Args:
        path: Path to .save.json.gz file

    Returns:
        dict or None: Parsed save data, or None on failure
    """
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load save file {path}: {e}")
        return None


def scan_saves():
    """
    Scan Saves/ directory for save files and extract metadata.

    Returns:
        list[dict]: Save entries sorted by datetime descending (newest first).
        Each entry has: path, mission_id, mission_text, save_name, datetime, turn_number
    """
    if not os.path.isdir(SAVE_DIR):
        return []

    saves = []
    for filename in os.listdir(SAVE_DIR):
        if not filename.endswith(SAVE_EXTENSION):
            continue

        filepath = os.path.join(SAVE_DIR, filename)
        try:
            data = load_save_file(filepath)
            if data is None:
                continue

            metadata = data.get('metadata', {})
            saves.append({
                'path': filepath,
                'mission_id': metadata.get('mission_id', 'unknown'),
                'mission_text': metadata.get('mission_text', 'Unknown Mission'),
                'save_name': metadata.get('save_name', 'Unnamed'),
                'datetime': metadata.get('datetime', ''),
                'turn_number': metadata.get('turn_number', 0),
            })
        except Exception as e:
            logger.warning(f"Skipping corrupt save file {filename}: {e}")

    # Sort by datetime descending (newest first)
    saves.sort(key=lambda s: s['datetime'], reverse=True)
    return saves


def delete_save(path):
    """
    Delete a save file.

    Args:
        path: Path to save file

    Returns:
        bool: True if deleted successfully
    """
    try:
        os.remove(path)
        logger.info(f"Deleted save: {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete save {path}: {e}")
        return False
