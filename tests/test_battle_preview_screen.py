# -*- coding: utf-8 -*-
"""
The battle preview (Phase 3 of the battle screen modernization, owner 2026-10-29).

Each side showed one opaque "Effective Strength" number in plain white lines. It now
shows the player (flag, name in their colour), a row per unit type ("2 x Archer", tagged
Advantage / Disadvantage where it counters the enemy or is countered) and a row per
bonus behind the strength, each with its icon - scrolling with the mouse wheel when they
outgrow the panel. The strength is not shown (an informed mystery): both bars start full,
the fight and then the report reveal it. A banner names the battle and the turn.

- GameState.calculate_army_effective_strength(breakdown=) lists the factors it applied;
  the strength itself is exactly the same with or without the list.
- ui/battle_screen_panels.py words the rows (bonus_lines, unit_rows) and composes each
  side once (compose_side_header / compose_side_body) and the banner.
"""

import os
import sys
from itertools import product

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import map_data  # noqa: E402
import mp_harness as h  # noqa: E402
from config.constants import PLAYER_COLORS  # noqa: E402
from config.font_manager import FontManager  # noqa: E402
from game_state import Battle, GameState  # noqa: E402
from ui.battle_screen_panels import (  # noqa: E402
    bonus_lines, flag_icon, readable, side_view, unit_rows)
from ui.effects.battle_interface import BattleInterfaceState, EnhancedBattleInterface  # noqa: E402


def new_state():
    return GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[1, 1],
                     skip_setup_phase=True)


def all_bonuses(gs, player=0, territory=None):
    """Every bonus the rule knows, on for `player` (territory: a friendly Keep there)."""
    gs.player_cavalry_strength_bonus[player] = 33
    gs.player_divide_conquer_bonus[player] = True
    gs.player_archer_keep_strength_bonus[player] = 50
    gs.player_has_hevilneu = lambda p: p == player
    gs.calculate_player_territorial_bonuses = (
        lambda p: {'archer_str': 10, 'pikeman_str': 20, 'swordsman_str': 10, 'cavalry_str': 30}
        if p == player else {})
    if territory is not None:
        gs.territory_owners[territory] = player
        gs.buildings[territory] = {0: 'Keep'}


# ============================================================================
# THE STRENGTH AND ITS BREAKDOWN (calculate_army_effective_strength)
# ============================================================================

UNIT_TYPES = ('Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain')
MIXES = [
    {'Swordsman': 3},
    {'Archer': 2, 'Cavalry': 1},
    {'Swordsman': 4, 'Cavalry': 3, 'Archer': 2, 'Captain': 1},
    {'Pikeman': 5, 'Archer': 3},
    {'Captain': 2},
]


class TestTheStrengthIsUnchanged:
    """The breakdown only records: the strength is bit-identical with or without it."""

    @pytest.mark.parametrize('army, enemy', list(product(MIXES, MIXES)))
    @pytest.mark.parametrize('bonuses', [False, True])
    def test_with_and_without_the_breakdown(self, army, enemy, bonuses):
        gs = new_state()
        territory = h.spread_territories(2)[0]
        if bonuses:
            all_bonuses(gs, 0, territory)
        levels = {'Swordsman': 1.5, 'Cavalry': 2.0} if bonuses else None
        plain = gs.calculate_army_effective_strength(army, enemy, 0, territory,
                                                     unit_avg_levels=levels)
        breakdown = []
        noted = gs.calculate_army_effective_strength(army, enemy, 0, territory,
                                                     unit_avg_levels=levels, breakdown=breakdown)
        assert noted == plain
        if bonuses and set(army) != {'Captain'}:           # (no bonus reaches Captains)
            assert breakdown


class TestTheBreakdown:

    def _breakdown(self, army, enemy, levels=None):
        gs = new_state()
        territory = h.spread_territories(2)[0]
        all_bonuses(gs, 0, territory)
        breakdown = []
        gs.calculate_army_effective_strength(army, enemy, 0, territory, unit_avg_levels=levels,
                                             breakdown=breakdown)
        return breakdown

    def test_every_bonus_is_listed(self):
        breakdown = self._breakdown({'Swordsman': 2, 'Archer': 2, 'Cavalry': 1, 'Captain': 1},
                                    {'Pikeman': 3}, levels={'Archer': 1.0})
        keys = {entry['key'] for entry in breakdown}
        assert keys >= {'vanquish', 'cavalry_tactics', 'battlement_archery', 'divide_and_conquer',
                        'territorial', 'veterancy', 'captain', 'matchup'}

    def test_each_entry_names_its_unit_type_and_amount(self):
        breakdown = self._breakdown({'Cavalry': 2}, {'Archer': 2}, levels={'Cavalry': 2.0})
        by_key = {entry['key']: entry for entry in breakdown}
        assert by_key['cavalry_tactics']['pct'] == 33
        assert by_key['veterancy']['pct'] == pytest.approx(30.0)      # 2 levels x 15%
        assert by_key['territorial']['pct'] == 30
        assert {entry['unit_type'] for entry in breakdown} == {'Cavalry'}

    def test_a_counter_matchup(self):
        gs = new_state()
        breakdown = []
        gs.calculate_army_effective_strength({'Swordsman': 2}, {'Archer': 2}, breakdown=breakdown)
        matchup = [entry for entry in breakdown if entry['key'] == 'matchup']
        assert matchup and matchup[0]['unit_type'] == 'Swordsman'
        assert matchup[0]['factor'] == gs.calculate_unit_effectiveness('Swordsman', {'Archer': 2})

    def test_nothing_when_nothing_applies(self):
        gs = new_state()
        breakdown = []
        gs.calculate_army_effective_strength({'Swordsman': 2}, {'Swordsman': 2}, 0,
                                             breakdown=breakdown)
        assert breakdown == []


# ============================================================================
# THE WORDS (bonus_lines, unit_rows, flags, colours)
# ============================================================================

def _entry(key, label, unit_type, pct):
    return {'key': key, 'label': label, 'unit_type': unit_type, 'pct': pct}


class TestBonusLines:

    def test_a_bonus_for_the_whole_army_names_no_unit(self):
        lines = bonus_lines([_entry('vanquish', 'Vanquish the Enemy', 'Archer', 20),
                             _entry('vanquish', 'Vanquish the Enemy', 'Pikeman', 20)],
                            {'Archer': 2, 'Pikeman': 1})
        assert lines == [('vanquish', '+20%', 'Vanquish the Enemy', [])]

    def test_a_bonus_for_some_units_shows_them(self):
        lines = bonus_lines([_entry('cavalry_tactics', 'Cavalry Tactics', 'Cavalry', 33)],
                            {'Cavalry': 1, 'Archer': 2})
        assert lines == [('cavalry_tactics', '+33%', 'Cavalry Tactics', ['Cavalry'])]

    def test_captains_do_not_count_as_left_out(self):
        lines = bonus_lines([_entry('vanquish', 'Vanquish the Enemy', 'Archer', 20),
                             _entry('captain', 'Captain', 'Archer', 12)],
                            {'Archer': 2, 'Captain': 1})
        assert lines == [('vanquish', '+20%', 'Vanquish the Enemy', []),
                         ('captain', '+12%', 'Captain', [])]

    def test_different_amounts_get_a_line_each(self):
        lines = bonus_lines([_entry('veterancy', 'Veterancy', 'Archer', 15),
                             _entry('veterancy', 'Veterancy', 'Cavalry', 30)],
                            {'Archer': 1, 'Cavalry': 1})
        assert lines == [('veterancy', '+30%', 'Veterancy', ['Cavalry']),
                         ('veterancy', '+15%', 'Veterancy', ['Archer'])]

    def test_the_order_and_the_keep(self):
        lines = bonus_lines([{'key': 'keep', 'label': 'Keep', 'flat': 2},
                             _entry('captain', 'Captain', 'Archer', 12),
                             _entry('vanquish', 'Vanquish the Enemy', 'Archer', 20)],
                            {'Archer': 1})
        assert [line[:3] for line in lines] == [('vanquish', '+20%', 'Vanquish the Enemy'),
                                                ('captain', '+12%', 'Captain'), ('keep', '+2', 'Keep')]

    def test_fractions(self):
        assert bonus_lines([_entry('veterancy', 'Veterancy', 'Archer', 22.5)], {'Archer': 1}) == [
            ('veterancy', '+22.5%', 'Veterancy', [])]

    def test_every_bonus_has_an_icon(self):
        from ui.battle_screen_panels import BONUS_ICONS, BONUS_ORDER
        assert set(BONUS_ORDER) == set(BONUS_ICONS)


class TestChipsFlagsColours:

    def test_marks(self):
        rows = unit_rows({'Swordsman': 2, 'Cavalry': 1, 'Archer': 3},
                           [{'key': 'matchup', 'unit_type': 'Swordsman', 'factor': 2.0},
                            {'key': 'matchup', 'unit_type': 'Cavalry', 'factor': 0.5},
                            {'key': 'matchup', 'unit_type': 'Archer', 'factor': 1.1}])
        assert rows == [('Archer', 3, None), ('Cavalry', 1, 'down'), ('Swordsman', 2, 'up')]

    def test_the_preview_shows_no_strength(self):
        """Owner, 2026-10-29: an informed mystery - the rows stay, the number goes."""
        view = side_view('Attacking', 'Red', 0, PLAYER_COLORS[0], {'Archer': 2}, [])
        assert 'strength' not in view

    def test_flags_follow_the_chosen_colour(self):
        assert flag_icon(0, PLAYER_COLORS[2]) == 'assets/mapicons/GreenFlag1.png'
        assert flag_icon(3, (12, 34, 56)) == 'assets/mapicons/YellowFlag1.png'   # by player
        assert flag_icon(-1, (150, 150, 150)) == 'assets/NeutralFlag.png'

    def test_a_dark_colour_is_lightened_for_its_name(self):
        for color in PLAYER_COLORS:                            # the game's own: unchanged
            assert readable(color) == tuple(color)
        light = readable((40, 60, 150))
        assert 0.299 * light[0] + 0.587 * light[1] + 0.114 * light[2] >= 139
        assert light[2] > light[0]                                   # still blue


# ============================================================================
# THE WINDOW
# ============================================================================

@pytest.fixture(scope='module')
def screen():
    pygame.init()
    surface = pygame.display.set_mode((1600, 900))
    yield surface
    pygame.quit()


def _window(screen, defenders=1, keep=False, attackers=6):
    """Player 0 attacks player 1's territory (player 1 and allies 2, 3 defending)."""
    gs = GameState(num_players=4, player_is_ai=[False, True, True, True],
                   player_ai_difficulty=[1, 1, 1, 1], skip_setup_phase=True)
    gs.player_teams = [0, 1, 1, 1]
    gs.turn_number = 9
    _, territory, _ = h.adjacent_triple()
    h.place(gs, territory, 1, h.units('Pikeman', 'Archer'))
    battle = Battle(territory)
    battle.original_owner = 1
    battle.add_army(1, 2, {'Pikeman': 1, 'Archer': 1})
    battle.add_army(0, attackers, {'Swordsman': attackers})
    battle.allied_defenders = [2, 3][:defenders - 1]
    if keep:
        battle.keep_bonus = 2
        battle.keep_bonus_player = 1
    gs.pending_battles = [battle]
    ui = EnhancedBattleInterface(screen=screen, game_state=gs, battle_index=0,
                                 font_manager=FontManager(), current_player_index=0)
    return ui, gs, territory


class TestThePreview:

    def test_composed_once_as_the_window_opens(self, screen):
        ui, _gs, _territory = _window(screen)
        sides, banner = list(ui._sides), ui._banner
        for _ in range(3):
            ui.render()
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.3)
        ui.render()                                            # the fight shows the same
        assert ui._sides == sides and ui._banner is banner

    def test_both_bars_start_full(self, screen):
        """The strengths' ratio gave the winner away; the fight still ends on the result."""
        ui, _gs, _territory = _window(screen, attackers=12)
        assert ui.attacker_strength > ui.defender_strength
        assert ui.attacker_fill == ui.defender_fill == 1.0
        ui.handle_click(ui.resolve_button_rect.center)
        ui.set_actual_battle_result(ui.attacker_player, 9, 0, None)
        assert ui.attacker_final_fill == pytest.approx(9 / 12)
        assert ui.defender_final_fill == 0.0

    def test_the_defender_keeps_its_name_in_the_fight(self, screen):
        """The fight said "Defenders" where the preview said "3 Defenders"."""
        ui, _gs, _territory = _window(screen, defenders=3)
        assert ui._defender_title() == "3 Defenders"

    def test_the_keep_is_a_bonus(self, screen):
        with_keep, _gs, _territory = _window(screen, keep=True)
        without, _gs2, _territory2 = _window(screen)
        assert {'key': 'keep', 'label': 'Keep', 'flat': 2} in with_keep.defender_breakdown
        assert not [e for e in without.defender_breakdown if e['key'] == 'keep']
        # The strength shown includes it
        assert with_keep.defender_strength == pytest.approx(without.defender_strength + 2)

    def test_the_banner_uses_the_display_name(self, screen, monkeypatch):
        ui, gs, territory = _window(screen)
        monkeypatch.setitem(map_data.TERRITORY_DISPLAY_NAMES, territory, "Renamed Hold")
        ui._prepare_preview()
        renamed = ui._banner.get_width()
        monkeypatch.setitem(map_data.TERRITORY_DISPLAY_NAMES, territory, "X")
        ui._prepare_preview()
        assert renamed > ui._banner.get_width()

    def test_the_content_fits_inside_the_art(self, screen):
        ui, _gs, _territory = _window(screen)
        for panel, content, (header, rows) in zip(
                (ui.attacker_panel_rect, ui.defender_panel_rect),
                (ui.attacker_content_rect, ui.defender_content_rect), ui._sides):
            assert panel.contains(content)
            assert header.get_width() == content.width
            assert content.contains(rows.rect)
            assert rows.rect.top == content.top + header.get_height()

    @pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
    def test_every_resolution(self, screen, size):
        ui, _gs, _territory = _window(pygame.Surface(size))
        ui.render()
        # Just above the panels (owner, 2026-10-29), clear of the art's spear tips (~5.5%)
        banner, panel = ui._banner_rect(), ui.attacker_panel_rect
        assert banner.top >= 0
        assert panel.top < banner.bottom < panel.top + panel.height * 0.055
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.3)
        ui.render()
        assert ui.screen.get_rect().contains(ui.skip_button_rect)

    def test_opening_after_the_prewarm_reads_no_unit_icon(self, screen, monkeypatch):
        from ui import battle_screen_kit
        from ui.battle_screen_panels import report_icons
        from ui.effects.battle_interface import prewarm_battle_screen
        battle_screen_kit._shared.clear()
        sources = {path: pygame.Surface((64, 64), pygame.SRCALPHA) for path, _style in report_icons()}
        prewarm_battle_screen(screen.get_size(), sources)
        loads = []
        real_load = pygame.image.load
        monkeypatch.setattr(pygame.image, 'load',
                            lambda *args, **kwargs: loads.append(str(args[0])) or real_load(*args, **kwargs))
        _window(screen)
        assert not [path for path in loads if 'Icon.png' in path and 'Battle' not in path]


class TestScrollingTheSides:
    """Owner, 2026-10-29: every unit and bonus visible - the side under the cursor scrolls."""

    def _full_house(self, screen):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        import battle_fx_preview
        ui, _ = battle_fx_preview.open_battle(screen, 'full house', 'bright')
        return ui

    def test_the_full_house_lists_everything(self, screen):
        ui = self._full_house(screen)
        keys = {entry['key'] for entry in ui.defender_breakdown}
        assert keys >= {'vanquish', 'cavalry_tactics', 'battlement_archery', 'divide_and_conquer',
                        'territorial', 'veterancy', 'captain', 'keep'}
        assert set(ui.attacker_composition) == set(ui.defender_composition) == {
            'Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain'}
        for _header, rows in ui._sides:
            assert rows.scrollable                              # more than the panel holds
            assert rows.max_offset == rows.surface.get_height() - rows.rect.height

    def test_the_side_under_the_cursor_scrolls(self, screen):
        ui = self._full_house(screen)
        attacker, defender = (rows for _header, rows in ui._sides)
        ui.handle_mouse_motion(ui.defender_panel_rect.center)
        assert ui.handle_wheel(-1) is True
        assert defender.offset > 0 and attacker.offset == 0
        ui.handle_mouse_motion((5, 5))                          # off both panels
        assert ui.handle_wheel(-1) is False
        ui.handle_mouse_motion(ui.attacker_panel_rect.center)
        ui.handle_wheel(-999)
        assert attacker.offset == attacker.max_offset           # the last row in view

    def test_it_scrolls_in_the_fight_too(self, screen):
        ui = self._full_house(screen)
        ui.handle_click(ui.resolve_button_rect.center)
        ui.handle_mouse_motion(ui.attacker_panel_rect.center)
        assert ui.handle_wheel(-1) is True
        ui.render()

    def test_the_name_stays_put(self, screen):
        ui = self._full_house(screen)
        header, rows = ui._sides[0]
        top = pygame.Rect(ui.attacker_content_rect.topleft, header.get_size())
        screen.fill((0, 0, 0))
        ui.render()
        before = pygame.image.tobytes(screen.subsurface(top), 'RGB')
        ui.handle_mouse_motion(ui.attacker_panel_rect.center)
        ui.handle_wheel(-3)
        screen.fill((0, 0, 0))
        ui.render()
        assert pygame.image.tobytes(screen.subsurface(top), 'RGB') == before

    def test_a_short_side_does_not_scroll(self, screen):
        ui, _gs, _territory = _window(screen)
        ui.handle_mouse_motion(ui.attacker_panel_rect.center)
        assert ui.handle_wheel(-1) is False


# ============================================================================
# THE TAGS EXPLAINED (hovering Advantage / Disadvantage)
# ============================================================================

class TestTheTagsExplained:
    """Owner, 2026-10-29: hovering a tag says where it comes from - the counter system."""

    def test_the_breakdown_carries_what_a_matchup_is_made_of(self):
        gs = new_state()
        breakdown = []
        gs.calculate_army_effective_strength({'Cavalry': 2}, {'Archer': 4, 'Pikeman': 3, 'Swordsman': 6},
                                             breakdown=breakdown)
        entry = next(e for e in breakdown if e['key'] == 'matchup')
        assert (entry['counters'], entry['counters_count']) == ('Archer', 4)
        assert (entry['countered_by'], entry['countered_by_count']) == ('Pikeman', 3)
        assert entry['enemy_total'] == 13
        assert entry['factor'] == pytest.approx((2 * 4 + 0.5 * 3 + 6) / 13)

    def test_an_advantage_in_words(self):
        from ui.battle_screen_panels import matchup_tip
        title, lines = matchup_tip({'key': 'matchup', 'unit_type': 'Cavalry', 'factor': 1.19,
                                    'counters': 'Archer', 'counters_count': 4,
                                    'countered_by': 'Pikeman', 'countered_by_count': 3,
                                    'enemy_total': 13})
        assert title == "Advantage  ×1.19"
        assert lines == ["Cavalry counter Archers: ×2 against the enemy's 4.",
                         "Pikemen counter Cavalry: ×0.5 against the enemy's 3.",
                         "×1 against the other 6 units.",
                         "Over all 13 enemy units: ×1.19 strength."]

    def test_a_disadvantage_leaves_out_what_is_not_there(self):
        from ui.battle_screen_panels import matchup_tip
        title, lines = matchup_tip({'key': 'matchup', 'unit_type': 'Swordsman', 'factor': 0.5,
                                    'counters': 'Pikeman', 'counters_count': 0,
                                    'countered_by': 'Archer', 'countered_by_count': 5,
                                    'enemy_total': 5})
        assert title.startswith("Disadvantage")
        assert lines == ["Archers counter Swordsmen: ×0.5 against the enemy's 5.",
                         "Over all 5 enemy units: ×0.50 strength."]

    def _full_house(self, screen):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        import battle_fx_preview
        ui, _ = battle_fx_preview.open_battle(screen, 'full house', 'bright')
        return ui

    @staticmethod
    def _on_screen(ui, side, rect):
        rows = ui._sides[side][1]
        return (rows.rect.x + rect.centerx, rows.rect.y + rect.centery - rows.offset)

    def test_hovering_a_tag_explains_it(self, screen):
        ui = self._full_house(screen)
        tags, matchups = ui._side_tags[0]
        assert tags                                             # the attacker has tags
        for rect, unit_type in tags:
            entry = ui._matchup_at(self._on_screen(ui, 0, rect))
            assert entry is matchups[unit_type]
        assert ui._matchup_at(ui.attacker_panel_rect.topleft) is None
        assert ui._matchup_at((5, 5)) is None

    def test_the_tooltip_shows(self, screen):
        ui = self._full_house(screen)
        rect, _unit_type = ui._side_tags[0][0][0]
        ui.handle_mouse_motion((5, 5))
        screen.fill((0, 0, 0))
        ui.render()
        plain = pygame.image.tobytes(screen, 'RGB')
        ui.handle_mouse_motion(self._on_screen(ui, 0, rect))
        screen.fill((0, 0, 0))
        ui.render()
        assert pygame.image.tobytes(screen, 'RGB') != plain

    def test_a_tag_scrolled_away_explains_nothing(self, screen):
        ui = self._full_house(screen)
        rect, _unit_type = ui._side_tags[0][0][0]               # the first unit row's tag
        ui.handle_mouse_motion(ui.attacker_panel_rect.center)
        ui.handle_wheel(-999)                                   # scrolled out of view
        moved = self._on_screen(ui, 0, rect)
        assert moved[1] < ui._sides[0][1].rect.top              # now above the visible rows
        assert ui._matchup_at(moved) is None
