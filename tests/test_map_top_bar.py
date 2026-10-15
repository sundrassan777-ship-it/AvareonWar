# -*- coding: utf-8 -*-
"""
Map top bar of the setup screens (ui/map_top_bar.py), shared by the Custom Game setup
(integrated_setup.py) and the multiplayer lobby (network/territory_selector.py):

- layout at 720p-1440p: every control inside the wood strip above the map and inside the
  map panel, no overlaps, labels inside their wood frames, the longest map name inside
  the TextBar's dark window; the short Randomize label only when the full one cannot fit
- feedback: every usable control is brighter on hover and brighter still on its click
  flash; a client's greyed Randomize and map name do not react; Show Borders glows on
- clicks: Randomize fills every active slot (lobby host: one LOBBY_STATE that reaches
  the clients), the arrows / name change the map, Show Borders toggles and is saved;
  one click sound each; a client's Randomize does nothing at all
- modal windows (Additional Options, friend picker) clear the bar's hover
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]
CONTROLS = ('randomize', 'prev', 'name', 'next', 'borders')


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    # Fresh display (an earlier module may leave a fullscreen 1024x768 one behind)
    pygame.display.quit()
    pygame.display.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    import map_data
    map_data.load_map('avareon')
    pygame.quit()


@pytest.fixture
def clicks(monkeypatch):
    """Counts UI click sounds; keeps Show Borders' saved setting untouched."""
    from global_sound import sound_manager
    from settings_manager import settings
    calls = []
    monkeypatch.setattr(sound_manager, 'play_ui_click', lambda *a, **k: calls.append(1))
    saved = []
    monkeypatch.setattr(settings, 'save', lambda *a, **k: saved.append(1))
    before = settings.get('show_setup_borders', False)
    yield SimpleCounter(calls, saved)
    settings.set('show_setup_borders', before)


class SimpleCounter:
    def __init__(self, sounds, saves):
        self.sounds = sounds
        self.saves = saves


class _StubConnection:
    """Enough of NetworkServer / NetworkClient for TerritorySelector (see test_setup_options)."""

    def __init__(self):
        from network.protocol import NetworkProtocol
        self.protocol = NetworkProtocol()
        self.sent = []
        self.message_queue = self

    def get_incoming_message(self):
        return None

    def send_message(self, message):
        self.sent.append(message)

    def broadcast_message(self, message):
        self.sent.append(message)

    def sent_types(self):
        return [self.protocol.decode_message(m)['type'] for m in self.sent]


def _custom(pygame_display, size=(1600, 900)):
    import map_data
    from integrated_setup import IntegratedSetup
    map_data.load_map('avareon')
    return IntegratedSetup(pygame_display.Surface(size))


def _lobby(pygame_display, is_host, size=(1600, 900)):
    import map_data
    from network.territory_selector import TerritorySelector
    map_data.load_map('avareon')
    sel = TerritorySelector(pygame_display.Surface(size), _StubConnection(), is_host=is_host,
                            local_player_index=0 if is_host else 1)
    sel.lobby_synced = True
    return sel


def _screens(pygame_display, size):
    """(name, top bar, band height, map panel x, map panel width) for all three views."""
    custom = _custom(pygame_display, size)
    host = _lobby(pygame_display, True, size)
    client = _lobby(pygame_display, False, size)
    mp = custom.map_preview
    return [
        ('custom', mp.map_top_bar, mp.offset_y, mp.bounds.x, mp.bounds.width),
        ('host', host.map_top_bar, host.map_y, host.left_panel_width, host.width - host.left_panel_width),
        ('client', client.map_top_bar, client.map_y, client.left_panel_width,
         client.width - client.left_panel_width),
    ]


def _brightness(surface, rect):
    import pygame
    r, g, b = pygame.transform.average_color(surface, rect)[:3]
    return r + g + b


def _draw(pygame_display, bar, borders_on=False, size=(1600, 900)):
    screen = pygame_display.Surface(size)
    screen.fill((70, 48, 28))   # Wood-ish background
    bar.draw(screen, "Azincournean Highlands", borders_on)
    return screen


# ---------------------------------------------------------------- layout


@pytest.mark.parametrize("size", RESOLUTIONS)
def test_layout_fits_the_strip_at_every_resolution(pygame_display, size):
    import pygame
    from ui.map_top_bar import (FONT_BOLD, FONT_SEMIBOLD, BORDERS_LABEL, MIN_LABEL_PX,
                                RANDOMIZE_LABEL, RANDOMIZE_LABEL_SHORT)
    for name, bar, band, area_x, area_w in _screens(pygame_display, size):
        lay = bar.layout()
        panel = pygame.Rect(area_x, 0, area_w, band)
        shown = [(c, lay[c]) for c in CONTROLS if lay.get(c) is not None]
        assert {c for c, _ in shown} == (set(CONTROLS) if name != 'client'
                                         else {'randomize', 'name', 'borders'}), name
        for control, rect in shown:
            # Inside the wood strip above the map, inside the map panel
            assert panel.contains(rect), (name, size, control, rect, panel)
        for i, (a, ra) in enumerate(shown):
            for b, rb in shown[i + 1:]:
                assert not ra.colliderect(rb), (name, size, a, b)
        # Left to right: Randomize, (<), name, (>), Borders
        xs = [lay[c].x for c in CONTROLS if lay.get(c) is not None]
        assert xs == sorted(xs), (name, size)

        # Labels clear the wood beams; readable size or the short label
        beam = bar.frames.beam(lay['randomize'].h)
        font = pygame.font.Font(FONT_SEMIBOLD, lay['label_px'])
        for control, label in (('randomize', lay['label']), ('borders', BORDERS_LABEL)):
            assert font.size(label)[0] + 2 * beam < lay[control].w, (name, size, control)
        assert lay['label'] in (RANDOMIZE_LABEL, RANDOMIZE_LABEL_SHORT)
        if lay['label'] == RANDOMIZE_LABEL:
            assert lay['label_px'] >= MIN_LABEL_PX

        # Every map name fits the TextBar's dark window
        window = lay['name_window']
        assert lay['name'].contains(window)
        name_font = pygame.font.Font(FONT_BOLD, lay['name_px'])
        for map_name in bar.map_names:
            text = name_font.render(map_name, True, (255, 255, 255))
            assert text.get_width() <= window.w, (name, size, map_name)
            assert text.get_bounding_rect().h <= window.h, (name, size, map_name)


@pytest.mark.parametrize("size", RESOLUTIONS[1:])
def test_full_randomize_label_above_720p(pygame_display, size):
    from ui.map_top_bar import RANDOMIZE_LABEL
    for name, bar, *_ in _screens(pygame_display, size):
        assert bar.layout()['label'] == RANDOMIZE_LABEL, (name, size)


def test_short_label_only_when_the_full_one_cannot_fit(pygame_display):
    from ui.map_top_bar import MapTopBar, MIN_LABEL_PX, RANDOMIZE_LABEL_SHORT
    bar = MapTopBar(0.8)
    bar.set_geometry(0, 700, 48)   # Narrower than any real map panel
    lay = bar.layout()
    assert lay['label'] == RANDOMIZE_LABEL_SHORT
    assert lay['label_px'] >= MIN_LABEL_PX
    assert lay['randomize'].right < lay['prev'].left
    assert lay['next'].right < lay['borders'].left


def test_layout_follows_permissions(pygame_display):
    from ui.map_top_bar import MapTopBar
    bar = MapTopBar(1.0)
    bar.set_geometry(560, 1040, 60)
    with_arrows = bar.layout()
    assert with_arrows['prev'] is not None
    bar.configure(can_change_map=False, randomize_enabled=False)
    without = bar.layout()
    assert without['prev'] is None and without['next'] is None
    # The name bar stays centred on the map panel either way
    assert without['name'].centerx == with_arrows['name'].centerx == 560 + 520


# ---------------------------------------------------------------- feedback


def test_every_usable_control_highlights_and_flashes(pygame_display):
    import pygame
    bar = _lobby(pygame_display, True).map_top_bar
    lay = bar.layout()
    for control in CONTROLS:
        rect = lay[control]
        bar.hovered, bar._flash = None, (None, 0)
        normal = _brightness(_draw(pygame_display, bar), rect)
        bar.hovered = control
        hover = _brightness(_draw(pygame_display, bar), rect)
        bar._flash = (control, pygame.time.get_ticks())
        flash = _brightness(_draw(pygame_display, bar), rect)
        assert normal < hover < flash, (control, normal, hover, flash)


def test_client_controls_it_cannot_use_do_not_react(pygame_display):
    import pygame
    host = _lobby(pygame_display, True).map_top_bar
    client = _lobby(pygame_display, False).map_top_bar
    lay = client.layout()
    for control in ('randomize', 'name'):
        rect = lay[control]
        client.hovered, client._flash = None, (None, 0)
        normal = _brightness(_draw(pygame_display, client), rect)
        client.hovered = control
        client._flash = (control, pygame.time.get_ticks())
        assert _brightness(_draw(pygame_display, client), rect) == normal, control
    # The greyed Randomize is darker than the host's
    host.hovered = client.hovered = None
    assert (_brightness(_draw(pygame_display, client), lay['randomize'])
            < _brightness(_draw(pygame_display, host), host.layout()['randomize']))


def test_show_borders_glows_while_on(pygame_display):
    bar = _lobby(pygame_display, False).map_top_bar
    inner = bar.layout()['borders'].inflate(-12, -12)
    off = _brightness(_draw(pygame_display, bar, borders_on=False), inner)
    on = _brightness(_draw(pygame_display, bar, borders_on=True), inner)
    assert on > off + 150, (off, on)


def test_randomize_tooltips(pygame_display):
    from config.setup_tooltips import SETUP_TOOLTIPS
    host = _lobby(pygame_display, True)
    client = _lobby(pygame_display, False)
    host.handle_hover(host.map_top_bar.layout()['randomize'].center)
    client.handle_hover(client.map_top_bar.layout()['randomize'].center)
    assert host.hovered_tooltip == 'randomize_starts'
    assert client.hovered_tooltip == 'randomize_starts_host_only'
    for key in ('randomize_starts', 'randomize_starts_host_only'):
        assert key in SETUP_TOOLTIPS
        assert host.setup_tooltips.draw(host.screen, key, (600, 20)) is not None
    host.handle_hover(host.map_top_bar.layout()['borders'].center)
    assert host.hovered_tooltip is None


# ---------------------------------------------------------------- Custom Game clicks


def test_custom_randomize_fills_every_active_slot(pygame_display, clicks):
    setup = _custom(pygame_display)
    mp = setup.map_preview
    setup.config.player_slots[2]['active'] = True
    mp.handle_click(mp.map_top_bar.layout()['randomize'].center)
    active = [s for s in setup.config.player_slots if s['active']]
    assert all(s['territory'] for s in active) and len({s['territory'] for s in active}) == 3
    assert setup.config.player_slots[3]['territory'] is None
    assert setup.config.is_ready()
    assert len(clicks.sounds) == 1
    assert mp.map_top_bar.is_flashing('randomize')
    # Pressable again: still a full, valid set
    mp.handle_click(mp.map_top_bar.layout()['randomize'].center)
    assert setup.config.is_ready() and len(clicks.sounds) == 2


def test_custom_arrows_and_name_change_the_map_with_one_sound(pygame_display, clicks):
    import map_data
    setup = _custom(pygame_display)
    mp = setup.map_preview
    maps = map_data.get_map_ids()
    lay = mp.map_top_bar.layout()
    setup.config.player_slots[0]['territory'] = 'Aelatania'
    mp.handle_click(lay['next'].center)
    assert setup.config.selected_map == maps[1]
    assert setup.config.player_slots[0]['territory'] is None
    assert len(clicks.sounds) == 1          # change_map no longer plays a second one
    mp.handle_click(lay['prev'].center)
    assert setup.config.selected_map == maps[0]
    mp.handle_click(lay['name'].center)
    assert setup.config.selected_map == maps[1]
    assert len(clicks.sounds) == 3


def test_custom_show_borders_toggles_and_saves(pygame_display, clicks):
    from settings_manager import settings
    setup = _custom(pygame_display)
    mp = setup.map_preview
    start = mp.show_borders
    mp.handle_click(mp.map_top_bar.layout()['borders'].center)
    assert mp.show_borders is (not start)
    assert settings.get('show_setup_borders') is (not start)
    assert clicks.saves and len(clicks.sounds) == 1


def test_custom_click_on_bare_wood_does_nothing(pygame_display, clicks):
    setup = _custom(pygame_display)
    mp = setup.map_preview
    lay = mp.map_top_bar.layout()
    spot = ((lay['randomize'].right + lay['prev'].left) // 2, lay['randomize'].centery)
    assert mp.map_top_bar.element_at(spot) is None
    assert not mp.handle_click(spot)
    assert clicks.sounds == []


def test_custom_overlay_clears_top_bar_hover(pygame_display, monkeypatch):
    import pygame
    setup = _custom(pygame_display)
    point = setup.map_preview.map_top_bar.layout()['randomize'].center
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: point)
    setup.handle_events()
    assert setup.map_preview.map_top_bar.hovered == 'randomize'
    setup.config_panel.options_overlay.open({'neutral_armies': False, 'randomize_bonuses': False,
                                             'gold_transfer': 0})
    setup.handle_events()
    assert setup.map_preview.map_top_bar.hovered is None


# ---------------------------------------------------------------- lobby clicks


def test_lobby_host_randomize_fills_slots_and_broadcasts(pygame_display, clicks):
    from network_config import MessageType
    sel = _lobby(pygame_display, True)
    sel.lobby_state.set_slot_ai(1)
    sel.lobby_state.set_slot_ai(2)
    sel.network_connection.sent.clear()
    sel.handle_click(sel.map_top_bar.layout()['randomize'].center)
    picks = [sel.lobby_state.slots[i].territory for i in (0, 1, 2)]
    assert all(picks) and len(set(picks)) == 3
    assert sel.player_selections[:3] == picks
    assert sel.network_connection.sent_types() == [MessageType.LOBBY_STATE]
    assert len(clicks.sounds) == 1


def test_lobby_host_arrow_changes_map(pygame_display, clicks):
    import map_data
    from network_config import MessageType
    sel = _lobby(pygame_display, True)
    sel.randomize_starting_positions()
    sel.network_connection.sent.clear()
    sel.handle_click(sel.map_top_bar.layout()['next'].center)
    assert sel.selected_map == map_data.get_map_ids()[1]
    assert not any(sel.player_selections)
    assert sel.lobby_state._territory_claims == {}   # Claims go with the old map
    assert MessageType.SETUP_CONFIG in sel.network_connection.sent_types()
    assert len(clicks.sounds) == 1


def test_lobby_client_cannot_randomize_or_change_map(pygame_display, clicks):
    sel = _lobby(pygame_display, False)
    lay = sel.map_top_bar.layout()
    before = [slot.territory for slot in sel.lobby_state.slots]
    for control in ('randomize', 'name'):
        sel.handle_click(lay[control].center)
    assert [slot.territory for slot in sel.lobby_state.slots] == before
    assert sel.selected_map == 'avareon'
    assert sel.network_connection.sent == [] and clicks.sounds == []
    assert not sel.map_top_bar.is_flashing('randomize')
    assert sel.randomize_starting_positions() is False
    # Show Borders is this PC's own view: it works for clients
    start = sel.show_borders
    sel.handle_click(lay['borders'].center)
    assert sel.show_borders is (not start) and len(clicks.sounds) == 1


def test_lobby_modals_clear_top_bar_hover(pygame_display):
    sel = _lobby(pygame_display, True)
    point = sel.map_top_bar.layout()['randomize'].center
    sel.handle_hover(point)
    assert sel.map_top_bar.hovered == 'randomize'
    sel.options_overlay.open(sel._additional_options_values())
    sel.handle_hover(point)
    assert sel.map_top_bar.hovered is None and sel.hovered_tooltip is None
    sel.options_overlay.close()
    sel._show_friend_picker = True
    sel.handle_hover(point)
    assert sel.map_top_bar.hovered is None


def test_randomized_starts_reach_the_clients(pygame_display):
    """Real lobby flow over the in-memory network: the host's Randomize arrives at a
    client as the host's exact picks."""
    import map_data
    import mp_harness as h
    from network.territory_selector import TerritorySelector
    from network_config import MessageType
    map_data.load_map('avareon')
    screen = pygame_display.display.get_surface()
    net = h.Network()
    host = TerritorySelector(screen, net.server, is_host=True, local_player_index=0)
    client_conn = net.add_client(1, "P2")
    net.server.message_queue.receive_message({
        'type': MessageType.LOBBY_JOIN, 'data': {'player_index': 1, 'player_name': "P2"}})
    host._process_network_messages()
    client = TerritorySelector(screen, client_conn, is_host=False, local_player_index=1)
    client._process_network_messages()

    assert host.randomize_starting_positions()
    client._process_network_messages()
    picks = [host.lobby_state.slots[i].territory for i in (0, 1)]
    assert all(picks)
    assert [client.lobby_state.slots[i].territory for i in (0, 1)] == picks
    assert client.player_selections[:2] == picks
