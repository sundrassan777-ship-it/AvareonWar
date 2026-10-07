# -*- coding: utf-8 -*-
"""
East map extension — fills the strip past the map background's right edge.

WHY THIS EXISTS
The map background is left-aligned (camera min_x = 0). On a 16:9 window at the
minimum zoom (1.65) the scaled map is narrower than the window, so it ends before
the right edge: at 1600x900 the map stops at x=1427 and the frame's white fill
shows from 1427 to 1600. The right sidebar (x >= 1350) used to hide that strip.
Once the sidebar can collapse, the strip would be exposed, so this module draws a
continuation of the map there instead. Zoom is never changed for it.

WHAT IT DRAWS
* Override: if '<background path without .png>_east.png' exists (for example
  maps/azincournean_highlands/map_east.png or assets/CampaignMaps/Campaign3Map_east.png),
  that painted image is drawn, scaled to the map's height. Anything past its end is
  filled with the average colour of its rightmost column.
* Generated (default): the map's rightmost strip, mirrored horizontally (so the seam
  is seamless), fading into MAP_EAST_FOG_COLOR. Past its end is solid fog.

COST
The extension is built once per (map surface, window width) and stored at a reduced
density capped at MAP_EAST_MAX_PIXELS. Per frame it costs one blit while the camera
is static; a rescale of only the visible slice happens when the zoom changes (the
same viewport-cache pattern as Game._blit_map_background).
"""

import math
import os

import pygame

from config.constants import (
    MAP_EAST_FOG_COLOR, MAP_EAST_MIN_SRC_PX, MAP_EAST_MAX_SRC_PX, MAP_EAST_MAX_PIXELS,
    MAP_EAST_BLUR_FACTOR, MAP_EAST_CRISP_BAND,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def east_extension_override_path(background_path):
    """Path of the optional painted extension for a map background, or None.

    The rule is '<background without extension>_east.png', so one rule covers
    maps/<id>/map.png, assets/map.png and the campaign map images.
    """
    if not background_path:
        return None
    root, _ext = os.path.splitext(background_path)
    return root + '_east.png'


def required_source_width(src_w, window_w, map_width, min_zoom):
    """Source pixels needed to cover the widest east gap (at minimum zoom).

    At zoom z the map covers map_width * z screen px, and one screen px is
    src_w / (map_width * z) source px. The gap is widest at the minimum zoom.
    Returns 0 when the map already reaches the window edge at minimum zoom
    (16:10 and 4:3 windows).
    """
    scaled = map_width * min_zoom
    if scaled <= 0:
        return 0
    gap = window_w - scaled
    if gap <= 0:
        return 0
    return gap * src_w / scaled


def _storage_density(logical_w, src_h, src_w, window_w, max_pixels):
    """Scale at which the extension is stored (<= 1.0).

    Any zoom that shows a gap renders fewer than window_w / src_w screen px per
    source px (otherwise the map would reach the window edge), so storing at that
    density is lossless. The pixel cap bounds memory on ultrawide windows.
    """
    density = min(1.0, window_w / max(1, src_w))
    cap = math.sqrt(max_pixels / max(1, logical_w * src_h))
    return max(0.01, min(density, cap))


def _fog_ramp(width, height, fog_color):
    """SRCALPHA overlay: transparent at x=0, fully fog-coloured at x=width-1.

    Built as a width x 1 row and stretched vertically, so only `width` pixels
    are computed (no per-pixel work over the full surface).
    """
    row = pygame.Surface((width, 1), pygame.SRCALPHA)
    last = max(1, width - 1)
    for x in range(width):
        t = x / last
        # smoothstep: a gentle start keeps the mirrored terrain readable near the seam
        alpha = int(round(255 * t * t * (3.0 - 2.0 * t)))
        row.set_at((x, 0), (*fog_color, alpha))
    return pygame.transform.scale(row, (width, height))


def _blurred(surface, factor):
    """Cheap box-ish blur: smoothscale down by `factor`, then back up."""
    w, h = surface.get_size()
    small = pygame.transform.smoothscale(surface, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def _fade_out_right(surface, band):
    """Copy of `surface`'s leftmost `band` columns, opaque at x=0 and transparent at band.

    Uses a BLEND_RGBA_MULT alpha ramp (no per-pixel loops over the surface).
    """
    w, h = surface.get_size()
    band = max(1, min(band, w))
    # Fresh SRCALPHA surface (opaque copy of the band) — works with or without a display
    piece = pygame.Surface((band, h), pygame.SRCALPHA)
    piece.blit(surface, (0, 0), pygame.Rect(0, 0, band, h))
    row = pygame.Surface((band, 1), pygame.SRCALPHA)
    last = max(1, band - 1)
    for x in range(band):
        row.set_at((x, 0), (255, 255, 255, int(round(255 * (1.0 - x / last)))))
    piece.blit(pygame.transform.scale(row, (band, h)), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return piece


def _to_display_format(surface):
    """Convert to the display's pixel format when a display exists (fast blits)."""
    if pygame.display.get_init() and pygame.display.get_surface() is not None:
        try:
            return surface.convert()
        except pygame.error:
            pass
    return surface


class MapEastExtension:
    """Builds and draws the east extension for one Game.

    Lifecycle: Game calls ensure_built() lazily from the render path (so missions
    that bake cloud cover into the map AFTER loading are included) and invalidate()
    whenever the map background or the display changes.
    """

    def __init__(self, fog_color=MAP_EAST_FOG_COLOR):
        self.fog_color = tuple(fog_color)
        # Built extension
        self.surface = None          # Stored (reduced density) extension, display format
        self.logical_width = 0       # Extension width in SOURCE pixels (map-image space)
        self.fill_color = self.fog_color  # Colour beyond the extension's end
        self.is_override = False
        self._build_key = None
        # Viewport cache (scaled slice of the extension) — mirrors _map_view_* in main.py
        self._view_key = None
        self._view_surface = None
        self._view_offset = (0, 0)

    # ------------------------------------------------------------------ build

    def invalidate(self):
        """Forget the built extension and its scaled slice."""
        self.surface = None
        self.logical_width = 0
        self.fill_color = self.fog_color
        self.is_override = False
        self._build_key = None
        self._view_key = None
        self._view_surface = None
        self._view_offset = (0, 0)

    def ensure_built(self, src, window_w, map_width, min_zoom, override_path=None,
                     max_pixels=MAP_EAST_MAX_PIXELS):
        """Build the extension if the inputs changed since the last build.

        Note: a mission that draws INTO src (cloud cover) keeps id(src) unchanged,
        so such code must call invalidate() itself.
        """
        key = (id(src), src.get_size(), int(window_w), int(map_width),
               round(float(min_zoom), 4), override_path, max_pixels)
        if key == self._build_key:
            return  # Built (or a failed build) for these inputs — don't retry per frame
        self.invalidate()
        self._build_key = key

        src_w, src_h = src.get_size()
        if src_w <= 0 or src_h <= 0:
            return

        if override_path and os.path.exists(override_path):
            if self._build_from_override(override_path, src_w, src_h, window_w, max_pixels):
                return
        self._build_generated(src, src_w, src_h, window_w, map_width, min_zoom, max_pixels)

    def _build_from_override(self, path, src_w, src_h, window_w, max_pixels):
        """Use a painted extension image. Returns False if it can't be loaded."""
        try:
            image = pygame.image.load(path)
        except pygame.error as exc:
            logger.warning(f"Could not load map east extension '{path}': {exc}")
            return False
        img_w, img_h = image.get_size()
        if img_w <= 0 or img_h <= 0:
            return False
        image = _to_display_format(image)

        # Scale to the source map's height; its width in source px follows the aspect ratio
        logical_w = max(1, int(round(img_w * src_h / img_h)))
        density = _storage_density(logical_w, src_h, src_w, window_w, max_pixels)
        store_size = (max(1, int(logical_w * density)), max(1, int(src_h * density)))
        self.surface = _to_display_format(pygame.transform.smoothscale(image, store_size))
        self.logical_width = logical_w
        self.is_override = True
        # Past the painted image's end: continue with its rightmost column's colour
        edge = image.subsurface(pygame.Rect(img_w - 1, 0, 1, img_h))
        self.fill_color = tuple(pygame.transform.average_color(edge)[:3])
        logger.info(f"Map east extension: using painted override '{path}' "
                    f"({img_w}x{img_h}, stored {store_size[0]}x{store_size[1]})")
        return True

    def _build_generated(self, src, src_w, src_h, window_w, map_width, min_zoom, max_pixels):
        """Mirror the map's rightmost strip and fade it into the fog colour."""
        needed = required_source_width(src_w, window_w, map_width, min_zoom)
        logical_w = int(math.ceil(needed))
        logical_w = max(MAP_EAST_MIN_SRC_PX, min(MAP_EAST_MAX_SRC_PX, logical_w))
        logical_w = min(logical_w, src_w)  # cannot mirror more than the whole map

        density = _storage_density(logical_w, src_h, src_w, window_w, max_pixels)
        store_size = (max(1, int(logical_w * density)), max(1, int(src_h * density)))

        strip = src.subsurface(pygame.Rect(src_w - logical_w, 0, logical_w, src_h))
        mirrored = pygame.transform.flip(strip, True, False)
        crisp = pygame.transform.smoothscale(mirrored, store_size)

        # A plain mirror reads as mirrored map art (reversed labels, the Avareon scale
        # bar). Blur it so only colour masses (sea / land) continue, and keep the crisp
        # mirror for a thin band at the seam only, so the join itself stays seamless.
        stored = _blurred(crisp, MAP_EAST_BLUR_FACTOR)
        band = max(4, int(store_size[0] * MAP_EAST_CRISP_BAND))
        stored.blit(_fade_out_right(crisp, band), (0, 0))
        stored.blit(_fog_ramp(store_size[0], store_size[1], self.fog_color), (0, 0))

        self.surface = _to_display_format(stored)
        self.logical_width = logical_w
        self.fill_color = self.fog_color
        self.is_override = False

    # ------------------------------------------------------------------- draw

    def draw(self, screen, map_right, map_y, scaled_map_width, scaled_map_height,
             src_w, vis_top, vis_bottom, margin=0):
        """Draw the extension to the right of the map's right edge.

        Args:
            map_right: Screen x where the map background ends.
            map_y: Screen y of the map's top edge.
            scaled_map_width/height: On-screen size of the whole map at this zoom.
            src_w: Width of the map source image (defines source -> screen scale).
            vis_top/vis_bottom: Visible vertical range of the map area on screen.
            margin: Extra rows rendered above/below while the zoom is unchanged, so
                vertical panning re-blits instead of rescaling.
        """
        screen_w = screen.get_width()
        gap_w = screen_w - map_right
        if gap_w <= 0 or vis_bottom <= vis_top or scaled_map_width <= 0 or src_w <= 0:
            return

        # On-screen width of the whole extension at this zoom
        ext_screen_w = 0
        if self.surface is not None and self.logical_width > 0:
            ext_screen_w = int(self.logical_width * scaled_map_width / src_w)

        drawn_w = min(gap_w, ext_screen_w)
        if drawn_w > 0:
            self._blit_slice(screen, map_right, map_y, ext_screen_w, scaled_map_height,
                             drawn_w, vis_top, vis_bottom, margin)

        # Anything beyond the extension's end (ultrawide windows, missing build)
        if drawn_w < gap_w:
            screen.fill(self.fill_color,
                        pygame.Rect(map_right + drawn_w, vis_top, gap_w - drawn_w,
                                    vis_bottom - vis_top))

    def _blit_slice(self, screen, map_right, map_y, ext_screen_w, ext_screen_h,
                    drawn_w, vis_top, vis_bottom, margin):
        """Scale (or reuse) the visible slice of the extension and blit it."""
        stored_w, stored_h = self.surface.get_size()
        # Wanted region, in "scaled-extension space" (relative to its top-left corner)
        want_x1 = drawn_w
        want_y0 = max(0, vis_top - map_y)
        want_y1 = min(ext_screen_h, vis_bottom - map_y)
        if want_y1 <= want_y0:
            return

        size_key = (id(self.surface), ext_screen_w, ext_screen_h)
        cached = self._view_key
        reusable = (
            cached is not None
            and self._view_surface is not None
            and cached[0] == size_key
            and cached[1] >= want_x1
            and cached[2] <= want_y0 and cached[3] >= want_y1
        )
        if not reusable:
            # Only spend the margin when the zoom held still (same idea as the map cache:
            # during continuous zooming every frame rebuilds anyway).
            use_margin = margin if (cached is not None and cached[0] == size_key) else 0
            reg_y0 = int(max(0, want_y0 - use_margin))
            reg_y1 = int(min(ext_screen_h, want_y1 + use_margin))
            reg_w = max(1, int(want_x1))
            reg_h = max(1, reg_y1 - reg_y0)

            x_ratio = stored_w / max(1, ext_screen_w)
            y_ratio = stored_h / max(1, ext_screen_h)
            src_x = 0
            src_y = max(0, min(stored_h - 1, int(reg_y0 * y_ratio)))
            src_w_slice = max(1, min(stored_w - src_x, int(math.ceil(reg_w * x_ratio))))
            src_h_slice = max(1, min(stored_h - src_y, int(math.ceil(reg_h * y_ratio))))

            if self._view_surface is None or self._view_surface.get_size() != (reg_w, reg_h):
                self._view_surface = _to_display_format(pygame.Surface((reg_w, reg_h)))
            sub = self.surface.subsurface(pygame.Rect(src_x, src_y, src_w_slice, src_h_slice))
            try:
                pygame.transform.smoothscale(sub, (reg_w, reg_h), self._view_surface)
            except (ValueError, pygame.error):
                # Format mismatch (e.g. no display yet) — fall back to a fresh surface
                self._view_surface = pygame.transform.smoothscale(sub, (reg_w, reg_h))
            self._view_key = (size_key, reg_w, reg_y0, reg_y1)
            self._view_offset = (0, reg_y0)

        off_x, off_y = self._view_offset
        # Clip vertically to the map area: the top/bottom panels are drawn later anyway,
        # but keep the fill and the slice consistent.
        area = pygame.Rect(0, max(0, vis_top - (map_y + off_y)), drawn_w,
                           max(0, vis_bottom - vis_top))
        screen.blit(self._view_surface, (map_right + off_x, map_y + off_y + area.y), area)
