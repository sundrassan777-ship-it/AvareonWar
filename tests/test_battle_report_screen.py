# -*- coding: utf-8 -*-
"""
The battle report screen (Phase 2 of the battle screen modernization, owner 2026-10-28).

The report was VICTORY / DEFEAT and the viewer's losses in plain white lines. It now
shows what happened to the territory (captured / held / lost), the viewer's army as a
table (fought / lost / survived), and the outcome: the Keep (or Castle), the other
buildings, the heroes slain there, and the XP and level-ups the viewer's survivors
gained.

- GameState.battle_outcome() gathers it for the resolver's window; the defender's stored
  Battle Report carries the same keys (JSON-safe: it rides on BATTLE_RESOLVE).
- ui/battle_screen_panels.py words it (report_view) and composes it once.
- The report panel is sized to the report, between 55% and 80% of the screen height.
"""

import json
import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from config.font_manager import FontManager  # noqa: E402
from game_state import Battle, GameState  # noqa: E402
from ui.battle_screen_panels import report_view  # noqa: E402
from ui.effects.battle_interface import (  # noqa: E402
    BattleInterfaceState, EnhancedBattleInterface,
    REPORT_PANEL_MAX_HEIGHT_RATIO, REPORT_PANEL_MIN_HEIGHT_RATIO)

HERO = 'Halon Nextroy'


def new_state():
    gs = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                   skip_setup_phase=True)
    gs.current_player = 0
    return gs


def fight(gs, owner_units, attacker_units, buildings=None, keep_bonus=0, hero=False,
          castle=False):
    """
    Player 0 defends a territory (garrison + buildings), player 1 attacks; resolved.
    Returns (territory, battle).
    """
    _, territory, _ = h.adjacent_triple()
    h.place(gs, territory, 0, owner_units, buildings=buildings or {})
    if hero:
        gs.heroes.setdefault(0, {})[HERO] = {'keep_territory': territory, 'keep_plot': 0}
        gs.hero_ownership[0].add(HERO)
    if castle:
        gs.castle_upgrades[territory] = {0: True}
    gs.territory_garrisons[territory][1] = {
        'unmoved': 0, 'moved': len(attacker_units), 'units': attacker_units}
    battle = Battle(territory)
    battle.original_owner = 0
    if owner_units:
        battle.add_army(0, len(owner_units), _composition(owner_units))
    battle.add_army(1, len(attacker_units), _composition(attacker_units))
    if keep_bonus:
        battle.keep_bonus = keep_bonus
        battle.keep_bonus_player = 0
        battle.original_garrison = len(owner_units)
    gs.pending_battles = [battle]
    assert gs.resolve_battle(0)
    return territory, battle


def _composition(units):
    result = {}
    for unit in units:
        result[unit['type']] = result.get(unit['type'], 0) + 1
    return result


# ============================================================================
# WHAT THE BATTLE DID (GameState.battle_outcome)
# ============================================================================

class TestBattleOutcome:

    def test_a_captured_keep_with_its_hero(self):
        gs = new_state()
        territory, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12),
                                  buildings={0: 'Keep', 1: 'Farm'}, hero=True)
        outcome = gs.battle_outcome(battle, 1)
        assert outcome['previous_owner'] == 0
        assert outcome['holder'] == 1
        assert outcome['held'] is False
        assert (outcome['keep'], outcome['keep_name']) == ('destroyed', 'Keep')
        assert outcome['structures_destroyed'] == 2
        assert outcome['heroes_slain'] == [[0, HERO]]

    def test_the_winners_xp_and_level_ups(self):
        gs = new_state()
        territory, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12),
                                  buildings={0: 'Keep'}, hero=True)
        outcome = gs.battle_outcome(battle, 1)
        # 1 kill (10 XP) + a Hero Keep destroyed (100): every survivor goes 0 -> level 2
        assert outcome['xp_per_unit'] == gs.BATTLE_XP_PER_KILL + gs.HERO_KEEP_DESTROY_XP
        survivors = gs.territory_garrisons[territory][1]['units']
        assert outcome['level_ups'] == [['Swordsman', 2, len(survivors)]]
        assert all(unit['level'] == 2 for unit in survivors)

    def test_the_loser_gains_no_xp(self):
        gs = new_state()
        _, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12))
        outcome = gs.battle_outcome(battle, 0)
        assert (outcome['xp_per_unit'], outcome['level_ups']) == (0, [])

    def test_a_held_keep(self):
        gs = new_state()
        _, battle = fight(gs, h.units(*['Archer'] * 6), h.units('Swordsman'),
                          buildings={0: 'Keep'}, keep_bonus=2)
        outcome = gs.battle_outcome(battle, 0)
        assert outcome['held'] is True and outcome['holder'] == 0
        assert outcome['keep'] == 'held'
        assert outcome['xp_per_unit'] > 0                 # the defenders won

    def test_a_castle_is_named(self):
        gs = new_state()
        _, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12),
                          buildings={0: 'Keep'}, castle=True)
        assert gs.battle_outcome(battle, 1)['keep_name'] == 'Castle'

    def test_the_buildings_by_type(self):
        gs = new_state()
        _, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12),
                          buildings={0: 'Keep', 1: 'Farm', 2: 'Barracks', 3: 'Farm'})
        outcome = gs.battle_outcome(battle, 1)
        assert outcome['buildings_destroyed'] == {'Farm': 2, 'Barracks': 1}   # the Keep has its own line
        assert outcome['buildings_captured'] == {}

    def test_saved_buildings_are_captured(self):
        """Champion of the People keeps Farms and Mines for the winner."""
        gs = new_state()
        _, territory, _ = h.adjacent_triple()
        before = {0: 'Keep', 1: 'Farm', 2: 'Mine', 3: 'Barracks', 4: None}
        gs.buildings[territory] = {1: 'Farm', 2: 'Mine'}
        assert gs._battle_building_changes(before, territory, held=False) == (
            {'Barracks': 1}, {'Farm': 1, 'Mine': 1})
        gs.buildings[territory] = dict(before)
        assert gs._battle_building_changes(before, territory, held=True) == ({}, {})

    def test_no_keep(self):
        gs = new_state()
        _, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12))
        assert gs.battle_outcome(battle, 1)['keep'] is None

    def test_json_safe(self):
        gs = new_state()
        _, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12),
                          buildings={0: 'Keep'}, hero=True)
        outcome = gs.battle_outcome(battle, 1)
        assert json.loads(json.dumps(outcome)) == outcome

    def test_the_heroes_stay_with_their_battle(self):
        """_battle_hero_deaths is reset by the next battle; the outcome keeps its own."""
        gs = new_state()
        _, battle = fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12),
                          buildings={0: 'Keep'}, hero=True)
        gs._battle_hero_deaths = []
        assert gs.battle_outcome(battle, 1)['heroes_slain'] == [[0, HERO]]


class TestTheStoredReport:
    """The defender's Battle Report (opened later on the detail screen) has the same keys."""

    def test_a_lost_keep(self):
        gs = new_state()
        fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12), buildings={0: 'Keep'})
        report = gs.last_battle_reports[0]
        assert (report['keep'], report['keep_name']) == ('destroyed', 'Keep')
        assert (report['xp_per_unit'], report['level_ups']) == (0, [])
        assert (report['buildings_destroyed'], report['buildings_captured']) == ({}, {})
        assert json.loads(json.dumps(report)) == report

    def test_a_held_keep_with_xp(self):
        gs = new_state()
        fight(gs, h.units(*['Archer'] * 6), h.units('Swordsman'), buildings={0: 'Keep'},
              keep_bonus=2)
        report = gs.last_battle_reports[0]
        assert report['held'] and report['keep'] == 'held'
        assert report['xp_per_unit'] > 0

    def test_an_uncontested_capture_names_its_keep(self):
        gs = new_state()
        _, territory, _ = h.adjacent_triple()
        h.place(gs, territory, 0, buildings={0: 'Keep', 1: 'Barracks'})
        before = dict(gs.buildings[territory])
        gs.destroy_buildings(territory, 0, new_owner=1)
        gs._capture_uncontested_report(territory, 0, 1, before)
        report = gs.last_battle_reports[-1]
        assert report['keep'] == 'destroyed'
        assert report['buildings_destroyed'] == {'Barracks': 1}


# ============================================================================
# THE WORDS (report_view)
# ============================================================================

class TestTheStrengths:
    """The preview hides both strengths (owner, 2026-10-29); the report shows them."""

    def test_taken_quietly_before_the_fight(self):
        gs = new_state()
        _, territory, _ = h.adjacent_triple()
        h.place(gs, territory, 0, h.units('Archer', 'Archer'), buildings={0: 'Keep'})
        gs.territory_garrisons[territory][1] = {'unmoved': 0, 'moved': 5,
                                                'units': h.units(*['Cavalry'] * 5)}
        battle = Battle(territory)
        battle.original_owner = 0
        battle.add_army(0, 2, {'Archer': 2})
        battle.add_army(1, 5, {'Cavalry': 5})
        battle.keep_bonus, battle.keep_bonus_player = 2, 0
        messages = len(gs.messages)
        shown = gs._shown_strengths(battle)
        assert len(gs.messages) == messages                   # no log lines
        assert shown[1] == gs.calculate_army_effective_strength(
            {'Cavalry': 5}, {'Archer': 2}, 1, territory,
            unit_avg_levels=gs.get_unit_avg_levels(territory, 1))
        assert shown[0] == pytest.approx(gs.calculate_army_effective_strength(
            {'Archer': 2}, {'Cavalry': 5}, 0, territory,
            unit_avg_levels=gs.get_unit_avg_levels(territory, 0)) + 2)

    def test_the_stored_report_has_both(self):
        gs = new_state()
        fight(gs, h.units('Swordsman'), h.units(*['Swordsman'] * 12), buildings={0: 'Keep'},
              keep_bonus=2)
        report = gs.last_battle_reports[0]
        assert report['attacker_strength'] == pytest.approx(12.0)
        assert report['defender_strength'] == pytest.approx(1.0 + 2)    # the Keep's +2
        assert json.loads(json.dumps(report)) == report

    def test_the_report_shows_the_viewers_first(self):
        view = report_view("Nefrid", True, BREAKDOWN, _outcome(), _ours, strengths=(8.4, 5.0))
        assert view['strengths'] == (8.4, 5.0)
        assert report_view("Nefrid", True, BREAKDOWN, _outcome(), _ours)['strengths'] is None


def _ours(player):
    return player == 0


BREAKDOWN = {'Swordsman': {'original': 4, 'survived': 3, 'lost': 1},
             'Archer': {'original': 2, 'survived': 2, 'lost': 0}}


def _outcome(**overrides):
    outcome = {'previous_owner': 1, 'holder': 0, 'held': False, 'keep': None,
               'keep_name': None, 'structures_destroyed': 0, 'structures_captured': 0,
               'heroes_slain': [], 'xp_per_unit': 0, 'level_ups': []}
    outcome.update(overrides)
    return outcome


def _texts(view):
    return [text for _icon, _style, text, _tone in view['lines']]


class TestReportView:

    @pytest.mark.parametrize('won, outcome, result, headline', [
        (True, _outcome(), 'victory', "Nefrid captured"),
        (True, _outcome(previous_owner=0, holder=0, held=True), 'victory', "Nefrid held"),
        (False, _outcome(previous_owner=0, holder=1), 'defeat', "Nefrid lost"),
        (False, _outcome(holder=1, held=True), 'defeat', "Repelled at Nefrid"),
        (None, _outcome(holder=-1), 'no_victor', "Both armies fell at Nefrid"),
        (True, {}, 'victory', "Nefrid"),                       # no outcome: just the name
    ])
    def test_the_headline(self, won, outcome, result, headline):
        view = report_view("Nefrid", won, BREAKDOWN, outcome, _ours)
        assert (view['result'], view['headline']) == (result, headline)

    def test_the_army_rows(self):
        view = report_view("Nefrid", True, BREAKDOWN, _outcome(), _ours)
        assert view['units'] == [('Archer', 2, 0, 2), ('Swordsman', 4, 1, 3)]

    def test_each_building_type_with_its_icon(self):
        """Owner, 2026-10-29: show which buildings fell, not an empty plot and a count."""
        view = report_view("Nefrid", True, BREAKDOWN, _outcome(
            keep='destroyed', keep_name='Castle',
            buildings_destroyed={'Farm': 1, 'Barracks': 2, 'Training Grounds': 1},
            buildings_captured={'Mine': 1}), _ours)
        assert _texts(view) == ["Castle destroyed", "2 Barracks destroyed", "Farm destroyed",
                                "Training Grounds destroyed", "Mine captured"]
        icons = [icon for icon, _style, _text, _tone in view['lines']]
        assert icons[1:] == ['assets/mapicons/BarracksIcon.png', 'assets/mapicons/FarmIcon.png',
                             'assets/mapicons/TrainingGroundsIcon.png', 'assets/mapicons/MineIcon.png']

    def test_an_older_report_counts_its_buildings(self):
        """No buildings by type (a report from before 2026-10-29): a fallen Keep counted once."""
        view = report_view("Nefrid", True, BREAKDOWN, _outcome(
            keep='destroyed', keep_name='Castle', structures_destroyed=3, structures_captured=1),
            _ours)
        assert _texts(view) == ["Castle destroyed", "2 buildings destroyed", "1 building captured"]

    def test_our_losses_read_as_losses(self):
        view = report_view("Nefrid", False, BREAKDOWN, _outcome(
            previous_owner=0, holder=1, keep='destroyed', keep_name='Keep',
            buildings_destroyed={}, buildings_captured={'Farm': 2}, heroes_slain=[[0, HERO]]),
            _ours)
        assert _texts(view) == ["Keep destroyed", "2 Farms taken by the enemy",
                                f"Hero slain: {HERO}"]
        assert {tone for _i, _s, _t, tone in view['lines']} == {'bad'}

    def test_an_enemy_hero(self):
        view = report_view("Nefrid", True, BREAKDOWN, _outcome(heroes_slain=[[1, HERO]]), _ours)
        assert _texts(view) == [f"Enemy hero slain: {HERO}"]
        assert view['lines'][0][1] == 'framed'

    def test_xp_and_level_ups(self):
        """Owner, 2026-10-29: the level-up line had no icon - one line per unit, its portrait."""
        view = report_view("Nefrid", True, BREAKDOWN, _outcome(
            xp_per_unit=30, level_ups=[['Archer', 2, 2], ['Swordsman', 3, 1]]), _ours)
        assert _texts(view) == ["+30 XP for each survivor", "2 Archers reached level 2",
                                "1 Swordsman reached level 3"]
        assert [(icon, style) for icon, style, _text, _tone in view['lines'][1:]] == [
            ('assets/mapicons/ArcherIcon.png', 'framed'),
            ('assets/mapicons/SwordsmanIcon.png', 'framed')]
        assert all(icon for icon, _style, _text, _tone in view['lines'])

    def test_the_held_keep_of_an_attack_that_failed(self):
        view = report_view("Nefrid", False, BREAKDOWN, _outcome(
            holder=1, held=True, keep='held', keep_name='Keep'), _ours)
        assert view['lines'][0][2:] == ("Keep held", 'bad')


# ============================================================================
# THE SCREEN
# ============================================================================

@pytest.fixture(scope='module')
def screen():
    pygame.init()
    surface = pygame.display.set_mode((1600, 900))
    yield surface
    pygame.quit()


def _battle_window(screen):
    """The resolver's window over a battle player 0 wins, ready to Resolve."""
    gs = new_state()
    _, territory, _ = h.adjacent_triple()
    h.place(gs, territory, 1, h.units('Swordsman'), buildings={0: 'Keep'})
    gs.territory_garrisons[territory][0] = {'unmoved': 0, 'moved': 6,
                                            'units': h.units(*['Swordsman'] * 6)}
    battle = Battle(territory)
    battle.original_owner = 1
    battle.add_army(1, 1, {'Swordsman': 1})
    battle.add_army(0, 6, {'Swordsman': 6})
    gs.pending_battles = [battle]
    ui = EnhancedBattleInterface(screen=screen, game_state=gs, battle_index=0,
                                 font_manager=FontManager(), current_player_index=0)
    return ui, gs, battle


def _fight_it(ui, gs, battle, with_outcome=True):
    """Resolve as main.py does: the real battle, then the real result into the window."""
    ui.handle_click(ui.resolve_button_rect.center)
    gs.resolve_battle(0)
    survivors = gs.territory_garrisons[battle.territory][0]['units']
    ui.set_actual_battle_result(0, len(survivors), 0, survivors,
                                outcome=gs.battle_outcome(battle, 0) if with_outcome else None)
    ui.skip_animation()
    ui.update(1.0 / 60.0)
    assert ui.state == BattleInterfaceState.SPLASH


def _report_height(ui):
    header, body = ui._report_parts
    return header.get_height() + body.get_height()


class TestReportScreen:

    def test_composed_once_at_the_splash(self, screen):
        ui, gs, battle = _battle_window(screen)
        _fight_it(ui, gs, battle)
        composed = ui._report_parts
        assert composed is not None                        # before the report shows
        ui._start_report()
        for _ in range(3):
            ui.render()
        assert ui._report_parts is composed

    def test_the_outcome_makes_it_longer(self, screen):
        ui, gs, battle = _battle_window(screen)
        _fight_it(ui, gs, battle)
        plain, gs2, battle2 = _battle_window(screen)
        _fight_it(plain, gs2, battle2, with_outcome=False)
        assert _report_height(ui) > _report_height(plain)

    def test_the_panel_fits_its_report(self, screen):
        ui, gs, battle = _battle_window(screen)
        _fight_it(ui, gs, battle)
        panel, content, close = ui.report_panel_rect, ui.report_content_rect, ui.close_button_rect
        assert (REPORT_PANEL_MIN_HEIGHT_RATIO * 900 - 1 <= panel.height
                <= REPORT_PANEL_MAX_HEIGHT_RATIO * 900 + 1)
        assert panel.contains(content)
        assert ui._report_scroller.max_offset == 0
        assert _report_height(ui) <= content.height
        assert max(part.get_width() for part in ui._report_parts) < content.width   # + scrollbar gutter
        assert close.top > content.bottom - 1
        assert screen.get_rect().contains(close)

    @pytest.mark.parametrize('size', [(1280, 720), (2560, 1440)])
    def test_every_resolution(self, screen, size):
        ui, gs, battle = _battle_window(pygame.Surface(size))
        _fight_it(ui, gs, battle)
        ui._start_report()
        ui.render()
        assert ui.screen.get_rect().contains(ui.close_button_rect)
        assert _report_height(ui) <= ui.report_content_rect.height

    def test_an_older_stored_report_still_opens(self, screen):
        """A report from before keep / xp_per_unit / level_ups: no outcome lines for them."""
        gs = new_state()
        report = {'territory': h.adjacent_triple()[1], 'turn_number': 3, 'defender': 0,
                  'attacker': 1, 'held': False, 'units_lost': 2, 'units_remaining': 0,
                  'structures_destroyed': 1, 'structures_captured': 0,
                  'structures_remaining': 0,
                  'unit_breakdown': {'Swordsman': {'original': 2, 'survived': 0, 'lost': 2}},
                  'defender_lost': 2, 'defender_survivors': 0, 'attacker_lost': 1,
                  'attacker_survivors': 4, 'heroes_slain': []}
        ui = EnhancedBattleInterface(screen=screen, game_state=gs, battle_index=0,
                                     font_manager=FontManager(), current_player_index=0,
                                     report_snapshot=report)
        assert ui.state == BattleInterfaceState.REPORT
        assert ui._report_parts is not None                # sized before any click
        assert ui._report_strengths() is None              # no strengths in it: no line
        ui.render()
        assert ui.handle_click(ui.close_button_rect.center) == 'close'

    def test_the_live_report_has_both_strengths(self, screen):
        ui, gs, battle = _battle_window(screen)                # player 0 attacks
        _fight_it(ui, gs, battle)
        assert ui._report_strengths() == (ui.attacker_strength, ui.defender_strength)

    def test_a_stored_report_shows_the_defenders_side_first(self, screen):
        gs = new_state()
        report = {'territory': h.adjacent_triple()[1], 'turn_number': 3, 'defender': 0,
                  'attacker': 1, 'held': True, 'units_lost': 0, 'units_remaining': 2,
                  'structures_destroyed': 0, 'structures_captured': 0, 'structures_remaining': 0,
                  'unit_breakdown': {'Archer': {'original': 2, 'survived': 2, 'lost': 0}},
                  'defender_lost': 0, 'defender_survivors': 2, 'attacker_lost': 3,
                  'attacker_survivors': 0, 'heroes_slain': [],
                  'attacker_strength': 3.0, 'defender_strength': 4.5}
        ui = EnhancedBattleInterface(screen=screen, game_state=gs, battle_index=0,
                                     font_manager=FontManager(), current_player_index=0,
                                     report_snapshot=report)
        assert ui._report_strengths() == (4.5, 3.0)


# A report too long for the largest panel: every building type, heroes, level-ups
LONG_OUTCOME = {
    'previous_owner': 1, 'holder': 0, 'held': False, 'keep': 'destroyed', 'keep_name': 'Castle',
    'structures_destroyed': 6, 'structures_captured': 3,
    'buildings_destroyed': {'Barracks': 2, 'Training Grounds': 1, 'Square': 1, 'Farm': 1},
    'buildings_captured': {'Farm': 2, 'Mine': 1},
    'heroes_slain': [[1, HERO], [1, 'Darius Brennhen']], 'xp_per_unit': 140,
    'level_ups': [['Archer', 2, 2], ['Captain', 3, 1], ['Pikeman', 2, 2], ['Swordsman', 3, 1]]}
LONG_ARMY = {unit_type: {'original': 3, 'survived': 2, 'lost': 1}
             for unit_type in ('Archer', 'Captain', 'Cavalry', 'Pikeman', 'Swordsman')}


def _long_report(screen):
    """The report screen over LONG_OUTCOME (the viewer won with all five unit types)."""
    ui, gs, battle = _battle_window(screen)
    _fight_it(ui, gs, battle)
    ui.battle_result['unit_breakdown'] = LONG_ARMY
    ui.outcome = LONG_OUTCOME
    ui._prepare_report()
    ui._start_report()
    return ui


class TestScrolling:
    """Owner, 2026-10-29: a long report needs the mouse wheel."""

    def test_a_long_report_scrolls_in_the_largest_panel(self, screen):
        ui = _long_report(screen)
        assert ui._report_scroller.max_offset > 0
        assert ui.report_panel_rect.height == int(900 * REPORT_PANEL_MAX_HEIGHT_RATIO)

    def test_the_wheel_scrolls_within_bounds(self, screen):
        ui = _long_report(screen)
        assert ui.handle_wheel(1) is False                 # already at the top
        assert ui.handle_wheel(-1) is True
        assert ui._report_scroller.offset > 0
        ui.handle_wheel(-999)
        assert ui._report_scroller.offset == ui._report_scroller.max_offset
        assert ui.handle_wheel(-1) is False                # at the end
        ui.handle_wheel(999)
        assert ui._report_scroller.offset == 0

    def test_the_header_stays_put(self, screen):
        ui = _long_report(screen)
        header = pygame.Rect(ui.report_content_rect.topleft,
                             (ui.report_content_rect.width, ui._report_parts[0].get_height()))
        screen.fill((0, 0, 0))
        ui.render()
        before = pygame.image.tobytes(screen.subsurface(header), 'RGB')
        body = pygame.Rect(header.left, header.bottom, header.width, 60)
        body_before = pygame.image.tobytes(screen.subsurface(body), 'RGB')
        ui.handle_wheel(-2)
        screen.fill((0, 0, 0))
        ui.render()
        assert pygame.image.tobytes(screen.subsurface(header), 'RGB') == before
        assert pygame.image.tobytes(screen.subsurface(body), 'RGB') != body_before

    def test_scrolling_builds_nothing_per_frame(self, screen):
        ui = _long_report(screen)
        ui.render()
        scratch = ui._report_scroller._scratch
        for step in (-1, -1, 1, -999):
            ui.handle_wheel(step)
            ui.render()
        assert ui._report_scroller._scratch is scratch
        assert len(ui._report_scroller._masks) <= 3                  # top / bottom / both faded

    def test_a_short_report_does_not_scroll(self, screen):
        ui, gs, battle = _battle_window(screen)
        _fight_it(ui, gs, battle)
        ui._start_report()
        assert ui.handle_wheel(-1) is False
        assert ui._report_scroller.offset == 0

    def test_only_the_report_scrolls(self, screen):
        ui, gs, battle = _battle_window(screen)
        assert ui.handle_wheel(-1) is False                # setup


# ============================================================================
# NO HITCH ON THE FIRST REPORT (prewarm_battle_screen)
# ============================================================================

class TestPrewarm:
    """
    Every icon is a 1024 px image: decoded as the first report's splash began, they cost
    ~130 ms. The loading screen bakes them first, from the images the game has loaded.
    """

    def test_the_first_report_reads_no_file(self, screen, monkeypatch):
        from ui import battle_screen_kit
        from ui.battle_screen_panels import report_icons
        from ui.effects.battle_interface import prewarm_battle_screen
        battle_screen_kit._shared.clear()
        sources = {path: pygame.Surface((64, 64), pygame.SRCALPHA) for path, _style in report_icons()}
        prewarm_battle_screen(screen.get_size(), sources)
        ui, gs, battle = _battle_window(screen)
        loads = []
        real_load = pygame.image.load
        monkeypatch.setattr(pygame.image, 'load',
                            lambda *args, **kwargs: loads.append(args) or real_load(*args, **kwargs))
        _fight_it(ui, gs, battle)                          # the report is composed here
        ui._start_report()
        ui.render()
        assert loads == []

    def test_the_game_hands_over_every_report_icon(self, real_game):
        from ui.battle_screen_panels import report_icons
        sources = real_game._battle_screen_icon_sources()
        assert {path for path, _style in report_icons()} <= set(sources)


@pytest.fixture(scope='module')
def real_game(screen):
    """A real Game (only the last tests use it: Game() opens its own display)."""
    from main import Game
    game = Game()
    game.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                          'player_ai_difficulty': [1, 1]})
    return game


class TestTheWheelGoesToTheBattleWindow:
    """The wheel scrolls a battle window's report; the map behind it no longer zooms."""

    def test_routing(self, real_game):
        from unittest import mock
        game = real_game
        game.enhanced_battle_ui = game.battle_report_detail_ui = None
        game.game_menu_visible = game.options_menu_visible = game.save_dialog_active = False
        assert game._battle_window_wheel(-1) is False          # no window: the camera zooms
        window, detail = mock.Mock(), mock.Mock()
        game.enhanced_battle_ui = window
        assert game._battle_window_wheel(-1) is True
        window.handle_wheel.assert_called_once_with(-1)
        game.battle_report_detail_ui = detail                  # drawn on top of the battle screen
        game._battle_window_wheel(1)
        detail.handle_wheel.assert_called_once_with(1)
        game.options_menu_visible = True                       # a menu above takes the wheel
        assert game._battle_window_wheel(-1) is False
        game.enhanced_battle_ui = game.battle_report_detail_ui = None
        game.options_menu_visible = False
