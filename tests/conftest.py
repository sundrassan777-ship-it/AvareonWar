# tests/conftest.py
# Shared pytest fixtures and session-level setup for test isolation.

"""
Ensures map_data is loaded and campaign territory filtering is cleared
before each test module runs, preventing cross-test contamination
(e.g., campaign_mission_4 calling set_enabled_territories() which
filters 57 territories down to 21).
"""

import sys
import os
import pytest

# Ensure project root is on sys.path for all test files
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data


@pytest.fixture(autouse=True)
def clean_map_data():
    """Reset map_data state before each test to prevent contamination.

    Campaign missions call map_data.set_enabled_territories() which filters
    the territory list globally. This fixture ensures every test starts with
    the full 57-territory map.
    """
    map_data.load_polygons()
    map_data.clear_enabled_territories()
    yield
    # Post-test cleanup: restore full territory list
    map_data.clear_enabled_territories()
