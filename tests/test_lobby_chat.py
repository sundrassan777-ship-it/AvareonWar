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
