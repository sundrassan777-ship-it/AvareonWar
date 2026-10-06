# -*- coding: utf-8 -*-
# tale_final_breaths.py
# Book of Tales — Tale II: "Final Breaths"
#
# Map: Avareon geometry with Campaign Mission 3's territories and background
# (assets/CampaignMaps/Campaign3Map.png, set by main.py's _TALE_REGISTRY).
# 3 factions, every one for themselves:
#   0 = the player (Zjoal Empire, Blue)       holds Lunedale (Castle) + 16 more
#   1 = Kerunian Empire (Red, built-in AI)    wealthy; attacks capped per target,
#                                             plus a forced attack every turn
#   2 = Nordian Rebels (Yellow, passive)      no land at start; takes Zjoal land
#                                             by rebellion and only ever defends
# Mission 3's five other territories start neutral and empty.
#
# Victory: still holding Lunedale and Free Cities when HOLD_TURNS turns are over.
# Defeat:  Lunedale or Free Cities changes hands.

import random
import pygame
import map_data
from utils.logger import get_logger
# Shared campaign utilities (TransmissionOverlay, camera animation, endgame sequences)
from campaign_utils import TransmissionOverlay, CameraZoomAnimation
from campaign_utils import update_endgame_sequence, render_endgame_sequence
from campaign_mission_3 import MISSION_3_TERRITORIES
# Shared with Tale I: plot-mix allocation and the BattleBar.png frame geometry
from tale_lack_of_funds import (
    allocate_building_counts, BAR_FRAME_CROP, BAR_FILL_LEFT, BAR_FILL_RIGHT,
    BAR_FILL_TOP, BAR_FILL_BOTTOM, BAR_FILL_HIDDEN_LEFT,
)

logger = get_logger(__name__)

# ============================================================================
# TALE CONFIGURATION
# ============================================================================

TALE_ID = 'tale_2'

# Player indices (match main.py _TALE_REGISTRY['tale_2'] config order)
PLAYER = 0   # Zjoal Empire
RED = 1      # Kerunian Empire
REBELS = 2   # Nordian Rebels

# Objectives: hold both for HOLD_TURNS turns; losing either is defeat
OBJECTIVE_TERRITORIES = ("Lunedale", "Free Cities")
HOLD_TURNS = 15

# Starting ownership (the Rebels start with nothing). Every other territory —
# including Mission 3's Zjoal Islands, Leimarch, Liadnon, Ahtep and Anodia — is
# neutral and empty.
FACTION_TERRITORIES = {
    PLAYER: ["Vense", "Lunedale", "Free Cities", "Daomea", "Damlére", "Role", "Vice",
             "Mose", "Riar", "Ajuna", "Espoia", "Nefrid", "Conda", "Odatria", "Cinto",
             "Oucine", "Ahara"],
    RED: ["Affrancian Uplands", "Carnae", "March of Auverne", "Orlais", "Cualus", "Orhas",
          "Linan", "Vianaa", "Osana", "Lamacia", "Aunon", "Fahlaan Dunes", "Sordia"],
}

FACTION_CAPITALS = {PLAYER: "Lunedale", RED: "Affrancian Uplands"}

# Colours by player index: Blue, Red, Yellow (same RGB as Tale I / missions 4-6)
PLAYER_COLORS = [
    (100, 150, 255),   # Player 0: Blue (Zjoal Empire)
    (255, 100, 100),   # Player 1: Red (Kerunian Empire)
    (255, 220, 100),   # Player 2: Yellow (Nordian Rebels)
]

# Flag icon slot each player takes from the default army_flag_icons order
# (0=Red, 1=Blue, 2=Green, 3=Yellow).
FLAG_ICON_SOURCE = {PLAYER: 1, RED: 0, REBELS: 3}

FACTION_NAMES = {
    PLAYER: None,                 # Human player keeps their profile name
    RED: "Kerunian Empire",
    REBELS: "Nordian Rebels",
}

# The Zjoal Empire is all but bankrupt; the Kerunians can buy an army at once
STARTING_GOLD = {PLAYER: 200, RED: 7000, REBELS: 0}
# The imperial treasury is empty: 100% taxation (level 4) on the Zjoal Empire
# only, so every gold left unspent at the end of the player's turn is lost.
# Other factions keep the game-wide level (0) — the Kerunians keep their 7000.
PLAYER_TAXATION_LEVEL = 4
# Red starts with 88 units, above the default command limit of 75. 100 only left
# room for ~12 units, so the 7000 gold sat unused and their attacks dried up after
# the first waves. At 200 they keep training (army ~88 -> ~230 by turn 10): in
# simulations a defending bot then lost 4 games in 6 (turns 7-15), vs 0 at 100.
RED_COMMAND_LIMIT = 200

# --- Buildings ---
# A Keep on plot 0 of these; Lunedale's is upgraded to a Castle (the Zjoal
# Empire's castle techs need one).
KEEP_TERRITORIES = ("Lunedale", "Affrancian Uplands", "March of Auverne", "Carnae")
CASTLE_TERRITORY = "Lunedale"
# Every other plot of the faction is filled from its mix (largest-remainder
# counts, shuffled). None = left empty. Zjoal's few empty plots and its Barracks
# glut are the point: demolishing Barracks (full refund with Makeshift Barracks)
# frees plots for Mines and Farms.
BUILD_MIX = {
    PLAYER: [('Barracks', 0.75), ('Mine', 0.10), ('Farm', 0.10), (None, 0.05)],
    RED: [('Barracks', 0.75), ('Mine', 0.10), ('Farm', 0.10), ('Square', 0.05)],
}

# --- Armies ---
# Every starting army is one Captain plus random basic units.
BASIC_UNIT_TYPES = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
LARGE_ARMY_TERRITORIES = ("Affrancian Uplands", "March of Auverne", "Lunedale", "Free Cities")
MEDIUM_ARMY_TERRITORIES = ("Vense", "Carnae", "Orlais", "Cualus", "Damlére")
LARGE_ARMY_SIZE = 12
MEDIUM_ARMY_SIZE = 8
DEFAULT_ARMY_SIZE = {PLAYER: 3, RED: 5}

# --- Technologies (Zjoal Empire only) ---
# Whole combat column, first 3 economy techs, first 5 leadership/hero techs.
# tech_{column}_{row}: column 0 = economy, 1 = combat, 2 = leadership.
PLAYER_TECHS = ([f"tech_1_{row}" for row in range(7)]
                + [f"tech_0_{row}" for row in range(3)]
                + [f"tech_2_{row}" for row in range(5)])

# --- AI rules ---
# Kerunian attacks: at most turn // 2 + ATTACK_CAP_BASE units against any one
# target per turn (see attack_cap_for_turn).
# Balance (headless simulations vs a bot that stacks both objectives to 15 at
# once, with the forced attacks and rebellion schedule below): base 1 or 3 never
# threatened it — once both objectives hold 15 units no single stack breaks them,
# so the danger is in the early turns. Base 10 lost 1 game in 6 (turn 8) with
# several close calls; no cap at all lost 4 in 6 by turn 7. Playtesting then
# found it still easy — the Kerunians ran out of units (see RED_COMMAND_LIMIT).
ATTACK_CAP_BASE = 10
# Forced attacks: at the start of every Kerunian turn the Tale itself orders
# FORCED_ATTACK_TARGETS attack(s) on the Zjoal Empire, sent up to the cap,
# whether or not the built-in AI would have judged it worth it. Target: the
# territory where the Kerunians can bring the most units relative to its
# defenders. Each source keeps FORCED_ATTACK_KEEP units at home. The AI's own
# attacks still follow, within whatever cap is left at each target.
FORCED_ATTACK_TARGETS = 1
FORCED_ATTACK_KEEP = 1
# True: forced attacks go for Lunedale / Free Cities whenever the Kerunians can
# reach one, and only fall back to other border land when they can't.
FORCED_ATTACK_OBJECTIVES_FIRST = True
# Kerunian reinforcements: at the start of every Kerunian turn (before the forced
# attack) each Kerunian territory gains a random (min, max) number of ready basic
# units, up to the 15-unit territory limit. Mission-granted: they ignore the
# command limit. FRONT_ONLY limits it to territories bordering Zjoal land.
# (0, 0) = off (the command limit is the chosen lever). Very strong when on: in
# simulations even (1, 1) front-only or (0, 2) everywhere beat the defending bot
# every time; (0, 1) everywhere lost 1 in 4.
KERUNIAN_REINFORCEMENTS = (0, 0)
KERUNIAN_REINFORCEMENTS_FRONT_ONLY = False
# Scale for the built-in AI's readability pauses (ai_player._pace), as Tale I
AI_DELAY_SCALE = 0.0

# Opening camera: zoom towards Lunedale (first step of the intro)
START_CAMERA_ZOOM = 2.0
START_CAMERA_DURATION = 1.0

# --- Transmissions ---
# Voice lines live in assets/sounds/transmissions/ and are keyed by file stem
# (global_sound.load_transmission_sounds loads them for any game with a campaign map).
ADVISOR_SPEAKER = "Advisor Valcerque"   # Speaks every line of this Tale

# Intro: zoom to Lunedale, then three voiced transmissions. Gameplay (and the
# planning timer) is paused until it ends; ESC skips the current line.
# Format: (action, param, speaker, text, voice_key, duration_seconds)
INTRO_SEQUENCE = [
    ('zoom_to', "Lunedale", None, "", None, 0.0),
    ('say', None, ADVISOR_SPEAKER,
     "The Kerunian Empire might outnumber us on the field, but I know that their "
     "population is tired of war.", 'T2T1', 7.0),
    ('say', None, ADVISOR_SPEAKER,
     "We just need to hold on. Contain their expansion. Soon, their will to fight will "
     "break and they will be forced to negotiate.", 'T2T2', 9.0),
    ('say', None, ADVISOR_SPEAKER, "Defend our heartland at all costs!", 'T2T3', 2.0),
]
INTRO_LINE_GAP = 1.0   # Silence between consecutive voiced intro lines (as Tale I)

# Gameplay / endgame transmissions: (speaker, text, voice_key, duration_seconds).
# A line is never shown for less than its recording lasts (see _show_transmission).
FIRST_REBELLION_TRANSMISSION = (ADVISOR_SPEAKER,
                                "The Nordians are rebelling against us. We must hold!", 'T2R1', 3.0)
REBELLION_TRANSMISSION = (ADVISOR_SPEAKER, "Another rebellion! Stay strong!", 'T2R+', 3.0)
DEFEAT_TRANSMISSION = (ADVISOR_SPEAKER,
                       "Our defenses have fallen! The legacy of our empire is undone.", 'T2L', 4.0)
VICTORY_TRANSMISSION = (ADVISOR_SPEAKER,
                        "We have done it! The Kerunians cannot continue the war - their people "
                        "are revolting! The negotiations can commence!", 'T2W', 8.0)

# --- Rebellions ---
# Before turn REBELLION_RAMP_TURN: REBELLIONS_EARLY territories rebel at the start
# of every REBELLION_INTERVAL-th player turn (turns 2, 4). From that turn on:
# REBELLIONS_LATE every REBELLION_INTERVAL_LATE turns. Random Zjoal territories;
# the Rebels take the land with its armies and buildings.
REBELLION_INTERVAL = 2
REBELLION_RAMP_TURN = 6
REBELLION_INTERVAL_LATE = 1
REBELLIONS_EARLY = 1
REBELLIONS_LATE = 1
REBELLION_IMMUNE = ("Lunedale", "Free Cities", "Damlére", "Oucine")

# --- "Turns to Hold" widget (bottom-left of the map area, Tale I's Popularity
# widget without the button). *_REF sizes are at ui_scale 1.0.
HOLD_BAR_WIDTH_REF = 320
HOLD_MARGIN_REF = 14          # From the map's left and bottom edges
HOLD_LABEL_SIZE_REF = 22
HOLD_CHAT_LIFT_REF = 50       # Lift above the chat input box while it is open
HOLD_EASE_PER_SEC = 2.0       # Bar drains at this many turns per second
HOLD_TRACK_COLOR = (18, 18, 28)
HOLD_FILL_TOP_COLOR = (120, 170, 255)
HOLD_FILL_BOTTOM_COLOR = (35, 75, 200)
HOLD_LABEL_COLOR = (240, 230, 200)
HOLD_FONT_PATH = 'assets/fonts/Cinzel-SemiBold.ttf'


def _ready_units(gs, territory, player):
    """`player`'s unmoved, unordered units in `territory`."""
    garrison = gs.territory_garrisons.get(territory, {}).get(player) or {}
    return [u for u in garrison.get('units', []) if u.get('status') == 'ready']


def attack_cap_for_turn(turn):
    """Units the Kerunian Empire may send against ONE target on player-visible turn `turn`.

    turn // 2 + ATTACK_CAP_BASE: turn 1 -> 10, 2-3 -> 11, 4-5 -> 12, ..., 10 -> 15, 14-15 -> 17.
    """
    return turn // 2 + ATTACK_CAP_BASE


def rebellions_for_turn(turn):
    """How many Zjoal territories rebel at the start of player-visible turn `turn`."""
    if turn >= REBELLION_RAMP_TURN:
        return REBELLIONS_LATE if turn % REBELLION_INTERVAL_LATE == 0 else 0
    if turn < REBELLION_INTERVAL or turn % REBELLION_INTERVAL != 0:
        return 0
    return REBELLIONS_EARLY


class TaleFinalBreaths:
    """
    Book of Tales — Tale II: "Final Breaths".

    Standard mission interface (see CODE_GUIDE "Mission Exit Contract" and the
    tutorial_mission hooks): update / update_ai_turn / render / notify_event /
    is_action_allowed / get_quest_log / get_save_state / restore_save_state.
    Also defines get_ai_attack_cap (ai_military.mission_ai_attack_cap).

    rng: optional random.Random for the randomised setup and rebellions
    (tests pass a seeded one).
    """

    def __init__(self, game_state, main_game, rng=None):
        self.game_state = game_state
        self.main_game = main_game
        # mission_id drives the save label, achievement stat and first-win XP
        self.mission_id = TALE_ID
        self.active = True
        self.rng = rng or random.Random()

        # Intro sequence state (INTRO_SEQUENCE). intro_active / game_paused /
        # timer_visible are also read by main.py (planning timer, input gating).
        self.intro_active = True
        self.intro_step_index = -1
        self._intro_waiting_for_camera = False
        self._intro_gap_timer = 0.0
        self.game_paused = True
        self.timer_visible = False
        self.allow_timer_expiry = True
        # Read by ai_player._pace(): fast AI turns for the built-in AI
        self.ai_delay_scale = AI_DELAY_SCALE

        # Camera animation (read by main.py to suspend manual zoom while active)
        self.camera_animation = None

        # Transmission overlay + queue of gameplay transmissions waiting for an
        # idle moment: list of (speaker, text, voice_key, duration) tuples
        self.transmission_overlay = None
        self.transmission_timer = 0.0
        self.transmission_duration = 0.0
        self.transmission_queue = []
        # The first rebellion gets its own line (T2R1); later ones T2R+
        self._rebellion_announced = False

        # Quest log — mirrors the Objectives in the Book of Tales description
        self.quest_log = [
            {'text': f'Defend Lunedale and Free Cities for {HOLD_TURNS} turns', 'completed': False},
        ]

        # Victory/defeat sequence state (same attrs as missions 4-7, needed by campaign_utils)
        self.game_frozen = False
        self.victory_sequence_active = False
        self.victory_phase = None
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0
        self.victory_image = None
        self.victory_image_scale = 0.0

        self.defeat_sequence_active = False
        self.defeat_phase = None
        self.defeat_timer = 0.0
        self.defeat_fade_alpha = 0
        self.defeat_image = None
        self.defeat_image_scale = 0.0
        self._pending_defeat = False
        self._pending_victory = False
        self._victory_waiting = False
        self._defeat_waiting = False

        # Store original flag icons for restoration on cleanup
        self.original_flag_icons = None

        # gs.turn_number of the last player turn start handled — guarantees the
        # rebellions (and victory check) run once per player turn
        self._last_turn_handled = None
        # Same for the start of the Kerunians' turn (forced attacks)
        self._last_red_turn_handled = None

        # "Turns to Hold" widget layout + caches (rebuilt when the screen/scale changes)
        self._display_remaining = float(self.get_turns_remaining())
        self._widget_key = None
        self._widget_rect = None
        self._bar_rect = None
        self._label_rect = None
        self._fill_rect = None
        self._fill_hidden = 0
        self._bar_frame_src = None      # Cropped BattleBar.png, loaded once
        self._bar_frame = None          # Frame scaled to the bar size
        self._bar_fill = None           # Blue gradient, full bar size
        self._font_cache = {}
        self._text_cache = {}

        # Unique unit ids across the whole setup
        self._next_unit_id = 0

        # Mission 3's territories only (cleared again in _cleanup)
        map_data.set_enabled_territories(MISSION_3_TERRITORIES)

        self._setup_initial_state()
        self._advance_intro()   # Step 0: zoom to Lunedale

        logger.info("Tale 'Final Breaths' initialized: 3 factions on the Mission 3 map")

    # ========================================================================
    # INITIAL STATE
    # ========================================================================

    def _setup_initial_state(self):
        """Configure factions, ownership, buildings, armies and technologies."""
        gs = self.game_state

        # Colours
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Flag icons follow the colours (army_flag_icons is keyed by player index)
        game = self.main_game
        flags = getattr(game, 'army_flag_icons', None)
        if flags and all(k in flags for k in FLAG_ICON_SOURCE.values()):
            self.original_flag_icons = dict(flags)
            for player_id, source in FLAG_ICON_SOURCE.items():
                flags[player_id] = self.original_flag_icons[source]

        # Names, gold, Red's command limit
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name
        for player_id, gold in STARTING_GOLD.items():
            if player_id < gs.num_players:
                gs.player_gold[player_id] = gold
        gs.player_command_limit[RED] = RED_COMMAND_LIMIT
        self._apply_taxation()

        # Wipe whatever initialize_game() placed (capital claims, starting armies)
        owner_of = {t: p for p, terrs in FACTION_TERRITORIES.items() for t in terrs}
        for territory in list(gs.territory_owners.keys()):
            gs.territory_owners[territory] = owner_of.get(territory, -1)
            gs.territory_garrisons[territory] = {}
            gs.buildings[territory] = {}
        gs.castle_upgrades = {}

        self._place_buildings()
        self._place_armies()
        self._grant_player_techs()

        for player_id, capital in FACTION_CAPITALS.items():
            gs.player_starting_territories[player_id] = capital

        # Ownership was rewritten wholesale — invalidate every derived cache
        gs._territory_owners_version += 1
        gs.invalidate_income_cache()
        gs.invalidate_army_count_cache()
        gs.invalidate_territorial_bonus_cache()

    def _apply_taxation(self):
        """Tax only the Zjoal Empire (GameState.get_taxation_level reads the override)."""
        self.game_state.player_taxation_override = {PLAYER: PLAYER_TAXATION_LEVEL}

    def _plot_count(self, territory):
        """Number of building plots in a territory (from the map's plot data)."""
        return len(map_data.get_plots(territory) or [])

    def _place_buildings(self):
        """Keeps (Lunedale's a Castle), then each faction's remaining plots from BUILD_MIX."""
        gs = self.game_state

        for territory in KEEP_TERRITORIES:
            if self._plot_count(territory) > 0:
                gs.buildings[territory][0] = 'Keep'
        if CASTLE_TERRITORY in KEEP_TERRITORIES:
            # A Castle is a Keep plot flagged in castle_upgrades (as mission 7)
            gs.castle_upgrades[CASTLE_TERRITORY] = {0: True}

        for faction, mix in BUILD_MIX.items():
            slots = [(t, i) for t in FACTION_TERRITORIES[faction]
                     for i in range(self._plot_count(t)) if i not in gs.buildings[t]]
            pool = allocate_building_counts(len(slots), mix, self.rng)
            # The engine allows one Square per territory: reshuffle until no
            # territory holds two (only ~1 Square, so the first try nearly always works)
            for _ in range(200):
                self.rng.shuffle(pool)
                squares = [slots[i][0] for i, b in enumerate(pool) if b == 'Square']
                if len(squares) == len(set(squares)):
                    break
            for (territory, plot_idx), building in zip(slots, pool):
                if building is not None:
                    gs.buildings[territory][plot_idx] = building

    def _make_units(self, unit_types):
        """Create ready (unmoved) unit dicts with unique ids."""
        units = []
        for unit_type in unit_types:
            units.append(self.game_state._make_unit(unit_type, self._next_unit_id, status='ready'))
            self._next_unit_id += 1
        return units

    def _army_size(self, faction, territory):
        if territory in LARGE_ARMY_TERRITORIES:
            return LARGE_ARMY_SIZE
        if territory in MEDIUM_ARMY_TERRITORIES:
            return MEDIUM_ARMY_SIZE
        return DEFAULT_ARMY_SIZE[faction]

    def _place_armies(self):
        """Every faction territory: one Captain plus random basic units."""
        gs = self.game_state
        for faction, territories in FACTION_TERRITORIES.items():
            for territory in territories:
                size = self._army_size(faction, territory)
                unit_types = ['Captain'] + [self.rng.choice(BASIC_UNIT_TYPES) for _ in range(size - 1)]
                units = self._make_units(unit_types)
                gs.set_garrison_armies(territory, faction, unmoved=len(units), moved=0, units=units)

    def _grant_player_techs(self):
        """Mark PLAYER_TECHS researched for the Zjoal Empire, effects included.

        Goes through GameState.apply_tech_effect() (the code finish_research()
        uses), so a pre-granted tech behaves exactly like a researched one. The
        next tech in each column is then made researchable, as finish_research()
        would have done.
        """
        gs = self.game_state
        techs = {tech['id']: tech for tech in gs.technologies}
        researched = gs.player_tech_researched[PLAYER]
        available = gs.player_tech_available[PLAYER]
        for tech_id in PLAYER_TECHS:
            tech = techs.get(tech_id)
            if tech is None:
                logger.warning(f"Tale: unknown tech {tech_id}")
                continue
            researched.add(tech_id)
            available.discard(tech_id)
            gs.apply_tech_effect(PLAYER, tech, announce=False)
        for column in range(3):
            next_row = max((techs[t]['row'] for t in researched
                            if t in techs and techs[t]['column'] == column), default=-1) + 1
            if next_row < 7:
                available.add(f"tech_{column}_{next_row}")
        gs.invalidate_income_cache(PLAYER)

    def _start_camera(self, territory):
        """Ease the camera onto `territory`. Returns True if an animation started."""
        try:
            import main as _main
            map_area_height = _main.MAP_HEIGHT
        except (ImportError, AttributeError):
            map_area_height = self.main_game.screen.get_height()
        camera = getattr(self.main_game, 'camera', None)
        if camera is None:
            return False
        target_center = getattr(self.main_game, 'scaled_centers', {}).get(
            territory, map_data.get_territory_center(territory))
        if target_center is None:
            return False
        self.camera_animation = CameraZoomAnimation(
            camera_handler=camera,
            start_zoom=camera.zoom,
            target_zoom=min(getattr(camera, 'max_zoom', START_CAMERA_ZOOM), START_CAMERA_ZOOM),
            duration=START_CAMERA_DURATION,
            target_center_world=target_center,
            screen_width=self.main_game.screen.get_width(),
            map_area_height=map_area_height,
        )
        return True

    def _is_gameplay_idle(self):
        """No battles, popups or turn announcements in flight."""
        gs = self.game_state
        battle_popup_open = getattr(self.main_game, 'battle_popup_visible', False)
        phase_ok = gs.turn_phase == 'planning' or gs.phase == 'ended'
        return (phase_ok
                and not gs.pending_battles
                and not battle_popup_open
                and not gs.turn_announcement_active)

    # ========================================================================
    # INTRO SEQUENCE (same machinery as Tale I)
    # ========================================================================

    def _advance_intro(self):
        """Move to the next INTRO_SEQUENCE step (or end the intro after the last)."""
        self.intro_step_index += 1
        if self.intro_step_index >= len(INTRO_SEQUENCE):
            self._end_intro()
            return
        action, param, speaker, text, voice_key, duration = INTRO_SEQUENCE[self.intro_step_index]
        if action == 'zoom_to':
            # Wait for the camera; skip straight on if it cannot animate (no camera)
            self._intro_waiting_for_camera = self._start_camera(param)
            if not self._intro_waiting_for_camera:
                self._advance_intro()
        elif action == 'say':
            self._show_transmission(text, duration, speaker, voice_key)

    def _update_intro(self, delta_time):
        """Drive the intro: camera step, then each line for its duration + a gap."""
        if self.camera_animation:
            self.camera_animation.update(delta_time)
            if not self.camera_animation.active:
                self.camera_animation = None
                if self._intro_waiting_for_camera:
                    self._intro_waiting_for_camera = False
                    self._advance_intro()
            return
        if self._intro_gap_timer > 0:
            self._intro_gap_timer -= delta_time
            if self._intro_gap_timer <= 0:
                self._intro_gap_timer = 0.0
                self._advance_intro()
            return
        if self.transmission_overlay and self.transmission_duration > 0:
            self.transmission_timer += delta_time
            if self.transmission_timer >= self.transmission_duration:
                self._finish_intro_line()

    def _finish_intro_line(self):
        """Current intro line is over: short silence before the next voiced line."""
        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.transmission_overlay = None
        self.transmission_duration = 0.0
        next_idx = self.intro_step_index + 1
        if next_idx < len(INTRO_SEQUENCE) and INTRO_SEQUENCE[next_idx][0] == 'say':
            self._intro_gap_timer = INTRO_LINE_GAP
        else:
            self._advance_intro()

    def _end_intro(self):
        """Intro over: unpause, show the planning timer and restart it from full."""
        import time
        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.intro_active = False
        self.game_paused = False
        self.timer_visible = True
        self.transmission_overlay = None
        self.transmission_duration = 0.0
        self._intro_gap_timer = 0.0
        self._intro_waiting_for_camera = False
        self.camera_animation = None
        self.game_state.planning_phase_start_time = time.time()
        logger.info("Tale intro complete — gameplay begins")

    # ========================================================================
    # TRANSMISSIONS
    # ========================================================================

    def _show_transmission(self, text, duration, speaker=ADVISOR_SPEAKER, voice_key=None):
        """Show a transmission and play its voice line.

        The text stays up for `duration` seconds, or for as long as the recording
        lasts if that is longer: the text expiring stops the voice, so a line
        timed shorter than its recording would otherwise be cut off.
        """
        import main as _main
        screen = self.main_game.screen
        if not self.transmission_overlay:
            self.transmission_overlay = TransmissionOverlay(
                screen.get_width(), screen.get_height(), text, _main.TOP_PANEL_HEIGHT,
                speaker=speaker)
        else:
            self.transmission_overlay.set_text(text, speaker=speaker)
        self.transmission_timer = 0.0
        self.transmission_duration = duration
        if voice_key:
            from global_sound import play_transmission_sound, get_transmission_length
            self.transmission_duration = max(duration, get_transmission_length(voice_key))
            play_transmission_sound(voice_key)

    def _queue_transmission(self, transmission):
        """Queue a (speaker, text, voice_key, duration) transmission for the next idle moment."""
        self.transmission_queue.append(transmission)

    def _start_pending_transmission(self):
        """Show the next queued transmission."""
        speaker, text, voice_key, duration = self.transmission_queue.pop(0)
        self._show_transmission(text, duration, speaker, voice_key)

    def skip_transmission(self):
        """ESC skips the visible transmission (during the intro: skips to the next line)."""
        if not self.active or not self.transmission_overlay:
            return False
        if self.victory_sequence_active or self.defeat_sequence_active:
            return False
        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.transmission_overlay = None
        self.transmission_timer = 0.0
        self.transmission_duration = 0.0
        if self.intro_active:
            self._intro_gap_timer = 0.0
            self._advance_intro()
        return True

    # ========================================================================
    # SAVE / RESTORE STATE
    # ========================================================================

    def get_save_state(self):
        """Serialize Tale-specific state for the campaign save system."""
        return {
            'active': self.active,
            'quest_log': self.quest_log,
            'timer_visible': self.timer_visible,
            'allow_timer_expiry': self.allow_timer_expiry,
            'game_frozen': self.game_frozen,
            '_last_turn_handled': self._last_turn_handled,
            '_last_red_turn_handled': self._last_red_turn_handled,
            '_rebellion_announced': self._rebellion_announced,
        }

    def restore_save_state(self, data):
        """Restore Tale-specific state. The intro is never replayed on load."""
        self.active = data.get('active', True)
        self.quest_log = data.get('quest_log', self.quest_log)
        self.timer_visible = data.get('timer_visible', True)
        self.allow_timer_expiry = data.get('allow_timer_expiry', True)
        self.game_frozen = data.get('game_frozen', False)
        self._last_turn_handled = data.get('_last_turn_handled', self._last_turn_handled)
        self._last_red_turn_handled = data.get('_last_red_turn_handled', self._last_red_turn_handled)
        self._rebellion_announced = data.get('_rebellion_announced', self._rebellion_announced)
        # The override isn't part of the saved game state: set it again
        self._apply_taxation()
        self._display_remaining = float(self.get_turns_remaining())   # No drain animation on load
        # Resuming mid-game: never replay the intro the constructor just started
        self.intro_active = False
        self.intro_step_index = len(INTRO_SEQUENCE)
        self._intro_waiting_for_camera = False
        self._intro_gap_timer = 0.0
        self.camera_animation = None
        self.transmission_overlay = None
        self.transmission_duration = 0.0
        self.transmission_queue = []
        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.game_paused = False

    # ========================================================================
    # UPDATE (called every frame)
    # ========================================================================

    def update(self, delta_time):
        """Per-frame update.

        Returns 'exit_campaign' on victory (main.py then plays an outro cutscene,
        if one exists) or 'exit_campaign_defeat' on defeat. None otherwise.
        """
        if not self.active:
            return None
        # Cap delta_time to prevent animation jumps on lag spikes
        delta_time = min(delta_time, 0.05)
        gs = self.game_state

        # The Rebels are never defeated: with no land, check_victory() quietly marks
        # them eliminated (Total Conquest never runs the destructive
        # eliminate_player()). Undo that so the Players window doesn't list them
        # as eliminated and their (empty) turn keeps coming round.
        gs.eliminated_players.discard(REBELS)

        # Intro sequence owns the frame until it ends (gameplay is paused)
        if self.intro_active:
            self._update_intro(delta_time)
            return None

        # Instant AI turns: skip the turn announcement banner for AI factions (as
        # Tale I). Completing it here runs the normal start-of-turn work and lets
        # handle_ai_turn() start the AI, which waits for turn_announcement_active.
        if gs.current_player != PLAYER and gs.turn_announcement_active:
            game = self.main_game
            if getattr(game, 'turn_announcement_effect', None):
                game.turn_announcement_effect.cleanup()
                game.turn_announcement_effect = None
            gs._complete_turn_announcement()

        # Opening camera move
        if self.camera_animation:
            self.camera_animation.update(delta_time)
            if not self.camera_animation.active:
                self.camera_animation = None

        # Turns bar eases towards the real value so each new turn visibly drains it
        target = float(self.get_turns_remaining())
        step = HOLD_EASE_PER_SEC * delta_time
        if abs(target - self._display_remaining) <= step:
            self._display_remaining = target
        else:
            self._display_remaining += step if target > self._display_remaining else -step

        # Objectives can be lost by any path (battle, uncontested move, ability)
        self._check_objectives()
        # The engine itself ends the game if the Kerunians are wiped out
        # (last team standing) — that is a win for the player too
        if gs.phase == 'ended' and gs.winner == PLAYER:
            self._start_victory()

        # Transmission timer — the voice line stops when its text expires
        if self.transmission_overlay and self.transmission_duration > 0:
            self.transmission_timer += delta_time
            if self.transmission_timer >= self.transmission_duration:
                self.transmission_overlay = None
                self.transmission_duration = 0.0
                from global_sound import stop_transmission_sound
                stop_transmission_sound()

        gameplay_idle = self._is_gameplay_idle()

        # Queued gameplay transmissions (rebellions) wait for an idle moment
        if not self.transmission_overlay and self.transmission_queue and gameplay_idle:
            self._start_pending_transmission()

        # Deferred victory/defeat: wait for battles, popups and queued transmissions
        # to finish, then play the outro line; the shared campaign endgame
        # sequence (victory/defeat screen) starts once it expires.
        endgame_ready = gameplay_idle and not self.transmission_overlay and not self.transmission_queue
        if self._victory_waiting and endgame_ready:
            self._victory_waiting = False
            self._pending_victory = True
            self.game_paused = True
            speaker, text, voice_key, duration = VICTORY_TRANSMISSION
            self._show_transmission(text, duration, speaker, voice_key)
        if self._defeat_waiting and endgame_ready:
            self._defeat_waiting = False
            self._pending_defeat = True
            self.game_paused = True
            speaker, text, voice_key, duration = DEFEAT_TRANSMISSION
            self._show_transmission(text, duration, speaker, voice_key)

        # Victory -> 'exit_campaign'; defeat -> 'exit_campaign_defeat' (never the
        # victory sentinel, or main.py would play the outro after a loss)
        if update_endgame_sequence(self, delta_time, 'victory') == 'exit':
            self._cleanup()
            return 'exit_campaign'
        if update_endgame_sequence(self, delta_time, 'defeat') == 'exit':
            self._cleanup()
            return 'exit_campaign_defeat'
        return None

    # ========================================================================
    # AI CONTROL — built-in AI for the Kerunians, nothing for the Rebels
    # ========================================================================

    @property
    def block_ai(self):
        """Only the Rebels' turn is blocked: they never act, they just hold land.

        The Kerunian Empire runs the built-in AI (it resolves its own battles),
        limited by is_ai_target_allowed / get_ai_attack_cap / is_action_allowed.
        """
        return self.game_state.current_player == REBELS

    def execute_ai_turn_override(self):
        """Rebels' turn: nothing to do — update_ai_turn() ends it."""
        return None

    def update_ai_turn(self, delta_time):
        """End the Rebels' turn as soon as it starts (they build, train and move nothing)."""
        if not self.active:
            return False
        gs = self.game_state
        if gs.current_player != REBELS:
            return False
        if gs.phase == 'ended' or gs.turn_announcement_active:
            return True
        if gs.turn_phase == 'planning' and not gs.pending_battles:
            gs.next_player()
        return True

    # ========================================================================
    # ACTION GATING
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """Gate player/AI actions (queried by game_state, the UI and the built-in AI)."""
        if not self.active:
            return True
        if self.victory_sequence_active or self.defeat_sequence_active:
            return False
        if self.game_paused or self.game_frozen:
            return False
        # Nobody trains Heroes in this Tale (the built-in AI asks via
        # ai_military.mission_allows_ai_action)
        if action_type == 'train_hero':
            return False
        return True

    def is_ai_target_allowed(self, attacker, territory):
        """AI targeting rules (see ai_military.mission_allows_ai_target).

        Moving within one's own land is always allowed. The Rebels never leave
        their land; the Kerunians may target anyone (their attacks are capped
        per target by get_ai_attack_cap instead).
        """
        owner = self.game_state.territory_owners.get(territory, -1)
        if owner == attacker:
            return True
        if attacker == REBELS:
            return False
        return True

    def get_ai_attack_cap(self, attacker, territory):
        """Most units the Kerunians may send against `territory` this turn (None = no cap).

        Read by ai_military.mission_ai_attack_cap, which only asks about land the
        attacker doesn't own. The cap is per target, so several targets may each
        be attacked with that many units in the same turn.
        """
        if attacker != RED:
            return None
        return attack_cap_for_turn(self.get_current_turn())

    def should_hide_hero_training(self):
        """No Heroes in this Tale: hide the Keep's hero training buttons."""
        return True

    def should_button_be_locked(self, button_id):
        return False

    def is_button_locked(self, button_id):
        return self.should_button_be_locked(button_id)

    def should_highlight_button(self, button_id):
        return False

    def is_timer_visible(self):
        return self.timer_visible

    def is_territory_interactive(self, territory_name):
        """Only Mission 3's territories are part of this Tale."""
        return territory_name in MISSION_3_TERRITORIES

    def is_attack_target_blocked(self, territory_name):
        return False

    def get_adjacency_override(self, territory):
        return None

    def get_highlight_territory(self):
        return None

    def should_highlight_plot(self, territory, plot_index):
        return False

    # ========================================================================
    # TURNS
    # ========================================================================

    def get_current_turn(self):
        """Player-visible turn number: 1 on the player's first turn.

        gs.turn_number is 0 on the first turn and increments when play returns
        to the player, so it is also the number of fully completed turns.
        """
        return self.game_state.turn_number + 1

    def get_turns_remaining(self):
        """Turns the player still has to hold out (0 = objective met)."""
        return max(0, HOLD_TURNS - self.game_state.turn_number)

    # ========================================================================
    # EVENTS / REBELLIONS / VICTORY / DEFEAT
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """Receive gameplay events from hooked game systems."""
        if not self.active:
            return
        if event_type == 'territory_conquered':
            self._check_objectives()
        elif event_type == 'turn_announcement_done':
            if kwargs.get('player_index') == PLAYER:
                self._on_player_turn_start()
            elif kwargs.get('player_index') == RED:
                self._on_kerunian_turn_start()

    def _on_kerunian_turn_start(self):
        """Start of a Kerunian turn: order the forced attack(s) before the AI plans.

        The built-in AI starts once the announcement clears, so these orders are
        already in place; its own attacks are then capped by what's left at each
        target (ai_player's guard counts existing orders). Once per turn.
        """
        gs = self.game_state
        if gs.phase == 'ended' or gs.turn_number == self._last_red_turn_handled:
            return
        self._last_red_turn_handled = gs.turn_number
        self._spawn_kerunian_reinforcements()
        for _ in range(FORCED_ATTACK_TARGETS):
            if not self._order_forced_attack():
                break

    def _spawn_kerunian_reinforcements(self):
        """Add KERUNIAN_REINFORCEMENTS ready units to Kerunian territories. Returns the total.

        Unit ids follow the engine's convention for new units (lowest id free in
        that garrison — ids are only unique per garrison).
        """
        low, high = KERUNIAN_REINFORCEMENTS
        if high <= 0:
            return 0
        gs = self.game_state
        total = 0
        for territory in sorted(t for t, owner in gs.territory_owners.items() if owner == RED):
            if KERUNIAN_REINFORCEMENTS_FRONT_ONLY and not any(
                    gs.territory_owners.get(n) == PLAYER for n in map_data.get_neighbors(territory)):
                continue
            room = gs.MAX_ARMIES_PER_TERRITORY - gs.get_territory_total_armies(territory)
            count = min(room, self.rng.randint(low, high))
            if count <= 0:
                continue
            garrison = gs.territory_garrisons.get(territory, {}).get(RED) or {}
            used = {u.get('id') for u in garrison.get('units', [])}
            units = []
            next_id = 0
            for _ in range(count):
                while next_id in used:
                    next_id += 1
                used.add(next_id)
                units.append(gs._make_unit(self.rng.choice(BASIC_UNIT_TYPES), next_id, status='ready'))
            gs.add_garrison(territory, RED, unmoved=count, units=units)
            gs.sync_legacy_garrison_data(territory)
            total += count
        if total:
            gs.invalidate_army_count_cache()
            logger.info(f"Tale: {total} Kerunian reinforcements arrived")
        return total

    def _forced_attack_sources(self, target):
        """Kerunian territories next to `target`: [(territory, [ready unit ids that may go])]."""
        gs = self.game_state
        sources = []
        for neighbor in map_data.get_neighbors(target):
            if gs.territory_owners.get(neighbor) != RED:
                continue
            units = _ready_units(gs, neighbor, RED)
            spare = units[:max(0, len(units) - FORCED_ATTACK_KEEP)]
            if spare:
                sources.append((neighbor, [u['id'] for u in spare]))
        # Biggest stacks first, so an attack comes from as few places as possible
        sources.sort(key=lambda s: -len(s[1]))
        return sources

    def _order_forced_attack(self):
        """Attack the Zjoal border territory where the Kerunians have the best odds.

        Odds = units the Kerunians can send (sources' spare units, capped by the
        room left under get_ai_attack_cap) minus its defenders; ties go to the
        weaker defender. Returns True if an order was placed.
        """
        gs = self.game_state
        best = None
        for target, owner in gs.territory_owners.items():
            if owner != PLAYER:
                continue
            room = attack_cap_for_turn(self.get_current_turn()) - sum(
                o.army_count for o in gs.movement_orders
                if o.player == RED and o.to_territory == target)
            if room <= 0:
                continue
            sources = self._forced_attack_sources(target)
            available = min(room, sum(len(ids) for _, ids in sources))
            if available <= 0:
                continue
            defenders = gs.get_territory_total_armies(target)
            is_objective = FORCED_ATTACK_OBJECTIVES_FIRST and target in OBJECTIVE_TERRITORIES
            key = (is_objective, available - defenders, -defenders)
            if best is None or key > best[0]:
                best = (key, target, sources, available)
        if best is None:
            return False
        _key, target, sources, to_send = best
        sent = 0
        for source, ids in sources:
            if sent >= to_send:
                break
            batch = ids[:to_send - sent]
            if gs.add_movement_order_for_units(source, target, batch, player=RED):
                sent += len(batch)
        if sent:
            logger.info(f"Tale: forced Kerunian attack on {target} with {sent} units")
        return sent > 0

    def _on_player_turn_start(self):
        """Start of a player turn: the hold may be over, otherwise rebellions break out.

        _last_turn_handled stops a repeated announcement (or a reload) from
        applying the same turn twice. The player's very first turn sends no
        announcement, which is fine: nothing happens on turn 1.
        """
        gs = self.game_state
        if gs.phase == 'ended' or gs.turn_number == self._last_turn_handled:
            return
        self._last_turn_handled = gs.turn_number

        # HOLD_TURNS full turns survived with both objectives held
        if gs.turn_number >= HOLD_TURNS and self._holds_objectives():
            logger.info(f"Tale: held out for {HOLD_TURNS} turns — victory")
            for quest in self.quest_log:
                quest['completed'] = True
            self._start_victory()
            return

        rebelled = [t for _ in range(rebellions_for_turn(self.get_current_turn()))
                    if (t := self._roll_rebellion())]
        if rebelled:
            # One voiced line per turn, however many territories rose up: the
            # first rebellion of the Tale gets T2R1, every later one T2R+
            if self._rebellion_announced:
                self._queue_transmission(REBELLION_TRANSMISSION)
            else:
                self._queue_transmission(FIRST_REBELLION_TRANSMISSION)
                self._rebellion_announced = True

    def get_rebellion_candidates(self):
        """Zjoal territories that may rebel (sorted, for determinism)."""
        return sorted(t for t, owner in self.game_state.territory_owners.items()
                      if owner == PLAYER and t not in REBELLION_IMMUNE)

    def _roll_rebellion(self):
        """One random eligible Zjoal territory rebels. Returns it (or None)."""
        candidates = self.get_rebellion_candidates()
        if not candidates:
            return None
        territory = self.rng.choice(candidates)
        self._rebel_territory(territory)
        return territory

    def _rebel_territory(self, territory):
        """Hand a Zjoal territory to the Nordian Rebels with its armies and buildings.

        Buildings, construction, training queues and castle upgrades are keyed
        by territory, so they follow the new owner automatically. Nobody has
        Heroes in this Tale, so no Keep hero can be caught here.
        """
        gs = self.game_state

        # Drop any of the player's orders touching this territory (none are
        # expected at turn start, but a stale one must not fire from Rebel land)
        for index in range(len(gs.movement_orders) - 1, -1, -1):
            order = gs.movement_orders[index]
            if order.player == PLAYER and territory in (order.from_territory, order.to_territory):
                gs.cancel_movement_order(index)

        # The garrison changes sides unit for unit
        garrisons = gs.territory_garrisons.setdefault(territory, {})
        old = garrisons.pop(PLAYER, None) or {}
        units = old.get('units', [])
        for unit in units:
            unit['status'] = 'ready'
            unit['order'] = None
        gs.territory_owners[territory] = REBELS
        if units:
            gs.set_garrison_armies(territory, REBELS, unmoved=len(units), moved=0, units=units)
        else:
            # Empty land: no garrison entry, just resync the legacy army counters
            gs.sync_legacy_garrison_data(territory)

        # Back in play if the player had wiped them out
        gs.eliminated_players.discard(REBELS)

        # Same cache invalidation as a conquest (military.py _update_battle_results)
        gs._territory_owners_version += 1
        gs.invalidate_income_cache()
        gs.invalidate_army_count_cache()
        gs.invalidate_territorial_bonus_cache()

        message = f"{territory} has rebelled and joined the {FACTION_NAMES[REBELS]}!"
        gs.add_message(message)
        # Red toast without the denial sound — it's news, not a refused action
        notifications = getattr(self.main_game, 'chat_notification_effect', None)
        if notifications:
            notifications.add_system_notification(message)
        logger.info(f"Tale: {territory} rebelled ({len(units)} units defected)")

    def _holds_objectives(self):
        owners = self.game_state.territory_owners
        return all(owners.get(t) == PLAYER for t in OBJECTIVE_TERRITORIES)

    def _check_objectives(self):
        """Defeat the moment Lunedale or Free Cities is no longer the player's."""
        if not self._holds_objectives():
            if not (self.defeat_sequence_active or self._pending_defeat or self._defeat_waiting):
                lost = [t for t in OBJECTIVE_TERRITORIES
                        if self.game_state.territory_owners.get(t) != PLAYER]
                logger.info(f"Tale: {', '.join(lost)} lost — defeat")
            self._start_defeat()

    def _start_victory(self):
        """Start the victory sequence (deferred until battles finish)."""
        if (self.victory_sequence_active or self._pending_victory or self._victory_waiting
                or self.defeat_sequence_active or self._pending_defeat or self._defeat_waiting):
            return
        self.game_state.winner = PLAYER
        self.game_state.phase = 'ended'
        self._victory_waiting = True

    def _start_defeat(self):
        """Start the defeat sequence (deferred until battles finish)."""
        if (self.defeat_sequence_active or self._pending_defeat or self._defeat_waiting
                or self.victory_sequence_active or self._pending_victory or self._victory_waiting):
            return
        self.game_state.phase = 'ended'
        self._defeat_waiting = True

    # ========================================================================
    # INPUT
    # ========================================================================

    def handle_click(self, pos):
        """Left clicks on the Turns widget (input/mouse_handler Priority 4.5).

        The widget has nothing to press, but it swallows clicks so they never
        select the map beneath it. Returns True if the click was consumed.
        """
        return bool(self.active and self._widget_rect is not None
                    and self._widget_rect.collidepoint(pos))

    # ========================================================================
    # RENDERING
    # ========================================================================

    def render(self, screen):
        """Draw Tale overlays after the normal game UI (map, panels, sidebar)."""
        if not self.active:
            return

        # Widget first, so the endgame fade covers it
        self._render_turns_widget(screen)

        if self.victory_sequence_active:
            render_endgame_sequence(self, screen, 'victory')
        elif self.defeat_sequence_active:
            render_endgame_sequence(self, screen, 'defeat')

        if self.transmission_overlay:
            self.transmission_overlay.render(screen)

    def _layout_widget(self):
        """(Re)compute the widget's rects; rebuild size-dependent caches if needed.

        Keyed on screen size, ui_scale, map bottom and chat-box state, so a
        resolution change (apply_display_settings) is picked up automatically.
        """
        game = self.main_game
        screen = game.screen
        s = getattr(game, 'ui_scale', 1.0) or 1.0
        map_bottom = getattr(game, 'TOP_PANEL_HEIGHT', 0) + getattr(game, 'MAP_HEIGHT', screen.get_height())
        chat_open = bool(getattr(game, 'chat_input_active', False))
        key = (screen.get_size(), round(s, 4), map_bottom, chat_open)
        if key == self._widget_key:
            return
        size_changed = self._widget_key is None or self._widget_key[:3] != key[:3]
        self._widget_key = key

        from utils.surface_utils import load_cached_image
        crop_w, crop_h = BAR_FRAME_CROP[2], BAR_FRAME_CROP[3]
        bar_w = max(60, int(HOLD_BAR_WIDTH_REF * s))
        bar_h = max(8, round(bar_w * crop_h / crop_w))
        margin = int(HOLD_MARGIN_REF * s)
        bottom = map_bottom - margin - (int(HOLD_CHAT_LIFT_REF * s) if chat_open else 0)

        self._bar_rect = pygame.Rect(margin, bottom - bar_h, bar_w, bar_h)
        self._label_size = max(12, int(HOLD_LABEL_SIZE_REF * s))
        label_h = self._font(self._label_size).get_height()
        self._label_rect = pygame.Rect(0, 0, bar_w, label_h)
        self._label_rect.midbottom = (self._bar_rect.centerx, self._bar_rect.top)
        self._widget_rect = self._label_rect.union(self._bar_rect)
        self._shadow_offset = max(1, int(2 * s))

        # Fill window of the frame, in screen coordinates
        sx, sy = bar_w / crop_w, bar_h / crop_h
        self._fill_rect = pygame.Rect(
            self._bar_rect.x + round(BAR_FILL_LEFT * sx),
            self._bar_rect.y + round(BAR_FILL_TOP * sy),
            max(1, round((BAR_FILL_RIGHT - BAR_FILL_LEFT) * sx)),
            max(1, round((BAR_FILL_BOTTOM - BAR_FILL_TOP) * sy)))
        self._fill_hidden = round(BAR_FILL_HIDDEN_LEFT * sx)

        if size_changed:
            # Frame: crop BattleBar.png to its opaque bounds once, scale per size
            if self._bar_frame_src is None:
                raw = load_cached_image("assets/BattleBar.png", alpha=True)
                if raw is not None:
                    self._bar_frame_src = raw.subsurface(pygame.Rect(BAR_FRAME_CROP)).copy()
                else:
                    logger.warning("Tale: BattleBar.png missing — drawing a plain bar frame")
            self._bar_frame = (pygame.transform.smoothscale(self._bar_frame_src, (bar_w, bar_h))
                               if self._bar_frame_src is not None else None)
            # Vertical blue gradient, blitted partially to show the current value
            fill = pygame.Surface(self._fill_rect.size)
            h = self._fill_rect.height
            for y in range(h):
                t = y / max(1, h - 1)
                color = tuple(int(a + (b - a) * t) for a, b in zip(HOLD_FILL_TOP_COLOR, HOLD_FILL_BOTTOM_COLOR))
                pygame.draw.line(fill, color, (0, y), (self._fill_rect.width, y))
            self._bar_fill = fill
            self._text_cache.clear()

    def _font(self, size):
        """Cinzel font per size (own instances, like the other menu screens)."""
        font = self._font_cache.get(size)
        if font is None:
            try:
                font = pygame.font.Font(HOLD_FONT_PATH, size)
            except (pygame.error, FileNotFoundError, OSError):
                font = pygame.font.Font(None, size)
            self._font_cache[size] = font
        return font

    def _text(self, text, size, color):
        """Cached text surface (never font.render() per frame)."""
        key = (text, size, color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 64:
                self._text_cache.clear()
            surf = self._font(size).render(text, True, color)
            self._text_cache[key] = surf
        return surf

    def _blit_shadowed(self, screen, surf, shadow, pos):
        """Blit text with a dark drop shadow so it reads over any map colour."""
        off = self._shadow_offset
        screen.blit(shadow, (pos[0] + off, pos[1] + off))
        screen.blit(surf, pos)

    def _render_turns_widget(self, screen):
        """'Turns to Hold: N' label over a BattleBar that drains by one each turn."""
        self._layout_widget()

        text = f"Turns to Hold: {self.get_turns_remaining()}"
        label = self._text(text, self._label_size, HOLD_LABEL_COLOR)
        shadow = self._text(text, self._label_size, (0, 0, 0))
        self._blit_shadowed(screen, label, shadow, label.get_rect(midbottom=self._label_rect.midbottom).topleft)

        # Bar: dark track, blue fill proportional to the (eased) value, frame on top
        fill_rect = self._fill_rect
        screen.fill(HOLD_TRACK_COLOR, fill_rect)
        frac = max(0.0, min(1.0, self._display_remaining / HOLD_TURNS))
        if frac > 0:
            width = self._fill_hidden + round((fill_rect.width - self._fill_hidden) * frac)
            screen.blit(self._bar_fill, fill_rect.topleft, area=pygame.Rect(0, 0, width, fill_rect.height))
        if self._bar_frame is not None:
            screen.blit(self._bar_frame, self._bar_rect.topleft)
        else:
            pygame.draw.rect(screen, (181, 166, 66), fill_rect.inflate(4, 4), 2)

    # ========================================================================
    # QUEST LOG
    # ========================================================================

    def get_quest_log(self):
        return self.quest_log

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _cleanup(self):
        """Restore shared state touched by the Tale."""
        logger.info("Cleaning up Tale 'Final Breaths'")
        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        map_data.clear_enabled_territories()
        self.game_state.player_taxation_override = {}
        if self.original_flag_icons and hasattr(self.main_game, 'army_flag_icons'):
            for i, flags in self.original_flag_icons.items():
                self.main_game.army_flag_icons[i] = flags
        self.active = False

    def deactivate(self):
        """Deactivate the Tale (called on exit)."""
        self._cleanup()
