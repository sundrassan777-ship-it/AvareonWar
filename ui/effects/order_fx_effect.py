# -*- coding: utf-8 -*-
"""
Order Effects (light)

The map's input marks drawn as light, in the style of the production rays and
the hero ability effects (order FX pass, 2026-10): the ring round a selected
banner or building, the arrows of movement orders, and the reticle on a
selected army's order destinations. Select (ring) -> order (arrow) -> target
(reticle) read as one input language.

Pieces:
    OrderArrow   one arrow to draw: world points (source, [via,] target), kind
                 ('attack' / 'own' / 'ally' / 'hovered' / 'cancelled'), army
                 count, whether it is an ally's order, and the cancel
                 animation's fade and shake
    OrderLight   the shared renderer (one per MapRenderer): sprite caches, ring
                 frames and arrow geometry. draw_selection(), draw_arrows(),
                 draw_reticle(), draw_beckon() (a campaign / tutorial "click here")

Cost rules (as the hero effects, see docs/PERFORMANCE_ROADMAP.md):
- each layer of a mark is one Surface.blits() call, or one blit for a ring
- brightness is quantized and baked into cached sprites and ring frames
- arrow geometry is cached per (route, zoom) relative to the camera origin:
  panning only adds an offset; the flow animates by picking sprites, nothing moves
- new sprites and ring frames per frame are capped (build budgets): no hitch
- arrows off screen are skipped before any per-bead work

Styles: order_fx_style.py. Preview / tune / measure: tools/order_fx_preview.py.
"""

import math
from collections import OrderedDict

import pygame

from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, TintSprites, SoftRing, path_beads, path_lengths, path_point
from ui.effects.order_fx_style import ORDER_FX_STYLE

ADD = pygame.BLEND_RGB_ADD
_TWO_PI = 2.0 * math.pi


def _even(value):
    return max(2, int(value) & ~1)


# A stable threshold per bead index for the cancel fizzle: a bead stays lit while
# the arrow's fade is above its threshold, so the beads go out one by one
_FIZZLE = [((i * 2654435761) & 0xFFFF) / 65536.0 for i in range(97)]


def _fizzled(points, fade):
    """The points (beads) still lit at this fade (0-1) of a fizzling arrow."""
    return [p for i, p in enumerate(points) if _FIZZLE[i % 97] < fade]


def _crest_shape(base, crest):
    """
    Brightness by u = phase ahead of a crest (0-255): a sharp front and a long
    fading trail behind it, so the crests read as flowing one way.
    """
    return [base + crest * max(math.exp(-u / 6.0), math.exp(-(256 - u) / 70.0)) for u in range(256)]


class OrderArrow:
    """
    One arrow to draw.

    Args:
        points: world points - source, optional waypoint (a Captain's 2-hop), target
        kind: the order's kind - 'attack' | 'own' | 'ally' (GameState.order_kind) -
            or 'hovered' / 'cancelled' (order_fx_style ARROWS['kinds'])
        count: armies on the route, shown on the badge (0 = no badge)
        allied: an ally's order (simultaneous mode): dimmer, no flow (ARROWS['allied'])
        fade: brightness 0-1 (the cancel animation fades it out)
        shake: sideways screen offset in px (the cancel animation)
    """

    __slots__ = ('points', 'kind', 'count', 'allied', 'fade', 'shake')

    def __init__(self, points, kind='own', count=0, allied=False, fade=1.0, shake=0.0):
        self.points = tuple((float(x), float(y)) for x, y in points)
        self.kind = kind
        self.count = count
        self.allied = allied
        self.fade = fade
        self.shake = shake


class _ArrowPath:
    """
    One arrow's geometry at one zoom, relative to the camera origin: sprite
    top-left corners (whole px) to which the origin is added each frame.
    """

    __slots__ = ('beads', 'tints', 'head', 'head_tints', 'tip', 'head_phase', 'badge', 'bbox')

    def __init__(self, beads, tints, head, head_tints, tip, head_phase, badge, bbox):
        self.beads = beads            # [(x, y, phase)] shaft light
        self.tints = tints            # [(x, y)] shaft colour band
        self.head = head              # [(x, y)] chevron light
        self.head_tints = head_tints  # [(x, y)] chevron colour band
        self.tip = tip                # (x, y) centre of the tip
        self.head_phase = head_phase  # flow phase at the tip
        self.badge = badge            # (x, y) centre of the army count badge
        self.bbox = bbox              # (x0, y0, x1, y1) everything drawn


class OrderLight:
    """
    The shared order effect renderer (one per MapRenderer, rebuilt with the
    display format like the other light renderers).

    Args:
        style: order_fx_style.ORDER_FX_STYLE
    """

    MAX_PATHS = 64       # arrow geometries kept (LRU): every arrow on screen at one zoom
    MAX_TABLES = 96      # 256-entry sprite tables kept (LRU)

    def __init__(self, style=ORDER_FX_STYLE):
        self.style = style
        self.glow = GlowSprites()
        self.tint = TintSprites()
        selection = style['selection']
        self.pulse_ring = SoftRing(selection['pulses']['width'])
        self.band_ring = SoftRing(selection['ring']['tint_width'])
        self.reticle_ring = SoftRing(style['reticle']['width'])
        self.beckon_ring = SoftRing(style['reticle']['width'])
        self._rings = (self.pulse_ring, self.band_ring, self.reticle_ring, self.beckon_ring)
        self._paths = OrderedDict()      # (points, zoom, radius, lift) -> _ArrowPath
        self._tables = OrderedDict()     # sprite tables (_table)
        self._circles = {}               # (radius, diameter, spacing, crests) -> ring bead offsets
        self._nothing = light_fx.new_black_surface(2)   # adds nothing: stands in for level 0
        warm = style['warm_white']

        def colours(spec):
            raw = tuple(spec['colour'])
            return raw, light_fx.light_colour(raw, spec['white_mix'], warm)

        self.selection_colours = colours(selection)
        self.arrow_colours = {kind: colours(spec) for kind, spec in style['arrows']['kinds'].items()}
        self.reticle_colours = {kind: colours(spec) for kind, spec in style['reticle']['kinds'].items()}
        self.beckon_colours = colours(style['beckon'])
        arrows = style['arrows']
        self._shaft_shape = _crest_shape(arrows['base'], arrows['crest'])
        self._head_shape = _crest_shape(arrows['head']['base'], arrows['head']['crest'])
        ring = selection['ring']
        self._ring_shape = [ring['base'] + ring['crest'] * (0.5 + 0.5 * math.cos(_TWO_PI * u / 256.0))
                            for u in range(256)]
        self.paths_built = 0

    # ---------- frame ----------

    def begin_frame(self):
        """Once per rendered frame, before any mark is drawn: resets the build budgets."""
        self.glow.begin_frame()
        self.tint.begin_frame()
        for ring in self._rings:
            ring.begin_frame()

    def prewarm(self, radii):
        """
        Build what the first frames would otherwise pay for (at load): the ring
        bases, and the bead and tint sprites of every arrow kind, the selection
        ring and the reticle ticks at every plot radius.
        """
        for ring in self._rings:
            ring.prewarm()
        arrows = self.style['arrows']
        selection = self.style['selection']['ring']
        ticks = self.style['reticle']['ticks']
        tint = arrows['tint']
        for radius in sorted(set(radii)):
            for kind, (raw, colour) in self.arrow_colours.items():
                self.glow.prewarm([_even(arrows['size'] * radius)], colour, profile='bead')
                self.tint.prewarm([_even(tint['size'] * radius)], raw, [tint['alpha']],
                                  tint.get('softness', 1.5))
                if kind != 'cancelled':
                    self.glow.prewarm([_even(arrows['head']['flare'] * radius)], colour)
            raw, colour = self.selection_colours
            self.glow.prewarm([_even(selection['size'] * radius)], colour, profile='bead')
            for raw, colour in self.reticle_colours.values():
                self.glow.prewarm([_even(ticks['size'] * radius)], colour, profile='bead')
                self.tint.prewarm([_even(2.0 * ticks['size'] * radius)], raw, [ticks['tint']])
            chevron = self.style['beckon']['chevron']
            raw, colour = self.beckon_colours
            self.glow.prewarm([_even(chevron['size'] * radius)], colour,
                              [int(GlowSprites.LEVELS * chevron['intensity'] + 0.5)], 'bead')
            self.tint.prewarm([_even(2.0 * chevron['size'] * radius)], raw, [chevron['tint']])

    # ---------- tables ----------

    def _table(self, key, ladder, shape, brightness):
        """
        256 sprites, one per phase: shape[u] * brightness on the ladder's levels
        (level 0 = nothing). Cached by key and the brightness (48 steps).
        """
        step = int(brightness * 48 + 0.5)
        full = key + (step,)
        table = self._tables.get(full)
        if table is None:
            steps = GlowSprites.LEVELS
            scale = steps * step / 48.0
            nothing = self._nothing
            table = []
            for value in shape:
                level = min(steps, int(scale * value + 0.5))
                table.append(ladder[level] if level > 0 else nothing)
            self._tables[full] = table
            if len(self._tables) > self.MAX_TABLES:
                self._tables.popitem(last=False)
        else:
            self._tables.move_to_end(full)
        return table

    # ---------- selection ring ----------

    def _circle(self, radius, diameter, spacing, crests):
        """Bead top-left offsets round a circle of this radius, with their crest phase."""
        key = (radius, diameter, spacing, crests)
        beads = self._circles.get(key)
        if beads is None:
            count = max(8, int(_TWO_PI * radius / max(1.0, spacing)))
            half = diameter >> 1
            beads = []
            for i in range(count):
                a = _TWO_PI * i / count
                beads.append((int(round(math.cos(a) * radius)) - half,
                              int(round(math.sin(a) * radius)) - half,
                              int(256 * crests * i / count) & 255))
            self._circles[key] = beads
            if len(self._circles) > 64:
                self._circles.pop(next(iter(self._circles)))
        return beads

    def draw_selection(self, view, x, y, target_radius, clock):
        """
        The selection ring round a plot or army circle of target_radius px
        centred on (x, y): pulses growing outward, the green band, and the ring
        of light with crests running round it.
        """
        selection = self.style['selection']
        ring = selection['ring']
        pulses = selection['pulses']
        radius = view.radius
        r = target_radius + ring['gap'] * radius
        reach = int(r * pulses['reach']) + 4
        if not view.visible(x, y, reach):
            return
        screen = view.screen
        x, y = int(x), int(y)
        raw, colour = self.selection_colours

        # Pulses: each leaves the ring, grows outward and fades
        count = pulses['count']
        levels = SoftRing.LEVELS
        for k in range(count):
            u = (clock / pulses['period'] + k / float(count)) % 1.0
            grow = 1.0 - (1.0 - u) ** 2
            pulse_r = int(r * (1.0 + (pulses['reach'] - 1.0) * grow))
            fade = min(1.0, u / 0.08) * (1.0 - u) ** 1.5
            band = self.pulse_ring.tint_frame(pulse_r, raw, pulses['tint'] * fade)
            if band is not None:
                half = band.get_width() >> 1
                screen.blit(band, (x - half, y - half))
            light = self.pulse_ring.frame(pulse_r, colour, int(levels * pulses['intensity'] * fade + 0.5))
            if light is not None:
                half = light.get_width() >> 1
                screen.blit(light, (x - half, y - half), special_flags=ADD)

        # The ring: green band under it, then beads of light with crests running round
        band = self.band_ring.tint_frame(int(r), raw, ring['tint'])
        if band is not None:
            half = band.get_width() >> 1
            screen.blit(band, (x - half, y - half))
        diameter = _even(ring['size'] * radius)
        ladder = self.glow.ladder(diameter, colour, 'bead')
        if ladder is None:
            return
        table = self._table(('ring', diameter, colour), ladder, self._ring_shape, ring['intensity'])
        beads = self._circle(int(r), diameter, diameter * ring['spacing'], ring['crests'])
        shift = int(256.0 * clock * ring['speed'] * ring['crests']) & 255
        screen.blits([(table[(p - shift) & 255], (x + dx, y + dy), None, ADD) for dx, dy, p in beads],
                     doreturn=False)

    # ---------- destination reticle ----------

    def draw_reticle(self, view, x, y, target_radius, kind, clock):
        """
        The mark on an order's destination round an army circle of target_radius
        px: a ring in the order kind's colour ('attack' / 'own' / 'ally'), and on
        an attack four ticks easing in and out.
        """
        reticle = self.style['reticle']
        ticks = reticle['ticks']
        radius = view.radius
        r = target_radius + reticle['gap'] * radius
        outer = r + (ticks['gap'] + ticks['travel'] + ticks['length'] + ticks['size']) * radius
        if not view.visible(x, y, outer):
            return
        screen = view.screen
        x, y = int(x), int(y)
        if kind not in self.reticle_colours:
            kind = 'attack'
        raw, colour = self.reticle_colours[kind]
        breath = 0.5 + 0.5 * math.sin(_TWO_PI * reticle['breath'] * clock)

        band = self.reticle_ring.tint_frame(int(r), raw, reticle['tint'])
        if band is not None:
            half = band.get_width() >> 1
            screen.blit(band, (x - half, y - half))
        level = int(SoftRing.LEVELS * reticle['intensity'] * (0.7 + 0.3 * breath) + 0.5)
        light = self.reticle_ring.frame(int(r), colour, level)
        if light is not None:
            half = light.get_width() >> 1
            screen.blit(light, (x - half, y - half), special_flags=ADD)
        if not reticle['kinds'][kind].get('ticks'):
            return

        # Ticks at N / E / S / W: closest to the ring as the ring is brightest ("locking on")
        diameter = _even(ticks['size'] * radius)
        tint_diameter = _even(2.0 * ticks['size'] * radius)
        spacing = max(1.0, diameter * ticks['spacing'])
        count = max(2, int(ticks['length'] * radius / spacing) + 1)
        inner = r + (ticks['gap'] + ticks['travel'] * (1.0 - breath)) * radius
        sprite = self.glow.sprite(diameter, colour, int(GlowSprites.LEVELS * ticks['intensity'] + 0.5),
                                  'bead')
        halo = self.tint.sprite(tint_diameter, raw, ticks['tint'])
        half, tint_half = diameter >> 1, tint_diameter >> 1
        points = []
        for ux, uy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            for k in range(count):
                d = inner + k * spacing
                points.append((x + int(ux * d), y + int(uy * d)))
        if halo is not None:
            screen.blits([(halo, (px - tint_half, py - tint_half)) for px, py in points], doreturn=False)
        if sprite is not None:
            screen.blits([(sprite, (px - half, py - half), None, ADD) for px, py in points],
                         doreturn=False)

    # ---------- campaign / tutorial "click here" ----------

    def draw_beckon(self, view, x, y, target_radius, clock):
        """
        A gold "click here" round a plot of target_radius px centred on (x, y):
        pulses closing in on a breathing ring - the opposite motion of the
        selection ring - and a chevron of light bobbing above it, pointing down.
        """
        beckon = self.style['beckon']
        pulses = beckon['pulses']
        chevron = beckon['chevron']
        radius = view.radius
        r = target_radius + beckon['gap'] * radius
        above = r + (chevron['height'] + chevron['bob'] + chevron['arm'] + chevron['size']) * radius
        if not view.visible(x, y, max(r * pulses['reach'], above) + 4):
            return
        screen = view.screen
        x, y = int(x), int(y)
        raw, colour = self.beckon_colours
        levels = SoftRing.LEVELS
        ring = self.beckon_ring

        # Pulses: from the outer edge in to the ring, speeding up and brightening
        count = pulses['count']
        for k in range(count):
            u = (clock / pulses['period'] + k / float(count)) % 1.0
            pulse_r = int(r * (pulses['reach'] - (pulses['reach'] - 1.0) * u * u))
            fade = min(1.0, u / 0.15) * min(1.0, (1.0 - u) / 0.08) * (0.25 + 0.75 * u)
            band = ring.tint_frame(pulse_r, raw, pulses['tint'] * fade)
            if band is not None:
                half = band.get_width() >> 1
                screen.blit(band, (x - half, y - half))
            light = ring.frame(pulse_r, colour, int(levels * pulses['intensity'] * fade + 0.5))
            if light is not None:
                half = light.get_width() >> 1
                screen.blit(light, (x - half, y - half), special_flags=ADD)

        # The ring, breathing
        breath = 0.5 + 0.5 * math.sin(_TWO_PI * beckon['breath'] * clock)
        band = ring.tint_frame(int(r), raw, beckon['tint'])
        if band is not None:
            half = band.get_width() >> 1
            screen.blit(band, (x - half, y - half))
        light = ring.frame(int(r), colour, int(levels * beckon['intensity'] * (0.7 + 0.3 * breath) + 0.5))
        if light is not None:
            half = light.get_width() >> 1
            screen.blit(light, (x - half, y - half), special_flags=ADD)

        # The chevron above the plot, bobbing, its tip pointing down at it
        diameter = _even(chevron['size'] * radius)
        tint_diameter = _even(2.0 * chevron['size'] * radius)
        spacing = max(1.0, diameter * chevron['spacing'])
        bob = chevron['bob'] * radius * math.sin(_TWO_PI * chevron['bob_speed'] * clock)
        tip_y = y - r - chevron['height'] * radius + bob
        angle = math.radians(chevron['angle'])
        dx, dy = math.sin(angle), -math.cos(angle)
        points = [(x, int(tip_y))]
        steps = int(chevron['arm'] * radius / spacing)
        for side in (-1.0, 1.0):
            for k in range(1, steps + 1):
                points.append((int(x + side * dx * k * spacing), int(tip_y + dy * k * spacing)))
        halo = self.tint.sprite(tint_diameter, raw, chevron['tint'])
        sprite = self.glow.sprite(diameter, colour, int(GlowSprites.LEVELS * chevron['intensity'] + 0.5), 'bead')
        if halo is not None:
            th = tint_diameter >> 1
            screen.blits([(halo, (px - th, py - th)) for px, py in points], doreturn=False)
        if sprite is not None:
            hd = diameter >> 1
            screen.blits([(sprite, (px - hd, py - hd), None, ADD) for px, py in points], doreturn=False)

    # ---------- arrows ----------

    def _path(self, arrow, view, lift):
        """The arrow's geometry at this zoom (cached; built from the style)."""
        key = (arrow.points, round(view.zoom, 5), view.radius, lift)
        path = self._paths.get(key)
        if path is None:
            path = self._build_path(arrow.points, view.zoom, view.radius, lift)
            self._paths[key] = path
            self.paths_built += 1
            if len(self._paths) > self.MAX_PATHS:
                self._paths.popitem(last=False)
        else:
            self._paths.move_to_end(key)
        return path

    def _build_path(self, points, zoom, radius, lift):
        arrows = self.style['arrows']
        head = arrows['head']
        tint = arrows['tint']
        corners = [(x * zoom, y * zoom - lift) for x, y in points]

        # Each leg a quadratic Bezier bowed to the right of travel (screen y down),
        # so an arrow A->B and one B->A run side by side instead of on top
        dense = [corners[0]]
        first_leg_end = None
        for i in range(len(corners) - 1):
            (sx, sy), (ex, ey) = corners[i], corners[i + 1]
            dx, dy = ex - sx, ey - sy
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            # The curve's peak offset is half the control point's
            bow = 2.0 * min(arrows['bow'] * length, arrows['max_bow'] * radius)
            cx = (sx + ex) / 2.0 - dy / length * bow
            cy = (sy + ey) / 2.0 + dx / length * bow
            steps = max(6, int(length / 6.0))
            for k in range(1, steps + 1):
                t = k / float(steps)
                a, b, c = (1.0 - t) ** 2, 2.0 * (1.0 - t) * t, t * t
                dense.append((a * sx + b * cx + c * ex, a * sy + b * cy + c * ey))
            if first_leg_end is None:
                first_leg_end = len(dense) - 1
        lengths = path_lengths(dense)
        total = lengths[-1]

        # Gaps at both ends, shrunk on short routes so a head always fits
        start = arrows['start_gap'] * radius
        end = arrows['end_gap'] * radius
        shortest = 1.2 * head['length'] * radius
        if total - start - end < shortest:
            share = max(0.0, (total - shortest) / (start + end)) if start + end > 0 else 0.0
            start, end = start * share, end * share
        stop = max(start, total - end)

        diameter = _even(arrows['size'] * radius)
        half = diameter >> 1
        spacing = max(1.0, diameter * arrows['spacing'])
        tint_diameter = _even(tint['size'] * radius)
        tint_half = tint_diameter >> 1
        tint_spacing = max(1.0, tint_diameter * tint['spacing'])
        wave = max(1.0, arrows['wave_length'] * radius)

        beads = [(int(x) - half, int(y) - half, int(256.0 * s / wave) & 255)
                 for x, y, s in path_beads(dense, spacing, start, stop)]
        tints = [(int(x) - tint_half, int(y) - tint_half)
                 for x, y, s in path_beads(dense, tint_spacing, start, stop)]

        # Chevron head: two arms back from the tip
        tip_x, tip_y, ux, uy = path_point(dense, lengths, stop)
        angle = math.radians(head['angle'])
        arm = head['length'] * radius
        heads, head_tints = [], []
        for side in (-1.0, 1.0):
            ca, sa = math.cos(angle), math.sin(angle) * side
            bx, by = -(ux * ca - uy * sa), -(uy * ca + ux * sa)
            k = 1
            while k * spacing <= arm + 1e-6:
                heads.append((int(tip_x + bx * k * spacing) - half, int(tip_y + by * k * spacing) - half))
                k += 1
            k = 1
            while k * tint_spacing <= arm + 1e-6:
                head_tints.append((int(tip_x + bx * k * tint_spacing) - tint_half,
                                   int(tip_y + by * k * tint_spacing) - tint_half))
                k += 1

        # Badge in the middle of the drawn path (of the first leg on a 2-hop)
        if len(corners) > 2 and first_leg_end is not None:
            badge_s = (start + min(stop, lengths[first_leg_end])) / 2.0
        else:
            badge_s = (start + stop) / 2.0
        bx, by, _, _ = path_point(dense, lengths, badge_s)

        flare = _even(head['flare'] * radius)
        pad = max(tint_diameter, flare)
        xs = [x for x, y in dense]
        ys = [y for x, y in dense]
        bbox = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
        return _ArrowPath(beads, tints, heads, head_tints, (tip_x, tip_y),
                          int(256.0 * stop / wave) & 255, (bx, by), bbox)

    def draw_arrows(self, view, arrows, clock, lift=0, badge=None):
        """
        Draw the arrows: every colour band first, then every arrow's light, then
        the army count badges on top (badge(pos, count, colour) draws one).
        An ally's order is dimmer and doesn't flow; a fizzling kind (cancelled)
        loses its beads one by one as it fades.

        Args:
            lift: px the arrow ends are raised above their world points (the army
                circle sits above its banner's anchor)
        """
        style = self.style['arrows']
        head_style = style['head']
        tint = style['tint']
        screen = view.screen
        ox, oy = int(round(view.ax)), int(round(view.ay))
        width, height = view.width, view.height
        radius = view.radius
        diameter = _even(style['size'] * radius)
        tint_diameter = _even(tint['size'] * radius)
        flare = _even(head_style['flare'] * radius)
        flare_half = flare >> 1
        softness = tint.get('softness', 1.5)
        flow_shift = int(256.0 * clock * style['flow']) & 255
        steps = GlowSprites.LEVELS
        allied = style['allied']

        shown = []
        for arrow in arrows:
            if len(arrow.points) < 2 or arrow.fade <= 0.02:
                continue
            path = self._path(arrow, view, lift)
            ax = ox + int(arrow.shake)
            x0, y0, x1, y1 = path.bbox
            if x1 + ax < 0 or y1 + oy < 0 or x0 + ax > width or y0 + oy > height:
                continue
            shown.append((arrow, path, ax))

        # Colour bands under all the light
        for arrow, path, ax in shown:
            kind = style['kinds'].get(arrow.kind, style['kinds']['own'])
            raw, _ = self.arrow_colours.get(arrow.kind, self.arrow_colours['own'])
            strength = arrow.fade * (allied['tint'] if arrow.allied else 1.0)
            sprite = self.tint.sprite(tint_diameter, raw, tint['alpha'] * strength, softness)
            if sprite is not None:
                tints, head_tints = path.tints, path.head_tints
                if kind.get('fizzle') and arrow.fade < 1.0:
                    tints, head_tints = _fizzled(tints, arrow.fade), _fizzled(head_tints, arrow.fade)
                seq = [(sprite, (x + ax, y + oy)) for x, y in tints]
                seq += [(sprite, (x + ax, y + oy)) for x, y in head_tints]
                screen.blits(seq, doreturn=False)

        # Light: the shaft with its flowing crests, the head, the flare at the tip
        for arrow, path, ax in shown:
            kind = style['kinds'].get(arrow.kind, style['kinds']['own'])
            _, colour = self.arrow_colours.get(arrow.kind, self.arrow_colours['own'])
            ladder = self.glow.ladder(diameter, colour, 'bead')
            if ladder is None:
                continue   # sprites still being built (within the frame budget)
            beads, head = path.beads, path.head
            if kind.get('fizzle'):
                # The beads still lit keep most of their light; the rest have gone out
                brightness = kind['intensity'] * (0.5 + 0.5 * arrow.fade)
                if arrow.fade < 1.0:
                    beads, head = _fizzled(beads, arrow.fade), _fizzled(head, arrow.fade)
            else:
                brightness = kind['intensity'] * arrow.fade
            flowing = kind.get('flowing', True)
            if arrow.allied:
                brightness *= allied['brightness']
                flowing = False
            shift = flow_shift if flowing else 0
            table = self._table(('shaft', diameter, colour), ladder, self._shaft_shape, brightness)
            seq = [(table[(p - shift) & 255], (x + ax, y + oy), None, ADD) for x, y, p in beads]
            u = (path.head_phase - shift) & 255
            head_level = min(steps, int(steps * brightness * self._head_shape[u] + 0.5))
            if head_level > 0:
                sprite = ladder[head_level]
                seq += [(sprite, (x + ax, y + oy), None, ADD) for x, y in head]
            flare_level = int(steps * brightness * head_style['flare_intensity'] * self._head_shape[u] + 0.5)
            if flare_level > 0:
                sprite = self.glow.sprite(flare, colour, min(steps, flare_level))
                if sprite is not None:
                    seq.append((sprite, (int(path.tip[0]) + ax - flare_half,
                                         int(path.tip[1]) + oy - flare_half), None, ADD))
            screen.blits(seq, doreturn=False)

        if badge is not None:
            for arrow, path, ax in shown:
                if arrow.count:
                    raw, _ = self.arrow_colours.get(arrow.kind, self.arrow_colours['own'])
                    badge((int(path.badge[0]) + ax, int(path.badge[1]) + oy), arrow.count, raw)
