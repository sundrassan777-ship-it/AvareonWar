# -*- coding: utf-8 -*-
"""
Battle Screen Effect Style

The look of the battle screen's bar fight (ui/effects/battle_fx_effect.py, driven
by BattleBarVolleyEffect in battle_interface.py), in the light style of the
hero / order / event passes:

- the bars: a gradient fill over a dark track, a seam of light at each bar's
  front, a faint sheen sliding along the fill
- shots: light gathers from the shooter's remaining bar into its front, then
  one bolt of light flies level at the enemy bar (flare, sparks, a shock ring,
  the chunk it destroys breaking off and falling out of the bar, embers)
- the finale: the bar left standing is swept with light and its frame glows gold
- the battle icon's gold glow and the backdrop's vignette

Sizes are in BAR HEIGHTS (H: the fill's height, 40 px at 1600x900), so the
effects scale with the screen. Times are in seconds. The battle screen is drawn
over the map whatever its look, so there is one style (no '2d' / '3d').
"""

from ui.effects.order_fx_style import GUIDE_GOLD

# ========================================
# THE BARS (drawn under the BattleBar frame)
# ========================================
BAR_STYLE = {
    # The fill: a vertical gradient of the player's colour, lighter at the top
    # (BottomPanelKit._bar_fill's recipe), with a thin glassy highlight line
    'fill_top': (1.3, 24),           # top colour = colour * gain + add
    'fill_bottom': (0.6, 0),
    'highlight_y': 0.2,              # share of H from the top
    'highlight_mix': 0.5,            # how far the highlight line is blended toward warm white
    # The empty track: dark bronze-black instead of flat grey
    'track_top': (34, 28, 21),
    'track_bottom': (12, 10, 8),
    # The seam of light at the bar's front (its inner tip)
    'seam': {
        'width': 0.9,                # H, the light's full width (a Gaussian across it)
        'white_mix': 0.3,
        'base': 0.42,                # brightness at rest
        'shimmer': 0.1,              # +- brightness, slow
        'shimmer_hz': 0.9,
        'hit_kick': 0.6,             # added when a bolt lands on this bar...
        'fire_kick': 0.25,           # ...and when this bar fires one
        'decay': 0.14,               # s, how fast a kick fades (exponential)
        'empty_fade': 0.04,          # fill share over which the seam fades out on an empty bar
    },
    # A soft slanted band of light sliding along the fill, outer end to front
    'sheen': {
        'width': 1.1,                # H
        'slant': 0.5,                # x shift top to bottom, H
        'period': 3.6,               # s between passes
        'travel': 1.6,               # s a pass takes
        'intensity': 0.2,
        'white_mix': 0.6,
    },
}

# ========================================
# A SHOT (one side's turn)
# ========================================
# Light gathers from the shooter's remaining bar into its front (the charge),
# then one bolt of light leaves from there and flies level at the enemy bar's
# front; the chunk it destroys breaks off and falls out of the bar.
# (A salvo of 3-5 smaller bolts was tried side by side and dropped - owner,
# 2026-10-28.)
BOLT_STYLE = {
    'travel': 0.2,                   # s to the enemy bar, straight across
    'ease': 1.2,                     # the flight speeds up into the target (u = p ** ease)
    'land_at': 0.15,                 # where in the chunk it lands (0 its front, 1 its back)
    'land_spread': 0.1,              # how far it may stray from that (share of the chunk)
    # The bolt: a hot head with a trail of fading motes (hero_fx comets)
    'head': 1.05,                    # H, the head's light diameter
    'white_mix': 0.35,
    'intensity': 1.0,
    'trail': 16,                     # motes behind the head, close enough to overlap into a streak
    'trail_gap': 0.0035,             # s between them
    'trail_shrink': 0.65,            # the last mote is this much smaller
    'halo': 2.4,                     # H, colour halo under the head (normal blend)
    'halo_alpha': 140,
}

# The charge (owner, 2026-10-28; may be rolled back - 'enabled': False puts the
# bolt back on the frame's spear tip, with no gathering): motes of light stream
# along the shooter's remaining bar into its front, a band of light sweeps the bar
# that way, the front's seam brightens and an orb of light swells there - then the
# bolt leaves from it.
CHARGE_STYLE = {
    'enabled': True,
    'duration': 0.24,                # s of gathering before the bolt leaves
    'motes': 16,
    'mote_size': (0.32, 0.55),       # H
    'mote_spread': 0.32,             # H, how far above / below the centre line a mote starts
    'mote_delay': 0.45,              # the latest a mote sets off, share of the charge
    'white_mix': 0.6,                # whiter than the bar under them, so they stand out
    'intensity': 1.0,
    'sweep': 0.55,                   # brightness of the band sweeping the bar to its front
    'seam': 0.8,                     # how much the front's seam brightens by the end
    'orb': (0.3, 1.5),               # H, the light swelling at the front: from / to
    'orb_intensity': 0.9,
}

# The flash at the front (the spear tip without a charge) as the bolt leaves
MUZZLE_STYLE = {
    'size': 2.0,                     # H
    'duration': 0.13,
    'intensity': 0.9,
    'white_mix': 0.45,
}

IMPACT_STYLE = {
    # A flare that grows and fades, and sparks sprayed back out of the bar
    'flare': {
        'size': (0.8, 2.9),          # H, from / to
        'grow': 0.05,
        'duration': 0.34,
        'intensity': 0.95,
        'white_mix': 0.2,            # keeps the shooter's colour; the core still burns white
    },
    'sparks': {
        'count': 10,
        'cone': 80.0,                # degrees either side of straight back at the shooter
        'distance': (0.8, 2.3),      # H
        'life': (0.26, 0.45),
        'size': (0.24, 0.4),         # H
        'white_mix': 0.55,
        'intensity': 1.0,
    },
    # A soft shock ring
    'ring': {
        'radius': (0.4, 1.6),        # H
        'duration': 0.32,
        'intensity': 0.5,
        'white_mix': 0.1,
    },
}

# The chunk a shot destroys breaks off glowing hot and falls out of the bar,
# fading (owner, 2026-10-28), with embers of its own colour bursting from it
BURN_STYLE = {
    'cool': 0.22,                    # s after the hit before the chunk is gone (the fill steps down)
    'white_mix': 0.4,                # the piece glows in the bar's own colour, white only at the hottest
    'heat': 0.85,                    # how hot the piece glows as it breaks off...
    'heat_decay': 0.12,              # ...cooling this fast (s)
    'fall': {
        'duration': 0.5,             # s until the piece is gone
        'pop': 0.5,                  # H per second, up as it breaks off
        'gravity': 14.0,             # H per second squared
        'push': 0.5,                 # H per second, the way the bolt was flying
        'spin': 50.0,                # degrees per second it topples that way
    },
    'embers': {
        'count': 14,
        'life': (0.5, 0.85),
        'speed': (1.4, 3.2),         # H per second, up and out of the bar
        'up': (40.0, 140.0),         # launch angle range, degrees from straight inward (90 = straight up)
        'gravity': 7.0,              # H per second squared
        'size': (0.18, 0.32),        # H
        'white_mix': 0.3,
        'intensity': 0.95,
    },
}


def charge_time():
    """Seconds a shot gathers light before its bolt leaves (0 with the charge off)."""
    return CHARGE_STYLE['duration'] if CHARGE_STYLE['enabled'] else 0.0

# ========================================
# THE FINALE (after the last bolt lands)
# ========================================
FINALE_STYLE = {
    # The bar left standing
    'sweep': 0.5,                    # s for a bright sheen to cross its fill
    'sweep_intensity': 0.85,
    'seam': 0.85,                    # its seam's brightness while it holds
    'frame_colour': GUIDE_GOLD,
    'frame_reach': 14,               # px at 1600x900, how far the gold light reaches round the frame
    'frame_fade_in': 0.2,
    'frame_intensity': 0.9,
    'frame_breathe': 0.1,            # +- brightness
    'frame_breathe_hz': 1.2,
    # The bar left empty: its seam goes out in a last shower of embers
    'out': 0.35,                     # s
    'embers': 12,
}

# ========================================
# THE BATTLE ICON (crossed swords between the panels)
# ========================================
ICON_GLOW_STYLE = {
    'colour': GUIDE_GOLD,
    'reach': 12,                     # px at 1600x900, light round the swords' outline
    'outline': (0.45, 0.75),         # brightness at the small / big end of the icon's pulse
    'bloom': 0.62,                   # a soft light behind the swords: diameter, share of the icon's height
    'bloom_level': (0.2, 0.32),
    'bloom_white_mix': 0.25,
    'shot_kick': 0.35,               # extra brightness as each bolt leaves...
    'shot_decay': 0.16,              # ...fading this fast (s)
}

# ========================================
# THE BACKDROP (over the map, every state of the battle screen)
# ========================================
BACKDROP_STYLE = {
    'centre_alpha': 165,             # the old flat overlay was 180 everywhere
    'edge_alpha': 232,
    'inner': 0.25,                   # where the darkening starts rising / reaches the edge alpha,
    'outer': 1.3,                    # share of the half-size (light_fx.vignette_surface)
}
