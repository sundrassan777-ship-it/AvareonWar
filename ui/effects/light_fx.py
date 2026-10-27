# -*- coding: utf-8 -*-
"""
Light FX kit

Shared building blocks for effects drawn as additive light, in the style of the
production light rays: opaque black surfaces blitted with BLEND_RGB_ADD (black
adds nothing, so there is no per-pixel alpha), soft radial profiles baked once,
and caches keyed only by quantized values.

Pieces:
    new_black_surface / radial_surface / light_colour
                          the helpers the production rays are built from
    GlowSprites           soft light dots (bright core + bloom) per (diameter,
                          colour, brightness level): bounded LRU, per-frame build
                          budget, one grey base per profile shared by every colour
    TintSprites           the same for normal-blend colour halos (keeps a light's
                          hue readable on the bright parchment map)
    SoftRing              Gaussian ring of light, baked once in grey, scaled per frame
                          (draw / draw_tint) or cached per radius and brightness
                          (frame / tint_frame)
    TerritoryRaster       territory id per world pixel: inside tests in O(1)
    bead_chain            evenly spaced points along a territory border
    path_beads            the same along an open path (path_point: a point on it)
    GlowFrame             soft light hugging a rectangle, circle or sprite outline
                          (UI highlights), cached per shape, size and brightness
    RisingMotes           motes of light rising and fading on screen or over a
                          panel, from a clock (nothing stored per mote)

Users: production_glow_effect.py (production rays), hero_fx_effect.py (hero
ability effects), order_fx_effect.py (selection rings, order arrows),
marker_fx_effect.py (map markers), turn_announcement_effect.py (turn banner),
main.py (Master Negotiator glow), ui_renderer.py (Ruthless Ingenuity motes).
"""

import math
import random
import time
from collections import OrderedDict

import pygame


def new_black_surface(size):
    """Opaque 32-bit black surface, square or (w, h) (black = no light under BLEND_RGB_ADD)."""
    if isinstance(size, int):
        size = (size, size)
    surface = pygame.Surface(size, 0, 32)
    if pygame.display.get_surface() is not None:
        surface = surface.convert()   # display format: fastest blits (needs a display)
    surface.fill((0, 0, 0))
    return surface


def radial_surface(size, profile):
    """
    Grey square whose brightness at distance r from the centre is profile(r) (0-1).

    Filled discs drawn from the outside in, each overwriting the middle of the
    previous one, give any radial profile in one pass (bake time only).
    """
    surface = new_black_surface(size)
    centre = size // 2
    last = 0
    for r in range(centre + 1, 0, -1):
        value = int(255 * max(0.0, min(1.0, profile(r))))
        # A zero after light (the inside of a ring) must still overwrite the middle
        if value or last:
            pygame.draw.circle(surface, (value, value, value), (centre, centre), r)
        last = value
    return surface


def light_colour(colour, white_mix, warm_white=(255, 240, 215)):
    """A colour blended toward warm white, so it reads as light, not paint."""
    return tuple(int(c + (w - c) * white_mix) for c, w in zip(colour[:3], warm_white))


def scaled_colour(colour, gain):
    """colour * gain, clamped (a BLEND_RGB_MULT fill colour)."""
    return tuple(max(0, min(255, int(c * gain))) for c in colour[:3])


# ========================================
# GLOW SPRITES (additive)
# ========================================

# Radial brightness profiles over t = r / radius (0 centre, 1 edge)
GLOW_PROFILES = {
    # Light mote: a small hot core inside a wide, soft bloom
    'mote': lambda t: 0.62 * math.exp(-(t / 0.22) ** 2) + 0.38 * max(0.0, 1.0 - t) ** 2.2,
    # Flare: broad Gaussian, for big blooms of light
    'flare': lambda t: math.exp(-(t / 0.42) ** 2) * max(0.0, 1.0 - t * t),
    # Bead: soft round light for strings of beads along a border (no hot core:
    # overlapping beads add up to an even line)
    'bead': lambda t: max(0.0, 1.0 - t * t) ** 2,
}


class _BuildBudget:
    """
    How many new sprites a cache may build this frame: at most `count`, and no
    more once `ms` of building has been spent (big sprites cost far more than
    small ones). A sprite that misses the budget is skipped for one frame.
    """

    def __init__(self, count, ms):
        self.count = count
        self.ms = ms
        self.left = count
        self.spent = 0.0

    def reset(self):
        self.left = self.count
        self.spent = 0.0

    def allows(self):
        # The first build of a frame always fits, so a frame always makes progress
        return self.left > 0 and (self.spent < self.ms or self.left == self.count)

    def charge(self, started):
        self.left -= 1
        self.spent += (time.perf_counter() - started) * 1000.0


class GlowSprites:
    """
    Additive light dots: opaque black squares holding a soft radial light.

    sprite(diameter, colour, level) -> Surface, or None when it isn't cached and
    this frame's build budget is spent (the caller skips that dot for one frame).
    Brightness is quantized to LEVELS steps and baked into the pixels, so fades
    stay on pygame's fast blit path. Draw with BLEND_RGB_ADD.
    """

    LEVELS = 12            # brightness steps (level 1..LEVELS)
    MAX_SPRITES = 2400     # bounded LRU (mostly tiny sprites)
    BUILDS_PER_FRAME = 24  # new sprites per frame at most (~20-200 us each)...
    BUILD_MS_PER_FRAME = 1.0   # ...and at most this much building per frame
    BASE_SIZE = 128        # grey base per profile, every sprite is scaled from it

    def __init__(self):
        self._sprites = OrderedDict()   # (diameter, colour, level, profile[, phase]) -> Surface
        self._bases = {}                # profile -> grey base
        self._shifted = OrderedDict()   # (diameter, profile, phase) -> grey, sub-pixel shifted
        self._budget = _BuildBudget(self.BUILDS_PER_FRAME, self.BUILD_MS_PER_FRAME)
        self.sprites_built = 0
        # Every base up front (~1-2 ms each), so no frame's budget pays for one
        for profile in GLOW_PROFILES:
            self._base(profile)

    def begin_frame(self):
        """Call once per rendered frame: resets the build budget."""
        self._budget.reset()

    def _base(self, profile):
        base = self._bases.get(profile)
        if base is None:
            shape = GLOW_PROFILES[profile]
            half = self.BASE_SIZE / 2.0
            base = radial_surface(self.BASE_SIZE, lambda r: shape(r / half))
            self._bases[profile] = base
        return base

    # Sub-pixel placement for slow-moving dots: copies shifted by quarter pixels down
    # and half pixels right. phase = quarter_y + 4 * half_x (0 = not shifted). A dot
    # rising 0.2 px a frame otherwise jumps a whole pixel every few frames - with
    # many of them, a visible crawl
    SUBPIXEL_PHASES = 8

    def sprite(self, diameter, colour, level, profile='mote', phase=0):
        key = (diameter, colour, level, profile, phase) if phase else (diameter, colour, level, profile)
        sprite = self._sprites.get(key)
        if sprite is not None:
            return sprite
        if not self._budget.allows():
            return None
        started = time.perf_counter()
        sprite = self._build_shifted(key) if phase else self._build(key)
        self._budget.charge(started)
        return sprite

    def _shifted_base(self, diameter, profile, phase):
        """
        The grey dot at this diameter, moved by phase's sub-pixel offset, on a
        (diameter + 1) square: drawn 4x larger at the offset, then smoothscaled down.
        """
        key = (diameter, profile, phase)
        grey = self._shifted.get(key)
        if grey is None:
            sub = 4
            big = pygame.transform.smoothscale(self._base(profile), (diameter * sub, diameter * sub))
            canvas = new_black_surface((diameter + 1) * sub)
            canvas.blit(big, ((phase // 4) * (sub // 2), phase % 4))
            grey = pygame.transform.smoothscale(canvas, (diameter + 1, diameter + 1))
            self._shifted[key] = grey
            if len(self._shifted) > 400:
                self._shifted.popitem(last=False)
        return grey

    def _build_shifted(self, key):
        diameter, colour, level, profile, phase = key
        sprite = self._shifted_base(diameter, profile, phase).copy()
        sprite.fill(scaled_colour(colour, level / float(self.LEVELS)), special_flags=pygame.BLEND_RGB_MULT)
        if pygame.display.get_surface() is not None:
            sprite = sprite.convert()
        self._sprites[key] = sprite
        self.sprites_built += 1
        if len(self._sprites) > self.MAX_SPRITES:
            for _ in range(self.MAX_SPRITES // 10):
                self._sprites.popitem(last=False)
        return sprite

    def prewarm(self, diameters, colour, levels=None, profile='mote'):
        """Build sprites now (at load), outside any frame's budget."""
        for diameter in diameters:
            for level in (levels or range(1, self.LEVELS + 1)):
                if (diameter, colour, level, profile) not in self._sprites:
                    self._build((diameter, colour, level, profile))

    def _build(self, key):
        diameter, colour, level, profile = key
        sprite = pygame.transform.smoothscale(self._base(profile), (diameter, diameter))
        sprite.fill(scaled_colour(colour, level / float(self.LEVELS)), special_flags=pygame.BLEND_RGB_MULT)
        if pygame.display.get_surface() is not None:
            sprite = sprite.convert()
        self._sprites[key] = sprite
        self.sprites_built += 1
        if len(self._sprites) > self.MAX_SPRITES:
            for _ in range(self.MAX_SPRITES // 10):
                self._sprites.popitem(last=False)   # oldest first
        return sprite

    def ladder(self, diameter, colour, profile='mote', phase=0):
        """
        [None, level 1 sprite, ..., level LEVELS sprite] for one size and colour
        (and sub-pixel phase), or None while any is still missing (built within the
        frame budget meanwhile). Lets a loop over many dots pick a sprite by index.
        """
        sprites = [None]
        complete = True
        for level in range(1, self.LEVELS + 1):
            sprite = self.sprite(diameter, colour, level, profile, phase)
            if sprite is None:
                complete = False
            sprites.append(sprite)
        return sprites if complete else None


class DarkSprites(GlowSprites):
    """
    Anti-light: soft dots that darken what is under them, drawn with
    BLEND_RGB_MULT (white = no change). The centre multiplies by `colour`
    (e.g. a dark purple) at full level; level 0 would change nothing.
    Same caching and build budget as GlowSprites.
    """

    MAX_SPRITES = 400

    def _build(self, key):
        diameter, colour, level, profile = key
        grey = pygame.transform.smoothscale(self._base(profile), (diameter, diameter))
        # How much each channel is taken away at the centre, scaled by the level
        depth = tuple(int((255 - c) * level / float(self.LEVELS)) for c in colour[:3])
        grey.fill(depth, special_flags=pygame.BLEND_RGB_MULT)
        sprite = pygame.Surface((diameter, diameter), 0, 32)
        sprite.fill((255, 255, 255))
        sprite.blit(grey, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        if pygame.display.get_surface() is not None:
            sprite = sprite.convert()
        self._sprites[key] = sprite
        self.sprites_built += 1
        if len(self._sprites) > self.MAX_SPRITES:
            for _ in range(self.MAX_SPRITES // 10):
                self._sprites.popitem(last=False)
        return sprite


# ========================================
# TINT SPRITES (normal blend)
# ========================================

class TintSprites:
    """
    Soft colour halos with per-pixel alpha (alpha (1 - t^2) ** softness), drawn
    with normal blending under the light, so a light keeps its hue on a bright
    map where pure additive light washes out toward white.
    """

    LEVELS = 12
    MAX_SPRITES = 1200
    BUILDS_PER_FRAME = 12
    BUILD_MS_PER_FRAME = 0.6
    BASE_SIZE = 64

    def __init__(self):
        self._sprites = OrderedDict()   # (diameter, colour, alpha level, softness) -> Surface
        self._bases = {}                # (colour, softness) -> full-alpha soft dot (~1 ms each)
        self._budget = _BuildBudget(self.BUILDS_PER_FRAME, self.BUILD_MS_PER_FRAME)
        self.sprites_built = 0

    def begin_frame(self):
        self._budget.reset()

    def prewarm(self, diameters, colour, alphas, softness=1.5):
        """Build sprites now (at load), outside any frame's budget."""
        for diameter in diameters:
            for alpha in alphas:
                level = int(alpha * self.LEVELS / 255.0 + 0.5)
                if level > 0 and (diameter, colour, level, softness) not in self._sprites:
                    self._build((diameter, colour, level, softness))

    def _base(self, colour, softness):
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

    def sprite(self, diameter, colour, alpha, softness=1.5):
        """alpha 0-255 is quantized to LEVELS steps."""
        level = int(alpha * self.LEVELS / 255.0 + 0.5)
        if level <= 0:
            return None
        key = (diameter, colour, level, softness)
        sprite = self._sprites.get(key)
        if sprite is not None:
            return sprite
        if not self._budget.allows():
            return None
        started = time.perf_counter()
        sprite = self._build(key)
        self._budget.charge(started)
        return sprite

    def alpha_ladder(self, diameter, colour, max_alpha, softness=1.5):
        """
        [None, ...LEVELS sprites from max_alpha / LEVELS up to max_alpha], or None
        while any is still missing. All the steps fall within the halo's own range:
        quantized to 255 / LEVELS, a halo that peaks at alpha 175 would only get 8
        steps, and each shows as a small pop on a big soft glow.
        """
        sprites = [None]
        for level in range(1, self.LEVELS + 1):
            alpha = int(max_alpha * level / float(self.LEVELS) + 0.5)
            key = (diameter, colour, ('alpha', alpha), softness)
            sprite = self._sprites.get(key)
            if sprite is None:
                if not self._budget.allows():
                    return None
                started = time.perf_counter()
                sprite = self._build(key)
                self._budget.charge(started)
            sprites.append(sprite)
        return sprites

    def _build(self, key):
        diameter, colour, level, softness = key
        sprite = pygame.transform.smoothscale(self._base(colour, softness), (diameter, diameter))
        # level: 1..LEVELS (alpha level * 255 / LEVELS), or ('alpha', exact alpha)
        a = level[1] if isinstance(level, tuple) else int(255 * level / self.LEVELS)
        if a < 255:
            sprite.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
        if pygame.display.get_surface() is not None:
            sprite = sprite.convert_alpha()
        self._sprites[key] = sprite
        self.sprites_built += 1
        if len(self._sprites) > self.MAX_SPRITES:
            for _ in range(self.MAX_SPRITES // 10):
                self._sprites.popitem(last=False)
        return sprite


# ========================================
# SOFT RING
# ========================================

class SoftRing:
    """
    A ring of light with a Gaussian cross-section, for shock waves.

    One grey ring is baked at REF_RADIUS (in the grey, colour-free), tinted once
    per colour, and scaled to the wanted radius per frame (only while a ring is
    on screen, at most a fraction of a second): the width scales with the radius,
    so a ring thickens as it grows, as a shock wave does.
    """

    REF_RADIUS = 96
    MAX_TINTED = 16
    # Cached frames (frame / tint_frame): brightness steps, how many are kept, and
    # how many may be built per frame (~0.1-0.3 ms each; a selection ring's pulses
    # fill their ~60 frames within the first pulse period)
    LEVELS = 24
    MAX_FRAMES = 96
    BUILDS_PER_FRAME = 4
    BUILD_MS_PER_FRAME = 0.5

    def __init__(self, width=0.16):
        self.width = width                       # ring half-width, as a share of the radius
        self._grey = None
        self._tinted = OrderedDict()             # colour -> tinted ring at REF_RADIUS
        self._halos = OrderedDict()              # colour -> normal-blend colour ring (alpha)
        self._frames = OrderedDict()             # (kind, radius, colour, level) -> scaled ring
        self._budget = _BuildBudget(self.BUILDS_PER_FRAME, self.BUILD_MS_PER_FRAME)
        self.frames_built = 0

    def begin_frame(self):
        """Call once per rendered frame when using frame() / tint_frame()."""
        self._budget.reset()

    def _grey_ring(self):
        if self._grey is None:
            ref = self.REF_RADIUS
            sigma = self.width * ref
            size = 2 * int(ref + 3 * sigma) + 2
            self._grey = radial_surface(size, lambda r: math.exp(-((r - ref) / sigma) ** 2))
        return self._grey

    def prewarm(self):
        self._grey_ring()

    def _tinted_ring(self, colour):
        ring = self._tinted.get(colour)
        if ring is None:
            ring = self._grey_ring().copy()
            ring.fill(colour, special_flags=pygame.BLEND_RGB_MULT)
            self._tinted[colour] = ring
            if len(self._tinted) > self.MAX_TINTED:
                self._tinted.popitem(last=False)
        else:
            self._tinted.move_to_end(colour)
        return ring

    def reach(self, radius):
        """Half the size of the ring's square at this radius (for culling)."""
        return int(radius * (1.0 + 3 * self.width)) + 2

    def draw(self, screen, x, y, radius, colour, brightness):
        """Add a ring of this radius (px) at brightness 0-1 to the screen."""
        if radius < 2 or brightness <= 0.02:
            return
        ring = self._tinted_ring(colour)
        size = max(2, int(ring.get_width() * radius / float(self.REF_RADIUS)))
        scaled = pygame.transform.scale(ring, (size, size))
        if brightness < 0.99:
            v = int(255 * brightness)
            scaled.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
        half = size // 2
        screen.blit(scaled, (x - half, y - half), special_flags=pygame.BLEND_RGB_ADD)

    def _halo_ring(self, colour):
        """The ring as a colour with per-pixel alpha (a wider profile), baked per colour."""
        ring = self._halos.get(colour)
        if ring is None:
            ref = self.REF_RADIUS
            sigma = self.width * ref * 1.4
            size = 2 * int(ref + 3 * self.width * ref) + 2
            centre = size // 2
            ring = pygame.Surface((size, size), pygame.SRCALPHA)
            for r in range(centre + 1, 0, -1):
                a = int(255 * math.exp(-((r - ref) / sigma) ** 2))
                pygame.draw.circle(ring, (colour[0], colour[1], colour[2], a), (centre, centre), r)
            if pygame.display.get_surface() is not None:
                ring = ring.convert_alpha()
            self._halos[colour] = ring
            if len(self._halos) > self.MAX_TINTED:
                self._halos.popitem(last=False)
        else:
            self._halos.move_to_end(colour)
        return ring

    def draw_tint(self, screen, x, y, radius, colour, alpha):
        """
        The normal-blend colour under a ring (alpha 0-255): keeps the ring's hue on
        a bright map, where the additive ring alone turns white.
        """
        if radius < 2 or alpha < 4:
            return
        ring = self._halo_ring(colour)
        size = max(2, int(ring.get_width() * radius / float(self.REF_RADIUS)))
        scaled = pygame.transform.scale(ring, (size, size))
        if alpha < 252:
            scaled.fill((255, 255, 255, int(alpha)), special_flags=pygame.BLEND_RGBA_MULT)
        half = size // 2
        screen.blit(scaled, (x - half, y - half))

    def frame(self, radius, colour, level):
        """
        The additive ring at this radius (whole px) and brightness level
        (1..LEVELS), cached: for rings drawn every frame, such as a selection
        ring and its pulses. A pulse whose brightness follows its radius uses
        one frame per radius. None when not cached and this frame's build
        budget is spent. Blit with BLEND_RGB_ADD, centred.
        """
        if radius < 2 or level <= 0:
            return None
        return self._cached(('light', int(radius), colour, min(level, self.LEVELS)))

    def tint_frame(self, radius, colour, alpha):
        """The normal-blend colour ring (alpha 0-255, in LEVELS steps), cached like frame()."""
        level = int(alpha * self.LEVELS / 255.0 + 0.5)
        if radius < 2 or level <= 0:
            return None
        return self._cached(('tint', int(radius), colour, min(level, self.LEVELS)))

    def _cached(self, key):
        surface = self._frames.get(key)
        if surface is not None:
            self._frames.move_to_end(key)
            return surface
        if not self._budget.allows():
            return None
        started = time.perf_counter()
        kind, radius, colour, level = key
        if kind == 'light':
            ring = self._tinted_ring(colour)
        else:
            ring = self._halo_ring(colour)
        size = max(2, int(ring.get_width() * radius / float(self.REF_RADIUS)) | 1)
        surface = pygame.transform.smoothscale(ring, (size, size))
        if kind == 'light':
            v = int(255 * level / float(self.LEVELS))
            if v < 255:
                surface.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
            if pygame.display.get_surface() is not None:
                surface = surface.convert()
        else:
            a = int(255 * level / float(self.LEVELS))
            if a < 255:
                surface.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
            if pygame.display.get_surface() is not None:
                surface = surface.convert_alpha()
        self._frames[key] = surface
        self.frames_built += 1
        if len(self._frames) > self.MAX_FRAMES:
            self._frames.popitem(last=False)
        self._budget.charge(started)
        return surface


# ========================================
# VIGNETTE
# ========================================

def vignette_surface(size, colour, centre_alpha, edge_alpha, inner=0.3, outer=1.3):
    """
    A colour wash that is faint in the middle and strong toward the edges
    (per-pixel alpha), for a whole-map mood such as the Vow of Silence.

    Baked once per size: concentric ellipses at 1/8 resolution, smoothscaled up
    (~5-10 ms). Draw with set_alpha() for a global fade or shimmer - no
    per-frame fill.

    Args:
        inner / outer: where the alpha starts rising / reaches edge_alpha, as a
            share of the half-size (1.0 = the middle of an edge; corners ~1.41)
    """
    width, height = size
    small_w, small_h = max(8, width // 8), max(8, height // 8)
    small = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
    small.fill((colour[0], colour[1], colour[2], edge_alpha))
    cx, cy = small_w / 2.0, small_h / 2.0
    steps = 120
    reach = 1.45
    for k in range(steps, 0, -1):
        s = reach * k / steps
        t = max(0.0, min(1.0, (s - inner) / (outer - inner)))
        alpha = int(centre_alpha + (edge_alpha - centre_alpha) * t * t * (3.0 - 2.0 * t))
        rect = pygame.Rect(0, 0, max(1, int(2 * s * cx)), max(1, int(2 * s * cy)))
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(small, (colour[0], colour[1], colour[2], alpha), rect)
    surface = pygame.transform.smoothscale(small, (width, height))
    if pygame.display.get_surface() is not None:
        surface = surface.convert_alpha()
    return surface


# ========================================
# TERRITORY RASTER
# ========================================

class TerritoryRaster:
    """
    Which territory each world pixel belongs to: a surface with every territory
    polygon filled in its own colour. at(x, y) is one get_at() instead of a
    point-in-polygon test over hundreds of vertices.

    Built once per map scale (~5-15 ms); about 2 MB at 1600x900.
    """

    def __init__(self, polygons):
        """polygons: {territory: [(x, y), ...]} in world coordinates."""
        xs = [p[0] for poly in polygons.values() if poly for p in poly]
        ys = [p[1] for poly in polygons.values() if poly for p in poly]
        self.width = int(max(xs)) + 2 if xs else 1
        self.height = int(max(ys)) + 2 if ys else 1
        self.surface = pygame.Surface((self.width, self.height), 0, 32)
        self.surface.fill((0, 0, 0))
        self._names = [None]
        self._ids = {}
        for territory in sorted(polygons):
            polygon = polygons[territory]
            if not polygon or len(polygon) < 3:
                continue
            index = len(self._names)
            self._names.append(territory)
            self._ids[territory] = index
            pygame.draw.polygon(self.surface, self._colour(index), polygon)
        self._map_rgb = self.surface.map_rgb

    @staticmethod
    def _colour(index):
        return (index & 0xFF, (index >> 8) & 0xFF, 0x55)

    def at(self, x, y):
        """The territory at world point (x, y), or None."""
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        r, g, b, _ = self.surface.get_at((x, y))
        if b != 0x55:
            return None
        return self._names[r | (g << 8)] if (r | (g << 8)) < len(self._names) else None

    def inside(self, territory, x, y):
        return self.at(x, y) == territory


# ========================================
# BEAD CHAINS (points along a border)
# ========================================

def smooth_outline(polygon, min_step=2.0):
    """
    The polygon without its pixel staircase: points closer than min_step to the
    last kept one are dropped, then one round of Chaikin corner cutting.

    Scaled territory polygons are rounded to whole pixels, so their edges zigzag;
    measured along the zigzag, arc length grows unevenly, and beads spaced by arc
    length would bunch up where it does (blotches along the border).
    """
    points = []
    for x, y in polygon:
        if not points or math.hypot(x - points[-1][0], y - points[-1][1]) >= min_step:
            points.append((float(x), float(y)))
    if len(points) > 3 and math.hypot(points[0][0] - points[-1][0],
                                      points[0][1] - points[-1][1]) < min_step:
        points.pop()
    if len(points) < 3:
        return [(float(x), float(y)) for x, y in polygon]
    # Long edges split into short ones, so corner cutting stays local (a quarter of
    # an edge is cut off each corner)
    longest = 2.0 * min_step
    split = []
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        pieces = max(1, int(math.hypot(x2 - x1, y2 - y1) / longest))
        for k in range(pieces):
            split.append((x1 + (x2 - x1) * k / pieces, y1 + (y2 - y1) * k / pieces))
    points = split
    smoothed = []
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        smoothed.append((0.75 * x1 + 0.25 * x2, 0.75 * y1 + 0.25 * y2))
        smoothed.append((0.25 * x1 + 0.75 * x2, 0.25 * y1 + 0.75 * y2))
    return smoothed


def bead_chain(polygon, spacing, inset=0.0):
    """
    Points every `spacing` world px along a closed polygon, each moved `inset`
    world px toward the inside, as [(x, y, arc length, outward nx, outward ny), ...].

    The outline is smoothed first (smooth_outline) and normals are taken over a
    few spacings either side, so the rounded vertices of a scaled polygon don't
    make the beads bunch up or wobble.
    """
    points = smooth_outline(polygon) if len(polygon) >= 3 else []
    if len(points) < 3:
        return []
    # Orientation (shoelace; y down): outward normal side
    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        area += x1 * y2 - x2 * y1
    sign = 1.0 if area > 0 else -1.0

    # Resample by arc length
    samples = []
    carry = 0.0
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        seg = math.hypot(x2 - x1, y2 - y1)
        if seg <= 1e-9:
            continue
        d = carry
        while d < seg:
            t = d / seg
            samples.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, total + d))
            d += spacing
        carry = d - seg
        total += seg
    count = len(samples)
    if count < 3:
        return []

    # Normals over ~8 world px either side: a wiggly border's short-range normals
    # swing about, and beads moved inward along them bunch up and spread out
    window = max(1, int(round(8.0 / max(spacing, 0.1))))
    chain = []
    for i, (x, y, s) in enumerate(samples):
        ax, ay, _ = samples[(i - window) % count]
        bx, by, _ = samples[(i + window) % count]
        tx, ty = bx - ax, by - ay
        length = math.hypot(tx, ty) or 1.0
        # Outward normal: the tangent turned a quarter (side by orientation)
        nx, ny = sign * ty / length, -sign * tx / length
        chain.append((x - nx * inset, y - ny * inset, s, nx, ny))
    return chain


# ========================================
# PATHS (points along an open line)
# ========================================

def path_lengths(points):
    """Arc length at each point of an open polyline: [0.0, ..., total]."""
    lengths = [0.0]
    for i in range(1, len(points)):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        lengths.append(lengths[-1] + math.hypot(x2 - x1, y2 - y1))
    return lengths


def path_point(points, lengths, s):
    """
    The point at arc length s along an open polyline (lengths from
    path_lengths), clamped to its ends, as (x, y, unit tangent x, y).
    """
    n = len(points)
    if n < 2:
        x, y = points[0] if points else (0.0, 0.0)
        return x, y, 1.0, 0.0
    s = max(0.0, min(lengths[-1], s))
    # Binary search for the segment holding s
    lo, hi = 0, n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if lengths[mid] <= s:
            lo = mid
        else:
            hi = mid
    x1, y1 = points[lo]
    x2, y2 = points[hi]
    seg = lengths[hi] - lengths[lo]
    if seg <= 1e-9:
        return x1, y1, 1.0, 0.0
    t = (s - lengths[lo]) / seg
    return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, (x2 - x1) / seg, (y2 - y1) / seg


def path_beads(points, spacing, start=0.0, stop=None):
    """
    Points every `spacing` along an open polyline, from arc length `start` to
    `stop` (default: its end), as [(x, y, arc length), ...]. The open-path
    sibling of bead_chain, for arrows and other routes.
    """
    if len(points) < 2 or spacing <= 0:
        return []
    lengths = path_lengths(points)
    stop = lengths[-1] if stop is None else min(stop, lengths[-1])
    beads = []
    i = 1
    s = max(0.0, start)
    while s <= stop + 1e-9:
        # Walk forward to the segment holding s (s only grows)
        while i < len(points) - 1 and lengths[i] < s:
            i += 1
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        seg = lengths[i] - lengths[i - 1]
        t = (s - lengths[i - 1]) / seg if seg > 1e-9 else 0.0
        beads.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, s))
        s += spacing
    return beads


# ========================================
# GLOW FRAME (UI highlights)
# ========================================

class GlowFrame:
    """
    Soft light hugging the outside of a shape - a rounded rectangle, a circle or a
    sprite's silhouette (an ornate button) - for UI highlights. Additive, on
    black, and nothing inside the shape, so the control itself is untouched: a
    crisp line of light on the outline and a halo fading outward.

    Baked once per shape and size in grey (rings by distance from the outline, the
    shape grown a pixel at a time), tinted per brightness level and cached, so a
    breathing highlight is one cached blit a frame.

    frame(size, colour, level, ...) -> (surface, pad): blit it at the shape's
    top-left minus (pad, pad) with BLEND_RGB_ADD.
    """

    LEVELS = 12
    MAX_GREYS = 32
    MAX_FRAMES = 192

    def __init__(self, reach=9):
        self.reach = max(3, int(reach))
        self._greys = OrderedDict()    # (shape key, w, h) -> grey glow
        self._frames = OrderedDict()   # (grey key, colour, level) -> tinted glow
        self.built = 0

    def frame(self, size, colour, level, shape='rect', corner=4, sprite=None, sprite_key=None):
        """
        The glow round a shape of this size at brightness level 1..LEVELS.

        Args:
            shape: 'rect' (rounded by corner px), 'circle' (inscribed in size) or
                'sprite' (the silhouette of sprite, alpha > 100; sprite_key names it
                in the cache)
        """
        w, h = max(1, int(size[0])), max(1, int(size[1]))
        grey_key = (shape, w, h, corner if shape == 'rect' else sprite_key)
        level = max(1, min(self.LEVELS, int(level)))
        key = (grey_key, colour, level)
        tinted = self._frames.get(key)
        if tinted is None:
            grey = self._grey(grey_key, w, h, shape, corner, sprite)
            tinted = grey.copy()
            tinted.fill(scaled_colour(colour, level / float(self.LEVELS)), special_flags=pygame.BLEND_RGB_MULT)
            if pygame.display.get_surface() is not None:
                tinted = tinted.convert()
            self._frames[key] = tinted
            self.built += 1
            if len(self._frames) > self.MAX_FRAMES:
                self._frames.popitem(last=False)
        else:
            self._frames.move_to_end(key)
        return tinted, self.reach + 2

    def _grey(self, key, w, h, shape, corner, sprite):
        grey = self._greys.get(key)
        if grey is not None:
            self._greys.move_to_end(key)
            return grey
        pad = self.reach + 2
        size = (w + 2 * pad, h + 2 * pad)
        silhouette = pygame.Surface(size, pygame.SRCALPHA)
        if shape == 'circle':
            pygame.draw.circle(silhouette, (255, 255, 255, 255), (pad + w // 2, pad + h // 2), min(w, h) // 2)
        elif shape == 'sprite' and sprite is not None:
            silhouette.blit(sprite, (pad, pad))
        else:
            pygame.draw.rect(silhouette, (255, 255, 255, 255), pygame.Rect(pad, pad, w, h),
                             border_radius=corner)
        inside = pygame.mask.from_surface(silhouette, 100)
        # Rings by distance from the outline: the shape grown 1 px a step (8
        # neighbours), so a rectangle, a circle and a pointed button all get the
        # same halo however big they are
        rings = [inside]
        for _ in range(self.reach):
            grown = rings[-1].copy()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                grown.draw(rings[-1], (dx, dy))
            rings.append(grown)
        grey = new_black_surface(size)
        # Outermost first, each nearer ring drawn over it: a crisp line of light on
        # the outline (2 px), then a halo fading out over the reach
        for t in range(self.reach, 0, -1):
            if t <= 2:
                v = 255
            else:
                v = int(200 * (1.0 - (t - 2) / float(self.reach - 1)) ** 1.5)
            rings[t].to_surface(grey, setcolor=(v, v, v), unsetcolor=None)
        # Nothing over the control itself
        inside.to_surface(grey, setcolor=(0, 0, 0), unsetcolor=None)
        self._greys[key] = grey
        if len(self._greys) > self.MAX_GREYS:
            self._greys.popitem(last=False)
        return grey


# ========================================
# RISING MOTES (screen and panel effects)
# ========================================

class RisingMotes:
    """
    Motes of light that rise, sway a little and fade, for effects drawn in screen
    px rather than on the map: the turn banner, the Master Negotiator glow, the
    Ruthless Ingenuity tech tree.

    Closed form from a clock, as the hero fireflies: each life a mote starts at a
    new point, spawn(a, b, index) -> (x, y), from two hashed numbers a, b in 0-1.

    Args:
        style: count, life (min, max) s, rise / sway px, size (min, max) diameter
            px, optional tint (alpha of a normal-blend halo under each mote, for a
            bright background) and tint_size (halo / mote diameter)
        seed: makes the table the same every run
        scale: multiplies the px sizes (screen or UI scale)
    """

    def __init__(self, style, seed, scale=1.0):
        rng = random.Random(seed)
        lo, hi = style['size']
        tint_size = style.get('tint_size', 1.6)
        self.rise = style['rise'] * scale
        self.sway = style['sway'] * scale
        self.tint_alpha = style.get('tint', 0)
        # Per mote: (1 / life, offset, diameter, halo diameter, hash salt, sway phase)
        self.motes = []
        for _ in range(style['count']):
            size = rng.uniform(lo, hi) * scale
            self.motes.append((1.0 / rng.uniform(*style['life']), rng.random(), max(2, int(size) & ~1),
                               max(4, int(size * tint_size) & ~3), rng.getrandbits(24),
                               rng.uniform(0.0, 2.0 * math.pi)))

    def draw(self, screen, glow, colour, clock, strength, spawn, tint=None, raw_colour=None):
        """
        Draw the motes at this clock (s) and strength (0-1): halos (with tint, in
        raw_colour) under the light. Sprites still being built within the frame
        budget are skipped for a frame.
        """
        if strength <= 0.02:
            return
        steps = GlowSprites.LEVELS
        use_tint = tint is not None and self.tint_alpha > 0 and raw_colour is not None
        sin, pi = math.sin, math.pi
        halos = []
        seq = []
        for index, (inv_life, offset, diameter, halo_d, salt, sway_phase) in enumerate(self.motes):
            u = clock * inv_life + offset
            cycle = int(u)
            age = u - cycle
            env = sin(pi * age)
            env *= env * strength
            level = int(steps * env + 0.5)
            if level <= 0:
                continue
            h = ((cycle * 73856093) ^ salt) & 0xFFFFFFFF
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
            x, y = spawn((h & 0xFFFF) / 65536.0, (h >> 16) / 65536.0, index)
            x = int(x + self.sway * sin(age * 5.0 + sway_phase))
            y = int(y - self.rise * age)
            if use_tint:
                halo = tint.sprite(halo_d, raw_colour, self.tint_alpha * env)
                if halo is not None:
                    halos.append((halo, (x - (halo_d >> 1), y - (halo_d >> 1))))
            sprite = glow.sprite(diameter, colour, min(steps, level))
            if sprite is not None:
                seq.append((sprite, (x - (diameter >> 1), y - (diameter >> 1)), None, pygame.BLEND_RGB_ADD))
        if halos:
            screen.blits(halos, doreturn=False)
        if seq:
            screen.blits(seq, doreturn=False)
