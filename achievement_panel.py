# -*- coding: utf-8 -*-
# achievement_panel.py
# Achievement list panel UI for the main menu

"""
Achievement Panel
=================

UI helper class that renders the achievement list panel content inside the
sliding OptionsMenuBG.png panel in main_menu.py. Handles category filtering,
name search, scrollable achievement list, and sorting (earned first, clustered by progression with lowest threshold on top).
"""

import pygame
from config.constants import WHITE
from achievement_manager import achievement_manager, CATEGORIES, CATEGORY_LABELS
from global_sound import sound_manager
from utils.logger import get_logger
from utils.surface_utils import crop_to_opaque

logger = get_logger(__name__)

# Colors
BRASS_COLOR = (181, 166, 66)
REWARD_TEXT_COLOR = (200, 180, 100)
DESCRIPTION_COLOR = (200, 200, 200)
SEARCH_PLACEHOLDER_COLOR = (150, 150, 150)


class AchievementPanel:
    """
    Renders achievement list content inside the main menu's sliding panel.
    Created once by MainMenu.__init__ and reused across panel open/close cycles.
    """

    def __init__(self, screen_width, screen_height, ui_scale):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.ui_scale = ui_scale

        # Filter state
        self.selected_category = None  # None = show all
        self.search_text = ''
        self.search_active = False
        self.scroll_offset = 0

        # UI element rects (populated during draw, used for click detection)
        self.ui_elements = {}

        # Item height for each achievement row (AchievementFull.png is 1331x649, ~2:1)
        self.item_height = int(110 * ui_scale)

        # Fonts
        try:
            self.title_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf',
                                               max(18, int(30 * ui_scale)))
            self.category_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf',
                                                  max(12, int(17 * ui_scale)))
            self.name_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf',
                                              max(13, int(18 * ui_scale)))
            self.desc_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf',
                                              max(11, int(14 * ui_scale)))
            self.desc_font_small = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf',
                                                     max(9, int(11 * ui_scale)))
            self.reward_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf',
                                                max(11, int(13 * ui_scale)))
            self.search_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf',
                                                max(12, int(16 * ui_scale)))
            self.close_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf',
                                               max(14, int(20 * ui_scale)))
        except Exception:
            self.title_font = pygame.font.SysFont('arial', max(18, int(30 * ui_scale)), bold=True)
            self.category_font = pygame.font.SysFont('arial', max(12, int(17 * ui_scale)))
            self.name_font = pygame.font.SysFont('arial', max(13, int(18 * ui_scale)), bold=True)
            self.desc_font = pygame.font.SysFont('arial', max(11, int(14 * ui_scale)))
            self.desc_font_small = pygame.font.SysFont('arial', max(9, int(11 * ui_scale)))
            self.reward_font = pygame.font.SysFont('arial', max(11, int(13 * ui_scale)))
            self.search_font = pygame.font.SysFont('arial', max(12, int(16 * ui_scale)))
            self.close_font = pygame.font.SysFont('arial', max(14, int(20 * ui_scale)))

        # Load and cache assets
        self._load_assets()

        # FPS OPTIMIZATION 5A: Cache scaled surfaces (only change on resize)
        self._cached_category_btn_bg = None
        self._cached_category_btn_bg_size = (0, 0)
        self._cached_achievement_bg = None
        self._cached_achievement_bg_size = (0, 0)
        self._cached_icon_border = None
        self._cached_icon_border_size = 0
        self._cached_scaled_icons = {}  # keyed by (icon_path, icon_size)

    def _load_assets(self):
        """Load and pre-cache all achievement panel assets."""
        # AchievementFull.png background for each list item
        try:
            self.achievement_bg = pygame.image.load(
                'assets/achievements/AchievementFull.png').convert_alpha()
        except Exception:
            self.achievement_bg = None

        # CampaignBTN.png for category filter buttons
        try:
            raw_btn = pygame.image.load('assets/CampaignBTN.png').convert_alpha()
            self.category_btn_image = crop_to_opaque(raw_btn, threshold=128)
        except Exception:
            self.category_btn_image = None

        # IconBorder.png for achievement icons
        try:
            self.icon_border = pygame.image.load('assets/mapicons/IconBorder.png').convert_alpha()
        except Exception:
            self.icon_border = None

        # Pre-load all achievement icons (keyed by icon path)
        self._icon_cache = {}
        for ach in achievement_manager.get_all_achievements():
            path = ach['icon']
            if path not in self._icon_cache:
                try:
                    self._icon_cache[path] = pygame.image.load(path).convert_alpha()
                except Exception:
                    self._icon_cache[path] = None

    def reset(self):
        """Reset panel state when opened."""
        self.search_text = ''
        self.search_active = False
        self.scroll_offset = 0
        # Reload achievements in case new ones were earned
        achievement_manager.load()

    def _get_filtered_achievements(self):
        """Get achievements filtered by category and search, sorted: earned first, then unearned. Within each group, clustered by stat_key with lowest threshold on top."""
        if self.selected_category:
            achievements = achievement_manager.get_achievements_by_category(self.selected_category)
        else:
            achievements = achievement_manager.get_all_achievements()

        # Apply name search filter
        if self.search_text.strip():
            query = self.search_text.strip().lower()
            achievements = [a for a in achievements if query in a['name'].lower()]

        # Sort: earned first, then unearned.
        # Within each group, cluster by stat_key and sort by stat_threshold ascending
        # (lowest requirement on top within a progression cluster).
        earned = [a for a in achievements if a['earned']]
        unearned = [a for a in achievements if not a['earned']]
        earned.sort(key=lambda a: (a.get('stat_key', ''), a.get('stat_threshold', 0)))
        unearned.sort(key=lambda a: (a.get('stat_key', ''), a.get('stat_threshold', 0)))

        return earned + unearned

    def handle_click(self, pos, panel_x, panel_y, panel_w, panel_h):
        """Handle mouse click inside the panel. Returns True if click was consumed."""
        # Category buttons
        for cat_id, elem in self.ui_elements.items():
            if cat_id.startswith('cat_') and elem['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                cat = cat_id[4:]  # Remove 'cat_' prefix
                if self.selected_category == cat:
                    self.selected_category = None  # Deselect
                else:
                    self.selected_category = cat
                self.scroll_offset = 0
                return True

        # Search input
        if 'search_input' in self.ui_elements:
            if self.ui_elements['search_input']['rect'].collidepoint(pos):
                self.search_active = True
                return True
            else:
                self.search_active = False

        # Close button
        if 'close_button' in self.ui_elements:
            if self.ui_elements['close_button']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                return 'close'

        return True  # Consume click inside panel to prevent passthrough

    def handle_scroll(self, direction, max_scroll):
        """Handle mouse wheel for scrolling. direction: 1=up, -1=down."""
        scroll_step = int(40 * self.ui_scale)
        self.scroll_offset -= direction * scroll_step
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

    def handle_keydown(self, event):
        """Handle keyboard input for search field."""
        if not self.search_active:
            return False
        if event.key == pygame.K_BACKSPACE:
            self.search_text = self.search_text[:-1]
            self.scroll_offset = 0
            return True
        elif event.key == pygame.K_RETURN or event.key == pygame.K_ESCAPE:
            self.search_active = False
            return True
        elif len(self.search_text) < 30 and event.unicode.isprintable():
            self.search_text += event.unicode
            self.scroll_offset = 0
            return True
        return False

    def draw(self, screen, panel_x, panel_y, panel_w, panel_h, hovered_element=None):
        """
        Render all panel content at the given position.
        Called by main_menu._draw_achievement_panel() each frame.
        """
        self.ui_elements = {}

        # Content area inside ornate border (asymmetric padding for OptionsMenuBG.png)
        pad_left = int(130 * self.ui_scale)
        pad_right = int(110 * self.ui_scale)
        pad_top = int(130 * self.ui_scale)
        pad_bottom = int(110 * self.ui_scale)

        content_x = panel_x + pad_left
        content_y = panel_y + pad_top
        content_w = panel_w - pad_left - pad_right
        content_h = panel_h - pad_top - pad_bottom

        y = content_y

        # --- Title ---
        title_surf = self.title_font.render("Achievements", True, WHITE)
        title_rect = title_surf.get_rect(centerx=panel_x + panel_w // 2, top=y)
        screen.blit(title_surf, title_rect)
        y += title_surf.get_height() + int(15 * self.ui_scale)

        # --- Category filter buttons ---
        y = self._draw_category_buttons(screen, content_x, y, content_w, hovered_element)
        y += int(12 * self.ui_scale)

        # --- Search input ---
        y = self._draw_search_input(screen, content_x, y, content_w, hovered_element)
        y += int(12 * self.ui_scale)

        # --- Close button at bottom ---
        close_btn_w = int(150 * self.ui_scale)
        close_btn_h = int(40 * self.ui_scale)
        close_btn_x = panel_x + (panel_w - close_btn_w) // 2
        close_btn_y = content_y + content_h - close_btn_h
        close_rect = pygame.Rect(close_btn_x, close_btn_y, close_btn_w, close_btn_h)

        # Draw close button
        is_hovered = (hovered_element == 'close_button')
        from utils.colors import lighten_color
        close_bg = lighten_color((120, 50, 50), 0.2) if is_hovered else (120, 50, 50)
        pygame.draw.rect(screen, close_bg, close_rect, border_radius=8)
        pygame.draw.rect(screen, (150, 150, 150), close_rect, 2, border_radius=8)
        close_text = self.close_font.render("Close", True, WHITE)
        close_text_rect = close_text.get_rect(center=close_rect.center)
        screen.blit(close_text, close_text_rect)
        self.ui_elements['close_button'] = {'rect': close_rect}

        # --- Achievement list (scrollable area between search and close button) ---
        list_top = y
        list_bottom = close_btn_y - int(10 * self.ui_scale)
        list_height = list_bottom - list_top
        if list_height > 0:
            self._draw_achievement_list(screen, content_x, list_top, content_w, list_height, hovered_element)

    def _draw_category_buttons(self, screen, x, y, available_width, hovered_element):
        """Draw 4 category filter buttons in a row. Returns y after buttons."""
        btn_spacing = int(8 * self.ui_scale)
        btn_count = len(CATEGORIES)
        btn_width = (available_width - (btn_count - 1) * btn_spacing) // btn_count

        # Compute button height from CampaignBTN.png aspect ratio
        if self.category_btn_image:
            img_w, img_h = self.category_btn_image.get_size()
            btn_height = int(btn_width * (img_h / img_w))
        else:
            btn_height = int(40 * self.ui_scale)

        for i, cat_id in enumerate(CATEGORIES):
            btn_x = x + i * (btn_width + btn_spacing)
            btn_rect = pygame.Rect(btn_x, y, btn_width, btn_height)

            is_selected = (self.selected_category == cat_id)
            is_hovered = (hovered_element == f'cat_{cat_id}')

            if self.category_btn_image:
                # FPS OPTIMIZATION 5A: Cache scaled category button background
                btn_size = (btn_width, btn_height)
                if self._cached_category_btn_bg is None or self._cached_category_btn_bg_size != btn_size:
                    self._cached_category_btn_bg = pygame.transform.smoothscale(
                        self.category_btn_image, btn_size)
                    self._cached_category_btn_bg_size = btn_size
                scaled_bg = self._cached_category_btn_bg
                button_surface = scaled_bg.copy()

                if is_selected:
                    button_surface.fill((140, 140, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
                else:
                    button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

                if is_hovered:
                    button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

                screen.blit(button_surface, btn_rect)
            else:
                # Fallback solid color
                color = (100, 130, 180) if is_selected else (60, 80, 120)
                pygame.draw.rect(screen, color, btn_rect, border_radius=5)

            # Button text
            label = CATEGORY_LABELS[cat_id]
            text_surf = self.category_font.render(label, True, WHITE)
            text_rect = text_surf.get_rect(center=btn_rect.center)
            screen.blit(text_surf, text_rect)

            self.ui_elements[f'cat_{cat_id}'] = {'rect': btn_rect}

        return y + btn_height

    def _draw_search_input(self, screen, x, y, width, hovered_element):
        """Draw the name search input field. Returns y after input."""
        input_height = int(32 * self.ui_scale)
        input_rect = pygame.Rect(x, y, width, input_height)

        # Draw input background (black)
        is_active = self.search_active
        input_bg = (30, 30, 30) if is_active else (20, 20, 20)
        pygame.draw.rect(screen, input_bg, input_rect, border_radius=5)
        pygame.draw.rect(screen, WHITE if is_active else (100, 100, 100), input_rect, 2, border_radius=5)

        # Draw text or placeholder
        if self.search_text:
            text_surf = self.search_font.render(self.search_text, True, WHITE)
        elif not is_active:
            text_surf = self.search_font.render("Search...", True, SEARCH_PLACEHOLDER_COLOR)
        else:
            text_surf = self.search_font.render("", True, WHITE)

        text_rect = text_surf.get_rect(midleft=(input_rect.left + 10, input_rect.centery))
        screen.blit(text_surf, text_rect)

        # Blinking cursor when active
        if is_active and int(pygame.time.get_ticks() / 500) % 2 == 0:
            cursor_x = text_rect.right + 2
            pygame.draw.line(screen, WHITE,
                             (cursor_x, input_rect.top + 6),
                             (cursor_x, input_rect.bottom - 6), 2)

        self.ui_elements['search_input'] = {'rect': input_rect}
        return y + input_height

    def _draw_achievement_list(self, screen, x, y, width, height, hovered_element):
        """Draw the scrollable achievement list."""
        achievements = self._get_filtered_achievements()

        # Calculate total content height
        item_spacing = int(8 * self.ui_scale)
        # A4 fix: clamp to 0 to avoid negative height when achievement list is empty
        total_content_height = max(0, len(achievements) * (self.item_height + item_spacing) - item_spacing)
        max_scroll = max(0, total_content_height - height)

        # Clamp scroll
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

        # Store max_scroll for handle_scroll
        self._max_scroll = max_scroll

        # Create clipping rect for the list area
        clip_rect = pygame.Rect(x, y, width, height)
        old_clip = screen.get_clip()
        screen.set_clip(clip_rect)

        # Draw each achievement item
        item_y = y - self.scroll_offset
        icon_size = int(65 * self.ui_scale)
        icon_margin = int(10 * self.ui_scale)
        mouse_pos = pygame.mouse.get_pos()
        hovered_ach = None

        for ach in achievements:
            # Skip items fully above visible area
            if item_y + self.item_height < y:
                item_y += self.item_height + item_spacing
                continue
            # Stop if items are fully below visible area
            if item_y > y + height:
                break

            item_rect = pygame.Rect(x, item_y, width, self.item_height)
            self._draw_achievement_item(screen, item_rect, ach, icon_size, icon_margin)

            # Track hovered achievement for tooltip (earned date or progress)
            if item_rect.collidepoint(mouse_pos):
                hovered_ach = ach

            item_y += self.item_height + item_spacing

        # Restore clip
        screen.set_clip(old_clip)

        # Draw scroll indicator if needed
        if max_scroll > 0:
            self._draw_scroll_indicator(screen, x + width - int(6 * self.ui_scale), y,
                                        int(4 * self.ui_scale), height, total_content_height)

        # Draw hover tooltip (after clip restore so it's not clipped)
        # Earned: show date. Unearned with threshold > 1: show progress.
        if hovered_ach:
            try:
                tooltip_lines = []
                tooltip_font = self.reward_font
                if hovered_ach['earned'] and hovered_ach.get('earned_timestamp'):
                    tooltip_lines.append(f"Earned: {hovered_ach['earned_timestamp'][:10]}")
                elif not hovered_ach['earned'] and hovered_ach.get('stat_threshold', 1) > 1:
                    # Show progress toward the achievement
                    progress = hovered_ach.get('stat_progress', 0)
                    threshold = hovered_ach['stat_threshold']
                    tooltip_lines.append(f"Progress: {progress} / {threshold}")

                if tooltip_lines:
                    line_surfs = [tooltip_font.render(line, True, (255, 255, 255)) for line in tooltip_lines]
                    line_h = tooltip_font.get_linesize()
                    pad = int(6 * self.ui_scale)
                    tw = max(s.get_width() for s in line_surfs) + pad * 2
                    th = len(line_surfs) * line_h + pad * 2
                    tx = min(mouse_pos[0] + 15, x + width - tw - 5)
                    ty = max(mouse_pos[1] - th - 5, 5)
                    bg = pygame.Surface((tw, th), pygame.SRCALPHA)
                    bg.fill((30, 30, 50, 220))
                    pygame.draw.rect(bg, (150, 150, 150), (0, 0, tw, th), 1)
                    screen.blit(bg, (tx, ty))
                    for i, surf in enumerate(line_surfs):
                        screen.blit(surf, (tx + pad, ty + pad + i * line_h))
            except (TypeError, IndexError):
                pass

    def _draw_achievement_item(self, screen, rect, ach, icon_size, icon_margin):
        """Draw a single achievement list item with AchievementFull.png background."""
        is_earned = ach['earned']

        # Draw background
        item_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        if self.achievement_bg:
            # FPS OPTIMIZATION 5A: Cache scaled achievement background (same size for all items)
            ach_bg_size = (rect.width, rect.height)
            if self._cached_achievement_bg is None or self._cached_achievement_bg_size != ach_bg_size:
                self._cached_achievement_bg = pygame.transform.smoothscale(self.achievement_bg, ach_bg_size)
                self._cached_achievement_bg_size = ach_bg_size
            bg = self._cached_achievement_bg.copy()
            item_surface.blit(bg, (0, 0))
        else:
            item_surface.fill((40, 40, 55, 200))
            pygame.draw.rect(item_surface, BRASS_COLOR, (0, 0, rect.width, rect.height), 1)

        # Grey out if not earned
        if not is_earned:
            item_surface.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)

        # Hover highlight
        mouse_pos = pygame.mouse.get_pos()
        if rect.collidepoint(mouse_pos):
            item_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGB_ADD)

        screen.blit(item_surface, rect)

        # Achievement icon on left edge
        icon_x = rect.x + icon_margin
        icon_y = rect.y + (rect.height - icon_size) // 2 - int(5 * self.ui_scale)

        icon_img = self._icon_cache.get(ach['icon'])
        if icon_img:
            # FPS OPTIMIZATION 5A: Cache scaled achievement icons (keyed by icon path + size)
            icon_cache_key = (ach['icon'], icon_size)
            if icon_cache_key not in self._cached_scaled_icons:
                self._cached_scaled_icons[icon_cache_key] = pygame.transform.smoothscale(icon_img, (icon_size, icon_size))
            scaled_icon = self._cached_scaled_icons[icon_cache_key].copy()
            if not is_earned:
                # Darken the icon too
                scaled_icon.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(scaled_icon, (icon_x, icon_y))

        # Icon border
        if self.icon_border:
            # FPS OPTIMIZATION 5A: Cache scaled icon border (same size for all items)
            if self._cached_icon_border is None or self._cached_icon_border_size != icon_size:
                self._cached_icon_border = pygame.transform.smoothscale(self.icon_border, (icon_size, icon_size))
                self._cached_icon_border_size = icon_size
            border = self._cached_icon_border.copy()
            if not is_earned:
                border.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(border, (icon_x, icon_y))

        # Text area (to the right of icon)
        text_x = icon_x + icon_size + int(15 * self.ui_scale)
        text_max_w = rect.right - text_x - int(10 * self.ui_scale)

        # Achievement name (top of the bright area)
        name_color = BRASS_COLOR if is_earned else (120, 110, 50)
        name_surf = self.name_font.render(ach['name'], True, name_color)
        name_y = rect.y + int(12 * self.ui_scale)
        screen.blit(name_surf, (text_x, name_y))

        # Description (below name) - word-wrap if too long, shrink font if needed
        desc_color = DESCRIPTION_COLOR if is_earned else (130, 130, 130)
        desc_y = name_y + name_surf.get_height() + int(4 * self.ui_scale)

        # Calculate max vertical space for description (above reward text area)
        reward_text = self._get_reward_text(ach)
        reward_reserve = int(25 * self.ui_scale) if reward_text else int(10 * self.ui_scale)
        desc_max_h = (rect.y + rect.height - reward_reserve) - desc_y

        # Use normal font for single-line descriptions, small font for multi-line
        desc_lines = self._wrap_text(ach['description'], self.desc_font, text_max_w)
        if len(desc_lines) > 1:
            # Switch to smaller font for consistent multi-line appearance
            desc_lines = self._wrap_text(ach['description'], self.desc_font_small, text_max_w)
            line_h = self.desc_font_small.get_linesize()
            use_font = self.desc_font_small
        else:
            line_h = self.desc_font.get_linesize()
            use_font = self.desc_font

        for line in desc_lines:
            line_surf = use_font.render(line, True, desc_color)
            screen.blit(line_surf, (text_x, desc_y))
            desc_y += line_h

        # Reward text in bottom dark band
        if reward_text:
            reward_color = REWARD_TEXT_COLOR if is_earned else (100, 90, 50)
            reward_surf = self.reward_font.render(reward_text, True, reward_color)
            reward_y = rect.y + rect.height - reward_surf.get_height() - int(12 * self.ui_scale)
            screen.blit(reward_surf, (text_x, reward_y))

    @staticmethod
    def _get_reward_text(ach):
        """Get reward display text for an achievement. Supports dual rewards (reward_type_2)."""
        parts = []
        # Primary reward
        if ach['reward_type'] == 'title':
            parts.append(f"\"{ach['reward_id']}\" Title")
        elif ach['reward_type'] == 'icon':
            icon_name = ach.get('reward_name', 'Exclusive Icon')
            parts.append(icon_name)
        # Secondary reward (dual-reward achievements like Conqueror, Devastator)
        if ach.get('reward_type_2') == 'title':
            parts.append(f"\"{ach['reward_id_2']}\" Title")
        elif ach.get('reward_type_2') == 'icon':
            icon_name = ach.get('reward_name_2', 'Exclusive Icon')
            parts.append(icon_name)
        if not parts:
            return None
        return "Reward: " + " + ".join(parts)

    @staticmethod
    def _wrap_text(text, font, max_width):
        """Word-wrap text to fit within max_width. Returns list of line strings."""
        words = text.split(' ')
        lines = []
        current_line = ''
        for word in words:
            test_line = (current_line + ' ' + word).strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines if lines else [text]

    def _draw_scroll_indicator(self, screen, x, y, width, height, total_content):
        """Draw a scroll position indicator bar."""
        if total_content <= 0:
            return
        # Indicator height proportional to visible area
        visible_ratio = height / total_content
        indicator_height = max(int(20 * self.ui_scale), int(height * visible_ratio))
        # Indicator position proportional to scroll offset
        scroll_range = total_content - height
        if scroll_range > 0:
            scroll_ratio = self.scroll_offset / scroll_range
        else:
            scroll_ratio = 0
        indicator_y = y + int((height - indicator_height) * scroll_ratio)

        # Draw track
        track_rect = pygame.Rect(x, y, width, height)
        # A3 fix: use RGB only — alpha in RGBA is ignored on non-SRCALPHA screen surface
        pygame.draw.rect(screen, (60, 60, 80), track_rect, border_radius=2)
        # Draw indicator
        indicator_rect = pygame.Rect(x, indicator_y, width, indicator_height)
        pygame.draw.rect(screen, (150, 150, 170), indicator_rect, border_radius=2)

    def get_element_at(self, pos):
        """Get the UI element ID at the given position (for hover detection)."""
        for elem_id, elem in self.ui_elements.items():
            if elem['rect'].collidepoint(pos):
                return elem_id
        return None
