# -*- coding: utf-8 -*-
"""
Sidebar overhaul — shared widget kit (rendering/sidebar_widgets.py), the pure layout
helpers (ui/sidebar_layout.py: content_geometry, ScrollState, compute_tab_rects) and
the new bookmarks (fitted labels, hover / flash / active states, panel border gap).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture
def game(pygame_display):
    from main import Game
    g = Game()
    g.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 1],
    })
    g.game_state.phase = 'playing'
    g.apply_display_settings(1600, 900, False)
    g.tutorial_mission = None
    return g


def _brightness(game, rect):
    import pygame
    return sum(pygame.transform.average_color(game.screen, rect)[:3])


# ============================================================================
# PURE LAYOUT
# ============================================================================

class TestContentGeometry:

    def test_centre_is_on_the_visible_tapestry(self):
        """The art's carved pillar (~24 px) makes the tapestry centre panel_x + 135."""
        from ui.sidebar_layout import content_geometry
        geo = content_geometry(1350, 40, 649)
        assert geo.center_x == 1350 + 135
        assert geo.x > 1350 + 24
        assert geo.right < 1600

    def test_header_footer_and_scrollbar_reserve_space(self):
        from ui.sidebar_layout import content_geometry
        plain = content_geometry(0, 40, 600)
        geo = content_geometry(0, 40, 600, header_h=50, footer_h=60, scrollbar=True)
        assert geo.top == 90 and geo.bottom == 580
        assert geo.right < plain.right


class TestScrollState:

    def test_clamps_to_content(self):
        from ui.sidebar_layout import ScrollState
        s = ScrollState('top')
        s.set_content(1000, 400)
        assert s.max_offset == 600
        s.scroll(10_000)
        assert s.offset == 600
        s.scroll(-10_000)
        assert s.offset == 0
        s.set_content(300, 400)          # content shrank below the viewport
        assert s.offset == 0 and s.max_offset == 0

    def test_bottom_anchor_shows_newest_and_scrolls_up_into_history(self):
        from ui.sidebar_layout import ScrollState
        s = ScrollState('bottom')
        s.set_content(1000, 400)
        assert s.view_top() == 600       # offset 0 = the newest content
        s.scroll(-100)                   # wheel up = back in history
        assert s.offset == 100 and s.view_top() == 500

    def test_reading_position_holds_when_content_grows(self):
        from ui.sidebar_layout import ScrollState
        s = ScrollState('bottom')
        s.set_content(1000, 400)
        s.scroll(-200)
        top_before = s.view_top()
        s.on_content_grew(50)
        s.set_content(1050, 400)
        assert s.view_top() == top_before

    def test_follows_newest_at_offset_zero(self):
        from ui.sidebar_layout import ScrollState
        s = ScrollState('bottom')
        s.set_content(1000, 400)
        s.on_content_grew(50)
        s.set_content(1050, 400)
        assert s.offset == 0 and s.view_top() == 650

    def test_thumb(self):
        from ui.sidebar_layout import ScrollState
        s = ScrollState('top')
        s.set_content(300, 400)
        assert s.thumb(0, 400) is None   # everything fits
        s.set_content(1600, 400)
        y, h = s.thumb(0, 400)
        assert y == 0 and h == 100
        s.scroll(10_000)
        y, h = s.thumb(0, 400)
        assert y + h == 400


class TestTabRects:

    def test_adjacent_and_equal(self):
        from ui.sidebar_layout import compute_tab_rects
        rects = compute_tab_rects(1310, 40, 649, 6, 40, 45, 12)
        assert len(rects) == 6
        heights = {r[3] for r in rects}
        assert len(heights) == 1
        for a, b in zip(rects, rects[1:]):
            assert a[1] + a[3] == b[1]
        assert rects[0][1] == 40 + 45
        assert rects[-1][1] + rects[-1][3] <= 40 + 649 - 12


# ============================================================================
# WIDGET KIT
# ============================================================================

class TestWidgets:

    def test_nine_slice_size_cache_and_fill(self, game):
        """Middle is our fill (ResourceSlot's own middle is opaque black)."""
        w = game.sidebar_widgets
        fill = (40, 90, 160)
        a = w.nine_slice('wood', (200, 90), 10, fill)
        assert a.get_size() == (200, 90)
        assert w.nine_slice('wood', (200, 90), 10, fill) is a     # cached
        assert tuple(a.get_at((100, 45)))[:3] == fill
        # Border keeps its thickness: the frame edge is not the fill colour
        assert tuple(a.get_at((3, 45)))[:3] != fill

    def test_bronze_frame_has_transparent_middle_without_fill(self, game):
        surf = game.sidebar_widgets.nine_slice('bronze', (200, 160), 12, None)
        assert surf.get_at((100, 80)).a == 0

    def test_card_states_are_baked_and_ordered(self, game):
        import pygame
        w = game.sidebar_widgets
        args = ('wood', (180, 80), 9, (60, 60, 60))
        mean = lambda s: sum(pygame.transform.average_color(s)[:3])
        normal, hover, flash, locked = (w.card(*args, state=st) for st in ('normal', 'hover', 'flash', 'locked'))
        assert mean(locked) < mean(normal) < mean(hover) < mean(flash)
        assert w.card(*args, state='hover') is hover

    def test_button_sprite_tint(self, game):
        import pygame
        w = game.sidebar_widgets
        plain = w.button_sprite('campaign', (190, 38))
        red = w.button_sprite('campaign', (190, 38), tint=(255, 110, 100))
        r, g, b = pygame.transform.average_color(red)[:3]
        r0, g0, b0 = pygame.transform.average_color(plain)[:3]
        assert r >= g and (g < g0)

    def test_fonts_are_capped_and_independent(self, game):
        w = game.sidebar_widgets
        game.ui_scale = 1.6
        try:
            assert w.scale == pytest.approx(1.15)
        finally:
            game.ui_scale = 1.0
        # Sidebar italic is its own object, not the shared small_font
        assert w.font('italic') is not game.small_font
        assert w.font('italic').get_italic() and not w.font('body').get_italic()

    def test_wrap_and_fit_by_pixels(self, game):
        w = game.sidebar_widgets
        lines = w.wrap("The quick brown fox jumps over the lazy dog of Lobardia", 'body', 90)
        assert len(lines) > 1
        assert all(w.font('body').size(line)[0] <= 90 for line in lines)
        short = w.fit_text("Great South Heilonic Fields", 'body', 80)
        assert short.endswith('…') and w.font('body').size(short)[0] <= 80

    @pytest.mark.parametrize('tab_h', [68, 93, 167])
    def test_common_label_size_fits_every_tab(self, game, tab_h):
        """'Action Queue' used to touch its borders (89 px in a 93 px tab)."""
        w = game.sidebar_widgets
        labels = ['Technology', 'Heroes', 'Action Queue', 'Action Log', 'Quests', 'Chat']
        max_len, max_thick = w.tab_label_space(40, tab_h)
        px = w.common_label_px(labels, max_len, max_thick)
        font = w.font('body', px)
        if px > 8:
            assert all(font.size(label)[0] <= max_len for label in labels)
        # Padding at both ends of the tab
        assert max_len <= tab_h - 16


# ============================================================================
# BOOKMARKS IN THE GAME
# ============================================================================

class TestBookmarks:

    def test_labels_have_padding_at_1600x900(self, game):
        game.draw_order_sidebar()
        w = game.sidebar_widgets
        rect = game.sidebar_tab_buttons['action_queue']
        max_len, _ = w.tab_label_space(rect.w, rect.h)
        px = w.common_label_px(['Technology', 'Heroes', 'Action Queue', 'Action Log', 'Quests', 'Chat'],
                               *w.tab_label_space(rect.w, rect.h))
        assert w.font('body', px).size('Action Queue')[0] <= max_len

    def test_active_tab_is_brighter_than_inactive(self, game):
        game.game_state.active_sidebar_tab = 'technology'
        game.mouse_pos = (0, 0)
        game.draw_order_sidebar()
        tabs = game.sidebar_tab_buttons
        assert _brightness(game, tabs['technology']) > _brightness(game, tabs['quests']) * 1.4

    def test_hover_highlights_a_tab(self, game):
        game.game_state.active_sidebar_tab = 'technology'
        game.mouse_pos = (0, 0)
        game.draw_order_sidebar()
        resting = _brightness(game, game.sidebar_tab_buttons['quests'])
        game.mouse_pos = game.sidebar_tab_buttons['quests'].center
        game.draw_order_sidebar()
        assert _brightness(game, game.sidebar_tab_buttons['quests']) > resting * 1.2

    def test_click_flashes_the_tab(self, game):
        game.draw_order_sidebar()
        heroes = game.sidebar_tab_buttons['heroes']
        game.mouse.handle_left_click(heroes.center)
        assert game.clicked_element == ('sidebar_tab', 'heroes')
        assert game.game_state.active_sidebar_tab == 'heroes'

    def test_panel_border_opens_beside_the_active_tab(self, game):
        game.game_state.active_sidebar_tab = 'action_log'
        game.draw_order_sidebar()
        lay = game.get_sidebar_layout()
        active = game.sidebar_tab_buttons['action_log']
        other = game.sidebar_tab_buttons['technology']
        bronze = (138, 98, 50)
        assert tuple(game.screen.get_at((lay.panel_x + 1, other.centery)))[:3] == bronze
        assert tuple(game.screen.get_at((lay.panel_x + 1, active.centery)))[:3] != bronze

    @pytest.mark.parametrize('style', ['ribbon', 'plaque'])
    def test_every_style_draws(self, game, style, monkeypatch):
        from ui.scaler import UIConstants
        monkeypatch.setattr(UIConstants, 'SIDEBAR_TAB_STYLE', style)
        game.draw_order_sidebar()
        assert len(game.sidebar_tab_buttons) == 6

    def test_tab_sprites_are_cached(self, game):
        game.mouse_pos = (0, 0)
        game.draw_order_sidebar()
        before = len(game.sidebar_widgets._sprites)
        game.draw_order_sidebar()
        assert len(game.sidebar_widgets._sprites) == before
