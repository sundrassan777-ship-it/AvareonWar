"""
Shared custom cursor utility.
Hides the system cursor and draws Cursor.png at the mouse position each frame.
Used across all screens (main menu, setup, game, campaign, recap, loading, cutscenes).
Attack cursor (AttackCursor.png) shown when hovering enemy/neutral territories with army selected.
"""
import pygame

_cached_cursor = None
_hotspot = (0, 0)  # Pixel offset of arrow tip within scaled cursor image

_cached_attack_cursor = None
_attack_hotspot = (0, 0)  # Pixel offset of sword tip within scaled attack cursor


def draw_custom_cursor(screen):
    """Draw Cursor.png at mouse position. Call just before display.flip()."""
    global _cached_cursor, _hotspot
    if _cached_cursor is None:
        try:
            img = pygame.image.load('assets/Cursor.png').convert_alpha()
            # Scale to 5% of original size
            new_w = max(1, int(img.get_width() * 0.05))
            new_h = max(1, int(img.get_height() * 0.05))
            _cached_cursor = pygame.transform.smoothscale(img, (new_w, new_h))
            # Arrow tip is ~25% from left, ~8% from top of the image
            _hotspot = (int(new_w * 0.25), int(new_h * 0.08))
        except pygame.error:
            return
    mx, my = pygame.mouse.get_pos()
    screen.blit(_cached_cursor, (mx - _hotspot[0], my - _hotspot[1]))


def draw_attack_cursor(screen):
    """Draw AttackCursor.png (sword) at mouse position for enemy/neutral territory hover."""
    global _cached_attack_cursor, _attack_hotspot
    if _cached_attack_cursor is None:
        try:
            img = pygame.image.load('assets/AttackCursor.png').convert_alpha()
            # Crop transparent padding before scaling for tighter fit
            bounding = img.get_bounding_rect()
            cropped = img.subsurface(bounding)
            # Scale to 5% of original full image size (matches normal cursor sizing)
            new_w = max(1, int(img.get_width() * 0.05))
            new_h = max(1, int(img.get_height() * 0.05))
            _cached_attack_cursor = pygame.transform.smoothscale(cropped, (new_w, new_h))
            # Sword tip is at ~30% from left, ~8% from top of cropped image
            _attack_hotspot = (int(new_w * 0.30), int(new_h * 0.08))
        except pygame.error:
            return
    mx, my = pygame.mouse.get_pos()
    screen.blit(_cached_attack_cursor, (mx - _attack_hotspot[0], my - _attack_hotspot[1]))


def invalidate_cursor_cache():
    """Call after display mode changes to force reload."""
    global _cached_cursor, _cached_attack_cursor
    _cached_cursor = None
    _cached_attack_cursor = None
