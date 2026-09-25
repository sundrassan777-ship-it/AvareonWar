# -*- coding: utf-8 -*-
# map_data.py
# Territory definitions and adjacency data for the game
# Supports multiple maps via maps/ directory structure and manifest.json

import json
import os
import random
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# Module-level globals (populated by load_map or load_polygons)
# ============================================================================

# Currently loaded map ID (None = not yet loaded)
_current_map_id = None

# Cached map manifest from maps/manifest.json
_map_manifest = None

# Territory polygons (loaded from JSON file)
TERRITORY_POLYGONS = {}

# Territory center coordinates (calculated from polygons)
TERRITORY_CENTERS = {}

# Building plot positions (loaded from JSON file)
TERRITORY_PLOTS = {}

# Economic tier data (loaded from JSON file)
TERRITORY_INCOME = {}

# Territorial bonuses system - each territory provides one global bonus to its owner
TERRITORY_BONUSES = {}

# Adjacency relationships - which territories border each other
ADJACENCIES = {}

# Fortress territories - territories with innate +2 defense (cannot build Keeps)
FORTRESS_TERRITORIES = set()

# Territory lore/descriptions - per-territory flavor text for UI tooltips
TERRITORY_LORE = {}

# Campaign mission territory filtering - when set, only these territories are active
# None means all territories are enabled (normal gameplay)
ENABLED_TERRITORIES = None

# Campaign mission territory display name overrides
# Maps internal territory names to display names for UI (e.g., "The Holy Land" -> "Neimer Coast")
TERRITORY_DISPLAY_NAMES = {}

# Income values per tier (reduced from 10/20/30 to slow gold accumulation
# and make economy buildings more impactful relative to base income)
TIER_INCOME = {
    1: 10,
    2: 15,
    3: 20
}

# Tutorial adjacency override (set by tutorial_mission.py when active)
# When not None, points to the TutorialMission instance for adjacency queries
_tutorial_mission_ref = None

# ============================================================================
# Legacy hardcoded adjacencies for Avareon map (used as fallback)
# ============================================================================

_AVAREON_ADJACENCIES = {
    "Aelatania": ["Courtieux", "Duchy of Daurels", "Londia", "Northern Heilonia"],
    "Affrancian Uplands": ["Carnae", "Lunedale", "March of Auverne", "Vense", "Zjoal Islands"],
    "Ahara": ["Cinto", "Conda", "Oucine"],
    "Ahtep": ["Amennia", "Daomea", "Liadnon"],
    "Ajuna": ["Daomea", "Espoia", "Odatria", "Riar"],
    "Amennia": ["Ahtep", "Duchy of Daurels", "Leuse Valley", "Liadnon", "Sstep"],
    "Amorian Shores": ["Anodia", "Northern Quil'en", "Southern Quil'en"],
    "Anodia": ["Amorian Shores", "Fahlaan Dunes", "Liadnon", "Northern Quil'en", "Sordia", "Southern Quil'en"],
    "Aunon": ["Fahlaan Dunes", "Lamacia", "Sordia"],
    "Carnae": ["Affrancian Uplands", "Leimarch", "March of Auverne", "Orhas", "Orlais", "Vense"],
    "Cinto": ["Ahara", "Conda", "Odatria", "Oucine", "Vice"],
    "Conda": ["Ahara", "Cinto", "Nefrid", "Odatria"],
    "Courtieux": ["Aelatania", "Londia"],
    "Cualus": ["Orhas", "Orlais"],
    "Damlére": ["Daomea", "Free Cities", "Lunedale", "Mose", "Role"],
    "Daomea": ["Ahtep", "Ajuna", "Damlére", "Espoia", "Mose", "Riar"],
    "Duchy of Daurels": ["Aelatania", "Amennia", "Leuse Valley", "Northern Heilonia", "Valeonia"],
    "Elland": ["Elletian Isles", "Lentria", "The Holy Land"],
    "Elletian Isles": ["Elland", "The Holy Land"],
    "Espoia": ["Ajuna", "Daomea", "Nefrid", "Odatria"],
    "Fahlaan Dunes": ["Anodia", "Aunon", "Linan", "Sordia"],
    "Free Cities": ["Damlére", "Lunedale", "Role", "Zjoal Islands"],
    "Lamacia": ["Aunon", "Osana", "Vianaa"],
    "Leimarch": ["Carnae", "Liadnon"],
    "Lentria": ["Elland", "Lobardia", "The Holy Land"],
    "Leuse Valley": ["Amennia", "Duchy of Daurels", "Nordica", "Sstep", "Valeonia", "Velognia"],
    "Liadnon": ["Ahtep", "Amennia", "Anodia", "Leimarch", "Nordica", "Northern Quil'en", "Sstep"],
    "Linan": ["Fahlaan Dunes", "Orhas", "Vianaa"],
    "Lobardia": ["Lentria", "The Holy Land", "Valeonia", "Velognia", "Venexia"],
    "Londia": ["Aelatania", "Courtieux", "Northern Heilonia"],
    "Lunedale": ["Affrancian Uplands", "Damlére", "Free Cities", "Vense"],
    "March of Auverne": ["Affrancian Uplands", "Carnae", "Orlais"],
    "Mose": ["Damlére", "Daomea", "Riar", "Role", "Vice"],
    "Nefrid": ["Conda", "Espoia", "Odatria"],
    "Nordica": ["Leuse Valley", "Liadnon", "Northern Quil'en", "Sstep"],
    "Northern Heilonia": ["Aelatania", "Duchy of Daurels", "Londia", "Révia", "Valeonia", "Venexia"],
    "Northern Quil'en": ["Amorian Shores", "Anodia", "Liadnon", "Nordica"],
    "Odatria": ["Ajuna", "Cinto", "Conda", "Espoia", "Nefrid", "Riar", "Vice"],
    "Orhas": ["Carnae", "Cualus", "Linan", "Orlais"],
    "Orlais": ["Carnae", "Cualus", "March of Auverne", "Orhas"],
    "Osana": ["Lamacia", "Vianaa"],
    "Oucine": ["Ahara", "Cinto", "Vice"],
    "Riar": ["Ajuna", "Daomea", "Mose", "Odatria", "Vice"],
    "Role": ["Damlére", "Free Cities", "Mose", "Vice"],
    "Révia": ["Northern Heilonia", "Venexia"],
    "Sordia": ["Anodia", "Aunon", "Fahlaan Dunes", "Southern Quil'en", "The Comet"],
    "Southern Quil'en": ["Amorian Shores", "Anodia", "Sordia", "The Comet"],
    "Sstep": ["Amennia", "Leuse Valley", "Liadnon", "Nordica"],
    "The Comet": ["Sordia", "Southern Quil'en"],
    "The Holy Land": ["Elland", "Elletian Isles", "Lentria", "Lobardia", "Venexia"],
    "Valeonia": ["Duchy of Daurels", "Leuse Valley", "Lobardia", "Northern Heilonia", "Velognia", "Venexia"],
    "Velognia": ["Leuse Valley", "Lobardia", "Valeonia"],
    "Venexia": ["Lobardia", "Northern Heilonia", "Révia", "The Holy Land", "Valeonia"],
    "Vense": ["Affrancian Uplands", "Carnae", "Lunedale"],
    "Vianaa": ["Lamacia", "Linan", "Osana"],
    "Vice": ["Cinto", "Mose", "Odatria", "Oucine", "Riar", "Role"],
    "Zjoal Islands": ["Affrancian Uplands", "Free Cities"],
}

# ============================================================================
# Map Manifest & Multi-Map Support
# ============================================================================

def get_map_manifest():
    """Load and cache the map manifest from maps/manifest.json.
    Returns list of map entries with id, display_name, directory, has_background."""
    global _map_manifest
    if _map_manifest is not None:
        return _map_manifest
    try:
        with open('maps/manifest.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        _map_manifest = data.get('maps', [])
        logger.info(f"Loaded map manifest with {len(_map_manifest)} maps")
        return _map_manifest
    except FileNotFoundError:
        logger.warning("maps/manifest.json not found, using default Avareon map only")
        _map_manifest = [{
            "id": "avareon",
            "display_name": "Avareon",
            "directory": "maps/avareon",
            "has_background": True
        }]
        return _map_manifest

def get_map_info(map_id):
    """Get manifest entry for a specific map by ID. Returns None if not found."""
    manifest = get_map_manifest()
    for entry in manifest:
        if entry['id'] == map_id:
            return entry
    return None

def get_map_directory(map_id):
    """Get the directory path for a map by ID."""
    info = get_map_info(map_id)
    if info:
        return info['directory']
    return f"maps/{map_id}"

def get_current_map_id():
    """Get the ID of the currently loaded map."""
    return _current_map_id

def current_map_draws_borders():
    """True if the loaded map asks the renderer to outline every territory.

    Set per map with "draw_borders": true in maps/manifest.json. Maps whose
    background art already has visible borders painted in (Avareon) leave it
    off; maps with faint painted borders (Azincournean Highlands) turn it on.
    The legacy load_polygons() path leaves _current_map_id unset (Avareon).
    """
    info = get_map_info(_current_map_id) if _current_map_id else None
    return bool(info and info.get('draw_borders', False))

def get_map_ids():
    """Get ordered list of enabled map IDs from manifest."""
    manifest = get_map_manifest()
    return [entry['id'] for entry in manifest if entry.get('enabled', True)]

def get_map_display_name(map_id):
    """Get the display name for a map by ID."""
    info = get_map_info(map_id)
    if info:
        return info.get('display_name', map_id)
    return map_id

# ============================================================================
# Map Loading Functions
# ============================================================================

def load_map(map_id):
    """Load all data for a specific map by ID.
    Sets all module globals (polygons, centers, plots, income, bonuses, adjacencies, fortresses).
    This is the primary entry point for switching maps."""
    global _current_map_id
    map_dir = get_map_directory(map_id)

    # Load all map data from the map's directory
    _load_polygons_from_dir(map_dir)
    _load_plots_from_dir(map_dir)
    _load_economic_data_from_dir(map_dir)
    _load_territory_bonuses_from_dir(map_dir)
    _load_adjacencies_from_dir(map_dir, map_id)
    _load_fortress_territories_from_dir(map_dir)
    _load_territory_lore_from_dir(map_dir)

    _current_map_id = map_id
    logger.info(f"Loaded map '{map_id}' from {map_dir} ({len(TERRITORY_POLYGONS)} territories)")

def load_polygons():
    """Load territory polygons from JSON file and calculate centers (UTF-8 safe).

    Backward-compatible entry point — loads the Avareon map from root-level files
    (used by campaign missions, tools, and legacy code paths)."""
    global TERRITORY_POLYGONS, TERRITORY_CENTERS, _current_map_id
    try:
        with open('territory_polygons.json', 'r', encoding='utf-8') as f:
            TERRITORY_POLYGONS = json.load(f)
        logger.info(f"Loaded {len(TERRITORY_POLYGONS)} territory polygons")

        # Calculate centers from polygons
        TERRITORY_CENTERS = {}
        for territory, polygon in TERRITORY_POLYGONS.items():
            TERRITORY_CENTERS[territory] = calculate_polygon_centroid(polygon)
        logger.info(f"Calculated centers for {len(TERRITORY_CENTERS)} territories")

        # Load building plots
        load_plots()

        # Load economic data
        load_economic_data()

        # Load territorial bonuses
        load_territory_bonuses()

        # Load adjacencies from legacy hardcoded dict for Avareon
        _load_avareon_adjacencies()

        # Load fortress territories (empty for Avareon via root-level path)
        _load_fortress_territories_from_dir('maps/avareon')

        # Load territory lore/descriptions
        _load_territory_lore_from_dir('maps/avareon')

        _current_map_id = 'avareon'

    except FileNotFoundError:
        logger.warning("territory_polygons.json not found!")
        logger.warning("Run polygon_tool.py first to define territories")

def _load_polygons_from_dir(map_dir):
    """Load territory polygons from a map directory and calculate centers."""
    global TERRITORY_POLYGONS, TERRITORY_CENTERS
    poly_path = os.path.join(map_dir, 'territory_polygons.json')
    try:
        with open(poly_path, 'r', encoding='utf-8') as f:
            TERRITORY_POLYGONS = json.load(f)
        logger.info(f"Loaded {len(TERRITORY_POLYGONS)} territory polygons from {poly_path}")

        # Calculate centers from polygons
        TERRITORY_CENTERS = {}
        for territory, polygon in TERRITORY_POLYGONS.items():
            TERRITORY_CENTERS[territory] = calculate_polygon_centroid(polygon)
        logger.info(f"Calculated centers for {len(TERRITORY_CENTERS)} territories")
    except FileNotFoundError:
        logger.warning(f"{poly_path} not found!")
        TERRITORY_POLYGONS = {}
        TERRITORY_CENTERS = {}

def _load_plots_from_dir(map_dir):
    """Load building plot positions from a map directory."""
    global TERRITORY_PLOTS
    plots_path = os.path.join(map_dir, 'plots.json')
    try:
        with open(plots_path, 'r', encoding='utf-8') as f:
            TERRITORY_PLOTS = json.load(f)
        logger.info(f"Loaded plots for {len(TERRITORY_PLOTS)} territories from {plots_path}")
    except FileNotFoundError:
        logger.warning(f"{plots_path} not found!")
        TERRITORY_PLOTS = {}

def _load_economic_data_from_dir(map_dir):
    """Load economic tier data from a map directory."""
    global TERRITORY_INCOME
    econ_path = os.path.join(map_dir, 'economic_data.json')
    try:
        with open(econ_path, 'r', encoding='utf-8') as f:
            economic_tiers = json.load(f)

        # Convert tier numbers to income values
        TERRITORY_INCOME = {}
        for territory, tier in economic_tiers.items():
            TERRITORY_INCOME[territory] = TIER_INCOME.get(tier, 20)

        logger.info(f"Loaded economic data for {len(TERRITORY_INCOME)} territories from {econ_path}")
    except FileNotFoundError:
        logger.warning(f"{econ_path} not found!")
        # Default all territories to 20 gold
        TERRITORY_INCOME = {}
        for territory in TERRITORY_POLYGONS.keys():
            TERRITORY_INCOME[territory] = 20

def _load_territory_bonuses_from_dir(map_dir):
    """Load territory bonus assignments from a map directory."""
    global TERRITORY_BONUSES
    bonuses_path = os.path.join(map_dir, 'territory_bonuses.json')
    try:
        with open(bonuses_path, 'r', encoding='utf-8') as f:
            TERRITORY_BONUSES = json.load(f)
        logger.info(f"Loaded territorial bonuses for {len(TERRITORY_BONUSES)} territories from {bonuses_path}")
    except FileNotFoundError:
        logger.warning(f"{bonuses_path} not found!")
        TERRITORY_BONUSES = {}

def _load_adjacencies_from_dir(map_dir, map_id):
    """Load adjacency data from a map directory's adjacencies.json.
    Falls back to hardcoded Avareon adjacencies if loading fails for the avareon map."""
    global ADJACENCIES
    adj_path = os.path.join(map_dir, 'adjacencies.json')
    try:
        with open(adj_path, 'r', encoding='utf-8') as f:
            ADJACENCIES = json.load(f)
        logger.info(f"Loaded adjacencies for {len(ADJACENCIES)} territories from {adj_path}")
    except FileNotFoundError:
        if map_id == 'avareon':
            # Fallback to hardcoded Avareon adjacencies
            _load_avareon_adjacencies()
        else:
            logger.warning(f"{adj_path} not found!")
            ADJACENCIES = {}

def _load_avareon_adjacencies():
    """Load the hardcoded Avareon adjacencies as fallback."""
    global ADJACENCIES
    ADJACENCIES = dict(_AVAREON_ADJACENCIES)
    logger.info(f"Loaded hardcoded Avareon adjacencies ({len(ADJACENCIES)} territories)")

def _load_fortress_territories_from_dir(map_dir):
    """Load fortress territory designations from a map directory."""
    global FORTRESS_TERRITORIES
    fortress_path = os.path.join(map_dir, 'fortress_territories.json')
    try:
        with open(fortress_path, 'r', encoding='utf-8') as f:
            fortress_list = json.load(f)
        FORTRESS_TERRITORIES = set(fortress_list)
        if FORTRESS_TERRITORIES:
            logger.info(f"Loaded {len(FORTRESS_TERRITORIES)} fortress territories from {fortress_path}")
    except FileNotFoundError:
        FORTRESS_TERRITORIES = set()

def _load_territory_lore_from_dir(map_dir):
    """Load territory lore/descriptions from a map directory's territory_lore.json."""
    global TERRITORY_LORE
    lore_path = os.path.join(map_dir, 'territory_lore.json')
    try:
        with open(lore_path, 'r', encoding='utf-8') as f:
            TERRITORY_LORE = json.load(f)
        if TERRITORY_LORE:
            logger.info(f"Loaded lore for {len(TERRITORY_LORE)} territories from {lore_path}")
    except (FileNotFoundError, json.JSONDecodeError):
        TERRITORY_LORE = {}

# ============================================================================
# Fortress Territory Accessors
# ============================================================================

def is_fortress_territory(territory):
    """Check if a territory is a fortress (innate +2 defense, cannot build Keeps)."""
    return territory in FORTRESS_TERRITORIES

def get_fortress_territories():
    """Get the set of all fortress territory names on the current map."""
    return set(FORTRESS_TERRITORIES)

# ============================================================================
# Territory Lore Accessors
# ============================================================================

def get_territory_lore(territory):
    """Get lore/description text for a territory. Returns empty string if none available."""
    return TERRITORY_LORE.get(territory, "")

# ============================================================================
# Geometry Functions
# ============================================================================

def calculate_polygon_centroid(polygon):
    """Calculate the centroid (center point) of a polygon"""
    if not polygon or len(polygon) < 3:
        return (0, 0)

    # Calculate centroid using the standard formula
    area = 0
    cx = 0
    cy = 0

    for i in range(len(polygon)):
        j = (i + 1) % len(polygon)
        x1, y1 = polygon[i]
        x2, y2 = polygon[j]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross

    area = area / 2.0
    if area == 0:
        # Fallback to simple average if area calculation fails
        cx = sum(p[0] for p in polygon) / len(polygon)
        cy = sum(p[1] for p in polygon) / len(polygon)
    else:
        cx = cx / (6.0 * area)
        cy = cy / (6.0 * area)

    return (int(cx), int(cy))

def point_in_polygon(point, polygon):
    """Check if a point is inside a polygon using ray casting algorithm"""
    x, y = point
    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside

def get_territory_at_position(pos):
    """Find which territory contains the given position.

    Only returns enabled territories (respects campaign mission filtering).
    """
    # Check from end to start (reverse order) to handle overlaps better
    # This way, later-defined territories take precedence
    for territory in reversed(list(TERRITORY_POLYGONS.keys())):
        # Skip disabled territories in campaign missions
        if not is_territory_enabled(territory):
            continue
        polygon = TERRITORY_POLYGONS[territory]
        if point_in_polygon(pos, polygon):
            return territory
    return None

# ============================================================================
# Legacy Load Functions (backward compat for root-level JSON files)
# ============================================================================

def load_plots():
    """Load building plot positions from root-level JSON file (backward compat)."""
    global TERRITORY_PLOTS
    try:
        with open('plots.json', 'r', encoding='utf-8') as f:
            TERRITORY_PLOTS = json.load(f)
        logger.info(f"Loaded plots for {len(TERRITORY_PLOTS)} territories")
    except FileNotFoundError:
        logger.warning("plots.json not found!")
        logger.warning("Run plot_tool.py to define building plots")

def load_economic_data():
    """Load economic tier data from root-level JSON file (backward compat)."""
    global TERRITORY_INCOME
    try:
        with open('economic_data.json', 'r', encoding='utf-8') as f:
            economic_tiers = json.load(f)

        # Convert tier numbers to income values
        TERRITORY_INCOME = {}
        for territory, tier in economic_tiers.items():
            TERRITORY_INCOME[territory] = TIER_INCOME.get(tier, 20)  # Default to 20 if tier invalid

        logger.info(f"Loaded economic data for {len(TERRITORY_INCOME)} territories")
    except FileNotFoundError:
        logger.warning("economic_data.json not found!")
        logger.warning("Run economic_tool.py to assign economic tiers")
        # Default all territories to 20 gold
        for territory in TERRITORY_POLYGONS.keys():
            TERRITORY_INCOME[territory] = 20

def load_territory_bonuses():
    """Load territory bonus assignments from root-level JSON file (backward compat)."""
    global TERRITORY_BONUSES
    try:
        with open('territory_bonuses.json', 'r', encoding='utf-8') as f:
            TERRITORY_BONUSES = json.load(f)
        logger.info(f"Loaded territorial bonuses for {len(TERRITORY_BONUSES)} territories")
    except FileNotFoundError:
        logger.warning("territory_bonuses.json not found!")
        logger.warning("Run Bonus_Tool.py to assign territorial bonuses")
        TERRITORY_BONUSES = {}

# ============================================================================
# Territory Data Accessors
# ============================================================================

def get_territory_income(territory):
    """Get the income value for a territory"""
    return TERRITORY_INCOME.get(territory, 20)  # Default to 20 if not found

def get_territory_bonus(territory):
    """Get the bonus type for a territory (returns None if no bonus assigned)"""
    return TERRITORY_BONUSES.get(territory, None)

def get_plots(territory):
    """Get list of plot positions for a territory"""
    return TERRITORY_PLOTS.get(territory, [])

def get_territory_center(territory_name):
    """Get the center point (centroid) of a territory in world coordinates"""
    return TERRITORY_CENTERS.get(territory_name, (0, 0))

def get_all_territories():
    """Get list of all enabled territory names.

    If campaign mission filtering is active, only returns enabled territories.
    """
    all_territories = list(TERRITORY_CENTERS.keys())
    if ENABLED_TERRITORIES is None:
        return all_territories
    return [t for t in all_territories if t in ENABLED_TERRITORIES]

# ============================================================================
# Bonus Randomization
# ============================================================================

def randomize_territory_bonuses():
    """Randomly assign bonuses to all territories with equal distribution.
    Mutates TERRITORY_BONUSES in-place and returns the new mapping."""
    global TERRITORY_BONUSES
    from game_state.data_definitions import BONUS_TYPES
    territories = list(TERRITORY_BONUSES.keys())
    bonus_types = list(BONUS_TYPES.keys())
    # Build balanced pool: equal of each type + random extras for remainder
    base_count = len(territories) // len(bonus_types)
    remainder = len(territories) % len(bonus_types)
    pool = bonus_types * base_count + random.sample(bonus_types, remainder)
    random.shuffle(pool)
    TERRITORY_BONUSES = {t: b for t, b in zip(territories, pool)}
    logger.info(f"Randomized territorial bonuses for {len(territories)} territories")
    return dict(TERRITORY_BONUSES)

def apply_territory_bonuses(mapping):
    """Replace territory bonuses with a provided mapping (for multiplayer client sync)."""
    global TERRITORY_BONUSES
    TERRITORY_BONUSES = dict(mapping)
    logger.info(f"Applied territory bonus mapping for {len(TERRITORY_BONUSES)} territories")

# ============================================================================
# Adjacency & Neighbors
# ============================================================================

def are_adjacent(territory1, territory2):
    """Check if two territories are adjacent.

    Returns False if either territory is disabled (campaign mission filtering).
    """
    # Both territories must be enabled for adjacency check
    if not is_territory_enabled(territory1) or not is_territory_enabled(territory2):
        return False
    # Tutorial override: restrict adjacency when tutorial is active
    if _tutorial_mission_ref:
        override = _tutorial_mission_ref.get_adjacency_override(territory1)
        if override is not None:
            return territory2 in override
    return territory2 in ADJACENCIES.get(territory1, [])

def get_neighbors(territory):
    """Get all enabled neighbors of a territory.

    Filters out disabled territories (campaign mission filtering).
    """
    # Tutorial override: restrict neighbors when tutorial is active
    if _tutorial_mission_ref:
        override = _tutorial_mission_ref.get_adjacency_override(territory)
        if override is not None:
            # Filter tutorial override to only enabled territories
            if ENABLED_TERRITORIES is not None:
                return [t for t in override if t in ENABLED_TERRITORIES]
            return override
    neighbors = ADJACENCIES.get(territory, [])
    # Filter to only enabled territories
    if ENABLED_TERRITORIES is not None:
        return [t for t in neighbors if t in ENABLED_TERRITORIES]
    return neighbors

# ============================================================================
# Tutorial & Campaign Mission Systems
# ============================================================================

def set_tutorial_mission(tutorial_mission):
    """Set or clear the tutorial mission reference for adjacency overrides."""
    global _tutorial_mission_ref
    _tutorial_mission_ref = tutorial_mission

def set_enabled_territories(territory_list):
    """Set which territories are enabled for the current campaign mission.

    Args:
        territory_list: List of territory names to enable, or None for all territories
    """
    global ENABLED_TERRITORIES
    ENABLED_TERRITORIES = set(territory_list) if territory_list else None

def clear_enabled_territories():
    """Clear territory filtering, enabling all territories (normal gameplay)."""
    global ENABLED_TERRITORIES
    ENABLED_TERRITORIES = None

def is_territory_enabled(territory):
    """Check if a territory is enabled (active) in the current mission.

    Returns True if:
    - ENABLED_TERRITORIES is None (all territories enabled), OR
    - territory is in the ENABLED_TERRITORIES set
    """
    return ENABLED_TERRITORIES is None or territory in ENABLED_TERRITORIES

def set_territory_display_names(name_map):
    """Set display name overrides for territories in current campaign mission.

    Args:
        name_map: Dict mapping internal names to display names
                  e.g., {"The Holy Land": "Neimer Coast"}
    """
    global TERRITORY_DISPLAY_NAMES
    TERRITORY_DISPLAY_NAMES = name_map if name_map else {}

def clear_territory_display_names():
    """Clear all territory display name overrides."""
    global TERRITORY_DISPLAY_NAMES
    TERRITORY_DISPLAY_NAMES = {}

def get_display_name(territory):
    """Get the display name for a territory (uses override if set, else original name)."""
    return TERRITORY_DISPLAY_NAMES.get(territory, territory)
