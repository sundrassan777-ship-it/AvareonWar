# -*- coding: utf-8 -*-
"""
Map Marker Effect Styles

The look of the map's event markers, in one place (event FX pass, 2026-10):
light in the style of the order effects - a normal-blend tint that carries the
colour on the bright map, additive light over it.

- 'kinds'    a battle to resolve ('battle') and allies arriving at the same
             territory together ('alliance'): the icon over a halo of its colour,
             a breathing ring of light with soft rings pulsing outward, and motes
             of light spiralling in (the old hurricane, as light)
- 'greyed'   the same marker when it isn't yours to click: ash grey, dimmer,
             no pulses
- 'marker'   the shape the kinds share
- 'overflow' the warning on a territory holding more armies than the limit
             (simultaneous mode, after an alliance arrival): an amber ring
             breathing fast, pulses running outward

COLOURS (owner, 2026-10-27): a battle takes the attack arrows' coral-red, an
alliance arrival the 'ally' arrows' green (config/constants.py COLOR_ARROW_*),
so red means attack and green means ally everywhere on the map.

Styles are keyed by map look ('2d' / '3d'); both looks share one style today.

UNITS: sizes and distances in PLOT RADII (EMPTY_PLOT_RADIUS * ui_scale, 16..24
px), so the markers grow and shrink with the zoom like the plots; times in seconds.
"""

from config.constants import COLOR_ARROW_ATTACK, COLOR_ARROW_REINFORCE, COLOR_ARROW_CANCELLED

WARM_WHITE = (255, 240, 215)

# ========================================
# MARKER KINDS
# ========================================
KINDS = {
    # Crossed swords over coral-red light, four spiral arms
    'battle': {
        'colour': COLOR_ARROW_ATTACK,
        'white_mix': 0.1,
        'icon': 'assets/mapicons/BattleIcon1.png',
        'icon_size': 3.6,      # the icon's longer side, plot radii
        'arms': 4,
    },
    # One sword over the allies' green, three spiral arms
    'alliance': {
        'colour': COLOR_ARROW_REINFORCE,
        'white_mix': 0.1,
        'icon': 'assets/mapicons/AllianceIcon1.png',
        'icon_size': 4.2,
        'arms': 3,
    },
}

# Not yours to click (another player resolves the battle / chooses the owner):
# ash grey, like a cancelled order, dimmer and still
GREYED = {
    'colour': COLOR_ARROW_CANCELLED,
    'white_mix': 0.05,
    'brightness': 0.55,        # share of the light...
    'tint': 0.6,               # ...and of the tint alpha
    'icon_grey': True,         # the icon in greyscale
    'icon_alpha': 210,
}

# ========================================
# MARKER SHAPE (both kinds)
# ========================================
MARKER = {
    'appear': 0.35,            # seconds to fade in when a marker first shows
    # The colour under everything (normal blend): what carries the hue on the map
    'halo': {
        'size': 5.4,           # diameter, plot radii
        'alpha': 125,
        'softness': 1.2,
    },
    # A ring of light round the icon, breathing
    'ring': {
        'radius': 2.4,         # plot radii
        'width': 0.1,          # ring half-width, share of its radius
        'intensity': 0.8,      # at the top of a breath...
        'breath_depth': 0.35,  # ...and this much less at the bottom
        'breath': 0.45,        # breaths per second
        'tint': 160,           # alpha of the colour band under it
    },
    # Soft rings leaving the ring and growing outward while they fade
    'pulses': {
        'count': 2,
        'period': 2.0,
        'reach': 1.7,          # final radius, share of the ring radius
        'width': 0.09,
        'intensity': 0.7,
        'tint': 110,
    },
    # Motes of light on spiral arms, drawn in toward the icon while the arms turn
    'motes': {
        'count': 40,           # all arms together
        'life': (1.6, 2.6),    # seconds from the outer edge to the centre
        'outer': 3.7,          # plot radii where a mote appears...
        'inner': 1.0,          # ...and where it goes out
        'spiral': 2.6,         # radians an arm winds from its outer end to its inner end
        'spin': 0.16,          # turns per second
        'jitter': 0.3,         # radians a mote may stray from its arm
        'size': (0.45, 0.8),   # diameter, plot radii
        'intensity': 1.0,
        'white_mix': 0.3,      # whiter than the ring: reads as a spark
        'tint': 120,           # alpha of the colour halo under each mote
        'tint_size': 2.2,      # halo diameter / mote diameter
    },
    'click': 3.3,              # click radius, plot radii (covers the icon and the ring)
    'label_gap': 0.35,         # plot radii between the icon's bottom and the "#N" label
    'label_shadow': (20, 14, 8),
}

# ========================================
# ARMY OVERFLOW WARNING
# ========================================
OVERFLOW = {
    'colour': (255, 125, 20),  # amber: a warning, not an attack
    'white_mix': 0.1,
    'gap': 0.7,                # plot radii from the army circle's rim to the ring (outside a reticle's)
    'width': 0.1,
    'intensity': 0.9,
    'breath_depth': 0.45,
    'breath': 1.3,             # breaths per second: urgent
    'tint': 170,
    'pulses': {
        'count': 2,
        'period': 1.1,
        'reach': 1.9,
        'width': 0.09,
        'intensity': 0.8,
        'tint': 120,
    },
}

MARKER_FX_STYLE = {
    'kinds': KINDS,
    'greyed': GREYED,
    'marker': MARKER,
    'overflow': OVERFLOW,
    'warm_white': WARM_WHITE,
}

MARKER_FX_STYLES = {
    '2d': MARKER_FX_STYLE,
    '3d': MARKER_FX_STYLE,
}


def get_marker_fx_style(look):
    """The map marker style for a map look ('2d' / '3d'); unknown looks use 2D."""
    return MARKER_FX_STYLES.get(look, MARKER_FX_STYLES['2d'])
