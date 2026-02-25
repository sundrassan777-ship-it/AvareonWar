# -*- coding: utf-8 -*-
"""
Campaign Mission 4 Playthrough Test & Difficulty Analysis
=========================================================

Tests Campaign Mission 4 ("Domination") by:
1. Validating initial setup (territories, buildings, units, gold, hero, flags)
2. Running a simulated playthrough — player conquers EK + Leuse (victory)
3. Testing defeat condition (Regnus Aevencourne killed)
4. Simulating AI turns to verify ramp/defense/attack-only-player logic
5. Deep-diving AI danger: economy projection, unit growth, attack pressure per turn

Usage:
    python tests/test_campaign_mission_4.py
"""

import sys
import os
import time
import traceback
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
from campaign_mission_4 import (
    Mission4, MISSION_4_TERRITORIES, MISSION_4_DISPLAY_NAMES,
    FACTION_TERRITORIES, PLAYER_COLORS, FACTION_NAMES, STARTING_GOLD,
    FACTION_DEFENSE_MIN, TERRITORY_SETUP, _make_units
)

# ============================================================================
# MOCKS
# ============================================================================

class MockScreen:
    def get_width(self): return 1920
    def get_height(self): return 1080
    def get_size(self): return (1920, 1080)


class MockCamera:
    """Mock camera handler matching Game.camera interface."""
    def __init__(self):
        self.offset = [0.0, 0.0]
        self.zoom = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 2.0
    def clamp_to_bounds(self): pass


class MockMainGame:
    """Mock main_game object for testing without pygame display."""
    def __init__(self, game_state):
        self.game_state = game_state
        self.screen = MockScreen()
        self.camera = MockCamera()
        self.camera_offset = [0.0, 0.0]
        self.camera_zoom = 1.0
        self.cached_scaled_map = None
        self.scaled_centers = {}
        self.army_flag_icons = [f"flag_{i}" for i in range(4)]
        self.return_to_campaign = False
        for territory in map_data.get_all_territories():
            self.scaled_centers[territory] = (500, 400)

    def world_to_screen(self, pos): return pos
    def get_screen_size(self): return (1920, 1080)


# ============================================================================
# HELPERS
# ============================================================================

def count_units(game, territory, player_id):
    """Count units a player has in a territory."""
    garrison = game.territory_garrisons.get(territory, {}).get(player_id, {})
    return len(garrison.get('units', []))


def count_all_units(game, player_id):
    """Count total units a player has across all mission territories."""
    total = 0
    for t in MISSION_4_TERRITORIES:
        total += count_units(game, t, player_id)
    return total


def get_player_territories(game, player_id):
    """Get list of territories owned by a player."""
    return [t for t in MISSION_4_TERRITORIES if game.territory_owners.get(t) == player_id]


def get_buildings_in_territory(game, territory):
    """Get dict of buildings in a territory."""
    return game.buildings.get(territory, {})


def force_conquer_territory(game, mission, territory, new_owner=0):
    """Force-conquer a territory by changing ownership and simulating the event.

    Also handles hero death detection (Keeps are destroyed on conquest).
    """
    old_owner = game.territory_owners.get(territory, -1)

    # Kill heroes in Keeps of the conquered territory (mirrors game_state.change_territory_owner)
    if old_owner is not None and old_owner >= 0 and territory in game.buildings:
        for plot_idx, btype in list(game.buildings[territory].items()):
            if btype == 'Keep':
                game.kill_heroes_in_keep(territory, plot_idx, old_owner)

    # Clear old garrison
    if territory in game.territory_garrisons:
        game.territory_garrisons[territory] = {}

    # Transfer ownership
    game.territory_owners[territory] = new_owner

    # Destroy buildings (mirrors battle resolution)
    game.buildings[territory] = {}

    # Add minimal garrison for the new owner
    game.add_garrison(territory, new_owner, unmoved=3, moved=0, units=[
        {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': i, 'xp': 0, 'level': 0}
        for i in range(3)
    ])
    game.sync_legacy_garrison_data(territory)

    # Notify mission
    if mission:
        mission.notify_event('territory_conquered', territory=territory, new_owner=new_owner)

    return old_owner


# ============================================================================
# SETUP
# ============================================================================

def setup_mission():
    """Initialize game state and Mission 4 for testing."""
    print("Loading map data...")
    map_data.load_polygons()

    from game_state import GameState

    print("Creating 4-player game state...")
    game = GameState(
        num_players=4,
        player_is_ai=[False, True, True, True],
        player_ai_difficulty=[0, 0, 0, 0],
        player_teams=[0, 1, 2, 3],
        skip_setup_phase=True,
        victory_condition='Total Conquest'
    )
    game.phase = 'playing'
    game.turn_phase = 'planning'

    print("Creating mock main_game...")
    mock_main = MockMainGame(game)

    print("Creating Mission 4...")
    try:
        mission = Mission4(game, mock_main)
        game.tutorial_mission = mission
        print("[OK] Mission 4 initialized successfully\n")
    except Exception as e:
        print(f"[ERROR] Failed to initialize mission: {e}")
        traceback.print_exc()
        mission = None

    return game, mission, mock_main


def skip_intro(mission):
    """Skip the intro sequence for testing."""
    if not mission:
        return
    mission.intro_active = False
    mission.game_paused = False
    mission.intro_step_index = 999
    mission.timer_visible = True
    mission.transmission_overlay = None
    mission.camera_animation = None


# ============================================================================
# PYTEST FIXTURES
# ============================================================================

@pytest.fixture
def mission_setup():
    """Create a fresh Mission4 game instance for testing."""
    game, mission, mock_main = setup_mission()
    yield game, mission


# ============================================================================
# TEST 1: INITIAL STATE VALIDATION
# ============================================================================

def test_initial_state(mission_setup):
    """Validate all initial conditions are set correctly."""
    game, mission = mission_setup
    print("=" * 70)
    print("TEST 1: INITIAL STATE VALIDATION")
    print("=" * 70)
    errors = []
    warnings = []

    # 1. Check all 21 territories are owned correctly
    print("\n[Checking territory ownership...]")
    for faction_id, territories in FACTION_TERRITORIES.items():
        for t in territories:
            owner = game.territory_owners.get(t, -1)
            if owner != faction_id:
                errors.append(f"  {t}: expected owner {faction_id}, got {owner}")

    owned_count = {0: 0, 1: 0, 2: 0, 3: 0}
    for t in MISSION_4_TERRITORIES:
        owner = game.territory_owners.get(t, -1)
        if owner in owned_count:
            owned_count[owner] += 1
    print(f"  Player 0 (Human):    {owned_count[0]} territories")
    print(f"  Player 1 (EK):       {owned_count[1]} territories")
    print(f"  Player 2 (Leuse):    {owned_count[2]} territories")
    print(f"  Player 3 (Ahtep):    {owned_count[3]} territories")
    total = sum(owned_count.values())
    if total != 21:
        errors.append(f"  Total territories: expected 21, got {total}")

    # 2. Check starting gold
    print("\n[Checking starting gold...]")
    for pid, expected_gold in STARTING_GOLD.items():
        actual = game.player_gold[pid]
        status = "OK" if actual == expected_gold else "FAIL"
        print(f"  Player {pid}: {actual}g (expected {expected_gold}g) [{status}]")
        if actual != expected_gold:
            errors.append(f"  Player {pid} gold: expected {expected_gold}, got {actual}")

    # 3. Check buildings
    print("\n[Checking buildings...]")
    for territory, config in TERRITORY_SETUP.items():
        expected_buildings = config.get("buildings", {})
        actual_buildings = game.buildings.get(territory, {})
        for plot_idx, expected_type in expected_buildings.items():
            actual_type = actual_buildings.get(plot_idx)
            if actual_type != expected_type:
                errors.append(f"  {territory} plot {plot_idx}: expected {expected_type}, got {actual_type}")
    print(f"  Checked {len(TERRITORY_SETUP)} territories")

    # 4. Check unit counts
    print("\n[Checking unit counts...]")
    for faction_id in range(4):
        total = count_all_units(game, faction_id)
        territories = get_player_territories(game, faction_id)
        per_territory = {}
        for t in territories:
            c = count_units(game, t, faction_id)
            per_territory[t] = c
        print(f"  Player {faction_id} ({FACTION_NAMES.get(faction_id, 'Human')}): {total} units")
        for t, c in per_territory.items():
            expected_count = len(TERRITORY_SETUP.get(t, {}).get("units", []))
            status = "OK" if c == expected_count else f"FAIL (expected {expected_count})"
            print(f"    {t}: {c} [{status}]")
            if c != expected_count:
                errors.append(f"  {t} units: expected {expected_count}, got {c}")

    # 5. Check human units are level 2
    print("\n[Checking human unit levels...]")
    for t in FACTION_TERRITORIES[0]:
        garrison = game.territory_garrisons.get(t, {}).get(0, {})
        for unit in garrison.get('units', []):
            if unit.get('level', 0) != 2:
                errors.append(f"  {t} unit {unit.get('type')} id={unit.get('id')}: level={unit.get('level')}, expected 2")
    if not any('level' in e for e in errors):
        print("  All human units are level 2: OK")

    # 6. Check AI units are level 0
    print("\n[Checking AI unit levels...]")
    ai_level_issues = 0
    for faction_id in [1, 2, 3]:
        for t in FACTION_TERRITORIES[faction_id]:
            garrison = game.territory_garrisons.get(t, {}).get(faction_id, {})
            for unit in garrison.get('units', []):
                if unit.get('level', 0) != 0:
                    ai_level_issues += 1
    if ai_level_issues == 0:
        print("  All AI units are level 0: OK")
    else:
        errors.append(f"  {ai_level_issues} AI units have non-zero levels")

    # 7. Check hero assignment
    print("\n[Checking Regnus Aevencourne...]")
    regnus = game.heroes.get(0, {}).get('Regnus Aevencourne')
    if regnus:
        print(f"  Hero found: keep_territory={regnus['keep_territory']}, keep_plot={regnus['keep_plot']}")
        if regnus['keep_territory'] != 'Aelatania':
            errors.append("  Regnus should be at Aelatania")
        if regnus['keep_plot'] != 1:
            errors.append("  Regnus should be at plot 1")
    else:
        errors.append("  Regnus Aevencourne NOT found in player 0 heroes!")

    if 'Regnus Aevencourne' in game.hero_ownership.get(0, set()):
        print("  Hero ownership tracking: OK")
    else:
        errors.append("  Regnus not in hero_ownership")

    # 8. Check display names
    print("\n[Checking display name overrides...]")
    for internal, display in MISSION_4_DISPLAY_NAMES.items():
        actual = map_data.get_display_name(internal)
        status = "OK" if actual == display else f"FAIL (got '{actual}')"
        print(f"  {internal} -> {display} [{status}]")
        if actual != display:
            errors.append(f"  Display name {internal}: expected '{display}', got '{actual}'")

    # 9. Check flag remapping
    print("\n[Checking flag remapping...]")
    if mission and mission.original_flag_icons:
        print("  Flag icons were remapped (original saved for cleanup)")
    else:
        warnings.append("  Flag icon remapping could not be verified (mock flags)")

    # 10. Quest log
    print("\n[Checking quest log...]")
    quests = mission.get_quest_log() if mission else []
    expected_quests = [
        'Conquer the Eastern Kingdoms',
        'Conquer the Confederacy of the Leuse',
        'Regnus Aevencourne in Aelatania must survive',
    ]
    for i, expected in enumerate(expected_quests):
        if i < len(quests):
            actual = quests[i]['text']
            completed = quests[i]['completed']
            status = "OK" if actual == expected and not completed else "FAIL"
            print(f"  [{status}] {actual} (completed={completed})")
        else:
            errors.append(f"  Missing quest {i}: {expected}")

    # 11. Check pre-researched technologies (9 techs, first 3 from each column)
    print("\n[Checking pre-researched technologies...]")
    expected_techs = {
        'tech_0_0', 'tech_0_1', 'tech_0_2',
        'tech_1_0', 'tech_1_1', 'tech_1_2',
        'tech_2_0', 'tech_2_1', 'tech_2_2',
    }
    researched = game.player_tech_researched.get(0, set())
    for tech_id in sorted(expected_techs):
        if tech_id in researched:
            print(f"  {tech_id}: OK")
        else:
            errors.append(f"  Missing pre-researched tech: {tech_id}")
    # Check bonus variables were applied
    if game.player_training_cost_discount[0] != 20:
        errors.append(f"  training_cost_discount: expected 20, got {game.player_training_cost_discount[0]}")
    if game.player_barracks_cost_discount[0] != 25:
        errors.append(f"  barracks_cost_discount: expected 25, got {game.player_barracks_cost_discount[0]}")
    if not game.player_barracks_full_refund[0]:
        errors.append("  barracks_full_refund: expected True")
    if game.player_cavalry_cost_discount[0] != 25:
        errors.append(f"  cavalry_cost_discount: expected 25, got {game.player_cavalry_cost_discount[0]}")
    if game.player_royal_decree_discount[0] != 15:
        errors.append(f"  royal_decree_discount: expected 15, got {game.player_royal_decree_discount[0]}")
    # Check next-tier techs are available
    # tech_1_3 is pre-researched, so next tier in column 1 is tech_1_4
    for next_tech in ['tech_0_3', 'tech_1_4', 'tech_2_3']:
        if next_tech not in game.player_tech_available.get(0, set()):
            errors.append(f"  Next-tier tech not available: {next_tech}")
    print(f"  Tech bonuses applied: OK" if not any('tech' in e.lower() or 'discount' in e.lower() or 'refund' in e.lower() for e in errors[len(errors):]) else "")

    # 12. Check Castle at Aelatania
    print("\n[Checking Castle at Aelatania...]")
    castle = game.castle_upgrades.get('Aelatania', {})
    if castle.get(1):
        print("  Castle at Aelatania plot 1: OK")
    else:
        errors.append("  Castle NOT found at Aelatania plot 1")

    # Summary
    print(f"\n{'='*50}")
    if errors:
        print(f"INITIAL STATE: FAIL ({len(errors)} errors)")
        for e in errors:
            print(f"  {e}")
    else:
        print("INITIAL STATE: ALL CHECKS PASSED")
    if warnings:
        for w in warnings:
            print(f"  Warning: {w}")

    assert len(errors) == 0, f"Initial state validation failed with {len(errors)} errors: {errors}"


# ============================================================================
# TEST 2: VICTORY PLAYTHROUGH
# ============================================================================

def test_victory_playthrough(mission_setup):
    """Simulate player conquering EK + Leuse to achieve victory."""
    game, mission = mission_setup
    print("\n" + "=" * 70)
    print("TEST 2: VICTORY PLAYTHROUGH")
    print("(Conquer EK + Leuse, leave Ahtep alive)")
    print("=" * 70)

    skip_intro(mission)

    # Conquest order: EK territories first, then Leuse
    # Strategic order: work from player's border outward
    ek_targets = [
        "Londia", "Northern Heilonia", "Révia", "Venexia",
        "Lobardia", "Lentria", "Elland", "The Holy Land", "Elletian Isles",
    ]
    leuse_targets = [
        "Valeonia", "Velognia", "Leuse Valley", "Nordica",
    ]

    turn = 0
    victory_triggered = False

    # Phase 1: Conquer Eastern Kingdoms
    print("\n--- Phase 1: Conquering Eastern Kingdoms ---")
    for target in ek_targets:
        turn += 1
        owner = game.territory_owners.get(target, -1)
        if owner == 0:
            continue  # Already ours

        old_owner = force_conquer_territory(game, mission, target, new_owner=0)
        ek_left = len([t for t in FACTION_TERRITORIES[1] if game.territory_owners.get(t) == 1])
        print(f"  Turn {turn}: Conquered {target} (EK territories remaining: {ek_left})")

        if mission.faction_defeated[1]:
            print("  >> Eastern Kingdoms DEFEATED!")
            break

    if not mission.faction_defeated[1]:
        print("  [FAIL] Eastern Kingdoms not defeated after conquering all territories!")
        assert False, "Eastern Kingdoms not defeated after conquering all territories"

    # Check quest log
    if mission.quest_log[0]['completed']:
        print("  [OK] Quest 'Conquer the Eastern Kingdoms' marked complete")
    else:
        print("  [FAIL] Quest not marked complete!")
        assert False, "Quest 'Conquer the Eastern Kingdoms' not marked complete"

    # Victory should NOT trigger yet (Leuse still alive)
    if mission._victory_waiting or mission.victory_sequence_active:
        print("  [FAIL] Victory triggered prematurely (Leuse still alive)!")
        assert False, "Victory triggered prematurely (Leuse still alive)"
    print("  [OK] No premature victory (Leuse still alive)")

    # Phase 2: Conquer Confederation of the Leuse
    print("\n--- Phase 2: Conquering Confederation of the Leuse ---")
    for target in leuse_targets:
        turn += 1
        owner = game.territory_owners.get(target, -1)
        if owner == 0:
            continue

        old_owner = force_conquer_territory(game, mission, target, new_owner=0)
        leuse_left = len([t for t in FACTION_TERRITORIES[2] if game.territory_owners.get(t) == 2])
        print(f"  Turn {turn}: Conquered {target} (Leuse territories remaining: {leuse_left})")

        if mission.faction_defeated[2]:
            print("  >> Confederation of the Leuse DEFEATED!")
            break

    if not mission.faction_defeated[2]:
        print("  [FAIL] Leuse not defeated!")
        assert False, "Leuse not defeated after conquering all territories"

    if mission.quest_log[1]['completed']:
        print("  [OK] Quest 'Conquer the Confederacy of the Leuse' marked complete")
    else:
        print("  [FAIL] Quest not marked complete!")
        assert False, "Quest 'Conquer the Confederacy of the Leuse' not marked complete"

    # Victory should trigger now
    victory_triggered = mission._victory_waiting or mission.victory_sequence_active or mission._pending_victory
    if victory_triggered:
        print(f"\n  [OK] VICTORY triggered after defeating EK + Leuse!")
        print(f"  Game winner: {game.winner}, phase: {game.phase}")
    else:
        print("  [FAIL] Victory NOT triggered!")
        assert False, "Victory not triggered after defeating EK + Leuse"

    # Verify Ahtep Empire is still alive (not required for victory)
    ahtep_territories = [t for t in FACTION_TERRITORIES[3] if game.territory_owners.get(t) == 3]
    print(f"\n  Ahtep Empire still alive: {len(ahtep_territories)} territories (correctly NOT required)")
    if not mission.faction_defeated[3]:
        print("  [OK] Ahtep Empire correctly NOT defeated")
    else:
        print("  [WARN] Ahtep Empire got defeated (shouldn't happen in this test)")

    # Check Regnus survived
    regnus_alive = 0 in game.heroes and 'Regnus Aevencourne' in game.heroes[0]
    print(f"  Regnus Aevencourne alive: {regnus_alive}")

    print(f"\nVICTORY PLAYTHROUGH: PASS (completed in {turn} turns)")


# ============================================================================
# TEST 3: DEFEAT CONDITION (Regnus dies)
# ============================================================================

def test_defeat_regnus_killed():
    """Test that defeat triggers when Regnus Aevencourne's Keep is conquered."""
    print("\n" + "=" * 70)
    print("TEST 3: DEFEAT CONDITION — Regnus Aevencourne Killed")
    print("=" * 70)

    game, mission, mock_main = setup_mission()
    if not mission:
        print("[ERROR] Mission failed to initialize")
        assert False, "Mission failed to initialize"

    skip_intro(mission)

    # Verify Regnus exists
    regnus = game.heroes.get(0, {}).get('Regnus Aevencourne')
    if not regnus:
        print("[FAIL] Regnus not found at start!")
        assert False, "Regnus not found at start"
    print(f"  Regnus at {regnus['keep_territory']} (plot {regnus['keep_plot']})")

    # Simulate AI conquering Aelatania (where Regnus's Keep is)
    print("  Simulating AI conquest of Aelatania...")
    force_conquer_territory(game, mission, "Aelatania", new_owner=3)

    # Check hero was killed
    regnus_alive = 0 in game.heroes and 'Regnus Aevencourne' in game.heroes[0]
    print(f"  Regnus alive after conquest: {regnus_alive}")

    # Check defeat triggered
    defeat_triggered = (
        mission._defeat_waiting or
        mission._pending_defeat or
        mission.defeat_sequence_active
    )
    print(f"  Defeat sequence triggered: {defeat_triggered}")

    if defeat_triggered and not regnus_alive:
        print("\n  [PASS] Defeat correctly triggered when Regnus was killed!")
    else:
        if regnus_alive:
            print("  [FAIL] Regnus survived Aelatania conquest (hero kill didn't fire)")
        if not defeat_triggered:
            print("  [FAIL] Defeat was NOT triggered!")
        assert False, "Defeat not correctly triggered when Regnus was killed"


# ============================================================================
# TEST 4: DEFEAT DOES NOT TRIGGER FROM TERRITORY LOSS (without hero death)
# ============================================================================

def test_no_defeat_from_territory_loss():
    """Test that losing territories (but keeping Regnus alive) does NOT trigger defeat."""
    print("\n" + "=" * 70)
    print("TEST 4: NO DEFEAT FROM TERRITORY LOSS (Regnus survives)")
    print("=" * 70)

    game, mission, mock_main = setup_mission()
    if not mission:
        print("[ERROR] Mission failed to initialize")
        assert False, "Mission failed to initialize"

    skip_intro(mission)

    # Conquer Courtieux and Duchy of Daurels (player loses 2/3 territories)
    # But Aelatania (with Regnus) survives
    print("  Simulating AI conquest of Courtieux...")
    force_conquer_territory(game, mission, "Courtieux", new_owner=1)

    print("  Simulating AI conquest of Duchy of Daurels...")
    force_conquer_territory(game, mission, "Duchy of Daurels", new_owner=2)

    # Player should still have Aelatania with Regnus alive
    player_territories = get_player_territories(game, 0)
    regnus_alive = 0 in game.heroes and 'Regnus Aevencourne' in game.heroes[0]
    defeat_triggered = (
        mission._defeat_waiting or
        mission._pending_defeat or
        mission.defeat_sequence_active
    )

    print(f"  Player territories: {player_territories}")
    print(f"  Regnus alive: {regnus_alive}")
    print(f"  Defeat triggered: {defeat_triggered}")

    if regnus_alive and not defeat_triggered:
        print("\n  [PASS] No defeat while Regnus lives (even with only 1 territory)")
    else:
        print("\n  [FAIL] Something went wrong")
        assert False, "Defeat triggered incorrectly or Regnus died unexpectedly"


# ============================================================================
# TEST 5: AI BEHAVIOR SIMULATION
# ============================================================================

def test_ai_behavior():
    """Test AI turn execution: ramp, defense minimums, attack-only-player-0."""
    print("\n" + "=" * 70)
    print("TEST 5: AI BEHAVIOR SIMULATION")
    print("=" * 70)

    game, mission, mock_main = setup_mission()
    if not mission:
        print("[ERROR] Mission failed to initialize")
        assert False, "Mission failed to initialize"

    skip_intro(mission)

    errors = []

    # Simulate several AI turns for each faction
    for faction_id in [1, 2, 3]:
        print(f"\n--- Faction {faction_id}: {FACTION_NAMES[faction_id]} ---")
        starting_gold = game.player_gold[faction_id]
        starting_units = count_all_units(game, faction_id)

        for turn in range(1, 6):
            game.current_player = faction_id
            mission._execute_faction_ai(faction_id)

            current_gold = game.player_gold[faction_id]
            current_units = count_all_units(game, faction_id)
            turn_count = mission.faction_turn_count[faction_id]

            print(f"  Turn {turn}: count={turn_count}, gold={current_gold}, units={current_units}")

        # Verify turn count
        expected_count = 5
        actual_count = mission.faction_turn_count[faction_id]
        if actual_count != expected_count:
            errors.append(f"  {FACTION_NAMES[faction_id]}: turn count={actual_count}, expected {expected_count}")

    # Reset current player
    game.current_player = 0

    # Check that AI factions did NOT attack each other (only player 0)
    print("\n--- Checking AI-vs-AI territory ownership ---")
    # Verify no AI faction lost territory to another AI faction
    for t in MISSION_4_TERRITORIES:
        owner = game.territory_owners.get(t, -1)
        original_owner = TERRITORY_SETUP.get(t, {}).get("owner", -1)
        if original_owner > 0 and owner > 0 and owner != original_owner:
            errors.append(f"  {t}: changed from player {original_owner} to {owner} (AI-vs-AI attack!)")

    if not any('AI-vs-AI' in e for e in errors):
        print("  [OK] No AI-vs-AI territory changes detected")

    # Summary
    print(f"\n{'='*50}")
    if errors:
        print(f"AI BEHAVIOR: FAIL ({len(errors)} errors)")
        for e in errors:
            print(f"  {e}")
        assert False, f"AI behavior failed with {len(errors)} errors: {errors}"
    else:
        print("AI BEHAVIOR: ALL CHECKS PASSED")


# ============================================================================
# TEST 6: ACTION GATING
# ============================================================================

def test_action_gating():
    """Test that Mission 4 correctly blocks/allows actions."""
    print("\n" + "=" * 70)
    print("TEST 6: ACTION GATING")
    print("=" * 70)

    game, mission, mock_main = setup_mission()
    if not mission:
        assert False, "Mission failed to initialize"

    skip_intro(mission)
    errors = []

    # Hero training should be blocked
    allowed = mission.is_action_allowed('train_hero')
    print(f"  train_hero: allowed={allowed} (expected False)")
    if allowed:
        errors.append("train_hero should be blocked")

    # Keep building is intentionally allowed in Mission 4
    # (unlike Mission 2 which blocks it; see campaign_mission_4.py is_action_allowed)
    allowed = mission.is_action_allowed('build', building_type='Keep')
    print(f"  build Keep: allowed={allowed} (expected True)")
    if not allowed:
        errors.append("build Keep should be allowed in Mission 4")

    # Normal building should be allowed
    allowed = mission.is_action_allowed('build', building_type='Barracks')
    print(f"  build Barracks: allowed={allowed} (expected True)")
    if not allowed:
        errors.append("build Barracks should be allowed")

    # Movement should be allowed
    allowed = mission.is_action_allowed('move')
    print(f"  move: allowed={allowed} (expected True)")
    if not allowed:
        errors.append("move should be allowed")

    # should_hide_hero_training
    hidden = mission.should_hide_hero_training()
    print(f"  should_hide_hero_training: {hidden} (expected True)")
    if not hidden:
        errors.append("should_hide_hero_training should return True")

    if errors:
        print(f"\nACTION GATING: FAIL ({len(errors)} errors)")
        assert False, f"Action gating failed with {len(errors)} errors: {errors}"
    print("\nACTION GATING: ALL CHECKS PASSED")


# ============================================================================
# DEEP DIVE: AI DANGER ANALYSIS
# ============================================================================

def deep_dive_ai_danger():
    """Analyze AI economy, unit growth, and attack pressure over time."""
    print("\n" + "=" * 70)
    print("DEEP DIVE: AI DANGER ANALYSIS")
    print("=" * 70)

    # ==========================================
    # Section A: Starting Military Strength
    # ==========================================
    print("\n--- A. STARTING MILITARY STRENGTH ---\n")

    faction_units = {}
    for faction_id in range(4):
        units_by_type = {}
        total = 0
        for t in FACTION_TERRITORIES.get(faction_id, []):
            config = TERRITORY_SETUP.get(t, {})
            for unit in config.get("units", []):
                utype = unit['type']
                units_by_type[utype] = units_by_type.get(utype, 0) + 1
                total += 1
        faction_units[faction_id] = (total, units_by_type)

    for faction_id in range(4):
        total, by_type = faction_units[faction_id]
        name = FACTION_NAMES.get(faction_id, "Human")
        level = 3 if faction_id == 0 else 0
        effective_mult = 1.0 + 0.15 * level  # veterancy bonus
        effective_str = total * effective_mult
        breakdown = ", ".join(f"{c}x {t}" for t, c in sorted(by_type.items(), key=lambda x: -x[1]))
        print(f"  Player {faction_id} ({name}):")
        print(f"    Total: {total} units (level {level}, effective ~{effective_str:.1f} strength)")
        print(f"    Composition: {breakdown}")
        print(f"    Territories: {len(FACTION_TERRITORIES.get(faction_id, []))}")

    # ==========================================
    # Section B: Starting Economy
    # ==========================================
    print("\n--- B. STARTING ECONOMY ---\n")

    from map_data import get_territory_income

    for faction_id in range(4):
        name = FACTION_NAMES.get(faction_id, "Human")
        gold = STARTING_GOLD.get(faction_id, 0)
        territories = FACTION_TERRITORIES.get(faction_id, [])
        base_income = sum(get_territory_income(t) for t in territories)

        # Count income-boosting buildings (Farm = +30g, Mine = +20g)
        farm_count = 0
        mine_count = 0
        barracks_count = 0
        keep_count = 0
        for t in territories:
            config = TERRITORY_SETUP.get(t, {})
            for plot_idx, btype in config.get("buildings", {}).items():
                if btype == 'Farm':
                    farm_count += 1
                elif btype == 'Mine':
                    mine_count += 1
                elif btype == 'Barracks':
                    barracks_count += 1
                elif btype == 'Keep':
                    keep_count += 1

        # Estimate income per turn (base + farm bonus)
        # Farm adds +30g per turn, Mine adds +20g per turn (from game mechanics)
        farm_income = farm_count * 30
        mine_income = mine_count * 20
        total_income = base_income + farm_income + mine_income

        print(f"  Player {faction_id} ({name}):")
        print(f"    Starting gold: {gold}g")
        print(f"    Base territory income: {base_income}g/turn")
        print(f"    Farms: {farm_count} (+{farm_income}g/turn)")
        print(f"    Mines: {mine_count} (+{mine_income}g/turn)")
        print(f"    Barracks: {barracks_count}")
        print(f"    Keeps: {keep_count}")
        print(f"    Estimated income: ~{total_income}g/turn")

    # ==========================================
    # Section C: Unit Production Capacity
    # ==========================================
    print("\n--- C. UNIT PRODUCTION CAPACITY ---\n")

    # Cost reference
    unit_costs = {'Swordsman': 25, 'Archer': 20, 'Pikeman': 30, 'Cavalry': 40}
    avg_unit_cost = sum(unit_costs.values()) / len(unit_costs)

    for faction_id in range(4):
        name = FACTION_NAMES.get(faction_id, "Human")
        territories = FACTION_TERRITORIES.get(faction_id, [])
        barracks_count = 0
        for t in territories:
            config = TERRITORY_SETUP.get(t, {})
            for plot_idx, btype in config.get("buildings", {}).items():
                if btype == 'Barracks':
                    barracks_count += 1

        gold = STARTING_GOLD.get(faction_id, 0)
        base_income = sum(get_territory_income(t) for t in territories)
        farm_count = sum(1 for t in territories
                         for b in TERRITORY_SETUP.get(t, {}).get("buildings", {}).values()
                         if b == 'Farm')
        mine_count = sum(1 for t in territories
                         for b in TERRITORY_SETUP.get(t, {}).get("buildings", {}).values()
                         if b == 'Mine')
        total_income = base_income + farm_count * 30 + mine_count * 20

        # How many units can be trained per turn (limited by barracks AND gold)
        max_per_turn_barracks = barracks_count  # 1 unit per barracks per turn
        max_per_turn_gold = total_income / avg_unit_cost  # limited by income
        actual_per_turn = min(max_per_turn_barracks, max_per_turn_gold)

        print(f"  Player {faction_id} ({name}):")
        print(f"    Barracks: {barracks_count} (max {barracks_count} units/turn)")
        print(f"    Income: ~{total_income}g/turn -> can afford ~{max_per_turn_gold:.1f} units/turn (avg cost {avg_unit_cost:.0f}g)")
        print(f"    Effective production: ~{actual_per_turn:.1f} units/turn")

    # ==========================================
    # Section D: AI Ramp Analysis
    # ==========================================
    print("\n--- D. AI RAMP ANALYSIS ---\n")
    print("  Turn N: AI faction can send max N attacks + N reinforcements")
    print("  Defense minimums: EK >= 1, Leuse >= 3, Ahtep >= 5\n")

    for faction_id in [1, 2, 3]:
        name = FACTION_NAMES.get(faction_id)
        territories = FACTION_TERRITORIES.get(faction_id, [])
        total_units, _ = faction_units[faction_id]
        defense_min = FACTION_DEFENSE_MIN.get(faction_id, 1)
        gold = STARTING_GOLD.get(faction_id, 0)
        base_income = sum(get_territory_income(t) for t in territories)
        farm_count = sum(1 for t in territories
                         for b in TERRITORY_SETUP.get(t, {}).get("buildings", {}).values()
                         if b == 'Farm')
        mine_count = sum(1 for t in territories
                         for b in TERRITORY_SETUP.get(t, {}).get("buildings", {}).values()
                         if b == 'Mine')
        total_income = base_income + farm_count * 30 + mine_count * 20
        barracks_count = sum(1 for t in territories
                             for b in TERRITORY_SETUP.get(t, {}).get("buildings", {}).values()
                             if b == 'Barracks')

        print(f"  {name} (Player {faction_id}):")
        print(f"    Start: {total_units} units, {gold}g, income ~{total_income}g/turn")
        print(f"    Defense min: {defense_min} units at border territories")
        print(f"    Barracks: {barracks_count}")

        # Find border territories (adjacent to player 0)
        player_0_territories = set(FACTION_TERRITORIES[0])
        border_count = 0
        for t in territories:
            neighbors = map_data.get_neighbors(t)
            if any(n in player_0_territories for n in neighbors):
                border_count += 1

        print(f"    Border territories (adj to player 0): {border_count}")
        print(f"    Min reserved for defense: {border_count * defense_min} units")

        # Project unit growth over 10 turns
        projected_units = total_units
        projected_gold = gold
        print(f"    Turn projection:")
        for turn in range(1, 11):
            # Income
            projected_gold += total_income
            # Training (1 unit per barracks, if affordable)
            trainable = min(barracks_count, int(projected_gold / avg_unit_cost))
            projected_units += trainable
            projected_gold -= trainable * avg_unit_cost
            # Available for attack = total - reserved
            attackable = max(0, projected_units - border_count * defense_min)
            # But capped to N attacks on turn N
            attacks_possible = min(turn, border_count)  # Can't attack from more territories than borders
            print(f"      Turn {turn:2d}: ~{projected_units:3d} units, "
                  f"~{int(projected_gold):5d}g, "
                  f"attackable={attackable:3d}, "
                  f"max_orders={turn}")
        print()

    # ==========================================
    # Section E: Player Border Exposure
    # ==========================================
    print("\n--- E. PLAYER BORDER EXPOSURE ---\n")

    player_territories = FACTION_TERRITORIES[0]
    for t in player_territories:
        neighbors = map_data.get_neighbors(t)
        enemy_neighbors = [n for n in neighbors if n in MISSION_4_TERRITORIES and
                           TERRITORY_SETUP.get(n, {}).get("owner", -1) != 0]
        config = TERRITORY_SETUP.get(t, {})
        units = len(config.get("units", []))
        buildings = config.get("buildings", {})
        has_keep = 'Keep' in buildings.values()
        print(f"  {t}: {units} units (level 2), Keep={has_keep}")
        for en in enemy_neighbors:
            en_owner = TERRITORY_SETUP.get(en, {}).get("owner", -1)
            en_units = len(TERRITORY_SETUP.get(en, {}).get("units", []))
            en_faction = FACTION_NAMES.get(en_owner, "?")
            print(f"    -> {en}: {en_units} units ({en_faction})")

    # ==========================================
    # Section F: Threat Summary
    # ==========================================
    print("\n--- F. THREAT SUMMARY ---\n")

    human_total, human_by_type = faction_units[0]
    human_effective = human_total * 1.30  # level 2 = +30%

    print(f"  Human effective strength: {human_total} units x 1.30 (level 2) = ~{human_effective:.0f}")
    print(f"  Human starting gold: {STARTING_GOLD[0]}g")
    print()

    for faction_id in [1, 2, 3]:
        name = FACTION_NAMES.get(faction_id)
        total, by_type = faction_units[faction_id]
        gold = STARTING_GOLD.get(faction_id, 0)
        defense_min = FACTION_DEFENSE_MIN.get(faction_id, 1)

        # Immediate threat: units in territories adjacent to player 0
        immediate_threat = 0
        for t in FACTION_TERRITORIES.get(faction_id, []):
            neighbors = map_data.get_neighbors(t)
            if any(n in set(FACTION_TERRITORIES[0]) for n in neighbors):
                immediate_threat += len(TERRITORY_SETUP.get(t, {}).get("units", []))

        print(f"  {name}:")
        print(f"    Total: {total} units (level 0)")
        print(f"    Starting gold: {gold}g")
        print(f"    Immediate border threat: {immediate_threat} units")
        print(f"    Defense min: {defense_min}/territory")
        print(f"    Danger rating: ", end="")

        # Rate danger
        if faction_id == 3:
            print("EXTREME (5000g = instant army, 5-unit defense min)")
        elif faction_id == 2:
            print("HIGH (250g start, 3-unit defense, 8 starting units near border)")
        else:
            print("MODERATE (100g start, 1-unit defense, 9 territories but spread thin)")

    # ==========================================
    # Section G: Difficulty Assessment
    # ==========================================
    print("\n--- G. DIFFICULTY ASSESSMENT ---\n")

    total_enemy_units = sum(faction_units[f][0] for f in [1, 2, 3])
    total_enemy_effective = total_enemy_units  # level 0

    print(f"  Overall unit ratio: {human_total} (human, eff ~{human_effective:.0f}) vs {total_enemy_units} (AI, eff {total_enemy_effective})")
    print(f"  Veterancy advantage: human units are 30% stronger (level 2)")
    print(f"  Adjusted ratio: ~{human_effective:.0f} vs ~{total_enemy_effective} = {human_effective/total_enemy_effective:.2f}x")
    print()
    print("  Key difficulty factors:")
    print("    1. THREE-FRONT WAR: Player borders 3 different factions simultaneously")
    print("    2. REGNUS MUST SURVIVE: Can't lose Aelatania — forces defensive play")
    print(f"    3. AHTEP'S 5000g WAR CHEST: Can instantly train ~{int(5000/avg_unit_cost)} units")
    print(f"    4. AI RAMP: Pressure builds each turn (turn 10 = up to 10 attacks)")
    print("    5. AI NEVER FIGHTS EACH OTHER: All 3 factions focus solely on player")
    print("    6. ECONOMY: Player has 200g start, enemies collectively have 5350g")
    print()
    print("  Mitigating factors:")
    print("    1. Level 2 veterans (+30% strength) — worth ~1.30x in combat")
    print("    1b. 9 pre-researched techs: -20% infantry, -25% cavalry, -25% barracks, +30s planning, +35 command, -15% Keep/Hero")
    print("    1c. Castle at Aelatania unlocks tier 4+ tech research from turn 1")
    print("    2. AI ramp starts slow (turn 1 = only 1 attack)")
    print("    3. Player can build/train freely while AI ramps up")
    print("    4. Regnus has Safe Haven (retreating units) and Reinforce (2 free Swordsmen)")
    print("    5. Scavenge the Fallen gives 30g per lost battle")
    print("    6. Victory only requires defeating 2/3 factions (can ignore Ahtep)")
    print()

    # Overall difficulty estimate
    print("  ESTIMATED DIFFICULTY: HARD")
    print("    - Early game: Manageable (AI ramp is slow, veterans dominate)")
    print("    - Mid game: Challenging (multiple fronts, Ahtep's gold kicks in)")
    print("    - Late game: Critical (10+ attacks/turn from each faction)")
    print("    - Win strategy: Rush EK fast (weakest), then Leuse before Ahtep snowballs")
    print("    - Lose condition: Getting greedy — must always defend Aelatania/Regnus")


# ============================================================================
# MAIN
# ============================================================================

def main():
    start_time = time.time()

    print("=" * 70)
    print("CAMPAIGN MISSION 4 — FULL TEST SUITE & ANALYSIS")
    print("=" * 70)

    # Setup once for initial tests
    game, mission, mock_main = setup_mission()
    if not mission:
        print("[FATAL] Could not initialize Mission 4")
        return

    results = {}

    # Test 1: Initial state
    results['initial_state'] = test_initial_state(game, mission)

    # Test 2: Victory playthrough (modifies game state)
    results['victory'] = test_victory_playthrough(game, mission)

    # Test 3: Defeat (Regnus killed) — fresh instance
    results['defeat_regnus'] = test_defeat_regnus_killed()

    # Test 4: No defeat from territory loss — fresh instance
    results['no_defeat_territory_loss'] = test_no_defeat_from_territory_loss()

    # Test 5: AI behavior — fresh instance
    game2, mission2, _ = setup_mission()
    if mission2:
        skip_intro(mission2)
        results['ai_behavior'] = test_ai_behavior()

    # Test 6: Action gating — fresh instance
    results['action_gating'] = test_action_gating()

    # Deep dive
    deep_dive_ai_danger()

    # Final results
    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    all_pass = True
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")
        if not passed:
            all_pass = False

    print(f"\nCompleted in {elapsed:.1f}s")
    print(f"Overall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")

    # Cleanup
    map_data.clear_enabled_territories()
    map_data.clear_territory_display_names()
    map_data.set_tutorial_mission(None)

    return all_pass


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
