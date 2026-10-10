# -*- coding: utf-8 -*-
"""
Multiplayer lobby, launch and loading-screen tests (pre-launch multiplayer audit).

TerritorySelector, LobbyState, MultiplayerSetup's config builder and LoadingScreen
are real; the network is tests/mp_harness.py's in-memory server/clients.

xfail(strict=True) tests reproduce confirmed audit findings (ID in the reason); the
fixing phase removes the marker.
"""

import gc
import os
import sys
import time
from types import SimpleNamespace

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
import map_data  # noqa: E402
from network.lobby import LobbyState, SLOT_AI, SLOT_EMPTY, SLOT_HUMAN  # noqa: E402
from network.message_queue import NetworkMessageQueue  # noqa: E402
from network.protocol import NetworkProtocol  # noqa: E402
from network_config import MessageType  # noqa: E402


@pytest.fixture(scope="module")
def display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame.display.get_surface()
    pygame.quit()


def drain(queue):
    messages = []
    while True:
        message = queue.get_incoming_message()
        if message is None:
            return messages
        messages.append(message)


def selector(screen, connection, is_host, local_index):
    from network.territory_selector import TerritorySelector
    return TerritorySelector(screen, connection, is_host=is_host, local_player_index=local_index)


def join(net, host_selector, index, name):
    """A client joins: harness connection + the LOBBY_JOIN the server posts to the host."""
    client = net.add_client(index, name)
    net.server.message_queue.receive_message({
        'type': MessageType.LOBBY_JOIN, 'data': {'player_index': index, 'player_name': name}})
    host_selector._process_network_messages()
    return client


def ready_to_launch(host_selector):
    """Give every active slot a distinct territory so the lobby can launch."""
    for slot, territory in zip(host_selector.lobby_state.get_active_players(),
                               h.spread_territories(4)):
        host_selector.lobby_state.claim_territory(slot.index, territory)
    host_selector._sync_from_lobby_state()


def config_for(sel):
    """The game config the real flow builds from a finished lobby.

    Uses the shared builder once the fix introduces it; until then this is what the
    Steam-invite join path does today (multiplayer_setup._build_config_from_lobby with
    no map_id) - the regular join path differs only by adding map_id afterwards.
    """
    from network import multiplayer_setup
    builder = getattr(multiplayer_setup, 'build_multiplayer_config', None)
    if builder is not None:
        return builder(sel)
    setup = multiplayer_setup.MultiplayerSetup.__new__(multiplayer_setup.MultiplayerSetup)
    setup.victory_options = ["Domination (45+)", "Capital Assault", "Total Conquest"]
    setup.turn_mode_options = ["Sequential", "Simultaneous"]
    return setup._build_config_from_lobby(
        sel.lobby_state, sel.victory_condition, sel.taxation_level, sel.turn_mode,
        sel.neutral_armies, sel.randomize_bonuses, sel.bonus_mapping, sel.gold_transfer)


class TestLobbyMembership:

    @pytest.mark.xfail(strict=True, reason="C7: when a client leaves the lobby the server tells "
                       "only the other clients; the host keeps a ghost player")
    def test_host_lobby_frees_the_slot_when_a_client_leaves(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        join(net, host_sel, 1, "P2")
        assert host_sel.lobby_state.get_slot(1).state == SLOT_HUMAN

        net.server._disconnect_client(1, "left")
        host_sel._process_network_messages()
        assert host_sel.lobby_state.get_slot(1).state == SLOT_EMPTY

    @pytest.mark.xfail(strict=True, reason="H8: clients identify their slot by display name, so "
                       "two players named 'Human' end up driving the same slot")
    def test_client_keeps_its_own_slot_when_names_collide(self, display, monkeypatch):
        from settings_manager import settings
        monkeypatch.setattr(settings, 'get_player_name', lambda: 'Human')

        connection = SimpleNamespace(protocol=NetworkProtocol(), message_queue=NetworkMessageQueue(),
                                     send_message=lambda m: None, broadcast_message=lambda m: None)
        client_sel = selector(display, connection, False, 2)
        lobby = LobbyState(host_name="Host")
        for index in (1, 2):
            lobby.slots[index].state = SLOT_HUMAN
            lobby.slots[index].player_name = 'Human'
        connection.message_queue.receive_message({'type': MessageType.LOBBY_STATE,
                                                  'data': lobby.serialize()})
        client_sel._process_network_messages()
        assert client_sel.local_player_index == 2


class TestLaunchRules:

    @pytest.mark.xfail(strict=True, reason="C8: a lobby with a gap (slot 3 empty, slot 4 used) "
                       "launches and breaks player indices in game")
    def test_lobby_with_a_gap_cannot_launch(self):
        lobby = LobbyState(host_name="Host")
        territories = h.spread_territories(2)
        lobby.slots[0].territory = territories[0]
        lobby.slots[2].state = SLOT_AI
        lobby.slots[2].territory = territories[1]
        assert not lobby.can_launch()

    @pytest.mark.xfail(strict=True, reason="L6: a lobby with everyone on one team launches and "
                       "the game ends on the first victory check")
    def test_lobby_needs_two_teams(self):
        lobby = LobbyState(host_name="Host")
        territories = h.spread_territories(2)
        lobby.slots[0].territory = territories[0]
        lobby.slots[1].state = SLOT_AI
        lobby.slots[1].territory = territories[1]
        lobby.slots[1].team = lobby.slots[0].team
        assert not lobby.can_launch()

    @pytest.mark.xfail(strict=True, reason="C3: set_game_started() is never called, so an "
                       "in-game disconnect is handled as a lobby leave")
    def test_launch_makes_disconnects_reach_the_host_game(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        join(net, host_sel, 1, "P2")
        ready_to_launch(host_sel)
        host_sel._launch_game()
        net.flush()
        drain(net.server.message_queue)

        net.server._disconnect_client(1, "crashed")
        types = [m['type'] for m in drain(net.server.message_queue)]
        assert MessageType.PLAYER_DISCONNECT in types


class TestSharedGameConfig:

    def _launched_pair(self, display, **host_settings):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        client = join(net, host_sel, 1, "P2")
        client_sel = selector(display, client, False, 1)
        for key, value in host_settings.items():
            setattr(host_sel, key, value)
        ready_to_launch(host_sel)
        host_sel._launch_game()
        net.flush()
        client_sel._process_network_messages()
        assert client_sel.ready_to_start
        return host_sel, client_sel

    @pytest.mark.xfail(strict=True, reason="M1: every PC rolls its own game_seed, so Neutral "
                       "Armies differ between host and clients")
    def test_host_and_client_share_the_game_seed(self, display):
        host_sel, client_sel = self._launched_pair(display, neutral_armies=True)
        host_config = config_for(host_sel)
        time.sleep(0.005)                         # different millisecond on the "other PC"
        client_config = config_for(client_sel)
        assert host_config['game_seed'] == client_config['game_seed']

    @pytest.mark.xfail(strict=True, reason="H9: the Steam-invite join builds its config without "
                       "the host's map_id, so the invited client loads Avareon")
    def test_joined_client_config_uses_the_host_map(self, display):
        try:
            host_sel, client_sel = self._launched_pair(
                display, selected_map='azincournean_highlands')
            assert config_for(client_sel).get('map_id') == 'azincournean_highlands'
        finally:
            map_data.load_map('avareon')


class TestLoadingScreen:

    @pytest.mark.xfail(strict=True, reason="M7: the loading screen discards every message that "
                       "is not GAME_READY, including ones queued behind it")
    def test_loading_screen_keeps_other_messages(self, display):
        from loading_screen import LoadingScreen
        connection = SimpleNamespace(protocol=NetworkProtocol(), message_queue=NetworkMessageQueue(),
                                     send_message=lambda m: None, broadcast_message=lambda m: None)
        game = SimpleNamespace(local_player_index=1, campaign_map=None)
        screen = LoadingScreen(display, game, {'num_players': 2, 'player_is_ai': [False, False]},
                               network_connection=connection)
        connection.message_queue.receive_message({'type': MessageType.GAME_READY,
                                                  'data': {'player_index': 0}})
        connection.message_queue.receive_message({'type': MessageType.SIM_TIMER_UPDATE,
                                                  'data': {'timers': {}}})
        screen._poll_network_ready()
        assert screen.all_players_ready
        assert [m['type'] for m in drain(connection.message_queue)] == [MessageType.SIM_TIMER_UPDATE]


class TestColours:

    @pytest.mark.xfail(strict=True, reason="M14: colour choices from the lobby / Custom Game are "
                       "never applied to player_colors")
    def test_chosen_colours_are_used_in_game(self, display):
        from main import Game
        from config.constants import PLAYER_COLORS
        game = Game()
        try:
            game.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                                  'player_ai_difficulty': [1, 1], 'player_colors': {0: 2, 1: 0}})
            assert game.game_state.player_colors[0] == PLAYER_COLORS[2]
            assert game.game_state.player_colors[1] == PLAYER_COLORS[0]
        finally:
            game.__dict__.clear()                 # ~400 MB of map art; don't keep it alive
            gc.collect()
