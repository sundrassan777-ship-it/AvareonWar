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
               a chevron head and a flare at its tip; coloured by order kind
- 'reticle'    the mark on a selected army's order destinations: a ring in the
               order kind's colour, with four ticks at N/E/S/W (from the hero
               targeting circle's spikes) on an attack only
- 'beckon'     a campaign / tutorial "click here" on a plot: a gold ring whose
               pulses close in on it, and a chevron of light bobbing above it
- 'objective'  a campaign / tutorial target territory: gold light running round
               its border (the hero aura border light) over a faint gold wash
- 'guide'      the gold glow round a highlighted button, tab or icon (UI)

GOLD is the colour of the player's input to give (owner, 2026-10-27): the hero
targeting circle, the hovered route and every tutorial highlight.

Styles are keyed by map look ('2d' / '3d'); both looks share one style today.

UNITS: sizes and distances in PLOT RADII (EMPTY_PLOT_RADIUS * ui_scale, 16..24
px), so the marks match the plots at every zoom; times in seconds.

COLOURS by order kind (GameState.order_kind), the same as the Action Queue
cards (config/constants.py COLOR_ARROW_*): 'attack' coral-red, 'own' (a move
into your own territory) blue, 'ally' (reinforcing an ally) green. Gold while
the order's card is under the mouse; an auto-cancelled order fizzles out in ash
grey. Allies' orders (simultaneous mode) take their kind's colour, dimmer and
without the flow (ARROWS['allied']). The reticle takes the kind's colour, and
only an attack's has ticks, so the shape tells attack from move as well as
the colour (red / green colour blindness).
"""

from config.constants import (COLOR_ARROW_ATTACK, COLOR_ARROW_MOVE, COLOR_ARROW_REINFORCE,
                              COLOR_ARROW_HOVERED, COLOR_ARROW_CANCELLED)

WARM_WHITE = (255, 240, 215)
GUIDE_GOLD = (255, 190, 60)

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
        'attack': {'colour': COLOR_ARROW_ATTACK, 'white_mix': 0.08, 'intensity': 0.85},
        'own': {'colour': COLOR_ARROW_MOVE, 'white_mix': 0.1, 'intensity': 0.85},
        'ally': {'colour': COLOR_ARROW_REINFORCE, 'white_mix': 0.1, 'intensity': 0.85},
        # Brighter as well as gold: the card under the mouse points at its arrow
        'hovered': {'colour': COLOR_ARROW_HOVERED, 'white_mix': 0.15, 'intensity': 1.0},
        # Ash grey, the flow stopped: the cancel animation shakes it while its beads
        # go out one by one (fizzle) and the rest fade (owner: not red, which now
        # means attack)
        'cancelled': {'colour': COLOR_ARROW_CANCELLED, 'white_mix': 0.05, 'intensity': 0.8,
                      'flowing': False, 'fizzle': True},
    },
    # An ally's order (simultaneous mode): its kind's colour, dimmer, no flow
    'allied': {'brightness': 0.55, 'tint': 0.6},
    'start_gap': 0.9,          # plot radii from the source banner to the tail
    'end_gap': 1.3,            # plot radii from the tip to the target banner
    'bow': 0.07,               # sideways bow to the right of travel, share of the length
    'max_bow': 1.6,            # ...at most this many plot radii (A->B and B->A part)
    'size': 0.34,              # light bead diameter, plot radii (owner: thinner, twice)
    'spacing': 0.42,           # bead spacing, share of the bead diameter
    # Crests of light flowing from source to target: a sharp front, a long trail
    'base': 0.4,               # steady light along the path
    'crest': 0.6,              # extra light at a crest
    'wave_length': 4.5,        # plot radii between crests
    'flow': 0.8,               # crests passing a point per second
    'tint': {'size': 0.74, 'spacing': 0.36, 'alpha': 140, 'softness': 1.0},
    'head': {
        'length': 1.05,        # chevron arm length, plot radii
        'angle': 32.0,         # degrees between an arm and the shaft
        'base': 0.7,           # the head stays bright between crests...
        'crest': 0.3,          # ...and flashes as one arrives
        'flare': 1.05,         # diameter of the light at the tip, plot radii
        'flare_intensity': 0.7,
    },
}

# ========================================
# DESTINATION RETICLE
# ========================================
RETICLE = {
    'kinds': {
        'attack': {'colour': COLOR_ARROW_ATTACK, 'white_mix': 0.08, 'ticks': True},
        'own': {'colour': COLOR_ARROW_MOVE, 'white_mix': 0.1, 'ticks': False},
        'ally': {'colour': COLOR_ARROW_REINFORCE, 'white_mix': 0.1, 'ticks': False},
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

# ========================================
# TUTORIAL / CAMPAIGN GUIDANCE (gold)
# ========================================
# "Click here" on a plot: the opposite motion of the selection ring - pulses
# close in on the plot - and a chevron of light bobbing above it, pointing down
BECKON = {
    'colour': GUIDE_GOLD,
    'white_mix': 0.12,
    'gap': 0.3,                # plot radii between the plot's rim and the ring
    'intensity': 0.85,         # the ring, breathing between 70% and 100% of it
    'tint': 150,               # alpha of the gold band under the ring
    'breath': 0.9,             # breaths per second
    'pulses': {
        'count': 2,
        'period': 1.4,         # seconds from the outer edge to the ring
        'reach': 2.1,          # where a pulse starts, share of the ring radius
        'intensity': 0.8,      # at the ring (a pulse brightens as it closes in)
        'tint': 90,
    },
    'chevron': {
        'size': 0.42,          # bead diameter, plot radii
        'spacing': 0.42,
        'arm': 0.6,            # arm length, plot radii
        'angle': 42.0,         # degrees between an arm and the vertical
        'height': 0.75,        # plot radii from the ring's top to the chevron's tip
        'bob': 0.22,           # plot radii up and down
        'bob_speed': 1.2,      # bobs per second
        'intensity': 1.0,
        'tint': 150,
    },
}

# A target territory (the tutorial's "attack the territory to the north")
OBJECTIVE = {
    'colour': GUIDE_GOLD,
    'white_mix': 0.12,
    'fill_alpha': 34,          # the faint gold wash over the territory (normal blend)
    'rim': {
        'size': 0.62,
        'spacing': 0.5,
        'inset': 0.45,
        'base': 0.3,
        'wave': 0.7,
        'wave_speed': 0.5,
        'intensity': 0.9,
        'tint': {'size': 1.2, 'spacing': 0.42, 'inset': 0.3, 'alpha': 110, 'softness': 1.0},
    },
}

# The glow round a highlighted button, tab or icon: additive light hugging its
# outline, breathing
GUIDE = {
    'colour': GUIDE_GOLD,
    'reach': 9,                # px of glow outside the outline (scaled with the UI)
    'base': 0.55,              # brightness at the bottom of a breath...
    'amplitude': 0.45,         # ...plus this at the top
    'breath': 0.9,             # breaths per second
    'tint': (255, 214, 120),   # inner tint of a highlighted ornate button (End Turn, Select All)
}

ORDER_FX_STYLE = {
    'selection': SELECTION,
    'arrows': ARROWS,
    'reticle': RETICLE,
    'beckon': BECKON,
    'objective': OBJECTIVE,
    'guide': GUIDE,
    'warm_white': WARM_WHITE,
}

ORDER_FX_STYLES = {
    '2d': ORDER_FX_STYLE,
    '3d': ORDER_FX_STYLE,
}


def get_order_fx_style(look):
    """The order effect style for a map look ('2d' / '3d'); unknown looks use 2D."""
    return ORDER_FX_STYLES.get(look, ORDER_FX_STYLES['2d'])
