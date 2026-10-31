# -*- coding: utf-8 -*-
"""
Banner Effect Styles

The look of the army banners' own effects, in one place (banner FX pass,
2026-10-31):
- 'wave'   the cloth of every banner on the map swaying in a steady breeze
           (BannerWave, banner_fx_effect.py): the crossbar and the pole stay
           still, the cloth below the crossbar sways more the further down it is,
           with a ripple always running down to the tails
- 'wind'   one breeze over the whole map: the banners lean the same way and
           neighbours ripple almost in step, a little behind or ahead, as the
           breeze crosses the map (a marching banner's pose follows its world
           position, so it carries on from its territory to the next)
- 'motes'  motes of light in the selection green rising from the selected
           banner's pole base to its top (BannerMotes)

The breeze is CONSTANT (owner, 2026-10-31): always moving, never still, no gusts
and no "wave once per period" - one even ripple at one strength, everywhere.

Styles are keyed by map look ('2d' / '3d', map_data.get_current_look()). Both
looks share one style today (the banners are the same pictures over either map).

UNITS: the wave's sway in BANNER WIDTHS, the motes' sizes and distances in
BANNER HEIGHTS (the banner is 50..75 px tall, by zoom), so both match the banner
at every zoom; times in seconds; the wind's wavelength in world px.
"""

from ui.effects.order_fx_style import SELECTION, WARM_WHITE

# ========================================
# WAVE (the cloth)
# ========================================
WAVE = {
    'frames': 32,          # poses in the loop (each tail step <= ~0.4 px: smooth)
    'period': 3.6,         # seconds per ripple: a slow breeze
    'amplitude': 0.055,    # sideways sway at the tails, banner widths
    'ripples': 0.8,        # ripples on the cloth at once, crossbar to tails
    # A second, quicker ripple under the first (share of its amplitude), so the
    # sway doesn't look like a pendulum. Twice the frequency: the loop stays seamless
    'flutter': 0.25,
    'flutter_ripples': 1.6,
    'lean': 0.03,          # steady lean downwind at the tails, banner widths
    'stiffness': 1.5,      # sway grows as (share of the way down the cloth) ** this
    'shade': 0.09,         # fold light: a row up to this much lighter or darker by its slope
}

# ========================================
# WIND (one breeze over the map)
# ========================================
WIND = {
    'direction': (1.0, 0.3),   # where the breeze blows to, in world space (east, a little south)
    # World px between banners in the same pose (~ the map's width): neighbours
    # ~20 degrees apart. Long, so a marching banner (its pose follows its world
    # position) keeps its own pace: crossing to a neighbour in 0.5 s it drifts
    # ~1.5 poses ahead or behind; at 700 px one marching with the breeze all but
    # stopped rippling
    'wavelength': 1500.0,
}

# ========================================
# SELECTED-BANNER MOTES
# ========================================
MOTES = {
    'colour': SELECTION['colour'],          # the selection ring's green
    'white_mix': SELECTION['white_mix'],
    'count': 10,
    'life': (1.5, 2.1),        # seconds from the pole base to the top
    'rise': 0.95,              # banner heights travelled over a life
    # Across: a fan from the pole base - within fan * spread of the pole at the
    # start, all of spread (banner heights; the banner is ~0.66 wide) by the top,
    # so some motes climb beside the cloth, over the map
    'spread': 0.62,
    'fan': 0.3,
    'start': 0.10,             # spawn up to this far above the pole base, banner heights
    'sway': 0.035,             # sideways drift, banner heights
    'size': (0.10, 0.15),      # light core diameter, banner heights (5-11 px)
    'intensity': 1.0,
    'fade_in': 0.15,           # share of a life spent lighting up at the base
    'fade_out': 0.4,           # share of a life spent fading out near the top
    # The green halo under each mote (normal blend): its hue on the bright map and
    # on the cloth's white, where the light alone washes out
    'tint': 150,               # alpha
    'tint_size': 2.4,          # halo / core diameter
    'appear': 0.15,            # seconds to full strength after a banner is selected
}

BANNER_FX_STYLE = {
    'wave': WAVE,
    'wind': WIND,
    'motes': MOTES,
    'warm_white': WARM_WHITE,
}

BANNER_FX_STYLES = {
    '2d': BANNER_FX_STYLE,
    '3d': BANNER_FX_STYLE,
}


def get_banner_fx_style(look):
    """The banner effect style for a map look ('2d' / '3d'); unknown looks use 2D."""
    return BANNER_FX_STYLES.get(look, BANNER_FX_STYLES['2d'])
