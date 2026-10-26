# -*- coding: utf-8 -*-
"""
Construction Dust Effect

Persistent dust around plots that are being built on, so construction is visible
at a glance (owner request, 2026-10-26):
- Back layer (before the plot disc): dust clouds rolling around the base
- Front layer (over the plot): thinner clouds across the bottom of the ring,
  motes rising from the lower rim, and tiny debris chips hopping off the
  building now and then
- 'upgrade' variant (Keep -> Castle in progress): every Nth mote is a twinkling
  gold glint, matching the golden burst when the Castle completes

STATELESS: every particle's position is a pure function of (shared clock, the
plot's phase). There are no effect objects to create, sync or remove, so the dust
is right in every mode (sequential, simultaneous, network, save/load, capture,
cancel) - it simply draws wherever game_state.under_construction says.

Each particle's spawn point changes every cycle (integer hash of the cycle
number), so a plot never visibly repeats.

Cost: one Surface.blits() call per layer, 15-19 sprites per plot (fewer on small,
zoomed-out plots: 'lod' in the style). Measured ~2.3 ms for 98 plots on screen at
min zoom, ~24 us each. The per-particle loops are kept lean (style unpacked once in __init__) because Python maths, not
blitting, is most of the cost. Sprites are scaled from one soft base per colour
(built up front) and cached per (size, alpha); at most BUILDS_PER_FRAME new ones
are made per frame, so a new zoom level never causes a hitch. Measure with
tools/plot_fx_preview.py --bench.

Integration:
    - Owned by MapRenderer (one instance), drawn from the plot render loop;
      call begin_frame() once per frame
    - Styles: plot_fx_style.DUST_STYLE
"""

import math
import random
from collections import OrderedDict

import pygame

from ui.effects.plot_fx_style import DUST_STYLE

VARIANT_BUILD = 'build'
VARIANT_UPGRADE = 'upgrade'

_TWO_PI = 2.0 * math.pi
# Sizes in the style are given at the smallest plot radius
_BASE_RADIUS = 16.0


# Spawn directions: a particle's direction for one cycle is picked from a 256-entry
# table of (cos, sin) by an integer hash of (cycle, particle, plot). Inlined in the
# loops below as:
#     h = ((cycle * 73856093) ^ particle_salt ^ plot_salt) & 0xFFFFFFFF
#     h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
#     cos_a, sin_a = table[(h >> 16) & 255]
# with particle_salt = index * 19349663 and plot_salt = seed * 83492791. A table
# lookup instead of cos()/sin() and no function call: Python maths is most of the
# dust's cost.
_DIRECTIONS = 256


def _direction_table(start_degrees, end_degrees):
    """(cos, sin) for _DIRECTIONS angles spread evenly over the arc (y down)."""
    start = math.radians(start_degrees)
    span = math.radians(end_degrees - start_degrees)
    return tuple((math.cos(start + span * i / (_DIRECTIONS - 1)),
                  math.sin(start + span * i / (_DIRECTIONS - 1))) for i in range(_DIRECTIONS))


def _plot_salt(phase):
    """The plot's part of the spawn hash, from its phase."""
    return (int(phase * 65536) * 83492791) & 0xFFFFFFFF


def _particle_salt(index):
    """A particle's part of the spawn hash."""
    return (index * 19349663) & 0xFFFFFFFF


class ConstructionDust:
    """
    Draws construction dust for one plot at a time (one shared instance).

    Usage, inside the plot render loop:
        dust.begin_frame()                                   # once per frame
        dust.draw_back(screen, x, y, radius, clock, phase)   # before the plot disc
        ...draw the plot...
        dust.draw_front(screen, x, y, radius, clock, phase)  # after the plot rings
    """

    MAX_SPRITES = 3000      # cached sprites (mostly tiny); the oldest are dropped past this
    ALPHA_STEPS = 12        # alpha is quantized to 12 levels so the sprites can be cached
    BUILDS_PER_FRAME = 12   # new sprites made per frame at most (40-250 us each). A particle whose
                            # sprite isn't ready is skipped for that frame: no hitch on a new zoom
    BASE_SIZE = 64          # full-alpha soft dot per colour that every sprite is scaled from

    def __init__(self, style=DUST_STYLE):
        self.style = style
        # Fixed seed: the same particle tables every run (deterministic tests)
        rng = random.Random(20261026)

        self._back_puffs = self._puff_tables(rng, style['puffs'], salt=0)
        self._front_puffs = self._puff_tables(rng, style['front_puffs'], salt=50)

        motes = style['motes']
        upgrade = style['upgrade']
        self._motes_shape = (_direction_table(*motes['arc']), motes['alpha'], motes['softness'])
        self._glint = (upgrade['alpha'], upgrade['size_mult'], upgrade['twinkle'],
                       tuple(upgrade['colours']))
        # Per mote: (1 / life, offset, phase multiplier, distance, rise, sway, size,
        #            colour, wobble, is a gold glint when upgrading, hash salt)
        self._motes = []
        for j in range(motes['count']):
            self._motes.append((
                1.0 / rng.uniform(*motes['life']), rng.random(), j + 2.718,
                rng.uniform(*motes['distance']), rng.uniform(*motes['rise']),
                rng.uniform(*motes['sway']), rng.uniform(*motes['size']),
                motes['colours'][rng.randrange(len(motes['colours']))],
                rng.uniform(0.0, _TWO_PI), j % upgrade['glint_every'] == 0, _particle_salt(j)))

        chips = style['chips']
        # Chips leave from around the building's upper half (180-360 deg, y down)
        self._chips_shape = (_direction_table(180.0, 360.0), chips['hop'], chips['start'],
                             chips['reach'], chips['height'], chips['size'], chips['alpha'],
                             tuple(chips['colours']))
        # Per chip: (cycle length, offset, phase multiplier, colour index, hash salt)
        self._chips = [(rng.uniform(*chips['cycle']), rng.random(), j + 1.414,
                        rng.randrange(len(chips['colours'])), _particle_salt(j + 101))
                       for j in range(chips['count'])]

        # Level of detail: smaller plots (zoomed out, when the most plots are on screen)
        # get proportionally fewer particles - the same density in a smaller area, and
        # the cost follows what is visible. Lists pre-sliced per radius, cached.
        lod = style['lod']
        self._lod_full_radius = float(lod['full_radius'])
        self._lod_min_share = float(lod['min_share'])
        self._lod_tables = {}           # radius -> (back clouds, front clouds, motes, chips)

        self._sprites = OrderedDict()   # (diameter, colour, alpha, softness) -> Surface
        self._bases = {}                # (colour, softness) -> full-alpha soft dot, BASE_SIZE
        self._build_budget = self.BUILDS_PER_FRAME
        self.sprites_built = 0          # lifetime count (tests and benchmarks read it)
        # Every base up front (~0.2 ms each), so no frame ever pays for one
        for kind in ('puffs', 'front_puffs', 'motes'):
            for colour in style[kind]['colours']:
                self._base(colour, style[kind]['softness'])
        for colour in upgrade['colours']:
            self._base(colour, motes['softness'])

    @staticmethod
    def _puff_tables(rng, style, salt):
        """(shape constants, per-cloud constants) for one cloud layer."""
        # Brightness over a cloud's life: rises until 'swell', holds full until 'hold',
        # then fades out (stored as reciprocals for the loop)
        swell, hold = style['swell'], style['hold']
        shape = (_direction_table(*style['arc']), style['distance'], style['drift'],
                 style['size'][0], style['size'][1] - style['size'][0], style['alpha'],
                 style['softness'], 1.0 / swell, hold, 1.0 / (1.0 - hold))
        # Per cloud: (1 / life, offset, phase multiplier, colour, hash salt)
        clouds = [(1.0 / rng.uniform(*style['life']), rng.random(), j + 1.618,
                   style['colours'][rng.randrange(len(style['colours']))], _particle_salt(j + salt))
                  for j in range(style['count'])]
        return shape, clouds

    def begin_frame(self):
        """Call once per rendered frame before drawing: resets the sprite build budget."""
        self._build_budget = self.BUILDS_PER_FRAME

    def _tables_for(self, radius):
        """The particles drawn at this plot radius (level of detail), cached per radius."""
        tables = self._lod_tables.get(radius)
        if tables is None:
            share = min(1.0, max(self._lod_min_share, radius / self._lod_full_radius))

            def keep(items):
                return items[:max(1, int(math.ceil(len(items) * share)))]

            tables = (keep(self._back_puffs[1]), keep(self._front_puffs[1]),
                      keep(self._motes), keep(self._chips))
            self._lod_tables[radius] = tables
        return tables

    def particle_count(self, radius):
        """Particles one plot draws at this radius (tests, benchmarks)."""
        return sum(len(table) for table in self._tables_for(radius))

    # ---------- sprites ----------

    def _base(self, colour, softness):
        """Full-alpha soft dot (radial falloff (1 - t^2) ** softness) at BASE_SIZE."""
        key = (colour, softness)
        base = self._bases.get(key)
        if base is None:
            size = self.BASE_SIZE
            base = pygame.Surface((size, size), pygame.SRCALPHA)
            centre = size // 2
            for r in range(centre, 0, -1):
                t = r / float(centre)
                a = int(255 * (1.0 - t * t) ** softness)
                if a > 0:
                    pygame.draw.circle(base, (colour[0], colour[1], colour[2], a), (centre, centre), r)
            self._bases[key] = base
        return base

    def _sprite(self, key):
        """
        The sprite for key = (diameter, colour, alpha, softness), or None when it
        isn't cached and this frame's build budget is spent (the caller skips the
        particle for one frame).

        softness None = a hard square (debris chips). Alpha is baked into the
        pixels (no set_alpha), which keeps the blit on pygame's fast path.
        """
        sprite = self._sprites.get(key)
        if sprite is not None:
            return sprite
        if self._build_budget <= 0:
            return None
        self._build_budget -= 1
        diameter, colour, alpha, softness = key
        if softness is None or diameter <= 2:
            sprite = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
            sprite.fill((colour[0], colour[1], colour[2], alpha))
        else:
            sprite = pygame.transform.smoothscale(self._base(colour, softness), (diameter, diameter))
            if alpha < 255:
                sprite.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        if pygame.display.get_surface() is not None:
            sprite = sprite.convert_alpha()
        self._sprites[key] = sprite
        self.sprites_built += 1
        if len(self._sprites) > self.MAX_SPRITES:
            for _ in range(self.MAX_SPRITES // 10):
                self._sprites.popitem(last=False)   # oldest first
        return sprite

    # ---------- layers ----------

    def _add_clouds(self, seq, shape, clouds, x, y, radius, clock, phase, plot_salt):
        """Dust clouds that form on the rim, swell and drift out (appends to seq)."""
        (directions, distance, drift, size0, size_span, peak, softness, inv_swell, hold,
         inv_fade) = shape
        steps = self.ALPHA_STEPS
        sprites_get = self._sprites.get
        for inv_life, offset, phase_mult, colour, salt in clouds:
            u = clock * inv_life + offset + phase * phase_mult
            cycle = int(u)
            age = u - cycle
            # Swell, hold at full strength, fade out
            if age < hold:
                env = age * inv_swell
                if env > 1.0:
                    env = 1.0
            else:
                env = (1.0 - age) * inv_fade
            level = int(env * steps + 0.5)
            if level <= 0:
                continue
            # Even diameters only: half the sprite variants to cache, invisible on soft clouds
            diameter = max(2, int((size0 + size_span * age) * radius) & ~1)
            key = (diameter, colour, peak * level // steps, softness)
            sprite = sprites_get(key)
            if sprite is None:
                sprite = self._sprite(key)
                if sprite is None:
                    continue   # not built yet (budget spent): drawn from next frame
            h = ((cycle * 73856093) ^ salt ^ plot_salt) & 0xFFFFFFFF
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
            cos_a, sin_a = directions[(h >> 16) & 255]
            dist = (distance + drift * age) * radius
            half = diameter >> 1
            seq.append((sprite, (int(x + cos_a * dist) - half,
                                 int(y + sin_a * dist - 0.15 * age * radius) - half)))

    def draw_back(self, screen, x, y, radius, clock, phase, variant=VARIANT_BUILD):
        """Dust clouds rolling around the base. Draw BEFORE the plot disc."""
        seq = []
        self._add_clouds(seq, self._back_puffs[0], self._tables_for(radius)[0], x, y, radius,
                         clock, phase, _plot_salt(phase))
        if seq:
            screen.blits(seq, doreturn=False)

    def draw_front(self, screen, x, y, radius, clock, phase, variant=VARIANT_BUILD):
        """
        Thin clouds across the bottom of the plot, rising motes (gold glints when
        upgrading) and debris chips. Draw AFTER the plot.
        """
        plot_salt = _plot_salt(phase)
        _, front_clouds, motes, chips = self._tables_for(radius)
        seq = []
        self._add_clouds(seq, self._front_puffs[0], front_clouds, x, y, radius, clock, phase,
                         plot_salt)

        directions, peak, softness = self._motes_shape
        upgrading = variant == VARIANT_UPGRADE
        glint_alpha, glint_size, twinkle, glint_colours = self._glint
        steps = self.ALPHA_STEPS
        scale = radius / _BASE_RADIUS
        sprites_get = self._sprites.get
        sin = math.sin

        for (inv_life, offset, phase_mult, dist, rise, sway, size, colour, wobble,
             glint, salt) in motes:
            u = clock * inv_life + offset + phase * phase_mult
            cycle = int(u)
            age = u - cycle
            # Fade in over the first 18%, fade out over the last 45%
            if age < 0.18:
                env = age * 5.5556
            elif age > 0.55:
                env = (1.0 - age) * 2.2222
            else:
                env = 1.0
            mote_peak = peak
            if upgrading and glint:
                # Gold glint: brighter, a little larger, twinkling
                colour = glint_colours[cycle % len(glint_colours)]
                mote_peak = glint_alpha
                size *= glint_size
                env *= 0.55 + 0.45 * sin(age * twinkle + wobble)
            level = int(env * steps + 0.5)
            if level <= 0:
                continue
            diameter = max(1, int(size * scale + 0.5))
            key = (diameter, colour, mote_peak * level // steps, softness)
            sprite = sprites_get(key)
            if sprite is None:
                sprite = self._sprite(key)
                if sprite is None:
                    continue
            h = ((cycle * 73856093) ^ salt ^ plot_salt) & 0xFFFFFFFF
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
            cos_a, sin_a = directions[(h >> 16) & 255]
            half = diameter >> 1
            seq.append((sprite, (int(x + (cos_a * dist + sway * sin(age * 8.17 + wobble)) * radius) - half,
                                 int(y + (sin_a * dist - rise * age) * radius) - half)))

        directions, hop, start, reach, height, chip_px, chip_alpha, chip_colours = self._chips_shape
        chip_size = max(1, int(chip_px * scale + 0.5))
        chip_half = chip_size >> 1
        for cycle_len, offset, phase_mult, colour_index, salt in chips:
            u = clock / cycle_len + offset + phase * phase_mult
            cycle = int(u)
            elapsed = (u - cycle) * cycle_len
            if elapsed >= hop:
                continue   # resting between hops
            a = elapsed / hop
            env = 1.0 if a < 0.75 else (1.0 - a) * 4.0
            level = int(env * steps + 0.5)
            if level <= 0:
                continue
            colour = chip_colours[(colour_index + cycle) % len(chip_colours)]
            key = (chip_size, colour, chip_alpha * level // steps, None)
            sprite = sprites_get(key)
            if sprite is None:
                sprite = self._sprite(key)
                if sprite is None:
                    continue
            # Leave from somewhere around the building's upper half, flying outward
            h = ((cycle * 73856093) ^ salt ^ plot_salt) & 0xFFFFFFFF
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
            cos_a, sin_a = directions[(h >> 16) & 255]
            direction = 1.0 if cos_a >= 0 else -1.0
            px = x + (cos_a * start + direction * reach * a) * radius
            py = y + (sin_a * start - (4.0 * height * a * (1.0 - a) - 0.3 * a)) * radius
            seq.append((sprite, (int(px) - chip_half, int(py) - chip_half)))

        if seq:
            screen.blits(seq, doreturn=False)
