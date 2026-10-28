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
    kind      'rays' | 'flare' | 'ring' | 'sparks' | 'drain' | 'dust' (at a point),
              'rim' | 'motes' (over territories), 'comets' (from one point to
              another), 'curtain' (the whole screen), 'each' (repeat cues at points)
    at        start, seconds after the cast
    anchor    resolved by MapRenderer._ability_anchors():
              points - 'target' (territory centre), 'keep' (the caster hero's
              Keep plot), 'source' / 'dest' (arc ends);
              point lists for 'each' - 'points' (inside the target territory,
              the ability's 'points' of them), 'keeps' (the caster's Keeps and
              Castles), 'enemy_keeps' (up to 3), 'satellites' (4 around the target);
              territory lists - 'territory' (the target), 'territories' (up to 5
              of the caster's), 'enemy_territories' (the players it hits)
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
  motes:  count (per territory), life (min, max), rise / sway (world px),
          size (min, max) diameter in plot radii; optional density / min / lod /
          tint / tint_size / white_mix (see the auras)
  comets: from / to (anchors, default 'source' / 'dest'), count, travel
          (seconds per flight), stagger, arc (height, share of the distance),
          trail (motes behind the head), trail_gap (seconds between them), size
          (head diameter, plot radii), spread (sideways weave, world px), tint
  drain:  size (start, end) diameter in plot radii, grow, darkness (how dark
          the multiply colour is at the centre)
  dust:   count, life, spread, distance, size (start, end) in plot radii,
          alpha, softness, colours - normal-blend clouds, not light
  curtain: sweep (seconds to cross the screen), width (share of the screen),
          wave (front waviness, share of the height), alpha (at the front),
          ramp (how the alpha builds toward the front: < 1 full sooner),
          strip_colour (the strip; the front's light uses colour), embers (count)
  each:   stagger, cues - the cues repeated at every point of the anchor

LIGHT ON THE PARCHMENT: additive light washes out toward white on the bright 2D
map, so the colour comes from a low white_mix plus the normal-blend 'tint'
layers under the light; the additive part supplies the glow. Additive red over
a green territory turns yellow: where a colour must hold on any territory, let
the tint carry it (the Embargo border light).
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
# PERSISTENT EFFECTS (from game state)
# ========================================
PERSISTENT = {
    # Embargo: while players are embargoed (their next income blocked), embers
    # drift up over all their territories. Sparse: it can cover half the map
    'embargo': {
        'colour': (200, 40, 20),
        'white_mix': 0.12,
        'fade': 0.6,
        'motes': {
            'count': 14,
            'density': 1.4,        # embers per 1000 world px^2 (~5 in a median territory)...
            'min': 2,
            # ...thinned to 55% on the smallest plots (zoomed out, the whole map on
            # screen): it lasts a whole turn over every embargoed territory
            'lod': {'full_radius': 24, 'min_share': 0.55},
            'life': (2.0, 3.2),
            'rise': 11.0,
            'sway': 2.0,
            'size': (0.7, 1.15),
            'intensity': 1.0,
            # A hot orange-white core in a deep red smudge, lit for most of its life:
            # stands out on the bright 2D map's orange and yellow territories too
            # (owner, 2026-10-27: the embers could not be seen)
            'white_mix': 0.35,
            'glow_power': 1,
            'tint': 175,
            'tint_size': 1.8,
            'tint_colour': (125, 12, 8),
        },
    },
}

# The Vow of Silence fog over the map while anyone is silenced (main.py
# draw_silence_fog_overlay): a crimson vignette, faint over the middle of the map
# and deep toward its edges. Fades in, then holds (see main.py for why it doesn't pulse)
SILENCE_FOG = {
    'colour': (110, 0, 0),
    'centre_alpha': 40,
    'edge_alpha': 145,
    'fade': 1.5,               # seconds to fade in
}

# Master Negotiator while its discount lasts (main.py draw_negotiator_glow): a
# green wash over the edges of the map and motes of green light rising there.
# Shown to the caster only, like its sound (owner, 2026-10-27); fades in, then holds.
# Screen px are for a 900 px tall window, scaled to the real one
NEGOTIATOR_GLOW = {
    'colour': (25, 130, 45),
    'centre_alpha': 0,
    'edge_alpha': 110,
    'inner': 0.68,             # where the wash starts, share of the half-size (vignette_surface):
                               # the map's colours stay readable, only its rim turns green
    'fade': 0.8,               # seconds to fade in
    'motes': {
        'count': 56,
        'life': (1.2, 2.2),
        'rise': 40.0,          # px over a life
        'sway': 5.0,
        'size': (14.0, 26.0),  # diameter, px
        'band': 0.1,           # how far in from the edges they rise, share of the map height
        'colour': (60, 200, 80),
        'white_mix': 0.25,
        'tint': 90,            # alpha of a green halo under each mote: the map is bright
        'tint_size': 1.6,
    },
}

# Erec Silvyr's Ruthless Ingenuity while the tech tree is open (ui_renderer
# _draw_ingenuity_motes): motes of blue light rising over the technology panel.
# Px at UI scale 1
INGENUITY_MOTES = {
    'colour': (70, 120, 255),
    'white_mix': 0.3,
    'count': 40,
    'life': (1.5, 3.0),
    'rise': 60.0,              # px over a life
    'sway': 4.0,
    'size': (12.0, 22.0),      # diameter, px
    'top': 50,                 # px below the panel's top (its header) where they may start
    'tint': 70,
    'tint_size': 1.6,
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
    # --- Halon Nextroy ---
    # Fire orange on an enemy territory: a flash runs round its border and
    # embers flare up inside, one after another
    'Aggressive Diplomacy': {
        'colour': (235, 105, 15),
        'white_mix': 0.12,
        'points': 6,
        'cues': (
            {'kind': 'rim', 'at': 0.0, 'anchor': 'territory', 'duration': 1.6, 'fade_in': 0.08,
             'fade_out': 0.7, 'intensity': 0.9, 'size': 0.62, 'spacing': 0.5, 'inset': 0.45,
             'base': 0.25, 'head': 0.75, 'sweep': 0.8,
             'tint': {'size': 1.2, 'spacing': 0.42, 'inset': 0.3, 'alpha': 100, 'softness': 1.0}},
            {'kind': 'each', 'at': 0.1, 'anchor': 'points', 'stagger': 0.12, 'cues': (
                {'kind': 'flare', 'at': 0.0, 'duration': 0.5, 'size': (0.5, 1.5), 'grow': 0.1,
                 'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.9, 'tint': 130, 'tint_size': 1.6},
                {'kind': 'sparks', 'at': 0.02, 'count': 8, 'life': (0.4, 0.8), 'spread': 0.05,
                 'distance': (0.6, 1.6), 'size': (0.35, 0.6), 'motion': 'explode', 'swirl': 0.8,
                 'intensity': 1.0},
            )},
        ),
    },
    # --- Aidam Narn ---
    # Gold-white: light is pulled out of the target and three comets carry it
    # in an arc to Narn's Keep, where it flares
    'Royal Charisma': {
        'colour': (255, 210, 90),
        'white_mix': 0.2,
        'cues': (
            {'kind': 'sparks', 'at': 0.0, 'anchor': 'source', 'count': 18, 'life': (0.5, 0.8),
             'spread': 0.1, 'distance': (1.5, 3.0), 'size': (0.35, 0.6), 'motion': 'implode',
             'swirl': 1.5, 'intensity': 1.0},
            {'kind': 'flare', 'at': 0.0, 'anchor': 'source', 'duration': 0.6, 'size': (1.8, 0.6),
             'grow': 0.5, 'fade_in': 0.05, 'fade_out': 0.25, 'intensity': 0.8, 'tint': 100},
            {'kind': 'comets', 'at': 0.25, 'count': 3, 'travel': 1.0, 'stagger': 0.15, 'arc': 0.4,
             'trail': 14, 'trail_gap': 0.025, 'size': 1.3, 'spread': 4.0, 'tint': 150,
             'intensity': 1.0},
            {'kind': 'flare', 'at': 1.25, 'anchor': 'dest', 'duration': 0.6, 'size': (1.0, 3.0),
             'grow': 0.1, 'fade_in': 0.03, 'fade_out': 0.45, 'intensity': 0.9, 'tint': 130,
             'tint_size': 1.5},
            {'kind': 'ring', 'at': 1.25, 'anchor': 'dest', 'duration': 0.5, 'radius': (0.5, 2.6),
             'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.7, 'tint': 90},
            {'kind': 'rays', 'at': 1.2, 'anchor': 'dest', 'duration': 1.0, 'fade_in': 0.08,
             'fade_out': 0.7, 'intensity': 0.8, 'spin': 2.0},
        ),
    },
    # Dark purple: the light drains out of the target, a ring closes in, sparks
    # spiral inward and it ends in a small violet flare
    'Regicide': {
        'colour': (150, 30, 200),
        'white_mix': 0.15,
        'cues': (
            {'kind': 'drain', 'at': 0.0, 'anchor': 'target', 'duration': 2.2, 'size': (2.0, 5.0),
             'grow': 0.6, 'fade_in': 0.3, 'fade_out': 0.8, 'intensity': 0.9, 'darkness': 0.35},
            {'kind': 'ring', 'at': 0.05, 'anchor': 'target', 'duration': 0.9, 'radius': (4.0, 0.4),
             'fade_in': 0.1, 'fade_out': 0.3, 'intensity': 0.8, 'tint': 110},
            {'kind': 'sparks', 'at': 0.1, 'anchor': 'target', 'count': 26, 'life': (0.7, 1.1),
             'spread': 0.15, 'distance': (2.0, 4.0), 'size': (0.35, 0.65), 'motion': 'implode',
             'swirl': 2.5, 'intensity': 1.0},
            {'kind': 'flare', 'at': 1.0, 'anchor': 'target', 'duration': 0.6, 'size': (0.4, 1.8),
             'grow': 0.12, 'fade_in': 0.03, 'fade_out': 0.45, 'intensity': 0.9, 'tint': 140,
             'tint_size': 1.6},
            {'kind': 'sparks', 'at': 1.05, 'anchor': 'target', 'count': 10, 'life': (0.4, 0.7),
             'spread': 0.05, 'distance': (0.5, 1.4), 'size': (0.3, 0.5), 'motion': 'explode',
             'swirl': 0.5, 'intensity': 0.9},
        ),
    },
    # --- Erec Silvyr ---
    # Gold at every Keep and Castle of the caster: a small flare, a ring and a
    # few coins popping up, one Keep after another
    'Extort Populace': {
        'colour': (255, 180, 30),
        'white_mix': 0.12,
        'cues': (
            {'kind': 'each', 'at': 0.0, 'anchor': 'keeps', 'stagger': 0.05, 'cues': (
                {'kind': 'flare', 'at': 0.0, 'duration': 0.5, 'size': (0.5, 1.6), 'grow': 0.1,
                 'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.9, 'tint': 120, 'tint_size': 1.6},
                {'kind': 'ring', 'at': 0.0, 'duration': 0.45, 'radius': (0.3, 1.5),
                 'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.5, 'tint': 60},
                {'kind': 'sparks', 'at': 0.03, 'count': 5, 'life': (0.6, 1.0), 'spread': 0.05,
                 'distance': (0.3, 1.0), 'size': (0.4, 0.6), 'motion': 'fountain', 'rise': 1.6,
                 'swirl': 0.0, 'intensity': 1.0},
            )},
        ),
    },
    # --- Darius Brennhen / Regnus Aevencourne ---
    # Silver-white: rays behind the Keep, a ring, and motes gathering into it
    'Reinforce': {
        'colour': (200, 215, 240),
        'white_mix': 0.3,
        'cues': (
            {'kind': 'rays', 'at': 0.0, 'anchor': 'keep', 'duration': 1.4, 'fade_in': 0.15,
             'fade_out': 0.8, 'intensity': 0.9, 'spin': 1.5},
            {'kind': 'ring', 'at': 0.0, 'anchor': 'keep', 'duration': 0.5, 'radius': (0.6, 3.2),
             'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.75, 'tint': 90},
            {'kind': 'sparks', 'at': 0.1, 'anchor': 'keep', 'count': 22, 'life': (0.7, 1.1),
             'spread': 0.2, 'distance': (2.0, 3.8), 'size': (0.35, 0.6), 'motion': 'implode',
             'swirl': 1.0, 'intensity': 1.0},
            {'kind': 'flare', 'at': 0.7, 'anchor': 'keep', 'duration': 0.5, 'size': (0.5, 2.0),
             'grow': 0.1, 'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.85, 'tint': 110},
        ),
    },
    # --- Neil Hevilneu / Serthus Diarcess ---
    # Pale blue: a ring as the troops leave the Keep, comets arcing to the
    # target, an impact flare, ring and sparks where they land
    'Valorous Charge': {
        'colour': (140, 190, 255),
        'white_mix': 0.25,
        'cues': (
            {'kind': 'ring', 'at': 0.0, 'anchor': 'source', 'duration': 0.5, 'radius': (0.5, 2.4),
             'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.7, 'tint': 90},
            {'kind': 'flare', 'at': 0.0, 'anchor': 'source', 'duration': 0.4, 'size': (0.8, 2.0),
             'grow': 0.08, 'fade_in': 0.03, 'fade_out': 0.3, 'intensity': 0.8, 'tint': 100},
            {'kind': 'comets', 'at': 0.1, 'count': 4, 'travel': 0.9, 'stagger': 0.1, 'arc': 0.3,
             'trail': 14, 'trail_gap': 0.025, 'size': 1.25, 'spread': 5.0, 'tint': 150,
             'intensity': 1.0},
            {'kind': 'flare', 'at': 1.05, 'anchor': 'dest', 'duration': 0.55, 'size': (1.2, 3.4),
             'grow': 0.1, 'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.9, 'tint': 140,
             'tint_size': 1.5},
            {'kind': 'ring', 'at': 1.05, 'anchor': 'dest', 'duration': 0.5, 'radius': (0.6, 3.4),
             'fade_in': 0.03, 'fade_out': 0.4, 'intensity': 0.8, 'tint': 110},
            {'kind': 'sparks', 'at': 1.07, 'anchor': 'dest', 'count': 18, 'life': (0.5, 0.9),
             'spread': 0.08, 'distance': (1.2, 3.0), 'size': (0.35, 0.65), 'motion': 'explode',
             'swirl': 0.6, 'intensity': 1.0},
        ),
    },
    # --- Seledra Rennervail ---
    # A crimson curtain sweeps across the whole screen, embers flaring where its
    # front passes; the silence fog (main.py) fades in behind it
    'Vow of Silence': {
        'colour': (200, 20, 30),
        'white_mix': 0.2,
        'cues': (
            # A deep crimson strip, full right behind its glowing front (owner,
            # 2026-10-27: the curtain was hardly visible on the bright 2D map)
            {'kind': 'curtain', 'at': 0.0, 'duration': 2.0, 'sweep': 1.4, 'fade_in': 0.05,
             'fade_out': 0.5, 'intensity': 1.0, 'width': 0.32, 'wave': 0.05, 'alpha': 215,
             'ramp': 0.6, 'strip_colour': (150, 8, 22), 'embers': 90},
        ),
    },
    # --- Evain Nithieln ---
    # Dark red: a flash runs round the embargoed players' territories and sparks
    # are pulled into up to three of their Keeps. While the embargo lasts,
    # embers drift over their land ('persistent' above)
    'Embargo': {
        'colour': (200, 40, 20),
        'white_mix': 0.15,
        'cues': (
            # Red mostly from the tint band: additive red light over green or blue
            # territories turns yellow or pink
            {'kind': 'rim', 'at': 0.0, 'anchor': 'enemy_territories', 'duration': 1.6,
             'fade_in': 0.1, 'fade_out': 0.8, 'intensity': 0.5, 'size': 0.62, 'spacing': 0.5,
             'inset': 0.45, 'base': 0.35, 'head': 0.65, 'sweep': 1.2, 'white_mix': 0.05,
             'tint': {'size': 1.3, 'spacing': 0.42, 'inset': 0.3, 'alpha': 165, 'softness': 1.0}},
            {'kind': 'each', 'at': 0.1, 'anchor': 'enemy_keeps', 'stagger': 0.1, 'cues': (
                {'kind': 'sparks', 'at': 0.0, 'count': 14, 'life': (0.5, 0.8), 'spread': 0.08,
                 'distance': (1.2, 2.6), 'size': (0.35, 0.6), 'motion': 'implode', 'swirl': 1.2,
                 'intensity': 1.0},
                {'kind': 'flare', 'at': 0.45, 'duration': 0.45, 'size': (0.4, 1.4), 'grow': 0.1,
                 'fade_in': 0.03, 'fade_out': 0.3, 'intensity': 0.85, 'tint': 120},
            )},
        ),
    },
    # Green: rays behind Nithieln's Keep and light running round the borders of
    # up to five of the caster's territories
    'Master Negotiator': {
        'colour': (60, 200, 80),
        'white_mix': 0.15,
        'cues': (
            {'kind': 'rays', 'at': 0.0, 'anchor': 'keep', 'duration': 1.2, 'fade_in': 0.1,
             'fade_out': 0.7, 'intensity': 0.85, 'spin': 1.8},
            {'kind': 'flare', 'at': 0.0, 'anchor': 'keep', 'duration': 0.5, 'size': (0.6, 2.2),
             'grow': 0.1, 'fade_in': 0.03, 'fade_out': 0.35, 'intensity': 0.85, 'tint': 120},
            {'kind': 'rim', 'at': 0.1, 'anchor': 'territories', 'duration': 1.6, 'fade_in': 0.1,
             'fade_out': 0.7, 'intensity': 0.8, 'size': 0.62, 'spacing': 0.5, 'inset': 0.45,
             'base': 0.3, 'head': 0.7, 'sweep': 1.0,
             'tint': {'size': 1.2, 'spacing': 0.42, 'inset': 0.3, 'alpha': 90, 'softness': 1.0}},
        ),
    },
    # --- Vearen Asford ---
    # Dust, not light: clouds thrown up at the target and four hoof-impact
    # flashes around it, one after another (four Cavalry arriving)
    'Relentless Charge': {
        'colour': (235, 200, 140),
        'white_mix': 0.3,
        'cues': (
            {'kind': 'dust', 'at': 0.0, 'anchor': 'target', 'count': 14, 'life': (1.0, 1.7),
             'spread': 0.1, 'distance': (0.8, 2.6), 'size': (0.9, 2.4), 'alpha': 210,
             'softness': 0.6, 'colours': ((170, 108, 62), (146, 90, 50), (192, 132, 82))},
            {'kind': 'each', 'at': 0.15, 'anchor': 'satellites', 'stagger': 0.15, 'cues': (
                {'kind': 'dust', 'at': 0.0, 'count': 5, 'life': (0.8, 1.2), 'spread': 0.05,
                 'distance': (0.3, 1.0), 'size': (0.6, 1.6), 'alpha': 190, 'softness': 0.6,
                 'colours': ((170, 108, 62), (192, 132, 82))},
                {'kind': 'flare', 'at': 0.0, 'duration': 0.3, 'size': (0.3, 1.2), 'grow': 0.06,
                 'fade_in': 0.02, 'fade_out': 0.22, 'intensity': 0.8, 'tint': 80},
                {'kind': 'ring', 'at': 0.0, 'duration': 0.35, 'radius': (0.2, 1.2),
                 'fade_in': 0.02, 'fade_out': 0.28, 'intensity': 0.5, 'tint': 70},
            )},
        ),
    },
}

HERO_FX_STYLE = {
    'rays': HERO_RAY_STYLE,
    'kit': KIT,
    'auras': AURAS,
    'persistent': PERSISTENT,
    'silence_fog': SILENCE_FOG,
    'negotiator_glow': NEGOTIATOR_GLOW,
    'ingenuity_motes': INGENUITY_MOTES,
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
