# -*- coding: utf-8 -*-
"""
Banner Effects

The army banners' own effects (banner FX pass, 2026-10-31; the look in
banner_fx_style.py):

BannerWave    every banner on the map waving in a steady breeze. Each flag
              picture is baked once per size step into a seamless loop of frames:
              the crossbar and the pole kept still, the cloth's rows shifted
              sideways by quarter pixels and lit by their slope. Drawing a banner
              is then ONE blit, as before the wave - the frame picked from the
              clock and the banner's world position (one breeze over the map, so a
              marching banner keeps its rhythm from its territory to the next).
              The loops are kept for the process and built on the loading screen
              (MapRenderer.prewarm_banners); one still missing in play is built a
              pose at a time within a per-frame budget, meanwhile the nearest built
              pose or size is drawn - or the plain flag, never nothing.
BannerMotes   motes of light in the selection green rising from the selected
              banner's pole base to its top, from the clock (nothing stored per
              mote), placed to quarter pixels so the slow rise doesn't crawl.

Flag pictures are known by their art name (register_art, called by the loader in
main.py): campaign missions move the same pictures between players
(army_flag_icons), so the frames follow the picture, not the player.
"""

import math
import random
import time
import weakref

import pygame

from config.constants import ARMY_CIRCLE_RADIUS, ARMY_FLAG_HEIGHT_RATIO
from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, TintSprites

ADD = pygame.BLEND_RGB_ADD
MULT = pygame.BLEND_RGB_MULT

SIZE_STEP = 5                 # banner heights are rounded to this (px), as the plain flags were
SUB = 4                       # cloth rows shift by 1 / SUB px
UI_SCALE_RANGE = (1.0, 1.5)   # CameraHandler.get_ui_scale_factor at min / max zoom
LAYOUT_HEIGHT = 120           # px: a flag picture's parts are measured at this height

_ART_NAMES = weakref.WeakKeyDictionary()   # flag Surface -> art key (name, width, height)
_LAYOUTS = {}                 # art key -> _Layout, or None (no cloth found: drawn plain)
_LOOPS = {}                   # (art key, wave signature) -> {size step: _Loop}


def register_art(surface, name):
    """
    Name a loaded flag picture (the loader in main.py), so its frames are found
    for whichever player shows it. Its size is part of the key: the neutral flag
    is scaled to each tier's size.
    """
    if surface is not None:
        _ART_NAMES[surface] = (name,) + surface.get_size()


def art_key(surface):
    """A flag picture's art key, or None if it wasn't registered (drawn plain)."""
    return _ART_NAMES.get(surface)


def size_step(height):
    """The size step a banner `height` px tall is drawn at."""
    return max(SIZE_STEP, int(round(height / float(SIZE_STEP))) * SIZE_STEP)


def size_steps():
    """Every size step the zoom range draws: the banners' heights, 50..75 px."""
    lo, hi = UI_SCALE_RANGE
    # Marching banners are int(int(radius * ui_scale) * ratio) px tall: a little lower
    low = min(int(int(ARMY_CIRCLE_RADIUS * lo) * ARMY_FLAG_HEIGHT_RATIO),
              ARMY_CIRCLE_RADIUS * lo * ARMY_FLAG_HEIGHT_RATIO)
    high = ARMY_CIRCLE_RADIUS * hi * ARMY_FLAG_HEIGHT_RATIO
    return list(range(size_step(low), size_step(high) + 1, SIZE_STEP))


def cache_bytes():
    """Pixels held by the built frames (for measuring)."""
    total = 0
    for by_step in _LOOPS.values():
        for loop in by_step.values():
            total += loop.built * loop.frame_width * loop.height * 4
    return total


def clear_cache():
    """Forget every built loop and layout (tests)."""
    _LOOPS.clear()
    _LAYOUTS.clear()


# ========================================
# LAYOUT (where a flag picture's parts are)
# ========================================

class _Layout:
    """
    Where a flag picture's parts are, as shares of its height / width: the
    crossbar above `hang` (still, in front of the cloth), the cloth from `hang`
    down (swaying fully from `cloth_end`, where its tails end), and the strip of
    pole from `pole_top` down between `pole_left` and `pole_right` (still,
    behind the cloth: it shows below it and in a swallow-tail's notch).
    """

    __slots__ = ('hang', 'cloth_end', 'pole_top', 'pole_left', 'pole_right')


def _row_spans(mask, width, y):
    """The runs of opaque pixels in one row of a mask: [(first x, last x), ...]."""
    spans = []
    start = None
    get = mask.get_at
    for x in range(width):
        if get((x, y)):
            if start is None:
                start = x
        elif start is not None:
            spans.append((start, x - 1))
            start = None
    if start is not None:
        spans.append((start, width - 1))
    return spans


def measure_layout(source):
    """A flag picture's _Layout (measured at LAYOUT_HEIGHT), or None when it has no cloth."""
    sw, sh = source.get_size()
    if sw < 2 or sh < 2:
        return None
    height = LAYOUT_HEIGHT
    width = max(8, int(round(sw * height / float(sh))))
    mask = pygame.mask.from_surface(pygame.transform.smoothscale(source, (width, height)), 127)
    rows = [_row_spans(mask, width, y) for y in range(height)]
    opaque = [y for y in range(height) if rows[y]]
    if len(opaque) < 8:
        return None
    top, bottom = opaque[0], opaque[-1]
    tall = bottom - top + 1
    extent = [(spans[-1][1] - spans[0][0] + 1) if spans else 0 for spans in rows]
    middle = sorted(extent[y] for y in range(top + int(tall * 0.4), top + int(tall * 0.7) + 1))
    cloth_width = middle[len(middle) // 2]

    # The crossbar and its finials reach out past the cloth: still down to their last row
    hang = top
    for y in range(top, top + int(tall * 0.25)):
        if extent[y] > cloth_width + 2:
            hang = y + 1

    # The pole: the narrow run at the bottom...
    narrow = max(3, int(cloth_width * 0.12))
    y = bottom
    left, right = width, -1
    while y > hang and rows[y] and extent[y] <= narrow:
        left = min(left, rows[y][0][0])
        right = max(right, rows[y][-1][1])
        y -= 1
    if right < 0:
        # ...or, when nothing hangs below the cloth, a narrow run between a
        # swallow-tail's tails, near the middle
        centre = sum((rows[y][0][0] + rows[y][-1][1]) / 2.0 for y in opaque) / len(opaque)
        between = [s for y in range(top + tall // 2, bottom + 1) for i, s in enumerate(rows[y])
                   if 0 < i < len(rows[y]) - 1 and s[1] - s[0] + 1 <= narrow
                   and abs((s[0] + s[1]) / 2.0 - centre) <= cloth_width * 0.15]
        if between:
            left = min(s[0] for s in between)
            right = max(s[1] for s in between)
    if right < 0:
        pole_top, left, right = height, 0, -1      # no pole to keep still
    else:
        left, right = left - 1, right + 1          # its soft edge

        def alone(spans):
            """The pole shows on its own in this row (between the tails, or below them)."""
            inside = [s for s in spans if s[0] >= left and s[1] <= right]
            return bool(inside) and all(s in inside or s[1] < left or s[0] > right for s in spans)

        # The lowest rows where it shows on its own: below the cloth and up through
        # a swallow-tail's notch
        y = bottom
        while y > hang and not alone(rows[y]):
            y -= 1
        while y > hang and alone(rows[y]):
            y -= 1
        pole_top = y + 1

    # The cloth ends after the last row with anything besides the pole
    cloth_end = hang + 1
    for y in range(bottom, hang, -1):
        if any(s[0] < left or s[1] > right for s in rows[y]):
            cloth_end = y + 1
            break

    layout = _Layout()
    layout.hang = hang / float(height)
    layout.cloth_end = cloth_end / float(height)
    layout.pole_top = min(pole_top, cloth_end) / float(height)
    layout.pole_left = max(0, left) / float(width)
    layout.pole_right = max(0, right + 1) / float(width)
    return layout


# ========================================
# LOOP (one flag picture's frames at one size)
# ========================================

class _Loop:
    """
    One flag picture's waving loop at one size step: frames[i] (None until
    built) are frame_width x height, the pole base at (anchor, height). The
    layers they are built from are dropped once every frame is built.
    """

    def __init__(self, source, layout, height, wave, lean):
        sw, sh = source.get_size()
        self.height = h = height
        self.width = w = max(4, int(round(sw * h / float(sh))))
        swing = (abs(lean) + wave['amplitude'] * (1.0 + abs(wave['flutter']))) * w
        self.pad = pad = int(math.ceil(swing)) + 1
        self.frame_width = fw = w + 2 * pad
        self.anchor = int(round(pad + w / 2.0))
        count = wave['frames']
        self.frames = [None] * count
        self.built = 0

        # The layers, SUB times as wide as the banner
        w4 = w * SUB
        art = pygame.transform.smoothscale(source, (w4, h))
        hang = min(h - 1, int(round(layout.hang * h)))
        cloth_end = max(hang + 1, min(h, int(round(layout.cloth_end * h))))
        pole_top = int(round(layout.pole_top * h))
        pole_left = int(math.floor(layout.pole_left * w4))
        pole_right = int(math.ceil(layout.pole_right * w4))
        x0 = pad * SUB
        fw4 = fw * SUB
        # Still parts, scaled to the frame once: the crossbar (drawn over the cloth)
        # and the strip of pole in a swallow-tail's notch and below the cloth (drawn
        # under it). Everything else moves, the soft edges of the tails' tips and a
        # glow round the flag included (below the cloth they move with the tails)
        bar = pygame.Surface((fw4, h), pygame.SRCALPHA)
        bar.blit(art, (x0, 0), (0, 0, w4, hang))
        pole = pygame.Surface((fw4, h), pygame.SRCALPHA)
        strip = None
        if pole_right > pole_left and pole_top < h:
            strip = (pole_left, pole_top, pole_right - pole_left, h - pole_top)
            pole.blit(art, (x0 + pole_left, pole_top), strip)
        self._bar = pygame.transform.smoothscale(bar, (fw, h))
        self._pole = pygame.transform.smoothscale(pole, (fw, h))
        cloth = art.copy()
        cloth.fill((0, 0, 0, 0), (0, 0, w4, hang))
        if strip is not None:
            cloth.fill((0, 0, 0, 0), strip)
        self._cloth = cloth
        self._rows = list(range(hang, h))

        # Every pose's row offsets (in 1 / SUB px) and fold light (row brightness)
        two_pi = 2.0 * math.pi
        amplitude, flutter = wave['amplitude'], wave['flutter']
        ripples, flutter_ripples = wave['ripples'], wave['flutter_ripples']
        stiffness = wave['stiffness']
        length = float(cloth_end - hang)

        def sway(row, phase):
            u = min(1.0, max(0.0, (row + 0.5 - hang) / length))
            return w * u ** stiffness * (lean + amplitude * (
                math.sin(phase - two_pi * ripples * u)
                + flutter * math.sin(2.0 * phase - two_pi * flutter_ripples * u)))

        offsets = []
        slopes = []
        for i in range(count):
            phase = two_pi * i / count
            offsets.append([int(round(sway(row, phase) * SUB)) for row in self._rows])
            slopes.append([(sway(row + 1, phase) - sway(row - 1, phase)) / 2.0 for row in self._rows])
        steepest = max(abs(s) for pose in slopes for s in pose) or 1.0
        shade = wave['shade']
        self._offsets = offsets
        self._shades = [[1.0 + shade * s / steepest for s in pose] for pose in slopes]
        # Where the crossfade to the next pose starts: the first row that moves half a
        # pixel or more from one pose to the next. Above it rows move a quarter pixel
        # at most (smooth as they are), so only the lower part pays for the faded blit
        self.fade_top = h
        for k, row in enumerate(self._rows):
            if any(abs(offsets[(i + 1) % count][k] - offsets[i][k]) >= SUB // 2 for i in range(count)):
                self.fade_top = row
                break

    def build(self, index):
        """Build pose `index` (~0.2-0.4 ms) and return it."""
        h = self.height
        fw = self.frame_width
        w4 = self.width * SUB
        x0 = self.pad * SUB
        cloth = self._cloth
        canvas = pygame.Surface((fw * SUB, h), pygame.SRCALPHA)
        canvas.blits([(cloth, (x0 + offset, row), (0, row, w4, 1))
                      for row, offset in zip(self._rows, self._offsets[index])], doreturn=False)
        cloth_frame = pygame.transform.smoothscale(canvas, (fw, h))
        # Fold light: rows darker or lighter by their slope (lighter = the row plus a
        # share of itself, so the colours keep their hue)
        for row, gain in zip(self._rows, self._shades[index]):
            if gain < 0.995:
                g = int(255 * gain + 0.5)
                cloth_frame.fill((g, g, g), (0, row, fw, 1), special_flags=MULT)
            elif gain > 1.005:
                g = int(255 * (gain - 1.0) + 0.5)
                lit = cloth_frame.subsurface((0, row, fw, 1)).copy()
                lit.fill((g, g, g), special_flags=MULT)
                cloth_frame.blit(lit, (0, row), special_flags=ADD)
        frame = self._pole.copy()
        frame.blit(cloth_frame, (0, 0))
        frame.blit(self._bar, (0, 0))
        if pygame.display.get_surface() is not None:
            frame = frame.convert_alpha()
        if self.frames[index] is None:
            self.built += 1
        self.frames[index] = frame
        if self.built == len(self.frames):
            # Complete: the layers are no longer needed
            self._cloth = self._bar = self._pole = None
            self._offsets = self._shades = None
        return frame

    def nearest(self, index):
        """The built pose nearest `index` round the loop, or None."""
        count = len(self.frames)
        for step in range(1, count // 2 + 1):
            for candidate in ((index + step) % count, (index - step) % count):
                frame = self.frames[candidate]
                if frame is not None:
                    return frame
        return None


# ========================================
# WAVE (drawing banners)
# ========================================

class BannerWave:
    """
    Draws banners waving (see the module docstring). One per MapRenderer; the
    loops are kept for the process, shared by every renderer with the same wave.

    Args:
        style: banner_fx_style.BANNER_FX_STYLE ('wave' and 'wind')
    """

    BUILDS_PER_FRAME = 4          # poses built in play per frame at most (~0.2-0.4 ms each)...
    BUILD_MS_PER_FRAME = 1.5      # ...and no more than this much building

    def __init__(self, style):
        wave, wind = style['wave'], style['wind']
        self.wave = wave
        dx, dy = wind['direction']
        norm = math.hypot(dx, dy) or 1.0
        # Phase (in cycles) lost per world px along the breeze: neighbours a little behind
        self.wind_x = dx / norm / wind['wavelength']
        self.wind_y = dy / norm / wind['wavelength']
        self.inv_period = 1.0 / wave['period']
        self.count = wave['frames']
        self.lean = wave['lean'] if dx >= 0 else -wave['lean']    # downwind
        self.signature = tuple(sorted(wave.items())) + (('lean_to', self.lean),)
        self._budget = light_fx._BuildBudget(self.BUILDS_PER_FRAME, self.BUILD_MS_PER_FRAME)
        self.frames_built = 0

    def begin_frame(self):
        """Call once per rendered frame: resets the build budget."""
        self._budget.reset()

    def phase(self, world_x, world_y, clock):
        """The breeze's pose at a world point at `clock`, in cycles (the loop repeats every 1)."""
        return clock * self.inv_period - world_x * self.wind_x - world_y * self.wind_y

    def pose(self, world_x, world_y, clock):
        """The frame index for a banner at a world point at `clock`."""
        return int(math.floor(self.phase(world_x, world_y, clock) * self.count)) % self.count

    def loops(self, art):
        """{size step: _Loop} of one flag picture (built or being built)."""
        by_step = _LOOPS.get((art, self.signature))
        if by_step is None:
            by_step = _LOOPS[(art, self.signature)] = {}
        return by_step

    def _loop(self, art, icon, step):
        """The loop of a picture at a size step, its layers made now if new; None if it has no cloth."""
        by_step = self.loops(art)
        loop = by_step.get(step)
        if loop is None:
            if art not in _LAYOUTS:
                _LAYOUTS[art] = measure_layout(icon)
            layout = _LAYOUTS[art]
            if layout is None:
                return None
            loop = by_step[step] = _Loop(icon, layout, step, self.wave, self.lean)
        return loop

    def frame(self, icon, height, world_x, world_y, clock):
        """
        (frame, loop) for flag picture `icon` drawn `height` px tall at a world
        point at `clock`, or (None, None) when it doesn't wave (not registered,
        no cloth, or nothing built yet and the frame budget spent).
        """
        art = _ART_NAMES.get(icon)
        if art is None:
            return None, None
        return self._frame(art, icon, size_step(height), self.pose(world_x, world_y, clock))

    def _frame(self, art, icon, step, index):
        """(frame, loop) of pose `index` at a size step, built or borrowed (see frame())."""
        by_step = _LOOPS.get((art, self.signature))
        loop = by_step.get(step) if by_step is not None else None
        if loop is not None:
            frame = loop.frames[index]
            if frame is not None:
                return frame, loop
        elif _LAYOUTS.get(art, True) is None:
            return None, None                       # no cloth: drawn plain
        if self._budget.allows():
            started = time.perf_counter()
            loop = self._loop(art, icon, step)
            frame = None
            if loop is not None:
                frame = loop.build(index)
                self.frames_built += 1
            self._budget.charge(started)
            return (frame, loop) if frame is not None else (None, None)
        # Over budget: the nearest pose built at this size, else at the nearest size
        if loop is not None:
            frame = loop.nearest(index)
            if frame is not None:
                return frame, loop
        if by_step:
            for other in sorted(by_step, key=lambda s: abs(s - step)):
                near = by_step[other]
                frame = near.frames[index] or near.nearest(index)
                if frame is not None:
                    return frame, near
        return None, None

    def draw(self, screen, icon, x, bottom, height, world_x, world_y, clock):
        """
        Blit the banner of flag picture `icon`, `height` px tall, its pole base at
        screen (x, bottom), in the breeze's pose at world (world_x, world_y).
        Returns False, drawing nothing, when it doesn't wave (see frame()): the
        caller draws the plain flag.
        """
        art = _ART_NAMES.get(icon)
        if art is None:
            return False
        count = self.count
        position = (clock * self.inv_period - world_x * self.wind_x - world_y * self.wind_y) * count
        whole = math.floor(position)
        index = int(whole) % count
        frame, loop = self._frame(art, icon, size_step(height), index)
        if frame is None:
            return False
        at = (int(round(x)) - loop.anchor, int(round(bottom)) - loop.height)
        screen.blit(frame, at)
        # Crossfaded into the next pose by how far the breeze is past this one, so
        # the cloth moves continuously, not in steps from pose to pose (a step moves
        # the tails up to ~0.75 px: seen ~9 times a second, it would tick). Only
        # below fade_top, where rows move half a pixel or more (a faded blit costs
        # ~4 plain ones)
        blend = int((position - whole) * 255.0 + 0.5)
        if blend >= 4:
            following = loop.frames[(index + 1) % count]
            if following is not None:
                top = loop.fade_top
                following.set_alpha(blend)
                screen.blit(following, (at[0], at[1] + top), (0, top, loop.frame_width, loop.height - top))
                # 255, not None: None would switch its per-pixel alpha off (pygame 2.6)
                following.set_alpha(255)
        return True

    def prewarm(self, icons, steps):
        """Build every pose of these flag pictures at these size steps now (the loading screen)."""
        for icon in icons:
            art = _ART_NAMES.get(icon)
            if art is None:
                continue
            for step in steps:
                loop = self._loop(art, icon, step)
                if loop is None:
                    break
                for index, frame in enumerate(loop.frames):
                    if frame is None:
                        loop.build(index)
                        self.frames_built += 1

    def keep_only(self, icons):
        """
        Drop the loops of every flag picture but these (a new game's), so the frames
        kept for the process stay those of one game's pictures: the neutral flag's
        size follows the first player's colour, and each size is a picture of its own.
        """
        keep = {_ART_NAMES.get(icon) for icon in icons}
        for key in [key for key in _LOOPS if key[0] not in keep]:
            del _LOOPS[key]

    def complete(self, icons, steps):
        """Whether every pose of these pictures at these sizes is built (tests, measuring)."""
        for icon in icons:
            art = _ART_NAMES.get(icon)
            if art is None or _LAYOUTS.get(art, True) is None:
                continue
            by_step = _LOOPS.get((art, self.signature), {})
            for step in steps:
                loop = by_step.get(step)
                if loop is None or loop.built < len(loop.frames):
                    return False
        return True


# ========================================
# MOTES (the selected banner)
# ========================================

def _even(value):
    return max(2, int(value) & ~1)


class BannerMotes:
    """
    The selected banner's motes (style['motes']): light rising from the pole
    base to the banner's top, each mote starting at a new point every life (a
    hash of its cycle), with a normal-blend halo of the raw colour under it.

    Args:
        style: banner_fx_style.MOTES
        warm_white: the white the light colour is mixed toward
    """

    def __init__(self, style, warm_white):
        self.style = style
        self.glow = GlowSprites()
        self.tint = TintSprites()
        self.raw = tuple(style['colour'])
        self.colour = light_fx.light_colour(self.raw, style['white_mix'], warm_white)
        rng = random.Random(0xBA7712)
        lo, hi = style['size']
        # Per mote: (1 / life, offset, core diameter share, sway phase, hash salt)
        self.motes = [(1.0 / rng.uniform(*style['life']), rng.random(), rng.uniform(lo, hi),
                       rng.uniform(0.0, 2.0 * math.pi), rng.getrandbits(24))
                      for _ in range(style['count'])]
        self._prepared = {}       # size step -> per mote sprites (complete)
        self._key = None          # what the motes are on, and since when (the appear ramp)
        self._since = 0.0
        self._last = None

    def begin_frame(self):
        """Call once per rendered frame: resets the sprite build budgets."""
        self.glow.begin_frame()
        self.tint.begin_frame()

    def _sprites(self, step):
        """
        Per mote at this size step: (core ladders by sub-pixel phase, core half
        size, halo ladder, halo half size); None while a ladder is still being
        built within the frame budget. Until a shifted copy exists its phase uses
        the unshifted ladder.
        """
        prepared = self._prepared.get(step)
        if prepared is not None:
            return prepared
        style = self.style
        prepared = []
        complete = True
        cores = {}
        halos = {}
        for _, _, size, _, _ in self.motes:
            diameter = _even(size * step)
            phases = cores.get(diameter)
            if phases is None:
                unshifted = self.glow.ladder(diameter, self.colour)
                if unshifted is None:
                    return None
                phases = [unshifted]
                for phase in range(1, GlowSprites.SUBPIXEL_PHASES):
                    shifted = self.glow.ladder(diameter, self.colour, 'mote', phase)
                    if shifted is None:
                        complete = False
                        shifted = unshifted
                    phases.append(shifted)
                cores[diameter] = phases
            halo_d = max(4, int(size * step * style['tint_size']) & ~1)
            halo = halos.get(halo_d)
            if halo is None:
                halo = self.tint.alpha_ladder(halo_d, self.raw, style['tint'])
                if halo is None:
                    return None
                halos[halo_d] = halo
            prepared.append((phases, diameter >> 1, halo, halo_d >> 1))
        if complete:
            self._prepared[step] = prepared
        return prepared

    def prewarm(self, steps):
        """Build every sprite the motes use at these size steps now (the loading screen)."""
        budgets = (self.glow._budget, self.tint._budget)
        self.glow._budget = self.tint._budget = light_fx._BuildBudget(10 ** 9, 10 ** 9)
        try:
            for step in steps:
                self._sprites(step)
        finally:
            self.glow._budget, self.tint._budget = budgets

    def strength(self, key, clock):
        """0-1: the motes light up over style['appear'] s once a banner is selected."""
        if key != self._key or self._last is None or clock < self._last or clock - self._last > 0.25:
            self._key = key
            self._since = clock
        self._last = clock
        appear = self.style['appear']
        return min(1.0, (clock - self._since) / appear) if appear > 0 else 1.0

    def draw(self, screen, key, x, bottom, height, clock):
        """
        The motes of the banner `key` (any value naming the selection), `height`
        px tall with its pole base at screen (x, bottom), at `clock`.
        """
        strength = self.strength(key, clock)
        if strength <= 0.0:
            return
        sprites = self._sprites(size_step(height))
        if sprites is None:
            return      # still being built (within the frame budget)
        style = self.style
        spread = style['spread'] * height
        fan = style['fan']
        start = style['start'] * height
        rise = style['rise'] * height
        sway = style['sway'] * height
        fade_in, fade_out = style['fade_in'], style['fade_out']
        core_scale = GlowSprites.LEVELS * style['intensity'] * strength
        halo_scale = TintSprites.LEVELS * strength
        steps = GlowSprites.LEVELS
        halo_top = TintSprites.LEVELS
        sin = math.sin
        halos = []
        cores = []
        for (inv_life, offset, _, sway_phase, salt), (phases, core_half, halo, halo_half) in \
                zip(self.motes, sprites):
            u = clock * inv_life + offset
            cycle = int(math.floor(u))
            age = u - cycle
            env = min(1.0, age / fade_in) * min(1.0, (1.0 - age) / fade_out)
            level = int(core_scale * env + 0.5)
            if level <= 0:
                continue
            h = ((cycle * 73856093) ^ salt) & 0xFFFFFFFF
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
            a = (h & 0xFFFF) / 65536.0
            b = (h >> 16) / 65536.0
            px = x + (a - 0.5) * spread * (fan + (1.0 - fan) * age) + sway * sin(age * 5.0 + sway_phase)
            py = bottom - b * start - rise * age
            # Sub-pixel placement (as the hero fireflies): half pixels across, quarter
            # pixels down, split into the whole pixel and the shifted sprite
            xq = int((px + 4096.0) * 2.0 + 0.5)
            yq = int((py + 4096.0) * 4.0 + 0.5)
            sx = (xq >> 1) - 4096
            sy = (yq >> 2) - 4096
            halo_level = int(halo_scale * env + 0.5)
            if halo_level > 0:
                halos.append((halo[halo_level if halo_level < halo_top else halo_top],
                              (sx - halo_half, sy - halo_half)))
            cores.append((phases[(yq & 3) + ((xq & 1) << 2)][level if level < steps else steps],
                          (sx - core_half, sy - core_half), None, ADD))
        if halos:
            screen.blits(halos, doreturn=False)
        if cores:
            screen.blits(cores, doreturn=False)
