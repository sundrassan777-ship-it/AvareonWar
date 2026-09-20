# -*- coding: utf-8 -*-
# display_utils.py
# Centralized pygame display-mode creation (resolution, fullscreen, VSync)

"""
Display Mode Helper
===================

One place that calls ``pygame.display.set_mode()``, so VSync is applied
consistently everywhere instead of being reintroduced or silently dropped by one
of the ~17 call sites scattered through main.py.

Why this module exists — three behaviours measured on pygame 2.6.1 / SDL 2.28.4
that are easy to get wrong:

1. ``vsync=1`` WITHOUT ``pygame.SCALED`` is silently ignored. set_mode() accepts
   it, raises nothing, and frames are not synchronised (flip ~1.3-1.5ms, i.e.
   hundreds of Hz). Real VSync needs ``pygame.SCALED`` (or OPENGL).

2. VSync is lost by any LATER set_mode() call, even one that passes ``vsync=1``
   and ``SCALED`` again:

       initial SCALED+vsync      flip = 5.99ms   (165Hz, synced)
       after resize (no reinit)  flip = 0.95ms   (vsync gone)
       vsync=1 again (no reinit) flip = 1.26ms   (still gone)

   Only ``pygame.display.quit()`` + ``pygame.display.init()`` before set_mode
   restores it. Since apply_display_settings() *is* the resolution path, without
   this VSync would die the first time a player changed resolution and never
   come back.

3. The achieved VSync state CANNOT be read back: ``Surface.get_flags()`` does not
   report the SCALED bit (it returns only FULLSCREEN). So callers must trust the
   ``vsync_active`` value returned here rather than inspecting the surface.

Also note (see set_display_mode): always pass the game's LOGICAL resolution.
Under plain FULLSCREEN, Windows DPI scaling means a request for 1920x1080 comes
back as 1536x864; under SCALED the request is honoured exactly, which would
silently raise the render resolution (and lower FPS) if callers passed a
physical size instead.
"""

import logging

import pygame

logger = logging.getLogger(__name__)


def _base_flags(fullscreen):
    return pygame.FULLSCREEN if fullscreen else 0


def _reinit_display():
    """Tear down and re-create the display subsystem so SCALED/vsync can take effect."""
    try:
        pygame.display.quit()
    except pygame.error:
        pass
    pygame.display.init()


def set_display_mode(size, fullscreen, vsync, force_reinit=False):
    """
    Create the display surface, applying VSync when requested.

    Args:
        size: (width, height) LOGICAL resolution. Never pass a physical/native size
            when vsync is on — SCALED honours this exactly and SDL upscales for free.
        fullscreen: Whether to use pygame.FULLSCREEN.
        vsync: Whether to request VSync (adds pygame.SCALED and vsync=1).
        force_reinit: Re-initialise the display subsystem even if vsync is off.
            Used when switching vsync OFF, so the SCALED renderer is torn down.

    Returns:
        (surface, vsync_active) — vsync_active reports what was actually achieved,
        which may be False if the driver refused SCALED/vsync.
    """
    flags = _base_flags(fullscreen)

    if vsync:
        # A fresh display is required; see note 2 in the module docstring.
        _reinit_display()
        try:
            surface = pygame.display.set_mode(size, flags | pygame.SCALED, vsync=1)
            logger.info(f"Display: {size[0]}x{size[1]} "
                        f"{'fullscreen' if fullscreen else 'windowed'} SCALED vsync=ON")
            return surface, True
        except pygame.error as exc:
            # Some drivers cannot create the SCALED renderer. Never fail to launch:
            # fall back to the historical behaviour (no SCALED, no vsync).
            logger.warning(f"VSync unavailable ({exc}); falling back to no vsync")
            _reinit_display()
    elif force_reinit:
        # Leaving vsync: drop the SCALED renderer, otherwise it can persist.
        _reinit_display()

    surface = pygame.display.set_mode(size, flags)
    logger.info(f"Display: {size[0]}x{size[1]} "
                f"{'fullscreen' if fullscreen else 'windowed'} vsync=OFF")
    return surface, False


def menu_frame_cap(default_fps=60):
    """
    Frame cap for the non-gameplay screens (menu, setup, cutscene, recap, browsers).

    These each own their own Clock and historically hard-coded 60. They now honour
    the user's FPS limit so the setting is consistent across the whole app. VSync
    needs no handling here: it is a property of the display surface, so it already
    paces these screens whenever it is on.

    Returns the cap to pass to Clock.tick(); never 0 (see resolve_frame_cap).
    """
    try:
        from settings_manager import settings
        limit = settings.get('fps_limit', 0)
    except Exception:
        return default_fps
    if limit and limit > 0:
        return limit
    return default_fps


def resolve_frame_cap(fps_limit, vsync_active, focused, focused_fps, unfocused_fps,
                      vsync_safety_cap=240):
    """
    Decide the argument for ``Clock.tick()`` this frame.

    NOTE: never returns 0 / no cap. ``Clock.get_time()`` returns INTEGER
    milliseconds, so in a fully uncapped loop it reports 0 for essentially every
    frame — measured: 100% of frames with ``delta_time == 0.0``, and summed delta
    running at 250% of real time. A high safety cap keeps frame timing meaningful
    even when vsync is pacing the frames.

    Args:
        fps_limit: User's manual cap, 0 for none.
        vsync_active: Whether VSync is actually pacing frames.
        focused: Whether the window has focus.
        focused_fps: Default cap when focused (config.constants.FPS).
        unfocused_fps: Cap when unfocused (config.constants.UNFOCUSED_FPS).
        vsync_safety_cap: Upper bound applied when vsync paces frames.

    Returns:
        int: frames-per-second cap to pass to Clock.tick().
    """
    if not focused:
        return unfocused_fps
    if fps_limit and fps_limit > 0:
        return fps_limit
    if vsync_active:
        return vsync_safety_cap
    return focused_fps
