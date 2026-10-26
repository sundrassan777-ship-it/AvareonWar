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
    TerritoryRaster       territory id per world pixel: inside tests in O(1)
    bead_chain            evenly spaced points along a territory border

Users: production_glow_effect.py (production rays), hero_fx_effect.py (hero
ability effects).
"""

import math
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
        self._sprites = OrderedDict()   # (diameter, colour, level, profile) -> Surface
        self._bases = {}                # profile -> grey base
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

    def sprite(self, diameter, colour, level, profile='mote'):
        key = (diameter, colour, level, profile)
        sprite = self._sprites.get(key)
        if sprite is not None:
            return sprite
        if not self._budget.allows():
            return None
        started = time.perf_counter()
        sprite = self._build(key)
        self._budget.charge(started)
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

    def ladder(self, diameter, colour, profile='mote'):
        """
        [None, level 1 sprite, ..., level LEVELS sprite] for one size and colour, or
        None while any is still missing (built within the frame budget meanwhile).
        Lets a loop over many dots pick a sprite by index.
        """
        sprites = [None]
        complete = True
        for level in range(1, self.LEVELS + 1):
            sprite = self.sprite(diameter, colour, level, profile)
            if sprite is None:
                complete = False
            sprites.append(sprite)
        return sprites if complete else None


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
        self._bases = {}                # (colour, softness) -> full-alpha soft dot
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

    def _build(self, key):
        diameter, colour, level, softness = key
        sprite = pygame.transform.smoothscale(self._base(colour, softness), (diameter, diameter))
        if level < self.LEVELS:
            a = int(255 * level / self.LEVELS)
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

    def __init__(self, width=0.16):
        self.width = width                       # ring half-width, as a share of the radius
        self._grey = None
        self._tinted = OrderedDict()             # colour -> tinted ring at REF_RADIUS
        self._halos = OrderedDict()              # colour -> normal-blend colour ring (alpha)

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
