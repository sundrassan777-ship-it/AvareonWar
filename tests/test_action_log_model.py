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
