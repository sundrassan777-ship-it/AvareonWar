# -*- coding: utf-8 -*-
# map_data.py
# Territory definitions and adjacency data for the game

import json
import os
from utils.logger import get_logger

logger = get_logger(__name__)

# Territory polygons (loaded from JSON file)
TERRITORY_POLYGONS = {}

# Campaign mission territory filtering - when set, only these territories are active
# None means all territories are enabled (normal gameplay)
ENABLED_TERRITORIES = None

# Campaign mission territory display name overrides
# Maps internal territory names to display names for UI (e.g., "The Holy Land" -> "Neimer Coast")
TERRITORY_DISPLAY_NAMES = {}

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

def load_polygons():
    """Load territory polygons from JSON file and calculate centers (UTF-8 safe)"""
    global TERRITORY_POLYGONS, TERRITORY_CENTERS
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

    except FileNotFoundError:
        logger.warning("territory_polygons.json not found!")
        logger.warning("Run polygon_tool.py first to define territories")

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

# Territory center coordinates (calculated from polygons)
TERRITORY_CENTERS = {}

# Building plot positions (loaded from JSON file)
TERRITORY_PLOTS = {}

# Economic tier data (loaded from JSON file)
TERRITORY_INCOME = {}

# Income values per tier (reduced from 10/20/30 to slow gold accumulation
# and make economy buildings more impactful relative to base income)
TIER_INCOME = {
    1: 10,
    2: 15,
    3: 20
}

def load_plots():
    """Load building plot positions from JSON file"""
    global TERRITORY_PLOTS
    try:
        with open('plots.json', 'r', encoding='utf-8') as f:
            TERRITORY_PLOTS = json.load(f)
        logger.info(f"Loaded plots for {len(TERRITORY_PLOTS)} territories")
    except FileNotFoundError:
        logger.warning("plots.json not found!")
        logger.warning("Run plot_tool.py to define building plots")

def load_economic_data():
    """Load economic tier data from JSON file"""
    global TERRITORY_INCOME
    try:
        with open('economic_data.json', 'r', encoding='utf-8') as f:
            economic_tiers = json.load(f)
        
        # Convert tier numbers to income values
        for territory, tier in economic_tiers.items():
            TERRITORY_INCOME[territory] = TIER_INCOME.get(tier, 20)  # Default to 20 if tier invalid
        
        logger.info(f"Loaded economic data for {len(TERRITORY_INCOME)} territories")
    except FileNotFoundError:
        logger.warning("economic_data.json not found!")
        logger.warning("Run economic_tool.py to assign economic tiers")
        # Default all territories to 20 gold
        for territory in TERRITORY_POLYGONS.keys():
            TERRITORY_INCOME[territory] = 20

def get_territory_income(territory):
    """Get the income value for a territory"""
    return TERRITORY_INCOME.get(territory, 20)  # Default to 20 if not found

# Territorial bonuses system - each territory provides one global bonus to its owner
TERRITORY_BONUSES = {}

def load_territory_bonuses():
    """Load territory bonus assignments from JSON file"""
    global TERRITORY_BONUSES
    try:
        with open('territory_bonuses.json', 'r', encoding='utf-8') as f:
            TERRITORY_BONUSES = json.load(f)
        logger.info(f"Loaded territorial bonuses for {len(TERRITORY_BONUSES)} territories")
    except FileNotFoundError:
        logger.warning("territory_bonuses.json not found!")
        logger.warning("Run Bonus_Tool.py to assign territorial bonuses")
        TERRITORY_BONUSES = {}

def get_territory_bonus(territory):
    """Get the bonus type for a territory (returns None if no bonus assigned)"""
    return TERRITORY_BONUSES.get(territory, None)

def get_plots(territory):
    """Get list of plot positions for a territory"""
    return TERRITORY_PLOTS.get(territory, [])

# Adjacency relationships - defines which territories border each other
# Verified and corrected using adjacency_tool.py
# UTF-8 encoding for accented characters (Damlére, Révia)
ADJACENCIES = {
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
}  # Will be populated via Adjacency_Tool.py with 59 territories

# Tutorial adjacency override (set by tutorial_mission.py when active)
# When not None, points to the TutorialMission instance for adjacency queries
_tutorial_mission_ref = None

def set_tutorial_mission(tutorial_mission):
    """Set or clear the tutorial mission reference for adjacency overrides."""
    global _tutorial_mission_ref
    _tutorial_mission_ref = tutorial_mission

# ============================================================================
# Campaign Mission Territory Filtering System
# Used to restrict which territories are active in campaign missions
# ============================================================================

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

# Get the center coordinates of a territory
def get_territory_center(territory_name):
    """Get the center point (centroid) of a territory in world coordinates"""
    return TERRITORY_CENTERS.get(territory_name, (0, 0))

# Get all territory names as a list
def get_all_territories():
    """Get list of all enabled territory names.

    If campaign mission filtering is active, only returns enabled territories.
    """
    all_territories = list(TERRITORY_CENTERS.keys())
    if ENABLED_TERRITORIES is None:
        return all_territories
    return [t for t in all_territories if t in ENABLED_TERRITORIES]

# Check if two territories are adjacent
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

# Get all neighbors of a territory
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