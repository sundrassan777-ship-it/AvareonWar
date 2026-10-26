# -*- coding: utf-8 -*-
"""
Hero Ability Effects (light)

Every hero ability shown as light, in the style of the production rays: soft
additive light on opaque black frames, one shared set of caches, positions
computed from time rather than stored per particle (hero ability FX pass, 2026-10).

Pieces:
    FxView             one frame's projection (world -> screen) and plot radius
    HeroLight          the shared renderer (one per MapRenderer): sprite caches,
                       a ray burst renderer, the soft ring, territory outlines
                       and firefly spawn points. Every effect draws through it.
    HeroAbilityEffect  one cast: a timeline of cues (hero_fx_style 'abilities')
                       at resolved anchors. update(dt) / is_finished(), drawn in
                       two layers: render_under() before the plots (rays, border
                       light, fireflies), render_over() after the armies (flares,
                       rings, sparks)
    HeroAura           a passive aura shown while its hero is selected: light
                       along the outline of the covered territories with a
                       shimmer running round it, and fireflies. Stateless: drawn
                       from the shared plot effect clock

Cost rules (see docs/PERFORMANCE_ROADMAP.md):
- no full-screen surfaces; each layer is one Surface.blits() call
- brightness is quantized and baked into cached sprites (no set_alpha)
- new sprites per frame are capped (GlowSprites.BUILDS_PER_FRAME): no hitch
- effects cull themselves by screen bounds before any per-dot work
- territory outlines and spawn points are built once per territory set and kept

Styles: hero_fx_style.py. Preview / tune / measure: tools/hero_fx_preview.py.
"""

import math
import random
import zlib
from collections import OrderedDict

import pygame

from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, TintSprites, SoftRing, TerritoryRaster, bead_chain
from ui.effects.production_glow_effect import ProductionRays
from ui.effects.hero_fx_style import HERO_FX_STYLE

ADD = pygame.BLEND_RGB_ADD
MULT = pygame.BLEND_RGB_MULT
_TWO_PI = 2.0 * math.pi


def _even(value):
    return max(2, int(value) & ~1)


def _smooth(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def envelope(t, duration, fade_in, fade_out):
    """Brightness 0-1 at time t of a cue: eases in, holds, eases out."""
    if t < 0.0 or t >= duration:
        return 0.0
    if fade_in > 0.0 and t < fade_in:
        return _smooth(t / fade_in)
    if fade_out > 0.0 and t > duration - fade_out:
        return _smooth((duration - t) / fade_out)
    return 1.0


def stable_seed(*parts):
    """A seed from strings/numbers that is the same every run (not hash())."""
    return zlib.crc32('|'.join(str(p) for p in parts).encode('utf-8')) & 0xFFFFFFFF


class FxView:
    """
    Where and how big to draw this frame.

    Screen position of a world point: (ax + x * zoom, ay + y * zoom) - the
    camera's world_to_screen() as an affine map, so loops over many points need
    no function call each. radius is the plot radius in px.
    """

    __slots__ = ('screen', 'ax', 'ay', 'zoom', 'radius', 'width', 'height')

    def __init__(self, screen, ax, ay, zoom, radius):
        self.screen = screen
        self.ax = ax
        self.ay = ay
        self.zoom = zoom
        self.radius = radius
        self.width, self.height = screen.get_size()

    @classmethod
    def from_world_to_screen(cls, screen, world_to_screen, zoom, radius):
        ax, ay = world_to_screen((0.0, 0.0))
        return cls(screen, ax, ay, zoom, radius)

    def to_screen(self, point):
        return self.ax + point[0] * self.zoom, self.ay + point[1] * self.zoom

    def visible(self, x, y, reach):
        return -reach < x < self.width + reach and -reach < y < self.height + reach


class Outline:
    """
    The border beads of a set of territories (HeroLight.outline()):
    parts = [(territory, world bbox, [(x, y, outward nx, ny, shimmer phase,
    sweep phase), ...]), ...]. serial identifies it in position caches.
    """

    __slots__ = ('serial', 'parts')

    def __init__(self, serial, parts):
        self.serial = serial
        self.parts = parts

    def __bool__(self):
        return any(beads for _, _, beads in self.parts)


# ========================================
# SHARED RENDERER
# ========================================

class HeroLight:
    """
    The shared hero effect renderer (one per MapRenderer, rebuilt with the display
    format like the production rays).

    Args:
        polygons: {territory: [(x, y), ...]} world coordinates (game.scaled_polygons)
        style: hero_fx_style.HERO_FX_STYLE
    """

    MAX_OUTLINES = 12   # territory sets whose outline is kept (LRU)

    def __init__(self, polygons, style=HERO_FX_STYLE):
        self.style = style
        self.kit = style['kit']
        self.warm_white = style['warm_white']
        self.glow = GlowSprites()
        self.tint = TintSprites()
        self.ring = SoftRing(self.kit['ring_width'])
        self.rays = ProductionRays(style['rays'])
        self.polygons = polygons
        self._raster = None
        self._fine = {}                  # territory -> bead_chain at fine spacing
        self._bboxes = {}                # territory -> world bbox
        self._outlines = OrderedDict()   # frozenset(territories) -> outline
        self._spawns = {}                # (territory, rise) -> [(x, y), ...]
        self._areas = {}                 # territory -> area, world px^2
        self._scratch = {}               # (w, h) -> black surface for fading ray frames
        self._wave_tables = OrderedDict()
        self._positions = OrderedDict()  # bead screen positions per (outline, camera, size)
        self._serial = 0
        self._nothing = light_fx.new_black_surface(2)   # adds nothing: stands in for level 0

    # ---------- frame ----------

    def begin_frame(self):
        """Once per rendered frame: resets the sprite build budgets."""
        self.glow.begin_frame()
        self.tint.begin_frame()

    def prewarm(self, radii):
        """
        Build what the first frames would otherwise pay for (at load): the ray
        bases for every plot radius, the ring, the territory raster, and the aura
        sprites at every size the zoom range gives.
        """
        self.rays.prewarm(radii)
        self.ring.prewarm()
        self.raster()
        for aura in self.style['auras'].values():
            colour = self.light_colour(aura['colour'], aura['white_mix'])
            rim = aura['rim']
            for radius in sorted(set(radii)):
                self.glow.prewarm([_even(rim['size'] * radius)], colour, profile='bead')
                tint = rim.get('tint')
                if tint and tint.get('alpha', 0) > 0:
                    self.tint.prewarm([_even(tint['size'] * radius)], tuple(aura['colour']),
                                      [tint['alpha']], tint.get('softness', 1.5))
            motes = aura['motes']
            lo, hi = motes['size']
            mote_colour = self.light_colour(aura['colour'], motes.get('white_mix', aura['white_mix']))
            self.glow.prewarm(range(_even(lo * min(radii)), _even(hi * max(radii)) + 1, 2), mote_colour)

    def light_colour(self, colour, white_mix):
        return light_fx.light_colour(colour, white_mix, self.warm_white)

    # ---------- territories ----------

    def raster(self):
        if self._raster is None:
            self._raster = TerritoryRaster(self.polygons)
        return self._raster

    def bbox(self, territory):
        box = self._bboxes.get(territory)
        if box is None:
            polygon = self.polygons.get(territory) or [(0, 0)]
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            box = self._bboxes[territory] = (min(xs), min(ys), max(xs), max(ys))
        return box

    def _fine_chain(self, territory):
        chain = self._fine.get(territory)
        if chain is None:
            chain = self._fine[territory] = bead_chain(
                self.polygons.get(territory) or [], self.kit['fine_spacing'])
        return chain

    def outline(self, territories):
        """
        The border beads of a set of territories, with the borders two of them
        share dropped (one outline around the whole set), cached per set.
        Phases are 0-255: shimmer repeats every kit['wave_length'] world px,
        sweep goes once round each territory.
        """
        key = frozenset(t for t in territories if self.polygons.get(t))
        outline = self._outlines.get(key)
        if outline is not None:
            self._outlines.move_to_end(key)
            return outline
        raster = self.raster()
        probe = self.kit['probe']
        wave_units = 256.0 / self.kit['wave_length']
        parts = []
        for territory in sorted(key):
            chain = self._fine_chain(territory)
            if not chain:
                continue
            perimeter = chain[-1][2] + self.kit['fine_spacing']
            sweep_units = 256.0 / perimeter
            beads = []
            for x, y, s, nx, ny in chain:
                neighbour = raster.at(x + nx * probe, y + ny * probe)
                if neighbour is not None and neighbour != territory and neighbour in key:
                    continue   # a border shared with another lit territory
                beads.append((x, y, nx, ny, int(s * wave_units) & 255, int(s * sweep_units) & 255))
            parts.append((territory, self.bbox(territory), beads))
        self._serial += 1
        outline = Outline(self._serial, parts)
        self._outlines[key] = outline
        if len(self._outlines) > self.MAX_OUTLINES:
            self._outlines.popitem(last=False)
        return outline

    def bead_positions(self, view, outline, diameter, spacing, inset):
        """
        Screen positions (top-left of a `diameter` sprite) of every `spacing`-th
        bead diameter along the outline, moved `inset` diameters inside, with
        each bead's phases: [(pos, shimmer phase, sweep phase), ...]. Cached
        until the camera moves, so a still frame only picks sprites.
        """
        z = view.zoom
        step = max(1, int(round(spacing * diameter / (self.kit['fine_spacing'] * z))))
        key = (outline.serial, view.ax, view.ay, z, diameter, step, inset)
        positions = self._positions.get(key)
        if positions is not None:
            return positions
        half = diameter >> 1
        k = inset * diameter / z                 # inset in world px
        ax, ay = view.ax - half, view.ay - half
        w, h = view.width, view.height
        positions = []
        append = positions.append
        for territory, (bx0, by0, bx1, by1), beads in outline.parts:
            if (ax + bx1 * z < -diameter or ax + bx0 * z > w
                    or ay + by1 * z < -diameter or ay + by0 * z > h):
                continue
            for x, y, nx, ny, p, q in beads[::step]:
                append(((int(ax + (x - nx * k) * z), int(ay + (y - ny * k) * z)), p, q))
        self._positions[key] = positions
        if len(self._positions) > 24:
            self._positions.popitem(last=False)
        return positions

    def spawn_points(self, territory, rise):
        """
        Up to kit['spawn_points'] points inside the territory that stay inside
        while a firefly rises `rise` world px (picked once, deterministic).
        """
        key = (territory, rise)
        points = self._spawns.get(key)
        if points is None:
            raster = self.raster()
            x0, y0, x1, y1 = self.bbox(territory)
            rng = random.Random(stable_seed('spawn', territory))
            points = []
            margin = 2.0
            for _ in range(600):
                if len(points) >= self.kit['spawn_points']:
                    break
                x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
                if (raster.at(x, y) == territory and raster.at(x, y - rise) == territory
                        and raster.at(x - margin, y - rise * 0.5) == territory
                        and raster.at(x + margin, y - rise * 0.5) == territory):
                    points.append((x, y))
            if not points:
                points = [((x0 + x1) / 2.0, (y0 + y1) / 2.0)]
            self._spawns[key] = points
        return points

    def points_inside(self, territory, count, seed):
        """count points spread over the territory (for 'each' cues), deterministic per seed."""
        raster = self.raster()
        x0, y0, x1, y1 = self.bbox(territory)
        rng = random.Random(seed)
        candidates = []
        for _ in range(400):
            if len(candidates) >= count * 6:
                break
            x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            if raster.at(x, y) == territory:
                candidates.append((x, y))
        if not candidates:
            return [((x0 + x1) / 2.0, (y0 + y1) / 2.0)] * max(1, count)
        # Farthest-point picks: spread out, not clumped
        points = [candidates[0]]
        while len(points) < min(count, len(candidates)):
            best = max(candidates, key=lambda c: min((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2
                                                     for p in points))
            points.append(best)
        rng.shuffle(points)
        return points

    # ---------- drawing ----------

    def draw_rays(self, view, x, y, colour, clock, phase, brightness):
        """A ray burst centred on (x, y) px, at brightness 0-1."""
        if brightness <= 0.02:
            return
        screen = view.screen
        v = int(255 * brightness)
        for surface, half in self.rays.layer_frames(view.radius, colour, clock, phase):
            if v < 250:
                size = surface.get_size()
                scratch = self._scratch.get(size)
                if scratch is None:
                    scratch = self._scratch[size] = light_fx.new_black_surface(size)
                scratch.blit(surface, (0, 0))
                scratch.fill((v, v, v), special_flags=MULT)
                surface = scratch
            screen.blit(surface, (x - half, y - half), special_flags=ADD)

    def wave_sprites(self, ladder, levels):
        """256 sprites for a 256-entry level table (level 0 = nothing)."""
        nothing = self._nothing
        return [ladder[level] if level > 0 else nothing for level in levels]

    def shimmer_levels(self, base, wave, brightness):
        """256 levels: base + wave * crest, a cosine crest every 256 phase units (cached)."""
        steps = GlowSprites.LEVELS
        key = (round(base, 3), round(wave, 3), int(brightness * 48))
        levels = self._wave_tables.get(key)
        if levels is None:
            b = int(brightness * 48) / 48.0
            levels = [int(steps * b * (base + wave * (0.5 + 0.5 * math.cos(_TWO_PI * i / 256.0))) + 0.5)
                      for i in range(256)]
            levels = [min(steps, level) for level in levels]
            self._wave_tables[key] = levels
            if len(self._wave_tables) > 256:
                self._wave_tables.popitem(last=False)
        return levels

    def draw_beads(self, view, outline, colour, rim, levels, shift, sweep=False):
        """
        Light along an outline (rim: size, spacing, inset - see hero_fx_style):
        each bead picks its brightness from the 256-entry levels table by its
        phase (shimmer phase, or sweep phase when sweep=True) minus shift.
        """
        diameter = _even(rim['size'] * view.radius)
        ladder = self.glow.ladder(diameter, colour, 'bead')
        if ladder is None:
            return   # sprites still being built (within the frame budget)
        sprites = self.wave_sprites(ladder, levels)
        positions = self.bead_positions(view, outline, diameter, rim['spacing'], rim.get('inset', 0.0))
        if sweep:
            seq = [(sprites[(q - shift) & 255], pos, None, ADD) for pos, p, q in positions]
        else:
            seq = [(sprites[(p - shift) & 255], pos, None, ADD) for pos, p, q in positions]
        if seq:
            view.screen.blits(seq, doreturn=False)

    def draw_bead_tint(self, view, outline, raw_colour, tint, strength):
        """
        The normal-blend colour band under an outline's light (tint: size,
        spacing, inset, alpha, softness): keeps the hue on the bright map.
        """
        alpha = tint['alpha'] * strength
        diameter = _even(tint['size'] * view.radius)
        sprite = self.tint.sprite(diameter, raw_colour, alpha, tint.get('softness', 1.5))
        if sprite is None:
            return
        positions = self.bead_positions(view, outline, diameter, tint['spacing'], tint.get('inset', 0.0))
        if positions:
            view.screen.blits([(sprite, pos) for pos, p, q in positions], doreturn=False)

    def draw_outline(self, view, outline, raw_colour, colour, rim, levels, shift, strength,
                     sweep=False):
        """Tint band (if the rim has one) then the light beads."""
        tint = rim.get('tint')
        if tint and tint.get('alpha', 0) > 0:
            self.draw_bead_tint(view, outline, raw_colour, tint, strength)
        self.draw_beads(view, outline, colour, rim, levels, shift, sweep)

    def area(self, territory):
        """A territory's area in world px^2 (shoelace), cached."""
        area = self._areas.get(territory)
        if area is None:
            polygon = self.polygons.get(territory) or []
            total = 0.0
            for i in range(len(polygon)):
                x1, y1 = polygon[i - 1]
                x2, y2 = polygon[i]
                total += x1 * y2 - x2 * y1
            area = self._areas[territory] = abs(total) / 2.0
        return area

    def mote_count(self, territory, style, available):
        """
        Fireflies in one territory: style['density'] per 1000 world px^2 (the
        same density in big and small territories), clamped to min..available.
        Without a density every firefly of the table is used.
        """
        density = style.get('density')
        if density is None:
            return available
        count = int(round(self.area(territory) * density / 1000.0))
        return max(min(style.get('min', 1), available), min(available, count))

    def draw_motes(self, view, territories, colour, motes, style, clock, brightness, raw_colour=None):
        """
        Fireflies rising inside each territory. motes: [(1 / life, offset,
        size share, sway phase, salt), ...] (see mote_table); style: rise,
        sway (world px), optional density / min (fireflies per territory, see
        mote_count) and tint / tint_size (a normal-blend halo of raw_colour
        under each firefly, so it keeps its hue on the bright map).
        Stateless: each firefly's spawn point changes every life by an
        integer hash.
        """
        if brightness <= 0.02:
            return
        rise = style['rise']
        sway = style['sway']
        tint_alpha = style.get('tint', 0) if raw_colour is not None else 0
        tint_size = style.get('tint_size', 2.0)
        radius = view.radius
        steps = GlowSprites.LEVELS
        z = view.zoom
        ax, ay = view.ax, view.ay
        w, h = view.width, view.height
        glow = self.glow
        tint = self.tint
        halos = []
        seq = []
        append = seq.append
        sin = math.sin
        pi = math.pi
        for territory in territories:
            bx0, by0, bx1, by1 = self.bbox(territory)
            if (ax + bx1 * z < -radius or ax + bx0 * z > w + radius
                    or ay + by1 * z < -radius or ay + by0 * z > h + radius):
                continue
            points = self.spawn_points(territory, rise)
            count = len(points)
            tsalt = stable_seed(territory) & 0xFFFF
            tphase = tsalt / 65536.0
            for inv_life, offset, size, sway_phase, salt in motes[:self.mote_count(territory, style, len(motes))]:
                u = clock * inv_life + offset + tphase
                cycle = int(u)
                age = u - cycle
                env = sin(pi * age)
                env *= env
                level = int(steps * brightness * env + 0.5)
                if level <= 0:
                    continue
                hsh = ((cycle * 73856093) ^ salt ^ tsalt) & 0xFFFFFFFF
                hsh = ((hsh ^ (hsh >> 13)) * 1274126177) & 0xFFFFFFFF
                px, py = points[(hsh >> 8) % count]
                x = ax + (px + sway * sin(age * 6.0 + sway_phase)) * z
                y = ay + (py - rise * age) * z
                if tint_alpha:
                    # Halo sizes in steps of 4 px: fewer sprites to build
                    halo_d = max(4, int(size * radius * tint_size) & ~3)
                    halo = tint.sprite(halo_d, raw_colour, tint_alpha * brightness * env)
                    if halo is not None:
                        half = halo_d >> 1
                        halos.append((halo, (int(x) - half, int(y) - half)))
                diameter = _even(size * radius)
                sprite = glow.sprite(diameter, colour, min(steps, level))
                if sprite is None:
                    continue
                half = diameter >> 1
                append((sprite, (int(x) - half, int(y) - half), None, ADD))
        if halos:
            view.screen.blits(halos, doreturn=False)
        if seq:
            view.screen.blits(seq, doreturn=False)


def mote_table(style, seed):
    """
    Per firefly: (1 / life, offset, size, sway phase, hash salt) - fixed per
    style. style['count'] fireflies (the most one territory shows).
    """
    rng = random.Random(seed)
    lo, hi = style['size']
    return [(1.0 / rng.uniform(*style['life']), rng.random(), rng.uniform(lo, hi),
             rng.uniform(0.0, _TWO_PI), (j * 19349663) & 0xFFFFFFFF)
            for j in range(style['count'])]


# ========================================
# CUES
# ========================================

class _Cue:
    """One timed piece of an ability effect. Subclasses draw in 'under' or 'over'."""

    layer = 'over'

    def __init__(self, spec, effect):
        self.at = spec.get('at', 0.0)
        self.duration = spec.get('duration', 1.0)
        self.fade_in = spec.get('fade_in', 0.05)
        self.fade_out = spec.get('fade_out', 0.3)
        self.intensity = spec.get('intensity', 1.0)
        raw = spec.get('colour', effect.colour)
        self.raw_colour = tuple(raw)
        self.colour = effect.light.light_colour(raw, spec.get('white_mix', effect.white_mix))

    @property
    def end(self):
        return self.at + self.duration

    def brightness(self, t):
        return self.intensity * envelope(t, self.duration, self.fade_in, self.fade_out)

    def render(self, light, view, t):   # pragma: no cover - interface
        raise NotImplementedError


class _RaysCue(_Cue):
    layer = 'under'

    def __init__(self, spec, effect, point):
        super().__init__(spec, effect)
        self.point = point
        self.spin = spec.get('spin', 1.0)
        self.phase = (effect.seed % 1000) / 1000.0

    def render(self, light, view, t):
        b = self.brightness(t)
        if b <= 0.02:
            return
        x, y = view.to_screen(self.point)
        reach = light.rays.reach(view.radius)
        if not view.visible(x, y, reach):
            return
        light.draw_rays(view, int(x), int(y), self.raw_colour, 10.0 + t * self.spin, self.phase, b)


def _ladder_size(px):
    """
    A diameter on a coarse geometric ladder (even px, ~12% apart): a growing
    flare reuses a dozen sprite sizes instead of building one per pixel.
    """
    if px <= 8:
        return 8
    step = int(round(math.log(px / 8.0) / math.log(1.12)))
    return _even(8.0 * 1.12 ** step)


class _FlareCue(_Cue):
    def __init__(self, spec, effect, point):
        super().__init__(spec, effect)
        self.point = point
        self.size = spec.get('size', (1.0, 3.0))
        self.grow = max(0.01, spec.get('grow', 0.1))
        self.tint = spec.get('tint', 0)
        self.tint_size = spec.get('tint_size', 1.3)

    def render(self, light, view, t):
        b = self.brightness(t)
        if b <= 0.02:
            return
        s0, s1 = self.size
        g = 1.0 - (1.0 - min(1.0, t / self.grow)) ** 2
        size = (s0 + (s1 - s0) * g) * view.radius
        diameter = _ladder_size(size)
        x, y = view.to_screen(self.point)
        if not view.visible(x, y, diameter * self.tint_size):
            return
        x, y = int(x), int(y)
        if self.tint:
            tint_diameter = _ladder_size(size * self.tint_size)
            halo = light.tint.sprite(tint_diameter, self.raw_colour, self.tint * b)
            if halo is not None:
                half = tint_diameter >> 1
                view.screen.blit(halo, (x - half, y - half))
        level = int(GlowSprites.LEVELS * b + 0.5)
        if level > 0:
            sprite = light.glow.sprite(diameter, self.colour, level, 'flare')
            if sprite is not None:
                half = diameter >> 1
                view.screen.blit(sprite, (x - half, y - half), special_flags=ADD)


class _RingCue(_Cue):
    def __init__(self, spec, effect, point):
        super().__init__(spec, effect)
        self.point = point
        self.radius = spec.get('radius', (0.5, 3.0))
        self.tint = spec.get('tint', 0)

    def render(self, light, view, t):
        b = self.brightness(t)
        if b <= 0.02:
            return
        r0, r1 = self.radius
        e = 1.0 - (1.0 - min(1.0, t / self.duration)) ** 3   # eased out
        radius = (r0 + (r1 - r0) * e) * view.radius
        x, y = view.to_screen(self.point)
        if not view.visible(x, y, light.ring.reach(radius)):
            return
        x, y = int(x), int(y)
        if self.tint:
            light.ring.draw_tint(view.screen, x, y, radius, self.raw_colour, self.tint * b)
        light.ring.draw(view.screen, x, y, radius, self.colour, b)


class _SparksCue(_Cue):
    """
    Sparks of light flung out ('explode'), drawn in ('implode') or popping up and
    falling back ('fountain'). Closed form: position = f(t), nothing stored per frame.
    """

    def __init__(self, spec, effect, point):
        super().__init__(spec, effect)
        self.point = point
        self.motion = spec.get('motion', 'explode')
        self.rise = spec.get('rise', 1.0)
        rng = random.Random(effect.seed ^ stable_seed('sparks', self.at, point))
        d0, d1 = spec.get('distance', (1.0, 3.0))
        s0, s1 = spec.get('size', (0.3, 0.6))
        l0, l1 = spec.get('life', (0.5, 1.0))
        spread = spec.get('spread', 0.0)
        swirl = spec.get('swirl', 0.0)
        # (angle, distance, size, delay, 1 / life, swirl)
        self.sparks = [(rng.uniform(0.0, _TWO_PI), rng.uniform(d0, d1), rng.uniform(s0, s1),
                        rng.uniform(0.0, spread), 1.0 / rng.uniform(l0, l1),
                        rng.uniform(-swirl, swirl))
                       for _ in range(spec.get('count', 20))]
        self.duration = spread + l1

    def brightness(self, t):
        return self.intensity if 0.0 <= t < self.duration else 0.0

    def render(self, light, view, t):
        if not 0.0 <= t < self.duration:
            return
        x0, y0 = view.to_screen(self.point)
        radius = view.radius
        if not view.visible(x0, y0, radius * 6):
            return
        steps = GlowSprites.LEVELS
        glow = light.glow
        colour = self.colour
        intensity = self.intensity
        motion = self.motion
        rise = self.rise
        cos, sin = math.cos, math.sin
        seq = []
        append = seq.append
        for angle, dist, size, delay, inv_life, swirl in self.sparks:
            u = (t - delay) * inv_life
            if u < 0.0 or u >= 1.0:
                continue
            if motion == 'implode':
                r = dist * (1.0 - u) ** 2
                a = angle + swirl * u
                dx, dy = cos(a) * r, sin(a) * r
            elif motion == 'fountain':
                a = angle
                dx = cos(a) * dist * u
                dy = sin(a) * dist * u * 0.35 - rise * 4.0 * u * (1.0 - u)
            else:   # explode
                r = dist * (1.0 - (1.0 - u) ** 3)
                a = angle + swirl * u
                dx, dy = cos(a) * r, sin(a) * r
            fade = u * 8.0 if u < 0.125 else (1.0 - u) ** 1.4 * 1.2
            level = int(steps * intensity * min(1.0, fade) + 0.5)
            if level <= 0:
                continue
            diameter = _even(size * radius * (1.0 - 0.35 * u))
            sprite = glow.sprite(diameter, colour, min(steps, level))
            if sprite is None:
                continue
            half = diameter >> 1
            append((sprite, (int(x0 + dx * radius) - half, int(y0 + dy * radius) - half), None, ADD))
        if seq:
            view.screen.blits(seq, doreturn=False)


class _RimCue(_Cue):
    """Light along the territories' outline; a bright head sweeps round each border."""

    layer = 'under'

    def __init__(self, spec, effect, territories):
        super().__init__(spec, effect)
        self.outline = effect.light.outline(territories)
        self.rim = spec
        self.base = spec.get('base', 0.4)
        self.head = spec.get('head', 0.6)
        self.sweep = max(0.05, spec.get('sweep', 1.0))
        # Brightness by u = phase ahead of the head (0-255): a sharp front and a long
        # fading trail behind it
        self.shape = [self.base + self.head * max(math.exp(-u / 6.0), math.exp(-(256 - u) / 70.0))
                      for u in range(256)]

    def render(self, light, view, t):
        b = self.brightness(t)
        if b <= 0.02:
            return
        steps = GlowSprites.LEVELS
        scale = steps * b
        levels = [min(steps, int(scale * s + 0.5)) for s in self.shape]
        shift = int(256.0 * t / self.sweep) & 255
        light.draw_outline(view, self.outline, self.raw_colour, self.colour, self.rim, levels, shift,
                           b, sweep=True)


class _MotesCue(_Cue):
    layer = 'under'

    def __init__(self, spec, effect, territories):
        super().__init__(spec, effect)
        self.territories = list(territories)
        self.style = dict(spec, rise=spec.get('rise', 8.0), sway=spec.get('sway', 1.2))
        self.motes = mote_table(spec, effect.seed ^ 0x5A5A)

    def render(self, light, view, t):
        b = self.brightness(t)
        if b > 0.02:
            light.draw_motes(view, self.territories, self.colour, self.motes, self.style, t, b,
                             self.raw_colour)


_POINT_CUES = {'rays': _RaysCue, 'flare': _FlareCue, 'ring': _RingCue, 'sparks': _SparksCue}
_TERRITORY_CUES = {'rim': _RimCue, 'motes': _MotesCue}


# ========================================
# ONE CAST
# ========================================

class HeroAbilityEffect:
    """
    One hero ability cast: the ability's cue timeline at resolved anchors.

    Args:
        light: the shared HeroLight
        spec: hero_fx_style 'abilities' entry
        anchors: {'target': (x, y), 'keep': (x, y), 'territory': [names],
                  'points': [(x, y), ...], ...} in world coordinates; cues whose
                  anchor is missing are skipped
        seed: makes the random parts (sparks, points) the same on every PC
    """

    def __init__(self, light, spec, anchors, seed=0):
        self.light = light
        self.colour = tuple(spec['colour'])
        self.white_mix = spec.get('white_mix', 0.3)
        self.seed = seed
        self.elapsed = 0.0
        self.cues = []
        self._add_cues(spec['cues'], anchors, 0.0)
        self.duration = max((cue.end for cue in self.cues), default=0.0)
        self._under = [cue for cue in self.cues if cue.layer == 'under']
        self._over = [cue for cue in self.cues if cue.layer != 'under']

    def _add_cues(self, specs, anchors, offset, point=None):
        for spec in specs:
            kind = spec['kind']
            if kind == 'each':
                for i, p in enumerate(anchors.get(spec.get('anchor', 'points')) or ()):
                    start = offset + spec.get('at', 0.0) + i * spec.get('stagger', 0.0)
                    self._add_cues(spec['cues'], anchors, start, point=p)
                continue
            shifted = dict(spec, at=offset + spec.get('at', 0.0))
            if kind in _POINT_CUES:
                p = point if point is not None else anchors.get(spec.get('anchor', 'target'))
                if p is not None:
                    self.cues.append(_POINT_CUES[kind](shifted, self, p))
            elif kind in _TERRITORY_CUES:
                territories = anchors.get(spec.get('anchor', 'territory'))
                if territories:
                    self.cues.append(_TERRITORY_CUES[kind](shifted, self, territories))

    def update(self, delta_time):
        self.elapsed += delta_time

    def is_finished(self):
        return self.elapsed >= self.duration

    def render_under(self, view):
        t = self.elapsed
        for cue in self._under:
            if cue.at <= t < cue.end:
                cue.render(self.light, view, t - cue.at)

    def render_over(self, view):
        t = self.elapsed
        for cue in self._over:
            if cue.at <= t < cue.end:
                cue.render(self.light, view, t - cue.at)


# ========================================
# PASSIVE AURA
# ========================================

class HeroAura:
    """
    A passive aura (Defiance, Haste, Safe Haven) over a set of territories, shown
    while its hero is selected. Fades in and out over the style's 'fade'.

    Stateless apart from the fade: the shimmer and the fireflies are drawn from
    the clock passed to render(), and the outline and spawn points are cached
    in the shared HeroLight per territory set.
    """

    def __init__(self, light, key, style=None):
        self.light = light
        self.key = key
        self.style = style or light.style['auras'][key]
        self.colour = light.light_colour(self.style['colour'], self.style['white_mix'])
        # Fireflies: a brighter, whiter core than the outline (a spark), coloured by
        # their halo
        motes = self.style['motes']
        self.mote_colour = light.light_colour(self.style['colour'],
                                              motes.get('white_mix', self.style['white_mix']))
        self.motes = mote_table(motes, stable_seed('aura', key))
        self.territories = ()
        self.outline = []
        self.strength = 0.0      # 0-1, eased toward 1 while shown
        self.shown = False

    def set_territories(self, territories):
        """The covered territories; the outline is rebuilt only when the set changes."""
        territories = tuple(sorted(territories))
        if territories != self.territories:
            self.territories = territories
            self.outline = self.light.outline(territories) if territories else []

    def update(self, delta_time, shown):
        self.shown = shown and bool(self.territories)
        step = delta_time / max(0.01, self.style['fade'])
        if self.shown:
            self.strength = min(1.0, self.strength + step)
        else:
            self.strength = max(0.0, self.strength - step)

    @property
    def visible(self):
        return self.strength > 0.0 and bool(self.territories)

    def render(self, view, clock):
        if not self.visible:
            return
        strength = _smooth(self.strength)
        rim = self.style['rim']
        levels = self.light.shimmer_levels(rim['base'], rim['wave'], strength * rim['intensity'])
        shift = int(clock * rim['wave_speed'] * 256.0) & 255
        self.light.draw_outline(view, self.outline, self.style['colour'], self.colour, rim, levels,
                                shift, strength)
        motes = self.style['motes']
        self.light.draw_motes(view, self.territories, self.mote_colour, self.motes, motes, clock,
                              strength * motes['intensity'], self.style['colour'])
