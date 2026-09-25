# -*- coding: utf-8 -*-
"""
Tests for Book of Tales — Tale I: "Lack of Funds" (tale_lack_of_funds.py).

Covers the scenario setup, the AI targeting/training rules (including the
generic ai_military.mission_allows_ai_target hook), Popularity (drops, Invest,
revolts, widget click + layout), victory/defeat sentinels, save/restore, and the
Book of Tales description markup + launch result.

A real Game on the Azincournean Highlands is needed: the Tale reads plots,
income tiers and adjacencies from that map, and the click test goes through the
real mouse handler. Game construction is slow, so it is module scoped and each
test gets a freshly set-up Tale on top of it.
"""

import json
import os
import random
import sys
from collections import Counter

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import map_data  # noqa: E402
import tale_lack_of_funds as tale_mod  # noqa: E402
from tale_lack_of_funds import (  # noqa: E402
    TaleLackOfFunds, FACTION_TERRITORIES, PLAYER, YELLOW, GREEN, RED, CAPITAL,
    allocate_building_counts, FULL_BUILD_MIX,
)

MAP_ID = 'azincournean_highlands'

# Mirrors main.py _TALE_REGISTRY['tale_1']['config']
TALE_CONFIG = {
    'map_id': MAP_ID,
    'num_players': 4,
    'player_is_ai': [False, True, True, True],
    'player_ai_difficulty': [0, 1, 2, 2],
    'player_teams': [0, 1, 2, 3],
    'win_condition': 'Total Conquest',
    'taxation_level': 0,
    'player1_territory': 'Generax',
    'player2_territory': 'Leyana',
    'player3_territory': 'Entaron',
    'player4_territory': 'Daurels',
}

# A player territory bordering Green (Entaron), used for attack orders
BORDER_FROM, GREEN_TARGET = 'Avantgardian Road', 'Entaron'


@pytest.fixture(scope='module')
def game():
    pygame.init()
    map_data.load_map(MAP_ID)
    from main import Game
    instance = Game(campaign_map='maps/azincournean_highlands/map.png')
    instance.initialize_game(dict(TALE_CONFIG))
    yield instance
    map_data.set_tutorial_mission(None)
    pygame.display.quit()
    pygame.quit()


@pytest.fixture(autouse=True)
def highlands_map():
    """conftest reloads Avareon before every test; the Tale needs its own map."""
    map_data.load_map(MAP_ID)
    yield
    map_data.set_tutorial_mission(None)


def _new_tale(game, seed=0, skip_intro=True):
    """Fresh Tale on the shared Game, wired in exactly as main.py does it.

    Most tests start in normal play, so the intro is skipped unless asked for.
    """
    gs = game.game_state
    gs.movement_orders = []
    gs.pending_battles = []
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    gs.turn_number = 0
    gs.turn_announcement_active = False
    gs.winner = None
    game.battle_popup_visible = False
    game.game_menu_visible = False
    game.options_menu_visible = False
    game.clicked_element = None
    mission = TaleLackOfFunds(gs, game, rng=random.Random(seed))
    game.tutorial_mission = mission
    gs.tutorial_mission = mission
    map_data.set_tutorial_mission(mission)
    if skip_intro:
        mission._end_intro()
    return mission


@pytest.fixture
def voices(monkeypatch):
    """Record transmission voice keys instead of playing them."""
    import global_sound
    played = []
    monkeypatch.setattr(global_sound, 'play_transmission_sound', lambda key: played.append(key) or True)
    return played


@pytest.fixture
def tale(game):
    return _new_tale(game)


def _owned(gs, player):
    return [t for t, o in gs.territory_owners.items() if o == player]


def _units(gs, territory, player):
    return gs.territory_garrisons.get(territory, {}).get(player, {}).get('units', [])


# ============================================================================
# SETUP
# ============================================================================

class TestSetup:

    def test_ownership_matches_spec(self, game, tale):
        gs = game.game_state
        for player, territories in FACTION_TERRITORIES.items():
            assert sorted(_owned(gs, player)) == sorted(territories)
        # Everything else on the 55-territory map is neutral
        assert len(gs.territory_owners) == 55
        assert len(_owned(gs, -1)) == 13

    def test_names_colors_gold(self, game, tale):
        gs = game.game_state
        assert gs.player_names[1:] == ["Aelatanaic Tribes", "Heilonic Kingdoms", "Kingdom of Daurels"]
        assert gs.player_names[0] is None          # Human keeps their profile name
        assert gs.player_gold == [750, 1500, 2500, 2000]
        assert gs.player_colors[PLAYER] == (100, 150, 255)
        assert gs.player_colors[YELLOW] == (255, 220, 100)
        assert gs.player_colors[GREEN] == (100, 200, 100)
        assert gs.player_colors[RED] == (255, 100, 100)

    def test_allocate_building_counts_sums_and_ratios(self):
        rng = random.Random(0)
        for n in range(1, 30):
            pool = allocate_building_counts(n, FULL_BUILD_MIX, rng)
            assert len(pool) == n
        counts = Counter(allocate_building_counts(10, FULL_BUILD_MIX, rng))
        assert counts['Barracks'] == 3
        assert counts['Training Grounds'] == 1 and counts['Square'] == 1
        assert counts['Mine'] + counts['Farm'] == 5

    @pytest.mark.parametrize('seed', range(8))
    def test_red_green_every_plot_filled_no_keeps(self, game, seed):
        _new_tale(game, seed)
        gs = game.game_state
        for faction in (GREEN, RED):
            pool = []
            for territory in FACTION_TERRITORIES[faction]:
                plots = len(map_data.get_plots(territory))
                buildings = gs.buildings.get(territory, {})
                assert sorted(buildings) == list(range(plots)), territory
                assert 'Keep' not in buildings.values()
                # Engine rule: at most one Training Grounds per territory
                assert list(buildings.values()).count('Training Grounds') <= 1
                pool.extend(buildings.values())
            expected = Counter(allocate_building_counts(len(pool), FULL_BUILD_MIX, random.Random(0)))
            got = Counter(pool)
            # Largest-remainder ties may land on either tied type; totals must match
            assert got['Barracks'] == expected['Barracks']
            assert sum(got.values()) == sum(expected.values())

    @pytest.mark.parametrize('seed', range(4))
    def test_player_and_yellow_buildings(self, game, seed):
        _new_tale(game, seed)
        gs = game.game_state
        assert gs.buildings['Generax'][0] == 'Barracks'
        assert gs.buildings['Lires'][0] == 'Square'
        assert gs.buildings['Atoney'][0] == 'Barracks'
        assert gs.buildings['Leyana'][0] == 'Barracks'
        for faction, fixed in ((PLAYER, {'Barracks': 1, 'Square': 1}), (YELLOW, {'Barracks': 2})):
            got = Counter(b for t in FACTION_TERRITORIES[faction] for b in gs.buildings.get(t, {}).values())
            assert got == Counter({**fixed, 'Farm': 4, 'Mine': 2})

    @pytest.mark.parametrize('seed', range(4))
    def test_starting_armies(self, game, seed):
        _new_tale(game, seed)
        gs = game.game_state
        capital = Counter(u['type'] for u in _units(gs, CAPITAL, PLAYER))
        for unit_type, count in (('Pikeman', 2), ('Archer', 1), ('Swordsman', 1), ('Captain', 1)):
            assert capital[unit_type] >= count
        player_units = Counter(u['type'] for t in FACTION_TERRITORIES[PLAYER] for u in _units(gs, t, PLAYER))
        assert player_units == Counter({'Pikeman': 2, 'Archer': 3, 'Swordsman': 3, 'Captain': 1, 'Cavalry': 2})

        for faction, (low, high) in ((YELLOW, (1, 2)), (GREEN, (2, 6)), (RED, (2, 6))):
            for territory in FACTION_TERRITORIES[faction]:
                assert low <= len(_units(gs, territory, faction)) <= high, territory
        for territory in _owned(gs, -1):
            units = _units(gs, territory, -1)
            assert len(units) == 1 and units[0]['type'] in tale_mod.BASIC_UNIT_TYPES

        all_ids = [u['id'] for g in gs.territory_garrisons.values() for gar in g.values() for u in gar['units']]
        assert len(all_ids) == len(set(all_ids))

    def test_no_techs_researched(self, game, tale):
        gs = game.game_state
        for p in range(4):
            assert gs.player_tech_researched[p] == set()
            assert gs.player_tech_available[p] == {"tech_0_0", "tech_1_0", "tech_2_0"}

    def test_player_cannot_train_heroes(self, game, tale):
        gs = game.game_state
        gs.current_player = PLAYER
        assert tale.is_action_allowed('train_hero') is False
        assert tale.should_hide_hero_training() is True
        gs.current_player = GREEN
        assert tale.is_action_allowed('train_hero') is True
        assert tale.should_hide_hero_training() is False

    def test_ai_is_built_in(self, tale):
        assert tale.block_ai is False
        assert tale.update_ai_turn(0.1) is False


# ============================================================================
# AI RULES
# ============================================================================

class TestAIRules:

    def test_ai_factions_never_target_each_other(self, tale):
        for attacker in (YELLOW, GREEN, RED):
            tale.faction_turns[attacker] = 10
            for other in (YELLOW, GREEN, RED):
                if other != attacker:
                    target = FACTION_TERRITORIES[other][0]
                    assert not tale.is_ai_target_allowed(attacker, target)

    def test_red_green_never_take_neutral_land(self, game, tale):
        neutral = _owned(game.game_state, -1)[0]
        for faction in (GREEN, RED):
            tale.hostile[faction] = True
            assert not tale.is_ai_target_allowed(faction, neutral)

    def test_red_green_leave_player_alone_until_provoked(self, game, tale):
        gs = game.game_state
        assert not tale.is_ai_target_allowed(GREEN, 'Lanta')
        ids = [_units(gs, BORDER_FROM, PLAYER)[0]['id']] if _units(gs, BORDER_FROM, PLAYER) else None
        if ids is None:
            # Seed left the border empty: give it a unit to order
            unit = gs._make_unit('Swordsman', 9999, status='ready')
            gs.set_garrison_armies(BORDER_FROM, PLAYER, unmoved=1, moved=0, units=[unit])
            ids = [9999]
        assert gs.add_movement_order_for_units(BORDER_FROM, GREEN_TARGET, ids, player=PLAYER)
        # Only the attacked faction turns hostile
        assert tale.hostile == {GREEN: True, RED: False}
        assert tale.is_ai_target_allowed(GREEN, 'Lanta')
        assert not tale.is_ai_target_allowed(RED, 'Lanta')

    def test_own_territory_always_allowed(self, tale):
        for faction in (YELLOW, GREEN, RED):
            assert tale.is_ai_target_allowed(faction, FACTION_TERRITORIES[faction][0])

    def test_yellow_opening_attack_restriction(self, game, tale):
        neutral = _owned(game.game_state, -1)[0]
        for turn in (1, 2, 3):
            tale.faction_turns[YELLOW] = turn
            assert not tale.is_ai_target_allowed(YELLOW, 'Lanta')
            assert not tale.is_ai_target_allowed(YELLOW, neutral)
        tale.faction_turns[YELLOW] = 4
        assert tale.is_ai_target_allowed(YELLOW, 'Lanta')
        assert tale.is_ai_target_allowed(YELLOW, neutral)

    def test_yellow_training_blocked_first_two_turns(self, game, tale):
        gs = game.game_state
        gs.current_player = YELLOW
        gs.player_gold[YELLOW] = 5000
        results = []
        for turn in (1, 2, 3):
            tale.faction_turns[YELLOW] = turn
            results.append(gs.start_training('Leyana', 0, 'Swordsman'))
        assert results == [False, False, True]

    def test_faction_turns_count_on_turn_start(self, tale):
        tale.notify_event('turn_announcement_done', player_index=YELLOW)
        tale.notify_event('turn_announcement_done', player_index=YELLOW)
        assert tale.faction_turns[YELLOW] == 2

    def test_find_reachable_enemies_respects_hook(self, game, tale):
        from ai_military import AttackPlanner

        class _Stub:
            player_index = GREEN

        planner = AttackPlanner(_Stub())
        assert 'Lanta' not in planner.find_reachable_enemies(game.game_state, 'Plein')
        tale.hostile[GREEN] = True
        assert 'Lanta' in planner.find_reachable_enemies(game.game_state, 'Plein')

    def test_ai_move_guard_blocks_forbidden_order(self, game, tale):
        from ai_player import AIPlayer
        gs = game.game_state
        gs.current_player = GREEN
        ai = AIPlayer(GREEN, 2)
        try:
            ok = ai._execute_action_internal(gs, 'move', {'from': 'Plein', 'to': 'Lanta'})
        finally:
            ai._thread_pool.shutdown(wait=False)
        assert ok is False
        assert not any(o.player == GREEN for o in gs.movement_orders)

    def test_tale_removes_ai_readability_pauses(self, game, tale, monkeypatch):
        """ai_player._pace() scales every AI pause by the mission's ai_delay_scale."""
        from ai_player import AIPlayer
        import ai_player
        slept = []
        monkeypatch.setattr(ai_player.time, 'sleep', lambda s: slept.append(s))
        ai = AIPlayer(GREEN, 2)
        try:
            ai._pace(game.game_state, 2.5)            # Tale active: scale 0.0
            assert slept == []
            tale.active = False                       # No active mission: full pause
            ai._pace(game.game_state, 2.5)
            assert slept == [2.5]
        finally:
            ai._thread_pool.shutdown(wait=False)

    def test_hook_is_inert_without_a_mission(self):
        from ai_military import mission_allows_ai_target

        class _GS:
            tutorial_mission = None
            territory_owners = {}

        assert mission_allows_ai_target(_GS(), 2, 'Lanta') is True


# ============================================================================
# POPULARITY
# ============================================================================

def _player_turn(game, tale, turn_number):
    gs = game.game_state
    gs.current_player = PLAYER
    gs.turn_number = turn_number
    tale.notify_event('turn_announcement_done', player_index=PLAYER)


class TestPopularity:

    def test_decay_sequence_starts_on_second_turn(self, game, tale, monkeypatch):
        monkeypatch.setattr(tale, '_roll_revolt', lambda: None)
        seen = []
        for turn in range(6):
            _player_turn(game, tale, turn)
            seen.append(tale.popularity)
        assert seen == [100, 94, 83, 67, 46, 20]          # Drops 6, 11, 16, 21, 26
        assert tale.popularity_decay == 31

    def test_full_popularity_protects_the_next_turn_start(self, game, tale):
        """The revolt is rolled BEFORE the drop: ending a turn at 100 means 0% chance."""
        gs = game.game_state
        before = dict(gs.territory_owners)
        for turn in range(1, 30):
            tale.popularity = 100                 # Player invested back to full
            _player_turn(game, tale, turn)
        assert gs.territory_owners == before
        # The drop still happened after each roll (clamped at 0 once it exceeds 100)
        assert tale.popularity == max(0, 100 - (tale.popularity_decay - tale_mod.DECAY_STEP))

    def test_revolt_uses_popularity_before_the_drop(self, game, tale):
        gs = game.game_state
        tale.popularity = 50                      # 100% chance before the drop
        _player_turn(game, tale, 1)
        assert len(_owned(gs, PLAYER)) == len(FACTION_TERRITORIES[PLAYER]) - 1
        assert tale.popularity == 50 - tale_mod.DECAY_START

    def test_same_turn_never_drops_twice(self, game, tale, monkeypatch):
        monkeypatch.setattr(tale, '_roll_revolt', lambda: None)
        _player_turn(game, tale, 1)
        _player_turn(game, tale, 1)
        assert tale.popularity == 94

    def test_invest(self, game, tale):
        gs = game.game_state
        gs.player_gold[PLAYER] = 1000
        tale.popularity, tale.popularity_decay = 60, 12
        assert tale.invest()
        assert (tale.popularity, tale.popularity_decay, tale.invest_cost) == (70, tale_mod.DECAY_START, 110)
        assert gs.player_gold[PLAYER] == 900
        assert tale.invest()
        assert tale.invest_cost == 120 and gs.player_gold[PLAYER] == 790

    def test_invest_caps_at_max_but_still_resets_decay(self, game, tale):
        game.game_state.player_gold[PLAYER] = 1000
        tale.popularity, tale.popularity_decay = 97, 10
        assert tale.invest()
        assert tale.popularity == 100 and tale.popularity_decay == tale_mod.DECAY_START

    def test_invest_refused_when_not_allowed(self, game, tale):
        gs = game.game_state
        gs.player_gold[PLAYER] = 99
        assert not tale.invest()                     # Too poor
        gs.player_gold[PLAYER] = 1000
        gs.current_player = YELLOW
        assert not tale.invest()                     # Not the player's turn
        gs.current_player = PLAYER
        gs.turn_announcement_active = True
        assert not tale.invest()                     # Turn banner still up
        gs.turn_announcement_active = False
        gs.turn_phase = 'execution'
        assert not tale.invest()                     # Orders executing
        assert gs.player_gold[PLAYER] == 1000 and tale.invest_cost == 100

    @pytest.mark.parametrize('pop,chance', [(100, 0), (96, 8), (90, 20), (75, 50), (60, 80), (50, 100), (0, 100)])
    def test_revolt_chance_is_two_percent_per_point(self, tale, pop, chance):
        tale.popularity = pop
        assert round(tale.get_revolt_chance() * 100) == chance

    def test_revolt_candidates_by_income_tier(self, tale):
        def incomes(pop):
            tale.popularity = pop
            cands = tale.get_revolt_candidates()
            assert CAPITAL not in cands
            return {map_data.get_territory_income(t) for t in cands}
        assert incomes(99) == {10}
        assert incomes(76) == {10}
        assert incomes(75) == {10, 15}
        assert incomes(51) == {10, 15}
        assert incomes(50) == {10, 15, 20}

    def test_no_revolt_at_full_popularity(self, game, tale):
        before = dict(game.game_state.territory_owners)
        for _ in range(50):
            assert tale._roll_revolt() is None
        assert game.game_state.territory_owners == before

    def test_revolt_hands_territory_to_yellow(self, game, tale):
        gs = game.game_state
        tale.popularity = 0                       # Certain revolt, every tier eligible
        version = gs._territory_owners_version
        units_before = {t: [u['id'] for u in _units(gs, t, PLAYER)] for t in _owned(gs, PLAYER)}
        buildings_before = {t: dict(gs.buildings.get(t, {})) for t in _owned(gs, PLAYER)}

        territory = tale._roll_revolt()

        assert territory and territory != CAPITAL
        assert gs.territory_owners[territory] == YELLOW
        assert PLAYER not in gs.territory_garrisons[territory]
        assert [u['id'] for u in _units(gs, territory, YELLOW)] == units_before[territory]
        assert all(u['status'] == 'ready' for u in _units(gs, territory, YELLOW))
        assert gs.buildings.get(territory, {}) == buildings_before[territory]
        assert gs._territory_owners_version > version

    def test_capital_never_revolts(self, game, tale):
        gs = game.game_state
        tale.popularity = 0
        for _ in range(len(FACTION_TERRITORIES[PLAYER]) + 3):
            tale._roll_revolt()
        assert gs.territory_owners[CAPITAL] == PLAYER
        assert _owned(gs, PLAYER) == [CAPITAL]

    def test_invest_click_through_mouse_handler(self, game, tale):
        gs = game.game_state
        gs.player_gold[PLAYER] = 1000
        tale.render(game.screen)                  # Lays out the widget rects
        assert game.mouse.handle_left_click(tale._invest_rect.center) is True
        assert tale.popularity == 100 and tale.invest_cost == 110
        assert gs.player_gold[PLAYER] == 900
        assert game.clicked_element == tale_mod.INVEST_FLASH_ID

    def test_widget_swallows_clicks_only_inside_itself(self, game, tale):
        tale.render(game.screen)
        assert tale.handle_click(tale._bar_rect.center) is True       # No map click-through
        outside = (tale._widget_rect.right + 50, tale._widget_rect.top - 50)
        assert tale.handle_click(outside) is False

    def test_menus_block_the_widget(self, game, tale):
        game.game_state.player_gold[PLAYER] = 1000
        tale.render(game.screen)
        game.game_menu_visible = True
        try:
            game.mouse.handle_left_click(tale._invest_rect.center)
        finally:
            game.game_menu_visible = False
        assert tale.invest_cost == 100

    def test_widget_layout_follows_scale_and_map_bottom(self, game, tale):
        tale.render(game.screen)
        map_bottom = game.TOP_PANEL_HEIGHT + game.MAP_HEIGHT
        assert tale._widget_rect.bottom <= map_bottom
        assert tale._widget_rect.left >= 0
        width = tale._bar_rect.width
        old_scale = game.ui_scale
        try:
            game.ui_scale = old_scale * 1.5       # As apply_display_settings would
            tale.render(game.screen)
            assert tale._bar_rect.width > width
            assert tale._widget_rect.bottom <= map_bottom
        finally:
            game.ui_scale = old_scale
            tale.render(game.screen)

    def test_bar_eases_toward_value(self, tale):
        tale.popularity = 50
        tale.update(0.05)
        assert 50 < tale._display_popularity < 100          # Moving, not snapped
        for _ in range(100):
            tale.update(0.05)
        assert tale._display_popularity == 50


# ============================================================================
# INTRO / TRANSMISSIONS
# ============================================================================

class TestTransmissions:

    def test_intro_plays_three_lines_in_order_then_unpauses(self, game, voices):
        tale = _new_tale(game, skip_intro=False)
        assert tale.intro_active and tale.game_paused and not tale.timer_visible
        assert not tale.is_action_allowed('build')          # Gameplay paused
        # Camera zoom (1s) + 8s + gap + 7s + gap + 6s, at 20 fps
        for _ in range(int(26 / 0.05)):
            tale.update(0.05)
            if not tale.intro_active:
                break
        assert voices == ['T1T1', 'T1T2', 'T1T3']
        assert not tale.intro_active and not tale.game_paused and tale.timer_visible
        assert tale.is_action_allowed('build')

    def test_intro_line_durations(self, game, voices):
        tale = _new_tale(game, skip_intro=False)
        while tale.intro_active and not voices:          # Finish the camera step
            tale.update(0.05)
        assert tale.transmission_duration == 8.0
        for _ in range(int(7.9 / 0.05)):
            tale.update(0.05)
        assert voices == ['T1T1'] and tale.transmission_overlay is not None
        for _ in range(int((0.2 + tale_mod.INTRO_LINE_GAP) / 0.05) + 1):
            tale.update(0.05)
        assert voices == ['T1T1', 'T1T2'] and tale.transmission_duration == 7.0

    def test_escape_skips_intro_lines(self, game, voices):
        tale = _new_tale(game, skip_intro=False)
        while tale.intro_active and not voices:
            tale.update(0.05)
        for expected in (['T1T1', 'T1T2'], ['T1T1', 'T1T2', 'T1T3']):
            assert tale.skip_transmission()
            assert voices == expected
        assert tale.skip_transmission()                   # Skipping the last line ends it
        assert not tale.intro_active

    def test_revolt_queues_its_transmission(self, game, tale, voices):
        tale.popularity = 0
        tale._roll_revolt()
        assert tale.transmission_queue == [tale_mod.REVOLT_TRANSMISSION]
        tale.update(0.05)                                 # Idle planning phase: plays now
        assert voices == ['T1Revolt'] and tale.transmission_duration == 3.0
        assert tale.transmission_queue == []

    def test_loaded_game_skips_intro(self, game, tale):
        data = json.loads(json.dumps(tale.get_save_state()))
        restored = _new_tale(game, skip_intro=False)
        restored.restore_save_state(data)
        assert not restored.intro_active and not restored.game_paused
        assert restored.transmission_overlay is None

    def test_voice_files_exist(self):
        keys = [step[4] for step in tale_mod.INTRO_SEQUENCE if step[4]]
        keys += [t[2] for t in (tale_mod.REVOLT_TRANSMISSION, tale_mod.VICTORY_TRANSMISSION,
                                tale_mod.DEFEAT_TRANSMISSION)]
        folder = 'assets/sounds/transmissions'
        stems = {os.path.splitext(f)[0] for f in os.listdir(folder)}
        assert set(keys) <= stems, set(keys) - stems


# ============================================================================
# KEEP DEMOLISH (engine fix found while playtesting the Tale)
# ============================================================================

class TestKeepDemolish:

    def test_demolish_keep_click_is_not_swallowed_by_sidebar(self, game, tale):
        """The Demolish Keep button sits in the bottom panel's rightmost 250 px.
        The sidebar click region used to cover that strip too (no y check), so
        the click never reached the button while the sidebar was open."""
        gs = game.game_state
        gs.sidebar_expanded = True
        gs.buildings['Alanca'][1] = 'Keep'
        game.selected_keep = ('Alanca', 1)
        try:
            game.draw()
            rect = game.demolish_keep_button
            assert rect is not None
            assert game.mouse.handle_left_click(rect.center)
            assert 1 not in gs.buildings.get('Alanca', {})
        finally:
            game.selected_keep = None

    @pytest.mark.parametrize('attackers,expected_owner,survivors', [
        (['Cavalry'], GREEN, 0),                  # 1 vs Keep (+2): Keep holds
        (['Cavalry'] * 4, PLAYER, 2),             # 4 vs Keep (+2): 2 survive
    ])
    def test_keep_alone_has_no_phantom_units(self, game, tale, attackers, expected_owner, survivors):
        """A Keep defending an empty territory used to show '2 Swordsman' on the
        pre-battle screen: the +2 bonus was turned into fake units in both the
        battle composition and the defender's garrison."""
        gs = game.game_state
        gs.territory_owners['Plein'] = GREEN
        gs.buildings['Plein'] = {0: 'Keep'}
        gs.territory_garrisons['Plein'] = {}
        gs.sync_legacy_garrison_data('Plein')
        units = [gs._make_unit(t, i, status='ready') for i, t in enumerate(attackers)]
        gs.set_garrison_armies('Lanta', PLAYER, unmoved=len(units), moved=0, units=units)
        assert gs.add_movement_order_for_units('Lanta', 'Plein', [u['id'] for u in units], player=PLAYER)
        gs.execute_all_orders()
        for _ in range(400):
            if not gs.active_animations and not gs.pending_arrivals:
                break
            gs.update_animations(0.05)

        battle = gs.pending_battles[0]
        assert battle.keep_bonus == 2 and battle.armies[GREEN] == 2
        assert not battle.army_compositions.get(GREEN)            # No fake Swordsmen
        assert GREEN not in gs.territory_garrisons['Plein']        # No fake garrison

        from ui.effects.battle_interface import EnhancedBattleInterface
        ui = EnhancedBattleInterface(screen=game.screen, game_state=gs, battle_index=0,
                                     font_manager=game.font_manager, current_player_index=PLAYER)
        assert ui.defender_composition == {} and ui.defender_strength == 2

        # Resolution is unchanged by the fix
        gs.resolve_battle(0)
        assert gs.territory_owners['Plein'] == expected_owner
        assert len(_units(gs, 'Plein', PLAYER)) == survivors

    def test_tale_allows_demolish(self, tale):
        # The Keep panel greys the button out only when this returns False
        assert tale.is_action_allowed('demolish') is True


# ============================================================================
# VICTORY / DEFEAT
# ============================================================================

def _run_until_exit(tale, frames=400):
    for _ in range(frames):
        result = tale.update(0.05)
        if result:
            return result
    return None


class TestEndgame:

    def test_generax_falling_is_defeat(self, game, tale, voices):
        tale.notify_event('territory_conquered', territory=CAPITAL, new_owner=GREEN)
        assert game.game_state.phase == 'ended'
        assert _run_until_exit(tale) == 'exit_campaign_defeat'
        assert voices == ['T1TLoss']
        assert tale.defeat_image is not None      # defeatscrn.png was shown (shared endgame)

    def test_yellow_eliminated_is_victory(self, game, tale, voices):
        gs = game.game_state
        for territory in FACTION_TERRITORIES[YELLOW]:
            gs.territory_owners[territory] = PLAYER
        tale.notify_event('territory_conquered', territory='Leyana', new_owner=PLAYER)
        assert gs.winner == PLAYER
        assert all(q['completed'] for q in tale.get_quest_log())
        assert _run_until_exit(tale) == 'exit_campaign'
        assert voices == ['T1TWin']

    def test_victory_awards_lack_of_funds_achievement(self, game, tale, voices, monkeypatch):
        import achievement_manager as am
        ach = next(a for a in am.ACHIEVEMENTS if a['id'] == 'campaign_tale_1')
        assert ach['name'] == 'Lack of Funds'
        assert ach['description'] == 'Win the Lack of Funds mission in the Book of Tales.'
        assert ach['reward_type'] is None and os.path.exists(ach['icon'])

        # Fresh manager with empty progress; never write the player's real profile
        manager = object.__new__(am.AchievementManager)
        manager.stats, manager.earned = {}, {}
        monkeypatch.setattr(manager, 'save', lambda: None)

        gs = game.game_state
        for territory in FACTION_TERRITORIES[YELLOW]:
            gs.territory_owners[territory] = PLAYER
        tale.notify_event('territory_conquered', territory='Leyana', new_owner=PLAYER)
        assert _run_until_exit(tale) == 'exit_campaign'
        earned = manager.record_game_result(game)
        assert 'campaign_tale_1' in [a['id'] for a in earned]

    def test_defeat_does_not_award_the_achievement(self, game, tale, voices, monkeypatch):
        import achievement_manager as am
        manager = object.__new__(am.AchievementManager)
        manager.stats, manager.earned = {}, {}
        monkeypatch.setattr(manager, 'save', lambda: None)
        tale.notify_event('territory_conquered', territory=CAPITAL, new_owner=GREEN)
        assert _run_until_exit(tale) == 'exit_campaign_defeat'
        assert 'campaign_tale_1' not in [a['id'] for a in manager.record_game_result(game)]

    def test_outro_waits_for_queued_revolt_transmission(self, game, tale, voices):
        tale._queue_transmission(tale_mod.REVOLT_TRANSMISSION)
        tale.notify_event('territory_conquered', territory=CAPITAL, new_owner=YELLOW)
        assert _run_until_exit(tale) == 'exit_campaign_defeat'
        assert voices == ['T1Revolt', 'T1TLoss']

    def test_no_victory_while_yellow_holds_land(self, game, tale):
        tale.notify_event('territory_conquered', territory='Velene', new_owner=PLAYER)
        assert game.game_state.phase == 'playing'
        assert not tale._victory_waiting


# ============================================================================
# SAVE / RESTORE
# ============================================================================

class TestSaveRestore:

    def test_round_trip_through_json(self, game, tale):
        tale.popularity, tale.popularity_decay, tale.invest_cost = 62, 10, 130
        tale._last_decay_turn = 4
        tale.faction_turns = {YELLOW: 5, GREEN: 5, RED: 4}
        tale.hostile = {GREEN: True, RED: False}
        data = json.loads(json.dumps(tale.get_save_state()))   # Save files are JSON

        restored = _new_tale(game, seed=1)
        restored.restore_save_state(data)
        assert (restored.popularity, restored.popularity_decay, restored.invest_cost) == (62, 10, 130)
        assert restored._last_decay_turn == 4
        assert restored.faction_turns == {YELLOW: 5, GREEN: 5, RED: 4}
        assert restored.hostile == {GREEN: True, RED: False}
        assert restored._display_popularity == 62            # No drain animation on load
        assert restored.camera_animation is None

    def test_save_label(self):
        import save_manager
        assert save_manager._MISSION_TEXTS['tale_1'] == 'Tale: Lack of Funds'


# ============================================================================
# BOOK OF TALES
# ============================================================================

class TestBookOfTales:

    def test_tale_1_is_listed(self):
        import book_of_tales
        tale = next(t for t in book_of_tales.SCENARIOS if t['id'] == 'tale_1')
        assert tale['name'] == 'Lack of Funds' and not tale.get('hidden')

    def test_wrap_text_markup(self):
        from book_of_tales import BookOfTales
        pygame.font.init()
        font = pygame.font.Font(None, 20)
        text = "First paragraph.\n\n_Objectives:\n- a list item long enough to wrap onto a second line here"
        lines = BookOfTales._wrap_text(text, font, 200, font)
        assert lines[0] == ('First paragraph.', False, 0)
        assert lines[1] == ('', False, 0)                         # '\n\n' -> empty line
        assert lines[2] == ('Objectives:', True, 0)               # '_' -> underlined, stripped
        assert lines[3][0].startswith('- ') and lines[3][2] == 0  # Item's first line flush
        assert len(lines) > 4 and lines[4][2] == font.size('- ')[0]  # Continuation hangs

    def test_launch_returns_scenario_id(self, game):
        from book_of_tales import BookOfTales
        screen_obj = BookOfTales(game.screen)
        screen_obj._launch_selected()            # Nothing selected: stays open
        assert screen_obj.result is None and not screen_obj.done
        screen_obj._select_tale(0)
        screen_obj._launch_selected()
        assert screen_obj.result == {'action': 'launch', 'scenario_id': 'tale_1'}
        assert screen_obj.done
