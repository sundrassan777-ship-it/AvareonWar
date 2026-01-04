# -*- coding: utf-8 -*-
# map_data.py
# Territory definitions and adjacency data for the game

import json
import os

# Territory polygons (loaded from JSON file)
TERRITORY_POLYGONS = {}

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
        print(f"Loaded {len(TERRITORY_POLYGONS)} territory polygons")
        
        # Calculate centers from polygons
        TERRITORY_CENTERS = {}
        for territory, polygon in TERRITORY_POLYGONS.items():
            TERRITORY_CENTERS[territory] = calculate_polygon_centroid(polygon)
        print(f"Calculated centers for {len(TERRITORY_CENTERS)} territories")
        
        # Load building plots
        load_plots()
        
        # Load economic data
        load_economic_data()
        
    except FileNotFoundError:
        print("Warning: territory_polygons.json not found!")
        print("Run polygon_tool.py first to define territories")

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
    """Find which territory contains the given position"""
    # Check from end to start (reverse order) to handle overlaps better
    # This way, later-defined territories take precedence
    for territory in reversed(list(TERRITORY_POLYGONS.keys())):
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

# Income values per tier
TIER_INCOME = {
    1: 10,
    2: 20,
    3: 30
}

def load_plots():
    """Load building plot positions from JSON file"""
    global TERRITORY_PLOTS
    try:
        with open('plots.json', 'r', encoding='utf-8') as f:
            TERRITORY_PLOTS = json.load(f)
        print(f"Loaded plots for {len(TERRITORY_PLOTS)} territories")
    except FileNotFoundError:
        print("Warning: plots.json not found!")
        print("Run plot_tool.py to define building plots")

def load_economic_data():
    """Load economic tier data from JSON file"""
    global TERRITORY_INCOME
    try:
        with open('economic_data.json', 'r', encoding='utf-8') as f:
            economic_tiers = json.load(f)
        
        # Convert tier numbers to income values
        for territory, tier in economic_tiers.items():
            TERRITORY_INCOME[territory] = TIER_INCOME.get(tier, 20)  # Default to 20 if tier invalid
        
        print(f"Loaded economic data for {len(TERRITORY_INCOME)} territories")
    except FileNotFoundError:
        print("Warning: economic_data.json not found!")
        print("Run economic_tool.py to assign economic tiers")
        # Default all territories to 20 gold
        for territory in TERRITORY_POLYGONS.keys():
            TERRITORY_INCOME[territory] = 20

def get_territory_income(territory):
    """Get the income value for a territory"""
    return TERRITORY_INCOME.get(territory, 20)  # Default to 20 if not found

def get_plots(territory):
    """Get list of plot positions for a territory"""
    return TERRITORY_PLOTS.get(territory, [])

# Adjacency relationships - defines which territories border each other
# Verified and corrected using adjacency_tool.py
# UTF-8 encoding for accented characters (Damlére, Révia)
ADJACENCIES = {
    "Ahara": ["Cinto", "Conda", "Oucine"],
    "Ahtep": ["Amennia", "Daomea", "Liadnon"],
    "Ajuna": ["Daomea", "Espoia", "Odatria", "Riar"],
    "Amennia": ["Ahtep", "Azincourne", "Liadnon", "Naragonthid", "Sstep"],
    "Anodia": ["Liadnon", "Quil'en", "Sordia"],
    "Aunon": ["Lamacia", "Sordia"],
    "Azincourne": ["Amennia", "Naragonthid", "Révia", "Venexia"],
    "Carnae": ["Orhas", "Orlais", "South Affrancia", "Vense"],
    "Cinto": ["Ahara", "Conda", "Odatria", "Oucine", "Vice"],
    "Conda": ["Ahara", "Cinto", "Nefrid", "Odatria"],
    "Cualus": ["Orhas", "Orlais"],
    "Damlére": ["Daomea", "Mose", "North Affrancia", "Role"],
    "Daomea": ["Ahtep", "Ajuna", "Damlére", "Espoia", "Mose", "Riar"],
    "Elletia": ["Naragonthid", "Venexia"],
    "Espoia": ["Ajuna", "Daomea", "Nefrid", "Odatria"],
    "Lamacia": ["Aunon", "Osana", "Vianaa"],
    "Liadnon": ["Ahtep", "Amennia", "Anodia", "Naragonthid", "Quil'en", "Sstep"],
    "Linan": ["Orhas", "Vianaa"],
    "Mose": ["Damlére", "Daomea", "Riar", "Role", "Vice"],
    "Naragonthid": ["Amennia", "Azincourne", "Elletia", "Liadnon", "Quil'en", "Sstep", "Venexia"],
    "Nefrid": ["Conda", "Espoia", "Odatria"],
    "North Affrancia": ["Damlére", "Role", "South Affrancia", "Vense"],
    "Odatria": ["Ajuna", "Cinto", "Conda", "Espoia", "Nefrid", "Riar", "Vice"],
    "Orhas": ["Carnae", "Cualus", "Linan", "Orlais"],
    "Orlais": ["Carnae", "Cualus", "Orhas", "South Affrancia"],
    "Osana": ["Lamacia", "Vianaa"],
    "Oucine": ["Ahara", "Cinto", "Vice"],
    "Quil'en": ["Anodia", "Liadnon", "Naragonthid", "Sordia", "The Comet"],
    "Riar": ["Ajuna", "Daomea", "Mose", "Odatria", "Vice"],
    "Role": ["Damlére", "Mose", "North Affrancia", "Vice"],
    "Révia": ["Azincourne", "Venexia"],
    "Sordia": ["Anodia", "Aunon", "Quil'en", "The Comet"],
    "South Affrancia": ["Carnae", "North Affrancia", "Orlais", "Vense"],
    "Sstep": ["Amennia", "Liadnon", "Naragonthid"],
    "The Comet": ["Quil'en", "Sordia"],
    "Venexia": ["Azincourne", "Elletia", "Naragonthid", "Révia"],
    "Vense": ["Carnae", "North Affrancia", "South Affrancia"],
    "Vianaa": ["Lamacia", "Linan", "Osana"],
    "Vice": ["Cinto", "Mose", "Odatria", "Oucine", "Riar", "Role"]
}

# Get the center coordinates of a territory
def get_territory_center(territory_name):
    """Get the center point (centroid) of a territory in world coordinates"""
    return TERRITORY_CENTERS.get(territory_name, (0, 0))

# Get all territory names as a list
def get_all_territories():
    return list(TERRITORY_CENTERS.keys())

# Check if two territories are adjacent
def are_adjacent(territory1, territory2):
    return territory2 in ADJACENCIES.get(territory1, [])

# Get all neighbors of a territory
def get_neighbors(territory):
    return ADJACENCIES.get(territory, [])
