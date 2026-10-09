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

# CampaignBTN.png (cropped by get_campaign_button_image(), 1502x297): the wooden
# window between the gold end caps and rails, as (x, y, w, h). Measured from the
# art (2026-10-08). tint_campaign_button_wood() tints only the wood inside it, so
# a coloured button keeps its gold frame (the whole-sprite multiply turned the
# frame green/blue too).
CAMPAIGN_BTN_WOOD_RECT = (228, 54, 1048, 189)
# Pixels whose green channel is at least this are gold frame, not wood: wood tops
# out around g=120, the gold rails start around g=130.
CAMPAIGN_BTN_GOLD_MIN_G = 125

# BattleBar.png (1536x1024): the frame's opaque bounds, and the inner window (in
# coordinates of that crop) where the fill shows. The fill rect overshoots the
# window slightly so its edges hide under the frame; BAR_FILL_HIDDEN_LEFT px of
# it sit under the left end cap, so an empty bar shows no fill. Shared by the
# Tales' Popularity widget and the bottom panel's planning timer.
BAR_FRAME_CROP = (46, 358, 1439, 174)
BAR_FILL_LEFT, BAR_FILL_RIGHT = 216, 1226
BAR_FILL_TOP, BAR_FILL_BOTTOM = 36, 128
BAR_FILL_HIDDEN_LEFT = 21


def tint_campaign_button_wood(image, tint):
    """
    A copy of the cropped CampaignBTN art with only its wooden window multiplied
    by `tint` (r, g, b); the gold frame is untouched.

    The wood is selected with a pygame mask (window rect AND "not gold" by the
    green channel), so no numpy is needed. Load-time cost only - callers cache.
    """
    if image is None:
        return None
    w, h = image.get_size()
    # Scale the measured window if the art was replaced at another size
    sx, sy = w / 1502.0, h / 297.0
    rx, ry, rw, rh = CAMPAIGN_BTN_WOOD_RECT
    window = pygame.Rect(round(rx * sx), round(ry * sy), round(rw * sx), round(rh * sy)).clip(image.get_rect())
    # Opaque (alpha > 200) pixels with g < CAMPAIGN_BTN_GOLD_MIN_G: from_threshold
    # matches when |pixel - colour| < threshold on every channel
    g_mid = CAMPAIGN_BTN_GOLD_MIN_G // 2
    wood = pygame.mask.from_threshold(image, (128, g_mid, 128, 228),
                                      (129, CAMPAIGN_BTN_GOLD_MIN_G - g_mid, 129, 28))
    in_window = pygame.mask.Mask((w, h))
    in_window.draw(pygame.mask.Mask(window.size, fill=True), window.topleft)
    wood = wood.overlap_mask(in_window, (0, 0))

    # Tinted copy, cut down to the wood by the mask's alpha, laid over the original.
    # The wood is greyed first: multiplying brown wood by blue gave mud, not blue.
    # Grey wood is dark (~75), so the tinted result is doubled to keep it readable.
    tinted = pygame.transform.grayscale(image)
    tinted.fill((tint[0], tint[1], tint[2], 255), special_flags=pygame.BLEND_RGBA_MULT)
    tinted.blit(tinted.copy(), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    cut = wood.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0))
    tinted.blit(cut, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    result = image.copy()
    result.blit(tinted, (0, 0))
    return result
