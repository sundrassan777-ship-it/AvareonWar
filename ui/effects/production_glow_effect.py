# -*- coding: utf-8 -*-
"""
Production Glow Effect (production light rays)

Soft rays of light slowly turning behind plots with active production - Barracks
training units, Keeps/Castles training heroes - in the style of BFME II's War of
the Ring map (owner request, 2026-10-26):
- Two counter-rotating layers of soft beams (7 long, 5 short) emerging from
  behind the plot, plus a faint halo just outside its rim
- Additive light in the owner's colour softened toward warm white
- Sized by the plot radius, so it matches the plot at every zoom

Pieces:
    ProductionRays        shared renderer (one per MapRenderer): builds and
                          rotates the frames, shared by every producing plot
    ProductionGlowEffect  one producing plot: territory, plot index, colour, phase

Integration:
    - MapRenderer.sync_production_glow_effects() creates/removes effects as
      training queues change (game_state._training_version dirty flag)
    - MapRenderer.render_production_glow_effects() draws them just before the
      plots, so the plots cover the inner ends of the rays
    - The shared clock is advanced by MapRenderer.update_plot_effects()
    - Styles: plot_fx_style.RAY_STYLE
"""

import pygame
import math
from collections import OrderedDict

from ui.effects.plot_fx_style import RAY_STYLE, plot_phase
from ui.effects import light_fx


# ========================================
# PRODUCTION LIGHT RAYS (shared renderer)
# ========================================
# Replaced the old 8-ray "star" (2026-10-26), which baked 16 frames 22.5 deg apart: with
# 8 rays repeating every 45 deg that gave only TWO distinct poses, so the "rotation"
# was a toggle every ~2.6 s. It was also sized by camera_zoom while plots use
# ui_scale, so at min zoom the rays poked ~4 px past the plot ring.
#
# How it stays smooth AND cheap with dozens of producing plots:
# - Sized by the plot radius rounded to even px (16..24): 5 sizes over the zoom range
# - Per (plot radius, player colour, phase group, layer) there is ONE current frame,
#   shared by every plot in that group. It is re-rotated (rotozoom, 0.06-0.12 ms)
#   only when the angle crosses an angle_step (0.25 deg = ~0.13 px where the rays
#   are bright, ~28 times a second): smooth motion, a few rotations per frame in
#   total, no frame archive in memory.
#   (A baked archive of 1-2 deg steps was tried first: the rays visibly ticked a
#   pixel at a time, 2-5 times a second. Fine steps would need ~25 MB per colour,
#   and 8-bit palette frames blit ~30x slower with BLEND_RGB_ADD.)
# - Plots are split into phase_groups by their stable phase, so neighbours don't
#   turn in lockstep.
# - Additive light on opaque black frames: one BLEND_RGB_ADD blit per layer, no
#   per-pixel alpha (black adds nothing).

SUPERSAMPLE = 2          # rays are drawn at 2x and smoothscaled down: soft, anti-aliased edges
WEDGE_LEVELS = 6         # nested wedges per ray -> a soft "tent" cross-section


# The light helpers are shared with the hero ability effects (light_fx.py)
_new_black_surface = light_fx.new_black_surface
_radial_surface = light_fx.radial_surface


def light_colour(player_color, style=RAY_STYLE):
    """The player colour blended toward warm white, so the rays read as light, not paint."""
    return light_fx.light_colour(player_color, style['white_mix'], style['warm_white'])


class _RaySet:
    """One (plot radius, colour): per layer, the tinted base and the current frames."""

    __slots__ = ('layers',)

    def __init__(self, layers):
        self.layers = layers   # [_RayLayer, ...]


class _RayLayer:
    """
    One layer of one ray set: the tinted, unrotated base and, per phase group, the
    frame currently shown ([angle step index, persistent canvas]).
    """

    __slots__ = ('base', 'span', 'speed', 'size', 'half', 'current')

    def __init__(self, base, span, speed, groups):
        self.base = base
        self.span = span              # degrees after which the layer looks the same again
        self.speed = speed            # degrees per second
        self.size = base.get_width()
        self.half = self.size // 2
        # Canvas per group, reused for every re-rotation (no per-frame allocation besides
        # rotozoom's own result). Index -1 = nothing drawn yet.
        self.current = [[-1, _new_black_surface(self.size)] for _ in range(groups)]


class ProductionRays:
    """
    Shared light-ray renderer for every producing plot (one per MapRenderer).

    Usage per frame:
        for each producing plot:
            for surface, half in rays.layer_frames(radius, colour, clock, phase):
                screen.blit(surface, (x - half, y - half), special_flags=pygame.BLEND_RGB_ADD)
    """

    MAX_SETS = 8          # (radius, colour) sets kept (LRU); ~0.2-0.6 MB each
    MAX_GREY_BASES = 8    # colour-free layer bases kept, keyed by radius

    def __init__(self, style=RAY_STYLE):
        self.style = style
        self._step = float(style['angle_step'])
        self._groups = max(1, int(style['phase_groups']))
        self._sets = OrderedDict()        # (radius, colour) -> _RaySet
        self._grey_bases = OrderedDict()  # radius -> [(rays grey, halo grey or None, size), ...]
        self.rotations = 0                # lifetime count of re-rotations (tests, benchmarks)

    def prewarm(self, radii):
        """
        Build the colour-free layer bases for these plot radii now (~1 ms each), so a
        zoom never pays for one mid-game. Call at load with the zoom range's radii.
        """
        for radius in sorted({(r + 1) & ~1 for r in radii}):
            self._get_grey_bases(radius)

    def reach(self, radius):
        """How far the light can reach from a plot's centre, in px (for off-screen culling)."""
        return int(math.ceil(max(layer['reach'] for layer in self.style['layers']) * (radius + 1))) + 2

    # ---------- per frame ----------

    def layer_frames(self, radius, colour, clock, phase):
        """
        The surfaces to blit for one producing plot, as [(surface, half_size), ...].

        Args:
            radius: plot radius in px (int(EMPTY_PLOT_RADIUS * ui_scale))
            colour: player (r, g, b)
            clock: shared effect clock, seconds
            phase: the plot's stable offset in [0, 1) (plot_fx_style.plot_phase)
        """
        # Even radii only (16, 18 ... 24): 5 sets across the zoom range instead of 9.
        # At most 1 px off, invisible on soft light.
        ray_set = self._get_set((radius + 1) & ~1, tuple(colour[:3]))
        groups = self._groups
        group = int(phase * groups) % groups
        step = self._step
        result = []
        for layer in ray_set.layers:
            span = layer.span
            # Groups are spread evenly over the layer's symmetry span
            angle = (clock * layer.speed + group * span / groups) % span
            index = int(angle / step)
            slot = layer.current[group]
            if slot[0] != index:
                self._rotate_into(layer, slot, index * step)
                slot[0] = index
            result.append((slot[1], layer.half))
        return result

    def _rotate_into(self, layer, slot, angle):
        """Redraw a group's canvas as the layer's base rotated by angle degrees."""
        rotated = pygame.transform.rotozoom(layer.base, angle, 1.0)
        canvas = slot[1]
        canvas.fill((0, 0, 0))
        # Even sizes in and out (checked: rotozoom of an even square is an even square),
        # so the offset is exact and the rays never wobble. Additive copy: takes the RGB
        # exactly and ignores any alpha; the rotated corners fall outside the canvas
        # (the light never reaches them).
        size = layer.size
        canvas.blit(rotated, ((size - rotated.get_width()) // 2, (size - rotated.get_height()) // 2),
                    special_flags=pygame.BLEND_RGB_ADD)
        self.rotations += 1

    # ---------- building ----------

    def _get_set(self, radius, colour):
        key = (radius, colour)
        ray_set = self._sets.get(key)
        if ray_set is not None:
            self._sets.move_to_end(key)
            return ray_set
        ray_set = self._build_set(radius, colour)
        self._sets[key] = ray_set
        if len(self._sets) > self.MAX_SETS:
            self._sets.popitem(last=False)   # least recently used
        return ray_set

    def _build_set(self, radius, colour):
        """Tint the colour-free bases for one colour (~0.3 ms)."""
        light = light_colour(colour, self.style)
        layers = []
        for layer, (rays_grey, halo_grey, size) in zip(self.style['layers'], self._get_grey_bases(radius)):
            tinted = rays_grey.copy()
            gain = layer['intensity']
            tinted.fill(tuple(int(c * gain) for c in light), special_flags=pygame.BLEND_RGB_MULT)
            if halo_grey is not None:
                halo = halo_grey.copy()
                halo_gain = self.style['halo_intensity']
                halo.fill(tuple(int(c * halo_gain) for c in light), special_flags=pygame.BLEND_RGB_MULT)
                tinted.blit(halo, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            layers.append(_RayLayer(tinted, 360.0 / layer['count'], layer['speed'], self._groups))
        return _RaySet(layers)

    def _get_grey_bases(self, radius):
        bases = self._grey_bases.get(radius)
        if bases is None:
            bases = [self._build_grey_base(radius, layer, with_halo=(i == 0))
                     for i, layer in enumerate(self.style['layers'])]
            self._grey_bases[radius] = bases
            if len(self._grey_bases) > self.MAX_GREY_BASES:
                self._grey_bases.popitem(last=False)
        else:
            self._grey_bases.move_to_end(radius)
        return bases

    def _build_grey_base(self, radius, layer, with_halo):
        """
        One layer's rays (and the halo, on the first layer) in grey, unrotated.

        Returns (rays, halo or None, size). size is even, which keeps rotozoom's
        output centred on the plot (odd sizes wobble by half a pixel).
        """
        style = self.style
        reach = layer['reach'] * radius
        size = 2 * int(math.ceil(reach)) + 4
        size += size % 2

        # Rays: nested wedges, widest and dimmest first, at SUPERSAMPLE x for soft edges
        big = _new_black_surface(size * SUPERSAMPLE)
        centre = size * SUPERSAMPLE / 2.0
        inner = style['inner'] * radius * SUPERSAMPLE
        outer = (reach + 1) * SUPERSAMPLE
        gains = layer['ray_gain']
        for k in range(layer['count']):
            angle = math.radians(k * 360.0 / layer['count'])
            gain = gains[k % len(gains)]
            for level in range(WEDGE_LEVELS):
                half = math.radians(layer['half_angle'] * (1.0 - level / float(WEDGE_LEVELS)))
                value = int(255 * gain * (level + 1) / WEDGE_LEVELS)
                points = [
                    (centre + inner * math.cos(angle - half), centre + inner * math.sin(angle - half)),
                    (centre + outer * math.cos(angle - half), centre + outer * math.sin(angle - half)),
                    (centre + outer * math.cos(angle), centre + outer * math.sin(angle)),
                    (centre + outer * math.cos(angle + half), centre + outer * math.sin(angle + half)),
                    (centre + inner * math.cos(angle + half), centre + inner * math.sin(angle + half)),
                ]
                pygame.draw.polygon(big, (value, value, value), points)
        rays = pygame.transform.smoothscale(big, (size, size))
        if pygame.display.get_surface() is not None:
            rays = rays.convert()

        # Brightness along the rays: full at the plot rim, fading to nothing at the reach
        power = style['falloff_power']
        span = max(1.0, reach - radius)

        def along(r):
            if r <= radius:
                return 1.0
            return max(0.0, 1.0 - (r - radius) / span) ** power

        rays.blit(_radial_surface(size, along), (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        halo = None
        if with_halo:
            width = max(1.0, style['halo_width'] * radius)
            halo = _radial_surface(size, lambda r: math.exp(-((r - radius - 1) / width) ** 2))
        return rays, halo, size



# ========================================
# ONE PRODUCING PLOT
# ========================================

class ProductionGlowEffect:
    """
    The light rays of one producing plot (MapRenderer.production_glow_effects).

    Holds only what is per plot - which plot, whose colour, its phase - while the
    frames come from the shared ProductionRays. The plot is kept as (territory,
    plot_index), not a position: MapRenderer looks the position up every frame,
    so the rays follow the plots through a resolution change (a stored world
    position went stale when apply_display_settings() rescaled the plots).

    Continuous: there is no duration; sync_production_glow_effects() removes it
    when production stops.
    """

    def __init__(self, territory, plot_index, player_color):
        self.territory = territory
        self.plot_index = plot_index
        self.player_color = tuple(player_color[:3])
        # Stable per plot, so neighbouring plots are not in lockstep
        self.phase = plot_phase(territory, plot_index)

    def update_color(self, new_color):
        """Follow a change of owner colour (frames are shared per colour, nothing to rebuild)."""
        self.player_color = tuple(new_color[:3])

    def render(self, screen, x, y, radius, clock, rays):
        """
        Add this plot's rays to the screen, centred on (x, y).

        Args:
            screen: target surface
            x, y: plot centre in screen px (ints)
            radius: plot radius in px (int(EMPTY_PLOT_RADIUS * ui_scale))
            clock: shared plot-effect clock, seconds
            rays: the shared ProductionRays
        """
        for surface, half in rays.layer_frames(radius, self.player_color, clock, self.phase):
            screen.blit(surface, (x - half, y - half), special_flags=pygame.BLEND_RGB_ADD)
