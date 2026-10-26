# -*- coding: utf-8 -*-
"""
Plot Effect Styles

The look of the persistent effects drawn on map plots, in one place:
- 'rays': production light rays (ProductionRays, production_glow_effect.py) on
  Barracks training units and Keeps/Castles training heroes
- 'dust': construction dust (ConstructionDust, construction_dust_effect.py) on
  plots under construction and Keeps being upgraded to Castles

Styles are keyed by map look ('2d' / '3d', map_data.get_current_look()). Both
looks share one style today; give '3d' its own dicts when the 3D look should
differ (owner, 2026-10-26: "for now both will share the same display").

All sizes are in PLOT RADII (EMPTY_PLOT_RADIUS * ui_scale, 16..24 px), so the
effects match the plot at every zoom level.
"""

import zlib

# ========================================
# PRODUCTION LIGHT RAYS
# ========================================
# Two counter-rotating layers of soft light beams emerging from behind the plot
# (BFME II War of the Ring style). Co-prime ray counts (7 and 5) keep the two
# layers from ever settling into a fixed pattern, so the overlap shimmers.
RAY_STYLE = {
    'layers': (
        {
            'count': 7,           # rays in the layer
            'speed': 7.0,         # degrees per second (positive = counter-clockwise)
            'reach': 2.6,         # where the rays fade out, in plot radii
            'half_angle': 4.5,    # angular half-width of a ray, degrees
            'intensity': 0.75,    # peak brightness at the plot rim (0-1)
            # Per-ray brightness: dimmer rays fade out sooner, so they read as shorter
            'ray_gain': (1.0, 0.68, 0.92, 0.6, 0.86, 0.74, 0.96),
        },
        {
            'count': 5,
            'speed': -4.5,        # turns the other way
            'reach': 2.0,
            'half_angle': 3.5,
            'intensity': 0.45,
            'ray_gain': (1.0, 0.8, 0.94, 0.7, 0.88),
        },
    ),
    # Rotation smoothness: a layer is re-rotated each time it turns this far.
    # 0.25 deg is ~0.13 px where the rays are bright, ~28 times a second: smooth.
    # (1.5-2 deg steps visibly ticked; owner, 2026-10-26: "stutters a little bit")
    'angle_step': 0.25,
    # Plots are split into this many groups by their phase, each turned a different
    # amount, so neighbours don't move in lockstep. Each group costs one rotation
    # per layer per angle_step.
    'phase_groups': 2,
    'inner': 0.6,                 # rays start here (hidden under the plot disc)
    'falloff_power': 1.3,         # brightness along a ray: (1 - t) ** power past the rim
    'halo_intensity': 0.18,       # soft ring of light just outside the plot rim
    'halo_width': 0.28,           # ring half-width, plot radii
    'white_mix': 0.30,            # player colour blended toward warm white, so it reads as light
    'warm_white': (255, 240, 215),
}

# ========================================
# CONSTRUCTION DUST
# ========================================
# Stateless particles: every position is a function of (clock, plot phase), so
# nothing has to be synced with game state. Angles are in degrees with y DOWN
# (0 = right, 90 = below the plot centre).
DUST_STYLE = {
    # Dust clouds rolling around the base, in warm sienna earth tones: they stand
    # out from the beige parchment of the 2D map by hue as well as tone, and from
    # the olive ground of the 3D one. (Mid-tone grey-browns were tried first and
    # were hard to see on the beige map; owner, 2026-10-26.)
    # 'softness' is the edge falloff exponent (lower = fuller).
    # Back clouds, drawn before the plot disc: they show around the lower rim
    'puffs': {
        'count': 5,
        'life': (2.2, 3.4),       # seconds per cloud
        'arc': (0.0, 180.0),      # where clouds form on the rim
        'distance': 1.05,         # from the plot centre, plot radii (mostly outside the ring)
        'drift': 0.35,            # outward + upward drift over a life
        'size': (1.0, 1.9),       # diameter at birth / at death, plot radii
        'alpha': 245,             # peak alpha
        'swell': 0.25,            # life fraction to reach full strength
        'hold': 0.55,             # full strength until this life fraction, then fades out
        'softness': 0.55,
        'colours': ((170, 108, 62), (146, 90, 50), (192, 132, 82)),
    },
    # Front clouds, drawn over the plot: thinner, across the bottom of the plot ring
    'front_puffs': {
        'count': 2,
        'life': (2.6, 3.6),
        'arc': (40.0, 140.0),
        'distance': 0.95,
        'drift': 0.25,
        'size': (0.8, 1.4),
        'alpha': 185,
        'swell': 0.25,
        'hold': 0.55,
        'softness': 0.7,
        'colours': ((176, 114, 68), (150, 96, 56)),
    },
    # Front layer, drawn over the plot: motes rising from the lower rim
    'motes': {
        'count': 10,
        'life': (2.2, 3.6),
        'arc': (-25.0, 205.0),    # most of the rim, open at the top
        'distance': (0.65, 1.1),
        'rise': (1.0, 1.8),       # height gained over a life, plot radii
        'sway': (0.06, 0.16),     # sideways sway amplitude, plot radii
        'size': (3.5, 6.5),       # diameter in px at the smallest plot radius (16)
        'alpha': 235,
        'softness': 0.45,
        'colours': ((252, 246, 232), (170, 110, 64), (96, 64, 40)),
    },
    # Front layer: tiny debris chips hopping off the building now and then (work going on)
    'chips': {
        'count': 2,
        'cycle': (1.7, 3.1),      # seconds between hops
        'hop': 0.55,              # seconds a hop lasts
        'start': 0.35,            # hop starts this far from the centre, plot radii
        'reach': 0.6,             # sideways distance travelled
        'height': 0.5,            # arc height
        'size': 2.5,              # px at plot radius 16
        'alpha': 240,
        'colours': ((74, 54, 34), (108, 84, 56)),
    },
    # Keep -> Castle upgrade in progress: every Nth mote is a twinkling gold glint
    'upgrade': {
        'glint_every': 2,         # every 2nd mote is gold
        'alpha': 255,
        'size_mult': 1.25,        # glints are a little larger than dust motes
        'twinkle': 30.0,          # twinkle speed, radians over a mote's life (~5 twinkles)
        'colours': ((255, 204, 60), (255, 232, 130)),
    },
}

PLOT_FX_STYLES = {
    '2d': {'rays': RAY_STYLE, 'dust': DUST_STYLE},
    '3d': {'rays': RAY_STYLE, 'dust': DUST_STYLE},
}


def get_plot_fx_style(look):
    """The plot effect style for a map look ('2d' / '3d'); unknown looks use 2D."""
    return PLOT_FX_STYLES.get(look, PLOT_FX_STYLES['2d'])


def plot_phase(territory, plot_index):
    """
    A stable animation offset in [0, 1) for one plot.

    Lets every plot animate out of step with its neighbours. Uses crc32, not
    hash(): str hashes change between runs (PYTHONHASHSEED), which would make
    the effects differ run to run and break deterministic tests.
    """
    key = f'{territory}|{plot_index}'.encode('utf-8')
    return (zlib.crc32(key) & 0xFFFFFF) / float(0x1000000)
