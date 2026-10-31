# -*- coding: utf-8 -*-
"""
Banner Effects Preview (dev tool)

Live preview of the banners waving in the breeze and the selected banner's
motes (ui/effects/banner_fx_effect.py) on the real Avareon map, to tune their
look (ui/effects/banner_fx_style.py) and check their cost. The map, fills,
plots and selection ring are the order preview's (tools/order_fx_preview.py);
every territory has a banner - the four colours, the three tiers and some
neutral ones - drawn as MapRenderer draws them, and a banner can march to a
neighbour as an army does (0.5 s, with the game's sideways wiggle).

Run from the game folder:
    py tools/banner_fx_preview.py                    live window
    py tools/banner_fx_preview.py --look 3d          start in the 3D map look
    py tools/banner_fx_preview.py --sheet out.png    stills: poses over a period at three zooms, motes, a march
    py tools/banner_fx_preview.py --bench            the banners' cost with and without the wave, the bake

Controls (live):
    click           select the banner (or plot) under the mouse
    M               march the selected banner to a neighbour and back, over and over (M again: stop)
    W               wave on / off (the plain flags, to compare)
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

import math  # noqa: E402
import zlib  # noqa: E402

import pygame  # noqa: E402

import map_data  # noqa: E402
from config.constants import (ARMY_CIRCLE_RADIUS, ARMY_CIRCLE_DRAW_SCALE, ARMY_CIRCLE_DRAW_LIFT,  # noqa: E402
                              ARMY_FLAG_HEIGHT_RATIO)
from tools.plot_fx_preview import ui_scale_for, MIN_ZOOM, MAX_ZOOM  # noqa: E402
from tools.hero_fx_preview import focus_territory  # noqa: E402
from tools.order_fx_preview import OrderPreview, FLAG_COLOURS  # noqa: E402
from ui.effects import banner_fx_effect  # noqa: E402
from ui.effects.banner_fx_effect import BannerWave, BannerMotes, register_art, size_steps  # noqa: E402
from ui.effects.banner_fx_style import get_banner_fx_style  # noqa: E402

MARCH_SECONDS = 0.5      # GameState ArmyAnimation.duration
WIGGLE_PX, WIGGLE_WAVES = 15, 2   # MapRenderer.draw_animated_armies


def _tier(territory):
    return 1 + zlib.crc32(territory.encode('utf-8')) % 3


class BannerPreview(OrderPreview):
    """The order preview's map and marks, every territory's banner waving."""

    def __init__(self, screen, look):
        self.wave = None
        self.motes = None
        self.waving = True
        self.march = None        # (from territory, to territory, preview clock at the start)
        self.banner_ms = 0.0     # this frame's banner blits (and motes)
        super().__init__(screen, look)

    def load_look(self, look):
        super().load_look(look)
        self.banner_style = get_banner_fx_style(self.look)
        # The game's flag pictures, named as the loader in main.py names them
        self.pictures = {}
        for colour in FLAG_COLOURS:
            for tier in (1, 2, 3):
                picture = pygame.image.load(f'assets/mapicons/{colour}Flag{tier}.png').convert_alpha()
                register_art(picture, f'{colour}Flag{tier}')
                self.pictures[(colour, tier)] = picture
        neutral = pygame.image.load('assets/NeutralFlag.png').convert_alpha()
        for tier in (1, 2, 3):
            picture = pygame.transform.smoothscale(neutral, self.pictures[(FLAG_COLOURS[0], tier)].get_size())
            register_art(picture, f'NeutralFlag{tier}')
            self.pictures[('Neutral', tier)] = picture
        territories = sorted(map_data.TERRITORY_PLOTS)
        self.banner_of = {}
        for i, territory in enumerate(territories):
            colour = 'Neutral' if i % 7 == 3 else FLAG_COLOURS[self.flag_index[territory]]
            self.banner_of[territory] = self.pictures[(colour, _tier(territory))]
        # As the loading screen: every pose of every picture at every size
        start = time.perf_counter()
        banner_fx_effect.clear_cache()
        self.wave = BannerWave(self.banner_style)
        self.motes = BannerMotes(self.banner_style['motes'], self.banner_style['warm_white'])
        for step in size_steps():
            self.wave.prewarm(list(self.pictures.values()), [step])
            self.motes.prewarm([step])
        self.bake_ms = (time.perf_counter() - start) * 1000
        self.march = None

    # ---------- banners ----------

    def _plain(self, picture, height):
        key = (id(picture), height)
        flag = self._flags.get(key)
        if flag is None:
            width = max(1, int(height * picture.get_width() / picture.get_height()))
            flag = self._flags[key] = pygame.transform.smoothscale(picture, (width, height))
        return flag

    def _blit_banner(self, picture, x, y, height, world):
        """The flag with its pole base at screen (x, y): waving, or plain (W)."""
        start = time.perf_counter()
        if not (self.waving and self.wave.draw(self.screen, picture, x, y, height,
                                               world[0], world[1], self.clock)):
            flag = self._plain(picture, int(height))
            self.screen.blit(flag, (int(x) - flag.get_width() // 2, int(y) - flag.get_height()))
        self.banner_ms += (time.perf_counter() - start) * 1000

    def _draw_circle(self, x, y, colour, ui_scale):
        radius = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
        cy = y - int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
        glow = self._glow(colour, radius)
        self.screen.blit(glow, glow.get_rect(center=(x, cy)))
        dark = tuple(int(c * 0.55) for c in colour)
        pygame.draw.circle(self.screen, dark, (x, cy), radius, max(2, radius // 5))

    def _draw_banner(self, x, y, territory, ui_scale):
        """The army circle and banner of a territory (OrderPreview.render calls it)."""
        if territory not in self.banner_of or (self.march and territory == self.march[0]):
            return      # no army there, or it is on the march
        self._draw_circle(x, y, self.owner_colour.get(territory, (150, 150, 150)), ui_scale)
        self._blit_banner(self.banner_of[territory], x, y,
                          ARMY_CIRCLE_RADIUS * ui_scale * ARMY_FLAG_HEIGHT_RATIO, self.world_centres[territory])

    def _march_position(self):
        """The marching banner's world position now (there and back, with the game's wiggle)."""
        source, target, since = self.march
        u = ((self.clock - since) / MARCH_SECONDS) % 2.0
        progress = u if u <= 1.0 else 2.0 - u
        (fx, fy), (tx, ty) = self.world_centres[source], self.world_centres[target]
        if u > 1.0:
            (fx, fy), (tx, ty) = (tx, ty), (fx, fy)
            progress = u - 1.0
        dx, dy = tx - fx, ty - fy
        length = math.hypot(dx, dy) or 1.0
        wiggle = math.sin(progress * math.pi * WIGGLE_WAVES) * WIGGLE_PX
        return fx + dx * progress - dy / length * wiggle, fy + dy * progress + dx / length * wiggle

    def render(self):
        """One frame; returns the ms spent on the banners and motes."""
        self.banner_ms = 0.0
        self.wave.begin_frame()
        self.motes.begin_frame()
        super().render()
        ui_scale = ui_scale_for(self.zoom)
        view = self.view()
        # The selected banner's motes, over every banner (as MapRenderer)
        if self.selected and self.selected[0] == 'army' and not self.march:
            territory = self.selected[1]
            x, y = view.to_screen(self.world_centres[territory])
            start = time.perf_counter()
            self.motes.draw(self.screen, self.selected, x, y,
                            ARMY_CIRCLE_RADIUS * ui_scale * ARMY_FLAG_HEIGHT_RATIO, self.clock)
            self.banner_ms += (time.perf_counter() - start) * 1000
        # The marching banner, over everything (as draw_animated_armies, its own sizes)
        if self.march:
            world = self._march_position()
            x, y = view.to_screen(world)
            radius = int(ARMY_CIRCLE_RADIUS * ui_scale)
            self._draw_circle(int(x), int(y), self.owner_colour.get(self.march[0], (150, 150, 150)), ui_scale)
            self._blit_banner(self.banner_of[self.march[0]], x, y, int(radius * ARMY_FLAG_HEIGHT_RATIO), world)
        return self.banner_ms

    def toggle_march(self):
        if self.march:
            self.march = None
        elif self.selected and self.selected[0] == 'army':
            neighbours = self._nearest_neighbours(self.selected[1])
            if neighbours:
                self.march = (self.selected[1], neighbours[0], self.clock)


def run_live(look, size):
    pygame.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption('Banner effects preview')
    preview = BannerPreview(screen, look)
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
            elif event.type == pygame.MOUSEMOTION and dragging:
                if abs(event.rel[0]) + abs(event.rel[1]) > 0:
                    moved = True
                preview.pan(*event.rel)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    preview.toggle_march()
                elif event.key == pygame.K_w:
                    preview.waving = not preview.waving
                elif event.key == pygame.K_l:
                    preview.load_look('2d' if preview.look == '3d' else '3d')
                elif event.key == pygame.K_SPACE:
                    preview.paused = not preview.paused
        if not preview.paused:
            preview.clock += min(dt, 0.05)
        start = time.perf_counter()
        banner_ms = preview.render()
        frame_ms = (time.perf_counter() - start) * 1000
        history = (history + [(frame_ms, banner_ms)])[-60:]
        avg = [sum(h[i] for h in history) / len(history) for i in range(2)]
        lines = [
            f"{clock.get_fps():6.1f} FPS   frame {avg[0]:5.2f} ms   banners {avg[1]:5.2f} ms"
            f"   bake {preview.bake_ms:.0f} ms   frames {banner_fx_effect.cache_bytes() / 1e6:.1f} MB",
            f"look {preview.look}   zoom {preview.zoom:.2f}   selected {preview.selected}"
            f"   wave {'on' if preview.waving else 'OFF'}{'   MARCHING' if preview.march else ''}"
            f"{'   PAUSED' if preview.paused else ''}",
            'click select  M march  W wave on/off  L look  Space pause',
        ]
        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            pygame.draw.rect(screen, (0, 0, 0), text.get_rect(topleft=(8, 8 + i * 20)).inflate(8, 2))
            screen.blit(text, (8, 8 + i * 20))
        pygame.display.flip()


def run_sheet(path, look, size, magnify=3):
    """
    Rows: the selected banner and its neighbours over one breeze period at the
    smallest, middle and largest zoom; the selected banner's motes over 2 s; a
    march there and back.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = BannerPreview(screen, look)
    territory = focus_territory(preview)
    font = pygame.font.SysFont('consolas', 15)
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    period = preview.banner_style['wave']['period']
    columns = 8
    rows = [('breeze', zoom, [period * k / columns for k in range(columns)])
            for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM)]
    rows.append(('motes', 2.4, [0.25 * k for k in range(columns)]))
    rows.append(('march', 2.4, [MARCH_SECONDS * 2 * k / columns for k in range(columns)]))
    cell_w, cell_h = 150 * magnify, 120 * magnify
    sheet = pygame.Surface((cell_w * columns, (cell_h + 20) * len(rows)))
    sheet.fill((30, 30, 30))
    for row, (name, zoom, times) in enumerate(rows):
        preview.zoom = zoom
        preview.centre = list(raw_centre)
        preview.clamp()
        cx, cy = preview.to_screen(*raw_centre)
        preview.selected = ('army', territory) if name in ('motes', 'march') else None
        preview.march = None
        if name == 'march':
            preview.toggle_march()
            preview.march = (preview.march[0], preview.march[1], 0.0)
        crop_w, crop_h = 150, 120      # screen px at every zoom: the banners' real sizes
        for col, t in enumerate(times):
            # A few frames before the still: the motes light up over their first 0.15 s
            for lead in (0.2, 0.1, 0.0):
                preview.clock = t - lead
                preview.render()
            crop = pygame.Rect(0, 0, crop_w, crop_h)
            crop.center = (cx, cy - crop_h // 5)
            cell = pygame.transform.smoothscale(screen.subsurface(crop.clip(screen.get_rect())), (cell_w, cell_h))
            top = row * (cell_h + 20)
            sheet.blit(cell, (col * cell_w, top + 20))
            caption = font.render(f'{name}  t={t:.2f}s  zoom {zoom:.2f}  ({preview.look})', True, (255, 255, 255))
            sheet.blit(caption, (col * cell_w + 6, top + 2))
    pygame.image.save(sheet, path)
    print(f'Wrote {path} ({territory})')
    pygame.quit()


def run_bench(look, size, frames=240):
    """
    The banners' cost per frame at three zooms, waving and plain, every
    territory's banner on screen that fits (worst: the smallest zoom); a
    selected banner's motes; a march. And the bake (the loading screen's work).
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = BannerPreview(screen, look)
    territory = focus_territory(preview)
    print(f'{look} look, {size[0]}x{size[1]}, focus {territory}')
    print(f'bake: {len(preview.pictures)} pictures x {len(size_steps())} sizes in {preview.bake_ms:.0f} ms, '
          f'{banner_fx_effect.cache_bytes() / 1e6:.1f} MB')
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    print(f"{'zoom':>5} {'scene':>14} {'avg ms':>8} {'p95 ms':>8} {'worst ms':>9} {'built':>6}")
    for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM):
        for name in ('plain', 'waving', 'motes', 'march'):
            preview.zoom = zoom
            preview.centre = list(raw_centre)
            preview.clamp()
            preview.waving = name != 'plain'
            preview.selected = ('army', territory) if name in ('motes', 'march') else None
            preview.march = None
            if name == 'march':
                preview.toggle_march()
            preview.clock = 0.0
            built = preview.wave.frames_built
            costs = []
            for _ in range(frames):
                preview.clock += 1.0 / 120
                costs.append(preview.render())
            costs.sort()
            print(f'{zoom:5.2f} {name:>14} {sum(costs) / len(costs):8.3f} {costs[int(len(costs) * 0.95)]:8.3f} '
                  f'{costs[-1]:9.3f} {preview.wave.frames_built - built:6d}')
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description='Banner effects preview')
    parser.add_argument('--look', choices=('2d', '3d'), default='2d')
    parser.add_argument('--size', default='1600x850', help='window size, e.g. 1920x1080')
    parser.add_argument('--sheet', help='write a contact sheet of stills to this PNG and exit')
    parser.add_argument('--bench', action='store_true', help="print the banners' frame cost and exit")
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
