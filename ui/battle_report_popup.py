# ui/battle_report_popup.py
# On-map Battle Report popups

"""
Battle Report popups: small on-map panels telling a defender what happened in a
battle they never watched.

One popup is anchored over each attacked territory and follows the camera, but its
SIZE is fixed in screen space (game.scale(), not the zoom-driven ui scale factor) so
the text stays readable at every zoom level.

All geometry comes from get_layout(). Drawing and hit-testing both call it, so they
cannot desync - the same rule the unit context menu follows in main.py.
"""

import pygame

from utils.logger import get_logger

logger = get_logger(__name__)


# TransmissionBG.png is a wooden board with feathered (not fully transparent) edges.
# Measured from the source image by alpha threshold: the solid board occupies the
# middle of the surface, so content must be inset against the BOARD, not the surface.
# Note campaign_utils.py documents only left/right/top; there is a bottom margin too.
BOARD_LEFT_FRAC = 0.070
BOARD_RIGHT_FRAC = 0.069
BOARD_TOP_FRAC = 0.201
BOARD_BOTTOM_FRAC = 0.205

BOARD_WIDTH_FRAC = 1.0 - BOARD_LEFT_FRAC - BOARD_RIGHT_FRAC     # 0.861
BOARD_HEIGHT_FRAC = 1.0 - BOARD_TOP_FRAC - BOARD_BOTTOM_FRAC    # 0.594

# Reference sizes at 1600x900 (game.scale() maps these to the current resolution).
# The board art is much wider than it is tall, and the content is not, so the height
# below is what actually drives the size: BOARD_ASPECT then sets the width. Keeping
# these tight is what keeps the popup small, since stretching the board instead would
# visibly squash the wood grain.
BOARD_MIN_WIDTH_REF = 150      # Floor only; the aspect rule normally wins
BOARD_ASPECT = 2.174           # Board w/h measured from the art; never distorted
CONTENT_PAD_REF = 7            # Inset from the board edge to text
TITLE_GAP_REF = 4              # Between the title underline and the first body line
BODY_LINE_REF = 13             # Body line height
BUTTON_GAP_REF = 4             # Between the last body line and the button row
BUTTON_HEIGHT_REF = 20
BUTTON_SPACING_REF = 6         # Between the Detail and Close buttons
ANCHOR_OFFSET_REF = 20         # Gap between the territory centre and the popup

COLOR_DEFENDED = (24, 92, 34)   # Dark green
COLOR_LOST = (140, 30, 30)      # Dark red
COLOR_BODY = (38, 28, 16)       # Dark brown, readable on the wooden board

# Fallback panel colours when TransmissionBG.png cannot be loaded
FALLBACK_FILL = (46, 36, 24, 236)
FALLBACK_BORDER = (180, 160, 100)

# draw_feedback_button() draws a solid rect when it has no bg_image, and passing
# base_color=None there raises "invalid color argument". menu_button_img is None
# whenever GMenuButton.png fails to load, so always hand it a real colour.
BUTTON_FALLBACK_COLOR = (92, 74, 46)


def _plural(count, singular, plural):
    """'1 Unit' vs '3 Units'."""
    return singular if count == 1 else plural


def build_report_lines(report):
    """
    The body lines for a report, left-aligned, in display order.

    Loss:     " - 3 Units Lost" / " - 2 Structures Destroyed" / " - 2 Structures Captured"
    Defended: " - 1 Unit Remaining" / " - 2 Structures Remaining"

    The Captured line only appears when Champion of the People saved Farms/Mines for
    the conqueror -- they are not rubble, but they are still lost to the enemy.
    """
    lines = []
    if report.get('held'):
        units = report.get('units_remaining', 0)
        structures = report.get('structures_remaining', 0)
        lines.append(" - %d %s Remaining" % (units, _plural(units, "Unit", "Units")))
        lines.append(" - %d %s Remaining" % (
            structures, _plural(structures, "Structure", "Structures")))
    else:
        units = report.get('units_lost', 0)
        destroyed = report.get('structures_destroyed', 0)
        captured = report.get('structures_captured', 0)
        lines.append(" - %d %s Lost" % (units, _plural(units, "Unit", "Units")))
        lines.append(" - %d %s Destroyed" % (
            destroyed, _plural(destroyed, "Structure", "Structures")))
        if captured > 0:
            lines.append(" - %d %s Captured" % (
                captured, _plural(captured, "Structure", "Structures")))
    return lines


class BattleReportPopupRenderer:
    """Draws and hit-tests the on-map Battle Report popups."""

    def __init__(self, game):
        self.game = game
        self._bg_raw = None
        self._bg_loaded = False
        self._bg_scaled = None
        self._bg_scaled_size = None

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------

    def invalidate(self):
        """
        Drop the cached scaled background.

        Called on resolution change: the display surface is recreated there, so a
        surface that was convert_alpha()'d against the old one must not be reused.
        """
        self._bg_scaled = None
        self._bg_scaled_size = None

    def _get_background(self, size):
        """Scaled TransmissionBG.png at `size`, or None if the asset is unavailable."""
        if not self._bg_loaded:
            self._bg_loaded = True
            try:
                self._bg_raw = pygame.image.load(
                    'assets/TransmissionBG.png').convert_alpha()
            except (pygame.error, FileNotFoundError, OSError) as exc:
                logger.warning("Battle report background unavailable: %s", exc)
                self._bg_raw = None

        if self._bg_raw is None:
            return None
        if self._bg_scaled is None or self._bg_scaled_size != size:
            self._bg_scaled = pygame.transform.smoothscale(self._bg_raw, size)
            self._bg_scaled_size = size
        return self._bg_scaled

    # ------------------------------------------------------------------
    # Geometry (single source of truth for draw AND hit-test)
    # ------------------------------------------------------------------

    def get_layout(self, report, anchor, bounds):
        """
        Compute every rect for one popup.

        Args:
            report: the snapshot dict
            anchor: (x, y) screen position of the territory centre
            bounds: (left, top, right, bottom) the popup must stay inside (the map band)

        Returns:
            dict with panel_rect, board_rect, detail_rect, close_rect, lines, title
        """
        game = self.game
        scale = game.scale

        lines = build_report_lines(report)

        pad = scale(CONTENT_PAD_REF)
        title_h = game.small_font_bold.get_height()
        body_h = scale(BODY_LINE_REF)
        button_h = scale(BUTTON_HEIGHT_REF)

        board_h = (pad + title_h + scale(TITLE_GAP_REF)
                   + len(lines) * body_h
                   + scale(BUTTON_GAP_REF) + button_h + pad)
        # Width follows the art's own proportions, so the board is scaled uniformly
        # rather than stretched. The floor only matters for an unusually short report.
        board_w = max(scale(BOARD_MIN_WIDTH_REF), int(board_h * BOARD_ASPECT))

        panel_w = int(round(board_w / BOARD_WIDTH_FRAC))
        panel_h = int(round(board_h / BOARD_HEIGHT_FRAC))

        left, top, right, bottom = bounds
        anchor_x, anchor_y = anchor
        offset = scale(ANCHOR_OFFSET_REF)

        # Prefer sitting above the territory; flip below when it would clear the top.
        panel_x = int(anchor_x - panel_w / 2)
        panel_y = int(anchor_y - offset - panel_h)
        if panel_y < top:
            panel_y = int(anchor_y + offset)

        # Clamp into the map band so a popup can never hide under the panels, whose
        # clicks would otherwise be stolen by the Priority 0 handler.
        panel_x = max(left, min(panel_x, right - panel_w))
        panel_y = max(top, min(panel_y, bottom - panel_h))

        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        board_rect = pygame.Rect(
            panel_x + int(panel_w * BOARD_LEFT_FRAC),
            panel_y + int(panel_h * BOARD_TOP_FRAC),
            board_w, board_h)

        button_y = board_rect.bottom - pad - button_h
        button_w = (board_rect.width - 2 * pad - scale(BUTTON_SPACING_REF)) // 2
        detail_rect = pygame.Rect(board_rect.left + pad, button_y, button_w, button_h)
        close_rect = pygame.Rect(board_rect.right - pad - button_w, button_y,
                                 button_w, button_h)

        return {
            'panel_rect': panel_rect,
            'board_rect': board_rect,
            'detail_rect': detail_rect,
            'close_rect': close_rect,
            'lines': lines,
            'title': "DEFENDED" if report.get('held') else "LOST",
            'title_color': COLOR_DEFENDED if report.get('held') else COLOR_LOST,
        }

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, screen, reports, bounds, anchor_for):
        """
        Draw every popup and return its clickable rects.

        Args:
            anchor_for: callable(report) -> (x, y) screen anchor, or None to skip

        Returns:
            [(rect, action, report)] where action is 'detail' or 'close'.
            Built in draw order; main.py hit-tests it in REVERSE so the popup drawn
            on top (and therefore visible) is the one that receives the click.
        """
        game = self.game
        rects = []

        for report in reports:
            anchor = anchor_for(report)
            if anchor is None:
                continue

            layout = self.get_layout(report, anchor, bounds)
            panel_rect = layout['panel_rect']

            background = self._get_background((panel_rect.width, panel_rect.height))
            if background is not None:
                screen.blit(background, panel_rect.topleft)
            else:
                board = layout['board_rect']
                fallback = pygame.Surface((board.width, board.height), pygame.SRCALPHA)
                fallback.fill(FALLBACK_FILL)
                screen.blit(fallback, board.topleft)
                pygame.draw.rect(screen, FALLBACK_BORDER, board, 2)

            self._draw_contents(screen, layout)
            rects.append((layout['detail_rect'], 'detail', report))
            rects.append((layout['close_rect'], 'close', report))

        return rects

    def _draw_contents(self, screen, layout):
        game = self.game
        board = layout['board_rect']
        pad = game.scale(CONTENT_PAD_REF)

        # Title: centred, bold, underlined. The underline is drawn rather than set via
        # font.set_underline(), which would leak -- FontManager hands out one shared
        # font object per (size, weight) and _get_cached_text() does not key on it.
        title_surface = game._get_cached_text(
            layout['title'], game.small_font_bold, layout['title_color'])
        title_rect = title_surface.get_rect(
            midtop=(board.centerx, board.top + pad))
        screen.blit(title_surface, title_rect)
        pygame.draw.line(
            screen, layout['title_color'],
            (title_rect.left, title_rect.bottom + 1),
            (title_rect.right, title_rect.bottom + 1),
            max(1, game.scale(1)))

        # Body lines: left-aligned against the board, not centred.
        y = title_rect.bottom + game.scale(TITLE_GAP_REF)
        text_x = board.left + pad
        for line in layout['lines']:
            line_surface = game._get_cached_text(line, game.small_font, COLOR_BODY)
            screen.blit(line_surface, (text_x, y))
            y += game.scale(BODY_LINE_REF)

        # Buttons reuse the shared helper, which supplies hover brightening, the click
        # flash and a cache of the scaled GMenuButton.png background.
        for rect, action, label in (
                (layout['detail_rect'], 'detail', "Detail"),
                (layout['close_rect'], 'close', "Close")):
            button_image = getattr(game, 'menu_button_img', None)
            game.helpers.draw_feedback_button(
                rect, None if button_image is not None else BUTTON_FALLBACK_COLOR,
                game.mouse_pos, game.clicked_element,
                'battle_report', action,
                text=label,
                text_color=(255, 255, 255),
                font=game.small_font_bold,
                bg_image=button_image)
