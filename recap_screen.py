# -*- coding: utf-8 -*-
# recap_screen.py
# Post-game recap/statistics screen with tabbed table UI

"""
Post-Game Recap Screen
======================

Displays cumulative game statistics in a tabbed table layout after each game ends.
Modeled after MissionScreen in campaign_screen.py (same background, tabs, panel style).

4 tabs: General, Units, Buildings, Economy
Each tab shows a sortable table with player rows and stat columns.
"""

import pygame
import sys
import random
import math
from config.constants import WHITE, BLACK, PLAYER_COLORS
from global_sound import sound_manager
from utils.surface_utils import crop_to_opaque

# Brass gold color for headers (matching campaign_screen)
BRASS_COLOR = (181, 166, 66)
# Winner highlight color
WINNER_GOLD = (255, 215, 0)

# Glitter particle gold shades (5 shades from dark to bright)
GLITTER_SHADES = [
    (139, 101, 8),    # Dark gold/bronze
    (184, 134, 11),   # Medium gold
    (218, 165, 32),   # Goldenrod
    (238, 201, 0),    # Bright gold
    (255, 223, 0),    # Light gold/yellow
]


class RecapScreen:
    """
    Post-game statistics screen showing 4 tabs of player performance data.
    Uses the same UI pattern as MissionScreen (CampaignBG + CampaignBTN tabs + OptionsMenuBG panel).
    """

    # Tab definitions
    TABS = ['general', 'units', 'buildings', 'economy']
    TAB_LABELS = {
        'general': 'General',
        'units': 'Units',
        'buildings': 'Buildings',
        'economy': 'Economy',
    }

    # Column definitions per tab: list of (display_header, stat_key)
    TAB_COLUMNS = {
        'general': [
            ('Territories Owned', 'territories_owned'),
            ('Units Trained', 'units_trained'),
            ('Heroes Trained', 'heroes_trained'),
            ('Gold Acquired', 'gold_acquired'),
        ],
        'units': [
            ('Units Trained', 'units_trained'),
            ('Units Killed', 'units_killed'),
            ('Heroes Trained', 'heroes_trained'),
            ('Heroes Killed', 'heroes_killed'),
        ],
        'buildings': [
            ('Econ. Buildings', 'economy_buildings_built'),
            ('Barracks Built', 'barracks_built'),
            ('Keeps Built', 'keeps_built'),
            ('Buildings Destroyed', 'buildings_destroyed'),
        ],
        'economy': [
            ('Gold Acquired', 'gold_acquired'),
            ('Gold Spent', 'gold_spent'),
            ('Gold Lost to Tax', 'gold_lost_to_taxation'),
            ('Max Income/Turn', 'max_income_per_turn'),
        ],
    }

    def __init__(self, screen, player_stats, player_names, player_colors, winner_index, num_players,
                 newly_earned_achievements=None, xp_result=None):
        """
        Args:
            screen: Pygame display surface
            player_stats: {player_index: {stat_name: value}} from get_end_game_stats()
            player_names: List of player name strings
            player_colors: List of player color tuples
            winner_index: Index of winning player (-1 if no winner)
            num_players: Total number of players
            newly_earned_achievements: List of achievement dicts earned this game (or None)
            xp_result: Dict from player_level_manager.record_game_xp() with xp_earned,
                       old_level, new_level, old_xp, new_xp (or None)
        """
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        self.clock = pygame.time.Clock()
        self.player_stats = player_stats
        self.player_names = player_names
        self.player_colors = player_colors
        self.winner_index = winner_index
        self.num_players = num_players

        # State
        self.done = False
        self.result = None
        self.selected_tab = 'general'
        self.hovered_button = None
        self.clicked_button = None

        # Sort state (default: first column, descending)
        self.sort_column = 0
        self.sort_ascending = False

        # UI scale (matching campaign_screen pattern)
        self.ui_scale = self.height / 1080.0

        # Load assets
        self.bg_image = pygame.image.load("assets/CampaignBG.png").convert()
        self.bg_image = pygame.transform.smoothscale(self.bg_image, (self.width, self.height))

        raw_btn_image = pygame.image.load("assets/CampaignBTN.png").convert_alpha()
        self.btn_image = crop_to_opaque(raw_btn_image, threshold=128)

        self.panel_image = pygame.image.load("assets/OptionsMenuBG.png").convert_alpha()

        # Button aspect ratio from cropped image
        btn_img_w, btn_img_h = self.btn_image.get_size()
        self.btn_aspect = btn_img_h / btn_img_w

        # --- Layout calculations ---

        # Top tab buttons (4 across, centered)
        tab_btn_width = int(350 * self.ui_scale)
        tab_btn_height = int(tab_btn_width * self.btn_aspect)
        tab_spacing = int(15 * self.ui_scale)
        total_tabs_width = 4 * tab_btn_width + 3 * tab_spacing
        tab_start_x = (self.width - total_tabs_width) // 2
        tab_y = int(30 * self.ui_scale)

        self.tab_buttons = {}
        for i, tab_id in enumerate(self.TABS):
            x = tab_start_x + i * (tab_btn_width + tab_spacing)
            self.tab_buttons[tab_id] = pygame.Rect(x, tab_y, tab_btn_width, tab_btn_height)

        # Bottom button (right side only - Main Menu)
        bottom_btn_width = int(400 * self.ui_scale)
        bottom_btn_height = int(bottom_btn_width * self.btn_aspect)
        bottom_y = self.height - bottom_btn_height - int(30 * self.ui_scale)
        bottom_margin = int(40 * self.ui_scale)

        self.return_button_rect = pygame.Rect(
            self.width - bottom_btn_width - bottom_margin, bottom_y,
            bottom_btn_width, bottom_btn_height
        )

        # Content panel (between tabs and bottom button)
        panel_margin = int(60 * self.ui_scale)
        panel_top = tab_y + tab_btn_height + int(20 * self.ui_scale)
        panel_bottom = bottom_y - int(20 * self.ui_scale)
        self.panel_rect = pygame.Rect(
            panel_margin, panel_top,
            self.width - 2 * panel_margin, panel_bottom - panel_top
        )

        # Table area inside panel (asymmetric padding for ornate border + extra table padding)
        table_pad_left = int(205 * self.ui_scale)   # 100 base + 40 + 30 + 20 + 15 extra
        table_pad_right = int(185 * self.ui_scale)   # 80 base + 40 + 30 + 20 + 15 extra
        table_pad_top = int(140 * self.ui_scale)     # 120 base + 20 extra
        table_pad_bottom = int(100 * self.ui_scale)
        self.table_rect = pygame.Rect(
            self.panel_rect.x + table_pad_left,
            self.panel_rect.y + table_pad_top,
            self.panel_rect.width - table_pad_left - table_pad_right,
            self.panel_rect.height - table_pad_top - table_pad_bottom
        )

        # Fonts
        self.tab_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(14, int(22 * self.ui_scale)))
        self.btn_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(16, int(24 * self.ui_scale)))
        self.header_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', max(14, int(20 * self.ui_scale)))
        self.data_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(18, int(30 * self.ui_scale)))
        self.title_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', max(18, int(28 * self.ui_scale)))

        # Header click rects (recalculated in _draw_table)
        self.header_rects = []

        # Pre-cache scaled panel
        self._scaled_panel = pygame.transform.smoothscale(
            self.panel_image, (self.panel_rect.width, self.panel_rect.height)
        )
        self._scaled_panel.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

        # --- Achievement preview popup state ---
        self.newly_earned = newly_earned_achievements or []
        self.current_achievement_index = 0
        self.achievement_preview_phase = 'waiting'  # waiting -> showing -> fading -> done
        self.achievement_preview_timer = 0.0
        self.achievement_preview_alpha = 0
        self.achievement_show_delay = 1.5   # seconds before first popup
        self.achievement_display_time = 3.0  # seconds each achievement shows
        self.achievement_fade_in_time = 0.3  # fade-in duration
        self.achievement_fade_time = 0.5     # fade-out duration

        # Glitter particles around the achievement preview
        self.glitter_particles = []
        self.glitter_spawn_accum = 0.0
        self.glitter_spawn_rate = 60  # particles per second

        # Pre-load achievement preview assets
        self.achievement_preview_bg = None
        self.achievement_preview_icons = []
        self.achievement_preview_font = pygame.font.Font(
            'assets/fonts/Cinzel-SemiBold.ttf', max(16, int(24 * self.ui_scale)))
        self.achievement_name_font = pygame.font.Font(
            'assets/fonts/Cinzel-Regular.ttf', max(18, int(26 * self.ui_scale)))
        if self.newly_earned:
            try:
                self.achievement_preview_bg = pygame.image.load(
                    'assets/achievements/AchievementPreview.png').convert_alpha()
            except Exception as e:
                pass  # Fallback to solid color
            # Pre-load icon for each newly earned achievement
            for ach in self.newly_earned:
                try:
                    icon = pygame.image.load(ach['icon']).convert_alpha()
                    self.achievement_preview_icons.append(icon)
                except Exception:
                    self.achievement_preview_icons.append(None)
            # Pre-load icon border for achievement icons
            try:
                self.achievement_icon_border = pygame.image.load(
                    'assets/mapicons/IconBorder.png').convert_alpha()
            except Exception:
                self.achievement_icon_border = None

        # --- Player Level XP bar state (shown after achievement popups) ---
        self.xp_result = xp_result
        self.xp_bar_phase = 'xp_waiting'  # xp_waiting -> xp_fading_in -> xp_filling -> xp_showing -> xp_fading -> xp_done
        self.xp_bar_timer = 0.0
        self.xp_bar_alpha = 0
        self.xp_bar_fill_progress = 0.0  # 0.0 to 1.0 animation progress
        self.xp_bar_anim_level = 0       # Animated level (tracks level changes during fill)
        self.xp_level_up_particles = []  # Golden burst particles on level-up
        self.xp_level_up_spawn_accum = 0.0

    def run(self):
        """Main loop - blocks until user clicks Main Menu."""
        while not self.done:
            dt = self.clock.tick(60) / 1000.0
            self._update_achievement_preview(dt)
            self._update_xp_bar(dt)
            self.handle_events()
            self.render()
            pygame.display.flip()
        return self.result

    def handle_events(self):
        """Process input events."""
        mouse_pos = pygame.mouse.get_pos()

        # Update hover state
        self.hovered_button = None
        if self.return_button_rect.collidepoint(mouse_pos):
            self.hovered_button = 'return'
        else:
            for tab_id, rect in self.tab_buttons.items():
                if rect.collidepoint(mouse_pos):
                    self.hovered_button = tab_id
                    break
            else:
                # Check header rects for hover cursor
                for i, rect in enumerate(self.header_rects):
                    if rect.collidepoint(mouse_pos):
                        self.hovered_button = f'header_{i}'
                        break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # H12 fix: graceful exit instead of hard sys.exit()
                self.result = 'main_menu'
                self.done = True
                return

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.result = 'main_menu'
                    self.done = True

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Return button
                    if self.return_button_rect.collidepoint(mouse_pos):
                        sound_manager.play_ui_click()
                        self.clicked_button = 'return'
                        self.result = 'main_menu'
                        self.done = True
                        return

                    # Tab buttons
                    for tab_id, rect in self.tab_buttons.items():
                        if rect.collidepoint(mouse_pos):
                            sound_manager.play_ui_click()
                            self.clicked_button = tab_id
                            if self.selected_tab != tab_id:
                                self.selected_tab = tab_id
                                # Reset sort to first column descending on tab change
                                self.sort_column = 0
                                self.sort_ascending = False
                            break
                    else:
                        # Column header clicks for sorting
                        for i, rect in enumerate(self.header_rects):
                            if rect.collidepoint(mouse_pos):
                                sound_manager.play_ui_click()
                                if self.sort_column == i:
                                    # Same column: toggle direction
                                    self.sort_ascending = not self.sort_ascending
                                else:
                                    # New column: set as sort, descending
                                    self.sort_column = i
                                    self.sort_ascending = False
                                break

    def render(self):
        """Render the full recap screen."""
        # Background
        self.screen.blit(self.bg_image, (0, 0))

        # Tab buttons
        for tab_id, rect in self.tab_buttons.items():
            self._draw_btn(rect, self.TAB_LABELS[tab_id], tab_id,
                           self.tab_font, is_selected=(tab_id == self.selected_tab))

        # Content panel
        self.screen.blit(self._scaled_panel, self.panel_rect)

        # Table content
        self._draw_table()

        # Bottom button
        self._draw_btn(self.return_button_rect, 'Main Menu', 'return', self.btn_font)

        # Achievement preview popup (drawn on top of everything)
        self._draw_achievement_preview()

        # Player Level XP bar (drawn after/instead of achievement preview)
        self._draw_xp_bar()

        # Reset clicked state after render
        self.clicked_button = None

    def _draw_btn(self, rect, text, btn_id, font, is_selected=False):
        """Draw a CampaignBTN.png-based button with hover/click/selected states."""
        is_hovered = (self.hovered_button == btn_id)
        is_clicked = (self.clicked_button == btn_id)

        scaled_bg = pygame.transform.smoothscale(self.btn_image, (rect.width, rect.height))
        button_surface = scaled_bg.copy()

        if is_selected:
            # Selected tab: brighter base
            button_surface.fill((140, 140, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            # Normal darkened base
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

        if is_clicked:
            button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
        elif is_hovered:
            button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.screen.blit(button_surface, rect)

        # Text
        text_surface = font.render(text, True, WHITE)
        text_r = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_r)

    def _get_sorted_players(self, columns):
        """Return list of player indices sorted by current sort column."""
        stat_key = columns[self.sort_column][1]
        players = list(range(self.num_players))
        players.sort(
            key=lambda p: self.player_stats.get(p, {}).get(stat_key, 0),
            reverse=not self.sort_ascending
        )
        return players

    def _draw_table(self):
        """Render the statistics table for the current tab."""
        columns = self.TAB_COLUMNS[self.selected_tab]

        content_x = self.table_rect.x
        content_y = self.table_rect.y
        content_w = self.table_rect.width
        row_height = int(88 * self.ui_scale)

        # Column layout: player name column + 4 data columns
        name_col_width = int(content_w * 0.28)
        data_col_total = content_w - name_col_width
        data_col_width = data_col_total // len(columns)

        # --- Draw header row ---
        header_y = content_y
        self.header_rects = []

        # "Player" label in name column
        player_label = self.header_font.render("Player", True, BRASS_COLOR)
        self.screen.blit(player_label, (content_x + int(10 * self.ui_scale), header_y + int(8 * self.ui_scale)))

        # Column headers (clickable)
        for col_idx, (header_text, stat_key) in enumerate(columns):
            col_x = content_x + name_col_width + col_idx * data_col_width
            header_rect = pygame.Rect(col_x, header_y, data_col_width, row_height)
            self.header_rects.append(header_rect)

            # Hover highlight on header
            if self.hovered_button == f'header_{col_idx}':
                hover_surf = pygame.Surface((data_col_width, row_height), pygame.SRCALPHA)
                hover_surf.fill((255, 255, 255, 20))
                self.screen.blit(hover_surf, (col_x, header_y))

            # Header text (centered in column)
            header_surf = self.header_font.render(header_text, True, BRASS_COLOR)
            text_r = header_surf.get_rect(center=(col_x + data_col_width // 2, header_y + row_height // 2))
            self.screen.blit(header_surf, text_r)

            # Sort indicator arrow (drawn as triangle polygon)
            if self.sort_column == col_idx:
                arrow_size = int(8 * self.ui_scale)
                arrow_cx = text_r.right + int(10 * self.ui_scale)
                arrow_cy = header_y + row_height // 2
                if self.sort_ascending:
                    # Up arrow: ▲
                    points = [
                        (arrow_cx, arrow_cy - arrow_size),
                        (arrow_cx - arrow_size, arrow_cy + arrow_size),
                        (arrow_cx + arrow_size, arrow_cy + arrow_size),
                    ]
                else:
                    # Down arrow: ▼
                    points = [
                        (arrow_cx, arrow_cy + arrow_size),
                        (arrow_cx - arrow_size, arrow_cy - arrow_size),
                        (arrow_cx + arrow_size, arrow_cy - arrow_size),
                    ]
                pygame.draw.polygon(self.screen, WINNER_GOLD, points)

        # Header divider line
        divider_y = header_y + row_height
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (content_x, divider_y), (content_x + content_w, divider_y), 1)

        # --- Draw player rows ---
        sorted_players = self._get_sorted_players(columns)

        for row_idx, player_idx in enumerate(sorted_players):
            row_y = divider_y + int(4 * self.ui_scale) + row_idx * row_height

            # Stop if we'd draw below the table area
            if row_y + row_height > self.table_rect.y + self.table_rect.height:
                break

            # Alternating row background
            if row_idx % 2 == 0:
                row_bg = pygame.Surface((content_w, row_height), pygame.SRCALPHA)
                row_bg.fill((255, 255, 255, 12))
                self.screen.blit(row_bg, (content_x, row_y))

            # Winner highlight (gold border around row)
            if player_idx == self.winner_index:
                winner_rect = pygame.Rect(content_x, row_y, content_w, row_height)
                pygame.draw.rect(self.screen, WINNER_GOLD, winner_rect, 2)

            # Player color dot
            dot_radius = int(12 * self.ui_scale)
            dot_x = content_x + int(10 * self.ui_scale) + dot_radius
            dot_y = row_y + row_height // 2
            color = self.player_colors[player_idx] if player_idx < len(self.player_colors) else (150, 150, 150)
            pygame.draw.circle(self.screen, color, (dot_x, dot_y), dot_radius)

            # Player name
            name = self.player_names[player_idx] if player_idx < len(self.player_names) else f"Player {player_idx + 1}"
            name_surf = self.data_font.render(name, True, WHITE)
            name_x = dot_x + dot_radius + int(10 * self.ui_scale)
            # Clip name if too long
            max_name_width = name_col_width - (name_x - content_x) - int(5 * self.ui_scale)
            if name_surf.get_width() > max_name_width:
                # Truncate with ellipsis
                truncated = name
                while self.data_font.size(truncated + "...")[0] > max_name_width and len(truncated) > 1:
                    truncated = truncated[:-1]
                name_surf = self.data_font.render(truncated + "...", True, WHITE)
            name_y = row_y + row_height // 2 - name_surf.get_height() // 2
            self.screen.blit(name_surf, (name_x, name_y))

            # Data columns (right-aligned numbers)
            stats = self.player_stats.get(player_idx, {})
            for col_idx, (header_text, stat_key) in enumerate(columns):
                col_x = content_x + name_col_width + col_idx * data_col_width
                value = stats.get(stat_key, 0)
                # Format number with comma separators for readability
                value_text = f"{value:,}"
                value_surf = self.data_font.render(value_text, True, WHITE)
                # Right-align within column (with right padding)
                value_x = col_x + data_col_width - value_surf.get_width() - int(15 * self.ui_scale)
                value_y = row_y + row_height // 2 - value_surf.get_height() // 2
                self.screen.blit(value_surf, (value_x, value_y))

    def _update_achievement_preview(self, dt):
        """Update achievement preview popup animation state machine and glitter particles."""
        if not self.newly_earned or self.current_achievement_index >= len(self.newly_earned):
            # Let remaining glitter particles finish their lifecycle after preview is done
            if self.glitter_particles:
                for p in self.glitter_particles:
                    p['age'] += dt
                    p['x'] += p['vx'] * dt
                    p['y'] += p['vy'] * dt
                self.glitter_particles = [p for p in self.glitter_particles if p['age'] < p['lifetime']]
            return

        self.achievement_preview_timer += dt

        if self.achievement_preview_phase == 'waiting':
            # Initial delay before first achievement popup
            if self.achievement_preview_timer >= self.achievement_show_delay:
                self.achievement_preview_phase = 'fading_in'
                self.achievement_preview_timer = 0.0
                self.achievement_preview_alpha = 0

        elif self.achievement_preview_phase == 'fading_in':
            # Fade in over achievement_fade_in_time
            progress = min(1.0, self.achievement_preview_timer / self.achievement_fade_in_time)
            self.achievement_preview_alpha = int(255 * progress)
            if progress >= 1.0:
                self.achievement_preview_phase = 'showing'
                self.achievement_preview_timer = 0.0
                self.achievement_preview_alpha = 255

        elif self.achievement_preview_phase == 'showing':
            # Hold at full visibility
            if self.achievement_preview_timer >= self.achievement_display_time:
                self.achievement_preview_phase = 'fading'
                self.achievement_preview_timer = 0.0

        elif self.achievement_preview_phase == 'fading':
            # Fade out over achievement_fade_time
            progress = min(1.0, self.achievement_preview_timer / self.achievement_fade_time)
            self.achievement_preview_alpha = max(0, int(255 * (1.0 - progress)))
            if progress >= 1.0:
                # Move to next achievement
                self.current_achievement_index += 1
                if self.current_achievement_index < len(self.newly_earned):
                    self.achievement_preview_phase = 'fading_in'
                    self.achievement_preview_timer = 0.0
                    self.achievement_preview_alpha = 0
                else:
                    self.achievement_preview_phase = 'done'

        # Update glitter particles during visible phases
        if self.achievement_preview_phase in ('fading_in', 'showing', 'fading'):
            self._update_glitter_particles(dt)

    def _draw_achievement_preview(self):
        """Draw the achievement preview popup at bottom-center of screen."""
        # Draw any trailing glitter particles even after preview is gone
        if self.glitter_particles and self.achievement_preview_phase == 'done':
            preview_w = int(450 * self.ui_scale)
            preview_h = int(100 * self.ui_scale)
            preview_x = (self.width - preview_w) // 2
            preview_y = self.height - preview_h - int(40 * self.ui_scale)
            self._draw_glitter_particles(preview_x, preview_y, preview_w, preview_h)

        if (not self.newly_earned or
                self.current_achievement_index >= len(self.newly_earned) or
                self.achievement_preview_phase in ('waiting', 'done')):
            return

        ach = self.newly_earned[self.current_achievement_index]

        # Preview dimensions and position (bottom-center)
        preview_w = int(450 * self.ui_scale)
        preview_h = int(100 * self.ui_scale)
        preview_x = (self.width - preview_w) // 2
        preview_y = self.height - preview_h - int(40 * self.ui_scale)

        # Build preview surface
        preview = pygame.Surface((preview_w, preview_h), pygame.SRCALPHA)
        if self.achievement_preview_bg:
            bg = pygame.transform.smoothscale(self.achievement_preview_bg, (preview_w, preview_h))
            preview.blit(bg, (0, 0))
        else:
            # Fallback: dark semi-transparent background
            preview.fill((30, 30, 45, 220))
            pygame.draw.rect(preview, BRASS_COLOR, (0, 0, preview_w, preview_h), 2)

        # Achievement icon on left
        icon_size = int(60 * self.ui_scale)
        icon_margin = int(18 * self.ui_scale)
        icon_y_offset = (preview_h - icon_size) // 2
        icon = self.achievement_preview_icons[self.current_achievement_index]
        if icon:
            scaled_icon = pygame.transform.smoothscale(icon, (icon_size, icon_size))
            preview.blit(scaled_icon, (icon_margin, icon_y_offset))
        # Icon border overlay
        if self.achievement_icon_border:
            border = pygame.transform.smoothscale(self.achievement_icon_border, (icon_size, icon_size))
            preview.blit(border, (icon_margin, icon_y_offset))

        # Text area to the right of icon
        text_x = icon_margin + icon_size + int(15 * self.ui_scale)

        # "Achievement Earned:" header
        header_surf = self.achievement_preview_font.render("Achievement Earned:", True, BRASS_COLOR)
        preview.blit(header_surf, (text_x, int(20 * self.ui_scale)))

        # Achievement name
        name_surf = self.achievement_name_font.render(ach['name'], True, WHITE)
        preview.blit(name_surf, (text_x, int(52 * self.ui_scale)))

        # Draw glitter particles behind the preview (underneath)
        self._draw_glitter_particles(preview_x, preview_y, preview_w, preview_h)

        # Apply fade alpha
        preview.set_alpha(self.achievement_preview_alpha)
        self.screen.blit(preview, (preview_x, preview_y))

    def _update_glitter_particles(self, dt):
        """Spawn and age glitter particles around the achievement preview."""
        # Spawn new particles along the preview border
        self.glitter_spawn_accum += dt
        to_spawn = int(self.glitter_spawn_accum * self.glitter_spawn_rate)
        self.glitter_spawn_accum -= to_spawn / self.glitter_spawn_rate

        # Preview rect (must match _draw_achievement_preview dimensions)
        preview_w = int(450 * self.ui_scale)
        preview_h = int(100 * self.ui_scale)
        preview_x = (self.width - preview_w) // 2
        preview_y = self.height - preview_h - int(40 * self.ui_scale)

        margin = int(20 * self.ui_scale)  # How far outside the preview particles can spawn

        for _ in range(to_spawn):
            # Spawn particles around the perimeter of the preview box (with margin)
            side = random.choice(['top', 'bottom', 'left', 'right'])
            if side == 'top':
                x = random.uniform(preview_x - margin, preview_x + preview_w + margin)
                y = random.uniform(preview_y - margin, preview_y)
            elif side == 'bottom':
                x = random.uniform(preview_x - margin, preview_x + preview_w + margin)
                y = random.uniform(preview_y + preview_h, preview_y + preview_h + margin)
            elif side == 'left':
                x = random.uniform(preview_x - margin, preview_x)
                y = random.uniform(preview_y - margin, preview_y + preview_h + margin)
            else:  # right
                x = random.uniform(preview_x + preview_w, preview_x + preview_w + margin)
                y = random.uniform(preview_y - margin, preview_y + preview_h + margin)

            # Each particle drifts slowly outward and upward
            angle = math.atan2(y - (preview_y + preview_h / 2), x - (preview_x + preview_w / 2))
            speed = random.uniform(8, 25) * self.ui_scale
            self.glitter_particles.append({
                'x': x, 'y': y,
                'vx': math.cos(angle) * speed + random.uniform(-3, 3),
                'vy': math.sin(angle) * speed - random.uniform(5, 15) * self.ui_scale,  # Drift upward
                'color': random.choice(GLITTER_SHADES),
                'size': random.choice([1, 1, 1, 2]),  # Mostly 1px, occasional 2px
                'lifetime': random.uniform(0.4, 1.0),
                'age': 0.0,
                'max_alpha': random.randint(150, 255),
            })

        # Age particles and remove dead ones
        for p in self.glitter_particles:
            p['age'] += dt
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
        self.glitter_particles = [p for p in self.glitter_particles if p['age'] < p['lifetime']]

    def _draw_glitter_particles(self, preview_x, preview_y, preview_w, preview_h):
        """Draw glitter sparkle particles around the achievement preview."""
        if not self.glitter_particles:
            return

        # Use the overall preview alpha so glitter fades with the preview
        global_alpha = self.achievement_preview_alpha / 255.0

        # Small SRCALPHA surface covering the particle area (preview + margin)
        margin = int(40 * self.ui_scale)
        area_x = preview_x - margin
        area_y = preview_y - margin
        area_w = preview_w + margin * 2
        area_h = preview_h + margin * 2
        particle_surf = pygame.Surface((area_w, area_h), pygame.SRCALPHA)

        for p in self.glitter_particles:
            progress = p['age'] / p['lifetime']
            # Fade in (first 20%) -> hold -> fade out (last 40%)
            if progress < 0.2:
                opacity = progress / 0.2
            elif progress < 0.6:
                opacity = 1.0
            else:
                opacity = 1.0 - (progress - 0.6) / 0.4

            alpha = int(p['max_alpha'] * opacity * global_alpha)
            if alpha <= 0:
                continue

            r, g, b = p['color']
            # Convert to local surface coordinates
            lx = int(p['x'] - area_x)
            ly = int(p['y'] - area_y)
            if 0 <= lx < area_w and 0 <= ly < area_h:
                pygame.draw.circle(particle_surf, (r, g, b, alpha), (lx, ly), p['size'])

        self.screen.blit(particle_surf, (area_x, area_y))

    # --- Player Level XP Bar ---

    def _update_xp_bar(self, dt):
        """Update XP bar animation state machine (queued after achievement popups)."""
        # Skip if no XP earned this game
        if not self.xp_result or self.xp_result['xp_earned'] <= 0:
            # Still update level-up particles if any remain
            if self.xp_level_up_particles:
                self._age_xp_particles(dt)
            return

        if self.xp_bar_phase == 'xp_waiting':
            # Wait for achievement popups to finish (or start after delay if none)
            achievements_done = (not self.newly_earned or
                                 self.achievement_preview_phase == 'done')
            glitter_done = not self.glitter_particles
            if achievements_done and glitter_done:
                self.xp_bar_timer += dt
                # Small delay after achievements finish (or 1.5s if no achievements)
                wait_time = 0.5 if self.newly_earned else 1.5
                if self.xp_bar_timer >= wait_time:
                    self.xp_bar_phase = 'xp_fading_in'
                    self.xp_bar_timer = 0.0
                    self.xp_bar_alpha = 0
                    # Initialize animated level to the old level
                    self.xp_bar_anim_level = self.xp_result['old_level']
            return

        self.xp_bar_timer += dt

        if self.xp_bar_phase == 'xp_fading_in':
            progress = min(1.0, self.xp_bar_timer / 0.3)
            self.xp_bar_alpha = int(255 * progress)
            if progress >= 1.0:
                self.xp_bar_phase = 'xp_filling'
                self.xp_bar_timer = 0.0
                self.xp_bar_alpha = 255

        elif self.xp_bar_phase == 'xp_filling':
            # Animate fill over 2 seconds with ease-out curve for smooth deceleration
            t = min(1.0, self.xp_bar_timer / 2.0)
            # Cubic ease-out: fast start, gentle landing
            self.xp_bar_fill_progress = 1.0 - (1.0 - t) ** 3

            # Check for level-up during fill animation
            from player_level import level_from_xp
            old_xp = self.xp_result['old_xp']
            new_xp = self.xp_result['new_xp']
            current_animated_xp = old_xp + (new_xp - old_xp) * self.xp_bar_fill_progress
            current_animated_level = level_from_xp(int(current_animated_xp))

            # Trigger level-up burst when animated level increases
            if current_animated_level > self.xp_bar_anim_level:
                self.xp_bar_anim_level = current_animated_level
                self._spawn_xp_level_up_burst()

            if self.xp_bar_fill_progress >= 1.0:
                self.xp_bar_phase = 'xp_showing'
                self.xp_bar_timer = 0.0

        elif self.xp_bar_phase == 'xp_showing':
            if self.xp_bar_timer >= 3.0:
                self.xp_bar_phase = 'xp_fading'
                self.xp_bar_timer = 0.0

        elif self.xp_bar_phase == 'xp_fading':
            progress = min(1.0, self.xp_bar_timer / 0.5)
            self.xp_bar_alpha = max(0, int(255 * (1.0 - progress)))
            if progress >= 1.0:
                self.xp_bar_phase = 'xp_done'

        # Update level-up particles during visible phases
        if self.xp_bar_phase in ('xp_fading_in', 'xp_filling', 'xp_showing', 'xp_fading'):
            self._age_xp_particles(dt)

    def _draw_xp_bar(self):
        """Draw the XP bar popup at bottom-center of screen (same position as achievements)."""
        # Always draw remaining level-up particles even after bar is gone
        if self.xp_level_up_particles and self.xp_bar_phase == 'xp_done':
            bar_w = int(450 * self.ui_scale)
            bar_h = int(80 * self.ui_scale)
            bar_x = (self.width - bar_w) // 2
            bar_y = self.height - bar_h - int(40 * self.ui_scale)
            self._draw_xp_particles(bar_x, bar_y, bar_w, bar_h)
            return

        if (not self.xp_result or self.xp_result['xp_earned'] <= 0 or
                self.xp_bar_phase in ('xp_waiting', 'xp_done')):
            return

        from player_level import get_progress_for_xp

        # Bar dimensions (same position as achievement popup)
        bar_w = int(450 * self.ui_scale)
        bar_h = int(80 * self.ui_scale)
        bar_x = (self.width - bar_w) // 2
        bar_y = self.height - bar_h - int(40 * self.ui_scale)

        # Calculate current animated XP for the fill
        old_xp = self.xp_result['old_xp']
        new_xp = self.xp_result['new_xp']
        current_xp = old_xp + (new_xp - old_xp) * self.xp_bar_fill_progress
        progress_info = get_progress_for_xp(int(current_xp))

        # Build bar surface
        bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)

        # Background (dark semi-transparent, matching achievement popup style)
        bar_surf.fill((30, 30, 45, 220))
        pygame.draw.rect(bar_surf, BRASS_COLOR, (0, 0, bar_w, bar_h), 2)

        # Text: "Level: X (+Y Experience)" centered at top
        level_display = self.xp_result['new_level']
        xp_earned = self.xp_result['xp_earned']
        text_str = f"Level: {level_display} (+{xp_earned} Experience)"
        text_surf = self.achievement_preview_font.render(text_str, True, WHITE)
        text_rect = text_surf.get_rect(centerx=bar_w // 2, top=int(10 * self.ui_scale))
        bar_surf.blit(text_surf, text_rect)

        # Inner progress bar
        inner_margin_x = int(20 * self.ui_scale)
        inner_h = int(24 * self.ui_scale)
        inner_y = bar_h - inner_h - int(14 * self.ui_scale)
        inner_w = bar_w - 2 * inner_margin_x
        inner_rect = pygame.Rect(inner_margin_x, inner_y, inner_w, inner_h)

        # Progress bar background
        pygame.draw.rect(bar_surf, (20, 20, 20), inner_rect, border_radius=4)

        # Gold fill based on current animated progress within current level
        fill_fraction = progress_info['progress_fraction']
        fill_width = int(inner_w * fill_fraction)
        if fill_width > 0:
            # Draw gold fill clipped to rounded rect
            fill_surf = pygame.Surface((inner_w, inner_h), pygame.SRCALPHA)
            pygame.draw.rect(fill_surf, (184, 134, 11), (0, 0, fill_width, inner_h), border_radius=4)
            # Clip to the rounded inner rect shape
            mask_surf = pygame.Surface((inner_w, inner_h), pygame.SRCALPHA)
            pygame.draw.rect(mask_surf, (255, 255, 255, 255), (0, 0, inner_w, inner_h), border_radius=4)
            fill_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            bar_surf.blit(fill_surf, inner_rect.topleft)

        # Progress bar border
        pygame.draw.rect(bar_surf, (100, 100, 100), inner_rect, 1, border_radius=4)

        # Draw level-up particles behind the bar
        self._draw_xp_particles(bar_x, bar_y, bar_w, bar_h)

        # Apply fade alpha and blit
        bar_surf.set_alpha(self.xp_bar_alpha)
        self.screen.blit(bar_surf, (bar_x, bar_y))

    def _spawn_xp_level_up_burst(self):
        """Spawn a burst of golden particles when the player levels up during the fill animation."""
        # Burst from the center of the XP bar
        bar_w = int(450 * self.ui_scale)
        bar_h = int(80 * self.ui_scale)
        bar_x = (self.width - bar_w) // 2
        bar_y = self.height - bar_h - int(40 * self.ui_scale)
        center_x = bar_x + bar_w // 2
        center_y = bar_y + bar_h // 2

        # Spawn ~100 particles exploding outward from center
        for _ in range(100):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(40, 160) * self.ui_scale
            self.xp_level_up_particles.append({
                'x': center_x + random.uniform(-10, 10),
                'y': center_y + random.uniform(-10, 10),
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed - random.uniform(10, 30) * self.ui_scale,  # Slight upward bias
                'color': random.choice(GLITTER_SHADES),
                'size': random.choice([1, 1, 2, 2, 3]),  # Larger particles for level-up
                'lifetime': random.uniform(0.6, 1.2),
                'age': 0.0,
                'max_alpha': random.randint(180, 255),
            })

    def _age_xp_particles(self, dt):
        """Age and remove dead level-up particles."""
        for p in self.xp_level_up_particles:
            p['age'] += dt
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
            # Decelerate over time
            p['vx'] *= 0.97
            p['vy'] *= 0.97
        self.xp_level_up_particles = [p for p in self.xp_level_up_particles if p['age'] < p['lifetime']]

    def _draw_xp_particles(self, bar_x, bar_y, bar_w, bar_h):
        """Draw golden level-up burst particles around the XP bar."""
        if not self.xp_level_up_particles:
            return

        global_alpha = self.xp_bar_alpha / 255.0 if self.xp_bar_alpha > 0 else 1.0

        # Particle area covers the bar + generous margin for the burst
        margin = int(80 * self.ui_scale)
        area_x = bar_x - margin
        area_y = bar_y - margin
        area_w = bar_w + margin * 2
        area_h = bar_h + margin * 2
        particle_surf = pygame.Surface((area_w, area_h), pygame.SRCALPHA)

        for p in self.xp_level_up_particles:
            progress = p['age'] / p['lifetime']
            # Quick fade in, then gradual fade out
            if progress < 0.1:
                opacity = progress / 0.1
            elif progress < 0.4:
                opacity = 1.0
            else:
                opacity = 1.0 - (progress - 0.4) / 0.6

            alpha = int(p['max_alpha'] * opacity * global_alpha)
            if alpha <= 0:
                continue

            r, g, b = p['color']
            lx = int(p['x'] - area_x)
            ly = int(p['y'] - area_y)
            if 0 <= lx < area_w and 0 <= ly < area_h:
                pygame.draw.circle(particle_surf, (r, g, b, alpha), (lx, ly), p['size'])

        self.screen.blit(particle_surf, (area_x, area_y))
