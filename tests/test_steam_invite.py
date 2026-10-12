# -*- coding: utf-8 -*-
"""
Steam invites from the multiplayer lobby (network/territory_selector.py friend picker):

- the invite carries every address the host can be joined at (LAN + public), so the
  same invite works for a friend on the host's network and one over the internet
- Invite waits ("Wait...") until UPnP and the public-IP lookup are done
- a friend can be invited again after INVITE_COOLDOWN_SECONDS (it used to be once per
  lobby); meanwhile the row shows "Invited" and a countdown
- the host's "Join IP:" label carries an (i) tooltip matching the UPnP result
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]
FRIEND = 76561198000000001


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


class _StubServer:
    """Enough of NetworkServer for a host lobby: messages + the join-address API."""

    def __init__(self, upnp_done=True, mapped=False, public_ip='212.20.115.148'):
        from network.protocol import NetworkProtocol
        self.protocol = NetworkProtocol()
        self.sent = []
        self.message_queue = self
        self.upnp_done = upnp_done
        self.mapped = mapped
        self.public_ip = public_ip
        self.upnp_manager = None

    # message plumbing used by TerritorySelector
    def get_incoming_message(self):
        return None

    def send_message(self, message):
        self.sent.append(message)

    def broadcast_message(self, message):
        self.sent.append(message)

    # join-address API (NetworkServer)
    def get_local_ip(self):
        return '192.168.18.5'

    def is_upnp_complete(self):
        return self.upnp_done

    def get_display_ip(self):
        return self.public_ip if self.mapped else self.get_local_ip()

    def get_join_addresses(self):
        if self.mapped:
            return [self.public_ip, self.get_local_ip()]
        return [self.get_local_ip()] + ([self.public_ip] if self.public_ip else [])

    @property
    def status(self):
        return 'success' if self.mapped else 'failed'


@pytest.fixture
def steam(monkeypatch):
    """steam_manager with invites recorded instead of sent."""
    from steam_integration import steam_manager
    sent = []
    monkeypatch.setattr(steam_manager, 'invite_friend',
                        lambda steam_id, text: sent.append((steam_id, text)) or True)
    monkeypatch.setattr(steam_manager, 'can_invite', lambda: True)
    return sent


@pytest.fixture
def clock(monkeypatch):
    """A controllable time.monotonic() for the lobby module."""
    import network.territory_selector as ts
    now = [1000.0]
    monkeypatch.setattr(ts.time, 'monotonic', lambda: now[0])
    return now


def _lobby(server, screen=None):
    import pygame
    from network.territory_selector import TerritorySelector
    screen = screen or pygame.display.get_surface()
    sel = TerritorySelector(screen, server, is_host=True, local_player_index=0,
                            host_ip='192.168.18.5')
    sel._friend_list = [{'steam_id': FRIEND, 'name': 'Friend'}]
    sel._show_friend_picker = True
    return sel


def _invite_button(sel):
    sel._draw_friend_picker()
    return sel._friend_picker_rects['invite_buttons'][FRIEND]


# ---------------------------------------------------------------- connect string


def test_invite_lists_lan_and_public_address(pygame_display, steam, clock):
    sel = _lobby(_StubServer(upnp_done=True, mapped=False))
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert steam == [(FRIEND, '+connect 192.168.18.5:7777,212.20.115.148:7777')]


def test_invite_puts_the_mapped_public_address_first(pygame_display, steam, clock):
    sel = _lobby(_StubServer(upnp_done=True, mapped=True))
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert steam == [(FRIEND, '+connect 212.20.115.148:7777,192.168.18.5:7777')]


def test_invite_string_parses_back_on_the_friends_pc(pygame_display, steam, clock):
    from network.client import parse_connect_targets
    sel = _lobby(_StubServer())
    text = sel._invite_connect_string()
    assert text.startswith('+connect ')
    assert parse_connect_targets(text[len('+connect '):]) == [
        ('192.168.18.5', 7777), ('212.20.115.148', 7777)]


def test_invite_waits_for_the_internet_address(pygame_display, steam, clock):
    server = _StubServer(upnp_done=False)
    sel = _lobby(server)
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert steam == []                                   # still looking up the address
    server.upnp_done = True
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert len(steam) == 1


# ---------------------------------------------------------------- cooldown


def test_friend_can_be_invited_again_after_the_cooldown(pygame_display, steam, clock):
    from network.territory_selector import INVITE_COOLDOWN_SECONDS
    sel = _lobby(_StubServer())
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert len(steam) == 1

    clock[0] += INVITE_COOLDOWN_SECONDS - 1
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert len(steam) == 1                               # still cooling down
    assert sel._invite_countdown_text(FRIEND) == "again in 0:01"

    clock[0] += 1
    assert sel._invite_countdown_text(FRIEND) is None
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert len(steam) == 2


def test_cooldown_is_per_friend(pygame_display, steam, clock):
    sel = _lobby(_StubServer())
    other = FRIEND + 1
    sel._friend_list.append({'steam_id': other, 'name': 'Other'})
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert sel._can_invite_friend(other)
    assert not sel._can_invite_friend(FRIEND)


def test_countdown_starts_at_thirty_seconds(pygame_display, steam, clock):
    sel = _lobby(_StubServer())
    sel._handle_friend_picker_click(_invite_button(sel).center)
    assert sel._invite_countdown_text(FRIEND) == "again in 0:30"


@pytest.mark.parametrize("size", RESOLUTIONS)
def test_countdown_fits_left_of_the_button(pygame_display, steam, clock, size):
    """The countdown sits between the (truncated) name and the button, inside the row."""
    import pygame
    sel = _lobby(_StubServer(), screen=pygame.Surface(size))
    sel._friend_list = [{'steam_id': FRIEND, 'name': 'A Friend With A Very Long Steam Name'}]
    sel._handle_friend_picker_click(_invite_button(sel).center)
    button = _invite_button(sel)                          # redraw: now "Invited" + countdown
    countdown = sel.tiny_font.size(sel._invite_countdown_text(FRIEND))[0]
    panel = sel._friend_picker_rects['panel']
    assert panel.contains(button)
    assert button.left - countdown - int(8 * sel.ui_scale) > panel.left


# ---------------------------------------------------------------- Join IP tooltip


@pytest.mark.parametrize("upnp_done, mapped, key", [
    (False, False, 'host_ip_pending'),
    (True, False, 'host_ip_lan'),
    (True, True, 'host_ip_internet'),
])
def test_join_ip_tooltip_follows_the_upnp_result(pygame_display, upnp_done, mapped, key):
    from config.setup_tooltips import SETUP_TOOLTIPS
    server = _StubServer(upnp_done=upnp_done, mapped=mapped)
    server.upnp_manager = server                          # .status read by _draw_host_ip
    sel = _lobby(server)
    sel._show_friend_picker = False
    sel.render()
    host_keys = {k for k in sel.tooltip_rects if k.startswith('host_ip_')}
    assert host_keys == {key}
    assert key in SETUP_TOOLTIPS
    # The mark sits on the label line, above the IP (which stays clickable)
    assert sel.tooltip_rects[key].bottom <= sel._ip_click_rect.bottom


def test_join_ip_tooltip_key_changes_when_upnp_finishes(pygame_display):
    server = _StubServer(upnp_done=False)
    server.upnp_manager = server
    sel = _lobby(server)
    sel._show_friend_picker = False
    sel.render()
    server.upnp_done = True
    sel.render()
    assert {k for k in sel.tooltip_rects if k.startswith('host_ip_')} == {'host_ip_lan'}


@pytest.mark.parametrize("size", RESOLUTIONS)
def test_join_ip_mark_stays_on_the_panel(pygame_display, size):
    import pygame
    server = _StubServer()
    server.upnp_manager = server
    sel = _lobby(server, screen=pygame.Surface(size))
    sel._show_friend_picker = False
    sel.render()
    rect = sel.tooltip_rects['host_ip_lan']
    assert rect.left > 0 and rect.right < sel.left_panel_width
    assert rect.bottom <= sel._player_block_rect().top
