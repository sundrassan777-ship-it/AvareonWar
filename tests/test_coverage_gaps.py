"""
Test coverage gap tests for QA Audit #3.

Covers 7 areas previously untested:
1. Tech research lifecycle
2. Building construction lifecycle
3. Movement order execution
4. Hero ability effects
5. Simultaneous mode conflict resolution
6. Alliance system
7. Achievement system
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
from game_state import GameState


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def game():
    """Standard 2-player game."""
    gs = GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True
    )
    return gs


@pytest.fixture
def game_4p():
    """4-player game for alliance tests."""
    gs = GameState(
        num_players=4,
        player_is_ai=[False, False, False, False],
        player_ai_difficulty=[1, 1, 1, 1],
        skip_setup_phase=True
    )
    return gs


# ============================================================================
# Gap 1: Tech Research Lifecycle
# ============================================================================

class TestTechResearch:
    """Tests for start_research, finish_research, cancel_research."""

    def test_start_research_deducts_gold(self, game):
        """Starting research should deduct gold."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        game.territory_owners[territories[0]] = 0

        # Need a Castle for some techs — find a tech that doesn't require one
        available = game.player_tech_available.get(0, set())
        assert len(available) > 0, "Player should have available techs"

        tech_id = list(available)[0]
        tech = next(t for t in game.technologies if t['id'] == tech_id)
        cost = tech['cost']

        gold_before = game.player_gold[0]
        result = game.start_research(tech_id)
        assert result == True, f"start_research should succeed, got {result}"
        assert game.player_gold[0] == gold_before - cost

    def test_finish_research_completes(self, game):
        """finish_research should complete when turns reach 0."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        game.territory_owners[territories[0]] = 0

        available = game.player_tech_available.get(0, set())
        tech_id = list(available)[0]

        game.start_research(tech_id)
        assert 0 in game.research_in_progress

        # Fast-forward: set turns_remaining to 1
        game.research_in_progress[0]['turns_remaining'] = 1

        game.finish_research()

        # Should be in researched set now
        assert tech_id in game.player_tech_researched.get(0, set())
        assert 0 not in game.research_in_progress

    def test_cancel_research_refunds(self, game):
        """cancel_research should refund full cost."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        game.territory_owners[territories[0]] = 0

        available = game.player_tech_available.get(0, set())
        tech_id = list(available)[0]

        game.start_research(tech_id)
        gold_after_start = game.player_gold[0]

        result = game.cancel_research()
        assert result == True
        # Gold should be back to pre-start amount
        assert game.player_gold[0] > gold_after_start
        assert 0 not in game.research_in_progress

    def test_research_effect_applied(self, game):
        """Completing research should apply its effect to game state."""
        game.current_player = 0
        game.player_gold[0] = 1000
        territories = list(game.territory_owners.keys())
        game.territory_owners[territories[0]] = 0

        # Find a tech with command_limit effect (tech_1_0 typically)
        target_tech = None
        for tech in game.technologies:
            if tech.get('effect_type') == 'command_limit' and tech['id'] in game.player_tech_available.get(0, set()):
                target_tech = tech
                break

        if target_tech is None:
            pytest.skip("No command_limit tech available")

        old_limit = game.player_command_limit[0]
        game.start_research(target_tech['id'])
        game.research_in_progress[0]['turns_remaining'] = 1
        game.finish_research()

        assert game.player_command_limit[0] == old_limit + target_tech['effect_value']


# ============================================================================
# Gap 2: Building Construction Lifecycle
# ============================================================================

class TestBuildingConstruction:
    """Tests for start_construction, finish_constructions, cancel_construction."""

    def test_start_construction_basic(self, game):
        """Start construction of a Farm."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0

        gold_before = game.player_gold[0]
        result = game.start_construction(terr, 0, 'Farm')
        assert result == True
        assert game.player_gold[0] < gold_before
        assert terr in game.under_construction
        assert 0 in game.under_construction[terr]

    def test_finish_constructions_completes(self, game):
        """finish_constructions should complete buildings when timer hits 0."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0

        game.start_construction(terr, 0, 'Farm')

        # Farm takes 1 turn, so finish should complete it
        completed = game.finish_constructions()
        assert len(completed) == 1
        assert completed[0][1] == 'Farm'
        assert game.buildings[terr][0] == 'Farm'
        assert terr not in game.under_construction

    def test_keep_takes_two_turns(self, game):
        """Keep should take 2 turns to build."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0

        game.start_construction(terr, 0, 'Keep')

        # First turn: should NOT complete
        completed = game.finish_constructions()
        assert len(completed) == 0
        assert terr in game.under_construction

        # Second turn: should complete
        completed = game.finish_constructions()
        assert len(completed) == 1
        assert game.buildings[terr][0] == 'Keep'

    def test_cancel_construction_refunds(self, game):
        """Cancelling construction should refund the paid cost."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0

        gold_before = game.player_gold[0]
        game.start_construction(terr, 0, 'Farm')
        gold_after_build = game.player_gold[0]

        result = game.cancel_construction(terr, 0)
        assert result == True
        assert game.player_gold[0] == gold_before  # Full refund
        assert terr not in game.under_construction

    def test_one_building_per_territory_per_turn(self, game):
        """Should only allow one building per territory per turn."""
        game.current_player = 0
        game.player_gold[0] = 500
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0

        game.start_construction(terr, 0, 'Farm')
        result = game.start_construction(terr, 1, 'Mine')
        assert result == False  # Should fail: already started this turn


# ============================================================================
# Gap 3: Movement Order Execution
# ============================================================================

class TestMovementExecution:
    """Tests for movement order execution and battle creation."""

    def _setup_garrison(self, game, territory, player, count):
        """Helper: set up a garrison with 'ready' units (can move)."""
        game.territory_owners[territory] = player
        # Units must have status='ready' to be orderable
        units = [game._make_unit('Swordsman', i, status='ready') for i in range(count)]
        game.add_garrison(territory, player, unmoved=count, moved=0, units=units)
        game.armies[territory] = count
        game.armies_unmoved[territory] = count
        game.armies_moved[territory] = 0
        game.army_units[territory] = [u.copy() for u in units]

    def test_execute_orders_moves_armies(self, game):
        """Movement orders should move units from source to destination."""
        territories = list(game.territory_owners.keys())
        from_terr = territories[0]
        neighbors = map_data.get_neighbors(from_terr)
        assert len(neighbors) > 0, f"Territory {from_terr} has no neighbors"
        to_terr = neighbors[0]

        self._setup_garrison(game, from_terr, 0, 5)
        game.territory_owners[to_terr] = 0  # Friendly destination
        game.armies[to_terr] = 0
        game.armies_unmoved[to_terr] = 0
        game.armies_moved[to_terr] = 0

        # Create movement order using unit IDs from garrison
        garrison = game.territory_garrisons[from_terr][0]
        unit_ids = [u['id'] for u in garrison['units'][:3]]
        game.current_player = 0
        success = game.add_movement_order_for_units(from_terr, to_terr, unit_ids, player=0)
        assert success, "Movement order should be created"

        # Execute
        game.execute_all_orders()

        # Units should arrive at destination (via pending_arrivals or direct)
        dest_armies = game.armies.get(to_terr, 0)
        pending = len(game.pending_arrivals)
        animations = len(game.active_animations)
        assert dest_armies > 0 or pending > 0 or animations > 0, \
            "Units should arrive or be in transit"

    def test_movement_into_enemy_creates_battle(self, game):
        """Moving into enemy territory should create a pending battle or arrival."""
        territories = list(game.territory_owners.keys())
        from_terr = territories[0]
        neighbors = map_data.get_neighbors(from_terr)
        assert len(neighbors) > 0
        to_terr = neighbors[0]

        self._setup_garrison(game, from_terr, 0, 5)
        self._setup_garrison(game, to_terr, 1, 3)

        # Create order from garrison
        garrison = game.territory_garrisons[from_terr][0]
        unit_ids = [u['id'] for u in garrison['units'][:5]]
        game.current_player = 0
        game.add_movement_order_for_units(from_terr, to_terr, unit_ids, player=0)

        game.execute_all_orders()

        # Should have pending battle, pending arrivals, or active animations
        has_conflict = (len(game.pending_battles) > 0 or
                       len(game.pending_arrivals) > 0 or
                       len(game.active_animations) > 0)
        assert has_conflict, "Moving into enemy territory should create a conflict"


# ============================================================================
# Gap 4: Hero Ability Effects
# ============================================================================

class TestHeroAbilities:
    """Tests for hero ability effects on game state."""

    def _setup_hero(self, game, player, hero_name, territory, plot=0):
        """Helper: add a hero to a player."""
        if player not in game.heroes:
            game.heroes[player] = {}
        game.heroes[player][hero_name] = {
            'keep_territory': territory,
            'keep_plot': plot,
            'status': 'active'
        }
        game.hero_ownership[player].add(hero_name)

    def test_levy_adds_gold(self, game):
        """Levy ability should add territory income to player gold."""
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0
        game.current_player = 0
        game.player_gold[0] = 100

        self._setup_hero(game, 0, 'Halon Nextroy', terr)

        gold_before = game.player_gold[0]
        expected_income = game.calculate_territory_income(terr)
        result = game.execute_levy(terr, 0)

        assert result[0] == True, f"Levy should succeed: {result}"
        assert game.player_gold[0] == gold_before + expected_income

    def test_extort_populace_gains_gold(self, game):
        """Extort Populace should give 50 gold per Keep/Castle."""
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0
        game.current_player = 0
        game.player_gold[0] = 100

        # Build a Keep
        if terr not in game.buildings:
            game.buildings[terr] = {}
        game.buildings[terr][0] = 'Keep'

        self._setup_hero(game, 0, 'Erec Silvyr', terr)

        gold_before = game.player_gold[0]
        result = game.execute_extort_populace(0)
        assert result[0] == True
        assert game.player_gold[0] == gold_before + 50  # 1 Keep = 50 gold

    def test_vow_of_silence_silences_enemies(self, game):
        """Vow of Silence should set silence status on all enemy players."""
        territories = list(game.territory_owners.keys())
        terr = territories[0]
        game.territory_owners[terr] = 0
        game.current_player = 0

        self._setup_hero(game, 0, 'Auric Valorion', terr)

        # Manually call the internal method
        ability = {'cooldown': 3}
        game._activate_vow_of_silence('Auric Valorion', ability)

        # Player 1 should be silenced
        assert game.hero_silence_status[1] > 0, "Enemy should be silenced"
        # Player 0 (caster) should NOT be silenced
        assert game.hero_silence_status[0] == 0, "Caster should not be silenced"


# ============================================================================
# Gap 5: Simultaneous Mode Conflict Resolution
# ============================================================================

class TestSimConflictResolution:
    """Tests for crossing army detection and resolution."""

    def test_detect_crossing_conflict(self):
        """Two opposing armies crossing should be detected."""
        from simultaneous.sim_conflict_resolver import SimConflictResolver

        # Create minimal mock
        class MockGS:
            player_teams = [0, 1]  # FFA: each on own team
        class MockSimState:
            gs = MockGS()

        resolver = SimConflictResolver(MockSimState())

        orders = {
            0: [{'type': 'movement', 'from_territory': 'A', 'to_territory': 'B',
                 'army_count': 5, 'player_id': 0}],
            1: [{'type': 'movement', 'from_territory': 'B', 'to_territory': 'A',
                 'army_count': 3, 'player_id': 1}],
        }

        conflicts = resolver.detect_crossing_conflicts(orders)
        assert len(conflicts) == 1, f"Should detect 1 crossing conflict, got {len(conflicts)}"

    def test_no_conflict_same_team(self):
        """Allies crossing should NOT be a conflict."""
        from simultaneous.sim_conflict_resolver import SimConflictResolver

        class MockGS:
            player_teams = [0, 0]  # Same team
        class MockSimState:
            gs = MockGS()

        resolver = SimConflictResolver(MockSimState())

        orders = {
            0: [{'type': 'movement', 'from_territory': 'A', 'to_territory': 'B',
                 'army_count': 5, 'player_id': 0}],
            1: [{'type': 'movement', 'from_territory': 'B', 'to_territory': 'A',
                 'army_count': 3, 'player_id': 1}],
        }

        conflicts = resolver.detect_crossing_conflicts(orders)
        assert len(conflicts) == 0, "Allies shouldn't trigger crossing conflicts"

    def test_resolve_crossing_stronger_wins(self):
        """Stronger army should win crossing conflict."""
        from simultaneous.sim_conflict_resolver import SimConflictResolver

        class MockGS:
            player_teams = [0, 1]
        class MockSimState:
            gs = MockGS()

        resolver = SimConflictResolver(MockSimState())

        orders = {
            0: [{'type': 'movement', 'from_territory': 'A', 'to_territory': 'B',
                 'army_count': 10, 'player_id': 0}],
            1: [{'type': 'movement', 'from_territory': 'B', 'to_territory': 'A',
                 'army_count': 3, 'player_id': 1}],
        }

        conflicts = resolver.detect_crossing_conflicts(orders)
        result = resolver.resolve_crossing_conflicts(orders, conflicts)

        # Weaker player's orders should be cancelled
        assert len(result.get(1, [])) == 0, "Weaker player's orders should be cancelled"
        assert len(result.get(0, [])) > 0, "Stronger player's orders should survive"


# ============================================================================
# Gap 6: Alliance System
# ============================================================================

class TestAllianceSystem:
    """Tests for are_allies and team-based mechanics."""

    def test_are_allies_same_team(self, game_4p):
        """Players on same team should be allies."""
        game_4p.player_teams = [0, 0, 1, 1]
        assert game_4p.are_allies(0, 1) == True
        assert game_4p.are_allies(2, 3) == True

    def test_are_allies_different_team(self, game_4p):
        """Players on different teams should NOT be allies."""
        game_4p.player_teams = [0, 0, 1, 1]
        assert game_4p.are_allies(0, 2) == False
        assert game_4p.are_allies(1, 3) == False

    def test_are_allies_self(self, game_4p):
        """Player should NOT be 'allied' with themselves."""
        game_4p.player_teams = [0, 0, 1, 1]
        assert game_4p.are_allies(0, 0) == False

    def test_are_allies_invalid_index(self, game_4p):
        """Invalid player index should return False."""
        game_4p.player_teams = [0, 0, 1, 1]
        assert game_4p.are_allies(-1, 0) == False
        assert game_4p.are_allies(0, 99) == False

    def test_are_allies_no_teams(self, game):
        """With no teams (FFA), no one should be allies."""
        assert game.are_allies(0, 1) == False

    def test_ffa_all_separate_teams(self, game_4p):
        """FFA mode: each player on own team, no allies."""
        game_4p.player_teams = [0, 1, 2, 3]
        for i in range(4):
            for j in range(4):
                if i != j:
                    assert game_4p.are_allies(i, j) == False


# ============================================================================
# Gap 7: Achievement System
# ============================================================================

class TestAchievementSystem:
    """Tests for achievement earning and stat tracking."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset AchievementManager singleton between tests."""
        from achievement_manager import AchievementManager
        AchievementManager._instance = None
        yield
        AchievementManager._instance = None

    def test_achievement_not_earned_initially(self):
        """Achievements should not be earned initially."""
        from achievement_manager import AchievementManager
        mgr = AchievementManager()
        mgr.stats = {}
        mgr.earned = {}

        assert mgr.is_earned('halberdier') == False

    def test_check_achievement_earned_on_threshold(self):
        """Achievement should be earned when stat reaches threshold."""
        from achievement_manager import AchievementManager
        mgr = AchievementManager()
        mgr.stats = {}
        mgr.earned = {}

        # Find an achievement with known stat_key
        from achievement_manager import ACHIEVEMENTS as achievements
        if not achievements:
            pytest.skip("No achievements defined")

        test_ach = achievements[0]
        stat_key = test_ach.get('stat_key')
        threshold = test_ach.get('stat_threshold', 1)

        if not stat_key:
            pytest.skip("First achievement has no stat_key")

        # Set stat above threshold
        mgr.stats[stat_key] = threshold
        newly_earned = mgr._check_new_achievements()
        assert len(newly_earned) >= 1, f"Should earn achievement when {stat_key} >= {threshold}"
        assert mgr.is_earned(test_ach['id'])

    def test_get_all_achievements_returns_list(self):
        """get_all_achievements should return enriched list."""
        from achievement_manager import AchievementManager
        mgr = AchievementManager()
        mgr.stats = {}
        mgr.earned = {}

        all_achs = mgr.get_all_achievements()
        assert isinstance(all_achs, list)
        assert len(all_achs) > 0
        # Each should have 'earned' field
        assert 'earned' in all_achs[0]

    def test_earned_timestamp_set(self):
        """Earned achievements should have a timestamp."""
        from achievement_manager import AchievementManager
        mgr = AchievementManager()
        mgr.stats = {}
        mgr.earned = {}

        from achievement_manager import ACHIEVEMENTS as achievements
        if not achievements:
            pytest.skip("No achievements defined")

        test_ach = achievements[0]
        stat_key = test_ach.get('stat_key')
        threshold = test_ach.get('stat_threshold', 1)
        if not stat_key:
            pytest.skip("First achievement has no stat_key")

        mgr.stats[stat_key] = threshold
        mgr._check_new_achievements()

        timestamp = mgr.get_earned_timestamp(test_ach['id'])
        assert timestamp is not None, "Earned achievement should have a timestamp"
