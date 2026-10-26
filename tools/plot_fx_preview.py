# -*- coding: utf-8 -*-
"""
Plot Effects Preview (dev tool)

Live preview of the plot effects on the real Avareon map, to tune their look
(ui/effects/plot_fx_style.py) and check their frame cost:
- production light rays (ProductionGlowEffect + the shared ProductionRays) on
  producing Barracks / Keeps
- construction dust (ConstructionDust) on plots under construction
- the gold-glint dust variant on Keeps being upgraded to Castles

Plots are drawn the way MapRenderer draws them (disc, icon, rings) at the game's
plot size (EMPTY_PLOT_RADIUS * ui_scale), and positioned with the game's map scale.
Every plot gets an effect (or a share of them, N), far more than a real game shows.

Run from the game folder:
    py tools/plot_fx_preview.py                      live window
    py tools/plot_fx_preview.py --look 3d            start in the 3D map look
    py tools/plot_fx_preview.py --sheet out.png      headless contact sheet of stills
    py tools/plot_fx_preview.py --sheet out.png --closeups --zoom 1.65   one plot per effect
    py tools/plot_fx_preview.py --bench              effect cost per frame (avg / worst ms)

Controls (live):
    mouse wheel  zoom (1.65 - 4.0, like the game)     drag   pan
    L  2D / 3D look        R  rays on/off         D  dust on/off
    E  all effects off (baseline FPS)             N  share of plots with effects
    Space  pause the effect clock                  Esc  quit
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)   # asset paths are relative to the game folder

if '--sheet' in sys.argv or '--bench' in sys.argv:
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')   # stills and timings need no window

import pygame  # noqa: E402

import map_data  # noqa: E402
from config.constants import (EMPTY_PLOT_RADIUS, PLAYER_COLORS, COLOR_CONSTRUCTION,  # noqa: E402
                              COLOR_CONSTRUCTION_BORDER, COLOR_PLOT_BORDER)
from ui.effects.plot_fx_style import get_plot_fx_style, plot_phase  # noqa: E402
from ui.effects.production_glow_effect import ProductionRays, ProductionGlowEffect  # noqa: E402
from ui.effects.construction_dust_effect import (ConstructionDust, VARIANT_BUILD,  # noqa: E402
                                                 VARIANT_UPGRADE)

MIN_ZOOM, MAX_ZOOM = 1.65, 4.0          # the game's camera range (main.py camera_min/max_zoom)
MAP_HEIGHT_SHARE = 649.0 / 850.0        # map area / window height at the default 1600x850
ORIGINAL_MAP_SIZE = (4096, 3072)
DENSITIES = (1.0, 0.5, 0.25)

# Plot states in the preview
PRODUCING, CONSTRUCTING, UPGRADING, PLAIN = 'producing', 'constructing', 'upgrading', 'plain'
CONSTRUCTION_TYPES = ('Barracks', 'Farm', 'Keep', 'Mine', 'Square', 'Training Grounds')
PLAIN_TYPES = ('Farm', 'Mine', 'Square')


def ui_scale_for(zoom):
    """The game's ui_scale (CameraHandler.get_ui_scale_factor): 1.0 at min zoom, 1.5 at max."""
    return 1.0 + 0.5 * (zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)


def plot_radii():
    """Every plot radius the zoom range produces (16..24 px)."""
    return range(int(EMPTY_PLOT_RADIUS * ui_scale_for(MIN_ZOOM)),
                 int(EMPTY_PLOT_RADIUS * ui_scale_for(MAX_ZOOM)) + 1)


class Preview:
    """Map, plots and effects for one window size."""

    def __init__(self, screen, look):
        self.screen = screen
        self.width, self.height = screen.get_size()
        # The game's scale_factor: the 4096x3072 map fitted into the map area
        self.map_scale = min(self.width / ORIGINAL_MAP_SIZE[0],
                             self.height * MAP_HEIGHT_SHARE / ORIGINAL_MAP_SIZE[1])
        self.zoom = 2.4
        self.centre = [2900.0, 1150.0]   # raw map pixels (Aelatania area: plots close together)
        self.clock = 0.0
        self.paused = False
        self.show_rays = True
        self.show_dust = True
        self.effects_off = False
        self.density_index = 0
        self._icons = {}
        self._icon_cache = {}
        self._background_key = None
        self._background = None
        self.rays = None
        self.dust = None
        self.load_look(look)

    # ---------- map ----------

    def load_look(self, look):
        map_data.load_map('avareon', look)
        self.look = map_data.get_current_look()   # '2d' if the 3D look is missing / stale
        picture = map_data.look_picture('assets/map.png', 'avareon', self.look)
        self.map_image = pygame.image.load(picture).convert()
        style = get_plot_fx_style(self.look)
        self.rays = ProductionRays(style['rays'])
        self.rays.prewarm(plot_radii())
        self.dust = ConstructionDust(style['dust'])
        self._background_key = None
        self._assign_plots()

    def _assign_plots(self):
        """Give every plot a state and an owner (deterministic, so runs compare)."""
        self.plots = []
        density = DENSITIES[self.density_index]
        territories = sorted(map_data.TERRITORY_PLOTS)
        for t_index, territory in enumerate(territories):
            owner_colour = PLAYER_COLORS[t_index % len(PLAYER_COLORS)]
            for plot_index, (raw_x, raw_y) in enumerate(map_data.TERRITORY_PLOTS[territory]):
                phase = plot_phase(territory, plot_index)
                n = len(self.plots)
                if phase >= density:
                    state, building = PLAIN, PLAIN_TYPES[n % len(PLAIN_TYPES)]
                elif n % 9 == 4:
                    state, building = UPGRADING, 'Castle'
                elif n % 2 == 0:
                    state, building = PRODUCING, ('Barracks' if n % 6 else 'Keep')
                else:
                    state, building = CONSTRUCTING, CONSTRUCTION_TYPES[n % len(CONSTRUCTION_TYPES)]
                # Producing plots get the game's own effect object
                glow = (ProductionGlowEffect(territory, plot_index, owner_colour)
                        if state == PRODUCING else None)
                self.plots.append((territory, plot_index, raw_x, raw_y, state, building,
                                   owner_colour, phase, glow))

    def counts(self):
        totals = {PRODUCING: 0, CONSTRUCTING: 0, UPGRADING: 0, PLAIN: 0}
        for plot in self.plots:
            totals[plot[4]] += 1
        return totals

    # ---------- camera ----------

    @property
    def scale(self):
        return self.map_scale * self.zoom

    def to_screen(self, raw_x, raw_y):
        s = self.scale
        return (int((raw_x - self.centre[0]) * s + self.width / 2),
                int((raw_y - self.centre[1]) * s + self.height / 2))

    def clamp(self):
        half_w = self.width / 2 / self.scale
        half_h = self.height / 2 / self.scale
        self.centre[0] = min(max(self.centre[0], half_w), ORIGINAL_MAP_SIZE[0] - half_w)
        self.centre[1] = min(max(self.centre[1], half_h), ORIGINAL_MAP_SIZE[1] - half_h)

    def zoom_by(self, steps):
        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * (1.1 ** steps)))
        self.clamp()

    def pan(self, dx, dy):
        self.centre[0] -= dx / self.scale
        self.centre[1] -= dy / self.scale
        self.clamp()

    # ---------- drawing ----------

    def _draw_background(self):
        key = (round(self.zoom, 4), round(self.centre[0], 1), round(self.centre[1], 1))
        if key != self._background_key:
            s = self.scale
            rect = pygame.Rect(int(self.centre[0] - self.width / 2 / s),
                               int(self.centre[1] - self.height / 2 / s),
                               int(self.width / s) + 1, int(self.height / s) + 1)
            rect = rect.clip(self.map_image.get_rect())
            self._background = pygame.transform.smoothscale(
                self.map_image.subsurface(rect), (int(rect.width * s), int(rect.height * s)))
            self._background_pos = self.to_screen(rect.x, rect.y)
            self._background_key = key
        self.screen.fill((20, 20, 20))
        self.screen.blit(self._background, self._background_pos)

    def _icon(self, name, size, alpha=None):
        key = (name, size, alpha)
        icon = self._icon_cache.get(key)
        if icon is None:
            base = self._icons.get(name)
            if base is None:
                base = pygame.image.load(f"assets/mapicons/{name.replace(' ', '')}Icon.png").convert_alpha()
                self._icons[name] = base
            icon = pygame.transform.smoothscale(base, (size, size))
            if alpha is not None:
                icon = icon.copy()
                icon.set_alpha(alpha)
            self._icon_cache[key] = icon
        return icon

    def _draw_plot(self, x, y, radius, state, building, colour):
        """Same layers as MapRenderer._render_completed_plot / _render_construction_plot."""
        screen = self.screen
        if state == CONSTRUCTING:
            disc = self._icon_cache.get(('construction disc', radius))
            if disc is None:
                disc = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(disc, COLOR_CONSTRUCTION, (radius + 2, radius + 2), radius)
                pygame.draw.circle(disc, COLOR_CONSTRUCTION_BORDER, (radius + 2, radius + 2), radius, 2)
                self._icon_cache[('construction disc', radius)] = disc
            screen.blit(disc, (x - radius - 2, y - radius - 2))
            icon = self._icon(building, radius * 2, alpha=180)
        else:
            softened = tuple(int(c * 0.7) for c in colour)
            pygame.draw.circle(screen, softened, (x, y), radius)
            pygame.draw.circle(screen, COLOR_PLOT_BORDER[:3], (x, y), radius, 2)
            icon = self._icon(building, radius * 2)
        screen.blit(icon, icon.get_rect(center=(x, y)))
        pygame.draw.circle(screen, (0, 0, 0), (x, y), radius, 1)
        pygame.draw.circle(screen, colour, (x, y), radius - 1, 3)
        pygame.draw.circle(screen, (0, 0, 0), (x, y), radius - 4, 1)

    def render(self):
        """Draw one frame; returns (rays ms, dust ms, rays drawn, dust drawn)."""
        self._draw_background()
        radius = int(EMPTY_PLOT_RADIUS * ui_scale_for(self.zoom))
        margin = radius * 3
        visible = []
        for plot in self.plots:
            x, y = self.to_screen(plot[2], plot[3])
            if -margin < x < self.width + margin and -margin < y < self.height + margin:
                visible.append((x, y, plot))

        perf = time.perf_counter
        rays_on = self.show_rays and not self.effects_off
        dust_on = self.show_dust and not self.effects_off
        rays_drawn = dust_drawn = 0

        # Production rays first, under every plot (MapRenderer draws them before draw_plots)
        start = perf()
        if rays_on:
            for x, y, plot in visible:
                if plot[8] is not None:
                    plot[8].render(self.screen, x, y, radius, self.clock, self.rays)
                    rays_drawn += 1
        rays_ms = (perf() - start) * 1000

        dust_ms = 0.0
        self.dust.begin_frame()
        for x, y, plot in visible:
            state = plot[4]
            dusty = dust_on and state in (CONSTRUCTING, UPGRADING)
            variant = VARIANT_UPGRADE if state == UPGRADING else VARIANT_BUILD
            if dusty:
                start = perf()
                self.dust.draw_back(self.screen, x, y, radius, self.clock, plot[7], variant)
                dust_ms += perf() - start
            self._draw_plot(x, y, radius, state, plot[5], plot[6])
            if dusty:
                start = perf()
                self.dust.draw_front(self.screen, x, y, radius, self.clock, plot[7], variant)
                dust_ms += perf() - start
                dust_drawn += 1
        return rays_ms, dust_ms * 1000, rays_drawn, dust_drawn


def run_live(look, size, max_frames=None):
    """The interactive window. max_frames quits after that many frames (smoke tests)."""
    pygame.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption('Plot effects preview')
    preview = Preview(screen, look)
    font = pygame.font.SysFont('consolas', 16)
    clock = pygame.time.Clock()
    dragging = False
    history = []
    frame = 0
    while max_frames is None or frame < max_frames:
        frame += 1
        dt = clock.tick(0) / 1000.0   # uncapped: shows the real frame cost
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
                if event.key == pygame.K_l:
                    preview.load_look('2d' if preview.look == '3d' else '3d')
                elif event.key == pygame.K_r:
                    preview.show_rays = not preview.show_rays
                elif event.key == pygame.K_d:
                    preview.show_dust = not preview.show_dust
                elif event.key == pygame.K_e:
                    preview.effects_off = not preview.effects_off
                elif event.key == pygame.K_n:
                    preview.density_index = (preview.density_index + 1) % len(DENSITIES)
                    preview._assign_plots()
                elif event.key == pygame.K_SPACE:
                    preview.paused = not preview.paused
        if not preview.paused:
            preview.clock += min(dt, 0.05)

        start = time.perf_counter()
        rays_ms, dust_ms, rays_drawn, dust_drawn = preview.render()
        frame_ms = (time.perf_counter() - start) * 1000
        history.append((frame_ms, rays_ms, dust_ms))
        history = history[-60:]
        avg = [sum(h[i] for h in history) / len(history) for i in range(3)]

        radius = int(EMPTY_PLOT_RADIUS * ui_scale_for(preview.zoom))
        lines = [
            f"{clock.get_fps():6.1f} FPS   frame {avg[0]:5.2f} ms   rays {avg[1]:5.2f} ms ({rays_drawn})"
            f"   dust {avg[2]:5.2f} ms ({dust_drawn})",
            f"look {preview.look}   zoom {preview.zoom:.2f}   plot radius {radius}px   "
            f"effects on {int(DENSITIES[preview.density_index] * 100)}% of plots"
            f"{'   EFFECTS OFF' if preview.effects_off else ''}"
            f"{'   PAUSED' if preview.paused else ''}",
            "wheel zoom  drag pan  L look  R rays  D dust  E all off  N density  Space pause",
        ]
        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            pygame.draw.rect(screen, (0, 0, 0), text.get_rect(topleft=(8, 8 + i * 20)).inflate(8, 2))
            screen.blit(text, (8, 8 + i * 20))
        pygame.display.flip()
    pygame.quit()


def densest_point(preview, reach=260.0):
    """Raw map point with the most plots within `reach` px: where the effects crowd most."""
    points = [(p[2], p[3]) for p in preview.plots]
    best = max(points, key=lambda a: sum(1 for b in points
                                         if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 < reach * reach))
    return list(best)


def run_sheet(path, look, size, magnify=2):
    """
    Stills at several zooms and times, side by side, for review without a window.

    Every crop is centred on the same map point (the densest plot cluster) and
    magnified `magnify` x, so small details (dust motes, ray edges) are visible.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = Preview(screen, look)
    focus = densest_point(preview)
    font = pygame.font.SysFont('consolas', 15)
    crop_w, crop_h = 260, 170
    cell_w, cell_h = crop_w * magnify, crop_h * magnify
    rows = [('zoom 1.65', 1.65), ('zoom 2.4', 2.4), ('zoom 4.0', 4.0)]
    times = (0.0, 0.5, 1.0, 1.5)
    sheet = pygame.Surface((cell_w * len(times), (cell_h + 20) * len(rows)))
    sheet.fill((30, 30, 30))
    for row, (label, zoom) in enumerate(rows):
        preview.zoom = zoom
        preview.centre = list(focus)
        preview.clamp()
        sx, sy = preview.to_screen(*focus)   # the focus may sit off-centre near map edges
        for col, t in enumerate(times):
            preview.clock = t
            preview.render()
            crop = pygame.Rect(0, 0, crop_w, crop_h)
            crop.center = (sx, sy)
            cell = pygame.transform.smoothscale(screen.subsurface(crop.clip(screen.get_rect())),
                                                (cell_w, cell_h))
            top = row * (cell_h + 20)
            sheet.blit(cell, (col * cell_w, top + 20))
            caption = font.render(f'{label}  t={t:.1f}s  ({preview.look})', True, (255, 255, 255))
            sheet.blit(caption, (col * cell_w + 6, top + 2))
    pygame.image.save(sheet, path)
    print(f'Wrote {path} (focus {int(focus[0])}, {int(focus[1])})')
    pygame.quit()


def run_closeups(path, look, size, zoom=4.0, magnify=3):
    """
    One row per effect (producing, constructing, upgrading): the plot of that state
    nearest the densest cluster, cropped tight and magnified, at several times.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = Preview(screen, look)
    focus = densest_point(preview)
    preview.zoom = zoom
    font = pygame.font.SysFont('consolas', 15)
    radius = int(EMPTY_PLOT_RADIUS * ui_scale_for(zoom))
    crop_size = radius * 6
    cell = crop_size * magnify
    times = (0.0, 0.4, 0.8, 1.2, 1.6, 2.0)
    states = (PRODUCING, CONSTRUCTING, UPGRADING)
    sheet = pygame.Surface((cell * len(times), (cell + 20) * len(states)))
    sheet.fill((30, 30, 30))
    for row, state in enumerate(states):
        candidates = [p for p in preview.plots if p[4] == state]
        plot = min(candidates, key=lambda p: (p[2] - focus[0]) ** 2 + (p[3] - focus[1]) ** 2)
        preview.centre = [plot[2], plot[3]]
        preview.clamp()
        px, py = preview.to_screen(plot[2], plot[3])
        for col, t in enumerate(times):
            preview.clock = t
            preview.render()
            crop = pygame.Rect(0, 0, crop_size, crop_size)
            crop.center = (px, py)
            image = pygame.transform.scale(screen.subsurface(crop.clip(screen.get_rect())), (cell, cell))
            top = row * (cell + 20)
            sheet.blit(image, (col * cell, top + 20))
            caption = font.render(f'{state} {plot[5]}  t={t:.1f}s  r={radius}  ({preview.look})',
                                  True, (255, 255, 255))
            sheet.blit(caption, (col * cell + 6, top + 2))
    pygame.image.save(sheet, path)
    print(f'Wrote {path}')
    pygame.quit()


def run_bench(look, size, frames=240):
    """
    Effect cost per frame (avg / worst ms) with effects on every plot, at three zooms,
    starting from cold caches so the worst frame includes building them.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = Preview(screen, look)
    preview.centre = densest_point(preview)
    print(f'{look} look, {size[0]}x{size[1]}, {frames} frames per row, effects on 100% of plots')
    print(f"{'zoom':>5} {'effect':>10} {'drawn':>6} {'avg ms':>8} {'worst ms':>9}")
    for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM):
        for label in ('rays', 'dust'):
            style = get_plot_fx_style(preview.look)
            preview.rays = ProductionRays(style['rays'])       # cold caches every row
            preview.rays.prewarm(plot_radii())                 # as the game does at load
            preview.dust = ConstructionDust(style['dust'])
            preview.zoom = zoom
            preview.clamp()
            preview.show_rays = label == 'rays'
            preview.show_dust = label == 'dust'
            costs = []
            drawn = 0
            for i in range(frames):
                preview.clock = i / 80.0   # the game's frame cap
                rays_ms, dust_ms, rays_drawn, dust_drawn = preview.render()
                costs.append(dust_ms if label == 'dust' else rays_ms)
                drawn = dust_drawn if label == 'dust' else rays_drawn
            print(f'{zoom:5.2f} {label:>10} {drawn:6d} {sum(costs) / len(costs):8.3f} {max(costs):9.3f}')

    # Zoom sweep min -> max -> min over 3 s (240 frames), all effects on, warm caches
    # first: every plot size is crossed, so frame sets and sprites keep changing
    preview.show_rays = preview.show_dust = True
    costs = []
    for i in range(frames):
        t = i / (frames - 1.0)
        preview.zoom = MIN_ZOOM + (MAX_ZOOM - MIN_ZOOM) * (1.0 - abs(2.0 * t - 1.0))
        preview.clamp()
        preview.clock = 10.0 + i / 80.0
        rays_ms, dust_ms, _, _ = preview.render()
        costs.append(rays_ms + dust_ms)
    print(f"{'sweep':>5} {'rays+dust':>10} {'':>6} {sum(costs) / len(costs):8.3f} {max(costs):9.3f}")

    # Memory held by the caches after all of the above
    def surface_bytes(surface):
        return surface.get_width() * surface.get_height() * surface.get_bytesize()
    ray_bytes = sum(surface_bytes(layer.base) + sum(surface_bytes(slot[1]) for slot in layer.current)
                    for ray_set in preview.rays._sets.values() for layer in ray_set.layers)
    ray_bytes += sum(surface_bytes(s) for bases in preview.rays._grey_bases.values()
                     for rays_grey, halo, _ in bases for s in (rays_grey, halo) if s is not None)
    dust_bytes = sum(surface_bytes(s) for s in preview.dust._sprites.values())
    print(f'cache memory: rays {ray_bytes / 1e6:.1f} MB in {len(preview.rays._sets)} sets '
          f'({preview.rays.rotations} rotations), dust {dust_bytes / 1e6:.1f} MB in '
          f'{len(preview.dust._sprites)} sprites')
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description='Plot effects preview')
    parser.add_argument('--look', choices=('2d', '3d'), default='2d')
    parser.add_argument('--size', default='1600x850', help='window size, e.g. 1920x1080')
    parser.add_argument('--sheet', help='write a contact sheet of stills to this PNG and exit')
    parser.add_argument('--closeups', action='store_true',
                        help='with --sheet: magnified close-ups of one plot per effect instead')
    parser.add_argument('--zoom', type=float, default=4.0, help='zoom for --closeups')
    parser.add_argument('--bench', action='store_true', help='print the effects\' frame cost and exit')
    parser.add_argument('--frames', type=int, help='live window: quit after this many frames')
    args = parser.parse_args()
    size = tuple(int(v) for v in args.size.lower().split('x'))
    if args.bench:
        run_bench(args.look, size)
    elif args.sheet and args.closeups:
        run_closeups(args.sheet, args.look, size, zoom=args.zoom)
    elif args.sheet:
        run_sheet(args.sheet, args.look, size)
    else:
        run_live(args.look, size, args.frames)


if __name__ == '__main__':
    main()
