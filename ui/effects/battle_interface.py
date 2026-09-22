"""
Enhanced Battle Interface

A cinematic multi-phase battle interface featuring:
- Side-by-side attacker/defender panels with BattlePlayerScreen.png backgrounds
- Strength comparison bars with particle combat animation
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

from config.constants import WINDOW_WIDTH, WINDOW_HEIGHT, WHITE, BLACK
from utils.logger import get_logger
from utils.surface_utils import crop_to_opaque
from utils.colors import lighten_color

logger = get_logger(__name__)

# ========================================
# CONSTANTS
# ========================================

# Overlay darkness (semi-transparent black)
OVERLAY_ALPHA = 180

# Reference resolution for scaling (all pixel values tuned for this)
REFERENCE_WIDTH = 1600
REFERENCE_HEIGHT = 900

# Panel layout (values are for reference resolution, will be scaled)
PANEL_GAP_REF = 120  # Gap between panels for battle icon and button
PANEL_WIDTH_RATIO = 0.35  # Each panel takes 35% of screen width
PANEL_HEIGHT_RATIO = 0.55  # Panel height as ratio of screen height
PANEL_TOP_MARGIN_REF = 105  # Top margin for panels
PANEL_CONTENT_PADDING_V_REF = 80  # Vertical (top) padding inside panels (reduced from 100 for 5 unit types)
PANEL_CONTENT_PADDING_H_REF = 95  # Horizontal (left/right) padding for text breathing room

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

# Button dimensions (reference resolution)
RESOLVE_BUTTON_WIDTH_REF = 180
RESOLVE_BUTTON_HEIGHT_REF = 50
CLOSE_BUTTON_WIDTH_REF = 150
CLOSE_BUTTON_HEIGHT_REF = 45

# Animation timing
# Bounds the volley schedule is clamped into (the duration is derived from the
# volley count, not drawn directly)
ANIMATION_MIN_DURATION = 2.0  # Minimum animation duration (seconds)
ANIMATION_MAX_DURATION = 6.0  # Maximum animation duration (seconds)

# Splash timing (seconds)
SPLASH_GROW_DURATION = 0.5
SPLASH_HOLD_DURATION = 2.0
SPLASH_SHRINK_DURATION = 0.5
SPLASH_TARGET_SCALE = 0.75  # 75% of original size

# Volley settings - each volley is one blast per side, and each hit removes a
# visible chunk of the target bar (BFME2 auto-resolve style)
VOLLEY_MIN = 3  # Fewest volleys, however small the skirmish
VOLLEY_MAX = 14  # Cap so huge stacks do not trade blows forever
VOLLEY_SIZE_LOG_COEFF = 1.6  # volleys = 2 + coeff * ln(total armies), then clamped
VOLLEY_INTERVAL_MIN = 0.28  # Seconds between volleys (clamped to fit the duration window)
VOLLEY_INTERVAL_MAX = 0.42
VOLLEY_STAGGER_MIN = 0.06  # Offset between the two sides' shots within one volley
VOLLEY_STAGGER_MAX = 0.14
VOLLEY_LEAD_IN = 0.35  # Pause before the first shot
VOLLEY_TAIL = 0.60  # Pause after the last hit settles
CHUNK_JITTER_MIN = 0.6  # Per-volley damage weight, normalised so chunks sum exactly
CHUNK_JITTER_MAX = 1.4

# Travelling blast (one streak per shot, not a stream)
PROJECTILE_TRAVEL = 0.10  # Seconds to cross the gap
PROJECTILE_LENGTH_REF = 130  # Streak length at reference resolution
PROJECTILE_THICKNESS_REF = 10

# Impact burst
FLASH_DURATION = 0.22  # Seconds the burst is visible
FLASH_SIZE_REF = 90  # Burst sprite size at reference resolution
FLASH_FRAMES = 6  # Pre-rendered frames per side
FLASH_SPIKES = 8  # Radiating spikes per burst
FLASH_GLOW_RINGS = 5  # Concentric rings faking a radial gradient

# Hit reaction on the struck bar
BURN_DURATION = 0.13  # Seconds the doomed chunk glows white-hot before vanishing
FRAME_GLOW_DURATION = 0.30  # Seconds the bar frame keeps flaring
FRAME_GLOW_INTENSITY = 0.55  # How hard the flare brightens the frame artwork

# Bar background (empty portion of a strength bar)
DARK_GRAY = (60, 60, 60)

# Text settings (reference resolution)
TEXT_LINE_HEIGHT_REF = 34  # Vertical spacing between lines (reduced from 38 for 5 unit types)
TEXT_PADDING_REF = 20  # Padding for fallback (not BattlePlayerScreen)
REPORT_LINE_SPACING_REF = 5  # Extra spacing in battle report (reduced from 8 for 5 unit types)


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

    Instead of both bars sliding continuously to their final value, each side
    fires a discrete blast at the other. When a blast lands, the chunk of the
    target bar it destroyed flashes white-hot in place and then burns away, so
    the bar depletes in visible steps - one step per hit.

    The two bars are mirrored: the attacker bar is anchored at its left edge and
    the defender bar at its right edge, so both erode inward toward the centre.

    The whole schedule (how many volleys, when each one fires, how big each
    chunk is) is built once in __init__ from a seeded private RNG, so the
    animation is identical on every client in multiplayer. The chunk sizes are
    normalised to sum exactly to the damage each side takes, so the bars always
    land precisely on their final fill.
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
                 attacker_count=0, defender_count=0):
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
            ui_scale: Scale factor for sprite sizes
            attacker_count: Attacker army count (drives how many volleys are fired)
            defender_count: Defender army count (drives how many volleys are fired)

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
                'burn': None,            # {'t0', 'chunk'} - chunk burning white-hot
                'flash': None,           # {'t0', 'x', 'y'} - impact burst
                'glow_t0': None,         # frame flare start time
                'lance': None,           # sprite this side FIRES (own colour)
                'flash_frames': [],      # sprites for hits taken (attacker colour)
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
                'flash': None,
                'glow_t0': None,
                'lance': None,
                'flash_frames': [],
                'glow': None,
            },
        ]

        # Pre-render every sprite once. A blast fired BY a side carries that
        # side's colour, so the flashes a side RECEIVES are tinted with its
        # opponent's colour.
        for i, side in enumerate(self.sides):
            other = self.sides[1 - i]
            side['lance'] = self._build_lance_sprite(side['color'], side['anchor_right'])
            side['flash_frames'] = self._build_flash_sprites(other['color'])
            side['glow'] = self._build_frame_glow_sprite(side['border'], other['color'])

        self.elapsed = 0.0
        self.is_complete = False
        self.volleys = []
        self.duration = ANIMATION_MIN_DURATION

        self._build_schedule(attacker_final_fill, defender_final_fill)

    # ------------------------------------------------------------------
    # Schedule construction
    # ------------------------------------------------------------------

    def _build_schedule(self, attacker_final_fill, defender_final_fill):
        """
        Build the deterministic volley schedule.

        Uses a private random.Random so it never disturbs the global RNG that
        game logic draws from. Re-running it with the same seed reproduces the
        identical timing, which is what retarget() relies on.

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
        count = max(VOLLEY_MIN, min(VOLLEY_MAX, count))

        # Pick the gap between volleys, then clamp it so the resulting total
        # duration stays inside the allowed window for any volley count.
        interval = rng.uniform(VOLLEY_INTERVAL_MIN, VOLLEY_INTERVAL_MAX)
        fixed = VOLLEY_LEAD_IN + VOLLEY_TAIL
        min_interval = (ANIMATION_MIN_DURATION - fixed) / count
        max_interval = (ANIMATION_MAX_DURATION - fixed) / count
        interval = max(min_interval, min(max_interval, interval))
        self.duration = fixed + count * interval

        # Split each side's damage into chunks that sum exactly to the damage.
        atk_chunks = self._split_damage(
            rng, self.sides[self.ATTACKER]['initial'] - attacker_final_fill, count)
        def_chunks = self._split_damage(
            rng, self.sides[self.DEFENDER]['initial'] - defender_final_fill, count)
        self.sides[self.ATTACKER]['chunks'] = atk_chunks
        self.sides[self.DEFENDER]['chunks'] = def_chunks

        # Build the shot list. Each volley is two shots - one per side - fired
        # a fraction of a second apart so the hits interleave rather than
        # landing on top of each other.
        self.volleys = []
        for i in range(count):
            base_t = VOLLEY_LEAD_IN + i * interval
            stagger = rng.uniform(VOLLEY_STAGGER_MIN, VOLLEY_STAGGER_MAX)
            attacker_leads = rng.random() < 0.5

            atk_fire = base_t if attacker_leads else base_t + stagger
            def_fire = base_t + stagger if attacker_leads else base_t

            # A shot fired by the attacker damages the defender, and vice versa.
            self.volleys.append(self._make_shot(self.ATTACKER, self.DEFENDER,
                                                atk_fire, def_chunks[i]))
            self.volleys.append(self._make_shot(self.DEFENDER, self.ATTACKER,
                                                def_fire, atk_chunks[i]))

        self.volleys.sort(key=lambda v: v['fire_t'])

    @staticmethod
    def _make_shot(shooter, target, fire_t, chunk):
        """
        Build one shot record.

        Args:
            shooter: Side index firing the blast
            target: Side index taking the hit
            fire_t: Time (seconds into the animation) the lance leaves the bar
            chunk: Fill ratio this hit removes from the target

        Returns:
            Shot dict
        """
        return {
            'shooter': shooter,
            'target': target,
            'fire_t': fire_t,
            'land_t': fire_t + PROJECTILE_TRAVEL,
            'chunk': chunk,
            'fired': False,
            'landed': False,
            'start_x': 0.0,   # filled in at fire time
            'end_x': 0.0,
        }

    @staticmethod
    def _split_damage(rng, damage, count):
        """
        Split a total damage amount into `count` jittered chunks.

        The chunks are normalised so they sum to exactly `damage`, which is what
        lets the bar land precisely on its final fill instead of drifting.

        Args:
            rng: random.Random instance
            damage: Total fill ratio to remove (may be 0 or negative)
            count: Number of chunks

        Returns:
            List of chunk sizes
        """
        if count <= 0:
            return []
        # Draw the weights unconditionally so the RNG stream advances by the
        # same number of steps regardless of damage - retarget() depends on it.
        weights = [rng.uniform(CHUNK_JITTER_MIN, CHUNK_JITTER_MAX) for _ in range(count)]
        if damage <= 0:
            return [0.0] * count
        total = sum(weights)
        chunks = [damage * w / total for w in weights]
        # Fold any float residue into the last chunk
        chunks[-1] += damage - sum(chunks)
        return chunks

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
    # Sprite pre-rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _lerp_color(a, b, t):
        """
        Blend between two RGB colours.

        utils.colors.lighten_color is multiplicative, so it barely moves a dark
        player colour toward white. These blasts need a true linear blend.

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

    def _build_lance_sprite(self, color, fires_left):
        """
        Pre-render the travelling blast as a tapered, motion-blurred streak.

        Built once per side at init, then blitted - nothing is drawn per frame.

        Args:
            color: RGB tuple of the firing player
            fires_left: True if this side shoots right-to-left (the defender)

        Returns:
            pygame.Surface with per-pixel alpha, head pointing in travel direction
        """
        length = max(8, int(PROJECTILE_LENGTH_REF * self.ui_scale))
        thickness = max(3, int(PROJECTILE_THICKNESS_REF * self.ui_scale))
        surf = pygame.Surface((length, thickness), pygame.SRCALPHA)

        # Build it pointing right: faint, thin tail at x=0 growing into a hot,
        # white-tipped head at x=length-1.
        for x in range(length):
            p = x / max(1, length - 1)
            alpha = int(255 * (p ** 1.6))
            # Whiten only the last few pixels - a gentler curve here washed the
            # whole streak out and both sides' blasts looked identical.
            col = self._lerp_color(color, WHITE, p ** 8)
            height = max(1, int(thickness * (0.35 + 0.65 * p)))
            top = (thickness - height) // 2
            pygame.draw.line(surf, (*col, alpha), (x, top), (x, top + height - 1))

        if fires_left:
            surf = pygame.transform.flip(surf, True, False)
        return surf

    def _build_flash_sprites(self, color):
        """
        Pre-render the impact burst as a short sprite sequence.

        Frame 0 is the bright, tight burst; the last frame is the faded, spread
        remnant. Same pre-rendered-frames approach as ProductionGlowEffect.

        Args:
            color: RGB tuple of the player whose blast lands here

        Returns:
            List of FLASH_FRAMES pygame.Surfaces with per-pixel alpha
        """
        size = max(12, int(FLASH_SIZE_REF * self.ui_scale))
        centre = size // 2
        spike_color = lighten_color(color, 0.5)
        frames = []

        for frame in range(FLASH_FRAMES):
            p = frame / max(1, FLASH_FRAMES - 1)   # 0 at impact, 1 at the end
            fade = (1.0 - p) ** 1.6
            surf = pygame.Surface((size, size), pygame.SRCALPHA)

            # Soft radial glow in the shooter's colour. pygame.draw does not
            # blend onto SRCALPHA, it overwrites - so draw the widest, faintest
            # ring first and work inward to build a stepped gradient.
            glow_radius = size * (0.22 + 0.34 * p)
            for ring in range(FLASH_GLOW_RINGS, 0, -1):
                r = int(glow_radius * ring / FLASH_GLOW_RINGS)
                if r < 1:
                    continue
                ring_alpha = int(200 * fade * (1.0 - (ring - 1) / FLASH_GLOW_RINGS))
                if ring_alpha > 0:
                    pygame.draw.circle(surf, (*color, ring_alpha), (centre, centre), r)

            # Radiating spikes, lengthening and thinning as the burst expands
            spike_len = size * (0.34 + 0.26 * p)
            spike_width = max(1, int((1.0 - p * 0.6) * 3 * self.ui_scale))
            spike_alpha = int(220 * fade)
            if spike_alpha > 0:
                for s in range(FLASH_SPIKES):
                    angle = 2 * math.pi * s / FLASH_SPIKES
                    ex = centre + math.cos(angle) * spike_len
                    ey = centre + math.sin(angle) * spike_len
                    pygame.draw.line(surf, (*spike_color, spike_alpha),
                                     (centre, centre), (int(ex), int(ey)), spike_width)

            # White-hot core, shrinking as it cools
            core_radius = max(1, int(size * 0.10 * (1.0 - p * 0.8)))
            core_alpha = int(255 * fade)
            if core_alpha > 0:
                pygame.draw.circle(surf, (255, 255, 255, core_alpha),
                                   (centre, centre), core_radius)

            frames.append(surf)

        return frames

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

        This is where incoming blasts land and where chunks burn away.

        Args:
            side: Side dict
            fill: Fill ratio 0.0-1.0

        Returns:
            float x coordinate
        """
        rect = side['rect']
        width = rect.width * max(0.0, min(1.0, fill))
        if side['anchor_right']:
            return rect.right - width
        return rect.left + width

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

    def _muzzle_x(self, side):
        """
        X coordinate a side's blasts are fired from (its inner bar edge).

        Args:
            side: Side dict

        Returns:
            float x coordinate
        """
        rect = side['rect']
        return rect.left if side['anchor_right'] else rect.right

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

        Args:
            delta_time: Time since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Fire and land shots that have come due
        for shot in self.volleys:
            if not shot['fired'] and self.elapsed >= shot['fire_t']:
                shot['fired'] = True
                shooter = self.sides[shot['shooter']]
                target = self.sides[shot['target']]
                shot['start_x'] = self._muzzle_x(shooter)
                # Aim at where the target's fill tip is right now and hold that
                # point for the flight, so the lance does not chase the bar.
                shot['end_x'] = self._fill_tip_x(target, target['current'])

            if shot['fired'] and not shot['landed'] and self.elapsed >= shot['land_t']:
                shot['landed'] = True
                target = self.sides[shot['target']]
                # A second hit arriving mid-burn settles the first one, so no
                # chunk is ever silently dropped.
                self._settle_burn(target)
                target['burn'] = {'t0': shot['land_t'], 'chunk': shot['chunk']}
                target['flash'] = {'t0': shot['land_t'],
                                   'x': shot['end_x'],
                                   'y': self.fill_y + target['rect'].height / 2}
                target['glow_t0'] = shot['land_t']

        # Close burns whose window has elapsed, and expire flashes/glows
        for side in self.sides:
            burn = side['burn']
            if burn is not None and self.elapsed - burn['t0'] >= BURN_DURATION:
                self._settle_burn(side)
            if side['flash'] is not None and self.elapsed - side['flash']['t0'] >= FLASH_DURATION:
                side['flash'] = None
            if side['glow_t0'] is not None and self.elapsed - side['glow_t0'] >= FRAME_GLOW_DURATION:
                side['glow_t0'] = None

        if self.elapsed >= self.duration:
            self._finish()

    def _finish(self):
        """Settle everything and snap both bars exactly onto their final fill."""
        for side in self.sides:
            self._settle_burn(side)
            side['current'] = side['final']
            side['flash'] = None
            side['glow_t0'] = None
        self.is_complete = True

    def skip(self):
        """
        Jump straight to the end of the animation.

        Used by the click/Space skip so a player can cut a long battle short.
        """
        self.elapsed = self.duration
        for shot in self.volleys:
            shot['fired'] = True
            shot['landed'] = True
        self._finish()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, screen):
        """
        Render both bars, the blasts in flight and the impacts.

        Nothing is allocated per frame: the fills and the burning chunk are
        drawn straight to the screen, and the lances, frame flares and impact
        bursts are all sprites pre-rendered in __init__.

        Args:
            screen: pygame.Surface to render to
        """
        # 1. Bar backgrounds and the surviving fill
        for side in self.sides:
            rect = side['rect']
            pygame.draw.rect(screen, DARK_GRAY,
                             pygame.Rect(rect.left, self.fill_y, rect.width, rect.height))
            if side['current'] > 0:
                pygame.draw.rect(screen, side['color'],
                                 self._fill_rect(side, side['current']))

        # 2. The chunk currently burning away: white-hot, cooling to empty
        for side in self.sides:
            burn = side['burn']
            if burn is None or burn['chunk'] <= 0:
                continue
            p = max(0.0, min(1.0, (self.elapsed - burn['t0']) / BURN_DURATION))
            chunk_rect = self._chunk_rect(
                side, side['current'] - burn['chunk'], side['current'])
            if chunk_rect.width > 0:
                pygame.draw.rect(screen, self._lerp_color(WHITE, DARK_GRAY, p), chunk_rect)

        # 3. Lances in flight. Drawn BEFORE the frame so the tail, which is
        #    still inside the firing bar at launch, is hidden by the frame's
        #    solid end cap instead of poking out over it.
        for shot in self.volleys:
            if not shot['fired'] or shot['landed']:
                continue
            p = max(0.0, min(1.0, (self.elapsed - shot['fire_t']) / PROJECTILE_TRAVEL))
            x = shot['start_x'] + (shot['end_x'] - shot['start_x']) * p
            shooter = self.sides[shot['shooter']]
            sprite = shooter['lance']
            # Anchor the sprite's head on the travelling point; the tail trails
            # back toward the bar that fired it.
            sprite_x = x if shooter['anchor_right'] else x - sprite.get_width()
            sprite_y = self.fill_y + (shooter['rect'].height - sprite.get_height()) / 2

            # Clip to everything beyond the muzzle. At launch the tail is still
            # inside the firing bar, and without this it renders as a streak
            # lying across the bar's own fill.
            muzzle = int(self._muzzle_x(shooter))
            screen_rect = screen.get_rect()
            if shooter['anchor_right']:
                clip = pygame.Rect(0, 0, muzzle, screen_rect.height)
            else:
                clip = pygame.Rect(muzzle, 0, screen_rect.width - muzzle, screen_rect.height)
            previous_clip = screen.get_clip()
            screen.set_clip(clip.clip(screen_rect))
            screen.blit(sprite, (int(sprite_x), int(sprite_y)))
            screen.set_clip(previous_clip)

        # 4. Decorative frame (defender's copy is mirrored)
        png_offset_y = (self.attacker_rect.height - self.bar_png_height) // 2
        for side in self.sides:
            rect = side['rect']
            if side['border']:
                png_x = rect.centerx - self.bar_png_width // 2
                screen.blit(side['border'], (png_x, rect.top + png_offset_y))
            else:
                pygame.draw.rect(screen, WHITE, rect, BAR_BORDER_WIDTH)

        # 5. Frame flare on a bar that was just hit - a hot copy of the frame
        #    laid over the normal one at the exact same position.
        for side in self.sides:
            if side['glow_t0'] is None or side['glow'] is None:
                continue
            p = max(0.0, min(1.0, (self.elapsed - side['glow_t0']) / FRAME_GLOW_DURATION))
            fade = (1.0 - p) ** 1.5
            sprite = side['glow']
            # pygame multiplies surface alpha with per-pixel alpha, so one hot
            # copy covers every fade level. Pre-rendering a frame per step cost
            # ~21 ms up front, a visible hitch when the battle starts. The alpha
            # is set unconditionally on every blit, so the sprite never carries
            # a stale value.
            sprite.set_alpha(int(255 * fade))
            rect = side['rect']
            png_x = rect.centerx - self.bar_png_width // 2
            screen.blit(sprite, (png_x, rect.top + png_offset_y))

        # 6. Impact bursts
        for side in self.sides:
            flash = side['flash']
            if flash is None:
                continue
            p = max(0.0, min(1.0, (self.elapsed - flash['t0']) / FLASH_DURATION))
            frames = side['flash_frames']
            if not frames:
                continue
            index = min(len(frames) - 1, int(p * len(frames)))
            sprite = frames[index]
            screen.blit(sprite, (int(flash['x'] - sprite.get_width() / 2),
                                 int(flash['y'] - sprite.get_height() / 2)))

    def is_finished(self):
        """Check if animation is complete."""
        return self.is_complete


# ========================================
# ENHANCED BATTLE INTERFACE
# ========================================

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
        self.is_finished_flag = False

        # Pre-calculated battle result (populated when Resolve is clicked)
        self.battle_result = None
        self.animation_duration = 0.0
        self.animation_seed = None

        # Sub-effects
        self.particle_effect = None
        self.splash_effect = None

        # UI state
        self.mouse_pos = (0, 0)
        self.clicked_button = None

        # Load assets
        self._load_assets()

        # Calculate layout
        self._calculate_layout()
        # Both of the above are battle-data free, and _calculate_layout() is the only
        # producer of report_panel_rect / close_button_rect / _scaled_report_bg and the
        # text metrics _render_report() needs, so report-only mode still runs them.

        if report_snapshot is not None:
            self._apply_report_snapshot(report_snapshot)
        else:
            # Extract battle data for display
            self._extract_battle_data()

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

        try:
            # Panel background
            self.panel_bg = pygame.image.load("assets/BattlePlayerScreen.png").convert_alpha()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattlePlayerScreen.png: {e}")
            self.panel_bg = None

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
            # Button background
            btn_full = pygame.image.load("assets/CampaignBTN.png").convert_alpha()
            # Crop to opaque content
            self.button_bg = crop_to_opaque(btn_full, threshold=128)
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load CampaignBTN.png: {e}")
            self.button_bg = None

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
        self.title_font = self.font_manager.get_bold_font(int(24 * ui_scale))
        self.text_font = self.font_manager.get_font(int(16 * ui_scale))
        self.small_font = self.font_manager.get_font(int(14 * ui_scale))
        self.button_font = self.font_manager.get_font(int(14 * ui_scale))  # Smaller button text

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
        self.panel_content_padding_v = s(PANEL_CONTENT_PADDING_V_REF)
        self.panel_content_padding_h = s(PANEL_CONTENT_PADDING_H_REF)
        self.bar_fill_height = s(BAR_FILL_HEIGHT_REF)
        self.bar_png_height = s(BAR_PNG_HEIGHT_REF)
        self.bar_top_margin = s(BAR_TOP_MARGIN_REF)
        self.bar_fill_offset = int(BAR_FILL_OFFSET_REF * self.scale)  # Keep sign
        resolve_button_width = s(RESOLVE_BUTTON_WIDTH_REF)
        resolve_button_height = s(RESOLVE_BUTTON_HEIGHT_REF)
        close_button_width = s(CLOSE_BUTTON_WIDTH_REF)
        close_button_height = s(CLOSE_BUTTON_HEIGHT_REF)
        self.text_line_height = s(TEXT_LINE_HEIGHT_REF)
        self.text_padding = s(TEXT_PADDING_REF)
        self.report_line_spacing = s(REPORT_LINE_SPACING_REF)

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
            # Resolve button positioned below battle icon (reduced gap)
            button_y = icon_y + self.battle_icon.get_height() + s(8)
        else:
            self.battle_icon_pos = (gap_center_x, panel_top_margin + s(50))
            self.icon_center_y = panel_top_margin + s(80)
            button_y = panel_top_margin + s(130)

        # Resolve button (below battle icon in gap)
        self.resolve_button_rect = pygame.Rect(
            gap_center_x - resolve_button_width // 2,
            button_y,
            resolve_button_width,
            resolve_button_height
        )

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

        # Report panel (centered, used in REPORT state)
        report_width = int(self.screen_width * 0.4)
        report_height = int(self.screen_height * 0.6)
        self.report_panel_rect = pygame.Rect(
            (self.screen_width - report_width) // 2,
            (self.screen_height - report_height) // 2,
            report_width,
            report_height
        )

        # Close button (bottom of report panel)
        self.close_button_rect = pygame.Rect(
            self.report_panel_rect.centerx - close_button_width // 2,
            self.report_panel_rect.bottom - close_button_height - s(20),
            close_button_width,
            close_button_height
        )

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
        self._scaled_report_bg = None
        if self.panel_bg:
            self._scaled_panel_bg = pygame.transform.smoothscale(
                self.panel_bg, (self.attacker_panel_rect.width, self.attacker_panel_rect.height))
            self._scaled_report_bg = pygame.transform.smoothscale(
                self.panel_bg, (self.report_panel_rect.width, self.report_panel_rect.height))

    def _extract_battle_data(self):
        """Extract battle information for display."""
        battle = self.game_state.pending_battles[self.battle_index]

        self.territory = battle.territory

        # Identify attacker and defenders
        # Attacker is the player who moved into the territory (not the original owner)
        original_owner = battle.original_owner

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
                    unit_avg_levels=atk_avg_levels
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
                    unit_avg_levels=def_avg_levels
                )
                self.defender_strength = base_strength + (self.keep_bonus if self.has_keep else 0)
            else:
                self.defender_strength = self.keep_bonus if self.has_keep else 0.0
        else:
            # Fallback to simple army counts
            self.attacker_strength = float(self.attacker_count)
            self.defender_strength = float(self.defender_count) + (self.keep_bonus if self.has_keep else 0)

        # Calculate bar fill proportions
        if self.attacker_strength >= self.defender_strength and self.attacker_strength > 0:
            self.attacker_fill = 1.0
            self.defender_fill = self.defender_strength / self.attacker_strength if self.attacker_strength > 0 else 0.0
        elif self.defender_strength > 0:
            self.defender_fill = 1.0
            self.attacker_fill = self.attacker_strength / self.defender_strength
        else:
            self.attacker_fill = 0.5
            self.defender_fill = 0.5

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
        battle = self.game_state.pending_battles[self.battle_index]

        # Generate deterministic seed for animation (for multiplayer sync)
        # Use battle territory name and turn number for reproducibility
        seed_str = f"{battle.territory}_{self.game_state.turn_number}"
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
            defender_count=self.defender_count
        )

        # The duration now falls out of the volley schedule rather than being
        # drawn up front, so adopt it - update() times the post-animation hold
        # against self.animation_duration.
        self.animation_duration = self.particle_effect.duration

    def _start_splash(self):
        """Start the victory/defeat splash animation."""
        self.state = BattleInterfaceState.SPLASH
        self.elapsed = 0.0

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
                                  defender_survivors: int, surviving_units: list = None):
        """
        Update the battle result with actual values from game_state.resolve_battle().

        This replaces the pre-calculated estimates with the real battle outcome.
        Should be called immediately after game_state.resolve_battle().

        Args:
            winner: Actual winner player index
            attacker_survivors: Actual number of attacker survivors
            defender_survivors: Actual number of defender survivors
            surviving_units: List of surviving unit dicts with 'type' key
        """
        # Update internal survivor counts
        self.winner = winner
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
            str or None: 'resolve', 'close', or None if no button clicked
        """
        if self.state == BattleInterfaceState.SETUP:
            if self.resolve_button_rect.collidepoint(pos):
                self._pre_calculate_battle_result()
                self._start_animation()
                return 'resolve'

        elif self.state == BattleInterfaceState.ANIMATING:
            # Clicking anywhere cuts a long battle short
            if self.skip_animation():
                return 'skip'

        elif self.state == BattleInterfaceState.REPORT:
            if self.close_button_rect.collidepoint(pos):
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

    def _wrap_text(self, text, font, max_width):
        """
        Wrap text to fit within max_width, returning list of lines.

        Tries to break on word boundaries first, then character boundaries
        if a single word is too long.

        Args:
            text: Text string to wrap
            font: pygame.Font to measure with
            max_width: Maximum width in pixels

        Returns:
            List of text lines that fit within max_width
        """
        # First check if text fits as-is
        if font.size(text)[0] <= max_width:
            return [text]

        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            # Check if adding this word would exceed max_width
            test_line = f"{current_line} {word}".strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                # Current line is full, start new line
                if current_line:
                    lines.append(current_line)

                # Check if single word fits
                if font.size(word)[0] <= max_width:
                    current_line = word
                else:
                    # Word too long - break by character
                    current_line = ""
                    for char in word:
                        test = current_line + char
                        if font.size(test)[0] <= max_width:
                            current_line = test
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = char

        # Add remaining text
        if current_line:
            lines.append(current_line)

        return lines if lines else [text]

    def _render_overlay(self):
        """Render the semi-transparent dark overlay."""
        # FPS OPT: Cache overlay surface (avoids fullscreen SRCALPHA alloc every frame)
        if not hasattr(self, '_cached_overlay') or self._cached_overlay.get_size() != (self.screen_width, self.screen_height):
            self._cached_overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
            self._cached_overlay.fill((0, 0, 0, OVERLAY_ALPHA))
        self.screen.blit(self._cached_overlay, (0, 0))

    def _render_panel(self, rect, title, title_color, territory, composition,
                      effective_strength, is_defender=False):
        """
        Render a battle information panel.

        Args:
            rect: pygame.Rect for panel bounds
            title: Player name to display
            title_color: Color for player name
            territory: Territory name
            composition: Dict of unit_type -> count
            effective_strength: Calculated effective strength
            is_defender: If True, show Keep info if applicable
        """
        # P3 fix: use pre-scaled panel background instead of smoothscale per frame
        if self._scaled_panel_bg:
            self.screen.blit(self._scaled_panel_bg, rect.topleft)
        elif self.panel_bg:
            self.screen.blit(pygame.transform.smoothscale(self.panel_bg, (rect.width, rect.height)), rect.topleft)
        else:
            # Fallback solid color
            pygame.draw.rect(self.screen, (40, 40, 60), rect)
            pygame.draw.rect(self.screen, WHITE, rect, 2)

        # Content area with separate H/V padding for BattlePlayerScreen.png
        padding_h = self.panel_content_padding_h if self.panel_bg else self.text_padding
        padding_v = self.panel_content_padding_v if self.panel_bg else self.text_padding
        content_x = rect.left + padding_h
        content_width = rect.width - padding_h * 2
        y = rect.top + padding_v

        # Player name (colored) - wrap if too long
        name_lines = self._wrap_text(title, self.title_font, content_width)
        for line in name_lines:
            name_surface = self.title_font.render(line, True, title_color)
            name_rect = name_surface.get_rect(centerx=rect.centerx, top=y)
            self.screen.blit(name_surface, name_rect)
            y += self.text_line_height
        y += int(5 * self.scale)  # Extra spacing after name

        # Territory
        territory_text = f"Territory: {territory}"
        territory_surface = self.text_font.render(territory_text, True, WHITE)
        self.screen.blit(territory_surface, (content_x, y))
        y += self.text_line_height

        # Army Composition header
        comp_header = self.text_font.render("Army Composition:", True, WHITE)
        self.screen.blit(comp_header, (content_x, y))
        y += self.text_line_height - int(5 * self.scale)

        # Separator line
        pygame.draw.line(self.screen, WHITE,
                        (content_x, y),
                        (content_x + content_width, y),
                        1)
        y += int(12 * self.scale)

        # Unit counts
        if composition:
            for unit_type, count in sorted(composition.items()):
                unit_text = f"{count} {unit_type}"
                unit_surface = self.small_font.render(unit_text, True, WHITE)
                self.screen.blit(unit_surface, (content_x + int(10 * self.scale), y))
                y += self.text_line_height - int(10 * self.scale)  # Tighter spacing for 5 unit types
        else:
            no_units = self.small_font.render("No units", True, (150, 150, 150))
            self.screen.blit(no_units, (content_x + int(10 * self.scale), y))
            y += self.text_line_height - int(10 * self.scale)

        # Keep indicator (defender only)
        if is_defender and self.has_keep:
            y += int(8 * self.scale)
            keep_text = f"Territory has a Keep. (+{self.keep_bonus})"
            keep_surface = self.small_font.render(keep_text, True, (255, 200, 100))
            self.screen.blit(keep_surface, (content_x + int(10 * self.scale), y))
            y += self.text_line_height

        # Effective Strength
        y += 12
        strength_text = f"Effective Strength: {effective_strength:.1f}"
        strength_surface = self.text_font.render(strength_text, True, WHITE)
        self.screen.blit(strength_surface, (content_x, y))

    def _render_button(self, rect, text, bg_image=None):
        """
        Render a button with hover/click effects.

        Args:
            rect: pygame.Rect for button bounds
            text: Text to display on button
            bg_image: Optional background image
        """
        is_hovering = rect.collidepoint(self.mouse_pos)

        if bg_image:
            # FPS OPT: Cache scaled+darkened base button image (avoids smoothscale+copy+Surface every frame)
            if not hasattr(self, '_button_base_cache'):
                self._button_base_cache = {}
            btn_key = (id(bg_image), rect.width, rect.height)
            if btn_key not in self._button_base_cache:
                scaled_img = pygame.transform.smoothscale(bg_image, (rect.width, rect.height))
                darkened = scaled_img.copy()
                dark_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                dark_surface.fill((100, 100, 100, 255))
                darkened.blit(dark_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                self._button_base_cache[btn_key] = darkened

            if is_hovering:
                # Only .copy() + brighten for the hovered button (rare — 1 at a time)
                modified_img = self._button_base_cache[btn_key].copy()
                bright_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                bright_surface.fill((40, 40, 40, 0))
                modified_img.blit(bright_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
                self.screen.blit(modified_img, rect.topleft)
            else:
                # FPS OPT: Blit directly from cache — no .copy() needed
                self.screen.blit(self._button_base_cache[btn_key], rect.topleft)
        else:
            # Fallback solid color button
            color = (80, 80, 120) if not is_hovering else (100, 100, 150)
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, WHITE, rect, 2)

        # FPS OPT: Cache button text render (avoids font.render() every frame)
        if not hasattr(self, '_button_text_cache'):
            self._button_text_cache = {}
        if text not in self._button_text_cache:
            self._button_text_cache[text] = self.button_font.render(text, True, WHITE)
        text_surface = self._button_text_cache[text]
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def _render_pulsed_icon(self):
        """
        Draw the pulsing battle icon between the two panels.

        The pulse used to smoothscale the icon on every single frame in both the
        SETUP and ANIMATING states. The scale is quantised to
        ICON_PULSE_SCALE_STEPS steps and the results cached, so each distinct
        size is only ever built once. Shared by both states so the two copies
        cannot drift apart.
        """
        if not self.battle_icon or self.battle_icon_base_w <= 0:
            return

        # Calculate pulse scale using sine wave for smooth animation
        pulse_progress = (math.sin(self.elapsed * ICON_PULSE_SPEED * 2 * math.pi) + 1) / 2
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
        self.screen.blit(scaled_icon, (icon_x, icon_y))

    def _render_strength_bars(self):
        """Render the strength comparison bars using BattleBar.png as border."""
        # Calculate fill Y position (offset from bar rect for independent positioning)
        fill_y = self.attacker_bar_rect.top + self.bar_fill_offset

        # Draw bar backgrounds (dark fill area) at offset position
        attacker_fill_rect = pygame.Rect(
            self.attacker_bar_rect.left, fill_y,
            self.attacker_bar_rect.width, self.attacker_bar_rect.height
        )
        defender_fill_rect = pygame.Rect(
            self.defender_bar_rect.left, fill_y,
            self.defender_bar_rect.width, self.defender_bar_rect.height
        )
        pygame.draw.rect(self.screen, DARK_GRAY, attacker_fill_rect)
        pygame.draw.rect(self.screen, DARK_GRAY, defender_fill_rect)

        # Draw fills at offset position. The bars are mirrored - the attacker
        # fills from its left edge, the defender from its right - so both erode
        # inward toward the centre once the volleys start. This must match
        # BattleBarVolleyEffect._fill_rect() or the bar would jump when the
        # animation begins.
        if self.attacker_fill > 0:
            fill_width = int(self.attacker_bar_rect.width * self.attacker_fill)
            fill_rect = pygame.Rect(
                self.attacker_bar_rect.left,
                fill_y,
                fill_width,
                self.attacker_bar_rect.height
            )
            pygame.draw.rect(self.screen, self.attacker_color, fill_rect)

        if self.defender_fill > 0:
            fill_width = int(self.defender_bar_rect.width * self.defender_fill)
            fill_rect = pygame.Rect(
                self.defender_bar_rect.right - fill_width,
                fill_y,
                fill_width,
                self.defender_bar_rect.height
            )
            pygame.draw.rect(self.screen, self.defender_color, fill_rect)

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
        # Render panels
        attacker_name = self.game_state.get_player_name(self.attacker_player) if self.attacker_player is not None else "Unknown"
        self._render_panel(
            self.attacker_panel_rect,
            attacker_name,
            self.attacker_color,
            self.territory,
            self.attacker_composition,
            self.attacker_strength,
            is_defender=False
        )

        defender_name = "Defenders"
        if self.defender_players:
            if len(self.defender_players) == 1:
                defender_name = self.game_state.get_player_name(self.defender_players[0])
            else:
                defender_name = f"{len(self.defender_players)} Defenders"
        self._render_panel(
            self.defender_panel_rect,
            defender_name,
            self.defender_color,
            self.territory,
            self.defender_composition,
            self.defender_strength,
            is_defender=True
        )

        # Render battle icon with pulsation animation
        self._render_pulsed_icon()

        # Render resolve button
        self._render_button(self.resolve_button_rect, "Resolve Battle", self.button_bg)

        # Render strength bars
        self._render_strength_bars()

    def _render_animating(self):
        """Render the ANIMATING state (particle combat)."""
        # Render panels (static during animation)
        attacker_name = self.game_state.get_player_name(self.attacker_player) if self.attacker_player is not None else "Unknown"
        self._render_panel(
            self.attacker_panel_rect,
            attacker_name,
            self.attacker_color,
            self.territory,
            self.attacker_composition,
            self.attacker_strength,
            is_defender=False
        )

        defender_name = "Defenders"
        if self.defender_players:
            if len(self.defender_players) == 1:
                defender_name = self.game_state.get_player_name(self.defender_players[0])
        self._render_panel(
            self.defender_panel_rect,
            defender_name,
            self.defender_color,
            self.territory,
            self.defender_composition,
            self.defender_strength,
            is_defender=True
        )

        # Render battle icon with pulsation animation
        self._render_pulsed_icon()

        # Render particle effect (includes animated bars)
        if self.particle_effect:
            self.particle_effect.render(self.screen)

    def _render_splash(self):
        """Render the SPLASH state (victory/defeat image)."""
        if self.splash_effect:
            self.splash_effect.render(self.screen)

    def _render_report(self):
        """Render the REPORT state (battle summary with unit type breakdown)."""
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

        # Content with separate H/V padding for BattlePlayerScreen.png
        padding_h = self.panel_content_padding_h if self.panel_bg else self.text_padding
        padding_v = self.panel_content_padding_v if self.panel_bg else self.text_padding
        content_x = self.report_panel_rect.left + padding_h
        content_width = self.report_panel_rect.width - padding_h * 2
        y = self.report_panel_rect.top + padding_v
        center_x = self.report_panel_rect.centerx

        # Title
        title = self.title_font.render("Battle Report:", True, WHITE)
        title_rect = title.get_rect(centerx=center_x, top=y)
        self.screen.blit(title, title_rect)
        y += self.text_line_height + self.report_line_spacing

        # Territory name
        territory_text = self.text_font.render(self.territory, True, WHITE)
        territory_rect = territory_text.get_rect(centerx=center_x, top=y)
        self.screen.blit(territory_text, territory_rect)
        y += self.text_line_height + self.report_line_spacing + int(5 * self.scale)

        # Separator
        pygame.draw.line(self.screen, WHITE,
                        (content_x, y),
                        (content_x + content_width, y),
                        1)
        y += int(12 * self.scale)  # Reduced from 15 for 5 unit types

        # Victory/Defeat
        if self.current_player_won:
            result_text = "VICTORY"
            result_color = (100, 255, 100)
        else:
            result_text = "DEFEAT"
            result_color = (255, 100, 100)

        result_surface = self.title_font.render(result_text, True, result_color)
        result_rect = result_surface.get_rect(centerx=center_x, top=y)
        self.screen.blit(result_surface, result_rect)
        y += self.text_line_height + self.report_line_spacing + int(5 * self.scale)

        # Separator
        pygame.draw.line(self.screen, WHITE,
                        (content_x, y),
                        (content_x + content_width, y),
                        1)
        y += int(12 * self.scale)  # Reduced from 15 for 5 unit types

        # Battle summary
        if self.battle_result:
            # "Your Units:" header
            your_units_header = self.text_font.render("Your Units:", True, WHITE)
            self.screen.blit(your_units_header, (content_x, y))
            y += self.text_line_height

            # Unit type breakdown for current player
            unit_breakdown = self.battle_result.get('unit_breakdown', {})
            if unit_breakdown:
                for unit_type, data in sorted(unit_breakdown.items()):
                    lost = data['lost']
                    survived = data['survived']
                    original = data['original']

                    if survived == 0:
                        unit_text = f"  {unit_type}: {lost} lost (all)"
                        text_color = (255, 150, 150)  # Reddish for total loss
                    elif lost == 0:
                        unit_text = f"  {unit_type}: {survived} survived (no losses)"
                        text_color = (150, 255, 150)  # Greenish for no losses
                    else:
                        unit_text = f"  {unit_type}: {lost} lost, {survived} survived"
                        text_color = WHITE

                    unit_surface = self.small_font.render(unit_text, True, text_color)
                    self.screen.blit(unit_surface, (content_x, y))
                    y += self.text_line_height - int(10 * self.scale)  # Tighter spacing for 5 unit types
            else:
                # Fallback if no breakdown available
                no_data = self.small_font.render("  No unit data available", True, (150, 150, 150))
                self.screen.blit(no_data, (content_x, y))
                y += self.text_line_height - int(10 * self.scale)

            # Add spacing before total summary
            y += self.report_line_spacing

            # Total summary line
            if self.current_player == self.attacker_player:
                total_lost = self.battle_result['attacker_lost']
                total_survived = self.battle_result['attacker_survivors']
            else:
                total_lost = self.battle_result['defender_lost']
                total_survived = self.battle_result['defender_survivors']

            total_text = f"Total: {total_lost} lost, {total_survived} survived"
            total_surface = self.text_font.render(total_text, True, WHITE)
            self.screen.blit(total_surface, (content_x, y))

        # Close button
        self._render_button(self.close_button_rect, "Close", self.button_bg)

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
