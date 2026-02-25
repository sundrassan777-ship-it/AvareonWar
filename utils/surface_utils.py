# utils/surface_utils.py
# Shared surface manipulation utilities (Phase 5A dedup)

import pygame


def crop_to_opaque(surface, threshold=128):
    """
    Crop a surface to its opaque bounding box.

    Scans all pixels to find the smallest rectangle containing all pixels
    with alpha > threshold. Used during asset loading (not per-frame).

    Args:
        surface: pygame.Surface with per-pixel alpha
        threshold: Minimum alpha value to consider opaque (default 128)

    Returns:
        New pygame.Surface cropped to opaque content, or a copy of the
        original surface if no opaque pixels are found.
    """
    w, h = surface.get_size()
    top, bottom, left, right = h, 0, w, 0
    for y in range(h):
        for x in range(w):
            if surface.get_at((x, y)).a > threshold:
                top = min(top, y)
                bottom = max(bottom, y)
                left = min(left, x)
                right = max(right, x)
    if bottom < top or right < left:
        return surface.copy()
    crop_rect = pygame.Rect(left, top, right - left + 1, bottom - top + 1)
    return surface.subsurface(crop_rect).copy()
