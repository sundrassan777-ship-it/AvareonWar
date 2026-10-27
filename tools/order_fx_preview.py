# -*- coding: utf-8 -*-
"""
Order Effects Preview (dev tool)

Live preview of the selection ring, the order arrows and the destination
reticle (ui/effects/order_fx_effect.py) on the real Avareon map, to tune their
look (ui/effects/order_fx_style.py) and check their frame cost. The map,
territory fills and plots are drawn the way the game draws them (via
tools/hero_fx_preview.py), banners as MapRenderer draws them, and the marks in
the game's order: the selection ring on a plot right after it, the reticle and
the selection ring of a banner under it, the arrows over everything.

Run from the game folder:
    py tools/order_fx_preview.py                    live window
    py tools/order_fx_preview.py --look 3d          start in the 3D map look
    py tools/order_fx_preview.py --sheet out.png    stills: rings over time, arrows at three zooms
    py tools/order_fx_preview.py --bench            mark cost per frame (avg / worst ms)

Controls (live):
    click           select the plot or banner under the mouse
    right-click     order from the selected banner to the territory under the mouse
    O  5 orders near the view      X  clear orders      R  reverse of the last order (A <-> B)
    T  a 2-hop order (Captain) from the selected banner
    H  hover the next order's card (gold)    Y  last order is an ally's (cyan)
    K  cancel the last order (red shake)     mouse wheel  zoom     drag  pan
    L  2D / 3D look     Space  pause     Esc  quit
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

import math  # noqa: E402

import pygame  # noqa: E402

import map_data  # noqa: E402
from config.constants import (ARMY_CIRCLE_RADIUS, ARMY_CIRCLE_DRAW_SCALE, ARMY_CIRCLE_DRAW_LIFT,  # noqa: E402
                              ARMY_FLAG_HEIGHT_RATIO, ARROW_CANCEL_DURATION, ARROW_CANCEL_SHAKE_FREQ,
                              ARROW_CANCEL_SHAKE_AMP, BADGE_RADIUS)
from tools.plot_fx_preview import ui_scale_for, plot_radii, MIN_ZOOM, MAX_ZOOM  # noqa: E402
from tools.hero_fx_preview import HeroPreview, focus_territory  # noqa: E402
from ui.effects.order_fx_style import get_order_fx_style  # noqa: E402
from ui.effects.order_fx_effect import OrderLight, OrderArrow  # noqa: E402

FLAG_COLOURS = ('Red', 'Blue', 'Green', 'Yellow')


class OrderPreview(HeroPreview):
    """The hero preview's map, fills and plots, plus banners and the order marks."""

    def __init__(self, screen, look):
        self.order_light = None
        self.orders = []         # [{'route': (from, [via,] to), 'kind': ..., 'count': ...}]
        self.cancelling = []     # [(order, preview clock when cancelled)]
        self.selected = None     # ('plot', territory, index) | ('army', territory)
        self.hovered = None      # index into orders
        self._flags = {}
        self._glows = {}
        self._texts = {}
        self._font = pygame.font.SysFont('arial', 16)   # loaded here: slow, not a mark's cost
        super().__init__(screen, look)

    def load_look(self, look):
        super().load_look(look)
        self.order_style = get_order_fx_style(self.look)
        start = time.perf_counter()
        self.order_light = OrderLight(self.order_style)
        self.order_light.prewarm(plot_radii())
        self.order_prewarm_ms = (time.perf_counter() - start) * 1000
        self.orders = []
        self.cancelling = []
        self.selected = None
        self.hovered = None
        territories = sorted(map_data.TERRITORY_PLOTS)
        self.flag_index = {t: i % len(FLAG_COLOURS) for i, t in enumerate(territories)}

    # ---------- orders ----------

    def add_order(self, route, kind='own', count=10):
        route = tuple(route)
        if len(route) >= 2 and route[0] != route[-1] and all(t in self.world_centres for t in route):
            self.orders.append({'route': route, 'kind': kind, 'count': count})

    def orders_near_view(self, count=5):
        """Orders from the territories nearest the view centre to their nearest neighbours."""
        cx, cy = self.centre[0] * self.map_scale, self.centre[1] * self.map_scale
        near = sorted(self.world_centres, key=lambda t: (self.world_centres[t][0] - cx) ** 2
                      + (self.world_centres[t][1] - cy) ** 2)
        made = 0
        for territory in near:
            neighbours = self._nearest_neighbours(territory)
            if neighbours and made < count:
                self.add_order((territory, neighbours[0]), count=5 + 3 * made)
                made += 1

    def cancel_last(self):
        if self.orders:
            self.cancelling.append((self.orders.pop(), self.clock))
            self.hovered = None

    def arrows(self):
        """The OrderArrows MapRenderer would draw for the current orders."""
        arrows = []
        for i, order in enumerate(self.orders):
            kind = 'hovered' if i == self.hovered else order['kind']
            arrows.append(OrderArrow([self.world_centres[t] for t in order['route']], kind,
                                     order['count']))
        live = []
        for order, since in self.cancelling:
            elapsed = self.clock - since
            progress = elapsed / ARROW_CANCEL_DURATION
            if progress >= 1.0:
                continue
            live.append((order, since))
            shake = math.sin(elapsed * ARROW_CANCEL_SHAKE_FREQ) * ARROW_CANCEL_SHAKE_AMP * (1.0 - progress)
            route = order['route']
            arrows.append(OrderArrow([self.world_centres[route[0]], self.world_centres[route[-1]]],
                                     'cancelled', order['count'], fade=1.0 - progress, shake=shake))
        self.cancelling = live
        return arrows

    def select_at(self, pos):
        """The plot under the mouse, else the banner of the territory under it."""
        view = self.view()
        best = None
        for plot in self.plots:
            x, y = self.to_screen(plot[2], plot[3])
            d = (x - pos[0]) ** 2 + (y - pos[1]) ** 2
            if d <= view.radius ** 2 and (best is None or d < best[0]):
                best = (d, ('plot', plot[0], plot[1]))
        if best is not None:
            self.selected = best[1]
            return
        territory = self.territory_at(pos)
        self.selected = ('army', territory) if territory in self.world_centres else None

    # ---------- drawing ----------

    def _glow(self, colour, radius):
        key = (colour, radius)
        surface = self._glows.get(key)
        if surface is None:
            margin = max(4, radius // 3)
            size = (radius + margin) * 2
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surface, (*colour, 35), (size // 2, size // 2), radius + margin)
            pygame.draw.circle(surface, (*colour, 55), (size // 2, size // 2), radius + margin // 2)
            self._glows[key] = surface
        return surface

    def _flag(self, index, height):
        key = (index, height)
        flag = self._flags.get(key)
        if flag is None:
            base = self._flags.get(index)
            if base is None:
                base = pygame.image.load(f'assets/mapicons/{FLAG_COLOURS[index]}Flag2.png').convert_alpha()
                self._flags[index] = base
            width = max(1, int(height * base.get_width() / base.get_height()))
            flag = pygame.transform.smoothscale(base, (width, height))
            self._flags[key] = flag
        return flag

    def _draw_banner(self, x, y, territory, ui_scale):
        """The army circle and banner, as MapRenderer._draw_army_circle and the flag blit."""
        colour = self.owner_colour.get(territory, (150, 150, 150))
        radius = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
        cy = y - int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
        glow = self._glow(colour, radius)
        self.screen.blit(glow, glow.get_rect(center=(x, cy)))
        dark = tuple(int(c * 0.55) for c in colour)
        pygame.draw.circle(self.screen, dark, (x, cy), radius, max(2, radius // 5))
        flag = self._flag(self.flag_index.get(territory, 0),
                          int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_FLAG_HEIGHT_RATIO))
        self.screen.blit(flag, (x - flag.get_width() // 2, y - flag.get_height()))

    def _badge(self, pos, count, colour):
        """GameHelpers.draw_circle_badge (text cached, as there)."""
        pygame.draw.circle(self.screen, (255, 255, 255), pos, BADGE_RADIUS)
        pygame.draw.circle(self.screen, colour, pos, BADGE_RADIUS, 2)
        text = self._texts.get(count)
        if text is None:
            text = self._texts[count] = self._font.render(str(count), True, (0, 0, 0))
        self.screen.blit(text, text.get_rect(center=pos))

    def render(self):
        """One frame; returns the ms spent on the order marks."""
        perf = time.perf_counter
        self._draw_background()
        self._draw_fills()
        view = self.view()
        light = self.order_light
        light.begin_frame()
        spent = 0.0
        radius = view.radius
        margin = radius * 3

        # Plots, the selected one ringed right after it is drawn (as _render_completed_plot)
        for plot in self.plots:
            x, y = self.to_screen(plot[2], plot[3])
            if not (-margin < x < self.width + margin and -margin < y < self.height + margin):
                continue
            self._draw_plot(x, y, radius, plot[4], plot[5], plot[6])
            if self.selected == ('plot', plot[0], plot[1]):
                start = perf()
                light.draw_selection(view, x, y, radius, self.clock)
                spent += perf() - start

        # Banners: the reticle and the selection ring under the army circle and flag
        ui_scale = ui_scale_for(self.zoom)
        circle = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
        lift = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
        army = self.selected[1] if self.selected and self.selected[0] == 'army' else None
        targets = {}
        for order in self.orders:
            if army is not None and order['route'][0] == army:
                target = order['route'][-1]
                friendly = self.owner_colour.get(target) == self.owner_colour.get(army)
                targets[target] = 'merge' if friendly else 'attack'
        for territory, centre in self.world_centres.items():
            x, y = view.to_screen(centre)
            if not (-margin * 2 < x < self.width + margin * 2 and -margin * 2 < y < self.height + margin * 2):
                continue
            x, y = int(x), int(y)
            start = perf()
            if territory in targets:
                light.draw_reticle(view, x, y - lift, circle, targets[territory], self.clock)
            if territory == army:
                light.draw_selection(view, x, y - lift, circle, self.clock)
            spent += perf() - start
            self._draw_banner(x, y, territory, ui_scale)

        # Arrows over everything, badges on top
        start = perf()
        light.draw_arrows(view, self.arrows(), self.clock, lift=lift, badge=self._badge)
        spent += perf() - start
        return spent * 1000


def run_live(look, size):
    pygame.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption('Order effects preview')
    preview = OrderPreview(screen, look)
    font = pygame.font.SysFont('consolas', 16)
    clock = pygame.time.Clock()
    dragging = moved = False
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
                dragging, moved = True, False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if not moved:
                    preview.select_at(event.pos)
                dragging = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if preview.selected and preview.selected[0] == 'army':
                    preview.add_order((preview.selected[1], preview.territory_at(event.pos)))
            elif event.type == pygame.MOUSEMOTION and dragging:
                if abs(event.rel[0]) + abs(event.rel[1]) > 0:
                    moved = True
                preview.pan(*event.rel)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_o:
                    preview.orders_near_view()
                elif event.key == pygame.K_x:
                    preview.orders = []
                    preview.hovered = None
                elif event.key == pygame.K_r and preview.orders:
                    route = preview.orders[-1]['route']
                    preview.add_order(tuple(reversed(route)))
                elif event.key == pygame.K_t and preview.selected and preview.selected[0] == 'army':
                    first = preview.selected[1]
                    via = preview._nearest_neighbours(first)
                    if via:
                        onward = [t for t in preview._nearest_neighbours(via[0]) if t != first]
                        if onward:
                            preview.add_order((first, via[0], onward[0]))
                elif event.key == pygame.K_h and preview.orders:
                    preview.hovered = 0 if preview.hovered is None else preview.hovered + 1
                    if preview.hovered >= len(preview.orders):
                        preview.hovered = None
                elif event.key == pygame.K_y and preview.orders:
                    order = preview.orders[-1]
                    order['kind'] = 'own' if order['kind'] == 'ally' else 'ally'
                elif event.key == pygame.K_k:
                    preview.cancel_last()
                elif event.key == pygame.K_l:
                    preview.load_look('2d' if preview.look == '3d' else '3d')
                elif event.key == pygame.K_SPACE:
                    preview.paused = not preview.paused
        if not preview.paused:
            preview.clock += min(dt, 0.05)
        start = time.perf_counter()
        marks_ms = preview.render()
        frame_ms = (time.perf_counter() - start) * 1000
        history = (history + [(frame_ms, marks_ms)])[-60:]
        avg = [sum(h[i] for h in history) / len(history) for i in range(2)]
        lines = [
            f"{clock.get_fps():6.1f} FPS   frame {avg[0]:5.2f} ms   order marks {avg[1]:5.2f} ms"
            f"   orders {len(preview.orders)}",
            f"look {preview.look}   zoom {preview.zoom:.2f}   selected {preview.selected}"
            f"{'   PAUSED' if preview.paused else ''}",
            'click select  right-click order  O orders  X clear  R reverse  T 2-hop  H hover'
            '  Y ally  K cancel  L look',
        ]
        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            pygame.draw.rect(screen, (0, 0, 0), text.get_rect(topleft=(8, 8 + i * 20)).inflate(8, 2))
            screen.blit(text, (8, 8 + i * 20))
        pygame.display.flip()


def _scene(preview, name, territory):
    """Set up one sheet / bench scene round the focus territory."""
    preview.orders = []
    preview.cancelling = []
    preview.hovered = None
    preview.selected = None
    neighbours = preview._nearest_neighbours(territory)
    if name == 'select plot':
        preview.selected = ('plot', territory, 0)
    elif name == 'select banner':
        preview.selected = ('army', territory)
    elif name in ('arrows', 'arrows selected'):
        # Own orders to every neighbour, one of them hovered, one an ally's, a
        # 2-hop, a pair A <-> B, and the reticles of the selected banner
        for n in neighbours[:4]:
            preview.add_order((territory, n))
        if len(neighbours) > 1:
            preview.add_order((neighbours[1], territory), kind='ally')
            preview.hovered = 1
        if neighbours:
            first = neighbours[0]
            vias = [t for t in preview._nearest_neighbours(first) if t != territory]
            if vias:
                onward = [t for t in preview._nearest_neighbours(vias[0]) if t not in (first, territory)]
                if onward:
                    preview.add_order((first, vias[0], onward[0]))
            preview.add_order((first, territory))
        if name == 'arrows selected':
            preview.selected = ('army', territory)
    elif name.startswith('arrows '):
        preview.orders_near_view(int(name.split()[1]))


def run_sheet(path, look, size, magnify=2):
    """
    Rows: a selected plot and a selected banner over a pulse period, then the
    arrows (own, hovered, ally, 2-hop, A <-> B, reticles) at three zooms and a
    cancel animation.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = OrderPreview(screen, look)
    territory = focus_territory(preview)
    font = pygame.font.SysFont('consolas', 15)
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    cell_w, cell_h = 330 * magnify, 230 * magnify
    period = preview.order_style['selection']['pulses']['period']
    rows = []
    for name in ('select plot', 'select banner'):
        for zoom in (MIN_ZOOM, MAX_ZOOM):
            rows.append((name, zoom, [period * k / 6.0 for k in range(6)]))
    rows.append(('arrows selected', MIN_ZOOM, [0.0, 0.3, 0.6, 0.9, 1.2, 1.5]))
    rows.append(('arrows selected', 2.4, [0.0, 0.3, 0.6, 0.9, 1.2, 1.5]))
    rows.append(('arrows selected', MAX_ZOOM, [0.0, 0.3, 0.6, 0.9, 1.2, 1.5]))
    rows.append(('cancel', 2.4, [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]))
    sheet = pygame.Surface((cell_w * 6, (cell_h + 20) * len(rows)))
    sheet.fill((30, 30, 30))
    for row, (name, zoom, times) in enumerate(rows):
        preview.zoom = zoom
        preview.centre = list(raw_centre)
        preview.clamp()
        cx, cy = preview.to_screen(*raw_centre)
        # Arrows reach further than the rings: a wider crop at the closer zooms
        widen = 1.0 if name.startswith('select') else max(1.0, zoom / 2.0)
        crop_w, crop_h = int(330 * widen * zoom / 2.4), int(230 * widen * zoom / 2.4)
        for col, t in enumerate(times):
            if name == 'cancel':
                _scene(preview, 'arrows', territory)
                preview.clock = 1.0
                preview.cancelling = [(order, 1.0 - t) for order in preview.orders]
                preview.orders = []
            else:
                _scene(preview, name, territory)
                preview.clock = t
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
    Order mark cost per frame at three zooms, from cold caches: the average once
    the caches are filled (after `settle` frames - a pulse period and more) and
    the worst frame, which includes building them.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = OrderPreview(screen, look)
    territory = focus_territory(preview)
    print(f'{look} look, {size[0]}x{size[1]}, focus {territory}; prewarm {preview.order_prewarm_ms:.1f} ms')
    print(f"{'zoom':>5} {'scene':>18} {'avg ms':>8} {'worst ms':>9}   (avg once warm; worst incl. cold)")
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    scenes = ('select plot', 'select banner', 'arrows 5', 'arrows 20', 'arrows selected')
    for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM):
        for name in scenes:
            # Cold caches each row (the sprites are prewarmed at load, as in the game)
            preview.order_light = OrderLight(preview.order_style)
            preview.order_light.prewarm(plot_radii())
            preview.zoom = zoom
            preview.centre = list(raw_centre)
            preview.clamp()
            _scene(preview, name, territory)
            preview.clock = 0.0
            costs = []
            for _ in range(frames):
                preview.clock += 1.0 / 60
                costs.append(preview.render())
            warm = costs[settle:]
            print(f'{zoom:5.2f} {name:>18} {sum(warm) / len(warm):8.3f} {max(costs):9.3f}')
    # Moving cameras with 20 arrows: panning (cached geometry, offset only) and zooming
    for motion in ('pan', 'zoom'):
        preview.order_light = OrderLight(preview.order_style)
        preview.order_light.prewarm(plot_radii())
        preview.zoom = 2.4
        preview.centre = list(raw_centre)
        preview.clamp()
        _scene(preview, 'arrows 20', territory)
        costs = []
        direction = 1
        for i in range(frames):
            preview.clock += 1.0 / 60
            if motion == 'pan':
                preview.pan(3 * direction, 1)
                if i % 60 == 59:
                    direction = -direction
            else:
                if preview.zoom >= MAX_ZOOM - 1e-6:
                    direction = -1
                elif preview.zoom <= MIN_ZOOM + 1e-6:
                    direction = 1
                preview.zoom_by(0.25 * direction)
            costs.append(preview.render())
        warm = costs[settle:]
        print(f"{'-':>5} {'arrows 20 ' + motion:>18} {sum(warm) / len(warm):8.3f} {max(costs):9.3f}")
    light = preview.order_light
    nbytes = sum(s.get_width() * s.get_height() * s.get_bytesize() for s in light.glow._sprites.values())
    print(f'glow sprites: {len(light.glow._sprites)} ({nbytes / 1e6:.1f} MB), '
          f'arrow paths built: {light.paths_built}')
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description='Order effects preview')
    parser.add_argument('--look', choices=('2d', '3d'), default='2d')
    parser.add_argument('--size', default='1600x850', help='window size, e.g. 1920x1080')
    parser.add_argument('--sheet', help='write a contact sheet of stills to this PNG and exit')
    parser.add_argument('--bench', action='store_true', help="print the marks' frame cost and exit")
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
