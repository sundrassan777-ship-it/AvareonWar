# -*- coding: utf-8 -*-
"""
Campaign Mission 3 Playthrough Test
====================================

Tests and analyzes Campaign Mission 3 ("Western Expansion") by:
1. Playing through the mission with simulated player actions
2. Validating alliance formation, betrayal trigger, awakening mechanics
3. Testing defeat condition (lose Zjoal Islands capital)
4. Providing analysis of gameplay balance and potential issues

Usage:
    python tests/test_campaign_mission_3.py
"""

import sys
import os
import time
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
import traceback

# Territory configuration (from campaign_mission_3.py)
FACTION_NAMES = {
    0: "Human Player",
    1: "Kingdom of Affrancia",
    2: "Warlords of Nordia",
    3: "Uhmayyan Empiurate",
}

FACTION_TERRITORIES = {
    0: ["Zjoal Islands"],
    1: ["Lunedale", "Free Cities", "Affrancian Uplands", "March of Auverne",
        "Vense", "Carnae", "Cualus", "Orlais", "Orhas"],
    2: ["Damlére", "Role", "Vice", "Oucine", "Daomea", "Espoia", "Nefrid",
        "Conda", "Ahara", "Cinto", "Odatria", "Mose", "Riar", "Ajuna"],
    3: ["Linan", "Vianaa", "Osana", "Lamacia", "Aunon", "Fahlaan Dunes",
        "Leimarch", "Liadnon", "Ahtep", "Sordia", "Anodia"],
}


class MissionAnalyzer:
    """Tracks and analyzes mission playthrough."""

    def __init__(self):
        self.turns = 0
        self.battles = 0
        self.territories_conquered = []
        self.issues = []
        self.events = []
        self.awakenings = []
        self.faction_defeats = []

    def log_event(self, event_type, details):
        self.events.append((self.turns, event_type, details))

    def log_issue(self, issue):
        self.issues.append((self.turns, issue))


class MockScreen:
    """Mock pygame screen for testing."""

    def get_width(self):
        return 1920

    def get_height(self):
        return 1080

    def get_size(self):
        return (1920, 1080)


class MockMainGame:
    """Mock main_game object for testing without pygame display."""

    def __init__(self, game_state):
        self.game_state = game_state
        self.camera = MockCamera()
        self.screen = MockScreen()
        self.scaled_centers = {}
        self.army_flag_icons = {0: None, 1: None, 2: None, 3: None}

        for territory in map_data.get_all_territories():
            self.scaled_centers[territory] = (500, 400)

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
        pass


def setup_mission_3():
    """Initialize game and mission for testing."""
    print("Loading map data...")
    map_data.load_polygons()

    from game_state import GameState
    from campaign_mission_3 import Mission3

    print("Creating 4-player game...")
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

    print("Creating Mission 3...")
    try:
        mission = Mission3(game, main_game=mock_main)
        print("[MISSION3] Mission 3 initialized successfully")
    except Exception as e:
        print(f"  Error initializing mission: {e}")
        traceback.print_exc()
        mission = None

    return game, mission


def skip_intro(mission):
    """Skip the intro sequence."""
    if not mission:
        return
    mission.intro_active = False
    mission.game_paused = False
    mission.timer_visible = True
    if mission.camera_animation:
        mission.camera_animation.active = False
        mission.camera_animation = None
    mission.transmission_overlay = None
    print("[TEST] Intro sequence skipped")


def get_faction_state(game, mission):
    """Get faction states for display."""
    state = {}
    for faction_id in range(4):
        territories = [t for t, owner in game.territory_owners.items() if owner == faction_id]
        total_armies = 0
        for t in territories:
            garrison = game.territory_garrisons.get(t, {}).get(faction_id, {})
            total_armies += len(garrison.get('units', []))

        # Determine status
        if faction_id == 0:
            status = ""
        elif mission and mission.faction_defeated.get(faction_id, False):
            status = " [DEFEATED]"
        elif faction_id == 3 and mission and mission.alliance_formed and not mission.betrayal_triggered:
            status = " [ALLIED]"
        elif faction_id == 3 and mission and mission.betrayal_triggered:
            status = " [HOSTILE - BETRAYED]"
        elif faction_id == 2 and mission and not mission.nordia_awakened:
            status = " [SEMI-DORMANT]"
        elif mission and mission.faction_awakened.get(faction_id, True):
            status = " [ACTIVE]"
        else:
            status = " [DORMANT]"

        state[faction_id] = {
            'territories': len(territories),
            'armies': total_armies,
            'territory_names': territories,
            'gold': game.player_gold[faction_id],
            'status': status,
        }
    return state


def print_state(game, mission, label):
    """Print current game state."""
    state = get_faction_state(game, mission)
    print(f"\n--- {label} ---")
    for faction_id in sorted(state.keys()):
        s = state[faction_id]
        name = FACTION_NAMES.get(faction_id, f"Player {faction_id}")
        print(f"  {name}: {s['territories']} territories, {s['armies']} armies, {s['gold']}g{s['status']}")
        if s['territory_names'] and s['territories'] <= 5:
            print(f"    Territories: {', '.join(sorted(s['territory_names']))}")


def print_quest_status(mission):
    """Print current quest status."""
    if not mission:
        return
    print("  Quest Log:")
    for quest in mission.quest_log:
        status = "[X]" if quest['completed'] else "[ ]"
        print(f"    {status} {quest['text']}")


def force_conquer_territory(game, mission, territory, new_owner, analyzer):
    """Conquer a territory for testing."""
    old_owner = game.territory_owners.get(territory, -1)

    # Clear old garrison
    if territory in game.territory_garrisons:
        if old_owner in game.territory_garrisons.get(territory, {}):
            game.territory_garrisons[territory].pop(old_owner, None)

    # Transfer ownership
    game.territory_owners[territory] = new_owner

    # Add garrison for new owner
    game.add_garrison(territory, new_owner, unmoved=3, moved=0, units=[
        {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': i}
        for i in range(3)
    ])
    game.sync_legacy_garrison_data(territory)

    analyzer.territories_conquered.append((analyzer.turns, territory))
    analyzer.battles += 1

    old_name = FACTION_NAMES.get(old_owner, f"Player {old_owner}")
    new_name = FACTION_NAMES.get(new_owner, f"Player {new_owner}")
    print(f"  [BATTLE] {new_name} conquers {territory} from {old_name}")

    # Notify mission
    if mission:
        mission.notify_event('territory_conquered', territory=territory, new_owner=new_owner, old_owner=old_owner)
        # Simulate turn_start to trigger territory count checks (happens each turn in real game)
        mission.notify_event('turn_start', player_index=0)


def count_faction_units(game, faction_id):
    """Count total units for a faction."""
    total = 0
    for territory, owner in game.territory_owners.items():
        if owner == faction_id:
            garrison = game.territory_garrisons.get(territory, {}).get(faction_id, {})
            total += len(garrison.get('units', []))
    return total


def get_garrison_units(game, territory, owner):
    """Get unit list for a garrison."""
    garrison = game.territory_garrisons.get(territory, {}).get(owner, {})
    return garrison.get('units', [])


def analyze_border_threats(game, player_id, enemy_id, enemy_name):
    """Analyze which enemy territories border the player and the threat level."""
    print(f"\n  --- {enemy_name} Border Threat Analysis ---")

    player_territories = [t for t, o in game.territory_owners.items() if o == player_id]
    enemy_territories = [t for t, o in game.territory_owners.items() if o == enemy_id]

    border_threats = []
    for enemy_t in enemy_territories:
        neighbors = map_data.get_neighbors(enemy_t)
        adjacent_player = [n for n in neighbors if n in player_territories]
        if adjacent_player:
            units = get_garrison_units(game, enemy_t, enemy_id)
            unit_types = {}
            for u in units:
                unit_types[u['type']] = unit_types.get(u['type'], 0) + 1
            composition = ", ".join(f"{count} {t}" for t, count in unit_types.items()) if units else "empty"
            border_threats.append((enemy_t, len(units), composition, adjacent_player))

    if not border_threats:
        print("    No border territories (no direct threat)")
        return []

    # Sort by army count descending
    border_threats.sort(key=lambda x: x[1], reverse=True)

    total_border_units = sum(t[1] for t in border_threats)
    print(f"    Border territories: {len(border_threats)}, Total border units: {total_border_units}")
    for enemy_t, count, comp, targets in border_threats:
        target_str = ", ".join(targets)
        print(f"    {enemy_t}: {count} units ({comp}) -> can attack: [{target_str}]")

    return border_threats


def simulate_ai_attacks(game, mission, enemy_id, enemy_name, border_threats, analyzer):
    """Simulate AI counter-attacks from border territories."""
    attacks = []
    for enemy_t, count, comp, targets in border_threats:
        if count == 0:
            continue

        # AI sends half of ready units (mission restriction)
        attackers = count // 2
        if attackers == 0 and count > 0:
            attackers = 1  # At least 1 if they have units

        # Pick a target (weakest player garrison)
        best_target = None
        best_defense = 999
        for target in targets:
            defender_units = get_garrison_units(game, target, 0)
            if len(defender_units) < best_defense:
                best_defense = len(defender_units)
                best_target = target

        if best_target and attackers > 0:
            attacks.append((enemy_t, best_target, attackers, count, best_defense))

    if not attacks:
        print(f"    {enemy_name}: No attacks possible (empty borders)")
        return

    print(f"\n  --- {enemy_name} Simulated Counter-attacks ---")
    for from_t, to_t, attackers, total, defenders in attacks:
        outcome = "LIKELY WIN" if attackers > defenders else ("CONTEST" if attackers == defenders else "LIKELY LOSE")
        print(f"    {from_t} -> {to_t}: {attackers}/{total} units vs {defenders} defenders [{outcome}]")
        analyzer.log_event("ai_attack", f"{enemy_name}: {from_t} -> {to_t} ({attackers} vs {defenders})")


def run_mission_playthrough():
    """Run a complete mission playthrough with strategic analysis."""
    print("=" * 70)
    print("CAMPAIGN MISSION 3 - PLAYTHROUGH ANALYSIS")
    print("Western Expansion")
    print("=" * 70)
    print()

    analyzer = MissionAnalyzer()

    try:
        game, mission = setup_mission_3()
    except Exception as e:
        print(f"[ERROR] Failed to initialize mission: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

    if not mission:
        print("[ERROR] Mission failed to initialize")
        return {'success': False, 'error': 'Mission init failed'}

    skip_intro(mission)

    # Print initial state
    print_state(game, mission, "TURN 0 STATE")
    print_quest_status(mission)

    # ========================================
    # INITIAL VALIDATION
    # ========================================

    print("\n--- INITIAL VALIDATION ---")
    errors = []

    # Check player starting conditions
    if game.territory_owners.get("Zjoal Islands") != 0:
        errors.append("Player should own Zjoal Islands")
    if game.player_gold[0] != 500:
        errors.append(f"Player should have 500 gold, has {game.player_gold[0]}")

    # Check player has 14 units
    player_units = count_faction_units(game, 0)
    if player_units != 14:
        errors.append(f"Player should have 14 units, has {player_units}")

    # Check hero assigned
    if 0 in game.heroes and "Serthus Diarcess" in game.heroes[0]:
        hero = game.heroes[0]["Serthus Diarcess"]
        if hero['keep_territory'] != "Zjoal Islands":
            errors.append(f"Serthus should be in Zjoal Islands, is in {hero['keep_territory']}")
    else:
        errors.append("Serthus Diarcess not assigned to player")

    # Check factions
    for faction_id, territories in FACTION_TERRITORIES.items():
        for t in territories:
            if game.territory_owners.get(t) != faction_id:
                errors.append(f"{t} should be owned by faction {faction_id}")

    # Check Affrancia active, Nordia semi-dormant, Uhmayya dormant
    if not mission.faction_awakened.get(1, False):
        errors.append("Affrancia should be active from start")
    if mission.nordia_awakened:
        errors.append("Nordia should be semi-dormant at start")
    if mission.faction_awakened.get(3, False):
        errors.append("Uhmayya should be dormant at start")

    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
            analyzer.log_issue(e)
    else:
        print("All initial conditions validated!")

    # ========================================
    # PLAYTHROUGH STRATEGY
    # ========================================
    # Phase 1: Conquer Affrancia (target Orhas early to trigger alliance)
    # Phase 2: Use Uhmayya alliance to fight Nordia
    # Phase 3: After Affrancia + Nordia eliminated, Uhmayya betrays
    # Phase 4: Conquer Uhmayya

    victory_achieved = False

    # --- Phase 1: Conquer Kingdom of Affrancia ---
    # Strategic order: nearby territories first, Orhas early for alliance
    affrancia_order = [
        "Free Cities", "Lunedale", "Affrancian Uplands",
        "Carnae", "Vense", "Cualus", "Orlais", "Orhas", "March of Auverne"
    ]

    print("\n" + "=" * 50)
    print("PHASE 1: Conquer Kingdom of Affrancia")
    print("=" * 50)

    nordia_awakened_turn = None

    for i, territory in enumerate(affrancia_order):
        analyzer.turns += 1
        print(f"\n== TURN {analyzer.turns}: Attack {territory} ==")
        force_conquer_territory(game, mission, territory, 0, analyzer)

        # Check Nordia awakening (first time)
        if mission.nordia_awakened and nordia_awakened_turn is None:
            nordia_awakened_turn = analyzer.turns
            analyzer.awakenings.append((analyzer.turns, "Nordia awakened (territory count)"))
            print(f"  [AWAKENING] Warlords of Nordia now fully active!")

            # Analyze immediate Nordia threat
            nordia_threats = analyze_border_threats(game, 0, 2, "Warlords of Nordia")
            simulate_ai_attacks(game, mission, 2, "Warlords of Nordia", nordia_threats, analyzer)

        # Check for alliance formation after Orhas
        if territory == "Orhas" and mission.alliance_formed:
            analyzer.log_event("alliance", "Uhmayya allied with player after Orhas captured")
            analyzer.awakenings.append((analyzer.turns, "Uhmayya allied (Orhas captured)"))
            print(f"  [ALLIANCE] Uhmayyan Empiurate joins player!")

        # Check if Affrancia defeated
        if mission.faction_defeated.get(1, False):
            analyzer.faction_defeats.append((analyzer.turns, "Kingdom of Affrancia"))
            print(f"  [DEFEAT] Kingdom of Affrancia eliminated!")
            break

    print_state(game, mission, f"POST-AFFRANCIA STATE (Turn {analyzer.turns})")

    # Nordia threat recap after Affrancia is gone
    if mission.nordia_awakened:
        print(f"  [NOTE] Nordia awakened on turn {nordia_awakened_turn} (territory count)")
        nordia_threats = analyze_border_threats(game, 0, 2, "Warlords of Nordia (post-Affrancia)")
        simulate_ai_attacks(game, mission, 2, "Warlords of Nordia", nordia_threats, analyzer)

    # --- Phase 2: Conquer Warlords of Nordia ---
    nordia_order = [
        "Damlére", "Role", "Vice", "Oucine", "Daomea",
        "Espoia", "Nefrid", "Conda", "Ahara", "Cinto",
        "Odatria", "Mose", "Riar", "Ajuna"
    ]

    print("\n" + "=" * 50)
    print("PHASE 2: Conquer Warlords of Nordia")
    print("=" * 50)

    for territory in nordia_order:
        # Skip if already conquered
        if game.territory_owners.get(territory) == 0:
            continue

        analyzer.turns += 1
        print(f"\n== TURN {analyzer.turns}: Attack {territory} ==")
        force_conquer_territory(game, mission, territory, 0, analyzer)

        # Check Nordia defeated
        if mission.faction_defeated.get(2, False):
            analyzer.faction_defeats.append((analyzer.turns, "Warlords of Nordia"))
            print(f"  [DEFEAT] Warlords of Nordia eliminated!")

            # Check betrayal trigger
            if mission.betrayal_triggered:
                analyzer.log_event("betrayal", "Uhmayya betrayed after Affrancia + Nordia eliminated")
                print(f"  [BETRAYAL] Uhmayyan Empiurate turns hostile!")
            break

    print_state(game, mission, f"POST-NORDIA STATE (Turn {analyzer.turns})")

    # Uhmayya threat analysis after betrayal
    if mission.betrayal_triggered:
        uhmayya_threats = analyze_border_threats(game, 0, 3, "Uhmayyan Empiurate (post-betrayal)")
        simulate_ai_attacks(game, mission, 3, "Uhmayyan Empiurate", uhmayya_threats, analyzer)

    # --- Phase 3: Conquer Uhmayyan Empiurate (after betrayal) ---
    if mission.betrayal_triggered:
        uhmayya_order = [
            "Linan", "Vianaa", "Osana", "Lamacia", "Aunon",
            "Fahlaan Dunes", "Leimarch", "Liadnon", "Ahtep",
            "Sordia", "Anodia"
        ]

        print("\n" + "=" * 50)
        print("PHASE 3: Conquer Uhmayyan Empiurate (after betrayal)")
        print("=" * 50)

        for territory in uhmayya_order:
            # Skip if not owned by Uhmayya
            if game.territory_owners.get(territory) != 3:
                continue

            analyzer.turns += 1
            print(f"\n== TURN {analyzer.turns}: Attack {territory} ==")
            force_conquer_territory(game, mission, territory, 0, analyzer)

            # Check Uhmayya defeated
            if mission.faction_defeated.get(3, False):
                analyzer.faction_defeats.append((analyzer.turns, "Uhmayyan Empiurate"))
                print(f"  [DEFEAT] Uhmayyan Empiurate eliminated!")
                break

    # Check victory
    if all(mission.faction_defeated.values()):
        victory_achieved = True
        print("\n*** VICTORY! All factions defeated! ***")

    # ========================================
    # FINAL STATE
    # ========================================

    print("\n" + "=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    print_state(game, mission, f"TURN {analyzer.turns} STATE")
    print_quest_status(mission)

    if victory_achieved:
        print("\n[VICTORY] Mission complete - all factions defeated!")
    else:
        print("\n[INCOMPLETE] Not all factions defeated")
        for fid, defeated in mission.faction_defeated.items():
            if not defeated:
                analyzer.log_issue(f"Faction {FACTION_NAMES[fid]} not defeated")

    # ========================================
    # ANALYSIS
    # ========================================

    print("\n" + "=" * 70)
    print("ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"Turns to completion: {analyzer.turns}")
    print(f"Total battles: {analyzer.battles}")
    print(f"Territories conquered: {len(analyzer.territories_conquered)}")
    print(f"Factions defeated: {len(analyzer.faction_defeats)}")

    print("\nAwakening/Alliance events:")
    for turn, event in analyzer.awakenings:
        print(f"  Turn {turn}: {event}")

    print("\nFaction defeats:")
    for turn, faction in analyzer.faction_defeats:
        print(f"  Turn {turn}: {faction} defeated")

    if analyzer.issues:
        print(f"\nIssues found ({len(analyzer.issues)}):")
        for turn, issue in analyzer.issues:
            print(f"  Turn {turn}: {issue}")
    else:
        print("\nIssues found: None")

    # Balance analysis
    print("\n" + "-" * 50)
    print("GAMEPLAY BALANCE ANALYSIS")
    print("-" * 50)

    # Count initial armies per faction
    print("Starting strength:")
    print(f"  - Player: 14 units (6 Swordsmen, 4 Pikemen, 4 Archers), 500g, 1 territory")
    print(f"  - Affrancia: ~38 units across 9 territories, 300g [ACTIVE]")
    print(f"  - Nordia: ~13+ units across 14 territories, 200g [SEMI-DORMANT]")
    print(f"    (Damlére: 9, Daomea: 4, others: random 0-3 each)")
    print(f"  - Uhmayya: ~39 units across 11 territories, 300g [DORMANT]")
    print()
    print("Strategic dynamics:")
    print("  1. Affrancia is aggressive from turn 1 - must handle early pressure")
    print("  2. Capturing Orhas triggers Uhmayya alliance (major power swing)")
    print("  3. Nordia awakens at 4+ player territories or if attacked directly")
    print("  4. After Affrancia+Nordia eliminated, Uhmayya betrays (surprise twist)")
    print("  5. Player capital (Zjoal Islands) loss = instant defeat")
    print()
    print("Alliance/betrayal flow:")
    print("  Capture Orhas -> Uhmayya allies -> Help vs Nordia -> Affrancia+Nordia fall -> Uhmayya betrays")
    print()
    print("Potential issues:")
    print("  1. Nordia random units (0-3 per territory) create variable difficulty")
    print("  2. If player skips Orhas, no alliance forms - much harder campaign")
    print("  3. Uhmayya has heavy cavalry focus (~22 Cavalry) - very strong post-betrayal")
    print("  4. Semi-dormant AI can still build/train, potentially snowballing")
    print("  5. Hero (Serthus) must survive in Zjoal - ties player to defending capital")

    print()
    print("=" * 70)

    return {
        'success': len(analyzer.issues) == 0 and victory_achieved,
        'turns': analyzer.turns,
        'battles': analyzer.battles,
        'territories_conquered': len(analyzer.territories_conquered),
        'factions_defeated': len(analyzer.faction_defeats),
        'issues': analyzer.issues,
        'victory': victory_achieved,
    }


def test_alliance_mechanics():
    """Test that alliance forms when Orhas is captured."""
    print("\n" + "=" * 70)
    print("ALLIANCE MECHANICS TEST")
    print("=" * 70)

    try:
        game, mission = setup_mission_3()
    except Exception as e:
        pytest.fail(f"Failed to initialize: {e}")

    if not mission:
        pytest.fail("Mission failed to initialize")

    skip_intro(mission)
    analyzer = MissionAnalyzer()

    # Capture Orhas
    print("\nCapturing Orhas to trigger alliance...")
    force_conquer_territory(game, mission, "Orhas", 0, analyzer)

    # Verify alliance
    alliance_ok = mission.alliance_formed
    team_ok = game.player_teams[3] == 0  # Uhmayya on player's team
    print(f"  Alliance formed: {alliance_ok}")
    print(f"  Uhmayya team == player team: {team_ok}")

    assert alliance_ok and team_ok, "Alliance mechanics broken!"


def test_betrayal_mechanics():
    """Test that Uhmayya betrays after Affrancia+Nordia eliminated."""
    print("\n" + "=" * 70)
    print("BETRAYAL MECHANICS TEST")
    print("=" * 70)

    try:
        game, mission = setup_mission_3()
    except Exception as e:
        pytest.fail(f"Failed to initialize: {e}")

    if not mission:
        pytest.fail("Mission failed to initialize")

    skip_intro(mission)
    analyzer = MissionAnalyzer()

    # Form alliance first
    print("\nForming alliance (capture Orhas)...")
    force_conquer_territory(game, mission, "Orhas", 0, analyzer)

    # Eliminate Affrancia (conquer all 9 territories)
    print("Eliminating Affrancia...")
    for t in FACTION_TERRITORIES[1]:
        if game.territory_owners.get(t) != 0:
            force_conquer_territory(game, mission, t, 0, analyzer)

    affrancia_defeated = mission.faction_defeated.get(1, False)
    print(f"  Affrancia defeated: {affrancia_defeated}")

    # Eliminate Nordia (conquer all 14 territories)
    print("Eliminating Nordia...")
    for t in FACTION_TERRITORIES[2]:
        if game.territory_owners.get(t) != 0:
            force_conquer_territory(game, mission, t, 0, analyzer)

    nordia_defeated = mission.faction_defeated.get(2, False)
    betrayal_ok = mission.betrayal_triggered
    team_hostile = game.player_teams[3] == 3  # Uhmayya back to enemy

    print(f"  Nordia defeated: {nordia_defeated}")
    print(f"  Betrayal triggered: {betrayal_ok}")
    print(f"  Uhmayya hostile again: {team_hostile}")

    # Check new quest added
    has_uhmayya_quest = any(q['text'] == 'Defeat the Uhmayyan Empiurate' for q in mission.quest_log)
    print(f"  Uhmayya defeat quest added: {has_uhmayya_quest}")

    assert all([affrancia_defeated, nordia_defeated, betrayal_ok, team_hostile, has_uhmayya_quest]), "Betrayal mechanics broken!"


def test_defeat_condition():
    """Test that player loses when Zjoal Islands is captured."""
    print("\n" + "=" * 70)
    print("DEFEAT CONDITION TEST")
    print("=" * 70)

    try:
        game, mission = setup_mission_3()
    except Exception as e:
        pytest.fail(f"Failed to initialize: {e}")

    if not mission:
        pytest.fail("Mission failed to initialize")

    skip_intro(mission)
    analyzer = MissionAnalyzer()

    # AI conquers Zjoal Islands
    print("\nSimulating AI conquest of Zjoal Islands...")
    force_conquer_territory(game, mission, "Zjoal Islands", 1, analyzer)

    # _defeat_waiting is set immediately; _pending_defeat only transitions during update() frame loop
    defeat_triggered = getattr(mission, '_defeat_waiting', False) or mission._pending_defeat or mission.defeat_sequence_active
    print(f"  Defeat sequence triggered: {defeat_triggered}")

    assert defeat_triggered, "Defeat condition did not trigger (checked _defeat_waiting, _pending_defeat, defeat_sequence_active)"


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

    # Run mechanics tests
    alliance_ok = test_alliance_mechanics()
    betrayal_ok = test_betrayal_mechanics()
    defeat_ok = test_defeat_condition()

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Victory playthrough: {'PASS' if results['success'] else 'FAIL'}")
    print(f"Alliance mechanics:  {'PASS' if alliance_ok else 'FAIL'}")
    print(f"Betrayal mechanics:  {'PASS' if betrayal_ok else 'FAIL'}")
    print(f"Defeat condition:    {'PASS' if defeat_ok else 'FAIL'}")
