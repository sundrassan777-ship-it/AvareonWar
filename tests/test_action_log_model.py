# -*- coding: utf-8 -*-
"""
Sidebar overhaul P3 — Action Log model (rendering/action_log_model.py, pure Python)
and the Action Log / Chat tabs (pixel scrolling, newest entry visible, no over-scroll).
"""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rendering.action_log_model import ActionLogModel, classify, banner_title  # noqa: E402

NAMES = ['Editoreus', 'AI (Medium)', 'AI (Hard)']


def _rows(messages, local=0, names=NAMES, category_filter=None):
    model = ActionLogModel()
    model.update(messages, local, names, category_filter)
    return model.rows


# ============================================================================
# CLASSIFICATION
# ============================================================================

@pytest.mark.parametrize('message,category', [
    ("Player 1 earned 85 gold from 12 territories", 'economy'),
    ("Player 1: 15 gold lost to taxation (20%)", 'economy'),
    ("Player 1 started building Barracks (60 gold, 2 turns)", 'construction'),
    ("Player 1: Farm completed in Lentria", 'construction'),
    ("Player 1: Swordsman trained in Lobardia", 'training'),
    ("Started research: Efficient Farming (120 gold, 3 turns)", 'research'),
    ("Order created: 3 armies Lobardia -> Lentria", 'orders'),
    ("=== BATTLE in Lentria! ===", 'battle'),
    ("  Defender casualties: 2 Swordsman, 1 Archer", 'battle'),
    ("Player 1 conquers Lentria (4 armies)", 'conquest'),
    ("Player 1: Halon Nextroy trained in Lobardia!", 'hero'),
    ("Player 1: Regicide killed Aidam Narn (Lentria)!", 'hero'),
    ("Not enough gold! (Need 400)", 'error'),
    ("Player 3 ELIMINATED!", 'victory'),
    ("   PLAYER 2 WINS!", 'victory'),
    ("Something nobody categorised", 'other'),
    # Per-player lines carry an owner prefix (GameState.add_player_message)
    ("Player 2: Started research: Master Planner I (85 gold, 2 turns)", 'research'),
    ("Player 2: Not enough gold! (Need 400)", 'error'),
    ("Player 1: Order created: 3 armies Lobardia -> Lentria", 'orders'),
])
def test_classify(message, category):
    assert classify(message) == category


def test_banner_title():
    assert banner_title("=== BATTLE in Lentria! ===") == "Battle in Lentria!"
    assert banner_title("=== Executing 3 orders ===") == "Executing 3 orders"
    assert banner_title("plain line") is None


# ============================================================================
# GROUPING, VISIBILITY, TURN SECTIONS
# ============================================================================

BATTLE_OWN = ["=== BATTLE in Lentria! ===", "  Participants:", "    Player 1: 5 armies",
              "    Player 2: 3 armies", "  Editoreus WINS! Lost 1 battalions, 4 remains"]
BATTLE_OTHERS = ["=== BATTLE in Odatria! ===", "  Participants:", "    Player 2: 4 armies",
                 "    Player 3: 2 armies"]


class TestGrouping:

    def test_battle_details_nest_under_their_banner(self):
        rows = _rows(BATTLE_OWN)
        kinds = [(r.kind, r.indent) for r in rows if r.kind != 'section']
        assert kinds[0] == ('banner', 0)
        assert all(kind == 'entry' and indent >= 1 for kind, indent in kinds[1:])
        assert len({r.group for r in rows if r.kind != 'section'}) == 1

    def test_detail_naming_only_the_opponent_stays_in_our_battle(self):
        """The old per-line filter dropped '    Player 2: 3 armies' from our own battle."""
        texts = [r.text for r in _rows(BATTLE_OWN)]
        assert 'AI (Medium): 3 armies' in texts

    def test_other_players_battle_is_hidden(self):
        texts = [r.text for r in _rows(BATTLE_OTHERS)]
        assert not any('Odatria' in t for t in texts)

    def test_global_lines_are_shown(self):
        assert any(r.text == "Not enough gold! (Need 400)" for r in _rows(["Not enough gold! (Need 400)"]))

    def test_names_replace_player_numbers(self):
        rows = _rows(["Player 1 earned 85 gold from 12 territories"])
        assert rows[-1].text == "Editoreus earned 85 gold from 12 territories"

    def test_elimination_of_another_player_is_one_visible_block(self):
        rows = _rows(["", "=" * 28, "Player 3 ELIMINATED!", "Capital conquered - all territories neutralized",
                      "=" * 28, ""])
        victory = [r for r in rows if r.kind == 'victory']
        assert len(victory) == 1
        assert victory[0].text.splitlines() == ["AI (Hard) ELIMINATED!",
                                                "Capital conquered - all territories neutralized"]
        assert not any(r.text.startswith('=') for r in rows)


class TestTurnSections:

    def test_turn_bands_and_sub_headings(self):
        rows = _rows(["--- Player 1's Turn ---", "Player 1 earned 85 gold from 12 territories",
                      "--- Player 2's Turn ---"] + BATTLE_OWN +
                     ["--- Player 1's Turn ---", "Player 1 earned 90 gold from 12 territories"])
        headings = [(r.kind, r.text) for r in rows if r.kind in ('section', 'turn', 'subturn')]
        assert headings == [('turn', 'Turn 1'), ('subturn', "AI (Medium)'s turn"), ('turn', 'Turn 2')]

    def test_no_empty_headings(self):
        """A turn whose messages are all hidden leaves no heading behind."""
        rows = _rows(["--- Player 1's Turn ---", "Player 1 earned 85 gold from 12 territories",
                      "--- Player 2's Turn ---", "Player 2 earned 60 gold from 9 territories",
                      "--- Player 3's Turn ---", "Player 3 earned 70 gold from 10 territories"])
        assert not any(r.kind == 'subturn' for r in rows)

    def test_start_of_game_section(self):
        rows = _rows(["Player 1 started building Farm (40 gold, 2 turns)", "--- Player 1's Turn ---",
                      "Player 1 earned 85 gold from 12 territories"])
        assert (rows[0].kind, rows[0].text) == ('section', 'Start of game')

    def test_simultaneous_mode_without_headers_is_flat(self):
        rows = _rows(["Player 1 earned 85 gold from 12 territories"] + BATTLE_OWN)
        assert [r.kind for r in rows].count('turn') == 0
        assert any(r.kind == 'banner' for r in rows)


class TestSimultaneousRounds:
    """Simultaneous mode logs '--- Round N ---' once per round (sim_state.start_planning_phase);
    the log shows them as 'Turn N' bands like sequential turns (owner feedback: the log
    used to be one endless 'Start of game' section in simultaneous games)."""

    def test_round_markers_become_turn_bands(self):
        rows = _rows(["--- Round 1 ---", "Player 1 earned 85 gold from 12 territories",
                      "--- Round 2 ---"] + BATTLE_OWN)
        headings = [(r.kind, r.text) for r in rows if r.kind in ('section', 'turn', 'subturn')]
        assert headings == [('turn', 'Turn 1'), ('turn', 'Turn 2')]

    def test_sim_state_logs_one_marker_per_round(self):
        import map_data
        from game_state import GameState
        from simultaneous.sim_state import SimultaneousGameState
        map_data.load_polygons()
        gs = GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[None, 1],
                       skip_setup_phase=True, game_mode='simultaneous')
        gs.phase = 'playing'
        sim = SimultaneousGameState(gs)
        sim.start_planning_phase()
        sim.start_planning_phase()        # repeated call for the same round: no duplicate
        sim.round_number = 2              # what complete_round / the network client do
        sim.start_planning_phase()
        markers = [m for m in gs.messages if m.startswith('--- Round')]
        assert markers == ['--- Round 1 ---', '--- Round 2 ---']


class GameStateHelper:
    @staticmethod
    def victims(text, players):
        from game_state import GameState
        return GameState.ability_victims_line(text, players)


class TestPerPlayerMessages:
    """Owner report: in a simultaneous game the log said "Started research: Master Planner I"
    twice and "Research complete" twice. The second pair was the AI researching the same
    tech a round later - the messages named nobody, so they were shown to everyone."""

    @staticmethod
    def _game_state():
        import map_data
        from game_state import GameState
        map_data.load_polygons()
        gs = GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[None, 1],
                       skip_setup_phase=True, game_mode='simultaneous')
        gs.phase = 'playing'
        return gs

    def test_the_reported_sequence_shows_only_our_research(self):
        rows = _rows(["--- Round 13 ---", "Player 1: Started research: Master Planner I (100 gold, 2 turns)",
                      "--- Round 14 ---", "Player 2: Started research: Master Planner I (85 gold, 2 turns)",
                      "Player 1 earned 189 gold from 4 territories",
                      "Player 1: Research complete: Master Planner I! Planning time increased by 30s",
                      "--- Round 15 ---", "Player 2 earned 756 gold from 31 territories",
                      "Player 2: Research complete: Master Planner I! Planning time increased by 30s"])
        research = [r.text for r in rows if r.category == 'research']
        assert research == ["Editoreus: Started research: Master Planner I (100 gold, 2 turns)",
                            "Editoreus: Research complete: Master Planner I! Planning time increased by 30s"]

    def test_research_messages_name_the_researching_player(self):
        gs = self._game_state()
        gs.current_player = 1
        gs.player_gold[1] = 10000
        tech_id = sorted(gs.player_tech_available[1])[0]
        assert gs.start_research(tech_id)
        assert gs.messages[-1].startswith("Player 2: Started research: ")
        assert gs.cancel_research(1)
        assert gs.messages[-1].startswith("Player 2: Research cancelled: ")
        tech = next(t for t in gs.technologies if t['id'] == tech_id)
        gs.apply_tech_effect(1, tech)
        assert gs.messages[-1].startswith("Player 2: Research complete: ")

    def test_refusals_name_the_player(self):
        gs = self._game_state()
        gs.current_player = 1
        gs.player_gold[1] = 0
        tech_id = sorted(gs.player_tech_available[1])[0]
        assert not gs.start_research(tech_id)
        assert gs.messages[-1].startswith("Player 2: Not enough gold!")
        assert classify(gs.messages[-1]) == 'error'

    def test_enemy_ability_is_shown_to_the_players_it_hits(self):
        """Vow of Silence / Embargo name their victims on a sub-line, so the whole cast
        block reaches them; a caster-only ability (Master Negotiator) stays private."""
        gs = self._game_state()
        gs._activate_embargo(1)
        gs._activate_master_negotiator(1)
        rows = _rows(gs.messages, local=0, names=NAMES[:2])
        texts = [r.text for r in rows]
        assert "AI (Medium): Embargo activated!" in texts
        assert "No income at the start of their next turn: Editoreus" in texts
        assert not any('Master Negotiator' in t or '75% less' in t for t in texts)

    def test_vow_of_silence_names_every_silenced_player(self):
        rows = _rows(["Player 2: Aidam Narn casts Vow of Silence!",
                      GameStateHelper.victims("Heroes silenced until next turn", [0, 2])], local=2)
        assert [r.text for r in rows if r.kind != 'section'] == [
            "AI (Medium): Aidam Narn casts Vow of Silence!",
            "Heroes silenced until next turn: Editoreus, AI (Hard)"]

    def test_attacked_player_sees_diplomacy_charisma_and_failed_regicide(self):
        lines = ["Player 2: Aggressive Diplomacy conquers Lentria from Player 1!",
                 "Player 2: Royal Charisma stole 3 units from Lentria (Player 1) to Odatria!",
                 "Player 2: Regicide failed in Lentria (Player 1) - no hero present!"]
        assert len([r for r in _rows(lines, local=0) if r.kind == 'entry']) == 3
        assert not [r for r in _rows(lines, local=2) if r.kind == 'entry']

    def test_vow_and_embargo_spare_allies_and_eliminated_players(self):
        """Owner rule: these hit enemies only. Both used to hit every player but the
        caster, so a team-mate lost their income / hero abilities too."""
        import map_data
        from game_state import GameState
        map_data.load_polygons()
        gs = GameState(num_players=4, player_is_ai=[False, True, True, True],
                       player_ai_difficulty=[None, 1, 1, 1], player_teams=[0, 0, 1, 1],
                       skip_setup_phase=True)
        gs.phase = 'playing'
        gs.eliminated_players.add(3)
        assert gs.ability_enemies(0) == [2]
        gs.current_player = 0
        gs._activate_vow_of_silence('Aidam Narn', {'name': 'Vow of Silence'})
        assert gs.hero_silence_status.get(1, 0) == 0 and gs.hero_silence_status[2] == 2
        gs._activate_embargo(0)
        assert gs.embargo_blocked_players == [2]
        assert gs.messages[-1] == "  No income at the start of their next turn: Player 3"

    def test_helper_without_player_logs_plain_text(self):
        gs = self._game_state()
        gs.add_player_message(None, "Cancelled 3 orders")
        assert gs.messages[-1] == "Cancelled 3 orders"


class TestIncremental:

    SAMPLE = (["Player 1 started building Farm (40 gold, 2 turns)", "--- Player 1's Turn ---",
               "Player 1 earned 85 gold from 12 territories"] + BATTLE_OWN +
              ["--- Player 2's Turn ---"] + BATTLE_OTHERS +
              ["--- Player 3's Turn ---", "Player 3 conquers Lobardia (3 armies)",
               "", "=" * 28, "Player 3 ELIMINATED!", "=" * 28, "",
               "--- Player 1's Turn ---", "Not enough gold! (Need 400)"] + BATTLE_OWN)

    def test_incremental_matches_full_rebuild_at_any_split(self):
        full = _rows(self.SAMPLE)
        rng = random.Random(7)
        for _ in range(25):
            messages = []
            model = ActionLogModel()
            cut_points = sorted(rng.sample(range(1, len(self.SAMPLE)), 4))
            last = 0
            for cut in cut_points + [len(self.SAMPLE)]:
                messages.extend(self.SAMPLE[last:cut])
                model.update(messages, 0, NAMES)
                last = cut
            assert model.rows == full

    def test_unchanged_messages_do_no_work(self):
        model = ActionLogModel()
        messages = list(self.SAMPLE)
        model.update(messages, 0, NAMES)
        assert model.update(messages, 0, NAMES) is None

    def test_clear_rebuilds(self):
        model = ActionLogModel()
        messages = list(self.SAMPLE)
        model.update(messages, 0, NAMES)
        messages.clear()
        messages.append("Player 1 earned 1 gold from 1 territories")
        model.update(messages, 0, NAMES)
        assert [r.text for r in model.rows if r.kind == 'entry'] == ["Editoreus earned 1 gold from 1 territories"]

    def test_category_filter(self):
        rows = _rows(self.SAMPLE, category_filter={'battle'})
        assert {r.category for r in rows if r.kind in ('entry', 'banner')} == {'battle'}


# ============================================================================
# THE TABS
# ============================================================================

@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture
def game(pygame_display):
    from main import Game
    g = Game()
    g.initialize_game({'num_players': 3, 'player_is_ai': [False, True, True],
                       'player_ai_difficulty': [None, 1, 2]})
    g.apply_display_settings(1600, 900, False)
    g.game_state.phase = 'playing'
    g.tutorial_mission = None
    return g


def _fill_log(game, rounds=30):
    msgs = game.game_state.messages
    for _ in range(rounds):
        msgs.extend(TestIncremental.SAMPLE)


class TestActionLogTab:

    def test_newest_entry_is_visible_at_offset_zero(self, game):
        _fill_log(game)
        game.game_state.messages.append("Player 1 earned 999 gold from 99 territories")
        game.game_state.active_sidebar_tab = 'action_log'
        game.draw_order_sidebar()
        scroll = game.sidebar_scroll['action_log']
        assert scroll.offset == 0 and scroll.max_offset > 0
        # The last row ends inside the viewport
        assert scroll.view_top() + scroll.viewport_h == scroll.content_h

    def test_wheel_cannot_scroll_past_the_start(self, game, monkeypatch):
        import pygame
        _fill_log(game, rounds=5)
        game.game_state.active_sidebar_tab = 'action_log'
        game.draw_order_sidebar()
        lay = game.get_sidebar_layout()
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (lay.panel_x + 120, lay.top + 200))
        for _ in range(500):
            game.handle_camera_zoom(1)      # wheel up, far past the start
            game.draw_order_sidebar()
        scroll = game.sidebar_scroll['action_log']
        assert scroll.offset == scroll.max_offset
        assert scroll.view_top() == 0

    def test_reading_position_holds_while_new_entries_arrive(self, game):
        _fill_log(game, rounds=10)
        game.game_state.active_sidebar_tab = 'action_log'
        game.draw_order_sidebar()
        scroll = game.sidebar_scroll['action_log']
        scroll.scroll(-600)
        game.draw_order_sidebar()
        before = scroll.view_top()
        game.game_state.messages.extend(["Player 1 earned 5 gold from 1 territories"] * 3)
        game.draw_order_sidebar()
        assert scroll.view_top() == before

    def test_no_work_when_nothing_changed(self, game):
        _fill_log(game, rounds=3)
        game.game_state.active_sidebar_tab = 'action_log'
        game.draw_order_sidebar()
        model = game.ui_renderer._log_state['model']
        assert model.update(game.game_state.messages, game.get_local_player(),
                            [game.game_state.get_player_name(i) for i in range(3)],
                            getattr(game, 'sidebar_log_filter', None)) is None


class TestChatTab:

    def test_chat_limit_uses_visible_messages(self, game, monkeypatch):
        """Team messages of the other team are hidden - and no longer count for scrolling."""
        import pygame
        gs = game.game_state
        monkeypatch.setattr(gs, 'get_visible_chat_messages',
                            lambda viewer: [m for m in gs.chat_messages if m[1] == 0])
        for i in range(200):
            gs.add_chat_message(i % 3, f"line {i}", 'all')
        gs.active_sidebar_tab = 'chat'
        game.draw_order_sidebar()
        scroll = game.sidebar_scroll['chat']
        items = game.ui_renderer._chat_state['items']
        assert len(items) == len([m for m in gs.chat_messages if m[1] == 0])
        assert scroll.content_h == sum(item[0] for item in items)

    def test_newest_chat_line_visible(self, game):
        gs = game.game_state
        for i in range(120):
            gs.add_chat_message(0, f"line {i}", 'all')
        gs.active_sidebar_tab = 'chat'
        game.draw_order_sidebar()
        scroll = game.sidebar_scroll['chat']
        assert scroll.offset == 0
        assert scroll.view_top() + scroll.viewport_h == scroll.content_h
