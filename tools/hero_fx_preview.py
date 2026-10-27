# -*- coding: utf-8 -*-
"""
Hero Ability Effects Preview (dev tool)

Live preview of the hero ability effects (ui/effects/hero_fx_effect.py) on the
real Avareon map, to tune their look (ui/effects/hero_fx_style.py) and check
their frame cost. The map, territory fills and plots are drawn the way the game
draws them (plots via tools/plot_fx_preview.py); effects are drawn in the game's
two layers: under the plots (rays, border light, fireflies) and over them.

Run from the game folder:
    py tools/hero_fx_preview.py                         live window
    py tools/hero_fx_preview.py --look 3d               start in the 3D map look
    py tools/hero_fx_preview.py --sheet out.png         stills of each effect over time
    py tools/hero_fx_preview.py --bench                 effect cost per frame (avg / worst ms)

Controls (live):
    1-9, 0, -, =  cast an ability at the territory under the mouse (order: ABILITY_KEYS)
    A  cycle the passive aura (off / Defiance / Haste / Safe Haven) on the territory
       under the mouse and its neighbours
    C  clear what a cast leaves behind: the Embargo embers, the Silence fog (in the
       game they last a turn; here until cleared or cast again)
    mouse wheel  zoom     drag  pan     L  2D / 3D look
    P  production rays + dust on/off   Space  pause   Esc  quit
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
from config.constants import EMPTY_PLOT_RADIUS  # noqa: E402
from tools.plot_fx_preview import (Preview, ui_scale_for, plot_radii, MIN_ZOOM,  # noqa: E402
                                   MAX_ZOOM)
from ui.effects.hero_fx_style import get_hero_fx_style  # noqa: E402
from ui.effects.hero_fx_effect import (HeroLight, HeroAbilityEffect, HeroAura, FxView,  # noqa: E402
                                       stable_seed)
from ui.effects.light_fx import vignette_surface  # noqa: E402

AURA_ORDER = (None, 'defiance', 'haste', 'safe_haven')


def ability_keys(style):
    """Ability names in key order (1-9, 0, -, =)."""
    return list(style['abilities'])


class HeroPreview(Preview):
    """The plot preview's map and plots, plus territory fills and the hero effects."""

    def __init__(self, screen, look):
        self.light = None
        self.effects = []
        self.aura = None
        # What casts leave behind - in the game drawn from game state, not by the cast
        self.embers = None           # HeroAura('embargo') over the embargoed territories
        self.embers_on = False
        self.silence_since = None    # preview clock when Vow of Silence was cast
        self._fog = None
        self.show_plot_fx = False
        self._fill_key = None
        self._fill = None
        super().__init__(screen, look)
        self.show_rays = self.show_dust = False

    def load_look(self, look):
        super().load_look(look)
        self.hero_style = get_hero_fx_style(self.look)
        # World coordinates as the game has them: raw map px * map scale, rounded
        self.world_polygons = {t: [(round(x * self.map_scale), round(y * self.map_scale)) for x, y in poly]
                               for t, poly in map_data.TERRITORY_POLYGONS.items()}
        self.world_centres = {t: (c[0] * self.map_scale, c[1] * self.map_scale)
                              for t, c in map_data.TERRITORY_CENTERS.items()}
        start = time.perf_counter()
        self.light = HeroLight(self.world_polygons, self.hero_style)
        self.light.prewarm(plot_radii())
        self.prewarm_ms = (time.perf_counter() - start) * 1000
        self.effects = []
        self.aura = None
        self.embers = HeroAura(self.light, 'embargo')
        self.embers_on = False
        self.silence_since = None
        self._fill_key = None
        territories = sorted(map_data.TERRITORY_PLOTS)
        from config.constants import PLAYER_COLORS
        self.owner_colour = {t: PLAYER_COLORS[i % len(PLAYER_COLORS)] for i, t in enumerate(territories)}

    # ---------- camera / view ----------

    def view(self):
        s = self.scale
        ax = self.width / 2 - self.centre[0] * s
        ay = self.height / 2 - self.centre[1] * s
        radius = int(EMPTY_PLOT_RADIUS * ui_scale_for(self.zoom))
        return FxView(self.screen, ax, ay, self.zoom, radius)

    def world_at(self, screen_pos):
        s = self.scale
        raw_x = (screen_pos[0] - self.width / 2) / s + self.centre[0]
        raw_y = (screen_pos[1] - self.height / 2) / s + self.centre[1]
        return raw_x * self.map_scale, raw_y * self.map_scale

    def territory_at(self, screen_pos):
        return self.light.raster().at(*self.world_at(screen_pos))

    # ---------- effects ----------

    def _plot_world(self, territory, index=0):
        plots = map_data.TERRITORY_PLOTS.get(territory) or []
        if index < len(plots):
            return plots[index][0] * self.map_scale, plots[index][1] * self.map_scale
        return self.world_centres[territory]

    def _nearest_neighbours(self, territory):
        cx, cy = self.world_centres[territory]
        return sorted((t for t in map_data.get_neighbors(territory) if t in self.world_polygons),
                      key=lambda t: (self.world_centres[t][0] - cx) ** 2
                      + (self.world_centres[t][1] - cy) ** 2)

    def anchors(self, ability, territory):
        """
        What MapRenderer._ability_anchors() resolves, for a cast on this territory
        by a hero whose Keep is on its first plot: arcs run to / from its nearest
        neighbour, Keeps are the first plots of it and its neighbours, enemies
        are the territories two steps away.
        """
        import math
        import random
        spec = self.hero_style['abilities'][ability]
        seed = stable_seed(ability, territory)
        rng = random.Random(seed)
        keep = self._plot_world(territory)
        neighbours = self._nearest_neighbours(territory)
        other = neighbours[0] if neighbours else territory
        cx, cy = self.world_centres[territory]
        far = sorted({t for n in neighbours for t in self._nearest_neighbours(n)}
                     - set(neighbours) - {territory})
        anchors = {
            'target': (cx, cy),
            'keep': keep,
            'territory': [territory],
            'points': self.light.points_inside(territory, spec.get('points', 0), seed),
            'satellites': [(cx + d * math.cos(a), cy + d * math.sin(a))
                           for a, d in ((math.pi / 2 * i + rng.uniform(-0.3, 0.3), rng.uniform(14, 22))
                                        for i in range(4))],
            'keeps': [self._plot_world(t) for t in [territory] + neighbours],
            'territories': [territory] + neighbours[:2],
            'enemy_territories': far,
            'enemy_keeps': [self._plot_world(t) for t in far[:3]],
        }
        if ability == 'Royal Charisma':          # from the target to the hero's Keep
            anchors['source'], anchors['dest'] = self.world_centres[other], keep
        else:                                    # Valorous Charge: Keep to target
            anchors['source'], anchors['dest'] = keep, self.world_centres[other]
        return anchors, seed

    def cast(self, ability, territory):
        if territory is None:
            return
        anchors, seed = self.anchors(ability, territory)
        self.effects.append(HeroAbilityEffect(self.light, self.hero_style['abilities'][ability],
                                              anchors, seed))
        # What the game shows afterwards from game state (MapRenderer.update_hero_effects,
        # Game.draw_silence_fog_overlay)
        if ability == 'Embargo':
            self.embers.set_territories(anchors['enemy_territories'])
            self.embers_on = True
        elif ability == 'Vow of Silence':
            self.silence_since = self.clock

    def clear_persistent(self, at_once=False):
        """End the Embargo embers (they fade out) and the Silence fog."""
        self.embers_on = False
        if at_once:
            self.embers.strength = 0.0
        self.silence_since = None

    def set_aura(self, key, territory, neighbours=3):
        """The aura over the territory and its nearest neighbours (as if the player owned them)."""
        if key is None or territory is None:
            self.aura = None
            return
        cx, cy = self.world_centres[territory]
        near = sorted((t for t in map_data.get_neighbors(territory) if t in self.world_polygons),
                      key=lambda t: (self.world_centres[t][0] - cx) ** 2
                      + (self.world_centres[t][1] - cy) ** 2)
        self.aura = HeroAura(self.light, key)
        self.aura.set_territories([territory] + near[:neighbours])

    def update(self, dt):
        for effect in self.effects:
            effect.update(dt)
        self.effects = [e for e in self.effects if not e.is_finished()]
        if self.aura is not None:
            self.aura.update(dt, True)
        self.embers.update(dt, self.embers_on)

    # ---------- drawing ----------

    def _draw_fills(self):
        """Owner-coloured territory fills (alpha 80), as MapRenderer.draw_territories()."""
        key = (round(self.zoom, 4), round(self.centre[0], 1), round(self.centre[1], 1))
        if key != self._fill_key:
            self._fill = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            for territory, polygon in map_data.TERRITORY_POLYGONS.items():
                points = [self.to_screen(x, y) for x, y in polygon]
                pygame.draw.polygon(self._fill, (*self.owner_colour.get(territory, (200, 200, 200)), 80),
                                    points)
            self._fill_key = key
        self.screen.blit(self._fill, (0, 0))

    def render(self):
        """One frame; returns (under ms, over ms) spent on the hero effects."""
        perf = time.perf_counter
        self._draw_background()
        self._draw_fills()
        view = self.view()
        self.light.begin_frame()
        start = perf()
        if self.aura is not None:
            self.aura.render(view, self.clock)
        if self.embers.visible:
            self.embers.render(view, self.clock)
        for effect in self.effects:
            effect.render_under(view)
        under_ms = (perf() - start) * 1000

        # Plots (and, with P, the plot effects) between the two layers, as in the game
        self.show_rays = self.show_dust = self.show_plot_fx
        self._render_plots_only()

        # The Silence fog, over the plots and under the casts' over layer, as in the game
        start = perf()
        self._draw_silence_fog()
        for effect in self.effects:
            effect.render_over(view)
        over_ms = (perf() - start) * 1000
        return under_ms, over_ms

    def _draw_silence_fog(self):
        """Game.draw_silence_fog_overlay(): the vignette, faded in, then held."""
        if self.silence_since is None:
            return
        fog = self.hero_style['silence_fog']
        if self._fog is None or self._fog.get_size() != (self.width, self.height):
            self._fog = vignette_surface((self.width, self.height), fog['colour'],
                                         fog['centre_alpha'], fog['edge_alpha'])
        progress = min(1.0, (self.clock - self.silence_since) / fog['fade'])
        self._fog.set_alpha(int(255 * progress) if progress < 1.0 else 255)
        self.screen.blit(self._fog, (0, 0))

    def _render_plots_only(self):
        radius = int(EMPTY_PLOT_RADIUS * ui_scale_for(self.zoom))
        margin = radius * 3
        if self.show_plot_fx:
            self.dust.begin_frame()
        for plot in self.plots:
            x, y = self.to_screen(plot[2], plot[3])
            if not (-margin < x < self.width + margin and -margin < y < self.height + margin):
                continue
            if self.show_plot_fx and plot[8] is not None:
                plot[8].render(self.screen, x, y, radius, self.clock, self.rays)
            self._draw_plot(x, y, radius, plot[4], plot[5], plot[6])


def focus_territory(preview):
    """The territory with the most neighbours near the default view (a wide aura)."""
    candidates = [t for t in preview.world_polygons if map_data.TERRITORY_PLOTS.get(t)]
    cx, cy = preview.centre
    near = sorted(candidates, key=lambda t: (map_data.TERRITORY_CENTERS[t][0] - cx) ** 2
                  + (map_data.TERRITORY_CENTERS[t][1] - cy) ** 2)[:8]
    return max(near, key=lambda t: (len(map_data.get_neighbors(t)), t))


def run_live(look, size):
    pygame.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption('Hero ability effects preview')
    preview = HeroPreview(screen, look)
    font = pygame.font.SysFont('consolas', 16)
    clock = pygame.time.Clock()
    keys = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7,
            pygame.K_8, pygame.K_9, pygame.K_0, pygame.K_MINUS, pygame.K_EQUALS]
    names = ability_keys(preview.hero_style)
    aura_index = 0
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
                territory = preview.territory_at(pygame.mouse.get_pos())
                if event.key in keys and keys.index(event.key) < len(names):
                    preview.cast(names[keys.index(event.key)], territory)
                elif event.key == pygame.K_a:
                    aura_index = (aura_index + 1) % len(AURA_ORDER)
                    preview.set_aura(AURA_ORDER[aura_index], territory)
                elif event.key == pygame.K_l:
                    preview.load_look('2d' if preview.look == '3d' else '3d')
                    aura_index = 0
                elif event.key == pygame.K_c:
                    preview.clear_persistent()
                elif event.key == pygame.K_p:
                    preview.show_plot_fx = not preview.show_plot_fx
                elif event.key == pygame.K_SPACE:
                    preview.paused = not preview.paused
        if not preview.paused:
            step = min(dt, 0.05)
            preview.clock += step
            preview.update(step)
        start = time.perf_counter()
        under_ms, over_ms = preview.render()
        frame_ms = (time.perf_counter() - start) * 1000
        history = (history + [(frame_ms, under_ms, over_ms)])[-60:]
        avg = [sum(h[i] for h in history) / len(history) for i in range(3)]
        lines = [
            f"{clock.get_fps():6.1f} FPS   frame {avg[0]:5.2f} ms   hero fx under {avg[1]:5.2f} ms"
            f"   over {avg[2]:5.2f} ms   casts {len(preview.effects)}",
            f"look {preview.look}   zoom {preview.zoom:.2f}   aura {AURA_ORDER[aura_index] or 'off'}"
            f"{'   EMBARGO EMBERS' if preview.embers_on else ''}"
            f"{'   SILENCE FOG' if preview.silence_since is not None else ''}"
            f"{'   PAUSED' if preview.paused else ''}",
            '  '.join(f"{k}:{n}" for k, n in zip('1234567890-=', names))
            + '   A aura  C clear embers/fog  P plot fx  L look',
        ]
        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            pygame.draw.rect(screen, (0, 0, 0), text.get_rect(topleft=(8, 8 + i * 20)).inflate(8, 2))
            screen.blit(text, (8, 8 + i * 20))
        pygame.display.flip()


def _frames(preview, until, fps=60):
    """Advance the preview from 0 to `until` seconds at fps (no drawing)."""
    steps = int(round(until * fps))
    for _ in range(steps):
        preview.clock += 1.0 / fps
        preview.update(1.0 / fps)


def run_sheet(path, look, size, zoom=2.4, magnify=2, only=None):
    """
    Rows: the Defiance aura and each ability, cast on the focus territory; columns:
    moments after the cast. Cropped around the territory and magnified.
    """
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = HeroPreview(screen, look)
    territory = focus_territory(preview)
    font = pygame.font.SysFont('consolas', 15)
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    cell_w, cell_h = 330 * magnify, 230 * magnify
    rows = [('aura', key) for key in ('defiance', 'haste', 'safe_haven')]
    rows += [('ability', name) for name in preview.hero_style['abilities']]
    if only:
        rows = [r for r in rows if r[1] in only]
    aura_times = (0.05, 0.15, 0.3, 0.6, 1.0, 1.5)
    ability_times = (0.08, 0.25, 0.5, 0.9, 1.3, 1.8)   # arcs and Regicide run ~2 s
    times = aura_times
    sheet = pygame.Surface((cell_w * len(times), (cell_h + 20) * len(rows)))
    sheet.fill((30, 30, 30))
    for row, (kind, name) in enumerate(rows):
        # Auras cover several territories: a little further out, a wider crop
        row_zoom = max(MIN_ZOOM, zoom * 0.75) if kind == 'aura' else zoom
        crop_w, crop_h = (int(330 * zoom / row_zoom), int(230 * zoom / row_zoom))
        preview.zoom = row_zoom
        preview.centre = list(raw_centre)
        preview.clamp()
        cx, cy = preview.to_screen(*raw_centre)
        times = aura_times if kind == 'aura' else ability_times
        for col, t in enumerate(times):
            preview.effects = []
            preview.aura = None
            preview.clear_persistent(at_once=True)
            preview.clock = 0.0
            if kind == 'aura':
                preview.set_aura(name, territory)
            else:
                preview.cast(name, territory)
            # Two passes: the first builds every sprite (the frame budget), the second is the still
            _frames(preview, t)
            for _ in range(8):
                preview.render()
            crop = pygame.Rect(0, 0, crop_w, crop_h)
            crop.center = (cx, cy)
            cell = pygame.transform.smoothscale(screen.subsurface(crop.clip(screen.get_rect())),
                                                (cell_w, cell_h))
            top = row * (cell_h + 20)
            sheet.blit(cell, (col * cell_w, top + 20))
            caption = font.render(f'{name}  t={t:.2f}s  zoom {row_zoom:.2f}  ({preview.look})', True,
                                  (255, 255, 255))
            sheet.blit(caption, (col * cell_w + 6, top + 2))
    pygame.image.save(sheet, path)
    print(f'Wrote {path} ({territory})')
    pygame.quit()


def run_bench(look, size, frames=180):
    """Hero effect cost per frame (avg / worst ms) at three zooms, from cold caches."""
    pygame.init()
    screen = pygame.display.set_mode(size)
    preview = HeroPreview(screen, look)
    territory = focus_territory(preview)
    print(f'{look} look, {size[0]}x{size[1]}, focus {territory}; prewarm {preview.prewarm_ms:.1f} ms')
    print(f"{'zoom':>5} {'effect':>18} {'avg ms':>8} {'worst ms':>9}")
    raw_centre = map_data.TERRITORY_CENTERS[territory]
    scenarios = [('aura', 'defiance')] + [('ability', n) for n in preview.hero_style['abilities']]
    for zoom in (MIN_ZOOM, 2.4, MAX_ZOOM):
        for kind, name in scenarios:
            # Cold caches each row (the aura sprites are prewarmed at load, as in the game)
            preview.light = HeroLight(preview.world_polygons, preview.hero_style)
            preview.light.prewarm(plot_radii())
            preview.zoom = zoom
            preview.centre = list(raw_centre)
            preview.clamp()
            preview.effects = []
            preview.aura = None
            preview.embers = HeroAura(preview.light, 'embargo')   # on the new light
            preview.clear_persistent(at_once=True)
            preview.clock = 0.0
            if kind == 'aura':
                preview.set_aura(name, territory)
            else:
                preview.cast(name, territory)
            costs = []
            for i in range(frames):
                preview.clock += 1.0 / 60
                preview.update(1.0 / 60)
                under_ms, over_ms = preview.render()
                costs.append(under_ms + over_ms)
                if kind == 'ability' and not preview.effects:
                    break
            label = f'{name} ({len(preview.aura.territories)})' if kind == 'aura' else name
            print(f'{zoom:5.2f} {label:>18} {sum(costs) / len(costs):8.3f} {max(costs):9.3f}')
    glow = preview.light.glow
    nbytes = sum(s.get_width() * s.get_height() * s.get_bytesize() for s in glow._sprites.values())
    print(f'glow sprites: {len(glow._sprites)} ({nbytes / 1e6:.1f} MB)')
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description='Hero ability effects preview')
    parser.add_argument('--look', choices=('2d', '3d'), default='2d')
    parser.add_argument('--size', default='1600x850', help='window size, e.g. 1920x1080')
    parser.add_argument('--sheet', help='write a contact sheet of stills to this PNG and exit')
    parser.add_argument('--zoom', type=float, default=2.4, help='zoom for --sheet')
    parser.add_argument('--only', nargs='*', help='with --sheet: only these effects (names / aura keys)')
    parser.add_argument('--bench', action='store_true', help="print the effects' frame cost and exit")
    args = parser.parse_args()
    size = tuple(int(v) for v in args.size.lower().split('x'))
    if args.bench:
        run_bench(args.look, size)
    elif args.sheet:
        run_sheet(args.sheet, args.look, size, zoom=args.zoom, only=args.only)
    else:
        run_live(args.look, size)


if __name__ == '__main__':
    main()
