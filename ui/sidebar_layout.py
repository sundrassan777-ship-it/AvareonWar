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


# ============================================================================
# CONTENT AREA (sidebar overhaul)
# ============================================================================
# RightPanel.jpg has a carved pillar down its left edge (~80 of its 871 source px,
# ~23 px at the 250 px panel width) and no art border on the right (the 3 px border
# is drawn by code). Content must be laid out on the visible tapestry, not on the
# full panel width — centring on panel_x + 125 made CANCEL ALL, headers and cards
# look ~10 px left of centre.
ART_INSET_LEFT = 24      # Carved pillar on the panel art's left edge
ART_INSET_RIGHT = 3      # Code-drawn panel border on the right
CONTENT_PAD = 6          # Breathing room between the tapestry edge and content
SCROLLBAR_W = 6          # Scrollbar track width (inside the right padding)

ContentGeometry = namedtuple('ContentGeometry', [
    'x',          # Left edge of the content column
    'right',      # Right edge of the content column (exclusive)
    'width',      # right - x
    'center_x',   # Centre of the visible tapestry (use for centred headers/buttons)
    'top',        # First y available for content (below the tab's header)
    'bottom',     # Last y available for content (above any pinned footer)
])


def content_geometry(panel_x, top, height, header_h=0, footer_h=0, panel_width=250,
                     scrollbar=False):
    """Content column of a sidebar tab, laid out on the visible tapestry.

    Args:
        panel_x, top, height: Panel position/size (SidebarLayout.panel_x/top/height).
        header_h: Pixels reserved above the content (tab title).
        footer_h: Pixels reserved below the content (a pinned button).
        scrollbar: Reserve room on the right for a scrollbar.
    """
    left = panel_x + ART_INSET_LEFT + CONTENT_PAD
    right = panel_x + panel_width - ART_INSET_RIGHT - CONTENT_PAD
    if scrollbar:
        right -= SCROLLBAR_W + 2
    center_x = panel_x + (ART_INSET_LEFT + panel_width - ART_INSET_RIGHT) // 2
    return ContentGeometry(left, right, right - left, center_x,
                           top + header_h, top + height - footer_h)


# ============================================================================
# SCROLLING (pixel based, one per scrollable tab)
# ============================================================================

class ScrollState:
    """Pixel scroll position of one sidebar list.

    anchor='top'    : offset 0 shows the start of the list (Action Queue, Heroes).
    anchor='bottom' : offset 0 shows the END of the list — the newest entries (Action
                      Log, Chat). Scrolling the wheel up moves back into history.

    The renderer reports the content and viewport heights every frame via
    set_content(); the wheel then scrolls within the limits of the last frame drawn.
    That keeps the limit exact — the old message-count offsets estimated it from
    UIConstants and the UNFILTERED message count, so the log scrolled past its end.
    """

    def __init__(self, anchor='top'):
        self.anchor = anchor
        self.offset = 0          # Pixels scrolled away from the anchor
        self.max_offset = 0      # max(0, content_h - viewport_h) of the last frame
        self.content_h = 0
        self.viewport_h = 0

    def set_content(self, content_h, viewport_h):
        """Record this frame's sizes and clamp the offset into range."""
        self.content_h = max(0, int(content_h))
        self.viewport_h = max(0, int(viewport_h))
        self.max_offset = max(0, self.content_h - self.viewport_h)
        self.offset = max(0, min(self.offset, self.max_offset))

    def scroll(self, delta_px):
        """Move the view. Positive = towards later content (down the list).

        For a bottom-anchored list "down" means towards the newest entries, i.e. a
        smaller offset. Returns True if the offset changed.
        """
        before = self.offset
        step = -delta_px if self.anchor == 'bottom' else delta_px
        self.offset = max(0, min(self.max_offset, self.offset + step))
        return self.offset != before

    def on_content_grew(self, added_px):
        """Content was appended at the end of a bottom-anchored list.

        At offset 0 the view follows the newest entries. When the reader has scrolled
        back into history, shift the offset by the added height so what they are
        reading stays still instead of drifting up by one entry per new message.
        """
        if self.anchor == 'bottom' and self.offset > 0 and added_px > 0:
            self.offset += int(added_px)
            self.max_offset = max(self.max_offset, self.offset)

    def reset(self):
        self.offset = 0

    def view_top(self):
        """Content-space y shown at the top of the viewport."""
        if self.anchor == 'bottom':
            return max(0, self.content_h - self.viewport_h - self.offset)
        return self.offset

    def thumb(self, track_y, track_h, min_h=18):
        """(y, h) of the scrollbar thumb, or None when everything fits."""
        if self.max_offset <= 0 or self.content_h <= 0 or track_h <= 0:
            return None
        h = max(min_h, int(track_h * self.viewport_h / self.content_h))
        frac = self.view_top() / float(self.max_offset)
        return track_y + int((track_h - h) * frac), h


def compute_tab_rects(tab_x, top, height, count, tab_width, pad_top, pad_bottom):
    """Bookmark tab rectangles as (x, y, w, h) tuples, top to bottom.

    Shared by the tab renderer and the panel border (which leaves a gap beside the
    active tab), so both always agree. Tabs are adjacent, equally tall, and fill the
    space between the collapse button (pad_top) and pad_bottom.
    """
    if count <= 0:
        return []
    tab_h = max(1, int((height - pad_top - pad_bottom) / count))
    y = top + pad_top
    return [(tab_x, y + i * tab_h, tab_width, tab_h) for i in range(count)]
