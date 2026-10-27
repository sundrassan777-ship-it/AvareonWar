# -*- coding: utf-8 -*-
"""
Map Marker Effects (light)

The map's event markers drawn as light, in the style of the order effects
(event FX pass, 2026-10): a battle to resolve, allies arriving at the same
territory together, and the army overflow warning. They replace the particle
hurricanes (600-1000 one-pixel dots a marker) of the old battleeffect.py and
alliance_marker_effect.py.

Pieces:
    MarkerState   what a marker keeps between frames (MapRenderer.battle_effects /
                  alliance_effects): whether it is greyed, its animation phase and
                  when it first showed
    MarkerLight   the shared renderer (one per MapRenderer): sprite caches, ring
                  frames and the scaled icons. draw_marker(), draw_overflow()

Cost rules (as the order effects, see docs/PERFORMANCE_ROADMAP.md):
- each layer of a marker is one blit or one Surface.blits() call
- positions come from the shared plot effect clock: nothing is stored per mote
- brightness is quantized and baked into cached sprites and ring frames
- new sprites and ring frames per frame are capped (build budgets): no hitch
- a marker off screen is skipped before any per-mote work

Styles: marker_fx_style.py. Preview / tune / measure: tools/event_fx_preview.py.
"""

import math
import random
from collections import OrderedDict

import pygame

from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, TintSprites, SoftRing
from ui.effects.marker_fx_style import MARKER_FX_STYLE
from utils.surface_utils import load_cached_image, crop_to_opaque

ADD = pygame.BLEND_RGB_ADD
_TWO_PI = 2.0 * math.pi

# Icons are cut to their opaque part and shrunk to this long side once; every
# zoom's icon is scaled from that (a fraction of a millisecond, not the 1024x1536 art)
ICON_BASE_SIZE = 192


def _even(value):
    return max(2, int(value) & ~1)


class MarkerState:
    """
    What a marker keeps between frames.

    Args:
        greyed_out: not the viewing player's to click (ash grey, no pulses)
        phase: seconds added to the clock, so markers don't pulse in step
        born: the clock when the marker first showed (it fades in from there)
    """

    __slots__ = ('greyed_out', 'phase', 'born')

    def __init__(self, greyed_out, phase=0.0, born=0.0):
        self.greyed_out = greyed_out
        self.phase = phase
        self.born = born


class _Scheme:
    """One colour scheme's colours and ring caches (each pulse is a cached frame per
    radius, so the schemes get their own rings rather than evict each other's)."""

    __slots__ = ('raw', 'light', 'spark', 'ring', 'pulse')

    def __init__(self, spec, ring_width, pulse_width, spark_mix, warm):
        self.raw = tuple(spec['colour'])
        self.light = light_fx.light_colour(self.raw, spec['white_mix'], warm)
        self.spark = light_fx.light_colour(self.raw, spark_mix, warm)
        self.ring = SoftRing(ring_width)
        self.pulse = SoftRing(pulse_width)


class MarkerLight:
    """
    The shared map marker renderer (one per MapRenderer, rebuilt with the display
    format like the other light renderers).

    Args:
        style: marker_fx_style.MARKER_FX_STYLE
    """

    MAX_ICONS = 48        # scaled icons kept (LRU): two kinds, grey or not, per plot radius
    MAX_MOTE_SETS = 32    # per-radius mote sprite sets kept (LRU)

    def __init__(self, style=MARKER_FX_STYLE):
        self.style = style
        self.glow = GlowSprites()
        self.tint = TintSprites()
        warm = style['warm_white']
        marker = style['marker']
        ring_width = marker['ring']['width']
        pulse_width = marker['pulses']['width']
        spark_mix = marker['motes']['white_mix']
        self._schemes = {kind: _Scheme(spec, ring_width, pulse_width, spark_mix, warm)
                         for kind, spec in style['kinds'].items()}
        self._schemes['greyed'] = _Scheme(style['greyed'], ring_width, pulse_width, spark_mix, warm)
        overflow = style['overflow']
        self._overflow = _Scheme(overflow, overflow['width'], overflow['pulses']['width'],
                                 overflow['white_mix'], warm)
        self._tables = {kind: self._mote_table(kind, spec['arms']) for kind, spec in style['kinds'].items()}
        self._bases = {}                   # kind -> icon cut and shrunk to ICON_BASE_SIZE
        self._icons = OrderedDict()        # (kind, greyed, radius) -> icon
        self._mote_sets = OrderedDict()    # (kind, scheme, radius) -> sprites per mote

    def _all_schemes(self):
        return list(self._schemes.values()) + [self._overflow]

    # ---------- frame ----------

    def begin_frame(self):
        """Once per rendered frame, before any marker is drawn: resets the build budgets."""
        self.glow.begin_frame()
        self.tint.begin_frame()
        for scheme in self._all_schemes():
            scheme.ring.begin_frame()
            scheme.pulse.begin_frame()

    def prewarm(self, radii):
        """
        Build what the first frames would otherwise pay for (at load): the ring
        bases, the icon bases and the motes' unshifted sprites at every plot
        radius (their sub-pixel copies follow within the frame budget).
        """
        for scheme in self._all_schemes():
            scheme.ring.prewarm()
            scheme.pulse.prewarm()
        for kind in self.style['kinds']:
            self._icon_base(kind)
        radii = sorted(set(radii))
        if not radii:
            return
        lo, hi = self.style['marker']['motes']['size']
        diameters = range(_even(lo * radii[0]), _even(hi * radii[-1]) + 1, 2)
        for scheme in self._schemes.values():
            self.glow.prewarm(diameters, scheme.spark)

    # ---------- markers ----------

    def reach(self, radius):
        """How far a marker's light reaches from its centre at this plot radius (px)."""
        marker = self.style['marker']
        ring = marker['ring']['radius'] * marker['pulses']['reach'] * (1.0 + 3 * marker['pulses']['width'])
        return int(max(marker['motes']['outer'], ring, marker['halo']['size'] / 2.0) * radius) + 4

    def click_radius(self, radius):
        """The radius (px) of a marker's click area at this plot radius."""
        return int(self.style['marker']['click'] * radius)

    def icon_half_height(self, kind, radius):
        """Half the height of a kind's icon at this plot radius (px), for the label below it."""
        base = self._icon_base(kind)
        if base is None:
            return int(radius)
        w, h = base.get_size()
        return int(self.style['kinds'][kind]['icon_size'] * radius * h / float(max(w, h))) // 2

    def draw_marker(self, view, x, y, kind, greyed, clock, phase=0.0, appear=1.0):
        """
        A marker of this kind ('battle' / 'alliance') centred on screen point (x, y):
        the colour halo, the pulses and the breathing ring, the motes spiralling
        in, and the icon on top. Greyed: ash grey, dimmer, no pulses.

        Args:
            clock: the shared plot effect clock, seconds
            phase: seconds added to the clock (MarkerState.phase)
            appear: 0-1, the fade-in as the marker first shows
        """
        marker = self.style['marker']
        radius = view.radius
        if not view.visible(x, y, self.reach(radius)):
            return
        screen = view.screen
        x, y = int(x), int(y)
        greyed_style = self.style['greyed']
        scheme = self._schemes['greyed' if greyed else kind]
        light = appear * (greyed_style['brightness'] if greyed else 1.0)
        tint = appear * (greyed_style['tint'] if greyed else 1.0)
        t = clock + phase

        halo = marker['halo']
        diameter = _even(halo['size'] * radius)
        sprite = self.tint.sprite(diameter, scheme.raw, halo['alpha'] * tint, halo['softness'])
        if sprite is not None:
            screen.blit(sprite, (x - (diameter >> 1), y - (diameter >> 1)))

        ring = marker['ring']
        r = ring['radius'] * radius
        if not greyed:
            self._pulses(screen, scheme, x, y, r, marker['pulses'], t, appear)
        breath = 0.5 + 0.5 * math.sin(_TWO_PI * ring['breath'] * t)
        brightness = ring['intensity'] * (1.0 - ring['breath_depth'] * (1.0 - breath)) * light
        self._ring(screen, scheme.ring, x, y, int(r), scheme, ring['tint'] * tint, brightness)

        self._draw_motes(view, x, y, kind, scheme, t, light, tint)

        icon = self._icon(kind, greyed, radius)
        if icon is not None:
            alpha = greyed_style['icon_alpha'] if greyed else 255
            icon.set_alpha(int(alpha * appear))
            screen.blit(icon, (x - icon.get_width() // 2, y - icon.get_height() // 2))

    def draw_overflow(self, view, x, y, target_radius, clock):
        """The amber warning round an army circle of target_radius px centred on
        (x, y): a ring breathing fast, pulses running outward."""
        style = self.style['overflow']
        r = target_radius + style['gap'] * view.radius
        pulses = style['pulses']
        if not view.visible(x, y, r * pulses['reach'] * (1.0 + 3 * pulses['width']) + 4):
            return
        screen = view.screen
        x, y = int(x), int(y)
        scheme = self._overflow
        self._pulses(screen, scheme, x, y, r, pulses, clock, 1.0)
        breath = 0.5 + 0.5 * math.sin(_TWO_PI * style['breath'] * clock)
        brightness = style['intensity'] * (1.0 - style['breath_depth'] * (1.0 - breath))
        self._ring(screen, scheme.ring, x, y, int(r), scheme, style['tint'], brightness)

    # ---------- pieces ----------

    @staticmethod
    def _ring(screen, ring, x, y, r, scheme, tint_alpha, brightness):
        """A ring of radius r: its colour band (normal blend), then its light."""
        band = ring.tint_frame(r, scheme.raw, tint_alpha)
        if band is not None:
            half = band.get_width() >> 1
            screen.blit(band, (x - half, y - half))
        level = int(SoftRing.LEVELS * brightness + 0.5)
        if level > 0:
            frame = ring.frame(r, scheme.light, level)
            if frame is not None:
                half = frame.get_width() >> 1
                screen.blit(frame, (x - half, y - half), special_flags=ADD)

    def _pulses(self, screen, scheme, x, y, r, pulses, t, strength):
        """Soft rings leaving a ring of radius r and growing outward while they fade."""
        count = pulses['count']
        for k in range(count):
            u = (t / pulses['period'] + k / float(count)) % 1.0
            grow = 1.0 - (1.0 - u) ** 2
            pulse_r = int(r * (1.0 + (pulses['reach'] - 1.0) * grow))
            fade = min(1.0, u / 0.08) * (1.0 - u) ** 1.5 * strength
            self._ring(screen, scheme.pulse, x, y, pulse_r, scheme, pulses['tint'] * fade,
                       pulses['intensity'] * fade)

    def _mote_table(self, kind, arms):
        """
        Per mote: (1 / life, offset, start angle, size share) - fixed per kind. The
        motes are dealt round the arms in turn; each strays a little from its arm.
        """
        style = self.style['marker']['motes']
        rng = random.Random('marker-motes-' + kind)
        jitter = style['jitter']
        lo, hi = style['size']
        return [(1.0 / rng.uniform(*style['life']), rng.random(),
                 _TWO_PI * (j % arms) / arms + rng.uniform(-jitter, jitter), rng.uniform(lo, hi))
                for j in range(style['count'])]

    def _mote_sprites(self, kind, scheme, radius):
        """
        Per mote of the kind's table at this plot radius: (core ladders by sub-pixel
        phase, core half size, halo ladder, halo half size). Cached once complete;
        None while the unshifted cores or the halos are still being built within the
        frame budget (until a shifted copy exists its phase uses the unshifted ladder).
        """
        key = (kind, id(scheme), radius)
        prepared = self._mote_sets.get(key)
        if prepared is not None:
            self._mote_sets.move_to_end(key)
            return prepared
        style = self.style['marker']['motes']
        prepared = []
        complete = True
        cores = {}
        halos = {}
        for _, _, _, size in self._tables[kind]:
            diameter = _even(size * radius)
            phases = cores.get(diameter)
            if phases is None:
                unshifted = self.glow.ladder(diameter, scheme.spark)
                if unshifted is None:
                    return None
                phases = [unshifted]
                for phase in range(1, GlowSprites.SUBPIXEL_PHASES):
                    shifted = self.glow.ladder(diameter, scheme.spark, 'mote', phase)
                    if shifted is None:
                        complete = False
                        shifted = unshifted
                    phases.append(shifted)
                cores[diameter] = phases
            # Halo sizes in steps of 4 px: fewer sprites to build
            halo_d = max(4, int(size * radius * style['tint_size']) & ~3)
            halo = halos.get(halo_d)
            if halo is None:
                halo = self.tint.alpha_ladder(halo_d, scheme.raw, style['tint'])
                if halo is None:
                    return None
                halos[halo_d] = halo
            prepared.append((phases, diameter >> 1, halo, halo_d >> 1))
        if complete:
            self._mote_sets[key] = prepared
            if len(self._mote_sets) > self.MAX_MOTE_SETS:
                self._mote_sets.popitem(last=False)
        return prepared

    def _draw_motes(self, view, x, y, kind, scheme, t, light, tint):
        """
        Motes of light on the kind's spiral arms: each appears at the outer edge,
        is drawn in toward the icon along its arm while the arms turn, and goes out
        near the centre. Closed form from the clock, as the hero fireflies.
        """
        style = self.style['marker']['motes']
        radius = view.radius
        sprites = self._mote_sprites(kind, scheme, radius)
        if sprites is None:
            return
        outer = style['outer'] * radius
        span = outer - style['inner'] * radius
        spiral = style['spiral']
        spin = _TWO_PI * style['spin'] * t
        steps = GlowSprites.LEVELS
        core_scale = steps * style['intensity'] * light
        halo_top = TintSprites.LEVELS
        halo_scale = halo_top * tint
        sin, cos, pi = math.sin, math.cos, math.pi
        halos = []
        seq = []
        for (inv_life, offset, angle, _), (phases, core_half, halo, halo_half) in zip(self._tables[kind], sprites):
            u = (t * inv_life + offset) % 1.0
            env = sin(pi * u)
            env *= env
            level = int(core_scale * env + 0.5)
            if level <= 0:
                continue
            # Faster as it nears the centre, like water down a drain
            r = outer - span * u * u
            a = angle + spin + spiral * u
            # Sub-pixel placement (as HeroLight.draw_motes): half pixels across,
            # quarter pixels down, offset by 4096 to stay positive
            xq = int((x + cos(a) * r + 4096.0) * 2.0 + 0.5)
            yq = int((y + sin(a) * r + 4096.0) * 4.0 + 0.5)
            px = (xq >> 1) - 4096
            py = (yq >> 2) - 4096
            halo_level = int(halo_scale * env + 0.5)
            if halo_level > 0:
                halos.append((halo[halo_level if halo_level < halo_top else halo_top],
                              (px - halo_half, py - halo_half)))
            seq.append((phases[(yq & 3) + ((xq & 1) << 2)][level if level < steps else steps],
                        (px - core_half, py - core_half), None, ADD))
        if halos:
            view.screen.blits(halos, doreturn=False)
        if seq:
            view.screen.blits(seq, doreturn=False)

    # ---------- icons ----------

    def _icon_base(self, kind):
        """The kind's icon cut to its opaque part and shrunk to ICON_BASE_SIZE (once)."""
        if kind in self._bases:
            return self._bases[kind]
        base = None
        image = load_cached_image(self.style['kinds'][kind]['icon'])
        if image is not None:
            image = crop_to_opaque(image, 40)
            w, h = image.get_size()
            scale = ICON_BASE_SIZE / float(max(w, h))
            base = pygame.transform.smoothscale(image, (max(1, int(w * scale)), max(1, int(h * scale))))
        self._bases[kind] = base
        return base

    def _icon(self, kind, greyed, radius):
        """The kind's icon at this plot radius (grey when greyed), cached."""
        key = (kind, greyed, radius)
        icon = self._icons.get(key)
        if icon is not None:
            self._icons.move_to_end(key)
            return icon
        base = self._icon_base(kind)
        if base is None:
            return None
        w, h = base.get_size()
        scale = self.style['kinds'][kind]['icon_size'] * radius / float(max(w, h))
        icon = pygame.transform.smoothscale(base, (max(1, int(w * scale)), max(1, int(h * scale))))
        if greyed and self.style['greyed'].get('icon_grey') and hasattr(pygame.transform, 'grayscale'):
            icon = pygame.transform.grayscale(icon)
        self._icons[key] = icon
        if len(self._icons) > self.MAX_ICONS:
            self._icons.popitem(last=False)
        return icon
