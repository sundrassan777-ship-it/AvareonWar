# -*- coding: utf-8 -*-
"""
Multiplayer tests for Battle Reports.

A client does NOT run resolve_battle(): the BATTLE_RESOLVE handler applies the
winner, garrison and ownership directly. The capture hook therefore never fires
on the defending client, which is exactly the player who needs the report - so
the reports ride along on that message and are unpacked here.

These tests drive _handle_network_message() directly rather than opening sockets.
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import map_data  # noqa: E402  (conftest autouse fixture handles load/cleanup)
from network_config import MessageType  # noqa: E402
from network.protocol import NetworkProtocol  # noqa: E402


@pytest.fixture(scope='module')
def game():
    pygame.init()
    map_data.load_polygons()
    from main import Game
    instance = Game()
    instance.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, False],
        'player_ai_difficulty': [None, None],
    })
    yield instance
    pygame.display.quit()
    pygame.quit()


@pytest.fixture
def client(game):
    """Act as player 1's client: the DEFENDER of the incoming battle."""
    gs = game.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 1
    gs.turn_announcement_active = False
    game.multiplayer_mode = True
    game.local_player_index = 1
    game.network_connection = None      # suppress outbound sends
    game.battle_report_queues = {}
    game.battle_report_popups = []
    game.battle_report_rects = []
    gs.battle_report_inbox = []
    # Leave player 1 holding ground: losing their LAST territory ends the game inside
    # the handler (check_victory), and reports never show once phase != 'playing'.
    for territory in sorted(game.scaled_centers.keys())[1:6]:
        gs.territory_owners[territory] = 1
    gs.eliminated_players.discard(1)
    gs.phase = 'playing'
    gs.winner = None
    yield game
    game.multiplayer_mode = False
    game.local_player_index = None


def _report(territory, defender=1, attacker=0):
    return {
        'territory': territory, 'turn_number': 2,
        'defender': defender, 'attacker': attacker,
        'held': False, 'units_lost': 2, 'units_remaining': 0,
        'structures_destroyed': 1, 'structures_captured': 0,
        'structures_remaining': 0,
        'unit_breakdown': {'Archer': {'original': 2, 'survived': 0, 'lost': 2}},
        'attacker_lost': 1, 'attacker_survivors': 5,
        'defender_lost': 2, 'defender_survivors': 0,
    }


def _battle_resolve(game, reports, territory=None):
    """A BATTLE_RESOLVE payload for a territory that has a pending battle."""
    from game_state import Battle
    gs = game.game_state
    territory = territory or sorted(game.scaled_centers.keys())[0]
    battle = Battle(territory)
    battle.original_owner = 1
    battle.add_army(1, 2, {'Archer': 2})
    battle.add_army(0, 9, {'Swordsman': 9})
    gs.pending_battles = [battle]
    return {
        'territory': territory,
        'winner': 0,
        'surviving_armies': 5,
        'new_owner': 0,
        'battle_reports': reports,
    }


def _send(game, data):
    game._handle_network_message({
        'type': MessageType.BATTLE_RESOLVE,
        'seq': 1,
        'data': data,
    })


class TestClientReceivesReports:

    def test_defending_client_gets_the_report(self, client):
        """
        The whole reason reports are on the wire: this client applied the result
        rather than resolving it, so nothing local would have produced a report.
        """
        report = _report(sorted(client.scaled_centers.keys())[0])
        _send(client, _battle_resolve(client, [report]))

        assert client.battle_report_queues.get(1) == [report]

    def test_report_reaches_the_screen(self, client):
        report = _report(sorted(client.scaled_centers.keys())[0])
        _send(client, _battle_resolve(client, [report]))
        client._update_battle_reports(0.016)
        client.draw_battle_reports()

        assert client.battle_report_popups == [report]
        assert [entry[1] for entry in client.battle_report_rects] == ['detail', 'close']

    def test_reports_for_other_players_are_ignored(self, client):
        """A relayed message reaches everyone; only our own reports are kept."""
        other = _report(sorted(client.scaled_centers.keys())[0], defender=0, attacker=1)
        _send(client, _battle_resolve(client, [other]))

        assert client.battle_report_queues.get(1, []) == []
        assert client.battle_report_queues.get(0, []) == []

    def test_message_without_reports_is_harmless(self, client):
        """Older builds omit the key entirely; the handler must not care."""
        data = _battle_resolve(client, [])
        del data['battle_reports']
        _send(client, data)

        assert client.battle_report_queues.get(1, []) == []
        assert client.game_state.territory_owners[data['territory']] == 0

    def test_non_dict_entries_are_skipped(self, client):
        """The payload is attacker-supplied, so it is not trusted to be well formed."""
        good = _report(sorted(client.scaled_centers.keys())[0])
        _send(client, _battle_resolve(client, ["nonsense", None, 42, good]))

        assert client.battle_report_queues.get(1) == [good]

    def test_battle_result_is_still_applied(self, client):
        """Adding reports must not disturb the existing apply path."""
        data = _battle_resolve(client, [_report(
            sorted(client.scaled_centers.keys())[0])])
        _send(client, data)

        assert client.game_state.territory_owners[data['territory']] == 0
        assert client.game_state.pending_battles == []


class TestPayloadIsWireSafe:

    def test_report_survives_the_real_protocol_encoder(self, client):
        """
        Encoding is plain JSON with a 1 MB cap, and _send_action_to_remote() has no
        try/except around it, so an unencodable value would crash the game loop.
        """
        protocol = NetworkProtocol()
        territory = sorted(client.scaled_centers.keys())[0]
        data = _battle_resolve(client, [_report(territory)])

        encoded = protocol.encode_message(MessageType.BATTLE_RESOLVE, data)
        assert len(encoded) < 1_000_000

        decoded = protocol.decode_message(encoded)  # full frame, incl. length prefix
        assert decoded['data']['battle_reports'][0] == data['battle_reports'][0]

    def test_validation_accepts_the_extra_key(self, client):
        """
        validate_message_data() has no BATTLE_RESOLVE branch, so an unknown key must
        pass. If that ever changes, the message would be silently dropped.
        """
        protocol = NetworkProtocol()
        territory = sorted(client.scaled_centers.keys())[0]
        message = {
            'type': MessageType.BATTLE_RESOLVE,
            'seq': 1,
            'data': _battle_resolve(client, [_report(territory)]),
        }
        assert protocol.validate_message(message) is True
        assert protocol.validate_message_data(message) is True

    def test_a_full_queue_stays_far_below_the_size_cap(self, client):
        """Twenty reports is the per-player cap; the payload must stay small."""
        protocol = NetworkProtocol()
        territory = sorted(client.scaled_centers.keys())[0]
        reports = [_report(territory) for _ in range(20)]
        data = _battle_resolve(client, reports)

        encoded = protocol.encode_message(MessageType.BATTLE_RESOLVE, data)
        assert len(encoded) < 100_000, len(encoded)


class TestLocalFilteringOnTheResolver:

    def test_resolver_does_not_hoard_remote_reports(self, client):
        """
        The resolver captures reports for remote defenders too (it ran the battle).
        Those belong to the other machine, which gets them over the wire, so they
        must not accumulate here.
        """
        remote = _report(sorted(client.scaled_centers.keys())[0],
                         defender=0, attacker=1)
        client.game_state.battle_report_inbox.append(remote)
        client._update_battle_reports(0.016)

        assert client.battle_report_queues.get(0, []) == []

    def test_single_player_keeps_every_human(self, game):
        """Hotseat: each human must see their own reports on their own turn."""
        game.multiplayer_mode = False
        game.local_player_index = None
        game.battle_report_queues = {}
        territory = sorted(game.scaled_centers.keys())[0]

        game.queue_battle_report(_report(territory, defender=0, attacker=1))
        game.queue_battle_report(_report(territory, defender=1, attacker=0))

        assert len(game.battle_report_queues.get(0, [])) == 1
        assert len(game.battle_report_queues.get(1, [])) == 1
