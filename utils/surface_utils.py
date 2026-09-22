# utils/surface_utils.py
# Shared surface manipulation utilities (Phase 5A dedup)

import pygame


def crop_to_opaque(surface, threshold=128):
    """
    Crop a surface to its opaque bounding box.

    Finds the smallest rectangle containing all pixels with alpha > threshold.
    Used during asset loading (not per-frame).

    Uses Surface.get_bounding_rect(), which is the C-speed equivalent of a
    per-pixel get_at() scan. min_alpha is inclusive ('>=') while this function's
    threshold is exclusive ('>'), hence the +1. On CampaignBTN.png this returns
    an identical rect to the old pixel loop in ~4 ms instead of ~276 ms, which
    matters because screens that crop it are reconstructed on every open.

    Args:
        surface: pygame.Surface with per-pixel alpha
        threshold: Alpha value a pixel must exceed to count as opaque (default 128)

    Returns:
        New pygame.Surface cropped to opaque content, or a copy of the
        original surface if no opaque pixels are found.
    """
    crop_rect = surface.get_bounding_rect(min_alpha=threshold + 1)
    if crop_rect.width <= 0 or crop_rect.height <= 0:
        return surface.copy()
    return surface.subsurface(crop_rect).copy()


# Process-wide cache of decoded images. Decoding the large menu PNGs costs
# 35-70 ms each, and the browser screens are reconstructed on every open, so
# the decode is shared rather than repeated. Converted surfaces stay valid
# across display-mode changes, so this is safe to hold for the process.
_image_cache = {}


def load_cached_image(path, alpha=True):
    """
    Load and convert an image once per process, reusing it on later calls.

    Args:
        path: Path to the image file
        alpha: True for convert_alpha() (per-pixel transparency), else convert()

    Returns:
        pygame.Surface, or None if the file could not be loaded.
    """
    key = (path, alpha)
    if key not in _image_cache:
        try:
            image = pygame.image.load(path)
            _image_cache[key] = image.convert_alpha() if alpha else image.convert()
        except pygame.error:
            _image_cache[key] = None
    return _image_cache[key]


_cropped_button = []


def get_campaign_button_image():
    """
    The shared ornate button art (assets/CampaignBTN.png), cropped to its opaque
    bounds. Used by the browser screens; cached because they are rebuilt on every
    open. Returns None if the asset is missing.
    """
    if not _cropped_button:
        raw = load_cached_image("assets/CampaignBTN.png", alpha=True)
        _cropped_button.append(crop_to_opaque(raw, threshold=128) if raw else None)
    return _cropped_button[0]
