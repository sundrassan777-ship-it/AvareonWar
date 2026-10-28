# -*- coding: utf-8 -*-
"""
Battle Screen Light

The battle screen's effects in the light style of the hero / order / event
passes, drawn for EnhancedBattleInterface and its BattleBarVolleyEffect
(ui/effects/battle_interface.py), styled in battle_fx_style.py:

- the bars: a gradient fill over a dark track, a seam of light at each bar's
  front and a faint sheen sliding along the fill (draw_bar, under the frame)
- shots: light gathering from the shooter's remaining bar into its front, then
  one bolt of light flying level at the enemy bar, landing in a flare with
  sparks and a shock ring; the chunk it destroys breaks off and falls out of
  the bar (draw_pieces, under the frame), embers bursting from it (Shot,
  draw_shot, over the frame)
- the finale: a sweep of light and gold light round the frame of the bar left
  standing, the seam of an emptied bar going out (draw_frame_glow and draw_bar)
- the battle icon's gold glow (draw_icon_glow) and the vignette (darken)

How it is drawn (see light_fx.py for the kit):
- Small lights (bolt heads and trails, charge motes, sparks, embers) are cached GlowSprites
  levels, prepared for both sides' colours while the setup screen shows
  (prepare_battle + prewarm_step), so the fight builds nothing.
- Big or long-lived lights (flares, seams, sheens, the frame and icon glows) are
  a grey baked once and tinted every frame (fill, multiply, add), so they fade
  without brightness steps.
- Every bake is kept in a module cache per display size (_shared), so it is paid
  once a session, not per battle.

Everything a shot shows is a function of the clock: a Shot is built once when
it is armed and never changes.
"""

import math

import pygame

from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, TintSprites, SoftRing, GlowFrame, GLOW_PROFILES
from ui.effects.hero_fx_effect import _even, _ladder_size
from ui.effects.battle_fx_style import (BAR_STYLE, BOLT_STYLE, CHARGE_STYLE, MUZZLE_STYLE, IMPACT_STYLE,
                                        BURN_STYLE, FINALE_STYLE, ICON_GLOW_STYLE, BACKDROP_STYLE)

ADD = pygame.BLEND_RGB_ADD
MULT = pygame.BLEND_RGB_MULT

REFERENCE_BAR_HEIGHT = 40.0   # H at 1600x900; px sizes in the style are for this
FRAME_ALPHA = 100             # silhouettes: BattleBar.png's fill window is alpha 92, its art opaque
LIGHT_PEAK = 220              # a side's light is made from its colour brightened to at least this peak

# ========================================
# SHARED (kept between battles)
# ========================================

# Rebuilt when the display changes (the surfaces carry its format):
# 'key', 'glow' (GlowSprites), 'tint' (TintSprites), 'ring' (SoftRing),
# 'frames' ({reach: GlowFrame}), 'greys' ({key: (grey, scratch)}),
# 'bars' ({(size, colour): (fill, track)}), 'darken' ({size: multiply surface}),
# 'tips' ({(frame size, mirrored): the frame art's opaque bounds})
_shared = {}


def _kit():
    display = pygame.display.get_surface()
    key = ('display', display.get_size() if display is not None else None)
    if _shared.get('key') != key:
        _shared.clear()
        _shared.update(key=key, glow=GlowSprites(), tint=TintSprites(), ring=SoftRing(),
                       frames={}, greys={}, bars={}, darken={}, tips={})
    return _shared


def _scratch_for(grey):
    return pygame.Surface(grey.get_size(), 0, grey)


def _add_tinted(screen, grey, scratch, colour, pos):
    """Add grey * colour to the screen at pos (the grey tinted this frame: no brightness steps)."""
    scratch.fill(colour)
    scratch.blit(grey, (0, 0), special_flags=MULT)
    screen.blit(scratch, pos, special_flags=ADD)


def tip_x(rect, anchor_right, fill):
    """x of the inner (centre-facing) end of a bar's fill (BattleBarVolleyEffect._fill_tip_x)."""
    width = rect.width * max(0.0, min(1.0, fill))
    return rect.right - width if anchor_right else rect.left + width


def spear_tip(border, png_pos, rect, fill_y, anchor_right):
    """
    The point of the frame's inner end cap (where a bar fires from): the inner
    edge of the frame art's opaque bounds, at their middle height. Without a
    frame, the inner end of the fill.
    """
    if border is None:
        return (rect.left if anchor_right else rect.right), fill_y + rect.height / 2.0
    tips = _kit()['tips']
    key = (border.get_size(), anchor_right)    # the defender's frame is the mirrored one
    bounds = tips.get(key)
    if bounds is None:
        bounds = tips[key] = border.get_bounding_rect(min_alpha=FRAME_ALPHA)
    x = png_pos[0] + (bounds.left if anchor_right else bounds.right)
    return x, png_pos[1] + bounds.centery


# ========================================
# A SHOT
# ========================================

class Shot:
    """
    One side's shot: light gathering from the shooter's remaining bar into its
    front (the charge, when CHARGE_STYLE is on), then one bolt of light flying
    level from there to the enemy bar, landing in a flare with sparks and a
    ring; the chunk it destroys breaks off and falls out of the bar, embers
    bursting from it.

    Built once when the shot is armed (as its charge begins), from its own
    random.Random (never the schedule's or the global one); after that
    everything it shows is a function of the clock.
    """

    def __init__(self, rng, arm_t, fire_t, muzzle, landing, chunk_span, piece, inward, bar, colours,
                 gather=None):
        """
        Args:
            rng: random.Random for this shot alone
            arm_t: when its charge begins (fire_t without a charge)
            fire_t: when the bolt leaves
            muzzle: (x, y) the bolt leaves from - the shooter's front (the
                frame's spear tip without a charge)
            landing: (x, y) where it lands
            chunk_span: (front x, back x) of the chunk it destroys; equal for no damage
            piece: (left x, width) of that chunk on the bar painter's pixels (width 0: none)
            inward: +1 if the target bar's front faces right, -1 if left
            bar: the target bar's fill rect (its top and size)
            colours: the shooter's and the target's light colours (BattleLight.colours)
            gather: (front x, outer end x) of the shooter's remaining bar, for the
                charge's motes, or None (no charge)
        """
        h = bar.height
        sparks = IMPACT_STYLE['sparks']
        self.arm_t = arm_t
        self.fire_t = fire_t
        self.land_t = fire_t + BOLT_STYLE['travel']
        self.muzzle = muzzle
        self.colours = colours
        self.bar = bar
        self.push = -inward        # the way the bolt flies: the piece falls that way
        # Straight across, level at the height it lands (aimed horizontally at
        # the enemy bar - owner, 2026-10-28)
        ex, ey = landing
        self.flight = (muzzle[0], ex, ey)
        # Sparks spray back out of the bar, toward the shooter
        back = 0.0 if muzzle[0] > ex else math.pi
        cone = math.radians(sparks['cone'])
        self.sparks = []
        for _ in range(sparks['count']):
            a = back + rng.uniform(-cone, cone)
            self.sparks.append((math.cos(a), math.sin(a), rng.uniform(*sparks['distance']) * h,
                                rng.uniform(*sparks['size']) * h, 1.0 / rng.uniform(*sparks['life'])))
        # The charge's motes: (start x, start y, when it sets off - share of the
        # charge, diameter), from all along the shooter's remaining bar
        self.motes = []
        if gather is not None:
            style = CHARGE_STYLE
            front, outer = gather
            for _ in range(style['motes']):
                self.motes.append((front + (outer - front) * rng.uniform(0.08, 1.0),
                                   muzzle[1] + rng.uniform(-1.0, 1.0) * style['mote_spread'] * h,
                                   rng.uniform(0.0, style['mote_delay']),
                                   rng.uniform(*style['mote_size']) * h))
        # Embers bursting from the destroyed chunk
        front_x, back_x = chunk_span
        self.embers = []
        if abs(back_x - front_x) >= 1.0:
            spec = BURN_STYLE['embers']
            for _ in range(spec['count']):
                x0 = front_x + (back_x - front_x) * rng.random()
                self.embers.append(ember(rng, self.land_t, x0, ey + rng.uniform(-0.3, 0.3) * h,
                                         inward, h, spec))
        # The piece it breaks off: (left x, width), or None
        self.piece = piece if piece[1] > 0 else None

        self.end = max([self.land_t + max(IMPACT_STYLE['flare']['duration'], IMPACT_STYLE['ring']['duration'],
                                          sparks['life'][1], BURN_STYLE['fall']['duration'])]
                       + [e[0] + 1.0 / e[6] for e in self.embers])

    def broken(self, t):
        """1 once the bolt has landed and its chunk broken off, else 0."""
        return 1.0 if t >= self.land_t else 0.0

    def hit_kick(self, t, decay):
        """The landing's kick at t, fading exponentially (the target's seam)."""
        age = t - self.land_t
        return math.exp(-age / decay) if 0.0 <= age < decay * 6.0 else 0.0

    def fire_kick(self, t, decay):
        """The same for the bolt leaving (the shooter's seam)."""
        age = t - self.fire_t
        return math.exp(-age / decay) if 0.0 <= age < decay * 6.0 else 0.0

    def charge(self, t):
        """How far the charge has built at t (0-1), or None outside it."""
        if self.fire_t <= self.arm_t or not self.arm_t <= t < self.fire_t:
            return None
        return (t - self.arm_t) / (self.fire_t - self.arm_t)


def ember(rng, t0, x0, y0, inward, h, spec):
    """
    One ember: (t0, x0, y0, vx, vy, diameter, 1 / life), flung up and toward the
    gap between the bars (inward), then falling.
    """
    angle = math.radians(rng.uniform(*spec['up']))
    speed = rng.uniform(*spec['speed']) * h
    return (t0, x0, y0, math.cos(angle) * speed * inward, -math.sin(angle) * speed,
            rng.uniform(*spec['size']) * h, 1.0 / rng.uniform(*spec['life']))


# ========================================
# BATTLE LIGHT
# ========================================

class BattleLight:
    """
    The battle screen's light kit for one bar height: the painters and the
    shared caches behind them.
    """

    def __init__(self, bar_height):
        """
        Args:
            bar_height: the bars' fill height, px (H)
        """
        kit = _kit()
        self.h = max(4, int(bar_height))
        self.scale = self.h / REFERENCE_BAR_HEIGHT
        self.glow = kit['glow']
        self.tint = kit['tint']
        self.ring = kit['ring']
        self._kit = kit
        self._colours = {}
        self._pending = []        # (diameter, colour, level) GlowSprites still to build
        self._denied = 0          # sprites wanted while drawing but not built yet (skipped a frame)
        style = BOLT_STYLE
        steps = GlowSprites.LEVELS
        # Bolt head and trail: (age behind the head, diameter, level) - fixed per bar height
        n = style['trail'] + 1
        self._trail = [(j * style['trail_gap'],
                        _even(style['head'] * self.h * (1.0 - style['trail_shrink'] * j / float(n))),
                        max(1, int(steps * style['intensity'] * (1.0 - j / float(n)) ** 1.3 + 0.5)))
                       for j in range(n)]
        self._halo_d = max(4, int(style['halo'] * self.h) & ~3)

    # ---------- caches ----------

    def begin_frame(self):
        """Call once per rendered frame: resets the sprite build budgets."""
        self.glow.begin_frame()
        self.tint.begin_frame()

    def sprites_built(self):
        return self.glow.sprites_built + self.tint.sprites_built

    def denied(self):
        return self._denied

    def colours(self, colour):
        """
        The light colours of one side's colour (cached). A dark player colour is
        brightened first (same hue, its brightest channel raised to LIGHT_PEAK),
        or its bolts would be dim next to a bright opponent's.
        """
        colour = tuple(colour[:3])
        found = self._colours.get(colour)
        if found is None:
            peak = max(colour)
            lit = tuple(min(255, int(c * LIGHT_PEAK / float(peak)))
                        for c in colour) if 0 < peak < LIGHT_PEAK else colour

            def mix(white_mix):
                return light_fx.light_colour(lit, white_mix)
            impact = IMPACT_STYLE
            found = self._colours[colour] = {
                'raw': colour,
                'bolt': mix(BOLT_STYLE['white_mix']),
                'charge': mix(CHARGE_STYLE['white_mix']),
                'muzzle': mix(MUZZLE_STYLE['white_mix']),
                'flare': mix(impact['flare']['white_mix']),
                'spark': mix(impact['sparks']['white_mix']),
                'ring': mix(impact['ring']['white_mix']),
                'ember': mix(BURN_STYLE['embers']['white_mix']),
                'heat': mix(BURN_STYLE['white_mix']),
                'seam': mix(BAR_STYLE['seam']['white_mix']),
                'sheen': mix(BAR_STYLE['sheen']['white_mix']),
            }
        return found

    def _grey(self, key, build):
        """A grey baked once (kept between battles) and its scratch surface for tinting."""
        greys = self._kit['greys']
        pair = greys.get(key)
        if pair is None:
            grey = build()
            pair = greys[key] = (grey, _scratch_for(grey))
        return pair

    def _flare_grey(self, diameter):
        def build():
            half = diameter / 2.0
            shape = GLOW_PROFILES['flare']
            return light_fx.radial_surface(diameter, lambda r: shape(r / half))
        return self._grey(('flare', diameter), build)

    def _mote(self, diameter, colour, level):
        sprite = self.glow.sprite(diameter, colour, level)
        if sprite is None:
            self._denied += 1
        return sprite

    # ---------- preparing ----------

    def prepare_battle(self, attacker_colour, defender_colour):
        """
        Bake what a fight between these colours draws, and queue its small light
        sprites for prewarm_step(). Greys and rings are baked now (a few ms the
        first time a session, then cached); the sprites are built while the setup
        screen shows, within the frame budget.
        """
        steps = GlowSprites.LEVELS
        h = self.h
        spark = IMPACT_STYLE['sparks']
        embers = BURN_STYLE['embers']
        charge = CHARGE_STYLE
        spark_sizes = range(_even(spark['size'][0] * h * 0.65), _even(spark['size'][1] * h) + 1, 2)
        ember_sizes = range(_even(embers['size'][0] * h * 0.6), _even(embers['size'][1] * h) + 1, 2)
        charge_sizes = range(_even(charge['mote_size'][0] * h * 0.7), _even(charge['mote_size'][1] * h) + 1, 2)
        pending = []
        for colour in (attacker_colour, defender_colour):
            c = self.colours(colour)
            if charge['enabled']:
                pending += [(d, c['charge'], level) for d in charge_sizes for level in range(1, steps + 1)]
            pending += [(d, c['bolt'], level) for _, d, level in self._trail]
            pending += [(d, c['spark'], level) for d in spark_sizes for level in range(1, steps + 1)]
            pending += [(d, c['ember'], level) for d in ember_sizes for level in range(1, steps + 1)]
            # The head's colour halo (one alpha) and the shock ring's tinted copy
            self.tint.prewarm([self._halo_d], c['raw'], [BOLT_STYLE['halo_alpha']])
            self.ring.draw(pygame.Surface((8, 8)), 4, 4, 3, c['ring'], 1.0)
        # Built last first (prewarm_step pops): the charge and the bolts are needed first
        self._pending = list(reversed(pending))
        # The flare greys every size a charge's orb, a muzzle flash or an impact can take
        lo = min(IMPACT_STYLE['flare']['size'][0], MUZZLE_STYLE['size'], charge['orb'][0]) * h
        hi = max(IMPACT_STYLE['flare']['size'][1], MUZZLE_STYLE['size'], charge['orb'][1]) * h
        size = lo
        while size <= hi * 1.13:
            self._flare_grey(_ladder_size(size))
            size *= 1.12
        self._seam_grey()
        self._sheen_grey(False)
        self._sheen_grey(True)

    def prewarm_step(self):
        """Build queued sprites within this frame's budget. True once all are built."""
        pending = self._pending
        while pending:
            d, colour, level = pending[-1]
            if self.glow.sprite(d, colour, level) is None:
                return False
            pending.pop()
        return True

    # ---------- the bars ----------

    def _bar_surfaces(self, size, colour):
        """(fill, track) for a bar of this size: vertical gradients, baked once."""
        bars = self._kit['bars']
        key = (size, tuple(colour[:3]))
        pair = bars.get(key)
        if pair is None:
            w, h = size
            style = BAR_STYLE
            g0, a0 = style['fill_top']
            g1, a1 = style['fill_bottom']
            top = tuple(min(255, int(c * g0) + a0) for c in colour[:3])
            bottom = tuple(min(255, int(c * g1) + a1) for c in colour[:3])
            shine = light_fx.light_colour(top, style['highlight_mix'])
            line_y = style['highlight_y'] * (h - 1)
            fill = pygame.Surface(size)
            track = pygame.Surface(size)
            for y in range(h):
                t = y / float(max(1, h - 1))
                row = [a + (b - a) * t for a, b in zip(top, bottom)]
                near = max(0.0, 1.0 - abs(y - line_y) / 1.5)
                row = tuple(int(c + (s - c) * near) for c, s in zip(row, shine))
                pygame.draw.line(fill, row, (0, y), (w, y))
                dark = [a + (b - a) * t for a, b in zip(style['track_top'], style['track_bottom'])]
                # An inner shadow along the top of the track
                shade = 0.55 if y == 0 else (0.8 if y == 1 else 1.0)
                pygame.draw.line(track, tuple(int(c * shade) for c in dark), (0, y), (w, y))
            if pygame.display.get_surface() is not None:
                fill, track = fill.convert(), track.convert()
            pair = bars[key] = (fill, track)
        return pair

    def _seam_grey(self):
        h = self.h
        width = _even(BAR_STYLE['seam']['width'] * h) + 1

        def build():
            grey = light_fx.new_black_surface((width, h))
            centre = (width - 1) / 2.0
            sigma = width / 5.0
            for x in range(width):
                v = int(255 * math.exp(-((x - centre) / sigma) ** 2))
                pygame.draw.line(grey, (v, v, v), (x, 0), (x, h - 1))
            return grey
        return self._grey(('seam', width, h), build)

    def _sheen_grey(self, leftward):
        """A soft slanted band of light, its top leaning the way it travels."""
        h = self.h
        style = BAR_STYLE['sheen']
        band = _even(style['width'] * h)
        slant = int(style['slant'] * h)

        def build():
            row = light_fx.new_black_surface((band, 1))
            centre, sigma = band / 2.0, band / 4.0
            for x in range(band):
                v = int(255 * math.exp(-((x - centre) / sigma) ** 2))
                row.set_at((x, 0), (v, v, v))
            grey = light_fx.new_black_surface((band + slant, h))
            for y in range(h):
                lean = int(slant * (1.0 - y / float(max(1, h - 1))))
                grey.blit(row, (lean, y))
            return pygame.transform.flip(grey, True, False) if leftward else grey
        return self._grey(('sheen', band, slant, h, leftward), build)

    def draw_bar(self, screen, rect, fill_y, anchor_right, colour, fill, eaten=0.0,
                 seam=None, sheen=None):
        """
        One bar under its frame: the track, the fill standing, the seam of light
        at the front and the sheen. (The pieces broken off fall separately:
        draw_pieces.)

        Args:
            rect: the bar's fill rect (its x and size; fill_y is its top)
            fill: fill share standing (0-1), the chunk being destroyed included
            eaten: share of that already broken off from the front (shown as track)
            seam: the seam's brightness (None: the seam at rest, unlit)
            sheen: (progress 0-1, brightness) of a sheen crossing the fill, or None
        """
        w, h = rect.width, rect.height
        fill_surface, track = self._bar_surfaces((w, h), colour)
        screen.blit(track, (rect.left, fill_y))
        standing = max(0.0, min(1.0, fill - eaten))
        width = int(w * standing)
        if width > 0:
            if anchor_right:
                screen.blit(fill_surface, (rect.right - width, fill_y), pygame.Rect(w - width, 0, width, h))
            else:
                screen.blit(fill_surface, (rect.left, fill_y), pygame.Rect(0, 0, width, h))
        c = self.colours(colour)
        front = tip_x(rect, anchor_right, standing)
        bar = pygame.Rect(rect.left, fill_y, w, h)
        clip = screen.get_clip()
        if sheen is not None and width > 0:
            self._draw_sheen(screen, rect, fill_y, anchor_right, width, c['sheen'], sheen, clip)
        if seam is not None and seam > 0.01:
            grey, scratch = self._seam_grey()
            screen.set_clip(bar.clip(clip) if clip else bar)
            _add_tinted(screen, grey, scratch, light_fx.scaled_colour(c['seam'], min(1.0, seam)),
                        (int(front) - grey.get_width() // 2, fill_y))
            screen.set_clip(clip)

    def _piece_surface(self, size, colour):
        """The fill's gradient with per-pixel alpha, for falling pieces (they turn: clear corners). Baked once."""
        bars = self._kit['bars']
        key = ('piece', size, tuple(colour[:3]))
        piece = bars.get(key)
        if piece is None:
            piece = pygame.Surface(size, pygame.SRCALPHA)
            piece.blit(self._bar_surfaces(size, colour)[0], (0, 0))
            bars[key] = piece
        return piece

    def draw_pieces(self, screen, shot, t):
        """
        The chunk a shot broke off its target bar: it pops up a little, falls and
        topples the way the bolt flew and fades out, glowing hot as it breaks and
        cooling as it falls. Draw under the frames, so it leaves the bar exactly
        as the bar showed it (the frame's window shade on it) and falls out
        below. (It is a small copy turned each frame, for half a second.)
        """
        if shot.piece is None:
            return
        fall = BURN_STYLE['fall']
        duration = fall['duration']
        age = t - shot.land_t
        if not 0.0 <= age < duration:
            return
        bar = shot.bar
        h = bar.height
        target = shot.colours[1]
        left, width = shot.piece
        p = age / duration
        dx = fall['push'] * age * h * shot.push
        dy = (-fall['pop'] * age + 0.5 * fall['gravity'] * age * age) * h
        piece = self._piece_surface(bar.size, target['raw']).subsurface(pygame.Rect(0, 0, width, h)).copy()
        heat = BURN_STYLE['heat'] * math.exp(-age / BURN_STYLE['heat_decay'])
        if heat > 0.01:
            # Hot: its colour toward white (adds to the colour, leaves the alpha)
            piece.fill(light_fx.scaled_colour(target['heat'], heat), special_flags=ADD)
        # Toppling the way it was pushed (pygame turns counter-clockwise)
        angle = -fall['spin'] * age * shot.push
        if abs(angle) >= 0.5:
            piece = pygame.transform.rotate(piece, angle)
        piece.set_alpha(int(255 * (1.0 - p * p)))
        centre = (int(left + width / 2.0 + dx), int(bar.top + h / 2.0 + dy))
        screen.blit(piece, piece.get_rect(center=centre))

    def _draw_sheen(self, screen, rect, fill_y, anchor_right, width, colour, sheen, clip):
        progress, brightness = sheen
        if brightness <= 0.01 or not 0.0 < progress < 1.0:
            return
        grey, scratch = self._sheen_grey(anchor_right)
        band = grey.get_width()
        # From beyond the bar's outer end to past its front
        if anchor_right:
            x = rect.right - progress * (width + band)
            visible = pygame.Rect(rect.right - width, fill_y, width, rect.height)
        else:
            x = rect.left - band + progress * (width + band)
            visible = pygame.Rect(rect.left, fill_y, width, rect.height)
        screen.set_clip(visible.clip(clip) if clip else visible)
        _add_tinted(screen, grey, scratch, light_fx.scaled_colour(colour, brightness), (int(x), fill_y))
        screen.set_clip(clip)

    def seam_level(self, clock, phase=0.0, kick=0.0):
        """The seam's brightness: at rest it shimmers slowly; kicks add to it."""
        style = BAR_STYLE['seam']
        rest = style['base'] + style['shimmer'] * math.sin(2.0 * math.pi * style['shimmer_hz'] * clock + phase)
        return rest + kick

    @staticmethod
    def idle_sheen(clock, offset=0.0):
        """(progress, brightness) of the faint sheen at this clock, or None between passes."""
        style = BAR_STYLE['sheen']
        u = ((clock + offset) % style['period']) / style['travel']
        if u >= 1.0:
            return None
        return u, style['intensity'] * math.sin(math.pi * u) ** 0.5

    # ---------- the light layer (over the frames) ----------

    def flare(self, screen, x, y, size, colour, brightness):
        """A flare of light (diameter in px) tinted this frame."""
        if brightness <= 0.01:
            return
        tint = light_fx.scaled_colour(colour, min(1.0, brightness))
        if not any(tint):
            return
        diameter = _ladder_size(size)
        grey, scratch = self._flare_grey(diameter)
        half = diameter >> 1
        _add_tinted(screen, grey, scratch, tint, (int(x) - half, int(y) - half))

    def draw_shot(self, screen, shot, t):
        """
        A shot at time t: its charge (motes streaming along the shooter's bar
        into its front, an orb swelling there), the flash as the bolt leaves, the
        bolt in flight, its impact (flare, sparks, ring) and the embers.
        """
        h = self.h
        steps = GlowSprites.LEVELS
        shooter, target = shot.colours
        halos = []
        seq = []
        append = seq.append
        mx, my = shot.muzzle

        # The charge
        p = shot.charge(t)
        if p is not None:
            style = CHARGE_STYLE
            for x0, y0, delay, d in shot.motes:
                q = (p - delay) / (1.0 - delay)
                if q <= 0.0:
                    continue
                u = q * q                         # speeding up into the front
                level = int(steps * style['intensity'] * min(1.0, q * 4.0) * (0.55 + 0.45 * q) + 0.5)
                diameter = _even(d * (1.0 - 0.3 * q))
                sprite = self._mote(diameter, shooter['charge'], max(1, min(steps, level)))
                if sprite is not None:
                    half = diameter >> 1
                    append((sprite, (int(x0 + (mx - x0) * u) - half, int(y0 + (my - y0) * u) - half), None, ADD))
            o0, o1 = style['orb']
            self.flare(screen, mx, my, (o0 + (o1 - o0) * p ** 1.5) * h, shooter['muzzle'],
                       style['orb_intensity'] * p ** 1.2)

        # The flash as the bolt leaves (taking over from the orb at full strength)
        age = t - shot.fire_t
        muzzle = MUZZLE_STYLE
        if 0.0 <= age < muzzle['duration']:
            self.flare(screen, mx, my, muzzle['size'] * h, shooter['muzzle'],
                       muzzle['intensity'] * (1.0 - age / muzzle['duration']) ** 1.5)

        # The head and its trail, straight across
        sx, ex, ey = shot.flight
        travel, ease = BOLT_STYLE['travel'], BOLT_STYLE['ease']
        trail = self._trail
        if 0.0 <= age < travel + trail[-1][0]:
            for lag, d, level in trail:
                tj = age - lag
                if tj < 0.0 or tj > travel:
                    continue
                x = sx + (ex - sx) * (tj / travel) ** ease
                if lag == 0.0:
                    halo = self.tint.sprite(self._halo_d, shooter['raw'], BOLT_STYLE['halo_alpha'])
                    if halo is not None:
                        half = self._halo_d >> 1
                        halos.append((halo, (int(x) - half, int(ey) - half)))
                sprite = self._mote(d, shooter['bolt'], level)
                if sprite is not None:
                    append((sprite, (int(x) - (d >> 1), int(ey) - (d >> 1)), None, ADD))

        # The impact: a flare, sparks sprayed back, a soft ring
        hit = t - shot.land_t
        if hit >= 0.0:
            flare = IMPACT_STYLE['flare']
            if hit < flare['duration']:
                s0, s1 = flare['size']
                grow = 1.0 - (1.0 - min(1.0, hit / flare['grow'])) ** 2
                self.flare(screen, ex, ey, (s0 + (s1 - s0) * grow) * h, shooter['flare'],
                           flare['intensity'] * (1.0 - hit / flare['duration']) ** 1.4)
            intensity = IMPACT_STYLE['sparks']['intensity']
            for dx, dy, dist, size, inv_life in shot.sparks:
                u = hit * inv_life
                if u >= 1.0:
                    continue
                r = dist * (1.0 - (1.0 - u) ** 3)
                fade = u * 8.0 if u < 0.125 else (1.0 - u) ** 1.4 * 1.2
                level = int(steps * intensity * min(1.0, fade) + 0.5)
                if level <= 0:
                    continue
                d = _even(size * (1.0 - 0.35 * u))
                sprite = self._mote(d, shooter['spark'], min(steps, level))
                if sprite is not None:
                    append((sprite, (int(ex + dx * r) - (d >> 1), int(ey + dy * r) - (d >> 1)), None, ADD))
            ring = IMPACT_STYLE['ring']
            if hit < ring['duration']:
                q = hit / ring['duration']
                r0, r1 = ring['radius']
                radius = (r0 + (r1 - r0) * (1.0 - (1.0 - q) ** 3)) * h
                b = ring['intensity'] * min(1.0, hit / 0.03) * (1.0 - q) ** 1.5
                self.ring.draw(screen, int(ex), int(ey), radius, shooter['ring'], b)
        self._embers(seq, shot.embers, t, target['ember'])
        if halos:
            screen.blits(halos, doreturn=False)
        if seq:
            screen.blits(seq, doreturn=False)

    def draw_embers(self, screen, embers, t, colour):
        """Embers on their own (an emptied bar's last shower)."""
        seq = []
        self._embers(seq, embers, t, colour)
        if seq:
            screen.blits(seq, doreturn=False)

    def _embers(self, seq, embers, t, colour):
        steps = GlowSprites.LEVELS
        spec = BURN_STYLE['embers']
        gravity = spec['gravity'] * self.h * 0.5
        for t0, x0, y0, vx, vy, size, inv_life in embers:
            age = t - t0
            if age < 0.0:
                continue
            u = age * inv_life
            if u >= 1.0:
                continue
            fade = u * 10.0 if u < 0.1 else (1.0 - u) ** 1.2
            level = int(steps * spec['intensity'] * min(1.0, fade) + 0.5)
            if level <= 0:
                continue
            d = _even(size * (1.0 - 0.4 * u))
            sprite = self._mote(d, colour, min(steps, level))
            if sprite is not None:
                x = x0 + vx * age
                y = y0 + vy * age + gravity * age * age
                seq.append((sprite, (int(x) - (d >> 1), int(y) - (d >> 1)), None, ADD))

    def finale_embers(self, rng, t0, x, y, inward):
        """An emptied bar's last shower of embers from its front."""
        spec = BURN_STYLE['embers']
        return [ember(rng, t0 + rng.uniform(0.0, 0.12), x, y + rng.uniform(-0.35, 0.35) * self.h,
                      inward, self.h, spec)
                for _ in range(FINALE_STYLE['embers'])]

    # ---------- glows round art (the winner's frame, the battle icon) ----------

    def _outline_grey(self, sprite, key, reach):
        """
        The light round a sprite's silhouette, cropped to the art's opaque bounds:
        (grey, scratch, offset of the grey from the sprite's top-left). Baked once.
        """
        greys = self._kit['greys']
        found = greys.get(('outline', key, reach))
        if found is None:
            frames = self._kit['frames']
            glow_frame = frames.get(reach)
            if glow_frame is None:
                glow_frame = frames[reach] = GlowFrame(reach=reach)
            bounds = sprite.get_bounding_rect(min_alpha=FRAME_ALPHA)
            grey, pad = glow_frame.grey(bounds.size, 'sprite', sprite=sprite.subsurface(bounds).copy(),
                                        sprite_key=key)
            found = greys[('outline', key, reach)] = (grey, _scratch_for(grey), (bounds.x - pad, bounds.y - pad))
        return found

    def _frame_reach(self):
        return max(3, int(FINALE_STYLE['frame_reach'] * self.scale))

    def prepare_frame(self, border, flipped):
        """Bake the gold light round a bar frame (shown in the finale)."""
        if border is not None:
            self._outline_grey(border, ('battlebar', border.get_size(), flipped), self._frame_reach())

    def draw_frame_glow(self, screen, border, flipped, png_pos, strength):
        """Gold light round a bar frame's outline at strength 0-1 (tinted this frame)."""
        if border is None or strength <= 0.01:
            return
        grey, scratch, offset = self._outline_grey(border, ('battlebar', border.get_size(), flipped),
                                                   self._frame_reach())
        colour = light_fx.scaled_colour(FINALE_STYLE['frame_colour'], min(1.0, strength))
        _add_tinted(screen, grey, scratch, colour, (png_pos[0] + offset[0], png_pos[1] + offset[1]))

    def _icon_reach(self):
        return max(3, int(ICON_GLOW_STYLE['reach'] * self.scale))

    def prepare_icon(self, icon):
        """Bake the gold light round the battle icon (shown from the first frame)."""
        if icon is not None:
            self._outline_grey(icon, ('icon', icon.get_size()), self._icon_reach())
            self._flare_grey(_ladder_size(ICON_GLOW_STYLE['bloom'] * icon.get_height()))

    def draw_icon_bloom(self, screen, icon, centre, brightness):
        """A soft light behind the battle icon's swords (draw before the icon)."""
        style = ICON_GLOW_STYLE
        colour = light_fx.light_colour(style['colour'], style['bloom_white_mix'])
        self.flare(screen, centre[0], centre[1], style['bloom'] * icon.get_height(), colour, brightness)

    def draw_icon_outline(self, screen, icon, scale, step, top_left, brightness):
        """
        Gold light round the battle icon's swords, drawn at the icon's pulsed
        scale (one scaled glow per pulse step, cached like the pulsed icon).

        Args:
            icon: the icon at its base size
            scale / step: the pulse's quantised scale and its cache key
            top_left: where the pulsed icon is drawn
        """
        if brightness <= 0.01:
            return
        base, scratch, offset = self._outline_grey(icon, ('icon', icon.get_size()), self._icon_reach())
        grey = base
        if abs(scale - 1.0) > 1e-6:
            def build():
                return pygame.transform.smoothscale(base, (max(1, int(base.get_width() * scale + 0.5)),
                                                           max(1, int(base.get_height() * scale + 0.5))))
            grey, scratch = self._grey(('icon pulse', icon.get_size(), step), build)
        colour = light_fx.scaled_colour(ICON_GLOW_STYLE['colour'], min(1.0, brightness))
        _add_tinted(screen, grey, scratch, colour,
                    (int(top_left[0] + offset[0] * scale), int(top_left[1] + offset[1] * scale)))

    # ---------- the backdrop ----------

    def prepare_backdrop(self, screen):
        """
        The vignette as a multiply surface for this screen, baked once (~8 ms at
        1600x900, so when the screen opens rather than in its first frame).
        """
        size = screen.get_size()
        cache = self._kit['darken']
        darken = cache.get(size)
        if darken is None:
            style = BACKDROP_STYLE
            vignette = light_fx.vignette_surface(size, (0, 0, 0), style['centre_alpha'], style['edge_alpha'],
                                                 inner=style['inner'], outer=style['outer'])
            darken = pygame.Surface(size, 0, screen)
            darken.fill((255, 255, 255))
            darken.blit(vignette, (0, 0))      # white under the black wash: 255 - its alpha
            cache[size] = darken
        return darken

    def darken(self, screen):
        """Darken the screen behind the battle screen with the vignette (one multiply)."""
        screen.blit(self.prepare_backdrop(screen), (0, 0), special_flags=MULT)
