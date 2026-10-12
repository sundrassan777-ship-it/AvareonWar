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
    """The game config the real flow builds from a finished lobby (host, Join Game and
    Steam-invite joins all use multiplayer_setup.build_multiplayer_config)."""
    from network.multiplayer_setup import build_multiplayer_config
    return build_multiplayer_config(sel)


def stub_connection(**extra):
    """Just enough of NetworkServer / NetworkClient for a selector or loading screen."""
    sent = []
    connection = SimpleNamespace(protocol=NetworkProtocol(), message_queue=NetworkMessageQueue(),
                                 send_message=sent.append, broadcast_message=sent.append,
                                 sent=sent, **extra)
    return connection


class TestLobbyMembership:

    def test_host_lobby_frees_the_slot_when_a_client_leaves(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        join(net, host_sel, 1, "P2")
        assert host_sel.lobby_state.get_slot(1).state == SLOT_HUMAN

        net.server._disconnect_client(1, "left")
        host_sel._process_network_messages()
        assert host_sel.lobby_state.get_slot(1).state == SLOT_EMPTY

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

    def test_joining_player_gets_the_slot_the_server_gave_them(self, display):
        """The host made slot 2 an AI in the same moment the server handed slot 2 to a
        joining player: the player keeps it (the server already told them it is theirs)."""
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        host_sel._apply_slot_dropdown_selection(1, 'type', ("AI (Medium)", SLOT_AI, 1))
        assert 1 in net.server.reserved_slots
        join(net, host_sel, 1, "P2")
        slot = host_sel.lobby_state.get_slot(1)
        assert (slot.state, slot.player_name) == (SLOT_HUMAN, "P2")
        assert host_sel.lobby_state.get_slot(2).state == SLOT_EMPTY
        assert 1 not in net.server.reserved_slots

    def test_other_clients_see_the_freed_slot(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        join(net, host_sel, 1, "P2")
        second = join(net, host_sel, 2, "P3")
        second_sel = selector(display, second, False, 2)
        second_sel._process_network_messages()
        assert second_sel.lobby_state.get_slot(1).state == SLOT_HUMAN

        net.server._disconnect_client(1, "left")
        host_sel._process_network_messages()
        second_sel._process_network_messages()
        assert host_sel.lobby_state.get_slot(1).state == SLOT_EMPTY
        assert second_sel.lobby_state.get_slot(1).state == SLOT_EMPTY
        assert second_sel.lobby_state.get_slot(2).state == SLOT_HUMAN

    def test_client_learns_why_the_lobby_ended(self, display):
        """Host closed the lobby / connection died: the join flow gets the reason."""
        from network.multiplayer_setup import run_client_lobby
        connection = stub_connection(player_index=1, disconnected=True,
                                     disconnect_reason="Host disconnected")
        assert run_client_lobby(display, connection) == ('lost', "Host disconnected")


class TestLaunchRules:

    def _lobby(self, *states):
        """Slot 0 is the host; `states` fill slots 1.. ; everyone gets a territory."""
        lobby = LobbyState(host_name="Host")
        for index, state in enumerate(states, start=1):
            lobby.slots[index].state = state
        for slot, territory in zip(lobby.get_active_players(), h.spread_territories(4)):
            lobby.claim_territory(slot.index, territory)
        return lobby

    def test_launch_blocker_reasons(self):
        assert LobbyState(host_name="Host").launch_blocker() == 'players'
        assert self._lobby(SLOT_AI).launch_blocker() is None
        assert self._lobby(SLOT_EMPTY, SLOT_AI).launch_blocker() == 'gap'
        same_team = self._lobby(SLOT_AI)
        same_team.slots[1].team = same_team.slots[0].team
        assert same_team.launch_blocker() == 'teams'
        no_land = self._lobby(SLOT_AI, SLOT_AI)
        no_land.slots[2].territory = ""
        assert no_land.launch_blocker() == 'territories'

    def test_every_launch_blocker_has_tooltip_text(self):
        from config.setup_tooltips import SETUP_TOOLTIPS
        for reason in ('players', 'gap', 'teams', 'territories'):
            assert SETUP_TOOLTIPS[f'launch_{reason}']['entries']

    def test_greyed_launch_button_explains_why(self, display, monkeypatch):
        host_sel = selector(display, stub_connection(), True, 0)
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: host_sel.launch_button_rect.center)
        host_sel._draw_buttons()
        assert host_sel._launch_tooltip_key == 'launch_players'
        host_sel.lobby_state.set_slot_ai(1)
        host_sel._draw_buttons()
        assert host_sel._launch_tooltip_key == 'launch_territories'
        ready_to_launch(host_sel)
        host_sel._draw_buttons()
        assert host_sel._launch_tooltip_key is None

    def test_launch_is_refused_until_the_lobby_is_ready(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        client = join(net, host_sel, 1, "P2")
        drain(client.message_queue)
        host_sel._launch_game()                   # nobody has a territory yet
        assert not host_sel.ready_to_start
        assert not net.server.game_started
        assert drain(client.message_queue) == []

    def test_launch_shares_the_seed_and_starts_the_game_on_the_server(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        client = join(net, host_sel, 1, "P2")
        ready_to_launch(host_sel)
        host_sel._launch_game()
        assert host_sel.ready_to_start and net.server.game_started
        launch = [m for m in drain(client.message_queue) if m['type'] == MessageType.LOBBY_LAUNCH]
        assert launch[-1]['data']['settings']['game_seed'] == host_sel.game_seed

    def test_lobby_with_a_gap_cannot_launch(self):
        lobby = LobbyState(host_name="Host")
        territories = h.spread_territories(2)
        lobby.slots[0].territory = territories[0]
        lobby.slots[2].state = SLOT_AI
        lobby.slots[2].territory = territories[1]
        assert not lobby.can_launch()

    def test_lobby_needs_two_teams(self):
        lobby = LobbyState(host_name="Host")
        territories = h.spread_territories(2)
        lobby.slots[0].territory = territories[0]
        lobby.slots[1].state = SLOT_AI
        lobby.slots[1].territory = territories[1]
        lobby.slots[1].team = lobby.slots[0].team
        assert not lobby.can_launch()

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

    def test_host_and_client_share_the_game_seed(self, display):
        host_sel, client_sel = self._launched_pair(display, neutral_armies=True)
        host_config = config_for(host_sel)
        time.sleep(0.005)                         # different millisecond on the "other PC"
        client_config = config_for(client_sel)
        assert host_config['game_seed'] == client_config['game_seed']

    def test_joined_client_config_uses_the_host_map(self, display):
        try:
            host_sel, client_sel = self._launched_pair(
                display, selected_map='azincournean_highlands')
            assert config_for(client_sel).get('map_id') == 'azincournean_highlands'
        finally:
            map_data.load_map('avareon')

    def test_host_and_client_build_the_same_game(self, display):
        host_sel, client_sel = self._launched_pair(
            display, neutral_armies=True, turn_mode=1, taxation_level=2, starting_gold=450,
            gold_transfer=2)
        host_config, client_config = config_for(host_sel), config_for(client_sel)
        for key in ('num_players', 'player_is_ai', 'player_ai_difficulty', 'player_territories',
                    'player_colors', 'player_teams', 'player_names', 'win_condition',
                    'taxation_level', 'game_mode', 'neutral_armies', 'randomize_bonuses',
                    'gold_transfer', 'starting_gold', 'map_id', 'game_seed'):
            assert host_config[key] == client_config[key], key
        assert client_config['game_mode'] == 'simultaneous'


class TestLoadingScreen:

    def _screen(self, display, local_index, num_players=2, **connection_extra):
        from loading_screen import LoadingScreen
        connection = stub_connection(**connection_extra)
        game = SimpleNamespace(local_player_index=local_index, campaign_map=None)
        screen = LoadingScreen(display, game, {'num_players': num_players,
                                               'player_is_ai': [False] * num_players},
                               network_connection=connection)
        screen.loading_complete = True
        return screen, connection

    @staticmethod
    def _key(key):
        return pygame.event.Event(pygame.KEYDOWN, key=key, unicode='', mod=0)

    def test_loading_screen_keeps_other_messages(self, display):
        screen, connection = self._screen(display, local_index=1)
        connection.message_queue.receive_message({'type': MessageType.GAME_READY,
                                                  'data': {'player_index': 0}})
        connection.message_queue.receive_message({'type': MessageType.SIM_TIMER_UPDATE,
                                                  'data': {'timers': {}}})
        screen._poll_network_ready()
        assert screen.all_players_ready
        assert [m['type'] for m in drain(connection.message_queue)] == [MessageType.SIM_TIMER_UPDATE]

    def test_messages_before_game_ready_reach_the_game_in_order(self, display):
        screen, connection = self._screen(display, local_index=1)
        queue = connection.message_queue
        queue.receive_message({'type': MessageType.CHAT_MESSAGE, 'data': {'message': 'hi'}})
        screen._poll_network_ready()              # chat is kept back while waiting
        queue.receive_message({'type': MessageType.GAME_READY, 'data': {'player_index': 0}})
        queue.receive_message({'type': MessageType.SIM_TIMER_UPDATE, 'data': {'timers': {}}})
        screen._poll_network_ready()
        screen._hand_over_deferred_messages()
        assert [m['type'] for m in drain(queue)] == [MessageType.CHAT_MESSAGE,
                                                     MessageType.SIM_TIMER_UPDATE]

    def test_host_stops_waiting_for_a_client_that_left(self, display):
        screen, connection = self._screen(display, local_index=0, num_players=3)
        assert screen.expected_remote_players == {1, 2}
        screen._handle_wait_event(self._key(pygame.K_SPACE))      # host is ready
        queue = connection.message_queue
        queue.receive_message({'type': MessageType.GAME_READY, 'data': {'player_index': 1}})
        queue.receive_message({'type': MessageType.PLAYER_DISCONNECT,
                               'data': {'player_index': 2, 'ai_takeover': True}})
        screen._update_wait_state()
        assert screen.result == 'start'
        assert NetworkProtocol().decode_message(connection.sent[-1])['type'] == MessageType.GAME_READY
        screen._hand_over_deferred_messages()     # the game still hands the seat to the AI
        assert [m['type'] for m in drain(queue)] == [MessageType.PLAYER_DISCONNECT]

    def test_escape_leaves_the_game(self, display):
        screen, connection = self._screen(display, local_index=1)
        screen._handle_wait_event(self._key(pygame.K_ESCAPE))
        assert screen.result == 'cancelled'
        assert connection.sent == []              # never told anyone it was ready

    def test_client_is_told_when_the_host_is_gone(self, display):
        screen, connection = self._screen(display, local_index=1, disconnected=False,
                                          disconnect_reason="")
        screen._handle_wait_event(self._key(pygame.K_SPACE))      # ready, waiting
        connection.disconnected = True
        connection.disconnect_reason = "Host disconnected"
        screen._update_wait_state()
        assert screen.result is None and "Host disconnected" in screen.failure_message
        screen._draw()                            # the message is shown
        screen._handle_wait_event(self._key(pygame.K_SPACE))
        assert screen.result == 'disconnected'


class TestRealLobby:
    """The whole Phase 2 path over real localhost sockets and network threads: connect,
    seat, claim territories, launch (shared seed / map / config), loading handshake."""

    @staticmethod
    def _until(condition, tick=lambda: None, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tick()
            if condition():
                return
            time.sleep(0.01)
        raise AssertionError("condition never became true")

    def _launched(self, display):
        from network.client import NetworkClient
        from network.server import NetworkServer
        server = NetworkServer(port=0)
        assert server.start()
        client = NetworkClient()
        try:
            host_sel = selector(display, server, True, 0)
            assert client.connect('127.0.0.1', server.socket.getsockname()[1], player_name="Guest")
            assert client.player_index == 1
            self._until(lambda: host_sel.lobby_state.get_slot(1).state == SLOT_HUMAN,
                        host_sel._process_network_messages)
            client_sel = selector(display, client, False, client.player_index)
            self._until(lambda: client_sel.lobby_synced
                        and client_sel.lobby_state.get_slot(1).state == SLOT_HUMAN,
                        client_sel._process_network_messages)

            host_land, client_land = h.spread_territories(2)
            host_sel.select_territory(host_land)
            client_sel.select_territory(client_land)
            self._until(host_sel._can_launch, host_sel._process_network_messages)
            host_sel._launch_game()
            self._until(lambda: client_sel.ready_to_start, client_sel._process_network_messages)
            return server, client, host_sel, client_sel
        except Exception:
            client.disconnect()
            server.stop()
            raise

    @staticmethod
    def _loading(display, connection, local_index, config):
        from loading_screen import LoadingScreen
        game = SimpleNamespace(local_player_index=local_index, campaign_map=None)
        screen = LoadingScreen(display, game, config, network_connection=connection)
        screen.loading_complete = True
        return screen

    def test_two_players_launch_and_start_together(self, display):
        server, client, host_sel, client_sel = self._launched(display)
        try:
            host_config, client_config = config_for(host_sel), config_for(client_sel)
            for key in ('num_players', 'player_territories', 'player_teams', 'map_id', 'game_seed'):
                assert host_config[key] == client_config[key], key
            assert server.game_started

            host_ls = self._loading(display, server, 0, host_config)
            client_ls = self._loading(display, client, 1, client_config)
            space = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, unicode=' ', mod=0)
            client_ls._handle_wait_event(space)
            host_ls._handle_wait_event(space)
            self._until(lambda: host_ls.result == 'start', host_ls._update_wait_state)
            self._until(lambda: client_ls.result == 'start', client_ls._update_wait_state)
        finally:
            client.disconnect()
            server.stop()

    def test_host_starts_without_a_client_who_quit_while_loading(self, display):
        server, client, host_sel, _ = self._launched(display)
        try:
            host_ls = self._loading(display, server, 0, config_for(host_sel))
            host_ls._handle_wait_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE,
                                                          unicode=' ', mod=0))
            client.disconnect()                   # e.g. Escape on the client's loading screen
            self._until(lambda: host_ls.result == 'start', host_ls._update_wait_state)
            host_ls._hand_over_deferred_messages()
            # The game still learns about it (its seat goes to the AI)
            self._until(lambda: any(m['type'] == MessageType.PLAYER_DISCONNECT
                                    for m in drain(server.message_queue)))
        finally:
            client.disconnect()
            server.stop()


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


class TestLobbyValidation:
    """Phase 7: a client changes only its own slot, and only its colour and team."""

    def test_a_client_changes_only_its_own_colour_and_team(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        client = join(net, host_sel, 1, "P2")
        slot = host_sel.lobby_state.get_slot(1)
        new_colour = host_sel.lobby_state.get_slot(3).color      # an empty slot's (swapped)
        client.send_message(client.protocol.create_lobby_slot_update(1, {
            'color': new_colour, 'team': 3, 'state': SLOT_AI, 'ai_difficulty': 2,
            'territory': h.spread_territories(4)[1]}))
        net.flush()
        host_sel._process_network_messages()
        assert (slot.color, slot.team) == (new_colour, 3)
        assert slot.state == SLOT_HUMAN and slot.territory == ""     # the rest ignored

    def test_a_client_cannot_change_another_slot(self, display):
        net = h.Network()
        host_sel = selector(display, net.server, True, 0)
        client = join(net, host_sel, 1, "P2")
        join(net, host_sel, 2, "P3")
        client.send_message(client.protocol.create_lobby_slot_update(2, {'state': SLOT_EMPTY}))
        net.flush()
        host_sel._process_network_messages()
        assert host_sel.lobby_state.get_slot(2).state == SLOT_HUMAN
