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
        self.incoming = []          # Messages _process_network_messages() will read
        self.message_queue = self   # TerritorySelector reads connection.message_queue

    def get_incoming_message(self):
        return self.incoming.pop(0) if self.incoming else None

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
    # The (i) mark after each option name never touches that option's control
    for row in lay['rows']:
        assert row['mark_rect'].right < row['control_rect'].left, row['key']
        assert inner.contains(row['mark_rect']), row['key']
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
    assert overlay.values == {'neutral_armies': False, 'randomize_bonuses': False, 'gold_transfer': 0,
                              'starting_gold': 100}
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


# ---------------------------------------------------------------- Starting Gold


def _type(overlay, text):
    import pygame
    for ch in text:
        key = pygame.K_BACKSPACE if ch == '\b' else (pygame.K_RETURN if ch == '\n' else ord(ch))
        overlay.handle_key(pygame.event.Event(pygame.KEYDOWN, key=key, unicode='' if ch in '\b\n' else ch))


def _focus_gold(overlay, size=(1600, 900)):
    field = overlay.layout(size)['rows'][3]['control_rect']
    overlay.handle_click(field.center, size)
    assert overlay.text_focus


@pytest.mark.parametrize("typed, expected", [
    ("\b\b\b250\n", 250),
    ("\b\b\b99999\n", 10000),       # clamped to the maximum
    ("\b\b\b0\n", 0),
    ("\b\b\b\n", 100),              # empty -> default
    ("\b\b\b0050\n", 50),           # leading zeros dropped
    ("\b\b\b12a3\n", 123),          # letters ignored
    ("\b\b\b123456\n", 10000),      # max five significant digits, then clamped
])
def test_gold_field_typing(pygame_display, typed, expected):
    overlay = _overlay()
    _focus_gold(overlay)
    _type(overlay, typed)
    assert not overlay.text_focus
    assert overlay.values['starting_gold'] == expected
    assert overlay.gold_text == str(expected)   # the field shows what will be used


def test_gold_field_escape_restores_and_keeps_window(pygame_display):
    import pygame
    overlay = _overlay(starting_gold=300)
    _focus_gold(overlay)
    _type(overlay, "\b\b\b7")
    overlay.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=''))
    assert overlay.is_open and not overlay.text_focus
    assert overlay.values['starting_gold'] == 300 and overlay.gold_text == '300'


def test_gold_confirm_commits_unfinished_typing(pygame_display):
    size = (1600, 900)
    overlay = _overlay()
    _focus_gold(overlay, size)
    _type(overlay, "\b\b\b4000")
    assert overlay.handle_click(overlay.layout(size)['confirm'].center, size) == 'confirm'
    assert overlay.values['starting_gold'] == 4000


def test_gold_read_only_cannot_focus(pygame_display):
    size = (1600, 900)
    overlay = _overlay(read_only=True, starting_gold=900)
    overlay.handle_click(overlay.layout(size)['rows'][3]['control_rect'].center, size)
    assert not overlay.text_focus
    _type(overlay, "5")
    assert overlay.values['starting_gold'] == 900


def test_clamp_starting_gold():
    from config.constants import clamp_starting_gold
    assert clamp_starting_gold(None) == 100
    assert clamp_starting_gold("abc") == 100
    assert clamp_starting_gold(-5) == 0
    assert clamp_starting_gold("20000") == 10000
    assert clamp_starting_gold(750) == 750


def test_custom_get_config_carries_starting_gold(custom_setup):
    panel = custom_setup.config_panel
    size = custom_setup.screen.get_size()
    assert custom_setup.get_config()['starting_gold'] == 100
    panel.handle_click(panel.ui_elements['additional_options_button'].center)
    _focus_gold(panel.options_overlay, size)
    _type(panel.options_overlay, "\b\b\b1500")
    panel.handle_click(panel.options_overlay.layout(size)['confirm'].center)
    assert custom_setup.get_config()['starting_gold'] == 1500


def test_custom_keys_reach_the_window(custom_setup):
    """The setup's event loop routes typing into the field (not only Escape)."""
    import pygame
    panel = custom_setup.config_panel
    panel.handle_click(panel.ui_elements['additional_options_button'].center)
    _focus_gold(panel.options_overlay, custom_setup.screen.get_size())
    pygame.event.clear()
    for key, ch in ((pygame.K_BACKSPACE, ''), (pygame.K_BACKSPACE, ''), (pygame.K_BACKSPACE, ''), (ord('8'), '8')):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=ch))
    custom_setup.handle_events()
    assert panel.options_overlay.gold_text == '8'
    assert not custom_setup.cancelled


def test_lobby_settings_round_trip():
    from network.lobby import LobbyState
    host = LobbyState(host_name="Host")
    host.starting_gold = 2500
    client = LobbyState(host_name="Host")
    client.update_from_network(host.serialize())
    assert client.starting_gold == 2500
    client.set_settings({'starting_gold': 999999})
    assert client.starting_gold == 10000


def test_lobby_host_confirm_updates_lobby_state(pygame_display):
    """A later LOBBY_STATE broadcast must carry the confirmed values."""
    sel = _selector(pygame_display, is_host=True)
    size = sel.screen.get_size()
    sel.handle_click(sel.additional_options_rect.center)
    _focus_gold(sel.options_overlay, size)
    _type(sel.options_overlay, "\b\b\b600")
    sel.handle_click(sel.options_overlay.layout(size)['confirm'].center)
    assert sel.starting_gold == 600
    assert sel.lobby_state.get_settings()['starting_gold'] == 600


def test_lobby_client_receives_setup_config(pygame_display):
    """Host SETUP_CONFIG -> client screen + lobby_state (clamped)."""
    from network_config import MessageType
    sel = _selector(pygame_display, is_host=False)
    sel.network_connection.incoming = [
        {'type': MessageType.SETUP_CONFIG, 'data': {'starting_gold': 3000, 'map_id': sel.selected_map}},
    ]
    sel._process_network_messages()
    assert sel.starting_gold == 3000 and sel.lobby_state.starting_gold == 3000

    sel.network_connection.incoming = [
        {'type': MessageType.SETUP_CONFIG, 'data': {'starting_gold': 50000, 'map_id': sel.selected_map}},
    ]
    sel._process_network_messages()
    assert sel.starting_gold == 10000


def test_build_config_from_lobby_reads_starting_gold():
    from network.lobby import LobbyState, SLOT_AI
    from network.multiplayer_setup import MultiplayerSetup
    lobby = LobbyState(host_name="Host")
    lobby.starting_gold = 1234
    lobby.slots[0].territory = 'A'
    lobby.slots[1].state = SLOT_AI
    lobby.slots[1].territory = 'B'
    setup = MultiplayerSetup.__new__(MultiplayerSetup)
    setup.victory_options = ["Domination (45+)", "Capital Assault", "Total Conquest"]
    config = setup._build_config_from_lobby(lobby, 0, 0, 0)
    assert config['starting_gold'] == 1234


def test_initialize_game_applies_starting_gold(pygame_display):
    from main import Game
    game = Game()
    game.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 1],
        'starting_gold': 2750,
    })
    assert game.game_state.starting_gold == 2750
    assert game.game_state.player_gold == [2750, 2750]

    game.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
    assert game.game_state.player_gold == [100, 100]   # campaigns / old configs keep the default


# ---------------------------------------------------------------- Label tooltips


def test_every_tooltip_renders(pygame_display):
    from config.setup_tooltips import SETUP_TOOLTIPS
    from ui.setup_tooltip import SetupTooltips
    tips = SetupTooltips(1.0)
    screen = pygame_display.display.get_surface()
    for key in SETUP_TOOLTIPS:
        rect = tips.draw(screen, key, (1590, 890))   # bottom-right corner: must flip
        assert screen.get_rect().contains(rect), key
    assert tips.box('no_such_key') is None


def test_every_overlay_row_has_a_tooltip():
    from config.setup_tooltips import SETUP_TOOLTIPS
    from ui.additional_options_overlay import ROWS
    for key, _, _ in ROWS:
        assert key in SETUP_TOOLTIPS, key


def test_custom_label_hover_shows_tooltip(custom_setup):
    panel = custom_setup.config_panel
    custom_setup.render()                       # draws the labels -> hover rects
    assert set(panel.tooltip_rects) == {'taxation', 'victory', 'turn_mode'}
    for key, rect in panel.tooltip_rects.items():
        panel.update_hover(rect.center)
        assert panel.hovered_tooltip == key
    # Not while a dropdown list is open (it can cover the labels)
    panel.active_dropdown = 'taxation'
    panel.update_hover(panel.tooltip_rects['turn_mode'].center)
    assert panel.hovered_tooltip is None


def test_turn_mode_hint_under_dropdown_is_gone(custom_setup):
    """The old one-line hint under the Turn Mode dropdown was replaced by the tooltip."""
    assert not hasattr(custom_setup.config, 'turn_mode_tooltips')


def test_lobby_label_hover_shows_tooltip(pygame_display):
    sel = _selector(pygame_display, is_host=False)
    sel.render()
    assert set(sel.tooltip_rects) == {'taxation', 'victory', 'turn_mode'}
    for key, rect in sel.tooltip_rects.items():
        sel.handle_hover(rect.center)
        assert sel.hovered_tooltip == key
    sel.render()


def test_overlay_name_hover_shows_tooltip(pygame_display):
    size = (1600, 900)
    overlay = _overlay(read_only=True)          # clients get the explanations too
    for row in overlay.layout(size)['rows']:
        overlay.update_hover(row['mark_rect'].center, size)
        assert overlay.hovered_tip == row['key']
    overlay.update_hover((0, 0), size)
    assert overlay.hovered_tip is None
