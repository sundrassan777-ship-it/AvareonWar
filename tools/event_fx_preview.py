# -*- coding: utf-8 -*-
"""
Event Effects Preview (dev tool)

Live preview of the event effects of the event FX pass on the real Avareon map,
to tune their look and check their frame cost:
- battle and alliance arrival markers, yours or greyed, and the army overflow
  warning (ui/effects/marker_fx_effect.py, styled in marker_fx_style.py)
- a Keep -> Castle upgrade finishing (plot_fx_style.py 'castle_complete', played
  by the hero ability cue engine)
- the Master Negotiator glow round the map (hero_fx_style.py 'negotiator_glow')
- the turn banner (ui/effects/turn_announcement_effect.py) over all of it

The map, territory fills, plots and banners are drawn as tools/order_fx_preview.py
draws them; the markers go over the banners and the castle bursts over everything,
as in the game.

Run from the game folder:
    py tools/event_fx_preview.py                    live window
    py tools/event_fx_preview.py --look 3d          start in the 3D map look
    py tools/event_fx_preview.py --sheet out.png    stills: markers over time at three zooms,
                                                    a Castle finishing, the turn banner
    py tools/event_fx_preview.py --bench            effect cost per frame (avg / worst ms)

Controls (live):
    B  battle marker on the territory under the mouse (again: greyed, again: off)
    A  alliance marker on the territory under the mouse (again: greyed, again: off)
    W  overflow warning on the territory under the mouse (toggle)
    C  a Castle upgrade finishing on the plot under the mouse   X  clear
    N  the turn banner (again: a name too long for one line)
    G  the Master Negotiator glow (toggle)
    mouse wheel  zoom     drag  pan     L  2D / 3D look     Space  pause     Esc  quit
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

if '--sheet' in sys.argv or '--bench' in sys.argv:
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

import map_data  # noqa: E402
from config.constants import ARMY_CIRCLE_RADIUS, ARMY_CIRCLE_DRAW_SCALE, ARMY_CIRCLE_DRAW_LIFT  # noqa: E402
from tools.plot_fx_preview import ui_scale_for, plot_radii, MIN_ZOOM, MAX_ZOOM  # noqa: E402
from tools.hero_fx_preview import focus_territory  # noqa: E402
from tools.order_fx_preview import OrderPreview  # noqa: E402
from ui.effects.hero_fx_effect import HeroAbilityEffect, stable_seed  # noqa: E402
from ui.effects.light_fx import vignette_surface, RisingMotes  # noqa: E402
from ui.effects.marker_fx_style import get_marker_fx_style  # noqa: E402
from ui.effects.marker_fx_effect import MarkerLight  # noqa: E402
from ui.effects.plot_fx_style import get_plot_fx_style  # noqa: E402
from ui.effects.turn_announcement_effect import TurnAnnouncementEffect  # noqa: E402

BANNER_NAMES = ('Empire of Naragonthid', 'The Most Serene Republic of the Azincournean Highlands')


class EventPreview(OrderPreview):
    """The order preview's map, plots and banners, plus the event effects."""

    def __init__(self, screen, look):
        self.marker_light = None
        self.markers = {}        # territory -> (kind, greyed)
        self.overflow = set()    # territories
        self.banner = None       # TurnAnnouncementEffect
        self.banner_names = 0    # announcements so far (cycles BANNER_NAMES)
        self.negotiator_since = None   # preview clock when Master Negotiator was cast
        self._negotiator = None        # (size, wash, RisingMotes)
        self._labels = {}
        super().__init__(screen, look)

    def load_look(self, look):
        super().load_look(look)
        self.marker_style = get_marker_fx_style(self.look)
        self.castle_style = get_plot_fx_style(self.look)['castle_complete']
        start = time.perf_counter()
        self.marker_light = MarkerLight(self.marker_style)
        self.marker_light.prewarm(plot_radii())
        self.marker_prewarm_ms = (time.perf_counter() - start) * 1000
        self.markers = {}
        self.overflow = set()

    # ---------- events ----------

    def cycle_marker(self, territory, kind):
        """Off -> yours -> greyed -> off (switching kind starts again at yours)."""
        if territory not in self.world_centres:
            return
        current = self.markers.get(territory)
        if current is None or current[0] != kind:
            self.markers[territory] = (kind, False)
        elif not current[1]:
            self.markers[territory] = (kind, True)
        else:
            del self.markers[territory]

    def castle_complete(self, territory, index=0):
        """MapRenderer.trigger_castle_upgrade_effect() on this plot."""
        if territory not in self.world_centres:
            return
        seed = stable_seed('castle', territory, index, len(self.effects))
        self.effects.append(HeroAbilityEffect(self.light, self.castle_style,
                                              {'keep': self._plot_world(territory, index)}, seed))

    def announce(self, name=None):
        """A turn banner, as main.py starts one at a turn change."""
        if name is None:
            name = BANNER_NAMES[self.banner_names % len(BANNER_NAMES)]
            self.banner_names += 1
        self.banner = TurnAnnouncementEffect(self.width, self.height, player_name=name)

    def update(self, dt):
        super().update(dt)
        if self.banner is not None:
            self.banner.update(dt)
            if self.banner.is_finished():
                self.banner = None

    def plot_at(self, pos):
        """(territory, plot index) of the plot nearest the mouse in the territory under it."""
        territory = self.territory_at(pos)
        best = None
        for plot in self.plots:
            if plot[0] != territory:
                continue
            x, y = self.to_screen(plot[2], plot[3])
            d = (x - pos[0]) ** 2 + (y - pos[1]) ** 2
            if best is None or d < best[0]:
                best = (d, plot[1])
        return (territory, best[1]) if best else (territory, 0)

    # ---------- drawing ----------

    def _label(self, text, x, y):
        """MapRenderer._draw_marker_label()."""
        surfaces = self._labels.get(text)
        if surfaces is None:
            shadow = self.marker_style['marker']['label_shadow']
            surfaces = self._labels[text] = (self._font.render(text, True, shadow),
                                             self._font.render(text, True, (255, 255, 255)))
        rect = surfaces[1].get_rect(center=(x, y))
        self.screen.blit(surfaces[0], rect.move(1, 1))
        self.screen.blit(surfaces[1], rect)

    def _draw_negotiator_glow(self):
        """Game.draw_negotiator_glow() over the whole preview window (the game's map area)."""
        if self.negotiator_since is None:
            return
        glow = self.hero_style['negotiator_glow']
        motes = glow['motes']
        size = (self.width, self.height)
        if self._negotiator is None or self._negotiator[0] != size:
            wash = vignette_surface(size, glow['colour'], glow['centre_alpha'], glow['edge_alpha'],
                                    inner=glow['inner'])
            self._negotiator = (size, wash, RisingMotes(motes, 'master-negotiator', self.height / 900.0))
        _, wash, rising = self._negotiator
        elapsed = self.clock - self.negotiator_since
        fade = min(1.0, max(0.0, elapsed / glow['fade']))
        wash.set_alpha(int(255 * fade) if fade < 1.0 else 255)
        self.screen.blit(wash, (0, 0))
        band = motes['band'] * self.height

        def spawn(a, b, index):
            side = int(a * 4.0)
            inset = (a * 4.0 - side) * band
            if side == 0:
                return b * self.width, inset
            if side == 1:
                return self.width - inset, b * self.height
            if side == 2:
                return b * self.width, self.height - inset
            return inset, b * self.height

        raw = tuple(motes['colour'])
        rising.draw(self.screen, self.light.glow, self.light.light_colour(raw, motes['white_mix']),
                    elapsed, fade, spawn, self.light.tint, raw)

    def render(self):
        """One frame; returns the ms spent on the event effects."""
        perf = time.perf_counter
        super().render()
        view = self.view()
        light = self.marker_light
        spent = 0.0
        start = perf()
        light.begin_frame()
        self.light.begin_frame()
        for effect in self.effects:
            effect.render_under(view)
        spent += perf() - start

        start = perf()
        self._draw_negotiator_glow()
        spent += perf() - start

        ui_scale = ui_scale_for(self.zoom)
        circle = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
        lift = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
        for territory in sorted(self.overflow):
            x, y = view.to_screen(self.world_centres[territory])
            start = perf()
            light.draw_overflow(view, x, y - lift, circle, self.clock)
            spent += perf() - start
        for number, (territory, (kind, greyed)) in enumerate(sorted(self.markers.items()), 1):
            x, y = view.to_screen(self.world_centres[territory])
            start = perf()
            light.draw_marker(view, x, y, kind, greyed, self.clock,
                              (stable_seed('marker', territory) & 0xFFFF) / 65536.0 * 8.0)
            spent += perf() - start
            if kind == 'battle':
                offset = (light.icon_half_height(kind, view.radius)
                          + int(self.marker_style['marker']['label_gap'] * view.radius)
                          + self._font.get_height() // 2)
                self._label(f'#{number}', int(x), int(y) + offset)

        start = perf()
        for effect in self.effects:
            effect.render_over(view)
        if self.banner is not None:
            self.banner.render(self.screen)
        spent += perf() - start
        return spent * 1000


def run_live(look, size):
    pygame.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption('Event effects preview')
    preview = EventPreview(screen, look)
    font = pygame.font.SysFont('consolas', 16)
    clock = pygame.time.Clock()
    dragging = False
    history = []
    while True:
        dt = clock.tick(0) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if event.type == pygame.MOUSEWHEEL:
                preview.zoom_by(event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                dragging = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                preview.pan(*event.rel)
            elif event.type == pygame.KEYDOWN:
                mouse = pygame.mouse.get_pos()
                if event.key == pygame.K_b:
                    preview.cycle_marker(preview.territory_at(mouse), 'battle')
                elif event.key == pygame.K_a:
                    preview.cycle_marker(preview.territory_at(mouse), 'alliance')
                elif event.key == pygame.K_w:
                    preview.overflow ^= {preview.territory_at(mouse)} - {None}
                elif event.key == pygame.K_c:
                    preview.castle_complete(*preview.plot_at(mouse))
                elif event.key == pygame.K_n:
                    preview.announce()
                elif event.key == pygame.K_g:
                    preview.negotiator_since = None if preview.negotiator_since is not None else preview.clock
                elif event.key == pygame.K_x:
                    preview.markers = {}
                    preview.overflow = set()
                    preview.effects = []
                    preview.banner = None
                    preview.negotiator_since = None
                elif event.key == pygame.K_l:
                    preview.load_look('2d' if preview.look == '3d' else '3d')
                elif event.key == pygame.K_SPACE:
                    preview.paused = not preview.paused
        if not preview.paused:
            step = min(dt, 0.05)
            preview.clock += step
            preview.update(step)
        start = time.perf_counter()
        fx_ms = preview.render()
        frame_ms = (time.perf_counter() - start) * 1000
        history = (history + [(frame_ms, fx_ms)])[-60:]
        avg = [sum(h[i] for h in history) / len(history) for i in range(2)]
        lines = [
            f"{clock.get_fps():6.1f} FPS   frame {avg[0]:5.2f} ms   event effects {avg[1]:5.2f} ms"
            f"   markers {len(preview.markers)}",
            f"look {preview.look}   zoom {preview.zoom:.2f}{'   PAUSED' if preview.paused else ''}",
            'B battle  A alliance (again: greyed, again: off)  W overflow  C castle done  N turn banner'
            '  G negotiator  X clear  L look',
        ]
        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            pygame.draw.rect(screen, (0, 0, 0), text.get_rect(topleft=(8, 8 + i * 20)).inflate(8, 2))
            screen.blit(text, (8, 8 + i * 20))
        pygame.display.flip()


def _scene(preview, name, territory):
    """Set up one sheet / bench scene round the focus territory."""
    preview.markers = {}
    preview.overflow = set()
    preview.effects = []
    preview.banner = None
    preview.negotiator_since = None
    neighbours = preview._nearest_neighbours(territory)
    if name == 'markers':
        # Yours and greyed of both kinds, and an overflow warning
        preview.markers[territory] = ('battle', False)
        kinds = (('alliance', False), ('battle', True), ('alliance', True))
        for n, kind in zip(neighbours, kinds):
            preview.markers[n] = kind
        if len(neighbours) > 3:
            preview.overflow.add(neighbours[3])
    elif name == 'castle':
        preview.castle_complete(territory)
    elif name.startswith('banner'):
        preview.announce(BANNER_NAMES[1] if name == 'banner long' else BANNER_NAMES[0])
    elif name == 'negotiator':
        preview.negotiator_since = 0.0
    elif name.startswith('markers '):
        # Many markers across the view (the bench's worst case)
        count = int(name.split()[1])
        cx, cy = preview.centre[0] * preview.map_scale, preview.centre[1] * preview.map_scale
        near = sorted(preview.world_centres, key=lambda t: (preview.world_centres[t][0] - cx) ** 2
                      + (preview.world_centres[t][1] - cy) ** 2)
        for i, t in enumerate(near[:count]):
            preview.markers[t] = ('battle' if i % 3 else 'alliance', i % 4 == 3)


def run_sheet(path, look, size, magnify=2):
    """Rows: the markers over a pulse period at three zooms, then a Castle upgrade finishing."""
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = EventPreview(screen, look)
    territory = focus_territory(preview)
    font = pygame.font.SysFont('consolas', 15)
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    cell_w, cell_h = 330 * magnify, 230 * magnify
    period = preview.marker_style['marker']['pulses']['period']
    rows = [('markers', zoom, [period * k / 6.0 for k in range(6)]) for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM)]
    rows.append(('castle', 2.4, [0.05, 0.2, 0.4, 0.7, 1.0, 1.5]))
    rows.append(('castle', MAX_ZOOM, [0.05, 0.2, 0.4, 0.7, 1.0, 1.5]))
    rows.append(('banner', 2.4, [0.1, 0.25, 0.5, 0.9, 1.15, 1.35]))
    rows.append(('banner long', 2.4, [0.1, 0.25, 0.5, 0.9, 1.15, 1.35]))
    rows.append(('negotiator', 2.4, [0.2, 0.5, 0.9, 1.5, 2.2, 3.0]))
    sheet = pygame.Surface((cell_w * 6, (cell_h + 20) * len(rows)))
    sheet.fill((30, 30, 30))
    for row, (name, zoom, times) in enumerate(rows):
        preview.zoom = zoom
        preview.centre = list(raw_centre)
        preview.clamp()
        cx, cy = preview.to_screen(*raw_centre)
        widen = max(1.0, zoom / 2.0) if name == 'markers' else 1.0
        crop_w, crop_h = int(330 * widen * zoom / 2.4), int(230 * widen * zoom / 2.4)
        if name.startswith('banner') or name == 'negotiator':
            # The whole screen
            crop_w, crop_h = preview.width, preview.height
            cx, cy = preview.width // 2, preview.height // 2
        for col, t in enumerate(times):
            _scene(preview, name, territory)
            # A marker shows fully after its fade-in; a cast runs from t = 0
            preview.clock = t + 1.0 if name == 'markers' else (t if name == 'negotiator' else 0.0)
            if name == 'castle':
                for effect in preview.effects:
                    effect.update(t)
            elif preview.banner is not None:
                preview.banner.update(t)
            # Repeat the frame: the first ones build sprites within the frame budget
            for _ in range(12):
                preview.render()
            crop = pygame.Rect(0, 0, crop_w, crop_h)
            crop.center = (cx, cy)
            cell = pygame.transform.smoothscale(screen.subsurface(crop.clip(screen.get_rect())),
                                                (cell_w, cell_h))
            top = row * (cell_h + 20)
            sheet.blit(cell, (col * cell_w, top + 20))
            caption = font.render(f'{name}  t={t:.2f}s  zoom {zoom:.2f}  ({preview.look})', True,
                                  (255, 255, 255))
            sheet.blit(caption, (col * cell_w + 6, top + 2))
    pygame.image.save(sheet, path)
    print(f'Wrote {path} ({territory})')
    pygame.quit()


def run_bench(look, size, frames=180, settle=60):
    """
    Event effect cost per frame at three zooms, from cold caches: the average once
    the caches are filled (after `settle` frames) and the worst frame, which
    includes building them.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = EventPreview(screen, look)
    territory = focus_territory(preview)
    print(f'{look} look, {size[0]}x{size[1]}, focus {territory}; '
          f'marker prewarm {preview.marker_prewarm_ms:.1f} ms')
    print(f"{'zoom':>5} {'scene':>12} {'avg ms':>8} {'worst ms':>9}   (avg once warm; worst incl. cold)")
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM):
        for name in ('markers', 'markers 12', 'castle', 'negotiator'):
            preview.marker_light = MarkerLight(preview.marker_style)
            preview.marker_light.prewarm(plot_radii())
            preview.zoom = zoom
            preview.centre = list(raw_centre)
            preview.clamp()
            _scene(preview, name, territory)
            preview.clock = 0.0
            costs = []
            for _ in range(frames):
                preview.clock += 1.0 / 60
                preview.update(1.0 / 60)
                if name == 'castle' and not preview.effects:
                    preview.castle_complete(territory)
                costs.append(preview.render())
            warm = costs[settle:]
            print(f'{zoom:5.2f} {name:>12} {sum(warm) / len(warm):8.3f} {max(costs):9.3f}')
    light = preview.marker_light
    nbytes = sum(s.get_width() * s.get_height() * s.get_bytesize() for s in light.glow._sprites.values())
    print(f'marker glow sprites: {len(light.glow._sprites)} ({nbytes / 1e6:.1f} MB)')
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description='Event effects preview')
    parser.add_argument('--look', choices=('2d', '3d'), default='2d')
    parser.add_argument('--size', default='1600x850', help='window size, e.g. 1920x1080')
    parser.add_argument('--sheet', help='write a contact sheet of stills to this PNG and exit')
    parser.add_argument('--bench', action='store_true', help="print the effects' frame cost and exit")
    args = parser.parse_args()
    size = tuple(int(v) for v in args.size.lower().split('x'))
    if args.bench:
        run_bench(args.look, size)
    elif args.sheet:
        run_sheet(args.sheet, args.look, size)
    else:
        run_live(args.look, size)


if __name__ == '__main__':
    main()
