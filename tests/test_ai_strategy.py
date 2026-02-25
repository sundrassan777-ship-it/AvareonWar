"""
Tests for AI strategy module (ai_strategy.py)

These tests cover the strategic evaluation and decision-making for AI opponents.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_strategy import TerritoryScorer, ThreatAnalyzer, OpportunityDetector, StrategyEvaluator


class MockGameState:
    """Mock game state for testing"""

    def __init__(self):
        self.territory_owners = {}
        self.armies = {}
        self.armies_unmoved = {}
        self.buildings = {}
        self.player_gold = {0: 100, 1: 100}
        self.player_command_limit = {0: 50, 1: 50}
        self.player_tech_researched = {0: set(), 1: set()}
        # Garrison-based army storage used by refactored AI code
        self.territory_garrisons = {}

    def calculate_player_income(self, player_index):
        return 50

    def get_player_army_count(self, player_index):
        return sum(
            self.armies.get(t, 0)
            for t, owner in self.territory_owners.items()
            if owner == player_index
        )

    def get_territory_total_armies(self, territory):
        """Return total armies in a territory (mock uses legacy armies dict)"""
        return self.armies.get(territory, 0)

    def are_allies(self, player1, player2):
        """Check if two players are allies (mock always returns False)"""
        return False

    def has_fortress(self, territory):
        """Check if territory has a Keep (mock always returns False)"""
        return False


class TestTerritoryScorer:
    """Tests for TerritoryScorer class"""

    @pytest.fixture
    def scorer(self):
        return TerritoryScorer()

    @pytest.fixture
    def game_state(self):
        return MockGameState()

    def test_calculate_territory_value_basic(self, scorer, game_state):
        """Basic territory value calculation"""
        game_state.territory_owners = {'TestTerritory': 0}
        game_state.buildings = {}

        with patch('map_data.get_territory_income', return_value=10):
            with patch('map_data.TERRITORY_PLOTS', {'TestTerritory': [0, 1]}):
                with patch('map_data.get_neighbors', return_value=['Neighbor1', 'Neighbor2']):
                    value = scorer.calculate_territory_value('TestTerritory', game_state, 0)

        assert value >= 0
        assert value <= 100

    def test_calculate_territory_value_with_buildings(self, scorer, game_state):
        """Territory with buildings has higher value"""
        game_state.territory_owners = {'TestTerritory': 0}
        game_state.buildings = {'TestTerritory': {0: 'Farm', 1: 'Mine'}}

        with patch('map_data.get_territory_income', return_value=10):
            with patch('map_data.TERRITORY_PLOTS', {'TestTerritory': [0, 1, 2]}):
                with patch('map_data.get_neighbors', return_value=['Neighbor1']):
                    value_with_buildings = scorer.calculate_territory_value('TestTerritory', game_state, 0)

        game_state.buildings = {}
        with patch('map_data.get_territory_income', return_value=10):
            with patch('map_data.TERRITORY_PLOTS', {'TestTerritory': [0, 1, 2]}):
                with patch('map_data.get_neighbors', return_value=['Neighbor1']):
                    value_without_buildings = scorer.calculate_territory_value('TestTerritory', game_state, 0)

        assert value_with_buildings > value_without_buildings

    def test_calculate_territory_value_adjacency_bonus(self, scorer, game_state):
        """Territory adjacent to owned territories has higher value"""
        game_state.territory_owners = {
            'TestTerritory': -1,  # Neutral
            'OwnedNeighbor1': 0,
            'OwnedNeighbor2': 0,
            'EnemyNeighbor': 1
        }

        with patch('map_data.get_territory_income', return_value=5):
            with patch('map_data.TERRITORY_PLOTS', {'TestTerritory': []}):
                with patch('map_data.get_neighbors', return_value=['OwnedNeighbor1', 'OwnedNeighbor2', 'EnemyNeighbor']):
                    value = scorer.calculate_territory_value('TestTerritory', game_state, 0)

        # Should have adjacency bonus for 2 friendly neighbors
        assert value > 0

    def test_evaluate_buildings_all_types(self, scorer, game_state):
        """Test building evaluation for all building types"""
        game_state.buildings = {
            'TestTerritory': {
                0: 'Farm',
                1: 'Mine',
                2: 'Barracks',
                3: 'Keep',
                4: 'Square'
            }
        }

        value = scorer._evaluate_buildings('TestTerritory', game_state)

        # Farm=3, Mine=4, Barracks=5, Keep=7, Square=6 = 25, capped at 30
        assert value == 25.0

    def test_evaluate_buildings_empty(self, scorer, game_state):
        """Empty territory has 0 building value"""
        value = scorer._evaluate_buildings('NonexistentTerritory', game_state)
        assert value == 0.0


class TestThreatAnalyzer:
    """Tests for ThreatAnalyzer class"""

    @pytest.fixture
    def analyzer(self):
        return ThreatAnalyzer()

    @pytest.fixture
    def game_state(self):
        return MockGameState()

    def test_calculate_territory_threat_no_enemies(self, analyzer, game_state):
        """Territory with no enemy neighbors has low threat"""
        game_state.territory_owners = {
            'TestTerritory': 0,
            'Neighbor1': 0,
            'Neighbor2': -1  # Neutral
        }
        game_state.armies = {'TestTerritory': 5}

        with patch('map_data.get_neighbors', return_value=['Neighbor1', 'Neighbor2']):
            threat = analyzer.calculate_territory_threat('TestTerritory', game_state, 0)

        assert threat == 0.0

    def test_calculate_territory_threat_enemy_neighbor(self, analyzer, game_state):
        """Territory with enemy neighbor has threat"""
        game_state.territory_owners = {
            'TestTerritory': 0,
            'EnemyNeighbor': 1
        }
        game_state.armies = {'TestTerritory': 5, 'EnemyNeighbor': 10}

        with patch('map_data.get_neighbors', return_value=['EnemyNeighbor']):
            threat = analyzer.calculate_territory_threat('TestTerritory', game_state, 0)

        assert threat > 0

    def test_calculate_territory_threat_undefended(self, analyzer, game_state):
        """Undefended territory at enemy border has high threat"""
        game_state.territory_owners = {
            'TestTerritory': 0,
            'EnemyNeighbor': 1
        }
        game_state.armies = {'TestTerritory': 0, 'EnemyNeighbor': 10}

        with patch('map_data.get_neighbors', return_value=['EnemyNeighbor']):
            threat = analyzer.calculate_territory_threat('TestTerritory', game_state, 0)

        # Undefended = 30 points + 5 for enemy neighbor
        assert threat >= 30.0

    def test_find_threatened_territories(self, analyzer, game_state):
        """Find all threatened territories above threshold"""
        game_state.territory_owners = {
            'Safe': 0,
            'Threatened': 0,
            'EnemyTerritory': 1
        }
        game_state.armies = {'Safe': 10, 'Threatened': 0, 'EnemyTerritory': 10}

        def mock_neighbors(territory):
            if territory == 'Threatened':
                return ['EnemyTerritory']
            return ['Safe']

        with patch('map_data.get_neighbors', side_effect=mock_neighbors):
            threatened = analyzer.find_threatened_territories(game_state, 0, threshold=20.0)

        # Should find 'Threatened' but not 'Safe'
        assert len(threatened) >= 1
        territory_names = [t[0] for t in threatened]
        assert 'Threatened' in territory_names


class TestOpportunityDetector:
    """Tests for OpportunityDetector class"""

    @pytest.fixture
    def detector(self):
        return OpportunityDetector()

    @pytest.fixture
    def game_state(self):
        return MockGameState()

    def test_find_expansion_targets_basic(self, detector, game_state):
        """Find expansion targets adjacent to owned territory"""
        game_state.territory_owners = {
            'Owned': 0,
            'NeutralTarget': -1,
            'EnemyTarget': 1
        }
        game_state.armies = {'Owned': 10, 'NeutralTarget': 0, 'EnemyTarget': 5}
        game_state.armies_unmoved = {'Owned': 10}

        def mock_neighbors(territory):
            if territory == 'Owned':
                return ['NeutralTarget', 'EnemyTarget']
            return ['Owned']

        with patch('map_data.get_neighbors', side_effect=mock_neighbors):
            with patch('map_data.get_territory_income', return_value=10):
                with patch('map_data.TERRITORY_PLOTS', {}):
                    targets = detector.find_expansion_targets(game_state, 0)

        assert len(targets) >= 1
        # Should include source territory in result
        target_names = [t[0] for t in targets]
        assert 'NeutralTarget' in target_names or 'EnemyTarget' in target_names

    def test_find_weak_enemy_territories(self, detector, game_state):
        """Find weakly defended enemy territories"""
        game_state.territory_owners = {
            'Owned': 0,
            'WeakEnemy': 1,
            'StrongEnemy': 1
        }
        game_state.armies = {'Owned': 10, 'WeakEnemy': 2, 'StrongEnemy': 50}

        def mock_neighbors(territory):
            if territory == 'Owned':
                return ['WeakEnemy', 'StrongEnemy']
            return ['Owned']

        with patch('map_data.get_neighbors', side_effect=mock_neighbors):
            weak = detector.find_weak_enemy_territories(game_state, 0)

        # WeakEnemy should be in the list (garrison=2, weakness=18)
        # StrongEnemy should not (garrison=50, weakness=0)
        assert len(weak) >= 1
        territory_names = [t[0] for t in weak]
        assert 'WeakEnemy' in territory_names
        assert 'StrongEnemy' not in territory_names


class TestStrategyEvaluator:
    """Tests for StrategyEvaluator class"""

    @pytest.fixture
    def mock_ai_player(self):
        ai = Mock()
        ai.player_index = 0
        return ai

    @pytest.fixture
    def evaluator(self, mock_ai_player):
        return StrategyEvaluator(mock_ai_player)

    @pytest.fixture
    def game_state(self):
        return MockGameState()

    def test_analyze_game_state(self, evaluator, game_state):
        """Analyze returns complete state analysis"""
        game_state.territory_owners = {'Territory1': 0, 'Territory2': 0}
        game_state.armies = {'Territory1': 5, 'Territory2': 10}

        with patch.object(evaluator.threat_analyzer, 'find_threatened_territories', return_value=[]):
            with patch.object(evaluator.opportunity_detector, 'find_expansion_targets', return_value=[]):
                with patch.object(evaluator.opportunity_detector, 'find_weak_enemy_territories', return_value=[]):
                    analysis = evaluator.analyze_game_state(game_state)

        assert 'owned_territories' in analysis
        assert 'territory_count' in analysis
        assert 'total_income' in analysis
        assert 'total_armies' in analysis
        assert 'threats' in analysis
        assert 'opportunities' in analysis
        assert 'available_gold' in analysis

        assert analysis['territory_count'] == 2
        assert analysis['total_armies'] == 15

    def test_get_strategic_priority_defense(self, evaluator, game_state):
        """High threats trigger defense priority"""
        game_state.territory_owners = {'T1': 0, 'T2': 0}

        with patch.object(evaluator.threat_analyzer, 'find_threatened_territories',
                         return_value=[('T1', 60.0)]):  # High threat
            priority = evaluator.get_strategic_priority(game_state)

        assert priority == 'defense'

    def test_get_strategic_priority_economy(self, evaluator, game_state):
        """Few territories triggers economy priority"""
        game_state.territory_owners = {f'T{i}': 0 for i in range(5)}  # Only 5 territories

        with patch.object(evaluator.threat_analyzer, 'find_threatened_territories', return_value=[]):
            priority = evaluator.get_strategic_priority(game_state)

        assert priority == 'economy'

    def test_get_strategic_priority_victory_push(self, evaluator, game_state):
        """Many territories triggers victory push"""
        game_state.territory_owners = {f'T{i}': 0 for i in range(40)}  # 40 territories (threshold is >=40)

        with patch.object(evaluator.threat_analyzer, 'find_threatened_territories', return_value=[]):
            priority = evaluator.get_strategic_priority(game_state)

        assert priority == 'victory_push'

    def test_get_strategic_priority_expansion(self, evaluator, game_state):
        """Mid-game with no threats triggers expansion"""
        game_state.territory_owners = {f'T{i}': 0 for i in range(20)}  # 20 territories (above economy threshold of <16)

        with patch.object(evaluator.threat_analyzer, 'find_threatened_territories', return_value=[]):
            priority = evaluator.get_strategic_priority(game_state)

        assert priority == 'expansion'
