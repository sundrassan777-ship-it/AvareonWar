"""Floating chat notification effect — shows new chat messages briefly on the map area.

Messages appear in the top-left of the map, just below the top panel. They fade out
after 5 seconds and stack vertically (max 5 visible at once).
"""

import pygame

# Timing
MAX_VISIBLE = 5
DISPLAY_DURATION = 5.0   # seconds at full opacity
FADE_DURATION = 1.0      # seconds to fade out after display
TOTAL_DURATION = DISPLAY_DURATION + FADE_DURATION

# Layout
PADDING_X = 8
PADDING_Y = 4
MARGIN_LEFT = 12
MARGIN_TOP = 8
LINE_SPACING = 4

# Colors
BG_COLOR = (20, 20, 20)
BG_ALPHA = 170
MSG_COLOR = (255, 255, 255)
TEAM_TAG_COLOR = (100, 200, 255)


class ChatNotificationEffect:
    """Manages floating chat message notifications on the map area."""

    def __init__(self, top_panel_height, game_state, viewer_player_id, font, font_bold):
        self.top_panel_height = top_panel_height
        self.game_state = game_state
        self.viewer_player_id = viewer_player_id
        self.font = font
        self.font_bold = font_bold
        self._notifications = []  # list of notification dicts
        self._last_chat_count = len(game_state.chat_messages)
        # Max text width — calculated lazily from screen width
        self._max_text_width = 500

    def update(self, delta_time):
        """Poll for new chat messages, age existing notifications, remove expired ones."""
        # Check for new messages
        current_count = len(self.game_state.chat_messages)
        if current_count > self._last_chat_count:
            for i in range(self._last_chat_count, current_count):
                chat_msg = self.game_state.chat_messages[i]
                # Filter visibility (team messages only for allies)
                if self.game_state.is_chat_visible_to_player(chat_msg, self.viewer_player_id):
                    notif = self._create_notification(chat_msg)
                    if notif:
                        self._notifications.append(notif)
            self._last_chat_count = current_count

        # Enforce max visible — pop oldest when over limit
        while len(self._notifications) > MAX_VISIBLE:
            self._notifications.pop(0)

        # Age notifications and remove expired
        self._notifications = [
            n for n in self._notifications
            if self._age_notification(n, delta_time)
        ]

    def _age_notification(self, notif, delta_time):
        """Advance elapsed time. Returns False if notification has expired."""
        notif['elapsed'] += delta_time
        return notif['elapsed'] < TOTAL_DURATION

    def render(self, screen):
        """Draw stacked notifications at top-left of map area."""
        if not self._notifications:
            return

        # Update max text width based on current screen width
        self._max_text_width = int(screen.get_width() * 0.4)

        y = self.top_panel_height + MARGIN_TOP
        for notif in self._notifications:
            elapsed = notif['elapsed']

            # Calculate alpha (full during display, fading during fade phase)
            if elapsed < DISPLAY_DURATION:
                alpha = 255
            else:
                fade_progress = (elapsed - DISPLAY_DURATION) / FADE_DURATION
                alpha = max(0, int(255 * (1.0 - fade_progress)))

            if alpha <= 0:
                continue

            x = MARGIN_LEFT

            # Draw background with alpha
            bg = notif['bg_surface']
            if alpha < 255:
                bg = bg.copy()
                bg.set_alpha(alpha)
            screen.blit(bg, (x, y))

            # Draw text surfaces with alpha
            text_x = x + PADDING_X
            text_y = y + PADDING_Y

            # Team tag (if present)
            if notif.get('team_surface'):
                surf = notif['team_surface']
                if alpha < 255:
                    surf = surf.copy()
                    surf.set_alpha(alpha)
                screen.blit(surf, (text_x, text_y))
                text_x += notif['team_width'] + 4

            # Player name
            name_surf = notif['name_surface']
            if alpha < 255:
                name_surf = name_surf.copy()
                name_surf.set_alpha(alpha)
            screen.blit(name_surf, (text_x, text_y))
            text_x += notif['name_width']

            # Colon + message
            msg_surf = notif['msg_surface']
            if alpha < 255:
                msg_surf = msg_surf.copy()
                msg_surf.set_alpha(alpha)
            screen.blit(msg_surf, (text_x, text_y))

            y += notif['height'] + LINE_SPACING

    def _create_notification(self, chat_msg):
        """Create a notification dict from a chat message tuple."""
        # Handle both 3-tuple (legacy) and 4-tuple formats
        if len(chat_msg) == 3:
            timestamp, player_id, message = chat_msg
            channel = 'all'
        else:
            timestamp, player_id, message, channel = chat_msg

        # Get player info
        try:
            player_color = self.game_state.get_player_color(player_id)
            player_name = self.game_state.get_player_name(player_id, include_title=False)
        except (IndexError, AttributeError):
            return None

        # Render team tag if team channel
        team_surface = None
        team_width = 0
        if channel == 'team':
            team_surface = self.font_bold.render("[TEAM] ", True, TEAM_TAG_COLOR)
            team_width = team_surface.get_width()

        # Render player name in their color (bold)
        name_surface = self.font_bold.render(player_name, True, player_color)
        name_width = name_surface.get_width()

        # Render ": message" in white — truncate if too long
        colon_msg = f": {message}"
        msg_surface = self.font.render(colon_msg, True, MSG_COLOR)

        # Truncate message if total width exceeds max
        total_text_width = team_width + (4 if team_surface else 0) + name_width + msg_surface.get_width()
        if total_text_width > self._max_text_width:
            # Progressively shorten message text until it fits
            available = self._max_text_width - team_width - (4 if team_surface else 0) - name_width
            truncated = colon_msg
            while len(truncated) > 4:
                truncated = truncated[:-1]
                test_surface = self.font.render(truncated + "...", True, MSG_COLOR)
                if test_surface.get_width() <= available:
                    msg_surface = test_surface
                    break
            else:
                msg_surface = self.font.render(": ...", True, MSG_COLOR)

        # Calculate total dimensions for background
        content_width = team_width + (4 if team_surface else 0) + name_width + msg_surface.get_width()
        text_height = max(
            name_surface.get_height(),
            msg_surface.get_height(),
            team_surface.get_height() if team_surface else 0
        )
        bg_width = content_width + PADDING_X * 2
        bg_height = text_height + PADDING_Y * 2

        # Create background surface with transparency
        bg_surface = pygame.Surface((bg_width, bg_height), pygame.SRCALPHA)
        bg_surface.fill((*BG_COLOR, BG_ALPHA))

        return {
            'elapsed': 0.0,
            'team_surface': team_surface,
            'team_width': team_width,
            'name_surface': name_surface,
            'name_width': name_width,
            'msg_surface': msg_surface,
            'bg_surface': bg_surface,
            'height': bg_height,
        }

    def on_resolution_change(self, top_panel_height, font, font_bold):
        """Update layout after resolution change. Clears active notifications."""
        self.top_panel_height = top_panel_height
        self.font = font
        self.font_bold = font_bold
        self._notifications.clear()

    def cleanup(self):
        """Clear all notifications."""
        self._notifications.clear()
