# -*- coding: utf-8 -*-
"""
P8 — italic text only where intended.

Game.small_font_italic used to be FontManager.get_font(12 * ui_scale) with
set_italic(True). get_font() returns one cached object per (size, weight), so that
made EVERY regular 12 px text italic (and the 16 px lore font every 16 px text): the
top bar, the bottom panels, tooltips, the options menu, the battle screen and, at
1280x720, even the normal-size font. Italic fonts are now separate objects
(FontManager.get_italic_font).
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


def _shared_italic(fm):
    """Shared (size, weight) cache entries that are italic - must always be empty."""
    return sorted(key for key, font in fm.font_cache.items() if len(key) == 2 and font.get_italic())


class TestFontManager:

    def test_italic_font_is_a_separate_cached_object(self, pygame_display):
        from config.font_manager import FontManager
        fm = FontManager()
        fm.load_fonts(os.getcwd())
        regular = fm.get_font(12)
        italic = fm.get_italic_font(12)
        assert italic is not regular
        assert italic.get_italic() and not regular.get_italic()
        assert fm.get_italic_font(12) is italic          # cached
        assert fm.get_font(12) is regular                 # shared entry untouched

    def test_italic_before_regular_still_leaves_regular_upright(self, pygame_display):
        from config.font_manager import FontManager
        fm = FontManager()
        fm.load_fonts(os.getcwd())
        italic = fm.get_italic_font(14)
        assert not fm.get_font(14).get_italic() and italic.get_italic()

    def test_cache_info_handles_italic_keys(self, pygame_display):
        from config.font_manager import FontManager
        fm = FontManager()
        fm.load_fonts(os.getcwd())
        fm.get_font(12)
        fm.get_italic_font(12)
        info = fm.get_cache_info()
        assert info['num_fonts'] == 2 and info['sizes'] == [12]


class TestGameFonts:

    @pytest.mark.parametrize('size', [(1600, 900), (1280, 720), (1920, 1080)])
    def test_only_the_italic_fonts_are_italic(self, pygame_display, size):
        from main import Game
        g = Game()
        g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
        g.apply_display_settings(*size, False)
        for name in ('font', 'small_font', 'large_font', 'small_font_bold', 'font_bold', 'extra_small_font'):
            assert not getattr(g, name).get_italic(), name
        assert g.small_font_italic.get_italic() and g.lore_font_italic.get_italic()
        assert g.small_font_italic is not g.small_font
        assert _shared_italic(g.font_manager) == []

    def test_resolution_changes_leave_no_italic_behind(self, pygame_display):
        """Switching resolution used to leave the old sizes italic as well."""
        from main import Game
        g = Game()
        g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
        for size in ((1600, 900), (1280, 720), (1920, 1080), (1600, 900)):
            g.apply_display_settings(*size, False)
        assert _shared_italic(g.font_manager) == []
        assert not g.font.get_italic() and not g.small_font.get_italic()

    def test_no_active_quests_stays_italic(self, pygame_display, monkeypatch):
        """Owner's choice in the P8 audit: only this placeholder keeps its italics."""
        from main import Game
        g = Game()
        g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
        g.apply_display_settings(1600, 900, False)
        g.game_state.phase = 'playing'
        g.tutorial_mission = None
        g.game_state.tutorial_mission = None
        g.game_state.active_sidebar_tab = 'quests'
        fonts = {}
        real = g.ui_renderer.get_cached_text
        monkeypatch.setattr(g.ui_renderer, 'get_cached_text',
                            lambda text, font, *a, **k: fonts.setdefault(text, font) and real(text, font, *a, **k))
        g.draw_order_sidebar()
        assert fonts["No active quests"].get_italic()
