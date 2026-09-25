# -*- coding: utf-8 -*-
# tale_lack_of_funds.py
# Book of Tales — Tale I: "Lack of Funds"
#
# Map: Azincournean Highlands (map_id 'azincournean_highlands', loaded by main.py's
# _TALE_REGISTRY config, not by this module).
# 4 factions, all hostile to one another:
#   0 = the player (Londic Empire, Blue)    capital Generax
#   1 = Aelatanaic Tribes (Yellow, Medium)  capital Leyana
#   2 = Heilonic Kingdoms (Green, Hard)     capital Entaron
#   3 = Kingdom of Daurels (Red, Hard)      capital Daurels
# The 13 unassigned territories are neutral, each guarded by 1 random unit.
#
# Unlike campaign missions 2-7, the AI factions are driven by the BUILT-IN AI
# (block_ai is False) at the difficulties set in the registry config.
#
# Victory: the Aelatanaic Tribes own no territories.
# Defeat:  Generax is conquered.

import random
import pygame
import map_data
from utils.logger import get_logger
# Shared campaign utilities (TransmissionOverlay, camera animation, endgame sequences)
from campaign_utils import TransmissionOverlay, CameraZoomAnimation
from campaign_utils import update_endgame_sequence, render_endgame_sequence

logger = get_logger(__name__)

# ============================================================================
# TALE CONFIGURATION
# ============================================================================

TALE_ID = 'tale_1'

# Player indices (match main.py _TALE_REGISTRY['tale_1'] config order)
PLAYER = 0
YELLOW = 1   # Aelatanaic Tribes
GREEN = 2    # Heilonic Kingdoms
RED = 3      # Kingdom of Daurels

CAPITAL = "Generax"  # Player capital: losing it is defeat

# Starting ownership. Every other territory on the map is neutral (owner -1).
FACTION_TERRITORIES = {
    PLAYER: ["North Angarfen Forest", "Loira", "South Angarfen Forest", "Alanca", "Lires",
             "Generax Pastures", "Generax", "Generax Fields", "Avantgardian Road", "Lanta"],
    YELLOW: ["Velene", "Astrae", "Lantaran Forest", "Astraean Coast", "Nixraec Forest",
             "Leyana", "Atoney", "Venira", "Delunce", "Beleton", "Hosfan Fields",
             "The Peaks of Ancaquarne", "Hosfan", "Eleques"],
    RED: ["Daurels", "North Daurels Pass", "Eirance", "Aurent", "Valley of Lossarne",
          "Passes of Finles", "Arcessfort", "Emmine"],
    GREEN: ["Entaron", "Plein", "Anderu", "Aiven Crossing", "Arcepte", "Bolere", "Beleta",
            "Great South Heilonic Fields", "Pardes", "Lecce"],
}

FACTION_CAPITALS = {PLAYER: "Generax", YELLOW: "Leyana", GREEN: "Entaron", RED: "Daurels"}

# Colours by player index: Blue, Yellow, Green, Red (same RGB as missions 4/6)
PLAYER_COLORS = [
    (100, 150, 255),   # Player 0: Blue (player)
    (255, 220, 100),   # Player 1: Yellow (Aelatanaic Tribes)
    (100, 200, 100),   # Player 2: Green (Heilonic Kingdoms)
    (255, 100, 100),   # Player 3: Red (Kingdom of Daurels)
]

# Flag icon slot each player takes from the default army_flag_icons order
# (0=Red, 1=Blue, 2=Green, 3=Yellow).
FLAG_ICON_SOURCE = {PLAYER: 1, YELLOW: 3, GREEN: 2, RED: 0}

FACTION_NAMES = {
    PLAYER: None,                 # Human player keeps their profile name
    YELLOW: "Aelatanaic Tribes",
    GREEN: "Heilonic Kingdoms",
    RED: "Kingdom of Daurels",
}

STARTING_GOLD = {PLAYER: 750, YELLOW: 1500, GREEN: 2500, RED: 2000}

# --- Buildings ---
# Red and Green: every plot filled with this mix (no Keeps). Counts are allocated
# exactly per faction by largest remainder, then shuffled across its plots.
FULL_BUILD_MIX = [
    ('Mine', 0.25),
    ('Farm', 0.25),
    ('Barracks', 0.30),
    ('Training Grounds', 0.10),
    ('Square', 0.10),
]
FULL_BUILD_FACTIONS = (GREEN, RED)

# Player and Yellow: fixed buildings (on plot 0) plus a few scattered on random free plots
FIXED_BUILDINGS = {
    PLAYER: {"Generax": "Barracks", "Lires": "Square"},
    YELLOW: {"Atoney": "Barracks", "Leyana": "Barracks"},
}
SCATTERED_BUILDINGS = {
    PLAYER: [('Farm', 4), ('Mine', 2)],
    YELLOW: [('Farm', 4), ('Mine', 2)],
}

# --- Armies ---
BASIC_UNIT_TYPES = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
PLAYER_CAPITAL_ARMY = [('Pikeman', 2), ('Archer', 1), ('Swordsman', 1), ('Captain', 1)]
# Each of these units goes to a random player territory
PLAYER_SCATTERED_ARMY = [('Swordsman', 2), ('Cavalry', 2), ('Archer', 2)]
# (min, max) random basic units in EACH territory of these factions
RANDOM_ARMY_RANGE = {YELLOW: (1, 2), GREEN: (2, 6), RED: (2, 6)}
# Neutral territories each get this many random basic units (slows early expansion)
NEUTRAL_ARMY_SIZE = 1

# --- AI rules (enforced through is_ai_target_allowed / is_action_allowed) ---
# The three AI factions never target each other. Red/Green never take neutral
# land and leave the player alone until the player orders an attack on them.
# Yellow sits still (no attacks at all) for its first N turns, and cannot train
# units from its Barracks for its first M turns.
# Scale for the built-in AI's readability pauses (ai_player._pace): 0 removes the
# thinking time and the gaps between actions, so AI turns pass about as fast as
# the scripted AI in missions 2-7. Army movement animations still play.
AI_DELAY_SCALE = 0.0
YELLOW_NO_ATTACK_TURNS = 3
YELLOW_NO_TRAINING_TURNS = 2
RETALIATING_FACTIONS = (GREEN, RED)

# --- Popularity (unique to this Tale) ---
# Drops at the start of each player turn from the 2nd on, by DECAY_START, then
# +DECAY_STEP more every turn (6, 11, 16, 21, ...). Investing buys INVEST_GAIN
# popularity (capped at POPULARITY_MAX), resets the drop to DECAY_START, and
# raises the next investment's price by INVEST_COST_STEP.
POPULARITY_MAX = 100
DECAY_START = 6    # Raised from 4 after playtesting: popularity was not punishing enough
DECAY_STEP = 5     # Raised from 2 (same reason)
INVEST_BASE_COST = 100
INVEST_COST_STEP = 10
INVEST_GAIN = 10
# Revolt: rolled BEFORE the drop, against the popularity the player ended their
# last turn with (so investing up to 100 fully protects the next turn start).
# REVOLT_CHANCE_PER_POINT % chance per missing popularity point (capped at 100%)
# that ONE eligible player territory defects to the Aelatanaic Tribes (buildings
# and armies too). At 2: 90 pop = 20%, 75 = 50%, 50 or lower = certain.
# A territory is eligible while popularity <= the threshold for its income tier
# (map_data tier 1/2/3 = 10/15/20 gold): poor lands revolt first, rich ones only
# once popularity is low. The capital never revolts.
REVOLT_THRESHOLD_BY_TIER = {1: 100, 2: 75, 3: 50}
REVOLT_CHANCE_PER_POINT = 2   # Doubled from 1 so revolts are a real threat early on
REVOLT_FACTION = YELLOW

# Popularity widget (bottom-left of the map area). *_REF sizes are at ui_scale 1.0.
POP_BAR_WIDTH_REF = 320
POP_BUTTON_WIDTH_REF = 230
POP_MARGIN_REF = 14          # From the map's left and bottom edges
POP_GAP_REF = 6              # Between label, bar and button
POP_LABEL_SIZE_REF = 22
POP_BUTTON_FONT_REF = 17
POP_CHAT_LIFT_REF = 50       # Lift above the chat input box while it is open
POP_EASE_PER_SEC = 40.0      # Bar drains/refills at this many points per second
# BattleBar.png (1536x1024): the frame's opaque bounds, and the inner window
# (in coordinates of that crop) where the fill shows. The fill rect overshoots
# the window slightly so its edges hide under the frame; FILL_HIDDEN_LEFT px of
# it sit under the left end cap, so an empty bar shows no blue.
BAR_FRAME_CROP = (46, 358, 1439, 174)
BAR_FILL_LEFT, BAR_FILL_RIGHT = 216, 1226
BAR_FILL_TOP, BAR_FILL_BOTTOM = 36, 128
BAR_FILL_HIDDEN_LEFT = 21
POP_TRACK_COLOR = (18, 18, 28)
POP_FILL_TOP_COLOR = (120, 170, 255)
POP_FILL_BOTTOM_COLOR = (35, 75, 200)
POP_LABEL_COLOR = (240, 230, 200)
POP_BUTTON_TEXT = (255, 255, 255)
POP_BUTTON_TEXT_DISABLED = (150, 140, 120)
POP_FONT_PATH = 'assets/fonts/Cinzel-SemiBold.ttf'
# clicked_element id for the Invest button's click flash (main.trigger_click_flash)
INVEST_FLASH_ID = ('tale_button', 'invest')

# --- Transmissions ---
# Voice lines live in assets/sounds/transmissions/ and are keyed by file stem
# (global_sound.load_transmission_sounds loads them for any game with a campaign map).
EMPEROR_SPEAKER = "Emperor Kondaron"
ADVISOR_SPEAKER = "Imperial Advisor"   # Addresses the emperor as "master" in T1T2

# Intro: zoom to Generax, then three voiced transmissions. Gameplay (and the
# planning timer) is paused until it ends; ESC skips the current line.
# Format: (action, param, speaker, text, voice_key, duration_seconds)
INTRO_SEQUENCE = [
    ('zoom_to', "Generax", None, "", None, 0.0),
    ('say', None, EMPEROR_SPEAKER,
     "Behold! On the horizon! The primitive Aelatanaic tribes are amassing! "
     "Take their lands as our own!", 'T1T1', 8.0),
    ('say', None, ADVISOR_SPEAKER,
     "But master, the people are already on the edge. If we do not cater to them.. "
     "they might revolt!", 'T1T2', 7.0),
    ('say', None, EMPEROR_SPEAKER,
     "I do NOT care! I am the emperor! Attack the tribes!", 'T1T3', 6.0),
]
INTRO_LINE_GAP = 1.0   # Silence between consecutive voiced intro lines (as mission 7)

# Gameplay / endgame transmissions: (speaker, text, voice_key, duration_seconds)
REVOLT_TRANSMISSION = (ADVISOR_SPEAKER, "A territory has rebelled against us!", 'T1Revolt', 3.0)
VICTORY_TRANSMISSION = (EMPEROR_SPEAKER,
                        "We have done it! The savages have been cleansed, and their fertile "
                        "lands are ours! Londia reigns supreme!", 'T1TWin', 7.0)
DEFEAT_TRANSMISSION = (ADVISOR_SPEAKER,
                       "The bastion of Generax is lost! Our battle is over.", 'T1TLoss', 4.0)

# Opening camera: zoom towards the player's capital
START_CAMERA_ZOOM = 2.5
START_CAMERA_DURATION = 1.0


def allocate_building_counts(num_plots, mix, rng):
    """Split num_plots between building types in proportion to mix.

    Uses largest-remainder rounding so the counts always sum to num_plots;
    ties between equal remainders are broken randomly.

    Returns: list of building type strings, length num_plots (unshuffled).
    """
    exact = [(btype, share * num_plots) for btype, share in mix]
    counts = {btype: int(value) for btype, value in exact}
    leftover = num_plots - sum(counts.values())
    # Highest fractional remainder first; random key breaks ties
    by_remainder = sorted(exact, key=lambda e: (-(e[1] - int(e[1])), rng.random()))
    for btype, _ in by_remainder[:leftover]:
        counts[btype] += 1
    pool = []
    for btype, _ in mix:
        pool.extend([btype] * counts[btype])
    return pool


class TaleLackOfFunds:
    """
    Book of Tales — Tale I: "Lack of Funds".

    Standard mission interface (see CODE_GUIDE "Mission Exit Contract" and the
    tutorial_mission hooks): update / update_ai_turn / render / notify_event /
    is_action_allowed / get_quest_log / get_save_state / restore_save_state.

    rng: optional random.Random for the randomised setup (tests pass a seeded one).
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

        # Quest log — mirrors the Objectives in the Book of Tales description
        self.quest_log = [
            {'text': 'Conquer the territories of the Aelatanaic Tribes', 'completed': False},
            {'text': 'Do not lose control over the city of Generax', 'completed': False},
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

        # Turns each AI faction has started (counted on 'turn_announcement_done');
        # the first turn is 1. Drives Yellow's opening restrictions.
        self.faction_turns = {YELLOW: 0, GREEN: 0, RED: 0}
        # Red/Green turn hostile to the player (independently) the moment the
        # player issues an attack order against one of their territories.
        self.hostile = {faction: False for faction in RETALIATING_FACTIONS}

        # Popularity state (see the POPULARITY constants)
        self.popularity = POPULARITY_MAX
        self.popularity_decay = DECAY_START     # Next drop
        self.invest_cost = INVEST_BASE_COST     # Price of the next investment
        # gs.turn_number of the last drop — guarantees one drop per player turn
        self._last_decay_turn = None
        # Bar value actually drawn; eases towards self.popularity so changes show
        self._display_popularity = float(self.popularity)

        # Popularity widget layout + caches (rebuilt when the screen/scale changes)
        self._widget_key = None
        self._widget_rect = None
        self._bar_rect = None
        self._invest_rect = None
        self._label_pos = None
        self._bar_frame_src = None      # Cropped BattleBar.png, loaded once
        self._bar_frame = None          # Frame scaled to the bar size
        self._bar_fill = None           # Blue gradient, full bar size
        self._btn_cache = {}
        self._font_cache = {}
        self._text_cache = {}

        # Unique unit ids across the whole setup
        self._next_unit_id = 0

        # All 55 territories stay enabled (neutrals are playable), but clear any
        # filter a previous mission might have leaked.
        map_data.clear_enabled_territories()

        self._setup_initial_state()
        self._advance_intro()   # Step 0: zoom to Generax

        logger.info("Tale 'Lack of Funds' initialized: 4 factions on Azincournean Highlands")

    # ========================================================================
    # INITIAL STATE
    # ========================================================================

    def _setup_initial_state(self):
        """Configure factions, ownership, buildings and armies."""
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

        # Names and gold
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name
        for player_id, gold in STARTING_GOLD.items():
            if player_id < gs.num_players:
                gs.player_gold[player_id] = gold

        # Wipe whatever initialize_game() placed (capital claims, starting armies)
        owner_of = {t: p for p, terrs in FACTION_TERRITORIES.items() for t in terrs}
        for territory in list(gs.territory_owners.keys()):
            gs.territory_owners[territory] = owner_of.get(territory, -1)
            gs.territory_garrisons[territory] = {}
            gs.buildings[territory] = {}

        self._place_buildings()
        self._place_armies()

        for player_id, capital in FACTION_CAPITALS.items():
            gs.player_starting_territories[player_id] = capital

        # Ownership was rewritten wholesale — invalidate every derived cache
        gs._territory_owners_version += 1
        gs.invalidate_income_cache()
        gs.invalidate_army_count_cache()
        gs.invalidate_territorial_bonus_cache()

        # Technologies: nothing is pre-researched; the engine default (row 0
        # researchable, nothing researched) is exactly what this Tale wants.

    def _plot_count(self, territory):
        """Number of building plots in a territory (from the map's plot data)."""
        return len(map_data.get_plots(territory) or [])

    def _place_buildings(self):
        """Fill Red/Green plots from FULL_BUILD_MIX; fixed + scattered for player/Yellow."""
        gs = self.game_state

        # --- Red and Green: every plot filled ---
        for faction in FULL_BUILD_FACTIONS:
            slots = [(t, i) for t in FACTION_TERRITORIES[faction]
                     for i in range(self._plot_count(t))]
            pool = allocate_building_counts(len(slots), FULL_BUILD_MIX, self.rng)
            # The engine allows one Training Grounds per territory: reshuffle until
            # no territory holds two (a handful of tries at most with ~1-2 TGs).
            for _ in range(200):
                self.rng.shuffle(pool)
                tg_territories = [slots[i][0] for i, b in enumerate(pool) if b == 'Training Grounds']
                if len(tg_territories) == len(set(tg_territories)):
                    break
            for (territory, plot_idx), building in zip(slots, pool):
                gs.buildings[territory][plot_idx] = building

        # --- Player and Yellow: fixed buildings on plot 0, then scattered ones ---
        for faction, fixed in FIXED_BUILDINGS.items():
            for territory, building in fixed.items():
                if self._plot_count(territory) > 0:
                    gs.buildings[territory][0] = building
            free = [(t, i) for t in FACTION_TERRITORIES[faction]
                    for i in range(self._plot_count(t)) if i not in gs.buildings[t]]
            wanted = [b for b, count in SCATTERED_BUILDINGS.get(faction, []) for _ in range(count)]
            if len(wanted) > len(free):
                logger.warning(f"Tale: faction {faction} has only {len(free)} free plots "
                               f"for {len(wanted)} scattered buildings")
            for (territory, plot_idx), building in zip(self.rng.sample(free, min(len(free), len(wanted))),
                                                       wanted):
                gs.buildings[territory][plot_idx] = building

    def _make_units(self, unit_types):
        """Create ready (unmoved) unit dicts with unique ids."""
        units = []
        for unit_type in unit_types:
            units.append(self.game_state._make_unit(unit_type, self._next_unit_id, status='ready'))
            self._next_unit_id += 1
        return units

    def _random_unit_types(self, count):
        return [self.rng.choice(BASIC_UNIT_TYPES) for _ in range(count)]

    def _place_armies(self):
        """Starting garrisons for every faction plus the neutral guards."""
        gs = self.game_state
        armies = {}  # territory -> (owner, [unit types])

        # Player: fixed capital army, then single units scattered over their lands
        armies[CAPITAL] = (PLAYER, [u for u, n in PLAYER_CAPITAL_ARMY for _ in range(n)])
        for unit_type, count in PLAYER_SCATTERED_ARMY:
            for _ in range(count):
                territory = self.rng.choice(FACTION_TERRITORIES[PLAYER])
                armies.setdefault(territory, (PLAYER, []))[1].append(unit_type)

        # Yellow, Green, Red: a random-sized random army in every territory
        for faction, (low, high) in RANDOM_ARMY_RANGE.items():
            for territory in FACTION_TERRITORIES[faction]:
                armies[territory] = (faction, self._random_unit_types(self.rng.randint(low, high)))

        # Neutral territories: a small guard each
        for territory, owner in gs.territory_owners.items():
            if owner == -1:
                armies[territory] = (-1, self._random_unit_types(NEUTRAL_ARMY_SIZE))

        for territory, (owner, unit_types) in armies.items():
            units = self._make_units(unit_types)
            gs.set_garrison_armies(territory, owner, unmoved=len(units), moved=0, units=units)

    def _start_camera(self, territory=CAPITAL):
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

    # ========================================================================
    # INTRO SEQUENCE
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

    def _show_transmission(self, text, duration, speaker=EMPEROR_SPEAKER, voice_key=None):
        """Show a transmission for `duration` seconds and play its voice line."""
        import main as _main
        screen = self.main_game.screen
        if not self.transmission_overlay:
            self.transmission_overlay = TransmissionOverlay(
                screen.get_width(), screen.get_height(), text, _main.TOP_PANEL_HEIGHT,
                speaker=speaker)
        else:
            self.transmission_overlay.set_text(text, speaker=speaker)
        self.transmission_duration = duration
        self.transmission_timer = 0.0
        if voice_key:
            from global_sound import play_transmission_sound
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
            # JSON keys must be strings; restored to ints below
            'faction_turns': {str(k): v for k, v in self.faction_turns.items()},
            'hostile': {str(k): v for k, v in self.hostile.items()},
            'popularity': self.popularity,
            'popularity_decay': self.popularity_decay,
            'invest_cost': self.invest_cost,
            '_last_decay_turn': self._last_decay_turn,
        }

    def restore_save_state(self, data):
        """Restore Tale-specific state. The opening camera move is dropped on load."""
        self.active = data.get('active', True)
        self.quest_log = data.get('quest_log', self.quest_log)
        self.timer_visible = data.get('timer_visible', True)
        self.allow_timer_expiry = data.get('allow_timer_expiry', True)
        self.game_frozen = data.get('game_frozen', False)
        for key, value in data.get('faction_turns', {}).items():
            if int(key) in self.faction_turns:
                self.faction_turns[int(key)] = value
        for key, value in data.get('hostile', {}).items():
            if int(key) in self.hostile:
                self.hostile[int(key)] = bool(value)
        self.popularity = data.get('popularity', self.popularity)
        self.popularity_decay = data.get('popularity_decay', self.popularity_decay)
        self.invest_cost = data.get('invest_cost', self.invest_cost)
        self._last_decay_turn = data.get('_last_decay_turn', self._last_decay_turn)
        self._display_popularity = float(self.popularity)   # No drain animation on load
        # Resuming mid-game: never replay the intro the constructor just started
        self.intro_active = False
        self.intro_step_index = len(INTRO_SEQUENCE)
        self._intro_waiting_for_camera = False
        self._intro_gap_timer = 0.0
        self.camera_animation = None
        self.transmission_overlay = None
        self.transmission_duration = 0.0
        self.transmission_queue = []
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

        # Intro sequence owns the frame until it ends (gameplay is paused)
        if self.intro_active:
            self._update_intro(delta_time)
            return None

        # Instant AI turns: skip the turn announcement banner for AI factions (as
        # missions 5-7 do). Completing it here runs the normal start-of-turn work
        # (construction, training, research) and lets handle_ai_turn() start the
        # built-in AI, which waits for turn_announcement_active to clear.
        gs = self.game_state
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

        # Popularity bar eases towards the real value so drops/investments visibly animate
        target = float(self.popularity)
        step = POP_EASE_PER_SEC * delta_time
        if abs(target - self._display_popularity) <= step:
            self._display_popularity = target
        else:
            self._display_popularity += step if target > self._display_popularity else -step

        # Transmission timer — the voice line stops when its text expires
        if self.transmission_overlay and self.transmission_duration > 0:
            self.transmission_timer += delta_time
            if self.transmission_timer >= self.transmission_duration:
                self.transmission_overlay = None
                self.transmission_duration = 0.0
                from global_sound import stop_transmission_sound
                stop_transmission_sound()

        gameplay_idle = self._is_gameplay_idle()

        # Queued gameplay transmissions (e.g. a revolt) wait for an idle moment
        if not self.transmission_overlay and self.transmission_queue and gameplay_idle:
            self._start_pending_transmission()

        # Deferred victory/defeat: wait for battles, popups and queued transmissions
        # to finish, then play the outro line; the victory/defeat screen (shared
        # campaign endgame sequence) starts once it expires.
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
    # AI CONTROL — the built-in AI plays all three factions
    # ========================================================================

    @property
    def block_ai(self):
        """False: ai_player runs its normal turn (and resolves its own battles)."""
        return False

    def execute_ai_turn_override(self):
        """Unused (block_ai is False); present for interface completeness."""
        return None

    def update_ai_turn(self, delta_time):
        """The built-in AI ends its own turns, so nothing to manage here."""
        return False

    # ========================================================================
    # ACTION GATING
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """Gate player/AI actions (queried by game_state and the UI)."""
        if not self.active:
            return True
        if self.victory_sequence_active or self.defeat_sequence_active:
            return False
        if self.game_paused or self.game_frozen:
            return False

        current = self.game_state.current_player

        # The player cannot train Heroes (AI factions still can)
        if action_type == 'train_hero' and current == PLAYER:
            return False

        # Yellow cannot train units from its Barracks for its opening turns.
        # start_training() queries this for every player, so the AI is gated too.
        if (action_type == 'train' and current == YELLOW
                and self.faction_turns[YELLOW] <= YELLOW_NO_TRAINING_TURNS):
            return False

        return True

    def is_ai_target_allowed(self, attacker, territory):
        """AI targeting rules for this Tale (see ai_military.mission_allows_ai_target).

        Moving within one's own land is always allowed. Otherwise:
          - Yellow: nothing during its first YELLOW_NO_ATTACK_TURNS turns, then
            the player's territories and neutral ones — never Red or Green.
          - Red/Green: only the player's territories, and only once the player
            has attacked that faction. Never neutral land or another AI faction.
        """
        owner = self.game_state.territory_owners.get(territory, -1)
        if owner == attacker:
            return True
        if attacker == YELLOW:
            if self.faction_turns[YELLOW] <= YELLOW_NO_ATTACK_TURNS:
                return False
            return owner in (PLAYER, -1)
        if attacker in RETALIATING_FACTIONS:
            return owner == PLAYER and self.hostile[attacker]
        return True

    def should_hide_hero_training(self):
        """Hide the Keep's hero training buttons on the player's turn."""
        return self.game_state.current_player == PLAYER

    def should_button_be_locked(self, button_id):
        return False

    def is_button_locked(self, button_id):
        return self.should_button_be_locked(button_id)

    def should_highlight_button(self, button_id):
        return False

    def is_timer_visible(self):
        return self.timer_visible

    def is_territory_interactive(self, territory_name):
        """Every territory on the map (including neutrals) is interactive."""
        return True

    def is_attack_target_blocked(self, territory_name):
        """The player may attack anyone (Red/Green retaliate — see notes)."""
        return False

    def get_adjacency_override(self, territory):
        return None

    def get_highlight_territory(self):
        return None

    def should_highlight_plot(self, territory, plot_index):
        return False

    # ========================================================================
    # EVENTS / VICTORY / DEFEAT
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """Receive gameplay events from hooked game systems."""
        if not self.active:
            return
        if event_type == 'territory_conquered':
            self._on_territory_conquered(kwargs.get('territory'), kwargs.get('new_owner'))
        elif event_type == 'turn_announcement_done':
            player = kwargs.get('player_index')
            if player in self.faction_turns:
                self.faction_turns[player] += 1
            elif player == PLAYER:
                self._on_player_turn_start()
        elif event_type == 'order_created':
            if kwargs.get('player') == PLAYER:
                self._check_provocation(kwargs.get('to_territory'))

    # ========================================================================
    # POPULARITY
    # ========================================================================

    def _on_player_turn_start(self):
        """Start of a player turn: a revolt may break out, THEN popularity drops.

        The revolt is rolled against the popularity the player ended their last
        turn with, so investing up to 100 before ending a turn fully protects
        the next turn start (the drop that follows shows as this turn's value).

        gs.turn_number is 0 on the player's first turn and increments each time
        play returns to the player, so the first roll + drop land on their 2nd
        turn. _last_decay_turn stops a repeated announcement (or a reload) from
        applying the same turn twice.
        """
        gs = self.game_state
        if gs.phase == 'ended' or gs.turn_number < 1 or gs.turn_number == self._last_decay_turn:
            return
        self._last_decay_turn = gs.turn_number
        self._roll_revolt()
        self.popularity = max(0, self.popularity - self.popularity_decay)
        self.popularity_decay += DECAY_STEP
        logger.info(f"Tale: popularity {self.popularity} (next drop {self.popularity_decay})")

    def get_revolt_chance(self):
        """Chance (0.0-1.0) of a revolt this turn: REVOLT_CHANCE_PER_POINT % per missing point."""
        missing = POPULARITY_MAX - self.popularity
        return max(0.0, min(1.0, missing * REVOLT_CHANCE_PER_POINT / 100.0))

    def _roll_revolt(self):
        """Roll get_revolt_chance(); on success one eligible territory defects."""
        chance = self.get_revolt_chance()
        if chance <= 0 or self.rng.random() >= chance:
            return None
        eligible = self.get_revolt_candidates()
        if not eligible:
            return None
        territory = self.rng.choice(eligible)
        self._revolt_territory(territory)
        return territory

    def get_revolt_candidates(self):
        """Player territories that can currently revolt (sorted, for determinism)."""
        tier_of_income = {income: tier for tier, income in map_data.TIER_INCOME.items()}
        candidates = []
        for territory, owner in self.game_state.territory_owners.items():
            if owner != PLAYER or territory == CAPITAL:
                continue
            tier = tier_of_income.get(map_data.get_territory_income(territory), 3)
            if self.popularity <= REVOLT_THRESHOLD_BY_TIER.get(tier, 50):
                candidates.append(territory)
        return sorted(candidates)

    def _revolt_territory(self, territory):
        """Hand a player territory to the Aelatanaic Tribes with its armies and buildings.

        Buildings, construction, training queues and castle upgrades are keyed
        by territory, so they follow the new owner automatically. The player
        cannot train Heroes in this Tale, so no Keep hero can be caught here.
        """
        gs = self.game_state

        # Drop any of the player's orders touching this territory (none are
        # expected at turn start, but a stale one must not fire from Yellow land)
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
        gs.territory_owners[territory] = REVOLT_FACTION
        if units:
            gs.set_garrison_armies(territory, REVOLT_FACTION, unmoved=len(units), moved=0, units=units)
        else:
            # Empty land: no garrison entry, just resync the legacy army counters
            gs.sync_legacy_garrison_data(territory)

        # Same cache invalidation as a conquest (military.py _update_battle_results)
        gs._territory_owners_version += 1
        gs.invalidate_income_cache()
        gs.invalidate_army_count_cache()
        gs.invalidate_territorial_bonus_cache()

        gs.add_message(f"{territory} has revolted and joined the {FACTION_NAMES[REVOLT_FACTION]}!")
        self._queue_transmission(REVOLT_TRANSMISSION)
        logger.info(f"Tale: {territory} revolted at popularity {self.popularity} "
                    f"({len(units)} units defected)")

    def can_invest(self):
        """Invest is usable on the player's own planning phase with enough gold."""
        gs = self.game_state
        return (self.active
                and gs.phase != 'ended'
                and not (self.game_paused or self.game_frozen)
                and gs.current_player == PLAYER
                and gs.turn_phase == 'planning'
                and not gs.turn_announcement_active
                and gs.player_gold[PLAYER] >= self.invest_cost)

    def invest(self):
        """Spend invest_cost gold: +popularity, drop resets, next price rises."""
        if not self.can_invest():
            return False
        gs = self.game_state
        cost = self.invest_cost
        gs.player_gold[PLAYER] -= cost
        self.popularity = min(POPULARITY_MAX, self.popularity + INVEST_GAIN)
        self.popularity_decay = DECAY_START
        self.invest_cost += INVEST_COST_STEP
        gs.add_message(f"Invested {cost} gold in internal affairs (popularity {self.popularity}).")
        logger.info(f"Tale: invested {cost}g -> popularity {self.popularity}, next cost {self.invest_cost}")
        return True

    def handle_click(self, pos):
        """Left clicks on the Popularity widget (input/mouse_handler Priority 4.5).

        The whole widget swallows clicks so they never select the map beneath it.
        Returns True if the click was consumed.
        """
        if not self.active or self._widget_rect is None or not self._widget_rect.collidepoint(pos):
            return False
        if self._invest_rect is not None and self._invest_rect.collidepoint(pos) and self.invest():
            from global_sound import sound_manager
            sound_manager.play_ui_click()
            if hasattr(self.main_game, 'trigger_click_flash'):
                self.main_game.trigger_click_flash(*INVEST_FLASH_ID)
        return True

    def _check_provocation(self, target_territory):
        """An attack order by the player turns that Red/Green faction hostile."""
        owner = self.game_state.territory_owners.get(target_territory, -1)
        if owner in self.hostile and not self.hostile[owner]:
            self.hostile[owner] = True
            name = FACTION_NAMES[owner]
            logger.info(f"Tale: player attacked {target_territory} — {name} turns hostile")
            self.game_state.add_message(f"The {name} will retaliate against your attack!")

    def _on_territory_conquered(self, territory, new_owner):
        """Defeat if Generax falls; victory once Yellow holds nothing."""
        if territory == CAPITAL and new_owner != PLAYER:
            logger.info("Tale: Generax has fallen — defeat")
            self._start_defeat()
            return
        self._check_victory()

    def _check_victory(self):
        """Victory when the Aelatanaic Tribes own no territory."""
        if any(owner == YELLOW for owner in self.game_state.territory_owners.values()):
            return
        logger.info("Tale: Aelatanaic Tribes eliminated — victory")
        for quest in self.quest_log:
            quest['completed'] = True
        self._start_victory()

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
    # RENDERING
    # ========================================================================

    def render(self, screen):
        """Draw Tale overlays after the normal game UI (map, panels, sidebar).

        main.py calls this after the HUD, so the Popularity widget sits above the
        map and all its markers; modal popups and menus still draw over it.
        """
        if not self.active:
            return

        # Popularity widget first, so the endgame fade/transmission covers it
        self._render_popularity(screen)

        if self.victory_sequence_active:
            render_endgame_sequence(self, screen, 'victory')
        elif self.defeat_sequence_active:
            render_endgame_sequence(self, screen, 'defeat')

        if self.transmission_overlay:
            self.transmission_overlay.render(screen)

    # ------------------------------------------------------------------------
    # Popularity widget
    # ------------------------------------------------------------------------

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

        from utils.surface_utils import load_cached_image, get_campaign_button_image
        crop_w, crop_h = BAR_FRAME_CROP[2], BAR_FRAME_CROP[3]
        bar_w = max(60, int(POP_BAR_WIDTH_REF * s))
        bar_h = max(8, round(bar_w * crop_h / crop_w))
        btn_img = get_campaign_button_image()
        btn_aspect = (btn_img.get_height() / btn_img.get_width()) if btn_img else 0.1977
        btn_w = max(60, int(POP_BUTTON_WIDTH_REF * s))
        btn_h = max(16, int(btn_w * btn_aspect))
        margin = int(POP_MARGIN_REF * s)
        gap = max(2, int(POP_GAP_REF * s))
        bottom = map_bottom - margin - (int(POP_CHAT_LIFT_REF * s) if chat_open else 0)

        x0 = margin
        self._invest_rect = pygame.Rect(0, 0, btn_w, btn_h)
        self._invest_rect.midbottom = (x0 + bar_w // 2, bottom)
        self._bar_rect = pygame.Rect(x0, self._invest_rect.top - gap - bar_h, bar_w, bar_h)
        self._label_size = max(12, int(POP_LABEL_SIZE_REF * s))
        self._button_font_size = max(10, int(POP_BUTTON_FONT_REF * s))
        label_h = self._font(self._label_size).get_height()
        label_rect = pygame.Rect(0, 0, bar_w, label_h)
        label_rect.midbottom = (self._bar_rect.centerx, self._bar_rect.top)
        self._label_rect = label_rect
        self._widget_rect = label_rect.union(self._bar_rect).union(self._invest_rect)
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
                color = tuple(int(a + (b - a) * t) for a, b in zip(POP_FILL_TOP_COLOR, POP_FILL_BOTTOM_COLOR))
                pygame.draw.line(fill, color, (0, y), (self._fill_rect.width, y))
            self._bar_fill = fill
            self._btn_cache.clear()
            self._text_cache.clear()

    def _font(self, size):
        """Cinzel font per size (own instances, like the other menu screens)."""
        font = self._font_cache.get(size)
        if font is None:
            try:
                font = pygame.font.Font(POP_FONT_PATH, size)
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

    def _button_surface(self, size, state):
        """CampaignBTN tinted per state — same tints as the Book of Tales buttons."""
        key = (size, state)
        surf = self._btn_cache.get(key)
        if surf is None:
            from utils.surface_utils import get_campaign_button_image
            img = get_campaign_button_image()
            if img is None:
                return None
            surf = pygame.transform.smoothscale(img, size)
            mult = (60, 60, 60, 255) if state == 'disabled' else (100, 100, 100, 255)
            surf.fill(mult, special_flags=pygame.BLEND_RGBA_MULT)
            if state == 'click':
                surf.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif state == 'hover':
                surf.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self._btn_cache[key] = surf
        return surf

    def _blit_shadowed(self, screen, surf, shadow, pos):
        """Blit text with a dark drop shadow so it reads over any map colour."""
        off = self._shadow_offset
        screen.blit(shadow, (pos[0] + off, pos[1] + off))
        screen.blit(surf, pos)

    def _render_popularity(self, screen):
        """'Popularity' label, BattleBar with a draining blue fill, Invest button."""
        self._layout_widget()

        # Label
        label = self._text("Popularity", self._label_size, POP_LABEL_COLOR)
        shadow = self._text("Popularity", self._label_size, (0, 0, 0))
        self._blit_shadowed(screen, label, shadow, label.get_rect(midbottom=self._label_rect.midbottom).topleft)

        # Bar: dark track, blue fill proportional to the (eased) value, frame on top
        fill_rect = self._fill_rect
        screen.fill(POP_TRACK_COLOR, fill_rect)
        frac = max(0.0, min(1.0, self._display_popularity / POPULARITY_MAX))
        if frac > 0:
            width = self._fill_hidden + round((fill_rect.width - self._fill_hidden) * frac)
            screen.blit(self._bar_fill, fill_rect.topleft, area=pygame.Rect(0, 0, width, fill_rect.height))
        if self._bar_frame is not None:
            screen.blit(self._bar_frame, self._bar_rect.topleft)
        else:
            pygame.draw.rect(screen, (181, 166, 66), fill_rect.inflate(4, 4), 2)

        # Invest button: disabled > click flash > hover > normal
        rect = self._invest_rect
        enabled = self.can_invest()
        if not enabled:
            state = 'disabled'
        elif getattr(self.main_game, 'clicked_element', None) == INVEST_FLASH_ID:
            state = 'click'
        elif rect.collidepoint(pygame.mouse.get_pos()):
            state = 'hover'
        else:
            state = 'normal'
        btn = self._button_surface(rect.size, state)
        if btn is not None:
            screen.blit(btn, rect.topleft)
        else:
            pygame.draw.rect(screen, (70, 60, 40) if state in ('hover', 'click') else (50, 42, 28),
                             rect, border_radius=6)
        text = f"Invest {self.invest_cost} Gold"
        color = POP_BUTTON_TEXT if enabled else POP_BUTTON_TEXT_DISABLED
        surf = self._text(text, self._button_font_size, color)
        screen.blit(surf, surf.get_rect(center=rect.center))

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
        logger.info("Cleaning up Tale 'Lack of Funds'")
        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        map_data.clear_enabled_territories()
        if self.original_flag_icons and hasattr(self.main_game, 'army_flag_icons'):
            for i, flags in self.original_flag_icons.items():
                self.main_game.army_flag_icons[i] = flags
        self.active = False

    def deactivate(self):
        """Deactivate the Tale (called on exit)."""
        self._cleanup()
