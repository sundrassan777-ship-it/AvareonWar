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
from ui.effects.light_fx import (GlowSprites, TintSprites, DarkSprites, SoftRing, TerritoryRaster,
                                 bead_chain)
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
        self.dark = DarkSprites()
        self.ring = SoftRing(self.kit['ring_width'])
        self.rays = ProductionRays(style['rays'])
        self.polygons = polygons
        self._raster = None
        self._fine = {}                  # territory -> its border beads (_border)
        self._bboxes = {}                # territory -> world bbox
        self._outlines = OrderedDict()   # frozenset(territories) -> outline
        self._spawns = {}                # (territory, rise) -> [(x, y), ...]
        self._areas = {}                 # territory -> area, world px^2
        self._mote_cache = OrderedDict() # firefly sprites per (mote table, radius, colours)
        self._mote_plans = OrderedDict() # per-territory firefly plans (_mote_plan)
        self.prewarm_radii = ()
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
        self.dark.begin_frame()

    def prewarm(self, radii):
        """
        Build what the first frames would otherwise pay for (at load, ~0.1 s):
        the ray bases for every plot radius, the ring, the territory raster,
        every territory's border beads, and the border-light and firefly sprites
        of the auras and abilities at every size the zoom range gives (a border
        light shows only once all its brightness levels exist).
        """
        self.prewarm_radii = sorted(set(radii))   # HeroAura prewarms its fireflies at these
        self.rays.prewarm(radii)
        self.ring.prewarm()
        self.raster()
        for territory in self.polygons:
            self._border(territory)
        radii = sorted(set(radii))
        rims = []   # (rim style, raw colour, light colour)
        styles = list(self.style['auras'].values()) + list(self.style.get('persistent', {}).values())
        for aura in styles:
            if aura.get('rim'):
                rims.append((aura['rim'], tuple(aura['colour']),
                             self.light_colour(aura['colour'], aura['white_mix'])))
        for spec in self.style['abilities'].values():
            for cue in _rim_cues(spec['cues']):
                raw = tuple(cue.get('colour', spec['colour']))
                rims.append((cue, raw, self.light_colour(raw, cue.get('white_mix', spec.get('white_mix', 0.3)))))
        for rim, raw, colour in rims:
            tint = rim.get('tint')
            for radius in radii:
                self.glow.prewarm([_even(rim['size'] * radius)], colour, profile='bead')
                if tint and tint.get('alpha', 0) > 0:
                    # Every alpha level: a one-shot border light fades in and out
                    self.tint.prewarm([_even(tint['size'] * radius)], raw,
                                      range(0, tint['alpha'] + 1, 255 // TintSprites.LEVELS),
                                      tint.get('softness', 1.5))
        for aura in styles:
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

    def _border(self, territory):
        """
        A territory's border beads, built once (~1 ms each; all of them at load,
        prewarm): ([(x, y, outward nx, ny, shimmer phase, sweep phase), ...],
        [the territory just outside each bead, or None]). Outlines of any set
        are then a filter over these, with no territory lookups at cast time.
        """
        border = self._fine.get(territory)
        if border is None:
            chain = bead_chain(self.polygons.get(territory) or [], self.kit['fine_spacing'])
            raster = self.raster()
            probe = self.kit['probe']
            wave_units = 256.0 / self.kit['wave_length']
            perimeter = (chain[-1][2] + self.kit['fine_spacing']) if chain else 1.0
            sweep_units = 256.0 / perimeter
            beads = [(x, y, nx, ny, int(s * wave_units) & 255, int(s * sweep_units) & 255)
                     for x, y, s, nx, ny in chain]
            outside = [raster.at(x + nx * probe, y + ny * probe) for x, y, s, nx, ny in chain]
            border = self._fine[territory] = (beads, outside)
        return border

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
        parts = []
        for territory in sorted(key):
            beads, outside = self._border(territory)
            if not beads:
                continue
            # Drop the beads on a border shared with another lit territory
            kept = [bead for bead, other in zip(beads, outside)
                    if other is None or other == territory or other not in key]
            parts.append((territory, self.bbox(territory), kept))
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

    def mote_count(self, territory, style, available, radius=None):
        """
        Fireflies in one territory: style['density'] per 1000 world px^2 (the
        same density in big and small territories), clamped to min..available.
        With a style['lod'] the density drops on small (zoomed-out) plots, down to
        min_share at the smallest - when the most territories are on screen.
        Without a density every firefly of the table is used.
        """
        density = style.get('density')
        if density is None:
            return available
        lod = style.get('lod')
        if lod and radius:
            density *= max(lod['min_share'], min(1.0, radius / float(lod['full_radius'])))
        count = int(round(self.area(territory) * density / 1000.0))
        return max(min(style.get('min', 1), available), min(available, count))

    def _mote_sprites(self, motes, radius, colour, halo_colour, tint_size, tint_alpha):
        """
        Per firefly of a mote table at this plot radius: (core ladders by sub-pixel
        phase, core half size, halo ladder or None, halo half size) - the ladders
        indexed by brightness level (the halo's spread over 0..tint_alpha). Cached
        per (table, radius, colours) once complete; None while the unshifted core
        or the halo ladders are still being built within the frame budget. Until
        a shifted copy exists its phase uses the unshifted ladder.
        """
        key = (id(motes), radius, colour, halo_colour, tint_size, tint_alpha)
        entry = self._mote_cache.get(key)
        if entry is not None and entry[0] is motes:
            return entry[1]
        prepared = []
        complete = True
        phases_by_diameter = {}
        halos_by_diameter = {}
        for _, _, size, _, _ in motes:
            diameter = _even(size * radius)
            phases = phases_by_diameter.get(diameter)
            if phases is None:
                unshifted = self.glow.ladder(diameter, colour)
                if unshifted is None:
                    return None
                phases = [unshifted]
                for phase in range(1, GlowSprites.SUBPIXEL_PHASES):
                    shifted = self.glow.ladder(diameter, colour, 'mote', phase)
                    if shifted is None:
                        complete = False
                        shifted = unshifted
                    phases.append(shifted)
                phases_by_diameter[diameter] = phases
            halo_ladder, halo_half = None, 0
            if tint_alpha:
                # Halo sizes in steps of 4 px: fewer sprites to build
                halo_d = max(4, int(size * radius * tint_size) & ~3)
                halo_ladder = halos_by_diameter.get(halo_d)
                if halo_ladder is None:
                    halo_ladder = self.tint.alpha_ladder(halo_d, halo_colour, tint_alpha)
                    if halo_ladder is None:
                        return None
                    halos_by_diameter[halo_d] = halo_ladder
                halo_half = halo_d >> 1
            prepared.append((phases, diameter >> 1, halo_ladder, halo_half))
        if complete:
            self._mote_cache[key] = (motes, prepared)
            if len(self._mote_cache) > 64:
                self._mote_cache.popitem(last=False)
        return prepared

    def _mote_plan(self, territories, style, motes, sprites, radius):
        """
        Per territory, what draw_motes needs besides the clock: (world bbox, spawn
        points, their count, hash salt, phase offset, [(firefly, its sprites), ...]
        for this territory's firefly count). Cached per (territory set, style,
        sprites, radius) - it only changes with the zoom level - so a frame does no
        per-territory bookkeeping (it was most of the embers' cost over 40
        territories).
        """
        key = (id(territories), id(style), id(sprites), radius)
        entry = self._mote_plans.get(key)
        if (entry is not None and entry[0] is territories and entry[1] is sprites
                and entry[2] is style):
            return entry[3]
        rise = style['rise']
        plan = []
        for territory in territories:
            points = self.spawn_points(territory, rise)
            tsalt = stable_seed(territory) & 0xFFFF
            n = self.mote_count(territory, style, len(motes), radius)
            plan.append((self.bbox(territory), points, len(points), tsalt, tsalt / 65536.0,
                         list(zip(motes[:n], sprites))))
        self._mote_plans[key] = (territories, sprites, style, plan)
        if len(self._mote_plans) > 32:
            self._mote_plans.popitem(last=False)
        return plan

    def prewarm_motes(self, motes, colour, halo_colour, tint_size, tint_alpha):
        """
        Build a mote table's unshifted and halo sprites for every prewarmed plot
        radius now (at load); the sub-pixel copies follow within the frame budget.
        """
        budgets = (self.glow._budget, self.tint._budget)
        self.glow._budget = self.tint._budget = light_fx._BuildBudget(10 ** 9, 10 ** 9)
        try:
            for radius in self.prewarm_radii:
                for _, _, size, _, _ in motes:
                    self.glow.ladder(_even(size * radius), colour)
                    if tint_alpha:
                        self.tint.alpha_ladder(max(4, int(size * radius * tint_size) & ~3),
                                               halo_colour, tint_alpha)
        finally:
            self.glow._budget, self.tint._budget = budgets

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
        halo_colour = tuple(style.get('tint_colour', raw_colour or (0, 0, 0)))
        # Brightness over a life: sin(pi * age) ** power (2 = a brief twinkle, 1 = lit
        # for most of it)
        squared = style.get('glow_power', 2) == 2
        radius = view.radius
        steps = GlowSprites.LEVELS
        # Each firefly's core and halo sprites for this plot size, looked up once
        # (a per-firefly cache lookup was most of the cost with hundreds of them)
        sprites = self._mote_sprites(motes, radius, colour, halo_colour, tint_size, tint_alpha)
        if sprites is None:
            return   # still being built (within the frame budget)
        halo_scale = TintSprites.LEVELS * brightness
        halo_top = TintSprites.LEVELS
        core_scale = steps * brightness
        z = view.zoom
        ax, ay = view.ax, view.ay
        w, h = view.width, view.height
        halos = []
        halo_append = halos.append
        seq = []
        append = seq.append
        sin = math.sin
        pi = math.pi
        for (bx0, by0, bx1, by1), points, count, tsalt, tphase, active in \
                self._mote_plan(territories, style, motes, sprites, radius):
            if (ax + bx1 * z < -radius or ax + bx0 * z > w + radius
                    or ay + by1 * z < -radius or ay + by0 * z > h + radius):
                continue
            for (inv_life, offset, size, sway_phase, salt), (phases, core_half, halo_ladder, halo_half) \
                    in active:
                u = clock * inv_life + offset + tphase
                cycle = int(u)
                age = u - cycle
                env = sin(pi * age)
                if squared:
                    env *= env
                level = int(core_scale * env + 0.5)
                if level <= 0:
                    continue
                hsh = ((cycle * 73856093) ^ salt ^ tsalt) & 0xFFFFFFFF
                hsh = ((hsh ^ (hsh >> 13)) * 1274126177) & 0xFFFFFFFF
                px, py = points[(hsh >> 8) % count]
                # Sub-pixel placement: the position rounded to half pixels across and
                # quarter pixels down (offset by 4096 to stay positive), split into the
                # whole pixel and the shifted copy of the sprite to draw there
                xq = int((ax + (px + sway * sin(age * 6.0 + sway_phase)) * z + 4096.0) * 2.0 + 0.5)
                yq = int((ay + (py - rise * age) * z + 4096.0) * 4.0 + 0.5)
                x = (xq >> 1) - 4096
                y = (yq >> 2) - 4096
                if halo_ladder is not None:
                    halo_level = int(halo_scale * env + 0.5)
                    if halo_level > 0:
                        halo_append((halo_ladder[halo_level if halo_level < halo_top else halo_top],
                                     (x - halo_half, y - halo_half)))
                append((phases[(yq & 3) + ((xq & 1) << 2)][level if level < steps else steps],
                        (x - core_half, y - core_half), None, ADD))
        if halos:
            view.screen.blits(halos, doreturn=False)
        if seq:
            view.screen.blits(seq, doreturn=False)


def _rim_cues(cues):
    """Every 'rim' cue of an ability, nested 'each' cues included."""
    for cue in cues:
        if cue['kind'] == 'rim':
            yield cue
        elif cue['kind'] == 'each':
            yield from _rim_cues(cue['cues'])


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


class _CometsCue(_Cue):
    """
    Comets of light flying an arc from one point to another: a bright head with
    a trail of fading motes behind it (Royal Charisma, Valorous Charge).
    Closed form: each comet's place on the curve is a function of time.
    """

    def __init__(self, spec, effect, source, dest):
        super().__init__(spec, effect)
        self.count = spec.get('count', 3)
        self.travel = spec.get('travel', 1.0)
        self.stagger = spec.get('stagger', 0.15)
        self.trail = spec.get('trail', 9)
        self.trail_gap = spec.get('trail_gap', 0.03)
        self.head = spec.get('size', 0.9)
        self.tint = spec.get('tint', 0)
        sx, sy = source
        dx, dy = dest
        length = math.hypot(dx - sx, dy - sy) or 1.0
        # Control point raised above the middle (screen up = -y) by `arc` of the distance
        lift = spec.get('arc', 0.35) * length
        self.curve = (sx, sy, (sx + dx) / 2.0, (sy + dy) / 2.0 - lift, dx, dy)
        # Perpendicular to the flight, for each comet's sideways weave
        self.normal = (-(dy - sy) / length, (dx - sx) / length)
        rng = random.Random(effect.seed ^ stable_seed('comets', self.at))
        spread = spec.get('spread', 4.0)
        self.weaves = [(rng.uniform(-spread, spread), rng.uniform(0.0, _TWO_PI))
                       for _ in range(self.count)]
        self.duration = (self.count - 1) * self.stagger + self.travel + self.trail * self.trail_gap
        self.fade_out = min(self.fade_out, self.duration * 0.5)

    def _point(self, u, weave, phase):
        sx, sy, cx, cy, dx, dy = self.curve
        a, b, c = (1.0 - u) ** 2, 2.0 * (1.0 - u) * u, u * u
        side = weave * math.sin(u * _TWO_PI + phase) * math.sin(u * math.pi)
        return (a * sx + b * cx + c * dx + self.normal[0] * side,
                a * sy + b * cy + c * dy + self.normal[1] * side)

    def render(self, light, view, t):
        if not 0.0 <= t < self.duration:
            return
        steps = GlowSprites.LEVELS
        radius = view.radius
        glow = light.glow
        z, ax, ay = view.zoom, view.ax, view.ay
        halos = []
        seq = []
        for i, (weave, phase) in enumerate(self.weaves):
            start = i * self.stagger
            for k in range(self.trail + 1):
                tk = t - start - k * self.trail_gap
                if tk < 0.0 or tk > self.travel:
                    continue
                u = _smooth(tk / self.travel)
                fade = (1.0 - k / float(self.trail + 1)) ** 1.3
                level = int(steps * self.intensity * fade + 0.5)
                if level <= 0:
                    continue
                wx, wy = self._point(u, weave, phase)
                x, y = ax + wx * z, ay + wy * z
                diameter = _even(self.head * radius * (1.0 - 0.45 * k / float(self.trail + 1)))
                if k % 3 == 0 and self.tint:
                    # A colour halo under the head and every third trail mote
                    halo_d = max(4, int(diameter * 2.2) & ~3)
                    halo = light.tint.sprite(halo_d, self.raw_colour, self.tint * self.intensity * fade)
                    if halo is not None:
                        halos.append((halo, (int(x) - (halo_d >> 1), int(y) - (halo_d >> 1))))
                sprite = glow.sprite(diameter, self.colour, min(steps, level))
                if sprite is not None:
                    half = diameter >> 1
                    seq.append((sprite, (int(x) - half, int(y) - half), None, ADD))
        if halos:
            view.screen.blits(halos, doreturn=False)
        if seq:
            view.screen.blits(seq, doreturn=False)


class _DrainCue(_Cue):
    """
    Anti-light (Regicide): a soft dark stain that swells over the point, as if
    the light were drawn out of it. Drawn with BLEND_RGB_MULT.
    """

    layer = 'under'

    def __init__(self, spec, effect, point):
        super().__init__(spec, effect)
        self.point = point
        self.size = spec.get('size', (2.0, 4.0))
        self.grow = max(0.01, spec.get('grow', 0.4))
        # The multiply colour at full depth: the raw colour, darkened
        darkness = spec.get('darkness', 0.45)
        self.dark = tuple(int(c * darkness) for c in self.raw_colour)

    def render(self, light, view, t):
        b = self.brightness(t)
        if b <= 0.02:
            return
        s0, s1 = self.size
        g = 1.0 - (1.0 - min(1.0, t / self.grow)) ** 2
        diameter = _ladder_size((s0 + (s1 - s0) * g) * view.radius)
        x, y = view.to_screen(self.point)
        if not view.visible(x, y, diameter):
            return
        level = int(GlowSprites.LEVELS * b + 0.5)
        sprite = light.dark.sprite(diameter, self.dark, level, 'flare') if level > 0 else None
        if sprite is not None:
            half = diameter >> 1
            view.screen.blit(sprite, (int(x) - half, int(y) - half), special_flags=MULT)


class _DustCue(_Cue):
    """
    Dust clouds thrown out from a point (Relentless Charge: cavalry arriving).
    Normal-blend soft puffs that swell, drift outward and thin out.
    """

    def __init__(self, spec, effect, point):
        super().__init__(spec, effect)
        self.point = point
        rng = random.Random(effect.seed ^ stable_seed('dust', self.at, point))
        d0, d1 = spec.get('distance', (0.8, 2.4))
        l0, l1 = spec.get('life', (0.9, 1.6))
        colours = [tuple(c) for c in spec.get('colours', ((170, 108, 62),))]
        self.size = spec.get('size', (0.8, 2.2))
        self.alpha = spec.get('alpha', 200)
        self.softness = spec.get('softness', 0.6)
        spread = spec.get('spread', 0.1)
        # (angle, distance, 1 / life, delay, colour)
        self.puffs = [(rng.uniform(0.0, _TWO_PI), rng.uniform(d0, d1), 1.0 / rng.uniform(l0, l1),
                       rng.uniform(0.0, spread), colours[rng.randrange(len(colours))])
                      for _ in range(spec.get('count', 10))]
        self.duration = spread + l1

    def brightness(self, t):
        return 1.0 if 0.0 <= t < self.duration else 0.0

    def render(self, light, view, t):
        if not 0.0 <= t < self.duration:
            return
        x0, y0 = view.to_screen(self.point)
        radius = view.radius
        if not view.visible(x0, y0, radius * 6):
            return
        s0, s1 = self.size
        tint = light.tint
        seq = []
        for angle, dist, inv_life, delay, colour in self.puffs:
            u = (t - delay) * inv_life
            if u < 0.0 or u >= 1.0:
                continue
            r = dist * (1.0 - (1.0 - u) ** 2) * radius
            alpha = self.alpha * min(1.0, u * 6.0) * (1.0 - u) ** 1.2
            diameter = max(4, int((s0 + (s1 - s0) * u) * radius) & ~3)
            sprite = tint.sprite(diameter, colour, alpha, self.softness)
            if sprite is None:
                continue
            half = diameter >> 1
            x = x0 + math.cos(angle) * r
            y = y0 + math.sin(angle) * r * 0.6 - 0.4 * u * radius   # flattened, rising
            seq.append((sprite, (int(x) - half, int(y) - half)))
        if seq:
            view.screen.blits(seq, doreturn=False)


class _CurtainCue(_Cue):
    """
    A wavy curtain of colour sweeping across the whole screen, left to right,
    with embers flaring where its front passes (Vow of Silence). Screen space:
    it does not follow the camera. The strip is baked once per cue (~2-4 ms);
    a frame is one or two strip blits plus the embers.
    """

    def __init__(self, spec, effect):
        super().__init__(spec, effect)
        self.sweep = spec.get('sweep', 1.4)
        self.width_share = spec.get('width', 0.2)
        self.wave = spec.get('wave', 0.05)
        self.alpha = spec.get('alpha', 150)
        self.ramp = spec.get('ramp', 1.6)
        self.strip_colour = tuple(spec.get('strip_colour', self.raw_colour))
        self.embers_spec = spec.get('embers', 60)
        self._strip = None
        self._glow = None
        self._embers = None
        self._seed = effect.seed

    def _front(self, t, width, strip_w):
        """Where the curtain's front is at time t (it starts off the left edge)."""
        u = _smooth(min(1.0, t / self.sweep))
        return -strip_w + (width + 2 * strip_w) * u

    def _bake(self, width, height):
        strip_w = max(40, int(width * self.width_share))
        amp = int(height * self.wave)
        # One row: transparent at the back (left), the colour building toward the front
        row_w = strip_w + 2 * amp
        row = pygame.Surface((row_w, 1), pygame.SRCALPHA)
        r, g, b = self.strip_colour
        for x in range(strip_w):
            a = int(self.alpha * (x / float(strip_w)) ** self.ramp)
            row.set_at((x, 0), (r, g, b, a))
        strip = pygame.Surface((row_w, height), pygame.SRCALPHA)
        # The front's glow: additive light along the front edge
        glow_w = max(8, strip_w // 7)
        glow_row = light_fx.new_black_surface((glow_w + 2 * amp, 1))
        lr, lg, lb = self.colour
        for x in range(glow_w):
            v = math.sin(math.pi * x / float(glow_w)) ** 2
            glow_row.set_at((x, 0), (int(lr * v), int(lg * v), int(lb * v)))
        glow = light_fx.new_black_surface((glow_w + 2 * amp, height))
        rng = random.Random(self._seed)
        phases = (rng.uniform(0, _TWO_PI), rng.uniform(0, _TWO_PI))
        for y in range(height):
            # Wavy front: two sine waves, so it doesn't look mechanical
            off = int(amp + amp * 0.6 * math.sin(_TWO_PI * 2.0 * y / height + phases[0])
                      + amp * 0.4 * math.sin(_TWO_PI * 5.0 * y / height + phases[1]))
            off = max(0, min(2 * amp, off))
            strip.blit(row, (off, y))
            glow.blit(glow_row, (off, y))
        if pygame.display.get_surface() is not None:
            strip = strip.convert_alpha()
        self._strip, self._glow = strip, glow
        self._size = (width, height, strip_w, amp, glow_w)
        # Embers: (x px, y share, size, life, when the front passes x)
        self._embers = []
        for _ in range(self.embers_spec):
            ex = rng.random() * width
            self._embers.append((ex, rng.random(), rng.uniform(0.5, 1.0), rng.uniform(0.6, 1.1),
                                 self._passed_time(ex, width, strip_w)))

    def render(self, light, view, t):
        b = self.brightness(t)
        if b <= 0.02:
            return
        width, height = view.width, view.height
        if self._strip is None or self._size[:2] != (width, height):
            self._bake(width, height)
        _, _, strip_w, amp, glow_w = self._size
        front = self._front(t, width, strip_w)
        x = int(front - strip_w - amp)
        screen = view.screen
        alpha = int(255 * b)
        self._strip.set_alpha(alpha if alpha < 252 else 255)
        screen.blit(self._strip, (x, 0))
        if b > 0.05:
            if b < 0.99:
                # Fade the front's light: a darkened copy (the glow strip is narrow)
                faded = self._glow.copy()
                v = int(255 * b)
                faded.fill((v, v, v), special_flags=MULT)
                screen.blit(faded, (int(front - glow_w // 2 - amp), 0), special_flags=ADD)
            else:
                screen.blit(self._glow, (int(front - glow_w // 2 - amp), 0), special_flags=ADD)
        # Embers flare where the front has passed, then rise and fade
        steps = GlowSprites.LEVELS
        radius = view.radius
        seq = []
        for ex, ys, size, life, passed in self._embers:
            if ex > front:
                continue
            u = (t - passed) / life
            if u < 0.0 or u >= 1.0:
                continue
            level = int(steps * b * (1.0 - u) ** 1.5 + 0.5)
            if level <= 0:
                continue
            diameter = _even(size * radius)
            sprite = light.glow.sprite(diameter, self.colour, min(steps, level))
            if sprite is None:
                continue
            half = diameter >> 1
            seq.append((sprite, (int(ex) - half, int(ys * height - u * radius * 2.5) - half),
                        None, ADD))
        if seq:
            screen.blits(seq, doreturn=False)

    def _passed_time(self, x, width, strip_w):
        """When the front reached screen x (inverse of _front, by bisection)."""
        lo, hi = 0.0, self.sweep
        for _ in range(12):
            mid = (lo + hi) / 2.0
            if self._front(mid, width, strip_w) < x:
                lo = mid
            else:
                hi = mid
        return hi


_POINT_CUES = {'rays': _RaysCue, 'flare': _FlareCue, 'ring': _RingCue, 'sparks': _SparksCue,
               'drain': _DrainCue, 'dust': _DustCue}
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
            elif kind == 'comets':
                source = anchors.get(spec.get('from', 'source'))
                dest = anchors.get(spec.get('to', 'dest'))
                if source is not None and dest is not None:
                    self.cues.append(_CometsCue(shifted, self, source, dest))
            elif kind == 'curtain':
                self.cues.append(_CurtainCue(shifted, self))

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
    while its hero is selected; also persistent effects drawn the same way (the
    Embargo embers: fireflies without the outline light). Fades in and out over
    the style's 'fade'.

    Stateless apart from the fade: the shimmer and the fireflies are drawn from
    the clock passed to render(), and the outline and spawn points are cached
    in the shared HeroLight per territory set.

    Args:
        key: an aura in style['auras'], or a persistent effect in style['persistent']
    """

    def __init__(self, light, key, style=None):
        self.light = light
        self.key = key
        if style is None:
            style = light.style['auras'].get(key) or light.style['persistent'][key]
        self.style = style
        self.colour = light.light_colour(self.style['colour'], self.style['white_mix'])
        # Fireflies: a brighter, whiter core than the outline (a spark), coloured by
        # their halo
        motes = self.style['motes']
        self.mote_colour = light.light_colour(self.style['colour'],
                                              motes.get('white_mix', self.style['white_mix']))
        self.motes = mote_table(motes, stable_seed('aura', key))
        # Its fireflies' sprites now, so the first selection doesn't wait for them
        light.prewarm_motes(self.motes, self.mote_colour,
                            tuple(motes.get('tint_colour', self.style['colour'])),
                            motes.get('tint_size', 2.0), motes.get('tint', 0))
        self.territories = ()
        self.outline = []
        self.strength = 0.0      # 0-1, eased toward 1 while shown
        self.shown = False

    def set_territories(self, territories):
        """The covered territories; the outline is rebuilt only when the set changes."""
        territories = tuple(sorted(territories))
        if territories != self.territories:
            self.territories = territories
            has_rim = 'rim' in self.style
            self.outline = self.light.outline(territories) if territories and has_rim else []
            # Firefly spawn points now, not in the first frame that draws them
            for territory in territories:
                self.light.spawn_points(territory, self.style['motes']['rise'])

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
        rim = self.style.get('rim')
        if rim:
            levels = self.light.shimmer_levels(rim['base'], rim['wave'], strength * rim['intensity'])
            shift = int(clock * rim['wave_speed'] * 256.0) & 255
            self.light.draw_outline(view, self.outline, self.style['colour'], self.colour, rim,
                                    levels, shift, strength)
        motes = self.style['motes']
        self.light.draw_motes(view, self.territories, self.mote_colour, self.motes, motes, clock,
                              strength * motes['intensity'], self.style['colour'])
