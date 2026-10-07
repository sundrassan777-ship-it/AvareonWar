# -*- coding: utf-8 -*-
"""
Right sidebar geometry — the single source of truth for where the sidebar is.

The sidebar (Technology / Heroes / Action Queue / Action Log / Quests / Chat) can be
expanded or collapsed, with a short slide between the two. Every piece of code that
needs to know whether a point is "over the sidebar" (clicks, right-clicks, hover,
tooltips, mouse wheel, the AI-turn click whitelist) must derive it from this layout
instead of recomputing `WINDOW_WIDTH - 250` on its own — that duplication is how the
old code ended up with hardcoded 250/40 values that ignored the collapsed state.

Geometry (screen pixels):
    expanded  (progress 1.0): panel at [W - SIDEBAR_WIDTH, W), bookmark tabs
                              stick out to its left at panel_x - TAB_WIDTH
    collapsed (progress 0.0): panel fully off-screen (panel_x = W), bookmark tabs
                              flush with the right screen edge at W - TAB_WIDTH
    sliding                 : panel_x moves linearly with the eased progress

Pure functions only (no pygame state), so they are unit-testable.
"""

from collections import namedtuple

SidebarLayout = namedtuple('SidebarLayout', [
    'progress',       # 0.0 collapsed .. 1.0 expanded (eased)
    'panel_x',        # Left edge of the panel body (== window width when collapsed)
    'tab_x',          # Left edge of the bookmark tab column
    'top',            # Top of the sidebar (below the top panel)
    'height',         # Sidebar height (the map area's height)
    'panel_visible',  # True when any part of the panel body is on screen
])


def smoothstep(t):
    """Ease-in-out on [0, 1]. Symmetric: smoothstep(1 - t) == 1 - smoothstep(t)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def sidebar_progress(expanded, anim_start_ms, now_ms, duration_ms):
    """Eased expansion progress (0.0 collapsed .. 1.0 expanded).

    Args:
        expanded: Target state (game_state.sidebar_expanded).
        anim_start_ms: Tick when the current slide started, or None (no slide).
        now_ms: Current tick.
        duration_ms: Slide duration.
    """
    target = 1.0 if expanded else 0.0
    if anim_start_ms is None or duration_ms <= 0:
        return target
    t = (now_ms - anim_start_ms) / float(duration_ms)
    if t >= 1.0:
        return target
    eased = smoothstep(t)
    return eased if expanded else 1.0 - eased


def reverse_anim_start(anim_start_ms, now_ms, duration_ms):
    """Start tick for a slide reversed mid-way, so the panel doesn't jump.

    With linear time t into the current slide, the reversed slide resumes at
    t' = 1 - t. Because smoothstep is symmetric, the eased position is identical
    at the moment of reversal. A finished (or absent) slide starts fresh.
    """
    if anim_start_ms is None or duration_ms <= 0:
        return now_ms
    t = (now_ms - anim_start_ms) / float(duration_ms)
    if t >= 1.0 or t < 0.0:
        return now_ms
    return now_ms - (1.0 - t) * duration_ms


def compute_sidebar_layout(window_w, top, height, progress, sidebar_width, tab_width):
    """Sidebar rectangles for a given eased progress."""
    progress = max(0.0, min(1.0, progress))
    panel_x = window_w - int(round(sidebar_width * progress))
    return SidebarLayout(
        progress=progress,
        panel_x=panel_x,
        tab_x=panel_x - tab_width,
        top=top,
        height=height,
        panel_visible=panel_x < window_w,
    )
