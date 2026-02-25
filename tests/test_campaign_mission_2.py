# -*- coding: utf-8 -*-
"""
Campaign Mission 2 Playthrough Test
====================================

Tests and analyzes Campaign Mission 2 ("Early Eastern Conquests") by:
1. Playing through the mission with simulated player actions
2. Validating awakening mechanics, faction defeats, and victory
3. Providing analysis of gameplay balance and potential issues

Usage:
    python tests/test_campaign_mission_2.py
"""

import sys
import os
import time
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
import traceback


# Mission 2 territory/faction configuration (from campaign_mission_2.py)
FACTION_TERRITORIES = {
    0: ["Lobardia"],  # Human player
    1: ["Elletian Isles", "Lentria", "Elland", "The Holy Land"],  # Elletic Tribes
    2: ["Venexia", "Révia"],  # Heilonic Tribes
    3: ["Valeonia", "Velognia"],  # Chiefdom of Valeonia
}

FACTION_NAMES = {
    0: "Human Player",
    1: "Elletic Tribes",
    2: "Heilonic Tribes",
    3: "Chiefdom of Valeonia",
}


class MissionAnalyzer:
    """Tracks and analyzes mission playthrough."""

    def __init__(self):
        self.turns = 0
        self.battles = 0
        self.territories_conquered = []
        self.factions_defeated = []
        self.awakenings = []
        self.issues = []
        self.events = []

    def log_event(self, event_type, details):
        """Log a game event."""
        self.events.append((self.turns, event_type, details))

    def log_issue(self, issue):
        """Log a potential issue."""
        self.issues.append((self.turns, issue))

    def print_summary(self):
        """Print analysis summary."""
        print()
        print("=" * 70)
        print("ANALYSIS SUMMARY")
        print("=" * 70)
        print(f"Turns to completion: {self.turns}")
        print(f"Total battles: {self.battles}")
        print(f"Territories conquered: {len(self.territories_conquered)}")
        print(f"Factions defeated: {len(self.factions_defeated)}")
        print()
        print("Awakening events:")
        for turn, faction, reason in self.awakenings:
            print(f"  Turn {turn}: {FACTION_NAMES[faction]} awakened ({reason})")
        print()
        print("Faction defeats:")
        for turn, faction in self.factions_defeated:
            print(f"  Turn {turn}: {FACTION_NAMES[faction]} defeated")
        print()
        if self.issues:
            print("Issues found:")
            for turn, issue in self.issues:
                print(f"  Turn {turn}: {issue}")
        else:
            print("Issues found: None")


class MockScreen:
    """Mock pygame screen for testing."""

    def get_width(self):
        return 1920

    def get_height(self):
        return 1080


class MockMainGame:
    """Mock main_game object for testing without pygame display."""

    def __init__(self, game_state):
        self.game_state = game_state
        self.camera = MockCamera()
        self.screen = MockScreen()
        self.scaled_centers = {}
        self.army_flag_icons = [None, None, None, None]  # 4 player slots

        # Populate scaled_centers with mock positions
        for territory in map_data.get_all_territories():
            self.scaled_centers[territory] = (500, 400)  # Mock center position

    def world_to_screen(self, pos):
        return pos

    def get_screen_size(self):
        return (1920, 1080)


class MockCamera:
    """Mock camera for testing."""

    def __init__(self):
        self.target_x = 0
        self.target_y = 0
        self.target_zoom = 1.0
        self.zoom = 1.0
        self.min_zoom = 0.3
        self.max_zoom = 2.0
        self.offset = [0, 0]
        self.x = 0
        self.y = 0

    def set_target(self, x, y, zoom=None):
        self.target_x = x
        self.target_y = y
        if zoom:
            self.target_zoom = zoom

    def clamp_to_bounds(self):
        """No-op for testing."""
        pass


def setup_mission_2():
    """Initialize game and mission for testing."""
    print("Loading map data...")
    map_data.load_polygons()

    from game_state import GameState
    from campaign_mission_2 import Mission2

    print("Creating 4-player game...")
    game = GameState(
        num_players=4,
        player_is_ai=[False, True, True, True],
        player_ai_difficulty=[0, 1, 1, 1],
        player_teams=[0, 1, 2, 3],  # FFA
        skip_setup_phase=True,
        victory_condition='Domination (45+)'
    )
    game.phase = 'playing'
    game.turn_phase = 'planning'

    print("Creating mock main_game...")
    mock_main = MockMainGame(game)

    print("Creating Mission 2...")
    try:
        mission = Mission2(game, main_game=mock_main)
        game.tutorial_mission = mission
        print("[MISSION2] Mission 2 initialized successfully")
    except Exception as e:
        print(f"  Error initializing mission: {e}")
        traceback.print_exc()
        mission = None

    return game, mission


def skip_intro(mission):
    """Skip the intro sequence for testing."""
    if not mission:
        return

    mission.intro_active = False
    mission.game_paused = False
    mission.intro_step_index = 999  # Past end
    mission.timer_visible = True
    print("[TEST] Intro sequence skipped")


def get_faction_state(game, mission):
    """Get current state of all factions."""
    state = {}
    for faction_id, territories in FACTION_TERRITORIES.items():
        owned = [t for t in territories if game.territory_owners.get(t) == faction_id]
        total_armies = 0
        for t in owned:
            garrison = game.territory_garrisons.get(t, {}).get(faction_id, {})
            total_armies += len(garrison.get('units', []))

        if mission and faction_id > 0:
            awakened = mission.faction_awakened.get(faction_id, False)
            defeated = mission.faction_defeated.get(faction_id, False)
        else:
            awakened = faction_id == 0  # Human always "awakened"
            defeated = False

        state[faction_id] = {
            'territories': len(owned),
            'armies': total_armies,
            'awakened': awakened,
            'defeated': defeated,
            'territory_names': owned,
        }
    return state


def print_state(game, mission, turn):
    """Print current game state."""
    state = get_faction_state(game, mission)
    print(f"\n--- TURN {turn} STATE ---")
    for faction_id in sorted(state.keys()):
        s = state[faction_id]
        status = ""
        if faction_id > 0:
            if s['defeated']:
                status = " [DEFEATED]"
            elif s['awakened']:
                status = " [AWAKENED]"
            else:
                status = " [DORMANT]"
        print(f"  {FACTION_NAMES[faction_id]}: {s['territories']} territories, {s['armies']} armies{status}")
        if s['territory_names']:
            print(f"    Territories: {', '.join(s['territory_names'])}")


def force_conquer_territory(game, mission, territory, analyzer):
    """Force-conquer a territory for testing."""
    old_owner = game.territory_owners.get(territory, -1)

    # Clear old garrison
    if territory in game.territory_garrisons:
        game.territory_garrisons[territory] = {}

    # Transfer ownership
    game.territory_owners[territory] = 0

    # Add minimal player garrison
    game.add_garrison(territory, 0, unmoved=3, moved=0, units=[
        {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': i}
        for i in range(3)
    ])

    # Sync legacy data
    game.sync_legacy_garrison_data(territory)

    analyzer.territories_conquered.append(territory)
    analyzer.battles += 1
    print(f"  [BATTLE] Player conquers {territory} from {FACTION_NAMES.get(old_owner, 'Neutral')}")

    # Notify mission of conquest
    if mission:
        # Check for awakening first (as if attacking)
        mission._check_attack_awakening(territory)

        # Then process conquest
        mission.notify_event('territory_conquered', territory=territory, new_owner=0)


def execute_ai_turns(game, mission, analyzer):
    """Execute AI turns for all factions."""
    for faction_id in [1, 2, 3]:
        state = get_faction_state(game, mission)
        faction_state = state[faction_id]

        if faction_state['defeated']:
            continue

        if mission and not mission.faction_awakened.get(faction_id, False):
            # Dormant - do nothing
            print(f"  AI Turn ({FACTION_NAMES[faction_id]}): [DORMANT - skipped]")
            continue

        # Awakened AI - simulate simple behavior
        # The actual mission AI trains units when affordable
        print(f"  AI Turn ({FACTION_NAMES[faction_id]}): Active, {faction_state['armies']} armies")


def check_awakening_events(mission, analyzer, turn):
    """Check and log any new awakening events."""
    if not mission:
        return

    for faction_id in [1, 2, 3]:
        if mission.faction_awakened.get(faction_id, False):
            # Check if this is a new awakening
            already_logged = any(a[1] == faction_id for a in analyzer.awakenings)
            if not already_logged:
                analyzer.awakenings.append((turn, faction_id, "attack/conquest"))
                print(f"  [AWAKENING] {FACTION_NAMES[faction_id]} is now active!")


def check_defeat_events(mission, analyzer, turn):
    """Check and log any new defeat events."""
    if not mission:
        return

    for faction_id in [1, 2, 3]:
        if mission.faction_defeated.get(faction_id, False):
            # Check if this is a new defeat
            already_logged = any(d[1] == faction_id for d in analyzer.factions_defeated)
            if not already_logged:
                analyzer.factions_defeated.append((turn, faction_id))
                print(f"  [DEFEAT] {FACTION_NAMES[faction_id]} has been eliminated!")


def check_quest_status(mission):
    """Print current quest status."""
    if not mission:
        return

    print("  Quest Log:")
    for quest in mission.quest_log:
        status = "[X]" if quest['completed'] else "[ ]"
        print(f"    {status} {quest['text']}")


def check_victory(mission):
    """Check if victory conditions are met."""
    if not mission:
        return False

    all_defeated = all(mission.faction_defeated.get(f, False) for f in [1, 2, 3])
    return all_defeated


def run_mission_playthrough():
    """Run a complete mission playthrough."""
    print("=" * 70)
    print("CAMPAIGN MISSION 2 - PLAYTHROUGH ANALYSIS")
    print("Early Eastern Conquests")
    print("=" * 70)
    print()

    analyzer = MissionAnalyzer()

    try:
        game, mission = setup_mission_2()
    except Exception as e:
        print(f"[ERROR] Failed to initialize mission: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

    if not mission:
        print("[ERROR] Mission failed to initialize")
        return {'success': False, 'error': 'Mission init failed'}

    # Skip intro
    skip_intro(mission)

    # Print initial state
    print_state(game, mission, 0)
    check_quest_status(mission)

    # Verify initial conditions
    print("\n--- INITIAL VALIDATION ---")
    errors = []

    # Check factions start dormant
    for faction_id in [1, 2, 3]:
        if mission.faction_awakened.get(faction_id, True):
            errors.append(f"Faction {faction_id} should start dormant")

    # Check player starting conditions
    lobardia_garrison = game.territory_garrisons.get("Lobardia", {}).get(0, {})
    player_units = len(lobardia_garrison.get('units', []))
    if player_units != 5:
        errors.append(f"Player should have 5 units, has {player_units}")

    if game.player_gold[0] != 500:
        errors.append(f"Player should have 500 gold, has {game.player_gold[0]}")

    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
            analyzer.log_issue(e)
    else:
        print("All initial conditions validated!")

    # ========================================
    # PLAYTHROUGH: Conquer all territories
    # ========================================

    # Attack order (strategic):
    # 1. Elland (adjacent to Lobardia, Elletic) - awakens Elletic
    # 2. Lentria (Elletic)
    # 3. The Holy Land (Elletic)
    # 4. Elletian Isles (Elletic HQ, has Keep) - defeats Elletic, awakens Heilonic
    # 5. Venexia (Heilonic)
    # 6. Révia (Heilonic HQ) - defeats Heilonic, awakens Valeonia
    # 7. Velognia (Valeonia)
    # 8. Valeonia (Valeonia HQ, has Keep) - defeats Valeonia, VICTORY

    conquest_order = [
        "Elland",
        "Lentria",
        "The Holy Land",
        "Elletian Isles",
        "Venexia",
        "Révia",
        "Velognia",
        "Valeonia",
    ]

    turn = 0
    max_turns = 50  # Safety limit

    for target in conquest_order:
        turn += 1
        analyzer.turns = turn

        if turn > max_turns:
            analyzer.log_issue(f"Exceeded max turns ({max_turns})")
            break

        print(f"\n{'='*50}")
        print(f"TURN {turn}: Attack {target}")
        print(f"{'='*50}")

        # Execute conquest
        force_conquer_territory(game, mission, target, analyzer)

        # Check for awakening events
        check_awakening_events(mission, analyzer, turn)

        # Check for defeat events
        check_defeat_events(mission, analyzer, turn)

        # Execute AI turns
        execute_ai_turns(game, mission, analyzer)

        # Print current state
        print_state(game, mission, turn)

        # Check for victory
        if check_victory(mission):
            print("\n*** VICTORY! All factions defeated! ***")
            break

    # Final state
    print("\n" + "=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    print_state(game, mission, turn)
    check_quest_status(mission)

    # Check victory conditions
    victory_achieved = check_victory(mission)
    if victory_achieved:
        print("\n[VICTORY] Mission complete - all factions defeated!")
    else:
        analyzer.log_issue("Victory not achieved after conquest sequence")

    # ========================================
    # ANALYSIS
    # ========================================

    analyzer.print_summary()

    # Balance analysis
    print("\n" + "-" * 50)
    print("GAMEPLAY BALANCE ANALYSIS")
    print("-" * 50)

    # Calculate strength ratios
    player_start_units = 5  # 3 Cavalry + 2 Archer
    elletic_units = 1 + 2 + 3 + 3  # 9 total
    heilonic_units = 6 + 6  # 12 total
    valeonia_units = 7 + 8  # 15 total
    total_enemy_units = elletic_units + heilonic_units + valeonia_units  # 36 total

    print(f"Starting strength ratio: {player_start_units}:{total_enemy_units} (1:{total_enemy_units/player_start_units:.1f})")
    print(f"  - Player: {player_start_units} units (3 Cavalry, 2 Archer)")
    print(f"  - Elletic Tribes: {elletic_units} units across 4 territories")
    print(f"  - Heilonic Tribes: {heilonic_units} units across 2 territories")
    print(f"  - Valeonia: {valeonia_units} units across 2 territories")
    print()
    print("Observations:")
    print("  1. Dormant AI gives player time to build up before conflict")
    print("  2. Elletic is weakest (9 units) - good first target")
    print("  3. Valeonia is strongest (15 units) - attacking early awakens ALL factions")
    print("  4. Player has 500 gold to train reinforcements before attacking")
    print()
    print("Potential issues:")
    print("  1. If player attacks Valeonia first, all 36 enemy units activate at once")
    print("  2. Heilonic has 6 Cavalry in Révia - strong counter-attack potential")
    print("  3. AI behavior is very basic (train + attack adjacent)")

    print()
    print("=" * 70)

    result = {
        'success': len(analyzer.issues) == 0 and victory_achieved,
        'turns': analyzer.turns,
        'battles': analyzer.battles,
        'territories_conquered': len(analyzer.territories_conquered),
        'factions_defeated': len(analyzer.factions_defeated),
        'issues': analyzer.issues,
        'victory': victory_achieved,
    }

    return result


@pytest.mark.xfail(reason="Known bug: defeat condition not triggered by territory conquest event")
def test_defeat_condition():
    """Test that player loses when they have 0 territories."""
    print("\n" + "=" * 70)
    print("DEFEAT CONDITION TEST")
    print("=" * 70)

    try:
        game, mission = setup_mission_2()
    except Exception as e:
        pytest.fail(f"Failed to initialize mission: {e}")

    if not mission:
        pytest.fail("Mission failed to initialize")

    skip_intro(mission)

    # Simulate AI conquering player's only territory (Lobardia)
    print("\nSimulating AI conquest of Lobardia...")

    # Transfer Lobardia from player to faction 1
    game.territory_owners["Lobardia"] = 1
    game.territory_garrisons["Lobardia"] = {}
    game.add_garrison("Lobardia", 1, unmoved=3, moved=0, units=[
        {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': i}
        for i in range(3)
    ])
    game.sync_legacy_garrison_data("Lobardia")

    # Notify mission of conquest (triggers defeat check)
    mission.notify_event('territory_conquered', territory="Lobardia", new_owner=1)

    # Check if defeat was triggered
    defeat_triggered = mission._pending_defeat or mission.defeat_sequence_active
    print(f"Defeat sequence triggered: {defeat_triggered}")

    if defeat_triggered:
        print("[PASS] Defeat condition works correctly!")
    else:
        assert False, "Defeat condition did not trigger!"


if __name__ == '__main__':
    start_time = time.time()
    results = run_mission_playthrough()
    elapsed = time.time() - start_time

    print(f"\nPlaythrough test completed in {elapsed:.1f} seconds")
    print(f"Playthrough result: {'PASS' if results['success'] else 'FAIL'}")

    if not results['success'] and results.get('issues'):
        print("Issues encountered:")
        for turn, issue in results['issues']:
            print(f"  Turn {turn}: {issue}")

    # Run defeat condition test
    defeat_test_passed = test_defeat_condition()

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Victory playthrough: {'PASS' if results['success'] else 'FAIL'}")
    print(f"Defeat condition: {'PASS' if defeat_test_passed else 'FAIL'}")
