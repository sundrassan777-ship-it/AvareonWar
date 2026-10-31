# -*- coding: utf-8 -*-
"""
Hosting through Steam, as friends see it (SDR Phase 4):

- the host's lobby sets its Steam rich presence ("connect" = the invite's connect
  string, "status") while it is open, sets it again when the string changes (UPnP adds
  the public address), and clears it however the lobby ends (launch, Alt+F4); clients
  never touch it
- steam_manager reads which friends host from their presence (a log line only when the
  list changes - the Join screen asks every 2 s)
- the lobby's Steam note after the join address: "or via Steam" / "Steam off" + tooltip,
  on the IP line (a line of its own pushed Return to Main Menu off a 900p screen)
- the Join Game screen: with Steam a "Steam Friends" tab (shown first) listing the
  hosting friends with a Join button each, and "Direct IP" (the address box); without
  Steam the address box only, as before
"""

import logging
import os
import sys
import threading
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from network.client import SteamTarget  # noqa: E402
from network.multiplayer_setup import (  # noqa: E402
    FRIEND_ROWS_VISIBLE, FRIENDS_REFRESH_SECONDS, JOIN_TAB_ROW_HEIGHT, NO_FRIENDS_HOSTING,
    FriendJoin, HostingFriendsList, MultiplayerSetup)
from steam_integration import (  # noqa: E402
    HOSTING_DISPLAY_TOKEN, HOSTING_STATUS, SteamManager, steam_manager)
from steam_networking import steam_net  # noqa: E402

HOST_ID = 76561198886995069
OTHER_ID = 76561198000000042
FRIEND_ID = 76561198740785701

FRIENDS = [
    {'steam_id': HOST_ID, 'name': 'Weel', 'connect': f'steam-{HOST_ID},192.168.18.5:7777',
     'status': HOSTING_STATUS},
    {'steam_id': OTHER_ID, 'name': 'Ann', 'connect': '10.0.0.2:7777', 'status': HOSTING_STATUS},
]


@pytest.fixture(scope='module')
def display():
    pygame.init()
    screen = pygame.display.set_mode((1600, 900))
    yield screen
    pygame.quit()


# ---------------------------------------------------------------------------
# steam_manager: our presence, friends' presence
# ---------------------------------------------------------------------------

class _FakeFriends:
    """SteamworksPy's Friends interface: our friend list."""

    def __init__(self):
        self.ids = []
        self.names = {}

    def GetFriendCount(self, flags):
        return len(self.ids)

    def GetFriendByIndex(self, index, flags):
        return self.ids[index]

    def GetFriendPersonaName(self, steam_id):
        return self.names.get(steam_id, '').encode('utf-8')   # bytes, as SteamworksPy


@pytest.fixture
def steam(monkeypatch):
    """
    A SteamManager on a fake Steam: steam.friends(*ids), their rich presence
    (steam.presence[id][key]) and names; steam.ours = the presence we set.
    """
    state = types.SimpleNamespace(presence={}, names={}, ours={}, calls=[])
    state.manager = SteamManager()
    state.manager._initialized = True
    state.manager._steamworks = types.SimpleNamespace(Friends=_FakeFriends())

    def set_rich_presence(key, value):
        state.calls.append((key, value))
        if value:
            state.ours[key] = value
        else:
            state.ours.pop(key, None)        # '' deletes the key (isteamfriends.h)
        return True

    monkeypatch.setattr(type(steam_net), 'available', property(lambda self: True))
    monkeypatch.setattr(steam_net, 'set_rich_presence', set_rich_presence)
    monkeypatch.setattr(steam_net, 'get_friend_rich_presence',
                        lambda steam_id, key: state.presence.get(steam_id, {}).get(key, ''))
    monkeypatch.setattr(steam_net, 'friend_name', lambda steam_id: state.names.get(steam_id, '[unknown]'))
    state.friends = lambda *ids: setattr(state.manager._steamworks.Friends, 'ids', list(ids))
    return state


class TestOurPresence:

    def test_set_then_cleared(self, steam):
        assert steam.manager.set_hosting_presence(f'+connect steam-{HOST_ID},192.168.18.5:7777')
        assert steam.ours == {'connect': f'+connect steam-{HOST_ID},192.168.18.5:7777',
                              'status': HOSTING_STATUS, 'steam_display': HOSTING_DISPLAY_TOKEN}
        steam.manager.clear_hosting_presence()
        assert steam.ours == {}
        calls = len(steam.calls)
        steam.manager.clear_hosting_presence()       # nothing set any more: no Steam calls
        assert len(steam.calls) == calls

    def test_nothing_without_steam(self, steam):
        steam.manager._initialized = False
        assert not steam.manager.set_hosting_presence(f'+connect steam-{HOST_ID}')
        steam.manager.clear_hosting_presence()
        assert steam.calls == []

    def test_the_display_token_is_in_the_file_to_upload(self):
        """Steam friends lists show "steam_display" only as a token from the localization
        file uploaded in Steamworks (Community -> Rich Presence): the game's token and the
        file must agree, or friends see nothing."""
        import re
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'docs', 'steam', 'rich_presence.vdf')
        with open(path, encoding='utf-8') as f:
            parts = re.findall(r'"([^"]*)"|([{}])', f.read())
        # A minimal KeyValues reader: "key" "value" or "key" { ... }
        stack, current, key = [], {}, None
        for text, brace in parts:
            if brace == '{':
                child = {}
                current[key] = child
                stack.append(current)
                current, key = child, None
            elif brace == '}':
                current = stack.pop()
            elif key is None:
                key = text
            else:
                current[key], key = text, None
        assert current['lang']['english']['tokens'][HOSTING_DISPLAY_TOKEN] == HOSTING_STATUS


class TestFriendCountLog:

    def test_logged_only_when_the_count_changes(self, steam, caplog):
        friends = steam.manager._steamworks.Friends
        steam.friends(HOST_ID, OTHER_ID)
        friends.names.update({HOST_ID: 'Weel', OTHER_ID: 'Ann'})
        with caplog.at_level(logging.INFO):
            for _ in range(3):
                assert [f['name'] for f in steam.manager.get_online_friends()] == ['Ann', 'Weel']
            steam.friends(HOST_ID)
            steam.manager.get_online_friends()
        lines = [r.getMessage() for r in caplog.records if 'Steam friends' in r.getMessage()]
        assert lines == ["Found 2 Steam friends", "Found 1 Steam friends"]


class TestHostingFriends:

    def test_hosting_friends_by_name(self, steam):
        steam.friends(HOST_ID, OTHER_ID, FRIEND_ID)
        steam.names.update({HOST_ID: 'Weel', OTHER_ID: 'Ann', FRIEND_ID: 'Rebeka'})
        steam.presence[HOST_ID] = {'connect': f'+connect steam-{HOST_ID},192.168.18.5:7777',
                                   'status': HOSTING_STATUS}
        steam.presence[OTHER_ID] = {'connect': '+connect 10.0.0.2:7777'}   # no Steam relay
        steam.presence[FRIEND_ID] = {'status': 'Playing'}                  # not hosting
        friends = steam.manager.get_hosting_friends()
        assert [f['name'] for f in friends] == ['Ann', 'Weel']
        assert friends[1] == {'steam_id': HOST_ID, 'name': 'Weel',
                              'connect': f'steam-{HOST_ID},192.168.18.5:7777',
                              'status': HOSTING_STATUS}
        assert friends[0]['connect'] == '10.0.0.2:7777'

    def test_nothing_to_join_is_not_listed(self, steam):
        steam.friends(HOST_ID, OTHER_ID)
        steam.presence[HOST_ID] = {'connect': '+connect'}
        steam.presence[OTHER_ID] = {'connect': 'garbage without the argument'}
        assert steam.manager.get_hosting_friends() == []

    def test_a_stranger_name_falls_back_to_the_id(self, steam):
        steam.friends(HOST_ID)
        steam.presence[HOST_ID] = {'connect': f'+connect steam-{HOST_ID}'}
        assert steam.manager.get_hosting_friends()[0]['name'] == str(HOST_ID)

    def test_logged_only_when_the_list_changes(self, steam, caplog):
        steam.friends(HOST_ID)
        steam.names[HOST_ID] = 'Weel'
        steam.presence[HOST_ID] = {'connect': f'+connect steam-{HOST_ID}'}
        with caplog.at_level(logging.INFO):
            for _ in range(3):
                steam.manager.get_hosting_friends()
            steam.presence[HOST_ID] = {}
            steam.manager.get_hosting_friends()
            steam.manager.get_hosting_friends()
        lines = [r.getMessage() for r in caplog.records if 'Friends hosting' in r.getMessage()]
        assert lines == [f"Friends hosting (Steam presence): Weel ('steam-{HOST_ID}')",
                         "Friends hosting (Steam presence): none"]

    def test_none_without_steam(self, steam, monkeypatch):
        monkeypatch.setattr(type(steam_net), 'available', property(lambda self: False))
        steam.friends(HOST_ID)
        steam.presence[HOST_ID] = {'connect': f'+connect steam-{HOST_ID}'}
        assert steam.manager.get_hosting_friends() == []


# ---------------------------------------------------------------------------
# The host's lobby
# ---------------------------------------------------------------------------

class _Server:
    """Enough of NetworkServer for the host's lobby: join addresses and Steam hosting."""

    upnp_manager = None

    def __init__(self, addresses=('192.168.18.5',), steam_id=HOST_ID):
        from network.message_queue import NetworkMessageQueue
        from network.protocol import NetworkProtocol
        self.protocol = NetworkProtocol()
        self.message_queue = NetworkMessageQueue()
        self.addresses = list(addresses)
        self.steam_id = steam_id
        self.sent = []

    def send_message(self, message):
        self.sent.append(message)

    broadcast_message = send_message

    def get_join_addresses(self):
        return list(self.addresses)

    def get_display_ip(self):
        return self.addresses[-1]

    def is_upnp_complete(self):
        return True

    def steam_host_id(self):
        return self.steam_id


def _lobby(screen, server, is_host=True):
    from network.territory_selector import TerritorySelector
    return TerritorySelector(screen, server, is_host=is_host,
                             local_player_index=0 if is_host else 1, host_ip='192.168.18.5')


@pytest.fixture
def presence(monkeypatch):
    """What the lobby asks steam_manager: [('set', connect) / ('clear',), ...]."""
    calls = []
    monkeypatch.setattr(steam_manager, 'set_hosting_presence',
                        lambda connect, status=HOSTING_STATUS: calls.append(('set', connect)) or True)
    monkeypatch.setattr(steam_manager, 'clear_hosting_presence', lambda: calls.append(('clear',)))
    return calls


@pytest.fixture
def frames(monkeypatch):
    """
    Per-frame hook of a screen loop (steam_manager.run_callbacks runs once a frame):
    frames.actions[n]() runs after frame n. A loop still running after 5 s gets Alt+F4.
    """
    record = types.SimpleNamespace(count=0, actions={})

    def pump():
        record.count += 1
        action = record.actions.get(record.count)
        if action:
            action()
    monkeypatch.setattr(steam_manager, 'run_callbacks', pump)
    backstop = threading.Timer(5.0, lambda: pygame.event.post(pygame.event.Event(pygame.QUIT)))
    backstop.start()
    pygame.event.clear()
    yield record
    backstop.cancel()
    pygame.event.clear()


def _quit():
    pygame.event.post(pygame.event.Event(pygame.QUIT))


class TestLobbyPresence:

    def test_set_while_open_and_cleared_on_alt_f4(self, display, presence, frames):
        lobby = _lobby(display, _Server())
        frames.actions[2] = _quit
        assert lobby.run() == 'quit'
        assert presence == [('set', f'+connect steam-{HOST_ID},192.168.18.5:7777'), ('clear',)]

    def test_cleared_on_launch(self, display, presence, frames):
        lobby = _lobby(display, _Server())
        lobby.ready_to_start = True              # Launch Game went through
        result = lobby.run()
        assert isinstance(result, tuple)
        assert presence == [('set', f'+connect steam-{HOST_ID},192.168.18.5:7777'), ('clear',)]

    def test_a_new_address_is_published_once_a_second_at_most(self, display, presence):
        server = _Server()
        lobby = _lobby(display, server)
        lobby._update_hosting_presence(now=100.0)
        server.addresses.append('212.20.115.148')    # UPnP found the public address
        lobby._update_hosting_presence(now=100.5)    # not checked yet
        lobby._update_hosting_presence(now=101.0)
        lobby._update_hosting_presence(now=102.0)    # unchanged: not set again
        assert presence == [
            ('set', f'+connect steam-{HOST_ID},192.168.18.5:7777'),
            ('set', f'+connect steam-{HOST_ID},192.168.18.5:7777,212.20.115.148:7777')]

    def test_without_steam_hosting_the_addresses_are_still_published(self, display, presence):
        """Steam's "Join Game" then launches the friend's game with the addresses, as
        an invite would."""
        lobby = _lobby(display, _Server(steam_id=0))
        lobby._update_hosting_presence(now=100.0)
        assert presence == [('set', '+connect 192.168.18.5:7777')]

    def test_clients_never_touch_it(self, display, presence, frames):
        lobby = _lobby(display, _Server(), is_host=False)
        frames.actions[2] = _quit
        assert lobby.run() == 'quit'
        assert presence == []


class TestLobbySteamNote:

    @pytest.mark.parametrize('size', [(1280, 720), (1600, 900), (1920, 1080)])
    @pytest.mark.parametrize('steam_id, key', [(HOST_ID, 'host_steam'), (0, 'host_steam_off')])
    def test_after_the_address_with_its_tooltip(self, display, size, steam_id, key):
        lobby = _lobby(pygame.Surface(size), _Server(steam_id=steam_id))
        lobby.render()
        note = lobby.tooltip_rects[key]              # note text + (i) mark
        address = lobby._ip_click_rect
        assert address.right < note.left and note.right < lobby.left_panel_width
        assert abs(note.centery - address.centery) <= 3   # on the IP line
        assert note.bottom <= lobby._player_block_rect().top
        assert lobby.return_button_rect.bottom <= size[1]
        other = 'host_steam_off' if key == 'host_steam' else 'host_steam'
        assert other not in lobby.tooltip_rects
        lobby.handle_hover(note.center)
        assert lobby.hovered_tooltip == key

    def test_the_note_follows_steam_hosting(self, display):
        server = _Server()
        lobby = _lobby(display, server)
        lobby.render()
        assert 'host_steam' in lobby.tooltip_rects
        server.steam_id = 0                          # Steam hosting stopped
        lobby.render()
        assert 'host_steam_off' in lobby.tooltip_rects and 'host_steam' not in lobby.tooltip_rects


# ---------------------------------------------------------------------------
# The Join Game screen
# ---------------------------------------------------------------------------

@pytest.fixture
def setup(display):
    pygame.event.clear()
    return MultiplayerSetup(display)


@pytest.fixture
def with_steam(setup, monkeypatch):
    """The Join screen with Steam; with_steam.list = the friends steam_manager reports."""
    state = types.SimpleNamespace(list=list(FRIENDS), reads=0)

    def hosting():
        state.reads += 1
        return list(state.list)
    monkeypatch.setattr(setup, '_steam_friends_available', lambda: True)
    monkeypatch.setattr(steam_manager, 'get_hosting_friends', hosting)
    return state


def _click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def _key(key, text=''):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=text))


class TestJoinScreenWithoutSteam:

    def test_the_address_box_only(self, setup, frames):
        layout = setup._join_screen_layout(False)
        assert layout['tabs'] == {} and layout['list'] is None

        def type_address():
            for _ in range(len("127.0.0.1")):
                _key(pygame.K_BACKSPACE)
            pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_BACKSPACE, mod=0))
            for char in "10.0.0.2":
                _key(0, char)
            _key(pygame.K_RETURN)
        frames.actions[1] = type_address
        assert setup._get_host_ip() == "10.0.0.2"

    def test_no_steam_means_no_tab(self, setup):
        assert not setup._steam_friends_available()   # tests run without Steam


class TestJoinScreenWithSteam:

    def test_starts_on_the_friends_tab_and_joins_one(self, setup, with_steam, frames):
        rows = setup._friend_row_rects(setup._join_screen_layout(True)['list'], 2)
        frames.actions[1] = lambda: _click(rows[0][1].center)
        assert setup._get_host_ip() == FriendJoin('Weel', f'steam-{HOST_ID},192.168.18.5:7777')
        assert with_steam.reads == 1

    def test_the_direct_ip_tab_is_the_address_box(self, setup, with_steam, frames):
        layout = setup._join_screen_layout(True)

        def switch_and_join():
            _click(layout['tabs']['ip'].center)
            _key(pygame.K_RETURN)                    # the box starts with 127.0.0.1
        frames.actions[1] = switch_and_join
        assert setup._get_host_ip() == "127.0.0.1"

    def test_typing_waits_for_the_direct_ip_tab(self, setup, with_steam, frames):
        def keys():
            _key(0, '5')                             # friends tab: not typed anywhere
            _key(pygame.K_RETURN)                    # friends tab: nothing to confirm
            _key(pygame.K_TAB)                       # Tab: Direct IP
            _key(pygame.K_RETURN)
        frames.actions[1] = keys
        assert setup._get_host_ip() == "127.0.0.1"

    def test_the_wheel_scrolls_the_list(self, setup, with_steam, frames):
        with_steam.list = [dict(FRIENDS[0], steam_id=i, name=f'F{i}', connect=f'steam-{i}')
                           for i in range(1, 6)]
        rows = setup._friend_row_rects(setup._join_screen_layout(True)['list'], FRIEND_ROWS_VISIBLE)
        frames.actions[1] = lambda: pygame.event.post(
            pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1, flipped=False))
        frames.actions[2] = lambda: _click(rows[0][1].center)
        assert setup._get_host_ip() == FriendJoin('F2', 'steam-2')

    def test_nobody_hosting_says_so(self, setup, with_steam, frames, monkeypatch):
        with_steam.list = []
        drawn = []
        real_text = setup._text
        monkeypatch.setattr(setup, '_text',
                            lambda font, text, color: drawn.append(text) or real_text(font, text, color))
        frames.actions[1] = _quit
        assert setup._get_host_ip() == 'quit'
        assert NO_FRIENDS_HOSTING in ' '.join(drawn)

    def test_escape_and_exit_go_back(self, setup, with_steam, frames):
        frames.actions[1] = lambda: _click(setup._join_screen_layout(True)['exit'].center)
        assert setup._get_host_ip() is None

    def test_hover_ids(self, setup):
        layout = setup._join_screen_layout(True)
        row_buttons = [(pygame.Rect(10, 10, 50, 20), FRIENDS[0])]
        assert setup._join_screen_hover(layout, 'steam', row_buttons, (20, 20)) == ('row', HOST_ID)
        assert setup._join_screen_hover(layout, 'steam', row_buttons,
                                        layout['tabs']['ip'].center) == 'tab_ip'
        assert setup._join_screen_hover(layout, 'steam', row_buttons, layout['join'].center) is None
        assert setup._join_screen_hover(layout, 'ip', row_buttons, layout['join'].center) == 'join'


class TestJoiningAFriend:

    def test_through_the_connecting_screen_named_after_them(self, setup, monkeypatch):
        calls, errors = [], []
        monkeypatch.setattr(setup, '_get_host_ip',
                            lambda: FriendJoin('Weel', f'steam-{HOST_ID},192.168.18.5:7777'))

        def fail(client, targets, player_name):
            calls.append(targets)
            client.disconnect_reason = "Weel is not hosting a game right now"
            return False
        monkeypatch.setattr(setup, 'connect_with_progress', fail)
        monkeypatch.setattr(setup, '_show_error', errors.append)
        assert setup._run_join_setup() is None
        assert calls == [[SteamTarget(HOST_ID), ('192.168.18.5', 7777)]]
        assert errors == ["Could not join Weel's game: Weel is not hosting a game right now"]


class TestFriendWithSteamOff:
    """
    Two-PC round 2026-10-13: the host's leftover --no-steam-relay ("Steam off" in its
    lobby) - the friend joined from the Steam Friends tab with addresses only, they timed
    out, and the error told them to "pick the host on the Steam Friends tab" - where they
    had come from. Now it says the host's lobby has joining through Steam off.
    """

    def test_unreachable_addresses_name_the_cause(self):
        from network.client import STEAM_JOIN_HINT, steam_off_reason, unreachable_reason
        reason = steam_off_reason(unreachable_reason('192.168.18.5'), 'Weel')
        assert reason.startswith("Weel's lobby has joining through Steam switched off")
        assert STEAM_JOIN_HINT not in reason
        assert 'home network' in reason                   # the address details stay
        assert steam_off_reason(unreachable_reason('10.0.0.2')).startswith("The host's lobby")

    def test_other_reasons_stay(self):
        from network.client import steam_off_reason
        assert steam_off_reason("Lobby is full", 'Weel') == "Lobby is full"
        assert steam_off_reason("", 'Weel') == ""

    def test_the_join_screen_says_so(self, setup, monkeypatch):
        from network.client import STEAM_JOIN_HINT, unreachable_reason
        errors = []
        monkeypatch.setattr(setup, '_get_host_ip',
                            lambda: FriendJoin('Weel', '192.168.18.5:7777'))   # no steam- target

        def unreachable(client, targets, player_name):
            client.disconnect_reason = unreachable_reason('192.168.18.5')
            return False
        monkeypatch.setattr(setup, 'connect_with_progress', unreachable)
        monkeypatch.setattr(setup, '_show_error', errors.append)
        assert setup._run_join_setup() is None
        assert errors[0].startswith("Could not join Weel's game: Weel's lobby has joining "
                                    "through Steam switched off")
        assert STEAM_JOIN_HINT not in errors[0]

    def test_a_typed_address_keeps_the_steam_hint(self, setup, monkeypatch):
        from network.client import STEAM_JOIN_HINT, unreachable_reason
        errors = []
        monkeypatch.setattr(setup, '_get_host_ip', lambda: '192.168.18.5')

        def unreachable(client, targets, player_name):
            client.disconnect_reason = unreachable_reason('192.168.18.5')
            return False
        monkeypatch.setattr(setup, 'connect_with_progress', unreachable)
        monkeypatch.setattr(setup, '_show_error', errors.append)
        setup._run_join_setup()
        assert errors[0].endswith(STEAM_JOIN_HINT)


class TestHostingFriendsList:

    def test_read_again_every_two_seconds(self):
        reads = []
        listing = HostingFriendsList(source=lambda: reads.append(1) or list(FRIENDS))
        listing.update(100.0)
        listing.update(100.0 + FRIENDS_REFRESH_SECONDS - 0.1)
        assert len(reads) == 1
        listing.update(100.0 + FRIENDS_REFRESH_SECONDS)
        assert len(reads) == 2

    def test_scrolls_a_row_at_a_time_within_the_list(self):
        many = [dict(FRIENDS[0], steam_id=i, name=f'F{i}') for i in range(5)]
        listing = HostingFriendsList(source=lambda: many)
        listing.update(0.0)
        assert listing.max_scroll() == 5 - FRIEND_ROWS_VISIBLE
        listing.scroll_by(-1)
        assert listing.scroll == 0
        listing.scroll_by(10)
        assert [f['name'] for f in listing.visible()] == ['F2', 'F3', 'F4']

    def test_a_shorter_list_pulls_the_scroll_back(self):
        friends = [dict(FRIENDS[0], steam_id=i, name=f'F{i}') for i in range(5)]
        listing = HostingFriendsList(source=lambda: list(friends))
        listing.update(0.0)
        listing.scroll_by(2)
        del friends[1:]                              # four stopped hosting
        listing.update(FRIENDS_REFRESH_SECONDS)
        assert listing.scroll == 0 and len(listing.visible()) == 1


@pytest.mark.parametrize('size', [(1280, 720), (1600, 900), (1920, 1080)])
def test_join_screen_layout_fits(size):
    setup = MultiplayerSetup.__new__(MultiplayerSetup)     # the layout needs the size only
    setup.width, setup.height = size
    layout = setup._join_screen_layout(True)
    plain = setup._join_screen_layout(False)
    panel = layout['panel']
    wood = panel.inflate(-2 * 65, 0)                         # the panel's metal frame
    assert pygame.Rect(0, 0, *size).contains(panel)
    for rect in layout['tabs'].values():
        assert wood.contains(rect)
        assert rect.top > layout['title_center'][1] + 20     # under the title
    assert wood.contains(layout['list'])
    rows = MultiplayerSetup._friend_row_rects(layout['list'], FRIEND_ROWS_VISIBLE)
    assert layout['list'].contains(rows[-1][0])              # every visible row fits
    assert layout['list'].bottom <= layout['exit'].top
    # The Direct IP content does not move; the title moves up to make room for the tabs
    for key in ('bar', 'bar_visual', 'join', 'exit', 'label_center'):
        assert plain[key] == layout[key]
    assert plain['title_center'][1] - layout['title_center'][1] == JOIN_TAB_ROW_HEIGHT


def test_tab_labels_fit(setup):
    for rect in setup._join_screen_layout(True)['tabs'].values():
        for label in ("Steam Friends", "Direct IP"):
            assert setup.list_font.size(label)[0] < rect.width - 20


def _strip_brightness(screen, rect):
    """Brightness of a tab's left strip (button art, no text)."""
    return sum(sum(screen.get_at((x, y))[:3])
               for x in range(rect.x + 2, rect.x + 27) for y in range(rect.y + 4, rect.bottom - 4))


def test_tabs_highlight_on_hover_and_flash_on_click(setup):
    if setup.button_bg_image is None:
        pytest.skip("button art not found")
    rect = pygame.Rect(100, 100, 225, 46)

    def brightness(**state):
        setup.screen.fill((0, 0, 0))
        setup._draw_join_tab(rect, "Direct IP", **state)
        return _strip_brightness(setup.screen, rect)
    closed = brightness(active=False, hovered=False, clicked=False)
    closed_hover = brightness(active=False, hovered=True, clicked=False)
    open_tab = brightness(active=True, hovered=False, clicked=False)
    open_hover = brightness(active=True, hovered=True, clicked=False)
    flash = brightness(active=False, hovered=True, clicked=True)
    assert closed < closed_hover and closed < open_tab < open_hover < flash


def test_join_buttons_highlight_on_hover_and_flash_on_click(setup):
    if setup.button_bg_image is None:
        pytest.skip("button art not found")
    rect = pygame.Rect(100, 100, 120, 44)

    def brightness(hovered, clicked):
        setup.screen.fill((0, 0, 0))
        setup._draw_join_screen_button(rect, "Join", (181, 166, 66), hovered, clicked)
        return _strip_brightness(setup.screen, pygame.Rect(rect.x, rect.y, 30, rect.height))
    assert brightness(False, False) < brightness(True, False) < brightness(True, True)
