# -*- coding: utf-8 -*-
"""
Game setup screens — the shared Additional Options window
(ui/additional_options_overlay.py) used by the Custom Game setup (integrated_setup.py)
and the multiplayer lobby (network/territory_selector.py):

- the window is modal: Custom Game territories under it no longer light up
- title, separators, rows and buttons sit inside the carved frame at every resolution
- Confirm applies the edited copy, Cancel / Escape discard it
- multiplayer clients get a read-only view (only Close works)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GOLD_OPTIONS = ["Disabled", "Enabled (25%)", "Enabled (50%)", "Enabled (75%)", "Enabled (100%)"]
RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _overlay(scale=1.0, read_only=False, **values):
    from ui.additional_options_overlay import AdditionalOptionsOverlay
    overlay = AdditionalOptionsOverlay(scale, GOLD_OPTIONS)
    start = {'neutral_armies': False, 'randomize_bonuses': False, 'gold_transfer': 0}
    start.update(values)
    overlay.open(start, read_only=read_only)
    return overlay


class _StubConnection:
    """Enough of NetworkServer / NetworkClient for TerritorySelector to build and sync."""

    def __init__(self):
        from network.protocol import NetworkProtocol
        self.protocol = NetworkProtocol()
        self.sent = []

    def send_message(self, message):
        self.sent.append(message)

    def broadcast_message(self, message):
        self.sent.append(message)


# ---------------------------------------------------------------- layout


@pytest.mark.parametrize("size", RESOLUTIONS)
def test_everything_sits_inside_the_frame(pygame_display, size):
    """Title, both rules, every control and the buttons stay inside the inner edge."""
    overlay = _overlay(scale=int(size[0] * 0.35) / 560)
    lay = overlay.layout(size)
    inner = lay['inner']
    assert inner.collidepoint(lay['content'].topleft)
    assert lay['title_top'] > inner.top
    assert inner.top < lay['sep1_y'] < lay['sep2_y'] < inner.bottom
    for row in lay['rows']:
        assert inner.contains(row['control_rect']), row['key']
        assert inner.contains(row['label_rect']), row['key']
        assert lay['sep1_y'] < row['control_rect'].top and row['control_rect'].bottom < lay['sep2_y']
    for key in ('cancel', 'confirm', 'close'):
        assert inner.contains(lay[key]), key
        assert lay[key].top > lay['sep2_y']
    assert not lay['cancel'].colliderect(lay['confirm'])
    # Fits on screen (sized to its rows, no scrolling)
    assert pygame_display.Rect((0, 0), size).contains(lay['panel'])


def test_draw_runs_in_both_modes(pygame_display):
    screen = pygame_display.display.get_surface()
    for read_only in (False, True):
        overlay = _overlay(read_only=read_only, neutral_armies=True)
        overlay.dropdown_open = not read_only
        overlay.draw(screen)


# ---------------------------------------------------------------- input


def test_confirm_returns_edited_copy(pygame_display):
    size = (1600, 900)
    overlay = _overlay()
    rects = overlay.layout(size)
    neutral = rects['rows'][0]['control_rect']
    assert overlay.handle_click(neutral.center, size) is None
    assert overlay.values['neutral_armies'] is True

    # Gold transfer: open the list, pick 75%
    gold = rects['rows'][2]['control_rect']
    overlay.handle_click(gold.center, size)
    assert overlay.dropdown_open
    item = overlay.rects['gold_transfer_item_3']
    overlay.handle_click(item.center, size)
    assert overlay.values['gold_transfer'] == 3 and not overlay.dropdown_open

    assert overlay.handle_click(rects['confirm'].center, size) == 'confirm'
    assert not overlay.is_open


def test_escape_closes_list_then_window(pygame_display):
    import pygame
    overlay = _overlay()
    overlay.dropdown_open = True
    esc = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    assert overlay.handle_key(esc) is None and overlay.is_open and not overlay.dropdown_open
    assert overlay.handle_key(esc) == 'cancel' and not overlay.is_open


def test_read_only_only_close_works(pygame_display):
    size = (1600, 900)
    overlay = _overlay(read_only=True)
    lay = overlay.layout(size)
    for row in lay['rows']:
        overlay.handle_click(row['control_rect'].center, size)
    assert overlay.values == {'neutral_armies': False, 'randomize_bonuses': False, 'gold_transfer': 0}
    assert not overlay.dropdown_open
    # Cancel / Confirm positions do nothing; Close closes
    overlay.handle_click(lay['confirm'].center, size)
    assert overlay.is_open
    assert overlay.handle_click(lay['close'].center, size) == 'cancel'
    assert not overlay.is_open


# ---------------------------------------------------------------- Custom Game


@pytest.fixture
def custom_setup(pygame_display):
    from integrated_setup import IntegratedSetup
    return IntegratedSetup(pygame_display.display.get_surface())


def _territory_point(setup):
    """A screen point inside some territory of the setup's map preview."""
    import map_data
    preview = setup.map_preview
    for territory, polygon in preview.scaled_polygons.items():
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        for fx in (0.5, 0.4, 0.6):
            point = (int(min(xs) + (max(xs) - min(xs)) * fx), int(min(ys) + (max(ys) - min(ys)) * 0.5))
            if preview._get_territory_at_screen_pos(point) == territory:
                return point
    raise AssertionError("no territory point found")


def test_custom_overlay_blocks_map_hover(custom_setup, monkeypatch):
    """Bug: territories lit up under the Additional Options window."""
    import pygame
    point = _territory_point(custom_setup)
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: point)

    custom_setup.handle_events()
    assert custom_setup.map_preview.hovered_territory is not None

    custom_setup.config_panel.options_overlay.open({'neutral_armies': False, 'randomize_bonuses': False,
                                                    'gold_transfer': 0})
    custom_setup.handle_events()
    assert custom_setup.map_preview.hovered_territory is None


def test_custom_confirm_writes_config(custom_setup):
    panel = custom_setup.config_panel
    size = custom_setup.screen.get_size()
    button = panel.ui_elements['additional_options_button']
    panel.handle_click(button.center)
    assert panel.overlay_open
    lay = panel.options_overlay.layout(size)
    panel.handle_click(lay['rows'][1]['control_rect'].center)   # Randomize bonuses on
    panel.handle_click(lay['confirm'].center)
    assert not panel.overlay_open
    assert custom_setup.config.randomize_bonuses is True
    assert custom_setup.get_config()['randomize_bonuses'] is True


def test_custom_cancel_discards(custom_setup):
    panel = custom_setup.config_panel
    lay = panel.options_overlay.layout(custom_setup.screen.get_size())
    panel.handle_click(panel.ui_elements['additional_options_button'].center)
    panel.handle_click(lay['rows'][0]['control_rect'].center)
    panel.handle_click(lay['cancel'].center)
    assert custom_setup.config.neutral_armies is False


# ---------------------------------------------------------------- Multiplayer lobby


def _selector(pygame_display, is_host):
    from network.territory_selector import TerritorySelector
    return TerritorySelector(pygame_display.display.get_surface(), _StubConnection(), is_host=is_host,
                             local_player_index=0 if is_host else 1)


def test_lobby_host_confirm_applies_and_syncs(pygame_display):
    sel = _selector(pygame_display, is_host=True)
    sel.handle_click(sel.additional_options_rect.center)
    assert sel.overlay_open and not sel.options_overlay.read_only
    lay = sel.options_overlay.layout(sel.screen.get_size())
    sel.handle_click(lay['rows'][0]['control_rect'].center)
    sent_before = len(sel.network_connection.sent)
    sel.handle_click(lay['confirm'].center)
    assert sel.neutral_armies is True
    assert len(sel.network_connection.sent) > sent_before   # SETUP_CONFIG went out


def test_lobby_client_gets_read_only_view(pygame_display):
    sel = _selector(pygame_display, is_host=False)
    sel.handle_click(sel.additional_options_rect.center)
    assert sel.overlay_open and sel.options_overlay.read_only
    lay = sel.options_overlay.layout(sel.screen.get_size())
    sel.handle_click(lay['rows'][0]['control_rect'].center)
    assert sel.neutral_armies is False
    # Host changes arriving while it's open show up on the next frame
    sel.gold_transfer = 2
    sel.render()
    assert sel.options_overlay.values['gold_transfer'] == 2
    sel.handle_click(lay['close'].center)
    assert not sel.overlay_open
