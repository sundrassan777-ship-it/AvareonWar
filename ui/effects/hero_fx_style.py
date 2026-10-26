# -*- coding: utf-8 -*-
"""
Hero Ability Effect Styles

The look of every hero ability effect, in one place (hero ability FX pass,
2026-10): light in the style of the production rays - additive, soft, slow -
with each ability keeping its own colour, blended toward warm white so it reads
as light (owner, 2026-10-26: ability colours, not player colours).

- HERO_RAY_STYLE   ray bursts (a second ProductionRays with this style)
- 'kit'            border beads, shimmer waves, rings, firefly spawn points
- 'auras'          passive auras shown while their hero is selected
- 'abilities'      one entry per active ability: a colour and a timeline of cues

Styles are keyed by map look ('2d' / '3d'); both looks share one style today.

UNITS: sizes and distances of effects at a point (a Keep, a target) are in PLOT
RADII (EMPTY_PLOT_RADIUS * ui_scale, 16..24 px), like the plot effects; effects
over a territory (border light, fireflies) are in world px; times in seconds.

CUES (one entry of an ability's 'cues'):
    kind      'rays' | 'flare' | 'ring' | 'sparks' | 'rim' | 'motes' | 'each'
    at        start, seconds after the cast
    anchor    'target' (territory centre) | 'keep' (the hero's Keep plot) |
              'territory' (the target territory) | 'points' (points inside it,
              for 'each') - resolved by MapRenderer.trigger_ability_effect()
    duration  seconds; fade_in / fade_out shape the brightness envelope
    intensity peak brightness 0-1
    colour / white_mix   override the ability's
  rays:   spin (rotation speed multiplier)
  flare:  size (start, peak) diameter in plot radii, grow (seconds to peak),
          tint (alpha of a normal-blend colour halo under it: keeps the hue on
          the bright map; 0 = none), tint_size (halo diameter / flare diameter)
  ring:   radius (start, end) in plot radii (eased out), tint (alpha of the
          normal-blend colour ring under it)
  sparks: count, life (min, max), spread (start jitter), distance (min, max)
          in plot radii, size (min, max) diameter in plot radii, motion
          'explode' | 'implode' | 'fountain', swirl (radians over a life),
          rise (fountain height, plot radii)
  rim:    size (bead diameter, plot radii), spacing (bead spacing, share of
          the diameter), inset (diameters inside the border), base (glow
          everywhere on the border), head (extra light at the sweeping head),
          sweep (seconds for the head to go round each border), tint (a colour
          band under the light: size, spacing, inset, alpha, softness)

LIGHT ON THE PARCHMENT: additive light washes out toward white on the bright 2D
map, so the colour comes from a low white_mix plus the normal-blend 'tint'
layers under the light; the additive part supplies the glow.
  motes:  count (per territory), life (min, max), rise / sway (world px),
          size (min, max) diameter in plot radii
  each:   stagger, cues - the cues repeated at every point of the anchor
"""

WARM_WHITE = (255, 240, 215)

# ========================================
# RAY BURST
# ========================================
# Same shape as plot_fx_style.RAY_STYLE (ProductionRays reads it), but longer,
# faster and brighter: a burst of light, not a glow.
HERO_RAY_STYLE = {
    'layers': (
        {
            'count': 9,
            'speed': 18.0,
            'reach': 3.6,
            'half_angle': 3.4,
            'intensity': 0.9,
            'ray_gain': (1.0, 0.66, 0.9, 0.58, 0.96, 0.72, 0.86, 0.62, 0.92),
        },
        {
            'count': 7,
            'speed': -11.0,
            'reach': 2.5,
            'half_angle': 3.0,
            'intensity': 0.55,
            'ray_gain': (1.0, 0.78, 0.9, 0.68, 0.94, 0.74, 0.86),
        },
    ),
    'angle_step': 0.25,
    'phase_groups': 2,
    'inner': 0.6,
    'falloff_power': 1.5,
    'halo_intensity': 0.2,
    'halo_width': 0.3,
    'white_mix': 0.2,
    'warm_white': WARM_WHITE,
}

# ========================================
# KIT
# ========================================
KIT = {
    'fine_spacing': 0.6,    # world px between border beads before level of detail (fine, so
                            # the level-of-detail step can match the wanted spacing closely)
    'probe': 2.5,           # world px past a border to look for a lit neighbour (shared
                            # borders between lit territories are dropped: one outline)
    'inset': 0.9,           # beads sit this far inside the border, world px
    'wave_length': 48.0,    # world px of border per shimmer wave
    'ring_width': 0.16,     # soft ring half-width, share of its radius
    'spawn_points': 40,     # firefly spawn points per territory
}

# ========================================
# PASSIVE AURAS (while the hero is selected)
# ========================================
# Light along the outline of the covered territories with a slow shimmer running
# round it, and fireflies rising inside. 'spacing' is the bead spacing as a share
# of the bead diameter (smaller = smoother line, more beads).
def _aura(colour, white_mix, wave_speed, rise, intensity=0.6, tint_alpha=70):
    return {
        'colour': colour,
        'white_mix': white_mix,
        'fade': 0.35,              # seconds to fade in / out on select / deselect
        'rim': {
            'size': 0.62,          # bead diameter, plot radii
            'spacing': 0.5,        # bead spacing, share of the bead diameter
            'inset': 0.45,         # beads sit this many diameters inside the border
            'base': 0.22,          # steady light along the whole outline
            'wave': 0.78,          # extra light at the shimmer's crest
            'wave_speed': wave_speed,   # shimmer waves passing a point per second
            'intensity': intensity,
            # Colour band just inside the border, under the light (normal blend):
            # the hue stays readable on the bright 2D map
            'tint': {'size': 1.2, 'spacing': 0.42, 'inset': 0.3, 'alpha': tint_alpha,
                     'softness': 1.0},
        },
        # Fireflies inside the covered territories. The same density everywhere:
        # a median territory (~3500 world px^2 at 1600x900) gets ~14 (owner,
        # 2026-10-26: 7 per territory were barely visible)
        'motes': {
            'count': 30,           # the most fireflies one territory shows
            'density': 4.0,        # fireflies per 1000 world px^2 of territory...
            'min': 6,              # ...but at least this many
            'life': (1.4, 2.4),
            'rise': rise,          # world px over a life
            'sway': 1.4,           # world px
            'size': (0.6, 1.05),   # diameter, plot radii
            'intensity': 1.0,
            'white_mix': 0.35,     # a whiter core than the outline: reads as a spark
            'tint': 120,           # alpha of the colour halo under each firefly
            'tint_size': 2.2,      # halo diameter / firefly diameter
        },
    }


AURAS = {
    # Seledra Rennervail - Defiance (purple)
    'defiance': _aura((150, 50, 210), 0.06, wave_speed=0.45, rise=7.0),
    # Vearen Asford - Haste (orange): a quicker shimmer
    'haste': _aura((255, 130, 10), 0.04, wave_speed=0.9, rise=8.0),
    # Darius Brennhen / Regnus Aevencourne - Safe Haven (light blue): calm
    'safe_haven': _aura((80, 160, 255), 0.06, wave_speed=0.3, rise=6.0),
}

# ========================================
# ACTIVE ABILITIES
# ========================================
ABILITIES = {
    # Blue-white strike from above: a sharp flare, a fast shock ring and a second
    # one 0.2 s later (the double impact), rays, and a short spray of sparks
    'Decisive Strike': {
        'colour': (60, 120, 255),
        'white_mix': 0.15,
        'cues': (
            {'kind': 'flare', 'at': 0.0, 'anchor': 'target', 'duration': 0.6, 'size': (1.2, 3.6),
             'grow': 0.12, 'fade_in': 0.03, 'fade_out': 0.45, 'intensity': 0.85, 'tint': 150,
             'tint_size': 1.5},
            {'kind': 'rays', 'at': 0.0, 'anchor': 'target', 'duration': 1.0, 'fade_in': 0.05,
             'fade_out': 0.7, 'intensity': 0.85, 'spin': 2.5},
            {'kind': 'ring', 'at': 0.0, 'anchor': 'target', 'duration': 0.45, 'radius': (0.6, 3.6),
             'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.8, 'tint': 120},
            {'kind': 'ring', 'at': 0.2, 'anchor': 'target', 'duration': 0.5, 'radius': (0.5, 2.8),
             'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.7, 'white_mix': 0.4, 'tint': 90},
            {'kind': 'sparks', 'at': 0.02, 'anchor': 'target', 'count': 26, 'life': (0.5, 0.95),
             'spread': 0.1, 'distance': (1.6, 3.6), 'size': (0.4, 0.7), 'motion': 'explode',
             'swirl': 0.5, 'intensity': 1.0},
        ),
    },
    # Gold: light runs round the territory's border, eight "coins of light" pop
    # up across it one after another, and gold motes rise
    'Levy': {
        'colour': (255, 180, 30),
        'white_mix': 0.12,
        'points': 8,
        'cues': (
            {'kind': 'rim', 'at': 0.0, 'anchor': 'territory', 'duration': 1.9, 'fade_in': 0.12,
             'fade_out': 0.75, 'intensity': 0.8, 'size': 0.62, 'spacing': 0.5, 'inset': 0.45,
             'base': 0.18, 'head': 0.82, 'sweep': 1.1,
             'tint': {'size': 1.2, 'spacing': 0.42, 'inset': 0.3, 'alpha': 85, 'softness': 1.0}},
            {'kind': 'motes', 'at': 0.15, 'anchor': 'territory', 'duration': 2.0, 'fade_in': 0.2,
             'fade_out': 0.8, 'count': 10, 'life': (1.0, 1.6), 'rise': 9.0, 'sway': 1.2,
             'size': (0.5, 0.9), 'intensity': 1.0},
            {'kind': 'each', 'at': 0.05, 'anchor': 'points', 'stagger': 0.1, 'cues': (
                {'kind': 'flare', 'at': 0.0, 'duration': 0.55, 'size': (0.5, 1.6), 'grow': 0.1,
                 'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.9, 'tint': 130, 'tint_size': 1.6},
                {'kind': 'ring', 'at': 0.0, 'duration': 0.45, 'radius': (0.3, 1.4),
                 'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.45, 'tint': 60},
                {'kind': 'sparks', 'at': 0.03, 'count': 8, 'life': (0.6, 1.0), 'spread': 0.05,
                 'distance': (0.4, 1.3), 'size': (0.45, 0.7), 'motion': 'fountain', 'rise': 1.8,
                 'swirl': 0.0, 'intensity': 1.0},
            )},
        ),
    },
}

HERO_FX_STYLE = {
    'rays': HERO_RAY_STYLE,
    'kit': KIT,
    'auras': AURAS,
    'abilities': ABILITIES,
    'warm_white': WARM_WHITE,
}

HERO_FX_STYLES = {
    '2d': HERO_FX_STYLE,
    '3d': HERO_FX_STYLE,
}


def get_hero_fx_style(look):
    """The hero ability effect style for a map look ('2d' / '3d'); unknown looks use 2D."""
    return HERO_FX_STYLES.get(look, HERO_FX_STYLES['2d'])
