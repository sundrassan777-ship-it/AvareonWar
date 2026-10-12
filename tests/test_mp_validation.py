# -*- coding: utf-8 -*-
"""
Who may send what (multiplayer audit, Phase 7).

The server stamps every client message with the index of the connection it came on, and
drops any that names another player as the actor or that only the host may send (L5).
Each PC then checks what that player may do now: only the turn owner acts in sequential
mode, a battle result comes from the battle's resolver, an alliance choice from its
chooser, a hero ability from the Hero's owner, and gold transfers keep to their rules.
The host is the authority and is never refused.

The server and client logic is real (tests/mp_harness.py); the messages a modified
client could send are put on the wire directly (send_as).
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from network.state_snapshot import build_snapshot  # noqa: E402
from network_config import MessageType  # noqa: E402


def drain(queue):
    messages = []
    while True:
        message = queue.get_incoming_message()
        if message is None:
            return messages
        messages.append(message)


def send_as(session, index, msg_type, data):
    """Put a message on the wire from client `index` - what a modified client could send."""
    client = session.net.clients[index]
    client.send_message(client.protocol.encode_message(msg_type, data))


class TestServer:

    def test_relayed_messages_name_their_sender(self):
        net = h.Network()
        first, second = net.add_client(1), net.add_client(2)
        first.send_message(first.protocol.encode_message(
            MessageType.CHAT_MESSAGE, {'player_index': 1, 'message': 'hi', 'channel': 'all'}))
        net.flush()
        [relayed] = drain(second.message_queue)
        [at_host] = drain(net.server.message_queue)
        assert relayed['from_player_index'] == at_host['from_player_index'] == 1

    def test_a_missing_player_field_is_filled_in(self):
        """Receivers no longer guess who sent it ('1 if local == 0 else 0')."""
        net = h.Network()
        first, second = net.add_client(1), net.add_client(2)
        first.send_message(first.protocol.encode_message(
            MessageType.BUILDING_ORDER, {'territory': 'X', 'plot_index': 0, 'building_type': 'Farm'}))
        net.flush()
        assert drain(net.server.message_queue)[0]['data']['player_index'] == 1
        assert drain(second.message_queue)[0]['data']['player_index'] == 1

    @pytest.mark.parametrize('msg_type', [
        MessageType.PLAYER_DISCONNECT, MessageType.AI_TAKEOVER, MessageType.LOBBY_JOIN,
        MessageType.LOBBY_LEAVE, MessageType.LOBBY_KICK, MessageType.LOBBY_LAUNCH,
        MessageType.SETUP_CONFIG, MessageType.FULL_STATE_SYNC, MessageType.DISCONNECT_ELIMINATION])
    def test_only_the_host_sends_these(self, msg_type):
        """E.g. a client's PLAYER_DISCONNECT made the host hand a player's empire to the AI."""
        net = h.Network()
        client, other = net.add_client(1), net.add_client(2)
        client.send_message(client.protocol.encode_message(msg_type, {'player_index': 1}))
        net.flush()
        assert drain(net.server.message_queue) == []
        assert drain(other.message_queue) == []

    @pytest.mark.parametrize('claimed', [1.0, True, '1'])
    def test_the_player_field_must_be_a_real_index(self, claimed):
        """1.0 / True compare equal to 1 - a float index would crash the receivers."""
        net = h.Network()
        client = net.add_client(1)
        client.send_message(client.protocol.encode_message(
            MessageType.CHAT_MESSAGE, {'player_index': claimed, 'message': 'x', 'channel': 'all'}))
        net.flush()
        assert drain(net.server.message_queue) == []

    def test_a_lobby_claim_for_another_slot_is_dropped(self):
        net = h.Network()
        client = net.add_client(1)
        client.send_message(client.protocol.encode_message(
            MessageType.TERRITORY_SELECT, {'player_index': 2, 'territory_name': 'X', 'timestamp': 0}))
        net.flush()
        assert drain(net.server.message_queue) == []


class TestTurnOwner:
    """Sequential mode: only the player whose turn it is acts."""

    def test_actions_out_of_turn_are_refused(self, make_session):
        session = make_session(num_players=3)
        capital = h.spread_territories(3)[2]                 # client 2's own capital
        h.set_turn(session, 1)
        send_as(session, 2, MessageType.BUILDING_ORDER, {
            'territory': capital, 'plot_index': 0, 'building_type': 'Farm', 'player_index': 2})
        session.run_until_quiet()
        for index in (0, 1):
            assert capital not in session.gs(index).under_construction

    def test_a_turn_end_out_of_turn_is_refused(self, make_session):
        """Its snapshot would have replaced the whole game."""
        session = make_session(num_players=3)
        h.set_turn(session, 1)
        forged = json.loads(json.dumps(build_snapshot(session.gs(2))))
        forged['player_gold'][2] = 99999
        forged['current_player'] = 2
        send_as(session, 2, MessageType.TURN_END, {'player_index': 2, 'snapshot': forged})
        session.run_until_quiet()
        for index in (0, 1):
            assert session.gs(index).current_player == 1
            assert session.gs(index).player_gold[2] != 99999


class TestBattles:

    def _sim_battle(self, session, resolver):
        _, b, _ = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, b, 0, h.units('Archer'))
            gs.territory_garrisons[b][1] = {'unmoved': 0, 'moved': 3,
                                            'units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}
            gs.pending_battles = [h.battle_at(b, owner=0, attacker=1, resolver=resolver)]
        session.on_all(arrange)
        for peer in session.peers.values():
            peer.game.sim_state.sim_phase = 'resolving'
        return b

    def test_only_the_resolver_may_send_a_battle_result(self, make_session):
        session = make_session(num_players=3, turn_mode='simultaneous')
        b = self._sim_battle(session, resolver=1)
        send_as(session, 2, MessageType.BATTLE_RESOLVE, {
            'territory': b, 'winner': 2, 'surviving_armies': 3, 'new_owner': 2, 'battle_seed': 5})
        session.run_until_quiet()
        for index in (0, 1):
            assert [bt.territory for bt in session.gs(index).pending_battles] == [b]
            assert session.gs(index).territory_owners[b] == 0

    def test_a_result_for_a_territory_without_a_battle_is_refused(self, make_session):
        """The turn owner claims a territory nobody fought over (it used to be applied)."""
        session = make_session(num_players=2)
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: h.place(gs, b, 0, h.units('Archer')))
        h.set_turn(session, 1)
        session.on_all(lambda gs: setattr(gs, 'turn_phase', 'battles'))
        send_as(session, 1, MessageType.BATTLE_RESOLVE, {
            'territory': b, 'winner': 1, 'surviving_armies': 3, 'new_owner': 1, 'battle_seed': 5,
            'garrisons': {'1': {'unmoved': 0, 'moved': 3,
                                'units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}}})
        session.run_until_quiet()
        assert session.gs(0).territory_owners[b] == 0

    def test_the_simultaneous_host_keeps_its_own_replay(self, make_session):
        """The resolver claims an outcome its seed does not give: the host's replay stands
        (sequential mode: the turn owner's outcome still wins - test_mp_battles)."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        b = self._sim_battle(session, resolver=1)
        claimed = h.units('Pikeman', 'Pikeman', status='moved')
        send_as(session, 1, MessageType.BATTLE_RESOLVE, {
            'territory': b, 'winner': 1, 'surviving_armies': 2, 'new_owner': 1, 'battle_seed': 7,
            'garrisons': {'1': {'unmoved': 0, 'moved': 2, 'units': claimed}}})
        session.flush()
        host = session.game(0)
        host._process_network_messages()
        assert host.game_state.pending_battles == []
        assert h.garrison_summary(host.game_state, b).get(1) != ['Pikeman', 'Pikeman']


class TestAllianceChoices:

    def _marker(self, session, chooser, players):
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, b, players[0]), setattr(gs, 'pending_battles', [])))
        for peer in session.peers.values():
            peer.game.sim_state.sim_phase = 'resolving'
            peer.game.sim_state.phase_manager.pending_alliance_markers = [
                {'type': 'alliance', 'territory': b, 'players': list(players), 'chooser': chooser}]
        return b

    def test_only_the_chooser_may_choose(self, make_session):
        session = make_session(num_players=3, teams=[0, 1, 1], turn_mode='simultaneous')
        b = self._marker(session, chooser=1, players=[1, 2])
        send_as(session, 2, MessageType.SIM_ALLIANCE_CHOICE, {'territory': b, 'new_owner': 2})
        session.run_until_quiet()
        pm = session.game(0).sim_state.phase_manager
        assert [m['territory'] for m in pm.pending_alliance_markers] == [b]
        assert session.gs(0).territory_owners[b] == 1

    def test_the_new_owner_must_be_one_of_the_allies(self, make_session):
        session = make_session(num_players=3, teams=[0, 1, 1], turn_mode='simultaneous')
        b = self._marker(session, chooser=1, players=[1, 2])
        send_as(session, 1, MessageType.SIM_ALLIANCE_CHOICE, {'territory': b, 'new_owner': 0})
        session.run_until_quiet()
        assert session.gs(0).territory_owners[b] == 1


class TestHeroAbilities:
    """Vow of Silence: the receiving side silences the caster's enemies as sent - no
    check of its own - so it shows whether the cast was accepted."""

    def _hero(self, session, owner):
        capital = h.spread_territories(2)[owner]
        hero, ability_index = h.hero_with_ability('Vow of Silence')

        def arrange(gs):
            gs.buildings[capital] = {0: 'Keep'}
            gs.heroes[owner][hero] = {'keep_territory': capital, 'keep_plot': 0, 'status': 'active'}
            gs.hero_ownership[owner].add(hero)
        session.on_all(arrange)
        h.set_turn(session, 1)
        return {'player_id': 1, 'hero_name': hero, 'ability_index': ability_index,
                'ability_name': 'Vow of Silence', 'target': None}

    def test_a_hero_of_someone_else_is_refused(self, make_session):
        session = make_session(num_players=2)
        cast = self._hero(session, owner=0)                  # the host's Hero
        send_as(session, 1, MessageType.SIM_HERO_ABILITY, cast)
        session.run_until_quiet()
        assert session.gs(0).hero_silence_status.get(0, 0) == 0

    def test_their_own_hero_is_accepted(self, make_session):
        session = make_session(num_players=2)
        cast = self._hero(session, owner=1)
        send_as(session, 1, MessageType.SIM_HERO_ABILITY, cast)
        session.run_until_quiet()
        assert session.gs(0).hero_silence_status.get(0, 0) > 0     # the host is silenced


class TestGoldTransfers:

    def _session(self, make_session, pct=100):
        session = make_session(num_players=3, teams=[0, 1, 1])
        session.on_all(lambda gs: setattr(gs, 'gold_transfer_pct', pct))
        h.set_turn(session, 1)
        return session

    def _send(self, session, recipient, amount):
        send_as(session, 1, MessageType.GOLD_TRANSFER, {
            'player_index': 1, 'recipient_index': recipient, 'amount': amount, 'turn_number': 1})
        session.run_until_quiet()

    def test_gold_cannot_be_sent_to_an_enemy(self, make_session):
        session = self._session(make_session)
        before = list(session.gs(0).player_gold)
        self._send(session, recipient=0, amount=50)
        assert session.gs(0).player_gold == before

    def test_gold_sent_is_capped_at_what_the_sender_has(self, make_session):
        session = self._session(make_session)
        session.on_all(lambda gs: gs.player_gold.__setitem__(1, 30))
        before = session.gs(0).player_gold[2]
        self._send(session, recipient=2, amount=9999)
        assert session.gs(0).player_gold[1] == 0
        assert session.gs(0).player_gold[2] == before + 30

    def test_gold_is_sent_once_per_turn_to_a_player(self, make_session):
        session = self._session(make_session)
        before = session.gs(0).player_gold[2]
        self._send(session, recipient=2, amount=10)
        self._send(session, recipient=2, amount=10)
        assert session.gs(0).player_gold[2] == before + 10

    def test_no_transfers_in_a_game_without_them(self, make_session):
        session = self._session(make_session, pct=0)
        before = list(session.gs(0).player_gold)
        self._send(session, recipient=2, amount=10)
        assert session.gs(0).player_gold == before


class TestBrokenMessages:

    def test_a_message_that_fails_is_skipped_and_the_game_goes_on(self, make_session, monkeypatch):
        """An exception while applying a received message used to escape the frame and
        close the game for that player. Now it is logged and skipped; the messages after
        it are still applied."""
        session = make_session(num_players=2)
        client = session.game(1)
        real_add = client.game_state.add_chat_message

        def add_chat_message(player, text, channel='all'):
            if text == "breaks":
                raise ValueError("a handler bug")
            real_add(player, text, channel)
        monkeypatch.setattr(client.game_state, 'add_chat_message', add_chat_message)

        h.send_chat(session.game(0), "breaks")
        h.send_chat(session.game(0), "arrives")
        session.flush()
        client._process_network_messages()           # Peer.step would fail the test here
        assert client.network_message_errors == [MessageType.CHAT_MESSAGE]
        assert [m[2] for m in client.game_state.chat_messages] == ["arrives"]
        client.network_message_errors.clear()         # expected: keep the fixture's check quiet
