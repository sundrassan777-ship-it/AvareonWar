# -*- coding: utf-8 -*-
"""
Multiplayer lobby chat (network/lobby_chat.py + network/territory_selector.py; the panel:
ui/lobby_chat_panel.py).

Owner rules: separate from the game's chat (its own LOBBY_CHAT type, which the game
ignores), cleared when the lobby ends, 'all' or 'team' lines, "joined / left the lobby"
notices, a click for someone else's line.

- model: text cleaning, empty lines, the 200-line cap, team visibility, unread count
- network (tests/mp_harness.py, the real server / client message handling): host ->
  clients, client -> host -> other clients, team lines delivered but shown to the team
  only, a line naming another slot dropped, join / leave / kick notices, sound
- a lobby line reaching a running game adds nothing to its chat; a new lobby starts empty
  and run() clears the chat however the lobby ends
"""

import os
import sys
import time

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (fixture)
from network.lobby_chat import (LobbyChat, MAX_ENTRIES, MAX_LENGTH, SYSTEM,  # noqa: E402
                                clean_text)
from network_config import MessageType  # noqa: E402


@pytest.fixture(scope="module")
def display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame.display.get_surface()


@pytest.fixture
def sounds(monkeypatch):
    from global_sound import sound_manager
    calls = []
    monkeypatch.setattr(sound_manager, 'play_ui_click', lambda *a, **k: calls.append(1))
    return calls


def _selector(screen, connection, is_host, index):
    import map_data
    from network.territory_selector import TerritorySelector
    map_data.load_map('avareon')
    sel = TerritorySelector(screen, connection, is_host=is_host, local_player_index=index)
    sel.lobby_synced = True
    return sel


class Lobby:
    """Host + clients in one lobby over the harness network."""

    def __init__(self, screen, clients=2):
        self.net = h.Network()
        self.host = _selector(screen, self.net.server, True, 0)
        self.clients = {}
        for index in range(1, clients + 1):
            self.join(screen, index)

    def join(self, screen, index):
        name = f"P{index + 1}"
        connection = self.net.add_client(index, name)
        self.net.server.message_queue.receive_message({
            'type': MessageType.LOBBY_JOIN, 'data': {'player_index': index, 'player_name': name}})
        self.host._process_network_messages()
        self.clients[index] = _selector(screen, connection, False, index)
        self.pump()

    def pump(self):
        """Deliver everything and let every lobby read its messages."""
        for _ in range(3):
            self.net.flush()
            self.host._process_network_messages()
            for sel in self.clients.values():
                sel._process_network_messages()

    def lines(self, sel, viewer_team=None):
        """Visible (name, text) of a lobby's chat, as its own player sees it."""
        team = sel.lobby_state.get_slot(sel.local_player_index).team if viewer_team is None else viewer_team
        return [(e.name, e.text) for e in sel.lobby_chat.visible(sel.local_player_index, team)]

    def player_lines(self, sel):
        return [line for line, e in zip(self.lines(sel), sel.lobby_chat.entries) if not e.is_system]


# ---------------------------------------------------------------- model


def test_clean_text():
    assert clean_text("  hello\nthere\t ") == "hellothere"
    assert clean_text("x" * 300) == "x" * MAX_LENGTH
    assert clean_text(None) == "" and clean_text(42) == "" and clean_text(["hi"]) == ""
    assert clean_text("\x00\x07  ") == ""


def test_empty_lines_are_not_added():
    chat = LobbyChat()
    assert chat.add_player_line(1, "P2", (1, 2, 3), "   ") is None
    assert chat.entries == []


def test_history_is_capped():
    chat = LobbyChat()
    for i in range(MAX_ENTRIES + 25):
        chat.add_player_line(1, "P2", (1, 2, 3), f"line {i}")
    assert len(chat.entries) == MAX_ENTRIES
    assert chat.entries[0].text == "line 25" and chat.entries[-1].text == f"line {MAX_ENTRIES + 24}"


def test_team_lines_show_to_the_team_only():
    chat = LobbyChat()
    entry = chat.add_player_line(1, "P2", (1, 2, 3), "flank left", channel='team', team=0)
    everyone = chat.add_player_line(2, "P3", (1, 2, 3), "hello all")
    assert chat.is_visible(entry, 1, 5)            # The sender, whatever team now
    assert chat.is_visible(entry, 0, 0)            # On the team it was sent to
    assert not chat.is_visible(entry, 2, 1)        # Another team
    assert chat.is_visible(everyone, 2, 1)
    assert chat.add_player_line(1, "P2", (1, 2, 3), "x", channel='nonsense').channel == 'all'


def test_unread_counts_others_lines_until_seen():
    chat = LobbyChat()
    chat.add_player_line(0, "Host", (1, 2, 3), "mine")
    chat.add_system_line("P2 joined the lobby")
    chat.add_player_line(1, "P2", (1, 2, 3), "hi")
    chat.add_player_line(2, "P3", (1, 2, 3), "secret", channel='team', team=3)
    assert chat.unread_count(0, 0) == 1            # Not own, not System, not the other team
    chat.mark_seen()
    assert chat.unread_count(0, 0) == 0
    chat.add_player_line(1, "P2", (1, 2, 3), "again")
    assert chat.unread_count(0, 0) == 1
    chat.clear()
    assert chat.entries == [] and chat.unread_count(0, 0) == 0


# ---------------------------------------------------------------- network


def test_host_line_reaches_every_client(display, sounds):
    lobby = Lobby(display)
    assert lobby.host.send_lobby_chat("Welcome!")
    lobby.pump()
    host_name = lobby.host.lobby_state.get_slot(0).player_name
    for sel in (lobby.host, *lobby.clients.values()):
        assert lobby.player_lines(sel) == [(host_name, "Welcome!")], sel.local_player_index
    assert len(sounds) == 2                        # One click on each client, none on the host


def test_client_line_reaches_host_and_other_client(display, sounds):
    lobby = Lobby(display)
    assert lobby.clients[1].send_lobby_chat("I take the north")
    lobby.pump()
    for sel in (lobby.host, lobby.clients[1], lobby.clients[2]):
        assert lobby.player_lines(sel) == [("P2", "I take the north")], sel.local_player_index
    # The line arrived once on the other client (relayed by the server, not echoed back)
    assert len([e for e in lobby.clients[2].lobby_chat.entries if not e.is_system]) == 1
    assert len([e for e in lobby.clients[1].lobby_chat.entries if not e.is_system]) == 1


def test_team_line_is_delivered_but_shown_to_the_team_only(display):
    lobby = Lobby(display)
    # Host + P2 on team 0, P3 on team 1
    lobby.host.lobby_state.set_player_team(1, 0)
    lobby.host.lobby_state.set_player_team(2, 1)
    lobby.host._broadcast_lobby_state()
    lobby.pump()
    lobby.clients[1].send_lobby_chat("rush them", channel='team')
    lobby.pump()
    assert ("P2", "rush them") in lobby.lines(lobby.host)
    assert ("P2", "rush them") in lobby.lines(lobby.clients[1])
    other = lobby.clients[2]
    assert any(e.text == "rush them" for e in other.lobby_chat.entries)   # Delivered...
    assert ("P2", "rush them") not in lobby.lines(other)                 # ...not shown
    assert other.lobby_chat.unread_count(2, 1) == 0


def test_a_line_naming_another_slot_is_dropped(display):
    lobby = Lobby(display)
    liar = lobby.net.clients[2]
    liar.send_message(liar.protocol.create_lobby_chat(1, "I am P2"))
    lobby.pump()
    for sel in (lobby.host, lobby.clients[1]):
        assert not any(e.text == "I am P2" for e in sel.lobby_chat.entries)


def test_bad_lines_are_ignored(display):
    lobby = Lobby(display, clients=1)
    queue = lobby.host.network_connection.message_queue
    for data in ({'player_index': 3, 'message': "empty slot"},          # Nobody in slot 3
                 {'player_index': 'x', 'message': "bad index"},
                 {'player_index': 1, 'message': ["not", "text"]},
                 {'player_index': 1, 'message': "   "}):
        queue.receive_message({'type': MessageType.LOBBY_CHAT, 'data': data, 'from_player_index': data['player_index']})
    lobby.host._process_network_messages()
    assert not [e for e in lobby.host.lobby_chat.entries if not e.is_system]


def test_join_leave_and_kick_notices(display, monkeypatch):
    lobby = Lobby(display)
    host_lines = [e.text for e in lobby.host.lobby_chat.entries if e.is_system]
    assert host_lines == ["P2 joined the lobby", "P3 joined the lobby"]
    # A client hears about later joins, never about its own
    lobby.clients[1].network_connection.message_queue.receive_message({
        'type': MessageType.LOBBY_JOIN, 'data': {'player_index': 3, 'player_name': "P4"}})
    lobby.clients[1]._process_network_messages()
    assert [e.text for e in lobby.clients[1].lobby_chat.entries if e.is_system] == ["P4 joined the lobby"]

    # P2 leaves: host and the other client say so (once)
    lobby.net.server._disconnect_client(1, "left")
    lobby.pump()
    for sel in (lobby.host, lobby.clients[2]):
        assert [e.text for e in sel.lobby_chat.entries if e.is_system].count("P2 left the lobby") == 1

    # The host kicks P3: one notice on the host (the server's LOBBY_LEAVE finds the slot empty)
    monkeypatch.setattr(time, 'sleep', lambda *_: None)
    lobby.host._kick_player(2)
    lobby.pump()
    assert [e.text for e in lobby.host.lobby_chat.entries].count("P3 left the lobby") == 1


def test_sound_for_others_lines_once_per_burst(display, sounds):
    lobby = Lobby(display, clients=1)
    lobby.host.send_lobby_chat("mine")                 # Own line: no sound here
    assert sounds == []
    for text in ("one", "two", "three"):
        lobby.clients[1].send_lobby_chat(text)
    lobby.pump()
    # Host: one click for the burst; the client clicked once for the host's line
    assert len(sounds) == 2


def test_lobby_line_never_reaches_game_chat(make_session):
    """A lobby line still in flight at launch: the game drops it (separate chats)."""
    session = make_session(num_players=2)
    client = session.net.clients[1]
    client.send_message(client.protocol.create_lobby_chat(1, "gg before start"))
    session.step_all()
    session.step_all()
    assert ('c2s', 1, MessageType.LOBBY_CHAT) in session.net.log   # It did reach the host
    for index in (0, 1):
        assert session.gs(index).chat_messages == []


def test_a_new_lobby_starts_empty_and_run_clears_the_chat(display):
    lobby = Lobby(display, clients=1)
    lobby.host.send_lobby_chat("old talk")
    assert lobby.host.lobby_chat.entries
    lobby.host._run_lobby = lambda: None            # Return to Main Menu at once
    lobby.host.run()
    assert lobby.host.lobby_chat.entries == []
    fresh = _selector(display, h.Network().server, True, 0)
    assert fresh.lobby_chat.entries == []


def test_system_sender_constant():
    chat = LobbyChat()
    entry = chat.add_system_line("P2 joined the lobby")
    assert entry.sender == SYSTEM and entry.is_system


# ---------------------------------------------------------------- the panel (ui/lobby_chat_panel.py)

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


class _Stub:
    """Enough of a server connection for a lobby that sends but receives nothing."""

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


def _lobby(display, size=(1600, 900), is_host=True):
    return _selector(pygame.Surface(size), _Stub(), is_host, 0 if is_host else 1)


def _key(key, char=''):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=char, mod=0)


def _type(sel, text):
    for char in text:
        sel.handle_key(_key(pygame.K_a, char))


def _brightness(surface, rect):
    r, g, b = pygame.transform.average_color(surface, rect)[:3]
    return r + g + b


def _draw(sel):
    sel.screen.fill((0, 0, 0))
    sel.chat_panel.draw()
    return sel.screen


@pytest.mark.parametrize("size", RESOLUTIONS)
def test_panel_geometry(display, size):
    from ui.scaler import UIConstants
    sel = _lobby(display, size)
    panel = sel.chat_panel
    # Starts collapsed: only the bookmark and the round button, at the screen's edge
    assert not panel.expanded and not panel.layout().panel_visible
    _draw(sel)
    tab, toggle = panel.tab_rect, panel.toggle_rect
    assert tab.right == size[0] and toggle.right == size[0]
    map_band = pygame.Rect(sel.left_panel_width, sel.map_y, size[0] - sel.left_panel_width,
                           sel.scaled_map_height)
    assert map_band.contains(tab) and map_band.contains(toggle)
    # Never over the map top bar (Show Borders sits right above it)
    assert not sel.map_top_bar.layout()['borders'].colliderect(toggle)

    panel.set_expanded(True, animate=False)
    _draw(sel)
    body = panel.panel_rect()
    assert body == pygame.Rect(size[0] - UIConstants.SIDEBAR_WIDTH, sel.map_y,
                               UIConstants.SIDEBAR_WIDTH, sel.scaled_map_height)
    assert panel.tab_rect.right == body.left
    assert body.contains(panel.input_rect)


def test_bookmark_opens_and_round_button_closes(display, sounds):
    sel = _lobby(display)
    panel = sel.chat_panel
    _draw(sel)
    sel.handle_click(panel.tab_rect.center)
    assert panel.expanded and panel.clicked_element == 'tab'
    sel.handle_click(panel.tab_rect.center)              # As in game: the bookmark only opens
    assert panel.expanded
    panel._anim_start_ms = None
    _draw(sel)
    sel.handle_click(panel.toggle_rect.center)
    assert not panel.expanded and panel.clicked_element == 'toggle'
    assert len(sounds) == 3
    # F2 too (not while typing)
    sel.handle_key(_key(pygame.K_F2))
    assert panel.expanded


def _point_on_territory_under_panel(sel):
    body = sel.chat_panel.panel_rect()
    for x in range(body.left + 20, body.right - 10, 15):
        for y in range(body.top + 60, body.bottom - 80, 15):
            if sel.get_territory_at_pos((x, y)):
                return (x, y)
    raise AssertionError("no territory under the panel")


def test_clicks_and_hover_over_the_panel_never_reach_the_map(display, sounds):
    sel = _lobby(display)
    sel.chat_panel.set_expanded(True, animate=False)
    _draw(sel)
    point = _point_on_territory_under_panel(sel)
    sel.handle_hover(point)
    assert sel.hovered_territory is None
    sel.handle_click(point)
    assert not sel.lobby_state.slots[0].territory
    assert sounds == []                                  # The list itself makes no sound
    # Collapsed, the same point is the map again
    sel.chat_panel.set_expanded(False, animate=False)
    sel.handle_hover(point)
    assert sel.hovered_territory is not None


def test_wheel_scrolls_the_open_panel_only(display):
    sel = _lobby(display)
    panel = sel.chat_panel
    for i in range(60):
        sel.lobby_chat.add_player_line(1, "P2", (100, 150, 255), f"line number {i}")
    panel.set_expanded(True, animate=False)
    _draw(sel)
    inside = panel.panel_rect().center
    sel.handle_wheel(inside, 1)
    assert panel.scroll.offset > 0                       # Back into older lines
    before = panel.scroll.offset
    sel.handle_wheel((sel.left_panel_width + 50, sel.map_y + 100), 1)   # Over the map
    assert panel.scroll.offset == before


def test_keyboard_flow(display):
    from network_config import MessageType
    sel = _lobby(display)
    panel = sel.chat_panel
    # Enter opens the chat and starts typing
    assert sel.handle_key(_key(pygame.K_RETURN)) is None
    assert panel.expanded and panel.focused
    _type(sel, "hello team")
    sel.handle_key(_key(pygame.K_TAB))                  # Team channel
    sel.handle_key(_key(pygame.K_BACKSPACE))
    assert panel.text == "hello tea" and panel.channel == 'team'
    sel.handle_key(_key(pygame.K_RETURN))               # Sends; typing goes on
    assert panel.text == "" and panel.focused
    entry = sel.lobby_chat.entries[-1]
    assert (entry.text, entry.channel) == ("hello tea", 'team')
    assert sel.network_connection.sent_types() == [MessageType.LOBBY_CHAT]
    # Enter on an empty line sends nothing
    sel.handle_key(_key(pygame.K_RETURN))
    assert len(sel.network_connection.sent) == 1
    # Escape stops typing (clears the draft) and does NOT leave the lobby...
    _type(sel, "draft")
    assert sel.handle_key(_key(pygame.K_ESCAPE)) is None
    assert not panel.focused and panel.text == ""
    # ...the next Escape leaves, as before
    assert sel.handle_key(_key(pygame.K_ESCAPE)) == 'leave'


def test_typing_is_capped_and_keeps_printable_characters(display):
    from network.lobby_chat import MAX_LENGTH
    sel = _lobby(display)
    sel.chat_panel.focus()
    _type(sel, "x" * (MAX_LENGTH + 20))
    assert len(sel.chat_panel.text) == MAX_LENGTH
    sel.chat_panel.text = ""
    sel.handle_key(_key(pygame.K_LSHIFT))                # No character
    sel.handle_key(_key(pygame.K_a, "\r"))
    assert sel.chat_panel.text == ""


def test_modal_windows_keep_their_keys(display):
    sel = _lobby(display)
    sel.options_overlay.open(sel._additional_options_values())
    sel.handle_key(_key(pygame.K_RETURN))
    assert not sel.chat_panel.focused and not sel.chat_panel.expanded
    sel.options_overlay.close()
    sel._show_friend_picker = True
    sel.handle_key(_key(pygame.K_RETURN))
    assert not sel.chat_panel.focused
    assert sel.handle_key(_key(pygame.K_ESCAPE)) is None and not sel._show_friend_picker


def test_clicking_elsewhere_stops_typing_and_the_field_resumes_it(display, sounds):
    sel = _lobby(display)
    panel = sel.chat_panel
    panel.focus()
    panel._anim_start_ms = None
    _type(sel, "keep me")
    _draw(sel)
    sel.handle_click((50, sel.height - 5))               # Somewhere on the left panel
    assert not panel.focused and panel.text == "keep me"   # The draft stays
    sel.handle_click(panel.input_rect.center)
    assert panel.focused and panel.clicked_element == 'input'


def test_controls_highlight_on_hover_and_flash_on_click(display):
    sel = _lobby(display)
    panel = sel.chat_panel
    panel.set_expanded(True, animate=False)
    _draw(sel)
    for element, rect in (('toggle', panel.toggle_rect), ('tab', panel.tab_rect),
                          ('input', panel.input_rect)):
        panel._flash = (None, 0)
        panel.update_hover((-1, -1))
        normal = _brightness(_draw(sel), rect)
        panel.update_hover(rect.center)
        hover = _brightness(_draw(sel), rect)
        panel._flash = (element, pygame.time.get_ticks())
        flash = _brightness(_draw(sel), rect)
        assert normal < hover < flash, (element, normal, hover, flash)


def test_unread_badge_until_the_panel_is_opened(display):
    sel = _lobby(display)
    panel = sel.chat_panel
    sel._add_lobby_chat_line(1, "anyone?", 'all')
    sel._add_lobby_chat_line(2, "here", 'all')
    sel.lobby_chat.add_system_line("P3 joined the lobby")
    _draw(sel)
    assert panel.unread() == 2
    badge_spot = pygame.Rect(panel.tab_rect.x - 8, panel.tab_rect.y + 6, 12, 12)
    gold = _brightness(sel.screen, badge_spot)
    panel.set_expanded(True, animate=False)
    _draw(sel)
    assert panel.unread() == 0
    panel.set_expanded(False, animate=False)
    _draw(sel)
    assert _brightness(sel.screen, badge_spot) < gold    # Badge gone
