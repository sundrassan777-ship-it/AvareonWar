# -*- coding: utf-8 -*-
"""
Order Effect Styles

The look of the map's input marks, in one place (order FX pass, 2026-10): light
in the style of the production rays and hero abilities - a normal-blend tint
that carries the colour on the bright map, additive light over it.

- 'selection'  the green ring round a selected banner or building: light runs
               round it and soft rings pulse outward from it
- 'arrows'     the arrows of movement orders: a light path bowed slightly to
               the right of travel, crests of light flowing toward the target,
               a chevron head and a flare at its tip
- 'reticle'    the mark on a selected army's order destinations: a ring with
               four ticks at N/E/S/W (from the hero targeting circle's spikes)

Styles are keyed by map look ('2d' / '3d'); both looks share one style today.

UNITS: sizes and distances in PLOT RADII (EMPTY_PLOT_RADIUS * ui_scale, 16..24
px), so the marks match the plots at every zoom; times in seconds.

COLOURS keep the meanings the flat arrows had (config/constants.py): green for
the player's own orders, cyan for an ally's, gold while the order's Action
Queue card is under the mouse, red for an order being auto-cancelled.
"""

from config.constants import (COLOR_ARROW_MOVEMENT, COLOR_ARROW_HOVERED, COLOR_ARROW_ALLY,
                              COLOR_ARROW_CANCELLED)

WARM_WHITE = (255, 240, 215)

# ========================================
# SELECTION RING
# ========================================
SELECTION = {
    'colour': (30, 215, 60),
    'white_mix': 0.1,
    # A ring of light just outside the selected plot / army circle, with
    # crests running round it (like the hero aura border light)
    'ring': {
        'gap': 0.24,           # plot radii between the target's rim and the ring
        'size': 0.44,          # bead diameter, plot radii
        'spacing': 0.42,       # bead spacing, share of the bead diameter
        'base': 0.5,           # steady light all round
        'crest': 0.5,          # extra light at the crests
        'crests': 2,           # crests on the ring at once
        'speed': 0.3,          # turns per second
        'intensity': 1.0,
        # The green band under the light (normal blend): the hue on the bright map
        'tint_width': 0.13,    # Gaussian ring half-width, share of the radius
        'tint': 150,           # alpha
    },
    # Soft rings leaving the ring and growing outward while they fade
    'pulses': {
        'count': 2,            # in flight at once, evenly spaced in time
        'period': 1.6,         # seconds from leaving the ring to gone
        'reach': 1.85,         # final radius, share of the ring radius
        'width': 0.09,         # ring half-width, share of its radius
        'intensity': 0.85,
        'tint': 110,           # alpha of the colour ring under it, at the start
    },
}

# ========================================
# ORDER ARROWS
# ========================================
ARROWS = {
    'kinds': {
        'own': {'colour': COLOR_ARROW_MOVEMENT, 'white_mix': 0.1, 'intensity': 0.85},
        'ally': {'colour': COLOR_ARROW_ALLY, 'white_mix': 0.1, 'intensity': 0.85},
        # Brighter as well as gold: the card under the mouse points at its arrow
        'hovered': {'colour': COLOR_ARROW_HOVERED, 'white_mix': 0.15, 'intensity': 1.0},
        # The flow stops; the cancel animation fades it out and shakes it
        'cancelled': {'colour': COLOR_ARROW_CANCELLED, 'white_mix': 0.05, 'intensity': 0.9,
                      'flowing': False},
    },
    'start_gap': 0.9,          # plot radii from the source banner to the tail
    'end_gap': 1.3,            # plot radii from the tip to the target banner
    'bow': 0.07,               # sideways bow to the right of travel, share of the length
    'max_bow': 1.6,            # ...at most this many plot radii (A->B and B->A part)
    'size': 0.48,              # light bead diameter, plot radii
    'spacing': 0.42,           # bead spacing, share of the bead diameter
    # Crests of light flowing from source to target: a sharp front, a long trail
    'base': 0.4,               # steady light along the path
    'crest': 0.6,              # extra light at a crest
    'wave_length': 4.5,        # plot radii between crests
    'flow': 0.8,               # crests passing a point per second
    'tint': {'size': 1.05, 'spacing': 0.36, 'alpha': 135, 'softness': 1.0},
    'head': {
        'length': 1.05,        # chevron arm length, plot radii
        'angle': 32.0,         # degrees between an arm and the shaft
        'base': 0.7,           # the head stays bright between crests...
        'crest': 0.3,          # ...and flashes as one arrives
        'flare': 1.2,          # diameter of the light at the tip, plot radii
        'flare_intensity': 0.7,
    },
}

# ========================================
# DESTINATION RETICLE
# ========================================
RETICLE = {
    'kinds': {
        'attack': {'colour': (225, 35, 25), 'white_mix': 0.08},
        'merge': {'colour': (0, 195, 210), 'white_mix': 0.1},
    },
    'gap': 0.3,                # plot radii between the army circle and the ring
    'width': 0.09,             # ring half-width, share of its radius
    'intensity': 0.85,
    'tint': 150,
    'breath': 0.7,             # breaths per second (ring brightness, ticks in / out)
    'ticks': {
        'gap': 0.25,           # plot radii from the ring to a tick's inner end...
        'travel': 0.25,        # ...plus up to this much while breathing out
        'length': 0.55,        # plot radii
        'size': 0.42,          # bead diameter, plot radii
        'spacing': 0.45,
        'intensity': 0.9,
        'tint': 140,
    },
}

ORDER_FX_STYLE = {
    'selection': SELECTION,
    'arrows': ARROWS,
    'reticle': RETICLE,
    'warm_white': WARM_WHITE,
}

ORDER_FX_STYLES = {
    '2d': ORDER_FX_STYLE,
    '3d': ORDER_FX_STYLE,
}


def get_order_fx_style(look):
    """The order effect style for a map look ('2d' / '3d'); unknown looks use 2D."""
    return ORDER_FX_STYLES.get(look, ORDER_FX_STYLES['2d'])
