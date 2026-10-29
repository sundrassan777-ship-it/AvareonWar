"""
Enhanced Battle Interface

A cinematic multi-phase battle interface featuring:
- Side-by-side attacker/defender panels with BattlePlayerScreen.png backgrounds
- Strength comparison bars trading bolts of light (the light itself is drawn by
  ui/effects/battle_fx_effect.py, styled in battle_fx_style.py)
- Victory/defeat splash screens with zoom animation
- Battle report summary

Integration:
    - Replaces simple battle popup in main.py
    - Used when battle marker is clicked during battles phase
    - Pre-calculates battle result before animation, applies after

States:
    SETUP -> ANIMATING -> SPLASH -> REPORT -> Done
"""

import pygame
import math
import random
from enum import Enum, auto

import map_data
from config.constants import WINDOW_WIDTH, WINDOW_HEIGHT, WHITE, BLACK, CLICK_FLASH_DURATION_MS
from utils.logger import get_logger
from ui import battle_screen_kit, battle_screen_panels
from ui.effects.battle_fx_effect import BattleLight, Shot, spear_tip, tip_x
from ui.effects.battle_fx_style import (BAR_STYLE, BOLT_STYLE, BURN_STYLE, CHARGE_STYLE, FINALE_STYLE,
                                        ICON_GLOW_STYLE, charge_time)
from ui.effects.hero_fx_effect import stable_seed

logger = get_logger(__name__)

# ========================================
# CONSTANTS
# ========================================

# Reference resolution for scaling (all pixel values tuned for this)
REFERENCE_WIDTH = 1600
REFERENCE_HEIGHT = 900

# Panel layout (values are for reference resolution, will be scaled)
PANEL_GAP_REF = 120  # Gap between panels for battle icon and button
PANEL_WIDTH_RATIO = 0.35  # Each panel takes 35% of screen width
PANEL_HEIGHT_RATIO = 0.57  # Panel height as ratio of screen height (0.55 before the bonus list)
PANEL_TOP_MARGIN_REF = 105  # Top margin for panels

# Strength bar dimensions (fill and PNG can be sized independently)
BAR_FILL_WIDTH_RATIO = 0.20  # Fill width as ratio of screen width
BAR_PNG_WIDTH_RATIO = 0.27  # PNG width as ratio of screen width (adjust separately from fill)
BAR_FILL_HEIGHT_REF = 40  # Height for the colored fill area
BAR_PNG_HEIGHT_REF = 400  # Height for BattleBar.png overlay
BAR_TOP_MARGIN_REF = 30  # Gap below panels (for PNG positioning)
BAR_FILL_OFFSET_REF = -30  # Move fill up relative to PNG (negative = up)
BAR_BORDER_WIDTH = 2

# Battle icon pulsation settings
ICON_PULSE_MIN_SCALE = 1.0  # Minimum scale (normal size)
ICON_PULSE_MAX_SCALE = 1.08  # Maximum scale (8% larger)
ICON_PULSE_SPEED = 1.0  # Pulsations per second (slower, more dramatic)
ICON_PULSE_SCALE_STEPS = 64  # Pulse scale is quantised to 1/64 so it can be cached
ICON_PULSE_CACHE_MAX = 32  # Upper bound on cached pulsed-icon sizes

# Battle report panel (centred): BattlePlayerScreen.png sized to the report it holds
# (2026-10-28: the outcome lines made it longer), between these shares of the screen height
REPORT_PANEL_WIDTH_RATIO = 0.4
REPORT_PANEL_MIN_HEIGHT_RATIO = 0.55
REPORT_PANEL_MAX_HEIGHT_RATIO = 0.8
# The art's board as shares of the panel (the 1024x1536 art, stretched to the panel):
# inside the frame, and below / above the corner spears (top ~17%, bottom ~18% of it)
REPORT_INSET_X = 0.14
PREVIEW_INSET_X = 0.17  # The side panels' (owner, 2026-10-29: the bonus list sat too near the frame)
# The battle's banner sits just above the panels: its bottom this share of a panel's height
# below their top, still clear of the art's corner spears (their tips ~5.5% down)
BANNER_BOTTOM_SHARE = 0.04
TIP_WIDTH_REF = 380  # The tags' tooltips, px at 1600x900 (a line each)
REPORT_INSET_TOP = 0.11
REPORT_INSET_BOTTOM = 0.19
REPORT_PANEL_ART = "assets/BattlePlayerScreen.png"
REPORT_CLOSE_Y = 0.92  # Close is centred here, on the art's bottom rail (share of the panel)
# A report taller than the largest panel scrolls with the mouse wheel (owner, 2026-10-29):
# its header (VICTORY / DEFEAT) stays, the body scrolls (battle_screen_kit.ScrollView, as
# the preview's sides)
CLOSE_BUTTON_WIDTH_REF = 180  # Its height follows the art's aspect
# Resolve Battle (setup) and Skip (the fight) share one slot centred under the bars
# (owner, 2026-10-28: a click or Space skipped the fight but nothing said so; then the
# two unified). Its height follows the art's aspect.
ACTION_BUTTON_WIDTH_REF = 220
ACTION_BUTTON_GAP_REF = 34  # Below the bars' fill
SKIP_HINT_GAP_REF = 8  # The Skip button's "Space" keycap below it

# Animation timing
# Bounds the volley schedule is clamped into (the duration is derived from the
# volley count, not drawn directly)
ANIMATION_MIN_DURATION = 2.0  # Minimum animation duration (seconds)
ANIMATION_MAX_DURATION = 8.0  # Maximum (one shot at a time takes longer - owner, 2026-10-28: fine)

# Splash timing (seconds)
SPLASH_GROW_DURATION = 0.5
SPLASH_HOLD_DURATION = 2.0
SPLASH_SHRINK_DURATION = 0.5
SPLASH_TARGET_SCALE = 0.75  # 75% of original size

# Volley settings - each volley is one shot per side, and each hit removes a
# visible chunk of the target bar (BFME2 auto-resolve style). The sides take
# turns, one shot at a time: a shot is fired once the one before has landed.
VOLLEY_MIN = 3  # Fewest volleys, however small the skirmish
VOLLEY_MAX = 10  # Cap so huge stacks do not trade blows forever (fewer if they would not fit the duration)
VOLLEY_SIZE_LOG_COEFF = 1.6  # volleys = 2 + coeff * ln(total armies), then clamped
SHOT_PAUSE = 0.05  # Seconds after a bolt lands before the other side starts charging its reply
VOLLEY_LEAD_IN = 0.35  # Pause before the first shot
VOLLEY_TAIL = 0.60  # Pause after the last hit settles
CHUNK_JITTER_MIN = 0.5  # A hit's random weight, normalised so a side's hits sum exactly
CHUNK_JITTER_MAX = 1.6  # (wider than the first 0.6-1.4: more varied pieces - owner, 2026-10-28)
# A hit is as heavy as the army firing it is strong at that moment (its fill),
# so a strong army keeps hitting hard while a weakening one's hits shrink
# (owner, 2026-10-28: show the armies' strength). 0 turns it off.
HIT_STRENGTH_POWER = 1.0
HIT_STRENGTH_FLOOR = 0.15  # A nearly beaten army still hits at least this hard (share of a full bar's)

# Shots (battle_fx_style.py): each gathers light (charge_time()), then one bolt
# flies to the enemy bar; the chunk it destroys breaks off as it lands
PROJECTILE_TRAVEL = BOLT_STYLE['travel']  # Seconds a bolt takes to reach the enemy bar

# Hit reaction on the struck bar
# Seconds from a bolt's landing until its chunk is gone and the fill steps down
BURN_DURATION = BURN_STYLE['cool']
FRAME_GLOW_DURATION = 0.30  # Seconds the bar frame keeps flaring
FRAME_GLOW_INTENSITY = 0.35  # How hard the flare brightens the frame artwork (the impacts carry the hit)



# ========================================
# BATTLE INTERFACE STATE
# ========================================

class BattleInterfaceState(Enum):
    """State machine states for the battle interface."""
    SETUP = auto()      # Two panels, Resolve button
    ANIMATING = auto()  # Bars shooting particles
    SPLASH = auto()     # Victory/defeat image scaling
    REPORT = auto()     # Battle summary, Close button


# ========================================
# BATTLE SPLASH EFFECT
# ========================================

class BattleSplashEffect:
    """
    Victory/defeat image scaling animation.

    Timeline:
    - 0.0s - 0.5s:   Grow from dot to 75% (ease-out cubic)
    - 0.5s - 2.5s:   Hold at 75%
    - 2.5s - 3.0s:   Shrink to dot (ease-in cubic)
    """

    def __init__(self, image, screen_width, screen_height):
        """
        Initialize splash effect.

        Args:
            image: pygame.Surface of victory/defeat image
            screen_width: Width of screen for centering
            screen_height: Height of screen for centering
        """
        self.original_image = image
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.elapsed = 0.0
        self.is_complete = False

        # Pre-calculate total duration
        self.total_duration = SPLASH_GROW_DURATION + SPLASH_HOLD_DURATION + SPLASH_SHRINK_DURATION

        # Store original dimensions for scaling
        self.original_width = image.get_width()
        self.original_height = image.get_height()

    def update(self, delta_time):
        """
        Update animation progress.

        Args:
            delta_time: Time since last update in seconds
        """
        self.elapsed += delta_time

        if self.elapsed >= self.total_duration:
            self.is_complete = True

    def _get_current_scale(self):
        """
        Calculate current scale based on elapsed time.

        Returns:
            float: Scale factor (0.0 to SPLASH_TARGET_SCALE)
        """
        if self.elapsed < SPLASH_GROW_DURATION:
            # Growing phase (ease-out cubic)
            progress = self.elapsed / SPLASH_GROW_DURATION
            eased = 1 - math.pow(1 - progress, 3)
            return eased * SPLASH_TARGET_SCALE

        elif self.elapsed < SPLASH_GROW_DURATION + SPLASH_HOLD_DURATION:
            # Hold phase
            return SPLASH_TARGET_SCALE

        else:
            # Shrinking phase (ease-in cubic)
            shrink_elapsed = self.elapsed - SPLASH_GROW_DURATION - SPLASH_HOLD_DURATION
            progress = min(1.0, shrink_elapsed / SPLASH_SHRINK_DURATION)
            eased = math.pow(progress, 3)
            return SPLASH_TARGET_SCALE * (1 - eased)

    def render(self, screen):
        """
        Render the splash image at current scale.

        Args:
            screen: pygame.Surface to render to
        """
        scale = self._get_current_scale()

        # Don't render if scale is too small
        if scale < 0.01:
            return

        # Calculate scaled dimensions
        scaled_width = int(self.original_width * scale)
        scaled_height = int(self.original_height * scale)

        if scaled_width < 1 or scaled_height < 1:
            return

        # Scale the image
        scaled_image = pygame.transform.smoothscale(
            self.original_image,
            (scaled_width, scaled_height)
        )

        # Center on screen
        x = (self.screen_width - scaled_width) // 2
        y = (self.screen_height - scaled_height) // 2

        screen.blit(scaled_image, (x, y))

    def is_finished(self):
        """Check if animation is complete."""
        return self.is_complete


# ========================================
# BATTLE BAR VOLLEY EFFECT
# ========================================

class BattleBarVolleyEffect:
    """
    Volley-based strength bar combat animation (BFME2 auto-resolve style).

    Instead of both bars sliding continuously to their final value, the sides
    take turns, one shot at a time: light gathers from the shooter's remaining
    bar into its front (the charge), a bolt of light flies from there to the
    enemy bar, and the chunk it destroys breaks off glowing hot and falls out of
    the bar, embers bursting from it - the fill steps down one step per shot. A
    hit is as heavy as the army firing it is strong at the time.

    The two bars are mirrored: the attacker bar is anchored at its left edge and
    the defender bar at its right edge, so both erode inward toward the centre.

    The whole schedule (how many volleys, when each one fires, how big each
    chunk is) is built once in __init__ from a seeded private RNG, so the
    animation is identical on every client in multiplayer. The chunk sizes are
    normalised to sum exactly to the damage each side takes, so the bars always
    land precisely on their final fill. What a shot looks like (where exactly
    it lands, its sparks, charge motes and embers) is drawn from a separate RNG
    per shot when it is armed, so it never touches the schedule.

    When the last bolt has landed, the bar left standing gets a finale (a sweep
    of light, gold light round its frame) that plays on after is_finished(),
    until the interface moves on to the splash.
    """

    # Side indices into self.sides
    ATTACKER = 0
    DEFENDER = 1

    def __init__(self, attacker_bar_rect, defender_bar_rect,
                 attacker_color, defender_color,
                 attacker_initial_fill, defender_initial_fill,
                 attacker_final_fill, defender_final_fill,
                 seed=None, bar_border_img=None, bar_png_width=None,
                 bar_fill_offset=None, bar_png_height=None, ui_scale=1.0,
                 attacker_count=0, defender_count=0, light=None, ambient_clock=0.0):
        """
        Initialize the volley combat effect.

        Args:
            attacker_bar_rect: pygame.Rect for attacker strength bar (fill area)
            defender_bar_rect: pygame.Rect for defender strength bar (fill area)
            attacker_color: RGB tuple for attacker blasts
            defender_color: RGB tuple for defender blasts
            attacker_initial_fill: Initial fill ratio (0.0-1.0) for attacker bar
            defender_initial_fill: Initial fill ratio (0.0-1.0) for defender bar
            attacker_final_fill: Final fill ratio after animation
            defender_final_fill: Final fill ratio after animation
            seed: Random seed for deterministic animation (for multiplayer sync)
            bar_border_img: Optional pygame.Surface for bar border (BattleBar.png)
            bar_png_width: Optional width for PNG (if different from fill width)
            bar_fill_offset: Scaled offset for fill positioning
            bar_png_height: Scaled height for PNG overlay
            ui_scale: Scale factor (light sizes follow the bar height instead)
            attacker_count: Attacker army count (drives how many volleys are fired)
            defender_count: Defender army count (drives how many volleys are fired)
            light: The interface's BattleLight (its sprites prepared during setup);
                a new one is made if None
            ambient_clock: The interface's clock at the start, so the bars'
                shimmer and sheen carry on from the setup screen without a jump

        Note:
            There is no `duration` argument - the duration falls out of the
            volley schedule and is exposed as `self.duration` for the caller.
        """
        self.attacker_rect = attacker_bar_rect
        self.defender_rect = defender_bar_rect
        self.bar_border_img = bar_border_img
        self.ui_scale = ui_scale
        self.attacker_count = attacker_count
        self.defender_count = defender_count
        self.seed = seed

        # PNG dimensions - use passed values or defaults
        self.bar_png_width = bar_png_width if bar_png_width else attacker_bar_rect.width
        self.bar_fill_offset = bar_fill_offset if bar_fill_offset is not None else BAR_FILL_OFFSET_REF
        self.bar_png_height = bar_png_height if bar_png_height else BAR_PNG_HEIGHT_REF

        # Fill area shares one Y for both bars (matches _render_strength_bars)
        self.fill_y = self.attacker_rect.top + self.bar_fill_offset

        # Pre-scale bar border once. The defender bar is mirrored, so its frame
        # is flipped too - BattleBar.png is not horizontally symmetric, and an
        # unflipped copy would break the mirror.
        self._scaled_bar_border = None
        self._scaled_bar_border_flipped = None
        if self.bar_border_img:
            self._scaled_bar_border = pygame.transform.smoothscale(
                self.bar_border_img, (self.bar_png_width, self.bar_png_height))
            self._scaled_bar_border_flipped = pygame.transform.flip(
                self._scaled_bar_border, True, False)

        # Per-side state. 'anchor_right' mirrors the defender bar so both bars
        # erode inward toward the centre "VS".
        self.sides = [
            {
                'rect': attacker_bar_rect,
                'color': attacker_color,
                'anchor_right': False,
                'border': self._scaled_bar_border,
                'initial': attacker_initial_fill,
                'final': attacker_final_fill,
                'current': attacker_initial_fill,
                'chunks': [],
                'burn': None,            # {'t0', 'chunk', 'fx'} - chunk being destroyed
                'glow_t0': None,         # frame flare start time
                'glow': None,            # frame flare overlay for hits taken
            },
            {
                'rect': defender_bar_rect,
                'color': defender_color,
                'anchor_right': True,
                'border': self._scaled_bar_border_flipped,
                'initial': defender_initial_fill,
                'final': defender_final_fill,
                'current': defender_initial_fill,
                'chunks': [],
                'burn': None,
                'glow_t0': None,
                'glow': None,
            },
        ]

        # The frame flare a side shows when hit carries its opponent's colour
        png_offset_y = (self.attacker_rect.height - self.bar_png_height) // 2
        for i, side in enumerate(self.sides):
            other = self.sides[1 - i]
            side['glow'] = self._build_frame_glow_sprite(side['border'], other['color'])
            side['png_pos'] = (side['rect'].centerx - self.bar_png_width // 2, side['rect'].top + png_offset_y)
            # Where this side's bolts leave from: the point of its frame's inner end cap
            side['tip'] = spear_tip(side['border'], side['png_pos'], side['rect'], self.fill_y,
                                    side['anchor_right'])

        # The light (bolts, impacts, the bars' look). The interface hands over the
        # one whose sprites it prepared during setup.
        self.light = light if light is not None else BattleLight(attacker_bar_rect.height)
        if light is None:
            self.light.prepare_battle(attacker_color, defender_color)
        self.ambient_clock = ambient_clock
        # A side's turn: the pause after the bolt that hit it, its charge, its own
        # bolt's flight
        self.charge = charge_time()
        self.turn = SHOT_PAUSE + self.charge + PROJECTILE_TRAVEL

        self.elapsed = 0.0
        self.is_complete = False
        self.skipped = False
        self.volleys = []
        self.duration = ANIMATION_MIN_DURATION
        # The finale: when it starts (the last bolt's landing) and its emptied bar's embers
        self.finale_t0 = None
        self.finale_embers = []

        self._build_schedule(attacker_final_fill, defender_final_fill)

    # ------------------------------------------------------------------
    # Schedule construction
    # ------------------------------------------------------------------

    def _build_schedule(self, attacker_final_fill, defender_final_fill):
        """
        Build the deterministic volley schedule.

        The sides take turns, one shot at a time (owner, 2026-10-28: easier to
        follow than both firing at once): a side starts charging its shot
        SHOT_PAUSE after the bolt before has landed. The side that loses opens and the winner has the
        last word, so an emptied bar never fires again. The fire times do not
        depend on who wins, only who fires each one - so retarget() can flip the
        winner without moving a single shot.

        Uses a private random.Random so it never disturbs the global RNG that
        game logic draws from. Re-running it with the same seed reproduces the
        identical chunks, which is what retarget() relies on.

        Args:
            attacker_final_fill: Fill ratio the attacker bar must end on
            defender_final_fill: Fill ratio the defender bar must end on
        """
        rng = random.Random(self.seed)

        self.sides[self.ATTACKER]['final'] = attacker_final_fill
        self.sides[self.DEFENDER]['final'] = defender_final_fill

        # Volley count scales with the size of the battle: a skirmish resolves
        # in a few punches, a huge stack trades blows for longer. Log curve so
        # very large battles do not run away.
        total_armies = max(2, self.attacker_count + self.defender_count)
        count = int(round(2 + VOLLEY_SIZE_LOG_COEFF * math.log(total_armies)))
        # As many as fit the duration: 2 * count turns (the first without its pause)
        fixed = VOLLEY_LEAD_IN - SHOT_PAUSE + VOLLEY_TAIL
        fits = int((ANIMATION_MAX_DURATION - fixed) / (2 * self.turn))
        count = max(VOLLEY_MIN, min(VOLLEY_MAX, fits, count))
        last_land = VOLLEY_LEAD_IN - SHOT_PAUSE + 2 * count * self.turn
        self.duration = max(ANIMATION_MIN_DURATION, last_land + VOLLEY_TAIL)

        # Turns alternate, the loser first, the winner last (no winner yet -
        # both bars emptied by the estimate: the attacker opens)
        winner, _ = self.finale_sides()
        first = (1 - winner) if winner is not None else self.ATTACKER

        # Split each side's damage into the hits it takes, summing exactly to
        # the damage. Each hit weighs its random draw times the strength of the
        # army firing it when it fires. The draws come first, in a fixed order,
        # whatever the damage: retarget() depends on it.
        jitters = {self.ATTACKER: self._draw_weights(rng, count),
                   self.DEFENDER: self._draw_weights(rng, count)}
        damage = {side: self.sides[side]['initial'] - self.sides[side]['final'] for side in jitters}
        chunks_taken = {side: self._spread(damage[side], jitters[side]) for side in jitters}
        # The strengths follow the chunks and the chunks the strengths: two
        # rounds settle it (the second sees the first's trajectories)
        for _ in range(2):
            strengths = self._shooter_strengths(first, count, chunks_taken)
            chunks_taken = {side: self._spread(damage[side], [j * s for j, s in zip(jitters[side], strengths[side])])
                            for side in jitters}
        self.sides[self.ATTACKER]['chunks'] = chunks_taken[self.ATTACKER]
        self.sides[self.DEFENDER]['chunks'] = chunks_taken[self.DEFENDER]

        # Build the shot list. A shot fired by the attacker damages the defender,
        # and vice versa.
        self.volleys = []
        for turn in range(2 * count):
            shooter = first if turn % 2 == 0 else 1 - first
            target = 1 - shooter
            fire_t = VOLLEY_LEAD_IN + self.charge + turn * self.turn
            self.volleys.append(self._make_shot(shooter, target, fire_t,
                                                chunks_taken[target][turn // 2], self.charge))

    @staticmethod
    def _make_shot(shooter, target, fire_t, chunk, charge):
        """
        Build one shot record.

        Args:
            shooter: Side index firing the shot
            target: Side index taking the hit
            fire_t: Time (seconds into the animation) the bolt leaves
            chunk: Fill ratio this shot removes from the target
            charge: Seconds the shot gathers light before the bolt leaves

        Returns:
            Shot dict ('arm_t' is when its charge begins, 'land_t' when the bolt
            lands and the chunk breaks off)
        """
        return {
            'shooter': shooter,
            'target': target,
            'arm_t': fire_t - charge,
            'fire_t': fire_t,
            'land_t': fire_t + PROJECTILE_TRAVEL,
            'chunk': chunk,
            'fired': False,
            'landed': False,
            'aim': None,      # the target's fill it was aimed at (_aim_fill), set when armed
            'end_x': 0.0,     # ...and that fill's front x
            'fx': None,       # its look (battle_fx_effect.Shot), built when armed
        }

    @staticmethod
    def _draw_weights(rng, count):
        """
        `count` random hit weights. Drawn unconditionally, so the RNG stream
        advances by the same number of steps whatever the damage - retarget()
        depends on it.
        """
        return [rng.uniform(CHUNK_JITTER_MIN, CHUNK_JITTER_MAX) for _ in range(count)]

    @staticmethod
    def _spread(damage, weights):
        """
        Split a total damage amount into chunks in proportion to `weights`.

        The chunks are normalised so they sum to exactly `damage`, which is what
        lets the bar land precisely on its final fill instead of drifting.

        Args:
            damage: Total fill ratio to remove (may be 0 or negative)
            weights: One positive weight per chunk

        Returns:
            List of chunk sizes
        """
        if not weights:
            return []
        if damage <= 0:
            return [0.0] * len(weights)
        total = sum(weights)
        chunks = [damage * w / total for w in weights]
        # Fold any float residue into the last chunk
        chunks[-1] += damage - sum(chunks)
        return chunks

    @classmethod
    def _split_damage(cls, rng, damage, count):
        """Split a total damage amount into `count` randomly weighted chunks (no strengths)."""
        return cls._spread(damage, cls._draw_weights(rng, count))

    def _shooter_strengths(self, first, count, chunks_taken):
        """
        For each side, the strength of the army behind each hit it takes: its
        fill when it fires (played through in turn order with these chunks),
        to HIT_STRENGTH_POWER, at least HIT_STRENGTH_FLOOR.

        Returns:
            {side: [strength of the shooter of each hit it takes, in order]}
        """
        fills = {side: self.sides[side]['initial'] for side in (self.ATTACKER, self.DEFENDER)}
        strengths = {self.ATTACKER: [], self.DEFENDER: []}
        for turn in range(2 * count):
            shooter = first if turn % 2 == 0 else 1 - first
            target = 1 - shooter
            strengths[target].append(max(HIT_STRENGTH_FLOOR, fills[shooter]) ** HIT_STRENGTH_POWER)
            fills[target] -= chunks_taken[target][turn // 2]
        return strengths

    def retarget(self, attacker_final_fill, defender_final_fill):
        """
        Re-aim the bars at a new final fill without disturbing the rhythm.

        Called once the real battle result is known (a moment after the
        animation starts). Because the schedule is rebuilt from a freshly
        seeded RNG that is consumed in the same order, the volley count and all
        fire times come out identical - only the chunk sizes change.

        Args:
            attacker_final_fill: Real final fill ratio for the attacker bar
            defender_final_fill: Real final fill ratio for the defender bar
        """
        self._build_schedule(attacker_final_fill, defender_final_fill)

    # ------------------------------------------------------------------
    # Frame flare sprite
    # ------------------------------------------------------------------

    @staticmethod
    def _lerp_color(a, b, t):
        """
        Blend between two RGB colours.

        utils.colors.lighten_color is multiplicative, so it barely moves a dark
        player colour toward white. The frame flare needs a true linear blend.

        Args:
            a: RGB tuple at t=0
            b: RGB tuple at t=1
            t: Blend factor 0.0-1.0

        Returns:
            Blended RGB tuple
        """
        t = max(0.0, min(1.0, t))
        return (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )

    def _build_frame_glow_sprite(self, border, color):
        """
        Pre-render the flare that runs over a bar frame when it is hit.

        A single brightened copy of the frame artwork, laid over the normal
        frame and faded out with set_alpha at blit time. Earlier attempts drew a
        rectangular halo around the bar, which read as a grey box over an ornate
        frame - lighting up the actual artwork is closer to the reference.

        BLEND_RGB_ADD brightens the colour channels but leaves alpha alone, so
        the frame's transparent regions stay transparent. That matters here:
        BattleBar.png stores non-zero RGB under its fully transparent pixels, so
        a plain additive blit would light up the whole rectangle.

        Args:
            border: The pre-scaled frame surface for this side, or None
            color: RGB tuple of the player whose blast lands here

        Returns:
            pygame.Surface to blit over the frame, or None if there is no frame
        """
        if border is None:
            return None

        # Held well below full strength: added on top of the gold artwork, a
        # brighter tint just saturates the whole frame to flat white and the
        # detail disappears.
        hot = self._lerp_color(color, WHITE, 0.2)
        hot = tuple(int(c * FRAME_GLOW_INTENSITY) for c in hot)

        surf = border.copy()
        surf.fill((*hot, 0), special_flags=pygame.BLEND_RGB_ADD)
        return surf

    # ------------------------------------------------------------------
    # Geometry helpers (mirror-aware)
    # ------------------------------------------------------------------

    def _fill_rect(self, side, fill):
        """
        Rect covering a side's filled portion.

        Args:
            side: Side dict
            fill: Fill ratio 0.0-1.0

        Returns:
            pygame.Rect anchored at the bar's outer edge
        """
        rect = side['rect']
        width = int(rect.width * max(0.0, min(1.0, fill)))
        if side['anchor_right']:
            return pygame.Rect(rect.right - width, self.fill_y, width, rect.height)
        return pygame.Rect(rect.left, self.fill_y, width, rect.height)

    def _fill_tip_x(self, side, fill):
        """
        X coordinate of the inner (centre-facing) end of a side's fill.

        This is where incoming bolts land and where chunks break off.

        Args:
            side: Side dict
            fill: Fill ratio 0.0-1.0

        Returns:
            float x coordinate
        """
        return tip_x(side['rect'], side['anchor_right'], fill)

    def _chunk_rect(self, side, from_fill, to_fill):
        """
        Rect covering the slice of bar between two fill ratios.

        Args:
            side: Side dict
            from_fill: Lower fill ratio (inner edge of the slice)
            to_fill: Higher fill ratio (outer edge of the slice)

        Returns:
            pygame.Rect, possibly zero-width
        """
        x1 = self._fill_tip_x(side, from_fill)
        x2 = self._fill_tip_x(side, to_fill)
        left, right = (x2, x1) if side['anchor_right'] else (x1, x2)
        return pygame.Rect(int(left), self.fill_y,
                           max(0, int(right) - int(left)), side['rect'].height)

    # ------------------------------------------------------------------
    # Shots
    # ------------------------------------------------------------------

    def _aim_fill(self, target_index):
        """
        The fill a shot armed now should hit: the target's front once the chunk
        still burning and the chunks of shots already on their way to it are
        gone - the front the bar shows, since a chunk breaks off as it is hit.
        (Also where a side's own bolt leaves from.)

        Args:
            target_index: Side index of the target

        Returns:
            Fill ratio
        """
        target = self.sides[target_index]
        fill = target['current']
        if target['burn'] is not None:
            fill -= target['burn']['chunk']
        for shot in self.volleys:
            if shot['target'] == target_index and shot['fired'] and not shot['landed']:
                fill -= shot['chunk']
        return max(0.0, fill)

    def _plan_shot(self, index, shot, aim):
        """
        Build the look of a shot as it is armed (battle_fx_effect.Shot).

        With the charge on, light gathers from the shooter's remaining bar and
        the bolt leaves from its front; off, from the frame's spear tip. It
        flies level along the bars' centre line and lands near the chunk's
        front. The RNG is the shot's own (seeded from the effect's seed and the
        shot's place in the schedule), never the schedule's or the global one.

        Args:
            index: The shot's place in self.volleys
            shot: Shot dict
            aim: Fill ratio aimed at (_aim_fill)

        Returns:
            Shot
        """
        rng = random.Random(stable_seed('battle shot', self.seed, index))
        shooter = self.sides[shot['shooter']]
        target = self.sides[shot['target']]
        chunk = min(shot['chunk'], aim)
        h = target['rect'].height
        centre_y = self.fill_y + h / 2.0
        share = max(0.0, min(1.0, BOLT_STYLE['land_at'] + rng.uniform(-1.0, 1.0) * BOLT_STYLE['land_spread']))
        landing = (self._fill_tip_x(target, aim - chunk * share), centre_y)
        span = (self._fill_tip_x(target, aim), self._fill_tip_x(target, aim - chunk))
        inward = -1 if target['anchor_right'] else 1
        colours = (self.light.colours(shooter['color']), self.light.colours(target['color']))
        # The chunk it breaks off, on the bar painter's pixels (BattleLight.draw_bar),
        # so the piece leaves exactly the hole
        edges = (self._fill_edge(target, aim), self._fill_edge(target, aim - chunk))
        piece = (min(edges), abs(edges[1] - edges[0]))
        bar = pygame.Rect(target['rect'].left, self.fill_y, target['rect'].width, h)
        if self.charge > 0.0:
            front = self._fill_tip_x(shooter, self._aim_fill(shot['shooter']))
            muzzle = (front, centre_y)
            gather = (front, self._fill_tip_x(shooter, 0.0))
        else:
            muzzle, gather = shooter['tip'], None
        return Shot(rng, shot['arm_t'], shot['fire_t'], muzzle, landing, span, piece, inward, bar, colours,
                    gather)

    def _fill_edge(self, side, fill):
        """The pixel column where a side's fill ends, as BattleLight.draw_bar() paints it."""
        rect = side['rect']
        width = int(rect.width * max(0.0, min(1.0, fill)))
        return rect.right - width if side['anchor_right'] else rect.left + width

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _settle_burn(self, side):
        """
        Close a side's active burn, removing the chunk from its fill.

        Args:
            side: Side dict
        """
        burn = side['burn']
        if burn is None:
            return
        side['current'] = max(0.0, side['current'] - burn['chunk'])
        side['burn'] = None

    def update(self, delta_time):
        """
        Advance the volley schedule.

        Once complete, only the clock moves on (for the finale's light); the
        bars stay on their final fill.

        Args:
            delta_time: Time since last update in seconds
        """
        self.elapsed += delta_time
        if self.is_complete:
            return

        # Fire and land shots that have come due
        for index, shot in enumerate(self.volleys):
            if not shot['fired'] and self.elapsed >= shot['arm_t']:
                # Aim before marking it fired: it must not count itself in flight.
                # The point is held for the flight, so the bolts do not chase the bar.
                aim = self._aim_fill(shot['target'])
                shot['fired'] = True
                shot['aim'] = aim
                shot['end_x'] = self._fill_tip_x(self.sides[shot['target']], aim)
                shot['fx'] = self._plan_shot(index, shot, aim)

            if shot['fired'] and not shot['landed'] and self.elapsed >= shot['land_t']:
                shot['landed'] = True
                target = self.sides[shot['target']]
                # A second hit arriving mid-burn settles the first one, so no
                # chunk is ever silently dropped.
                self._settle_burn(target)
                target['burn'] = {'t0': shot['land_t'], 'chunk': shot['chunk'], 'fx': shot['fx']}
                target['glow_t0'] = shot['land_t']

        # Close burns whose window has elapsed, and expire frame flares
        for side in self.sides:
            burn = side['burn']
            if burn is not None and self.elapsed - burn['t0'] >= BURN_DURATION:
                self._settle_burn(side)
            if side['glow_t0'] is not None and self.elapsed - side['glow_t0'] >= FRAME_GLOW_DURATION:
                side['glow_t0'] = None

        # The finale starts as the last bolt lands
        if self.finale_t0 is None and all(shot['fired'] for shot in self.volleys):
            last = max([shot['fx'].land_t for shot in self.volleys] or [self.elapsed])
            if self.elapsed >= last:
                self._start_finale(last)

        if self.elapsed >= self.duration:
            self._finish()

    def finale_sides(self):
        """
        (side left standing, side emptied) for the finale; either may be None.

        The winner is the side ending with the longer fill, if any is left -
        set_actual_battle_result() empties the loser's bar, so with the real
        result exactly one bar is left. Both empty (a drawn estimate): no finale.
        """
        attacker, defender = self.sides[self.ATTACKER]['final'], self.sides[self.DEFENDER]['final']
        if attacker > defender and attacker > 0:
            winner = self.ATTACKER
        elif defender > attacker and defender > 0:
            winner = self.DEFENDER
        else:
            return None, None
        loser = 1 - winner
        emptied = self.sides[loser]['final'] <= 0 < self.sides[loser]['initial']
        return winner, (loser if emptied else None)

    def _start_finale(self, t0):
        """Start the finale at t0 (the last bolt's landing): the emptied bar's last embers."""
        self.finale_t0 = t0
        winner, loser = self.finale_sides()
        if loser is not None:
            side = self.sides[loser]
            rng = random.Random(stable_seed('battle finale', self.seed))
            self.finale_embers = self.light.finale_embers(
                rng, t0, self._fill_tip_x(side, 0.0), self.fill_y + side['rect'].height / 2.0,
                -1 if side['anchor_right'] else 1)

    def _finish(self):
        """Settle everything and snap both bars exactly onto their final fill."""
        for side in self.sides:
            self._settle_burn(side)
            side['current'] = side['final']
            side['glow_t0'] = None
        self.is_complete = True

    def skip(self):
        """
        Jump straight to the end of the animation.

        Used by the click/Space skip so a player can cut a long battle short.
        Nothing more is drawn in flight, and there is no finale: the interface
        goes straight on to the splash.
        """
        self.elapsed = self.duration
        self.skipped = True
        for shot in self.volleys:
            shot['fired'] = True
            shot['landed'] = True
        self._finish()

    def shot_kick(self):
        """
        0-1: how recently a bolt left (1 the moment it leaves, fading) - the
        battle icon's glow flares with each one.
        """
        if self.skipped:
            return 0.0
        decay = ICON_GLOW_STYLE['shot_decay']
        kick = 0.0
        for shot in self.volleys:
            age = self.elapsed - shot['fire_t']
            if shot['fx'] is not None and 0.0 <= age < decay * 6.0:
                kick = max(kick, math.exp(-age / decay))
        return kick

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, screen):
        """
        Render both bars, the shots and the finale.

        Order: under the frames the bars themselves (track, fill, the seam of
        light at each front) and the pieces broken off them, falling; then the
        frames and their flares; then one layer of light over everything -
        charges, bolts, impacts, embers and the finale's gold frame light. Nothing is built here: the
        light's sprites were prepared during setup (any still missing are built
        within the frame budget, skipping a frame).

        Args:
            screen: pygame.Surface to render to
        """
        light = self.light
        light.begin_frame()
        t = self.elapsed
        clock = self.ambient_clock + t
        finale = None if self.finale_t0 is None or self.skipped else t - self.finale_t0
        winner, loser = self.finale_sides() if finale is not None else (None, None)
        seam_style = BAR_STYLE['seam']
        decay = seam_style['decay']
        # Shots with something on screen (none once skipped)
        active = [] if self.skipped else [shot for shot in self.volleys
                                          if shot['fx'] is not None and shot['arm_t'] <= t < shot['fx'].end]

        # 1. The bars, under their frames
        for i, side in enumerate(self.sides):
            # The seam flares as a bolt lands on this bar, builds as it charges
            # and kicks as its bolt leaves; a band of light sweeps it to its
            # front while it charges
            kick = 0.0
            charging = None
            for shot in active:
                if shot['target'] == i:
                    kick += seam_style['hit_kick'] * shot['fx'].hit_kick(t, decay)
                else:
                    kick += seam_style['fire_kick'] * shot['fx'].fire_kick(t, decay)
                    if shot['fx'].charge(t) is not None:
                        charging = shot['fx'].charge(t)
            eaten = 0.0
            burn = side['burn']
            if burn is not None and burn['fx'] is not None:
                eaten = burn['chunk'] * burn['fx'].broken(t)
            standing = side['current'] - eaten
            if charging is not None:
                kick += CHARGE_STYLE['seam'] * charging * charging
            seam = light.seam_level(clock, 1.7 * i, kick)
            # The seam fades out as a bar empties...
            seam *= min(1.0, max(0.0, standing) / seam_style['empty_fade'])
            sheen = light.idle_sheen(clock, i * BAR_STYLE['sheen']['period'] / 2.0)
            if charging is not None:
                sheen = (charging, CHARGE_STYLE['sweep'] * min(1.0, 2.0 * charging))
            if finale is not None:
                if i == winner:
                    # ...the bar left standing is swept with light, its seam held bright
                    seam = max(seam, FINALE_STYLE['seam'] * min(1.0, finale / 0.08))
                    p = finale / FINALE_STYLE['sweep']
                    if p < 1.0:
                        sheen = (p, FINALE_STYLE['sweep_intensity'] * math.sin(math.pi * p) ** 0.5)
                elif i == loser:
                    # ...and an emptied bar's last light goes out
                    out = 1.0 - finale / FINALE_STYLE['out']
                    seam = light.seam_level(clock, 1.7 * i) * max(0.0, out) if out > 0.0 else None
            light.draw_bar(screen, side['rect'], self.fill_y, side['anchor_right'], side['color'],
                           side['current'], eaten, seam, sheen)

        # 2. The chunks the bolts broke off, falling out of the bars (under the
        #    frames: they leave the bar as it showed them, and fall out below)
        for shot in active:
            light.draw_pieces(screen, shot['fx'], t)

        # 3. Decorative frame (defender's copy is mirrored)
        for side in self.sides:
            if side['border']:
                screen.blit(side['border'], side['png_pos'])
            else:
                pygame.draw.rect(screen, WHITE, side['rect'], BAR_BORDER_WIDTH)

        # 4. Frame flare on a bar that was just hit - a hot copy of the frame
        #    laid over the normal one at the exact same position.
        for side in self.sides:
            if side['glow_t0'] is None or side['glow'] is None:
                continue
            p = max(0.0, min(1.0, (t - side['glow_t0']) / FRAME_GLOW_DURATION))
            fade = (1.0 - p) ** 1.5
            sprite = side['glow']
            # pygame multiplies surface alpha with per-pixel alpha, so one hot
            # copy covers every fade level. Pre-rendering a frame per step cost
            # ~21 ms up front, a visible hitch when the battle starts. The alpha
            # is set unconditionally on every blit, so the sprite never carries
            # a stale value.
            sprite.set_alpha(int(255 * fade))
            screen.blit(sprite, side['png_pos'])

        # 5. Light over everything: the shots, an emptied bar's last embers, and
        #    the gold light round the frame of the bar left standing
        for shot in active:
            light.draw_shot(screen, shot['fx'], t)
        if finale is not None:
            if loser is not None:
                light.draw_embers(screen, self.finale_embers, t, light.colours(self.sides[loser]['color'])['ember'])
            if winner is not None:
                side = self.sides[winner]
                style = FINALE_STYLE
                strength = style['frame_intensity'] * min(1.0, finale / style['frame_fade_in'])
                strength *= 1.0 + style['frame_breathe'] * math.sin(2.0 * math.pi * style['frame_breathe_hz'] * finale)
                light.draw_frame_glow(screen, side['border'], side['anchor_right'], side['png_pos'], strength)

    def is_finished(self):
        """Check if animation is complete."""
        return self.is_complete


# ========================================
# ENHANCED BATTLE INTERFACE
# ========================================

def prewarm_battle_screen(screen_size, icon_sources=None):
    """
    Build what the battle report needs before the first battle (the loading screen, a
    resolution change): its icons at this screen's size - from the surfaces the game has
    already decoded (`icon_sources`, {path: surface}) - and the report panel's art at its
    smallest size, the size of most reports. Without it the first report of a session
    decoded ~10 images of 1024 px as its splash began (~130 ms).
    """
    width, height = screen_size
    scale = (width / REFERENCE_WIDTH + height / REFERENCE_HEIGHT) / 2
    battle_screen_panels.prewarm(scale, icon_sources)
    battle_screen_kit.art(REPORT_PANEL_ART, (int(width * REPORT_PANEL_WIDTH_RATIO),
                                             int(height * REPORT_PANEL_MIN_HEIGHT_RATIO)))


class EnhancedBattleInterface:
    """
    Main battle interface controller.

    Manages:
    - State machine transitions
    - Panel rendering with BattlePlayerScreen.png
    - Button handling (Resolve, Close)
    - Pre-calculation of battle result before animation
    - Integration with game loop
    """

    def __init__(self, screen, game_state, battle_index, font_manager,
                 current_player_index, on_complete_callback=None,
                 report_snapshot=None):
        """
        Initialize the enhanced battle interface.

        Args:
            screen: pygame.Surface to render to
            game_state: GameState object with battle data
            battle_index: Index of battle in pending_battles
            font_manager: FontManager for text rendering
            current_player_index: Index of the player viewing the battle
            on_complete_callback: Function to call when interface closes
            report_snapshot: Battle Report dict. When given, the interface opens
                directly in the REPORT state from that snapshot and never reads
                pending_battles -- the Battle object is popped the instant it
                resolves, so for a report there is nothing left to read. No
                animation is played.
        """
        self.screen = screen
        self.game_state = game_state
        self.battle_index = battle_index
        self.font_manager = font_manager
        self.current_player = current_player_index
        self.on_complete = on_complete_callback

        # Get screen dimensions
        self.screen_width = screen.get_width()
        self.screen_height = screen.get_height()

        # Initialize state
        self.state = BattleInterfaceState.SETUP
        self.elapsed = 0.0
        # Never reset (self.elapsed restarts with each state): drives the icon's
        # pulse and the bars' shimmer, so neither jumps when Resolve is clicked
        self._ambient_clock = 0.0
        self.is_finished_flag = False

        # Pre-calculated battle result (populated when Resolve is clicked)
        self.battle_result = None
        # What the battle did (GameState.battle_outcome(), or a stored report's keys) and
        # the report composed from it - once, before the report shows (_prepare_report)
        self.outcome = {}
        self.report_snapshot = None
        self._report_parts = None        # (header, body) surfaces
        self._report_header_pos = (0, 0)
        self._report_scroller = None     # The body (battle_screen_kit.ScrollView)
        self.animation_duration = 0.0
        self.animation_seed = None

        # Sub-effects
        self.particle_effect = None
        self.splash_effect = None

        # UI state
        self.mouse_pos = (0, 0)
        self._flash = (None, 0)  # (button id, ticks) of the last click, see clicked_element

        # Load assets
        self._load_assets()

        # Calculate layout
        self._calculate_layout()
        # Both of the above are battle-data free, and _calculate_layout() is the only
        # producer of report_panel_rect / close_button_rect / _scaled_report_bg and the
        # text metrics _render_report() needs, so report-only mode still runs them.

        # The light (battle_fx_effect.py): the backdrop in every state, and for a
        # battle the bars, the shots and the icon's glow
        self.light = BattleLight(self.bar_fill_height)
        self.light.prepare_backdrop(self.screen)

        if report_snapshot is not None:
            self._apply_report_snapshot(report_snapshot)
        else:
            # Extract battle data for display
            self._extract_battle_data()
            self._prepare_light()
            self._prepare_preview()

    def _prepare_light(self):
        """
        Bake the light the battle will show before its first frame: the gold
        light round the battle icon (it glows from the start) and round the bar
        frames (the finale), the flare greys, and queue the shots' sprites for
        both colours, built while the setup screen shows (prewarm_step). Every
        bake is kept between battles, so this is only paid once a session.
        """
        self.light.prepare_battle(self.attacker_color, self.defender_color)
        self.light.prepare_icon(self.battle_icon)
        self.light.prepare_frame(self._scaled_bar_border, False)
        self.light.prepare_frame(self._scaled_bar_border_flipped, True)

    def _apply_report_snapshot(self, report):
        """
        Open straight into the REPORT state from a stored Battle Report.

        Sets every field _render_report() touches. current_player_won in particular is
        otherwise first assigned in _pre_calculate_battle_result(), which a report never
        reaches -- leaving it unset would be an AttributeError on the first frame.

        current_player is the defender and attacker_player the attacker, so the totals
        line reads defender_lost / defender_survivors: the attacker saw this battle as a
        victory, the defender must see the same fight as a defeat.
        """
        self.report_snapshot = report
        self.territory = report.get('territory', '')
        self.current_player = report.get('defender', self.current_player)
        self.attacker_player = report.get('attacker')
        self.defender_players = [report.get('defender')]
        self.current_player_won = bool(report.get('held'))
        self.winner = report.get('defender') if report.get('held') else report.get('attacker')
        self.battle_result = {
            'winner': self.winner,
            'unit_breakdown': report.get('unit_breakdown', {}),
            'attacker_lost': report.get('attacker_lost', 0),
            'attacker_survivors': report.get('attacker_survivors', 0),
            'defender_lost': report.get('defender_lost', 0),
            'defender_survivors': report.get('defender_survivors', 0),
        }
        # The outcome lines, in GameState.battle_outcome()'s keys (a report from before
        # keep / xp_per_unit / level_ups existed shows without them)
        defender, attacker = report.get('defender'), report.get('attacker')
        self.outcome = {
            'previous_owner': defender,
            'holder': defender if report.get('held') else attacker,
            'held': bool(report.get('held')),
            'keep': report.get('keep'),
            'keep_name': report.get('keep_name'),
            'structures_destroyed': report.get('structures_destroyed', 0),
            'structures_captured': report.get('structures_captured', 0),
            'heroes_slain': [[defender, name] for name in report.get('heroes_slain') or []],
            'xp_per_unit': report.get('xp_per_unit', 0),
            'level_ups': report.get('level_ups') or [],
            # None (a report from before 2026-10-29): the counts above instead
            'buildings_destroyed': report.get('buildings_destroyed'),
            'buildings_captured': report.get('buildings_captured'),
        }
        # Composed (and the panel sized) before the first click can test Close's rect
        self._prepare_report()
        # Straight to REPORT: no SETUP/ANIMATING/SPLASH, so update() is a no-op and the
        # None sub-effects are never touched.
        self.state = BattleInterfaceState.REPORT
        self.elapsed = 0.0

    def _load_assets(self):
        """Load all required image assets."""
        # Calculate preliminary scale for asset loading
        scale_x = self.screen_width / REFERENCE_WIDTH
        scale_y = self.screen_height / REFERENCE_HEIGHT
        asset_scale = (scale_x + scale_y) / 2

        # Panel background - decoded once per process and shared with the report panel
        # (it was decoded again for every battle: ~40 ms of opening the window)
        self.panel_bg = battle_screen_kit.image(REPORT_PANEL_ART)
        if self.panel_bg is None:
            logger.warning(f"Could not load {REPORT_PANEL_ART}")

        try:
            # Battle icon for center gap
            battle_icon_full = pygame.image.load("assets/mapicons/BattleIcon1.png").convert_alpha()
            # Scale to 25.5% of original, then apply resolution scale
            icon_w, icon_h = battle_icon_full.get_size()
            icon_scale = 0.255 * asset_scale
            self.battle_icon = pygame.transform.smoothscale(
                battle_icon_full,
                (int(icon_w * icon_scale), int(icon_h * icon_scale))
            )
            # Store base dimensions for pulsation animation
            self.battle_icon_base_w = self.battle_icon.get_width()
            self.battle_icon_base_h = self.battle_icon.get_height()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattleIcon1.png: {e}")
            self.battle_icon = None
            self.battle_icon_base_w = 0
            self.battle_icon_base_h = 0

        try:
            # Victory/defeat splash images
            self.victory_img = pygame.image.load("assets/victoryscrn.png").convert_alpha()
            self.defeat_img = pygame.image.load("assets/defeatscrn.png").convert_alpha()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load victory/defeat images: {e}")
            self.victory_img = None
            self.defeat_img = None

        try:
            # BattleBar.png for strength bar borders
            self.bar_border_img = pygame.image.load("assets/BattleBar.png").convert_alpha()
            self.bar_border_original_h = self.bar_border_img.get_height()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattleBar.png: {e}")
            self.bar_border_img = None
            # C2 fix: BAR_HEIGHT was undefined — use BAR_PNG_HEIGHT_REF instead
            self.bar_border_original_h = BAR_PNG_HEIGHT_REF

        # Get fonts (scaled based on reference resolution)
        ui_scale = self.screen_height / REFERENCE_HEIGHT
        # The preview (ui/battle_screen_panels.py compose_side_* / compose_banner)
        self.preview_fonts = {
            'role': self.font_manager.get_bold_font(int(13 * ui_scale)),
            'name': self.font_manager.get_bold_font(int(21 * ui_scale)),
            'heading': self.font_manager.get_bold_font(int(14 * ui_scale)),
            'body': self.font_manager.get_font(int(15 * ui_scale)),
            'tag': self.font_manager.get_bold_font(int(12 * ui_scale)),
            'banner_title': self.font_manager.get_bold_font(int(20 * ui_scale)),
            'banner_sub': self.font_manager.get_font(int(14 * ui_scale)),
            # The Advantage / Disadvantage tags' tooltips
            'tip_title': self.font_manager.get_bold_font(int(15 * ui_scale)),
            'tip_body': self.font_manager.get_font(int(13 * ui_scale)),
        }
        self.button_font = self.font_manager.get_bold_font(int(15 * ui_scale))
        self.hint_font = self.font_manager.get_font(int(12 * ui_scale))  # The Skip button's keycap
        # The battle report (ui/battle_screen_panels.py compose_report)
        self.report_fonts = {
            'caption': self.font_manager.get_bold_font(int(13 * ui_scale)),
            'banner': self.font_manager.get_bold_font(int(34 * ui_scale)),
            'headline': self.font_manager.get_font(int(17 * ui_scale)),
            'heading': self.font_manager.get_bold_font(int(15 * ui_scale)),
            'body': self.font_manager.get_font(int(15 * ui_scale)),
            'columns': self.font_manager.get_bold_font(int(13 * ui_scale)),
        }

    def _calculate_layout(self):
        """Calculate positions and sizes for all UI elements.

        All pixel values are scaled based on screen size relative to
        the reference resolution (1600x900).
        """
        # Calculate scale factors based on reference resolution
        self.scale_x = self.screen_width / REFERENCE_WIDTH
        self.scale_y = self.screen_height / REFERENCE_HEIGHT
        # Use average for uniform scaling of most elements
        self.scale = (self.scale_x + self.scale_y) / 2

        # Scale helper function
        def s(value):
            """Scale a pixel value based on resolution."""
            return int(value * self.scale)

        # Scaled values from reference constants
        panel_gap = s(PANEL_GAP_REF)
        panel_top_margin = s(PANEL_TOP_MARGIN_REF)
        self.bar_fill_height = s(BAR_FILL_HEIGHT_REF)
        self.bar_png_height = s(BAR_PNG_HEIGHT_REF)
        self.bar_top_margin = s(BAR_TOP_MARGIN_REF)
        self.bar_fill_offset = int(BAR_FILL_OFFSET_REF * self.scale)  # Keep sign
        close_button_width = s(CLOSE_BUTTON_WIDTH_REF)
        close_button_height = battle_screen_kit.button_height(close_button_width)

        # Panel dimensions
        self.panel_width = int(self.screen_width * PANEL_WIDTH_RATIO)
        self.panel_height = int(self.screen_height * PANEL_HEIGHT_RATIO)

        # Panel positions (centered with gap)
        total_width = self.panel_width * 2 + panel_gap
        left_x = (self.screen_width - total_width) // 2

        self.attacker_panel_rect = pygame.Rect(
            left_x,
            panel_top_margin,
            self.panel_width,
            self.panel_height
        )

        self.defender_panel_rect = pygame.Rect(
            left_x + self.panel_width + panel_gap,
            panel_top_margin,
            self.panel_width,
            self.panel_height
        )

        # The side panels' content: inside the art's frame, clear of its corner spears
        self.attacker_content_rect = self._panel_content(self.attacker_panel_rect, PREVIEW_INSET_X)
        self.defender_content_rect = self._panel_content(self.defender_panel_rect, PREVIEW_INSET_X)

        # Battle icon position (centered in gap)
        gap_center_x = left_x + self.panel_width + panel_gap // 2
        self.icon_center_x = gap_center_x  # Store for pulsation rendering
        if self.battle_icon:
            icon_y = panel_top_margin + s(50)
            self.icon_center_y = icon_y + self.battle_icon.get_height() // 2  # Center Y for pulsation
            self.battle_icon_pos = (
                gap_center_x - self.battle_icon.get_width() // 2,
                icon_y
            )
        else:
            self.battle_icon_pos = (gap_center_x, panel_top_margin + s(50))
            self.icon_center_y = panel_top_margin + s(80)

        # Strength bars (below panels)
        # Fill and PNG can have independent widths
        bar_y = self.attacker_panel_rect.bottom + self.bar_top_margin
        bar_fill_width = int(self.screen_width * BAR_FILL_WIDTH_RATIO)
        self.bar_png_width = int(self.screen_width * BAR_PNG_WIDTH_RATIO)

        # Attacker bar - aligned with attacker panel (fill dimensions)
        self.attacker_bar_rect = pygame.Rect(
            self.attacker_panel_rect.centerx - bar_fill_width // 2,
            bar_y,
            bar_fill_width,
            self.bar_fill_height
        )

        # Defender bar - aligned with defender panel (fill dimensions)
        self.defender_bar_rect = pygame.Rect(
            self.defender_panel_rect.centerx - bar_fill_width // 2,
            bar_y,
            bar_fill_width,
            self.bar_fill_height
        )

        # The action button: Resolve Battle in setup, Skip in the fight, one slot centred
        # under the bars - clear of the bolts' level line and of the chunks, which fall
        # under their own bar. The Skip button's keycap goes below it.
        action_width = s(ACTION_BUTTON_WIDTH_REF)
        bar_fill_bottom = bar_y + self.bar_fill_offset + self.bar_fill_height
        self.resolve_button_rect = pygame.Rect(
            gap_center_x - action_width // 2,
            bar_fill_bottom + s(ACTION_BUTTON_GAP_REF),
            action_width,
            battle_screen_kit.button_height(action_width)
        )
        self.skip_button_rect = self.resolve_button_rect.copy()
        self.skip_hint_top = self.skip_button_rect.bottom + s(SKIP_HINT_GAP_REF)

        # Report panel (centered, used in REPORT state) and its Close button, on the
        # panel's bottom frame: the smallest panel until the report is composed
        # (_prepare_report sizes it)
        self._close_button_size = (close_button_width, close_button_height)
        self._report_parts = None
        self._layout_report(0)

        # P2/P3 fix: pre-scale battle bar borders and panel backgrounds (constant sizes)
        self._scaled_bar_border = None
        self._scaled_bar_border_flipped = None
        if self.bar_border_img:
            self._scaled_bar_border = pygame.transform.smoothscale(
                self.bar_border_img, (self.bar_png_width, self.bar_png_height))
            # The defender bar is mirrored, so its frame is mirrored too -
            # BattleBar.png is not horizontally symmetric.
            self._scaled_bar_border_flipped = pygame.transform.flip(
                self._scaled_bar_border, True, False)
        # Bounded cache of pulsed battle-icon sizes, keyed on a quantised scale,
        # so the pulse no longer smoothscales the icon every single frame.
        self._pulsed_icon_cache = {}
        self._scaled_panel_bg = None
        if self.panel_bg:
            self._scaled_panel_bg = pygame.transform.smoothscale(
                self.panel_bg, (self.attacker_panel_rect.width, self.attacker_panel_rect.height))

    @staticmethod
    def _panel_content(rect, inset_x_share=REPORT_INSET_X):
        """The content area of a panel drawn with the panel art (REPORT_INSET_* shares)."""
        inset_x = int(rect.width * inset_x_share)
        top = rect.top + int(rect.height * REPORT_INSET_TOP)
        return pygame.Rect(rect.left + inset_x, top, rect.width - 2 * inset_x,
                           rect.bottom - int(rect.height * REPORT_INSET_BOTTOM) - top)

    def _layout_report(self, content_height):
        """
        Size the report panel to a report `content_height` px tall (between the
        REPORT_PANEL_*_HEIGHT_RATIO shares of the screen), centred, with Close on its
        bottom frame. The panel art at that size comes from the kit's cache, so a report
        the same size as an earlier one scales nothing.
        """
        room = 1.0 - REPORT_INSET_TOP - REPORT_INSET_BOTTOM
        height = int(math.ceil(content_height / room)) if content_height > 0 else 0
        height = max(int(self.screen_height * REPORT_PANEL_MIN_HEIGHT_RATIO),
                     min(int(self.screen_height * REPORT_PANEL_MAX_HEIGHT_RATIO), height))
        width = int(self.screen_width * REPORT_PANEL_WIDTH_RATIO)
        self.report_panel_rect = pygame.Rect((self.screen_width - width) // 2,
                                             (self.screen_height - height) // 2, width, height)
        close_w, close_h = self._close_button_size
        self.close_button_rect = pygame.Rect(0, 0, close_w, close_h)
        self.close_button_rect.center = (self.report_panel_rect.centerx,
                                         self.report_panel_rect.top + int(height * REPORT_CLOSE_Y))
        self.report_content_rect = self._panel_content(self.report_panel_rect)
        self._scaled_report_bg = battle_screen_kit.art(REPORT_PANEL_ART, self.report_panel_rect.size)

    def _report_width(self):
        """The report's width: the board's, less a gutter for the scrollbar."""
        width = int(self.screen_width * REPORT_PANEL_WIDTH_RATIO)
        gutter = int((battle_screen_kit.SCROLL_BAR + battle_screen_kit.SCROLL_BAR_GAP) * self.scale)
        return width - 2 * int(width * REPORT_INSET_X) - gutter

    def _extract_battle_data(self):
        """Extract battle information for display."""
        battle = self.game_state.pending_battles[self.battle_index]

        self.territory = battle.territory

        # Identify attacker and defenders
        # Attacker is the player who moved into the territory (not the original owner)
        original_owner = battle.original_owner
        self.original_owner = original_owner

        self.attacker_player = None
        self.defender_players = []

        # SIMULTANEOUS MODE: Use battle.attackers list if available (correctly computed by sim_phase_manager)
        # This ensures allied defenders aren't mistakenly identified as attackers
        if hasattr(battle, 'attackers') and battle.attackers:
            # Use the pre-computed attackers list
            if len(battle.attackers) >= 1:
                self.attacker_player = battle.attackers[0]  # First attacker is shown on left panel

            # First, check if there are any non-attackers (true defenders)
            non_attackers = [p for p in battle.armies.keys() if p not in battle.attackers]

            if non_attackers:
                # There are true defenders (e.g., territory owner or allies)
                self.defender_players = non_attackers
            else:
                # All participants are attackers (multi-way attack on neutral territory)
                # Show other attackers as opponents on the right side for UI purposes
                for player_index in battle.attackers[1:]:  # Skip first attacker (shown on left)
                    if player_index in battle.armies:  # Only include those with armies
                        self.defender_players.append(player_index)
        else:
            # SEQUENTIAL MODE FALLBACK: Original logic based on owner
            all_participants = list(battle.armies.keys())
            for player_index in all_participants:
                # Check if this is the territory owner (defender)
                if player_index == original_owner and original_owner >= 0:
                    self.defender_players.append(player_index)
                else:
                    # Non-owner - first one is attacker, rest are "defenders" (opponents)
                    if self.attacker_player is None:
                        self.attacker_player = player_index
                    else:
                        # Additional non-owners are opponents (e.g., two players arriving at neutral)
                        self.defender_players.append(player_index)

            # If no clear attacker found, use first non-owner
            if self.attacker_player is None and len(battle.armies) > 0:
                self.attacker_player = list(battle.armies.keys())[0]

        # Add allied defenders (allies who contribute to defense but aren't in battle.armies directly)
        if hasattr(battle, 'allied_defenders'):
            for ally in battle.allied_defenders:
                if ally not in self.defender_players:
                    self.defender_players.append(ally)

        # If no defenders found, add original owner ONLY if it's a valid player (>= 0)
        # Don't add -1 (neutral) as a defender
        if not self.defender_players and original_owner is not None and original_owner >= 0:
            self.defender_players.append(original_owner)

        # Get army compositions
        self.attacker_composition = {}
        if self.attacker_player is not None and self.attacker_player in battle.army_compositions:
            self.attacker_composition = battle.army_compositions[self.attacker_player].copy()

        # Aggregate defender compositions
        self.defender_composition = {}
        for def_player in self.defender_players:
            if def_player in battle.army_compositions:
                for unit_type, count in battle.army_compositions[def_player].items():
                    self.defender_composition[unit_type] = self.defender_composition.get(unit_type, 0) + count

        # Get army counts
        self.attacker_count = battle.armies.get(self.attacker_player, 0) if self.attacker_player is not None else 0
        self.defender_count = sum(battle.armies.get(p, 0) for p in self.defender_players)

        # Check for Keep
        self.has_keep = (hasattr(battle, 'keep_bonus_player') and
                        battle.keep_bonus_player is not None)
        self.keep_bonus = getattr(battle, 'keep_bonus', 0)

        # Get player colors
        self.attacker_color = self.game_state.get_player_color(self.attacker_player) if self.attacker_player is not None else (200, 200, 200)

        # Defender color = territory owner color (if valid), otherwise use first defender's color
        if original_owner is not None and original_owner >= 0:
            self.defender_color = self.game_state.get_player_color(original_owner)
        elif self.defender_players:
            self.defender_color = self.game_state.get_player_color(self.defender_players[0])
        else:
            self.defender_color = (200, 200, 200)

        # Calculate effective strengths for display
        self._calculate_effective_strengths()

    def _calculate_effective_strengths(self):
        """Calculate effective strengths for display on panels."""
        battle = self.game_state.pending_battles[self.battle_index]
        # A simultaneous round's battle is fought with the round's frozen heroes and
        # territorial bonuses (BattleContext) - the bars show the same numbers; None = live
        battle_context = getattr(battle, 'battle_context', None)
        # What makes up each strength, for the panels' bonus lists (the same calls fill
        # them: calculate_army_effective_strength(breakdown=)); the Keep is a flat entry
        self.attacker_breakdown = []
        self.defender_breakdown = []

        # Use game_state's calculation method if available
        if hasattr(self.game_state, 'calculate_army_effective_strength'):
            # Calculate attacker strength (including veterancy bonus)
            if self.attacker_player is not None and self.attacker_composition:
                atk_avg_levels = self.game_state.get_unit_avg_levels(self.territory, self.attacker_player)
                self.attacker_strength = self.game_state.calculate_army_effective_strength(
                    self.attacker_composition,
                    self.defender_composition,
                    self.attacker_player,
                    self.territory,
                    unit_avg_levels=atk_avg_levels,
                    battle_context=battle_context,
                    breakdown=self.attacker_breakdown
                )
            else:
                self.attacker_strength = 0.0

            # Calculate defender strength (including veterancy bonus)
            if self.defender_composition:
                def_player = self.defender_players[0] if self.defender_players else None
                def_avg_levels = self.game_state.get_unit_avg_levels(self.territory, def_player) if def_player is not None else None
                base_strength = self.game_state.calculate_army_effective_strength(
                    self.defender_composition,
                    self.attacker_composition,
                    def_player,
                    self.territory,
                    unit_avg_levels=def_avg_levels,
                    battle_context=battle_context,
                    breakdown=self.defender_breakdown
                )
                self.defender_strength = base_strength + (self.keep_bonus if self.has_keep else 0)
            else:
                self.defender_strength = self.keep_bonus if self.has_keep else 0.0
        else:
            # Fallback to simple army counts
            self.attacker_strength = float(self.attacker_count)
            self.defender_strength = float(self.defender_count) + (self.keep_bonus if self.has_keep else 0)
        if self.has_keep and self.keep_bonus:
            self.defender_breakdown.append({'key': 'keep', 'label': 'Keep', 'flat': self.keep_bonus})

        # Both bars start full (owner, 2026-10-29: an informed mystery - the bonus list
        # and the Advantage tags show what each side has, the fight shows who is stronger:
        # each side's hits are sized to its real loss - and the report gives the numbers).
        # They used to start at the strengths' ratio, which gave the winner away.
        self.attacker_fill = 1.0
        self.defender_fill = 1.0

    @staticmethod
    def _survivor_fill(initial_fill, survivors, initial_count):
        """
        Convert a survivor count into a bar fill ratio.

        The bars are normalised so the stronger side starts at 1.0 and the
        weaker side at strength_ratio, so a raw survivors/count value is only
        meaningful relative to that starting fill. Scaling by initial_fill keeps
        the bar shrinking proportionally - without it a weaker side that wins
        would end with a *longer* bar than it started with.

        Args:
            initial_fill: The side's starting fill ratio (0.0-1.0)
            survivors: Surviving army count
            initial_count: Army count before the battle

        Returns:
            Final fill ratio (0.0-1.0)
        """
        if initial_count <= 0:
            return 0.0
        return initial_fill * (survivors / initial_count)

    def _pre_calculate_battle_result(self):
        """
        Pre-calculate battle outcome before animation.

        Stores result for animation display without applying to game state yet.
        """
        # Generate deterministic seed for animation (for multiplayer sync)
        # Use battle territory name and turn number for reproducibility. The territory
        # cached when the window opened - NOT pending_battles[self.battle_index]: in
        # multiplayer another player's battle can be resolved while this window is open,
        # which shifts the list (that index then pointed at another battle, or past the
        # end of the list and crashed the FIGHT click).
        seed_str = f"{self.territory}_{self.game_state.turn_number}"
        self.animation_seed = hash(seed_str) % (2**31)

        # Calculate animation duration deterministically
        random.seed(self.animation_seed)
        self.animation_duration = random.uniform(ANIMATION_MIN_DURATION, ANIMATION_MAX_DURATION)

        # Pre-calculate battle outcome using existing game logic
        # This simulates the battle without modifying game state

        # Store initial armies for survivor calculation
        initial_attacker = self.attacker_count
        initial_defender = self.defender_count

        # Determine winner based on effective strength
        if self.attacker_strength > self.defender_strength:
            self.winner = self.attacker_player
            # Estimate survivors (simplified)
            strength_diff = self.attacker_strength - self.defender_strength
            survivor_ratio = min(1.0, strength_diff / self.attacker_strength) if self.attacker_strength > 0 else 0
            self.attacker_survivors = max(1, int(initial_attacker * (0.3 + 0.7 * survivor_ratio)))
            self.defender_survivors = 0
        elif self.defender_strength > self.attacker_strength:
            self.winner = self.defender_players[0] if self.defender_players else None
            strength_diff = self.defender_strength - self.attacker_strength
            survivor_ratio = min(1.0, strength_diff / self.defender_strength) if self.defender_strength > 0 else 0
            self.defender_survivors = max(1, int(initial_defender * (0.3 + 0.7 * survivor_ratio)))
            self.attacker_survivors = 0
        else:
            # Tie - both bars drain to empty; actual winner determined by dice
            # set_actual_battle_result() will update winner/survivors with real values
            self.winner = self.attacker_player  # placeholder, overwritten by actual result
            self.attacker_survivors = 0
            self.defender_survivors = 0

        # Calculate final bar fills
        # Perfect tie: both drain to 0 (visually shows evenly matched before dice)
        if self.attacker_survivors == 0 and self.defender_survivors == 0:
            self.attacker_final_fill = 0.0
            self.defender_final_fill = 0.0
        elif self.winner == self.attacker_player:
            self.attacker_final_fill = self._survivor_fill(
                self.attacker_fill, self.attacker_survivors, initial_attacker)
            self.defender_final_fill = 0.0
        else:
            self.attacker_final_fill = 0.0
            self.defender_final_fill = self._survivor_fill(
                self.defender_fill, self.defender_survivors, initial_defender)

        # Determine if current player won
        self.current_player_won = (self.winner == self.current_player)

        # Calculate unit type breakdown for current player
        # Estimate which units survived/were lost proportionally
        current_player_composition = None
        current_player_survivors = 0
        current_player_total = 0

        if self.current_player == self.attacker_player:
            current_player_composition = self.attacker_composition.copy()
            current_player_survivors = self.attacker_survivors
            current_player_total = initial_attacker
        elif self.current_player in self.defender_players:
            current_player_composition = self.defender_composition.copy()
            current_player_survivors = self.defender_survivors
            current_player_total = initial_defender

        # Calculate unit breakdown for current player
        # Use a two-pass approach to ensure totals match exactly
        unit_breakdown = {}
        if current_player_composition and current_player_total > 0:
            # First pass: calculate preliminary survivors proportionally
            survivor_ratio = current_player_survivors / current_player_total
            preliminary = {}
            for unit_type, count in current_player_composition.items():
                survived = int(count * survivor_ratio)
                preliminary[unit_type] = {'original': count, 'survived': survived}

            # Calculate difference between sum and actual survivors
            calculated_sum = sum(p['survived'] for p in preliminary.values())
            difference = current_player_survivors - calculated_sum

            # Second pass: adjust to match actual total
            # Sort by original count (descending) to adjust largest units first
            sorted_types = sorted(preliminary.keys(),
                                  key=lambda t: preliminary[t]['original'],
                                  reverse=True)

            for unit_type in sorted_types:
                if difference == 0:
                    break
                original = preliminary[unit_type]['original']
                current_survived = preliminary[unit_type]['survived']

                if difference > 0:
                    # Need to add survivors - can't exceed original count
                    can_add = min(difference, original - current_survived)
                    preliminary[unit_type]['survived'] += can_add
                    difference -= can_add
                elif difference < 0:
                    # Need to remove survivors - can't go below 0
                    can_remove = min(-difference, current_survived)
                    preliminary[unit_type]['survived'] -= can_remove
                    difference += can_remove

            # Build final breakdown with lost counts
            for unit_type, data in preliminary.items():
                lost = data['original'] - data['survived']
                unit_breakdown[unit_type] = {
                    'original': data['original'],
                    'survived': data['survived'],
                    'lost': lost
                }

        # Store battle result
        self.battle_result = {
            'winner': self.winner,
            'attacker_survivors': self.attacker_survivors,
            'defender_survivors': self.defender_survivors,
            'attacker_lost': initial_attacker - self.attacker_survivors,
            'defender_lost': initial_defender - self.defender_survivors,
            'unit_breakdown': unit_breakdown  # Unit type breakdown for current player
        }

    def _start_animation(self):
        """Start the volley combat animation."""
        self.state = BattleInterfaceState.ANIMATING
        self.elapsed = 0.0

        # Create volley effect with bar border image and scaled dimensions
        self.particle_effect = BattleBarVolleyEffect(
            attacker_bar_rect=self.attacker_bar_rect,
            defender_bar_rect=self.defender_bar_rect,
            attacker_color=self.attacker_color,
            defender_color=self.defender_color,
            attacker_initial_fill=self.attacker_fill,
            defender_initial_fill=self.defender_fill,
            attacker_final_fill=self.attacker_final_fill,
            defender_final_fill=self.defender_final_fill,
            seed=self.animation_seed,
            bar_border_img=self.bar_border_img,
            bar_png_width=self.bar_png_width,
            bar_fill_offset=self.bar_fill_offset,
            bar_png_height=self.bar_png_height,
            ui_scale=self.scale,
            attacker_count=self.attacker_count,
            defender_count=self.defender_count,
            light=self.light,
            ambient_clock=self._ambient_clock
        )

        # The duration now falls out of the volley schedule rather than being
        # drawn up front, so adopt it - update() times the post-animation hold
        # against self.animation_duration.
        self.animation_duration = self.particle_effect.duration

    def _start_splash(self):
        """Start the victory/defeat splash animation."""
        self.state = BattleInterfaceState.SPLASH
        self.elapsed = 0.0
        # The result is final: compose the report now, not on its first frame
        self._prepare_report()

        # Choose appropriate image
        if self.current_player_won:
            image = self.victory_img
        else:
            image = self.defeat_img

        if image:
            self.splash_effect = BattleSplashEffect(
                image=image,
                screen_width=self.screen_width,
                screen_height=self.screen_height
            )
        else:
            # Skip splash if no image
            self._start_report()

    def _start_report(self):
        """Start the battle report display."""
        self.state = BattleInterfaceState.REPORT
        self.elapsed = 0.0

    def update(self, delta_time):
        """
        Update the interface state.

        Args:
            delta_time: Time since last update in seconds
        """
        self.elapsed += delta_time
        self._ambient_clock += delta_time

        if self.state == BattleInterfaceState.ANIMATING:
            if self.particle_effect:
                self.particle_effect.update(delta_time)
                if self.particle_effect.is_finished():
                    # Wait 0.5 seconds after animation completes
                    if self.elapsed >= self.animation_duration + 0.5:
                        self._start_splash()

        elif self.state == BattleInterfaceState.SPLASH:
            if self.splash_effect:
                self.splash_effect.update(delta_time)
                if self.splash_effect.is_finished():
                    self._start_report()

    def set_actual_battle_result(self, winner: int, attacker_survivors: int,
                                  defender_survivors: int, surviving_units: list = None,
                                  outcome: dict = None):
        """
        Update the battle result with actual values from game_state.resolve_battle().

        This replaces the pre-calculated estimates with the real battle outcome.
        Should be called immediately after game_state.resolve_battle().

        Args:
            winner: Actual winner player index
            attacker_survivors: Actual number of attacker survivors
            defender_survivors: Actual number of defender survivors
            surviving_units: List of surviving unit dicts with 'type' key
            outcome: GameState.battle_outcome() for the viewer - the report's outcome
                lines (the Keep, buildings, heroes slain, XP); None leaves them out
        """
        # Update internal survivor counts
        self.winner = winner
        self.outcome = outcome or {}
        self._report_parts = None
        self.attacker_survivors = attacker_survivors
        self.defender_survivors = defender_survivors
        self.current_player_won = (winner == self.current_player)

        # Re-aim the bars at the real outcome. This runs a frame after the
        # animation starts, while nothing has landed yet, so the volley rhythm
        # is untouched and only the chunk sizes change. It also fixes the
        # strength-tie case, where the pre-calculated estimate drains both bars
        # to empty and the report then names a winner anyway.
        if winner == self.attacker_player:
            self.attacker_final_fill = self._survivor_fill(
                self.attacker_fill, attacker_survivors, self.attacker_count)
            self.defender_final_fill = 0.0
        elif winner in self.defender_players:
            self.attacker_final_fill = 0.0
            self.defender_final_fill = self._survivor_fill(
                self.defender_fill, defender_survivors, self.defender_count)
        else:
            self.attacker_final_fill = 0.0
            self.defender_final_fill = 0.0

        if self.particle_effect is not None:
            self.particle_effect.retarget(self.attacker_final_fill,
                                          self.defender_final_fill)

        # Recalculate unit breakdown with actual survivors
        if self.current_player == self.attacker_player:
            current_player_composition = self.attacker_composition.copy()
            current_player_survivors = attacker_survivors
            current_player_total = self.attacker_count
        elif self.current_player in self.defender_players:
            current_player_composition = self.defender_composition.copy()
            current_player_survivors = defender_survivors
            current_player_total = self.defender_count
        else:
            current_player_composition = {}
            current_player_survivors = 0
            current_player_total = 0

        # If we have actual surviving units, use them for precise breakdown
        unit_breakdown = {}
        if surviving_units and self.current_player_won:
            # Count survivors by type from actual data
            survivor_counts = {}
            for unit in surviving_units:
                unit_type = unit.get('type', 'Swordsman')
                survivor_counts[unit_type] = survivor_counts.get(unit_type, 0) + 1

            # Build breakdown comparing original to survivors
            for unit_type, original_count in current_player_composition.items():
                survived = survivor_counts.get(unit_type, 0)
                lost = original_count - survived
                unit_breakdown[unit_type] = {
                    'original': original_count,
                    'survived': survived,
                    'lost': lost
                }
        elif current_player_composition and current_player_total > 0:
            # Fallback: proportional calculation (for losers or if no unit data)
            survivor_ratio = current_player_survivors / current_player_total if current_player_total > 0 else 0
            preliminary = {}
            for unit_type, count in current_player_composition.items():
                survived = int(count * survivor_ratio)
                preliminary[unit_type] = {'original': count, 'survived': survived}

            # Adjust to match actual total
            calculated_sum = sum(p['survived'] for p in preliminary.values())
            difference = current_player_survivors - calculated_sum

            sorted_types = sorted(preliminary.keys(),
                                  key=lambda t: preliminary[t]['original'],
                                  reverse=True)

            for unit_type in sorted_types:
                if difference == 0:
                    break
                original = preliminary[unit_type]['original']
                current_survived = preliminary[unit_type]['survived']

                if difference > 0:
                    can_add = min(difference, original - current_survived)
                    preliminary[unit_type]['survived'] += can_add
                    difference -= can_add
                elif difference < 0:
                    can_remove = min(-difference, current_survived)
                    preliminary[unit_type]['survived'] -= can_remove
                    difference += can_remove

            for unit_type, data in preliminary.items():
                lost = data['original'] - data['survived']
                unit_breakdown[unit_type] = {
                    'original': data['original'],
                    'survived': data['survived'],
                    'lost': lost
                }

        # Update battle_result with actual values
        self.battle_result = {
            'winner': winner,
            'attacker_survivors': attacker_survivors,
            'defender_survivors': defender_survivors,
            'attacker_lost': self.attacker_count - attacker_survivors,
            'defender_lost': self.defender_count - defender_survivors,
            'unit_breakdown': unit_breakdown
        }

    def handle_click(self, pos):
        """
        Handle mouse click events.

        Args:
            pos: (x, y) tuple of click position

        Returns:
            str or None: 'resolve', 'skip', 'close', or None if no button clicked
        """
        if self.state == BattleInterfaceState.SETUP:
            if self.resolve_button_rect.collidepoint(pos):
                self._trigger_flash('resolve')
                self._pre_calculate_battle_result()
                self._start_animation()
                return 'resolve'

        elif self.state == BattleInterfaceState.ANIMATING:
            # The Skip button - or a click anywhere - cuts a long battle short
            if self.skip_animation():
                return 'skip'

        elif self.state == BattleInterfaceState.REPORT:
            if self.close_button_rect.collidepoint(pos):
                self._trigger_flash('close')
                self.is_finished_flag = True
                return 'close'

        return None

    def skip_animation(self):
        """
        Jump the volley animation straight to its finished state.

        Returns:
            bool: True if an animation was actually skipped
        """
        if self.state != BattleInterfaceState.ANIMATING or self.particle_effect is None:
            return False
        # (No click flash: the splash replaces the Skip button on the next frame - owner,
        # 2026-10-28: it lingered over the splash while it flashed)
        self.particle_effect.skip()
        # Push past the post-animation hold so update() moves on to the splash
        # on the next frame.
        self.elapsed = self.animation_duration + 0.5
        return True

    def handle_key(self, event):
        """
        Handle key presses while the interface is open.

        Args:
            event: pygame KEYDOWN event

        Returns:
            str or None: 'skip' if the animation was skipped, else None
        """
        if event.key in (pygame.K_SPACE, pygame.K_ESCAPE):
            if self.skip_animation():
                return 'skip'
        return None

    def handle_mouse_motion(self, pos):
        """
        Handle mouse movement for hover effects.

        Args:
            pos: (x, y) tuple of mouse position
        """
        self.mouse_pos = pos

    def _render_overlay(self):
        """Darken the map behind the battle screen: a vignette, deeper toward the edges."""
        self.light.darken(self.screen)

    def _attacker_title(self):
        """The left panel's name."""
        if self.attacker_player is None:
            return "Unknown"
        return self.game_state.get_player_name(self.attacker_player)

    def _defender_title(self):
        """The right panel's name - the same in the preview and the fight."""
        if not self.defender_players:
            return "Defenders"
        if len(self.defender_players) == 1:
            return self.game_state.get_player_name(self.defender_players[0])
        return f"{len(self.defender_players)} Defenders"

    def _prepare_preview(self):
        """
        Compose the preview once, as the window opens (ui/battle_screen_panels.py): the
        banner naming the battle and, per side, its fixed top (role, flag, name) and its
        rows - the army, the bonuses - which scroll with the mouse wheel when they
        outgrow the panel (handle_wheel). Drawn unchanged through the setup and the fight.
        """
        fonts = self.preview_fonts
        owner = getattr(self, 'original_owner', None)
        defending = owner is not None and owner >= 0 and owner in self.defender_players
        views = (
            battle_screen_panels.side_view(
                "Attacking", self._attacker_title(), self.attacker_player, self.attacker_color,
                self.attacker_composition, self.attacker_breakdown),
            battle_screen_panels.side_view(
                "Defending" if defending else "Opposing", self._defender_title(),
                self.defender_players[0] if len(self.defender_players) == 1 else owner,
                self.defender_color, self.defender_composition, self.defender_breakdown,
                keep=self.has_keep))
        self._sides = []
        # Per side: where its Advantage / Disadvantage tags are in its rows, and what each
        # one explains (_matchup_at)
        self._side_tags = []
        for view, content in zip(views, (self.attacker_content_rect, self.defender_content_rect)):
            header = battle_screen_panels.compose_side_header(view, content.width, fonts, self.scale)
            left = battle_screen_panels.side_indent(content.width)
            body, tags = battle_screen_panels.compose_side_body(view, content.width - 2 * left, fonts,
                                                                self.scale)
            self._side_tags.append((tags, view['matchups']))
            room = pygame.Rect(content.left + left, content.top + header.get_height(),
                               content.width - 2 * left, content.bottom - content.top - header.get_height())
            self._sides.append((header, battle_screen_kit.ScrollView(body, room, self.scale)))
        turn = getattr(self.game_state, 'turn_number', 0)
        self._banner = battle_screen_panels.compose_banner(
            f"Battle of {map_data.get_display_name(self.territory)}",
            f"Turn {turn}" if turn else None, fonts, self.scale)

    def _render_sides(self):
        """The two panels with their composed content, and the banner above them."""
        for rect, content, (header, rows) in zip(
                (self.attacker_panel_rect, self.defender_panel_rect),
                (self.attacker_content_rect, self.defender_content_rect), self._sides):
            if self._scaled_panel_bg:
                self.screen.blit(self._scaled_panel_bg, rect.topleft)
            else:
                pygame.draw.rect(self.screen, (40, 40, 60), rect)
                pygame.draw.rect(self.screen, WHITE, rect, 2)
            self.screen.blit(header, content.topleft)
            rows.draw(self.screen)
        self.screen.blit(self._banner, self._banner_rect())

    def _matchup_at(self, pos):
        """The matchup (breakdown entry) of the Advantage / Disadvantage tag under `pos` in
        either side's visible rows, or None."""
        for (_header, rows), (tags, matchups) in zip(getattr(self, '_sides', ()),
                                                     getattr(self, '_side_tags', ())):
            if not rows.rect.collidepoint(pos):
                continue
            local = (pos[0] - rows.rect.x, pos[1] - rows.rect.y + rows.offset)
            for rect, unit_type in tags:
                if rect.collidepoint(local) and unit_type in matchups:
                    return matchups[unit_type]
        return None

    def _render_matchup_tip(self):
        """
        Hovering a unit type's Advantage / Disadvantage tag explains it (owner,
        2026-10-29): which enemy units it counters or is countered by, and the factor
        (battle_screen_panels.matchup_tip). Next to the cursor, kept on the screen.
        """
        entry = self._matchup_at(self.mouse_pos)
        if entry is None:
            return
        title, lines = battle_screen_panels.matchup_tip(entry)
        mark = 'up' if entry['factor'] >= 1 else 'down'
        fonts = self.preview_fonts
        box = battle_screen_kit.tooltip_box(
            title, battle_screen_panels.MARK_COLORS[mark], lines, fonts['tip_title'],
            fonts['tip_body'], self.scale, int(TIP_WIDTH_REF * self.scale))
        mx, my = self.mouse_pos
        x, y = mx + int(16 * self.scale), my + int(18 * self.scale)
        if x + box.get_width() > self.screen_width - 4:
            x = mx - box.get_width() - int(12 * self.scale)
        if y + box.get_height() > self.screen_height - 4:
            y = my - box.get_height() - int(10 * self.scale)
        self.screen.blit(box, (max(4, x), max(4, y)))

    def _banner_rect(self):
        """Where the battle's banner goes: centred, just above the panels."""
        panel = self.attacker_panel_rect
        return self._banner.get_rect(midbottom=(
            self.screen_width // 2, panel.top + int(panel.height * BANNER_BOTTOM_SHARE)))

    @property
    def clicked_element(self):
        """The button flashing after its click ('resolve' / 'skip' / 'close'), else None."""
        name, ticks = self._flash
        if name is not None and pygame.time.get_ticks() - ticks < CLICK_FLASH_DURATION_MS:
            return name
        return None

    def _trigger_flash(self, name):
        self._flash = (name, pygame.time.get_ticks())

    def _render_button(self, rect, text, key, mark=None):
        """
        Draw an ornate button (ui/battle_screen_kit.py): brighter under the cursor,
        flashing for a moment after its click. Every sprite is baked once.

        Args:
            rect: pygame.Rect for button bounds
            text: Label
            key: The button's click-flash id ('resolve' / 'skip' / 'close')
            mark: Optional mark after the label ('skip': fast-forward)
        """
        state = battle_screen_kit.button_state(rect, self.mouse_pos, self.clicked_element == key)
        battle_screen_kit.draw_button(self.screen, rect, text, self.button_font, state, mark)

    def _render_skip_button(self):
        """The Skip button under the bars, and its "Space" keycap (Esc and a click skip too)."""
        self._render_button(self.skip_button_rect, "Skip", 'skip', mark='skip')
        hint = battle_screen_kit.key_hint("Space", self.hint_font)
        self.screen.blit(hint, hint.get_rect(midtop=(self.skip_button_rect.centerx, self.skip_hint_top)))

    def _render_pulsed_icon(self):
        """
        Draw the pulsing battle icon between the two panels.

        The pulse used to smoothscale the icon on every single frame in both the
        SETUP and ANIMATING states. The scale is quantised to
        ICON_PULSE_SCALE_STEPS steps and the results cached, so each distinct
        size is only ever built once. Shared by both states so the two copies
        cannot drift apart.

        Gold light glows with it: a soft bloom behind the swords and light round
        their outline, brighter as the icon swells and flaring with each shot.
        The pulse runs on the never-reset ambient clock, so it carries on through
        the Resolve click instead of restarting.
        """
        if not self.battle_icon or self.battle_icon_base_w <= 0:
            return

        # Calculate pulse scale using sine wave for smooth animation
        pulse_progress = (math.sin(self._ambient_clock * ICON_PULSE_SPEED * 2 * math.pi) + 1) / 2
        current_scale = ICON_PULSE_MIN_SCALE + (ICON_PULSE_MAX_SCALE - ICON_PULSE_MIN_SCALE) * pulse_progress

        # Quantise so a continuously-varying float does not defeat the cache
        step = round(current_scale * ICON_PULSE_SCALE_STEPS)
        scaled_icon = self._pulsed_icon_cache.get(step)
        if scaled_icon is None:
            quantised_scale = step / ICON_PULSE_SCALE_STEPS
            scaled_w = max(1, int(self.battle_icon_base_w * quantised_scale))
            scaled_h = max(1, int(self.battle_icon_base_h * quantised_scale))
            scaled_icon = pygame.transform.smoothscale(self.battle_icon, (scaled_w, scaled_h))
            # The pulse only ever visits a small fixed set of steps, but keep the
            # cache bounded anyway so it can never grow without limit.
            if len(self._pulsed_icon_cache) >= ICON_PULSE_CACHE_MAX:
                self._pulsed_icon_cache.clear()
            self._pulsed_icon_cache[step] = scaled_icon

        # Center it at the stored center position
        icon_x = self.icon_center_x - scaled_icon.get_width() // 2
        icon_y = self.icon_center_y - scaled_icon.get_height() // 2

        style = ICON_GLOW_STYLE
        kick = 0.0
        if self.state == BattleInterfaceState.ANIMATING and self.particle_effect is not None:
            kick = style['shot_kick'] * self.particle_effect.shot_kick()
        bloom_lo, bloom_hi = style['bloom_level']
        self.light.draw_icon_bloom(self.screen, self.battle_icon, (self.icon_center_x, self.icon_center_y),
                                   bloom_lo + (bloom_hi - bloom_lo) * pulse_progress + kick * 0.5)
        self.screen.blit(scaled_icon, (icon_x, icon_y))
        outline_lo, outline_hi = style['outline']
        self.light.draw_icon_outline(self.screen, self.battle_icon, step / ICON_PULSE_SCALE_STEPS, step,
                                     (icon_x, icon_y),
                                     outline_lo + (outline_hi - outline_lo) * pulse_progress + kick)

    def _render_strength_bars(self):
        """Render the strength comparison bars using BattleBar.png as border."""
        # Calculate fill Y position (offset from bar rect for independent positioning)
        fill_y = self.attacker_bar_rect.top + self.bar_fill_offset

        # The bars are mirrored - the attacker fills from its left edge, the
        # defender from its right - so both erode inward toward the centre once
        # the volleys start. They are painted by the same BattleLight.draw_bar()
        # as BattleBarVolleyEffect.render(), at the same ambient clock, so
        # nothing jumps when the animation begins.
        sheen_period = BAR_STYLE['sheen']['period']
        bars = ((self.attacker_bar_rect, False, self.attacker_color, self.attacker_fill),
                (self.defender_bar_rect, True, self.defender_color, self.defender_fill))
        for i, (rect, anchor_right, colour, fill) in enumerate(bars):
            seam = self.light.seam_level(self._ambient_clock, 1.7 * i)
            seam *= min(1.0, max(0.0, fill) / BAR_STYLE['seam']['empty_fade'])
            self.light.draw_bar(self.screen, rect, fill_y, anchor_right, colour, fill, seam=seam,
                                sheen=self.light.idle_sheen(self._ambient_clock, i * sheen_period / 2.0))

        # Draw borders using BattleBar.png if available
        # P2 fix: use pre-scaled bar border instead of smoothscale per frame
        if self._scaled_bar_border:
            # Center PNG both vertically and horizontally over the fill area
            png_offset_y = (self.attacker_bar_rect.height - self.bar_png_height) // 2
            attacker_png_x = self.attacker_bar_rect.centerx - self.bar_png_width // 2
            defender_png_x = self.defender_bar_rect.centerx - self.bar_png_width // 2
            self.screen.blit(self._scaled_bar_border, (attacker_png_x, self.attacker_bar_rect.top + png_offset_y))
            # Mirrored frame for the mirrored defender bar
            self.screen.blit(self._scaled_bar_border_flipped or self._scaled_bar_border,
                             (defender_png_x, self.defender_bar_rect.top + png_offset_y))
        else:
            # Fallback to simple rectangle borders
            pygame.draw.rect(self.screen, WHITE, self.attacker_bar_rect, BAR_BORDER_WIDTH)
            pygame.draw.rect(self.screen, WHITE, self.defender_bar_rect, BAR_BORDER_WIDTH)

    def _render_setup(self):
        """Render the SETUP state (panels, icon, resolve button)."""
        # While the player reads the panels, build the shots' light sprites
        # within the frame budget, so the fight itself builds nothing
        self.light.begin_frame()
        self.light.prewarm_step()

        # The banner and both sides (composed once, _prepare_preview)
        self._render_sides()

        # Render battle icon with pulsation animation
        self._render_pulsed_icon()

        # Render strength bars
        self._render_strength_bars()

        # Resolve button, under the bars (the Skip button takes its place in the fight)
        self._render_button(self.resolve_button_rect, "Resolve Battle", 'resolve')

        self._render_matchup_tip()

    def _render_animating(self):
        """Render the ANIMATING state (particle combat)."""
        # The banner and both sides, unchanged through the fight
        self._render_sides()

        # Render battle icon with pulsation animation
        self._render_pulsed_icon()

        # Render particle effect (includes animated bars)
        if self.particle_effect:
            self.particle_effect.render(self.screen)

        self._render_skip_button()
        self._render_matchup_tip()

    def _render_splash(self):
        """Render the SPLASH state (victory/defeat image)."""
        if self.splash_effect:
            self.splash_effect.render(self.screen)

    def _is_ours(self, player):
        """The viewer or one of their allies (the report's "our" / "the enemy's")."""
        viewer = self.current_player
        if player is None or viewer is None or player < 0 or viewer < 0:
            return False
        return player == viewer or self.game_state.are_allies(player, viewer)

    def _prepare_report(self):
        """
        Compose the report (ui/battle_screen_panels.py) from the final result, once: at
        the splash's start, or on the report's first frame (report-only mode, no splash).
        """
        result = self.battle_result or {}
        won = self.current_player_won
        # No army survived (a perfect tie): neither side's victory
        if (self.report_snapshot is None and (self.winner is None or self.winner < 0)
                and not result.get('attacker_survivors') and not result.get('defender_survivors')):
            won = None
        view = battle_screen_panels.report_view(
            map_data.get_display_name(self.territory), won,
            result.get('unit_breakdown', {}), self.outcome, self._is_ours,
            strengths=self._report_strengths())
        header, body = battle_screen_panels.compose_report(
            view, self._report_width(), self.report_fonts, self.scale)
        self._report_parts = (header, body)
        self._layout_report(header.get_height() + body.get_height())
        # Centred on the board when it has room to spare; taller than the largest panel,
        # the body scrolls under the header (handle_wheel)
        content = self.report_content_rect
        top = content.top + max(0, (content.height - header.get_height() - body.get_height()) // 2)
        self._report_header_pos = (content.left, top)
        room = pygame.Rect(content.left, top + header.get_height(), body.get_width(),
                           content.bottom - top - header.get_height())
        self._report_scroller = battle_screen_kit.ScrollView(body, room, self.scale)

    def _report_strengths(self):
        """
        (the viewer's side's strength, the enemy's) for the report's line - the window's
        own numbers for a battle fought here, the stored report's for one opened later
        (None when it has none: an uncontested capture, an older report).
        """
        if self.report_snapshot is not None:
            report = self.report_snapshot
            yours, theirs = report.get('defender_strength'), report.get('attacker_strength')
            return (yours, theirs) if yours is not None and theirs is not None else None
        attacker = getattr(self, 'attacker_strength', None)
        defender = getattr(self, 'defender_strength', None)
        if attacker is None or defender is None:
            return None
        if self.current_player == self.attacker_player or self._is_ours(self.attacker_player):
            return (attacker, defender)
        return (defender, attacker)

    def handle_wheel(self, dy):
        """
        Mouse wheel (pygame MOUSEWHEEL y: + up): the report, or - before and during the
        fight - the side panel under the cursor, when its rows outgrow it.

        Returns:
            bool: True if something moved
        """
        if self.state == BattleInterfaceState.REPORT:
            scroller = self._report_scroller
        elif self.state in (BattleInterfaceState.SETUP, BattleInterfaceState.ANIMATING):
            scroller = next((rows for rect, (_header, rows) in
                             zip((self.attacker_panel_rect, self.defender_panel_rect),
                                 getattr(self, '_sides', ()))
                             if rect.collidepoint(self.mouse_pos)), None)
        else:
            scroller = None
        return scroller.wheel(dy) if scroller is not None else False

    def _render_report(self):
        """Render the REPORT state: the panel, the composed report, Close."""
        # P3 fix: use pre-scaled report panel background
        if self._scaled_report_bg:
            self.screen.blit(self._scaled_report_bg, self.report_panel_rect.topleft)
        elif self.panel_bg:
            self.screen.blit(pygame.transform.smoothscale(
                self.panel_bg, (self.report_panel_rect.width, self.report_panel_rect.height)),
                self.report_panel_rect.topleft)
        else:
            pygame.draw.rect(self.screen, (40, 40, 60), self.report_panel_rect)
            pygame.draw.rect(self.screen, WHITE, self.report_panel_rect, 2)

        if self._report_parts is None:
            self._prepare_report()
        self.screen.blit(self._report_parts[0], self._report_header_pos)
        self._report_scroller.draw(self.screen)

        # Close button
        self._render_button(self.close_button_rect, "Close", 'close')

    def render(self):
        """Render the current state of the interface."""
        # Always render overlay first
        self._render_overlay()

        # Render based on state
        if self.state == BattleInterfaceState.SETUP:
            self._render_setup()
        elif self.state == BattleInterfaceState.ANIMATING:
            self._render_animating()
        elif self.state == BattleInterfaceState.SPLASH:
            self._render_splash()
        elif self.state == BattleInterfaceState.REPORT:
            self._render_report()

    def is_finished(self):
        """Check if interface should close."""
        return self.is_finished_flag

    def get_battle_result(self):
        """
        Get the pre-calculated battle result.

        Returns:
            dict with 'winner', 'attacker_survivors', 'defender_survivors', etc.
            or None if battle hasn't been resolved yet.
        """
        return self.battle_result
