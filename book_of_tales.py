# -*- coding: utf-8 -*-
# book_of_tales.py
# Book of Tales — standalone scenario picker reached from the Campaign screen

"""
Book of Tales
=============

Lists standalone scenarios ("tales") as campaign-style buttons on the left,
and shows the selected tale's description in an ornate panel on the right.

Reached from the Book of Tales icon button (bottom-right) on CampaignScreen.
Follows the SaveBrowser / ReplayBrowser standalone screen pattern with its
own event loop, and reuses their bottom-button geometry and tint states so
Return / Launch look and behave identically to Return / Load there.

Edit SCENARIOS below to add tales. Launch returns the selected tale's id to
main.py, which starts it through its _TALE_REGISTRY.
"""

import pygame
from config.constants import WHITE
from global_sound import sound_manager
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.cursor import draw_custom_cursor
from utils.logger import get_logger
from utils.surface_utils import load_cached_image, get_campaign_button_image
from display_utils import menu_frame_cap

logger = get_logger(__name__)

# Colours — same palette as the browser screens (save_browser.py).
BRASS_COLOR = (181, 166, 66)
# White title. The Campaign title's dark brown (80,50,20) vanishes against
# the dark stone vault at the top of BookOfTalesBG.png, so this screen uses white.
TITLE_COLOR = WHITE
INFO_TEXT = (226, 216, 190)   # Parchment-warm off-white body text
DIM_TEXT = (168, 156, 128)    # Hints and disabled button labels
FALLBACK_BG = (20, 20, 30)    # Only if BookOfTalesBG.png fails to load

# Aspect ratio of CampaignBTN.png once cropped to its opaque bounds (1502x297).
_BTN_ASPECT_FALLBACK = 0.1977

# Tales. Each entry: id (returned on launch, and the key main.py's
# _TALE_REGISTRY uses to start it), name (button and description heading),
# description (see markup below). Optional 'hidden': True keeps a tale off the
# list until it is ready.
#
# Description markup (parsed by BookOfTales._wrap_text):
#   '\n'   line break                '\n\n'  empty line
#   '_'    at the start of a line draws that line underlined (headings)
#   '- '   at the start of a line is a list item; its wrapped lines are indented
SCENARIOS = [
    {
        'id': 'tale_1',
        'name': 'Lack of Funds',
        'description': (
            "At the very beginning of the Age of Empires, the nascent Londic Empire was in "
            "a state of internal turmoil. Undergoing a deeply reformative period, its emperor "
            "was eager to spend the imperial funds on containing external threats at bay - "
            "often forgetting, that the true danger lay within its borders. Emperor Kondaron "
            "was, therefore, often called The Lacking.\n"
            "\n"
            "The Emperor needed a strong, guiding hand to balance the amount of funds spent on "
            "external and internal affairs. However, his obsession with what was out of the "
            "imperial borders soon turned into a thirst for conquest.\n"
            "\n"
            "_Objectives:\n"
            "- conquer the territories of the Aelatanaic Tribes\n"
            "- do not lose control over the city of Generax\n"
            "\n"
            "_Notes:\n"
            "- keep your popularity high by spending funds on internal investments\n"
            "- the lower your popularity, the higher risk of your armies and population "
            "revolting against you\n"
            "- Kingdom of Daurels and Heilonic Kingdoms will turn hostile if you issue an "
            "attack against them"
        ),
    },
    {
        'id': 'tale_2',   # tale_final_breaths.py
        'name': 'Final Breaths',
        'description': (
            "In final years of the Age of Kings, the Zjoal Empire, once the most majestic "
            "and powerful entity of the world, was all but spent. Being a victim of a "
            "horrendous civil war, the empire was split into the Zjoal Empire proper, "
            "centered on Avinon, and the Kerunian Empire, covering vast coasts of the south, "
            "centered around Délaen. Now, as the Empire draws its last breaths, the war "
            "between Kerunians and Zjoals rages ever stronger and the eastern stretches of "
            "land are subject to rebellion, the only hope is to defend the glory of the "
            "olden Empire for as long as possible.\n"
            "\n"
            "_Objectives:\n"
            "- Defend territories of Lunedale and Free Cities for at least 15 turns\n"
            "\n"
            "_Notes:\n"
            "- While the primary attacks will come from Kerunian Empire in the south, do not "
            "neglect defenses in the east.\n"
            "- Economic situation within the Empire is worse than ever. Disassembling "
            "existing infrastructure to support the economy will work wonders.\n"
            "- The imperial treasury is taxed at 100%: all gold left unspent at the end "
            "of your turn is lost."
        ),
    },
    {
        'id': 'tale_3',
        'hidden': True,  # Not shown yet — remove to reveal
        'name': 'Tale III',
        'description': (
            "A placeholder tale. The scribes are still gathering the accounts "
            "of this chapter of history."
        ),
    },
    {
        'id': 'tale_4',
        'hidden': True,  # Not shown yet — remove to reveal
        'name': 'Tale IV',
        'description': (
            "A placeholder tale. Its pages are blank for now, but not for long."
        ),
    },
]


class BookOfTales:
    """
    Book of Tales screen.

    Usage:
        screen_obj = BookOfTales(screen)
        result = screen_obj.run()
        # result = {'action': 'back'}, {'action': 'quit'}
        #          or {'action': 'launch', 'scenario_id': '...'}
    """

    def __init__(self, screen):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        self.clock = pygame.time.Clock()
        self.ui_scale = self.height / 1080.0
        s = self.ui_scale

        # State
        self.done = False
        self.result = None
        # Only tales not flagged 'hidden' get a button
        self.scenarios = [t for t in SCENARIOS if not t.get('hidden')]
        self.selected_index = -1
        self.hovered_button = None   # 'back', 'launch', 'page_left', 'page_right' or ('tale', index)
        self.clicked_button = None   # Same ids; lasts exactly one rendered frame
        self.current_page = 0

        # --- Assets (decoded once per process, rescaled per instance) ---
        raw_bg = load_cached_image("assets/BookOfTalesBG.png", alpha=False)
        self.bg_image = (pygame.transform.smoothscale(raw_bg, (self.width, self.height))
                         if raw_bg is not None else None)
        if raw_bg is None:
            logger.warning("BookOfTales: could not load BookOfTalesBG.png")

        self.panel_image = load_cached_image("assets/IGOptMenuBG.png", alpha=True)
        if self.panel_image is None:
            logger.warning("BookOfTales: could not load IGOptMenuBG.png")

        self.btn_image = get_campaign_button_image()
        if self.btn_image is not None:
            bw, bh = self.btn_image.get_size()
            self.btn_aspect = bh / bw
        else:
            logger.warning("BookOfTales: could not load CampaignBTN.png")
            self.btn_aspect = _BTN_ASPECT_FALLBACK

        # --- Fonts (direct Font(), NOT font_manager — matches the browsers) ---
        font_path = 'assets/fonts/Cinzel-Regular.ttf'
        bold_path = 'assets/fonts/Cinzel-SemiBold.ttf'
        self.title_font = pygame.font.Font(bold_path, max(20, int(48 * s)))
        self.btn_font = pygame.font.Font(font_path, max(16, int(24 * s)))
        self.primary_font = pygame.font.Font(bold_path, max(16, int(24 * s)))
        # Same size/face as the Campaign screen's mission buttons
        self.tale_font = pygame.font.Font(font_path, max(14, int(24 * s)))
        self.heading_font = pygame.font.Font(bold_path, max(18, int(36 * s)))
        self.body_font = pygame.font.Font(font_path, max(13, int(24 * s)))
        # Separate instance for '_' heading lines: set_underline() mutates the
        # Font object, so the shared body_font must never be touched.
        self.body_font_underline = pygame.font.Font(font_path, max(13, int(24 * s)))
        self.body_font_underline.set_underline(True)

        # --- Layout ---
        self.title_surface = self.title_font.render("Book of Tales", True, TITLE_COLOR)
        self.title_rect = self.title_surface.get_rect(centerx=self.width // 2, top=int(30 * s))

        # Bottom buttons — identical geometry to SaveBrowser's Return / Load
        btn_width = int(400 * s)
        btn_height = int(btn_width * self.btn_aspect)
        btn_y = self.height - btn_height - int(30 * s)
        btn_margin = int(40 * s)
        self.btn_back = pygame.Rect(btn_margin, btn_y, btn_width, btn_height)
        self.btn_launch = pygame.Rect(
            self.width - btn_margin - btn_width, btn_y, btn_width, btn_height)

        # Content area between title and bottom buttons, split into a left
        # button column and a right description panel.
        margin = int(60 * s)
        content_top = self.title_rect.bottom + int(30 * s)
        content_bottom = btn_y - int(30 * s)
        content_h = max(1, content_bottom - content_top)
        content_w = max(1, self.width - 2 * margin)

        column_w = min(int(700 * s), int(content_w * 0.42))
        self.tale_btn_w = max(1, column_w)
        self.tale_btn_h = max(1, int(self.tale_btn_w * self.btn_aspect))
        self.tale_btn_spacing = int(40 * s)
        self.column_rect = pygame.Rect(margin, content_top, column_w, content_h)

        gap = int(60 * s)
        self.panel_rect = pygame.Rect(
            self.column_rect.right + gap, content_top,
            max(1, self.width - margin - (self.column_rect.right + gap)), content_h)

        # Inner text area. Fractions of the panel (not N * ui_scale) because the
        # IGOptMenuBG frame is stretched, so its border scales with the panel.
        pad_x = int(self.panel_rect.width * 0.10)
        pad_y = int(self.panel_rect.height * 0.09)
        self.text_rect = self.panel_rect.inflate(-2 * pad_x, -2 * pad_y)

        # Pagination: reserve a strip under the column for arrows only when needed
        arrow_size = int(50 * s)
        step = self.tale_btn_h + self.tale_btn_spacing
        per_page = max(1, (content_h + self.tale_btn_spacing) // step)
        if len(self.scenarios) > per_page:
            # Arrow strip takes the room of the gap below the last button
            per_page = max(1, (content_h - arrow_size) // step)
        self.per_page = per_page
        self.total_pages = max(1, (len(self.scenarios) + per_page - 1) // per_page)
        arrow_y = self.column_rect.bottom - arrow_size
        self.left_arrow_rect = pygame.Rect(
            self.column_rect.centerx - int(30 * s) - arrow_size, arrow_y, arrow_size, arrow_size)
        self.right_arrow_rect = pygame.Rect(
            self.column_rect.centerx + int(30 * s), arrow_y, arrow_size, arrow_size)
        self._update_visible_tales()

        # --- Pre-built surfaces (never allocate per-frame) ---
        if self.panel_image is not None:
            self._scaled_panel = pygame.transform.smoothscale(self.panel_image, self.panel_rect.size)
        else:
            self._scaled_panel = pygame.Surface(self.panel_rect.size, pygame.SRCALPHA)
            self._scaled_panel.fill((40, 20, 10, 235))
            pygame.draw.rect(self._scaled_panel, BRASS_COLOR, self._scaled_panel.get_rect(), 2)

        self._btn_cache = {}
        self._text_cache = {}
        self._outline_cache = {}   # size -> silhouette points for the selected outline
        # Description body geometry (fixed): heading + divider on top, then a
        # scrollable, clipped body. A narrow gutter on the right holds the
        # scroll indicator so text never runs under it.
        self.desc_divider_y = (self.text_rect.top + self.heading_font.get_height()
                               + int(12 * s))
        body_top = self.desc_divider_y + int(20 * s)
        self.desc_gutter = int(16 * s)
        self.desc_body_rect = pygame.Rect(
            self.text_rect.x, body_top,
            max(1, self.text_rect.width - self.desc_gutter),
            max(1, self.text_rect.bottom - body_top))
        self.desc_line_h = self.body_font.get_linesize()

        # Wrapped description lines + scroll state, rebuilt only on selection
        # change (never from the render path)
        self._desc_lines = []
        self.desc_scroll = 0
        self.desc_max_scroll = 0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Main loop — blocks until the user returns or quits."""
        while not self.done:
            self.clock.tick(menu_frame_cap())
            self._handle_events()
            self._render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()
        return self.result

    def _update_visible_tales(self):
        """Assign rects to the tales on the current page.

        The column centres a *full* page of slots (at least 4), not just the
        visible tales, so buttons stay in fixed slots from the top — a short
        list (e.g. while tales are hidden) doesn't float mid-screen.
        """
        start = self.current_page * self.per_page
        self.visible = list(range(start, min(start + self.per_page, len(self.scenarios))))
        slots = min(self.per_page, 4) if self.total_pages == 1 else self.per_page
        slots = max(slots, len(self.visible))
        stack_h = slots * self.tale_btn_h + max(0, slots - 1) * self.tale_btn_spacing
        usable_bottom = (self.left_arrow_rect.top - self.tale_btn_spacing
                         if self.total_pages > 1 else self.column_rect.bottom)
        top = self.column_rect.top + max(0, (usable_bottom - self.column_rect.top - stack_h) // 2)
        self.tale_rects = {}
        for slot, idx in enumerate(self.visible):
            y = top + slot * (self.tale_btn_h + self.tale_btn_spacing)
            self.tale_rects[idx] = pygame.Rect(self.column_rect.x, y,
                                               self.tale_btn_w, self.tale_btn_h)

    def _button_at(self, pos):
        """Hit-test every clickable element. Disabled Launch never hits."""
        if self.btn_back.collidepoint(pos):
            return 'back'
        if self.btn_launch.collidepoint(pos) and self.selected_index >= 0:
            return 'launch'
        if self.total_pages > 1:
            if self.current_page > 0 and self.left_arrow_rect.collidepoint(pos):
                return 'page_left'
            if self.current_page < self.total_pages - 1 and self.right_arrow_rect.collidepoint(pos):
                return 'page_right'
        for idx, rect in self.tale_rects.items():
            if rect.collidepoint(pos):
                return ('tale', idx)
        return None

    def _handle_events(self):
        """Process input events."""
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_button = self._button_at(mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.result = {'action': 'quit'}
                self.done = True
                return

            elif event.type == _MUSIC_END_EVENT:
                _music_manager.handle_music_end_event()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.result = {'action': 'back'}
                    self.done = True
                elif event.key == pygame.K_RETURN and self.selected_index >= 0:
                    self._launch_selected()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self._handle_left_click(mouse_pos)
                # Wheel (legacy buttons 4/5, like the browsers) scrolls the
                # description while the mouse is over its panel
                elif event.button in (4, 5) and self.panel_rect.collidepoint(mouse_pos):
                    step = self.desc_line_h * (-1 if event.button == 4 else 1)
                    self.desc_scroll = max(0, min(self.desc_max_scroll, self.desc_scroll + step))

    def _handle_left_click(self, mouse_pos):
        """Handle a left click on any button."""
        target = self._button_at(mouse_pos)
        if target is None:
            return
        sound_manager.play_ui_click()
        self.clicked_button = target

        if target == 'back':
            self.result = {'action': 'back'}
            self.done = True
        elif target == 'launch':
            self._launch_selected()
        elif target == 'page_left':
            self.current_page -= 1
            self._update_visible_tales()
        elif target == 'page_right':
            self.current_page += 1
            self._update_visible_tales()
        else:
            # ('tale', index) — select it; the description panel follows
            self._select_tale(target[1])

    def _select_tale(self, idx):
        """Select a tale: re-wrap its description and reset/re-bound the scroll."""
        if idx == self.selected_index:
            return
        self.selected_index = idx
        text = self.scenarios[idx].get('description', '')
        self._desc_lines = self._wrap_text(text, self.body_font, self.desc_body_rect.width,
                                           self.body_font_underline)
        self.desc_scroll = 0
        total_h = len(self._desc_lines) * self.desc_line_h
        self.desc_max_scroll = max(0, total_h - self.desc_body_rect.height)

    def _launch_selected(self):
        """Close the screen and hand the selected tale's id to main.py.

        main.py's campaign loop looks the id up in _TALE_REGISTRY, runs the
        tale, then reopens this screen.
        """
        if 0 <= self.selected_index < len(self.scenarios):
            scenario_id = self.scenarios[self.selected_index]['id']
            logger.info(f"BookOfTales: launching {scenario_id}")
            self.result = {'action': 'launch', 'scenario_id': scenario_id}
            self.done = True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self):
        """Render the full screen."""
        if self.bg_image:
            self.screen.blit(self.bg_image, (0, 0))
        else:
            self.screen.fill(FALLBACK_BG)

        self.screen.blit(self.title_surface, self.title_rect)

        # Left column: tale buttons
        for idx in self.visible:
            self._render_tale_button(idx)
        if self.total_pages > 1:
            if self.current_page > 0:
                self._draw_page_arrow(self.left_arrow_rect, 'left', 'page_left')
            if self.current_page < self.total_pages - 1:
                self._draw_page_arrow(self.right_arrow_rect, 'right', 'page_right')

        # Right side: description panel
        self.screen.blit(self._scaled_panel, self.panel_rect)
        self._render_description()

        # Bottom buttons — same as SaveBrowser's Return / Load
        self._render_btn(self.btn_back, "Return", 'back', self.btn_font, WHITE, enabled=True)
        self._render_btn(self.btn_launch, "Launch", 'launch', self.primary_font,
                         BRASS_COLOR, enabled=self.selected_index >= 0)

        # Reset click state after paint, so the press tint lasts exactly one frame
        self.clicked_button = None

    def _render_tale_button(self, idx):
        """Draw one tale button — Campaign mission button look plus a selected tint."""
        rect = self.tale_rects[idx]
        btn_id = ('tale', idx)
        if self.clicked_button == btn_id:
            state = 'click'
        elif self.hovered_button == btn_id:
            state = 'hover'
        else:
            state = 'normal'
        selected = (idx == self.selected_index)

        if self.btn_image is not None:
            self.screen.blit(self._btn_surface(rect.size, state, selected), rect)
        else:
            fill = (70, 60, 40) if (selected or state != 'normal') else (50, 42, 28)
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pygame.draw.rect(self.screen, BRASS_COLOR, rect, 1, border_radius=6)

        # Brass outline on the selected tale (like the selected row in Saved
        # Games), traced along the button art's silhouette rather than a box.
        if selected:
            points = self._outline_points(rect.size)
            if points:
                shifted = [(rect.x + px, rect.y + py) for px, py in points]
                pygame.draw.lines(self.screen, BRASS_COLOR, True, shifted,
                                  max(1, int(2 * self.ui_scale)))
            else:
                pygame.draw.rect(self.screen, BRASS_COLOR, rect, max(1, int(2 * self.ui_scale)))

        surf = self._cached_text(self.scenarios[idx]['name'], self.tale_font, WHITE)
        self.screen.blit(surf, surf.get_rect(center=rect.center))

    def _outline_points(self, size):
        """Silhouette of the scaled button art as a point list, cached per size."""
        if size not in self._outline_cache:
            points = []
            if self.btn_image is not None:
                scaled = self._btn_surface(size, 'normal')
                # Threshold matches crop_to_opaque so the outline hugs the visible art
                points = pygame.mask.from_surface(scaled, 128).outline(2)
            self._outline_cache[size] = points if len(points) > 2 else []
        return self._outline_cache[size]

    def _render_description(self):
        """Draw the selected tale's name and wrapped description inside the panel."""
        area = self.text_rect
        if self.selected_index < 0:
            hint = self._cached_text("Select a tale to read its story.", self.body_font, DIM_TEXT)
            self.screen.blit(hint, hint.get_rect(center=area.center))
            return

        tale = self.scenarios[self.selected_index]
        heading = self._cached_text(tale['name'], self.heading_font, BRASS_COLOR)
        self.screen.blit(heading, heading.get_rect(centerx=area.centerx, top=area.top))

        divider_y = self.desc_divider_y
        pygame.draw.line(self.screen, BRASS_COLOR, (area.left, divider_y), (area.right, divider_y),
                         max(1, int(2 * self.ui_scale)))

        # Scrollable body, clipped so scrolled lines never paint over the
        # heading or past the frame
        body = self.desc_body_rect
        line_h = self.desc_line_h
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(body)
        y = body.top - self.desc_scroll
        for line in self._desc_lines:
            # line = (text, underlined, indent_px) — see _wrap_text
            if y + line_h <= body.top:
                y += line_h
                continue
            if y >= body.bottom:
                break
            if line[0]:
                font = self.body_font_underline if line[1] else self.body_font
                surf = self._cached_text(line[0], font, INFO_TEXT)
                self.screen.blit(surf, (body.x + line[2], y))
            y += line_h
        self.screen.set_clip(prev_clip)

        self._draw_desc_scroll_indicator()

    def _draw_desc_scroll_indicator(self):
        """Slim brass scroll indicator (same look as SaveBrowser's). Visual only."""
        if self.desc_max_scroll <= 0:
            return
        body = self.desc_body_rect
        total_h = len(self._desc_lines) * self.desc_line_h
        track_w = max(2, int(6 * self.ui_scale))
        track_x = body.right + self.desc_gutter - track_w
        radius = max(1, track_w // 2)
        pygame.draw.rect(self.screen, (54, 42, 28),
                         pygame.Rect(track_x, body.y, track_w, body.height), border_radius=radius)
        thumb_h = max(int(20 * self.ui_scale), int(body.height * body.height / total_h))
        thumb_h = min(thumb_h, body.height)
        thumb_y = body.y + int((body.height - thumb_h) * (self.desc_scroll / self.desc_max_scroll))
        pygame.draw.rect(self.screen, BRASS_COLOR,
                         pygame.Rect(track_x, thumb_y, track_w, thumb_h), border_radius=radius)

    @staticmethod
    def _wrap_text(text, font, max_w, underline_font=None):
        """Word-wrap description text to max_w pixels, applying the SCENARIOS markup.

        Returns a list of (text, underlined, indent_px) tuples, one per drawn line:
          - each '\n'-separated source line starts a new line; an empty source
            line (i.e. '\n\n') becomes an empty drawn line
          - a leading '_' is stripped and marks the line underlined
          - a line starting with '- ' is a list item: its wrapped continuation
            lines are indented by the width of '- ' (hanging indent)
        """
        lines = []
        for raw in text.split('\n'):
            underlined = raw.startswith('_')
            if underlined:
                raw = raw[1:]
            words = raw.split()
            if not words:
                lines.append(('', False, 0))
                continue
            line_font = underline_font if (underlined and underline_font) else font
            hang = font.size('- ')[0] if raw.startswith('- ') else 0
            current = ''
            indent = 0   # First line is flush left; continuations get the hang
            for word in words:
                candidate = f"{current} {word}" if current else word
                if line_font.size(candidate)[0] <= max_w - indent or not current:
                    current = candidate
                else:
                    lines.append((current, underlined, indent))
                    current = word
                    indent = hang
            lines.append((current, underlined, indent))
        return lines

    def _draw_page_arrow(self, rect, direction, btn_id):
        """Pagination triangle, same colours as CampaignScreen's page arrows."""
        cx, cy = rect.center
        hw, hh = rect.width // 2, rect.height // 2
        if direction == 'left':
            points = [(cx - hw, cy), (cx + hw, cy - hh), (cx + hw, cy + hh)]
        else:
            points = [(cx + hw, cy), (cx - hw, cy - hh), (cx - hw, cy + hh)]
        if self.clicked_button == btn_id:
            color = (60, 40, 20)
        elif self.hovered_button == btn_id:
            color = (45, 28, 12)
        else:
            color = (30, 18, 8)
        pygame.draw.polygon(self.screen, color, points)

    def _cached_text(self, text, font, color):
        """Render text with caching."""
        key = (text, id(font), color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 512:
                self._text_cache.clear()
            surf = font.render(text, True, color)
            self._text_cache[key] = surf
        return surf

    def _btn_surface(self, size, state, selected=False):
        """
        Cached, fully tinted ornate button surface (same tints as SaveBrowser).
        selected=True uses MissionScreen's brighter selected base (140 vs 100).
        """
        key = (size[0], size[1], state, selected)
        surf = self._btn_cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(self.btn_image, size)
            if state == 'disabled':
                mult = (60, 60, 60, 255)
            elif selected:
                mult = (140, 140, 140, 255)
            else:
                mult = (100, 100, 100, 255)
            surf.fill(mult, special_flags=pygame.BLEND_RGBA_MULT)
            if state == 'click':
                surf.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif state == 'hover':
                surf.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self._btn_cache[key] = surf
        return surf

    def _render_btn(self, rect, text, btn_id, font, text_color, enabled=True):
        """Render a CampaignBTN.png-based button with hover/click/disabled states."""
        if not enabled:
            state = 'disabled'
        elif self.clicked_button == btn_id:
            state = 'click'
        elif self.hovered_button == btn_id:
            state = 'hover'
        else:
            state = 'normal'

        if self.btn_image is not None:
            self.screen.blit(self._btn_surface(rect.size, state), rect)
        else:
            fill = (70, 60, 40) if state in ('hover', 'click') else (50, 42, 28)
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pygame.draw.rect(self.screen, BRASS_COLOR if enabled else DIM_TEXT,
                             rect, 1, border_radius=6)

        surf = self._cached_text(text, font, text_color if enabled else DIM_TEXT)
        self.screen.blit(surf, surf.get_rect(center=rect.center))
