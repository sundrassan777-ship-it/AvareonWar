"""
players_window.py — "Players" modal window.

Non-pausing modal opened from the top-panel "Players" button. Lists all
players with columns:
    Name | Controller | Team | Color | Status | Transfer Gold | Send

Input field + Send button are only interactive when the Gold Transfer
feature is enabled, the row's player is an ally of the local sender,
the target hasn't already received a transfer this turn, the target is
still Playing, and we're currently in the Planning phase.

When disabled, hovering the field or button shows a tooltip explaining
why (e.g. "Cannot send Gold to enemy players.").
"""

import pygame

from config.constants import PLAYER_COLORS


TEXT_PRIMARY = (255, 250, 240)
TEXT_MUTED = (180, 170, 150)
PANEL_BG_COLOR = (40, 30, 20)
ROW_BG_ALT = (60, 45, 30)
ROW_BG = (50, 38, 25)
BRASS_COLOR = (210, 180, 100)
GRAY = (120, 120, 120)
DISABLED_TEXT = (130, 125, 115)
INPUT_BG = (30, 22, 15)
INPUT_BG_FOCUSED = (48, 38, 24)
SEND_BTN_BG = (80, 70, 45)
SEND_BTN_BG_HOVER = (110, 95, 60)
SEND_BTN_DISABLED = (60, 50, 35)
SUCCESS_COLOR = (170, 255, 170)
ERROR_COLOR = (255, 100, 100)  # Refused send (same red as the in-game error toast)

MAX_INPUT_DIGITS = 7  # Per product spec — cap typed amount at 7 digits
FEEDBACK_DURATION_MS = 1800  # How long "Transfer successful." stays onscreen

COLUMN_SHARES = [
    ('name', 0.17),
    ('controller', 0.15),   # Widened so the "Controller" header doesn't run into "Team"
    ('team', 0.07),
    ('color', 0.08),
    ('status', 0.12),
    ('transfer', 0.22),
    ('send', 0.18),
]

COLUMN_HEADERS = {
    'name': 'Name',
    'controller': 'Controller',
    'team': 'Team',
    'color': 'Color',
    'status': 'Status',
    'transfer': 'Transfer Gold',
    'send': '',
}


class PlayersWindow:
    """Modal overlay listing all players — supports ally gold transfers."""

    def __init__(self, game):
        self.game = game

        # Input state — persists until window closes or turn advances
        self.input_texts = {}  # {recipient_idx: str}
        self.focused_recipient = None  # int or None

        # Transient feedback toast
        self.feedback_message = None
        self.feedback_is_error = False  # True -> drawn red (a refused send)
        self.feedback_timer_ms = 0
        self._last_tick_ms = pygame.time.get_ticks()

        # Layout / hit-test rects — refreshed every frame by draw()
        self.panel_rect = None
        self.close_button_rect = None
        self._input_rects = {}
        self._send_rects = {}
        # Per-row disabled reason for tooltips, or None if the row is enabled.
        # Populated by draw() each frame so handle_hover can look it up.
        self._row_disabled_reason = {}

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def draw(self, screen):
        """Render the modal onto `screen`."""
        self._tick_feedback()

        screen_w, screen_h = screen.get_size()
        scale = self.game.ui_scale

        # Dimmed background (non-pausing — game keeps rendering beneath)
        dark = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 150))
        screen.blit(dark, (0, 0))

        # Panel
        panel_w = int(900 * scale)
        panel_h = int(520 * scale)
        panel_x = (screen_w - panel_w) // 2
        panel_y = (screen_h - panel_h) // 2
        self.panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        pygame.draw.rect(screen, PANEL_BG_COLOR, self.panel_rect, border_radius=6)
        pygame.draw.rect(screen, BRASS_COLOR, self.panel_rect, 2, border_radius=6)

        # Title
        title_font = self._font(int(28 * scale), bold=True)
        title_surface = title_font.render("Players", True, TEXT_PRIMARY)
        title_rect = title_surface.get_rect(midtop=(self.panel_rect.centerx, panel_y + int(16 * scale)))
        screen.blit(title_surface, title_rect)

        sep_y = title_rect.bottom + int(8 * scale)
        pygame.draw.line(screen, BRASS_COLOR,
                         (panel_x + int(20 * scale), sep_y),
                         (panel_x + panel_w - int(20 * scale), sep_y), 1)

        # Close button (top-right)
        close_size = int(24 * scale)
        close_x = panel_x + panel_w - close_size - int(10 * scale)
        close_y = panel_y + int(10 * scale)
        self.close_button_rect = pygame.Rect(close_x, close_y, close_size, close_size)
        mouse_pos = pygame.mouse.get_pos()
        close_hover = self.close_button_rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, (90, 50, 50) if close_hover else (70, 40, 40),
                         self.close_button_rect, border_radius=4)
        pygame.draw.rect(screen, BRASS_COLOR, self.close_button_rect, 1, border_radius=4)
        x_font = self._font(int(18 * scale), bold=True)
        x_surface = x_font.render("x", True, TEXT_PRIMARY)
        screen.blit(x_surface, x_surface.get_rect(center=self.close_button_rect.center))

        # Table layout
        table_x = panel_x + int(20 * scale)
        table_w = panel_w - int(40 * scale)
        table_top = sep_y + int(16 * scale)
        row_h = int(42 * scale)
        header_h = int(28 * scale)

        col_x = {}
        cur_x = table_x
        for col_id, share in COLUMN_SHARES:
            w = int(table_w * share)
            col_x[col_id] = (cur_x, w)
            cur_x += w

        # Header row
        header_font = self._font(max(12, int(16 * scale)), bold=True)
        for col_id, _share in COLUMN_SHARES:
            cx, _cw = col_x[col_id]
            label = COLUMN_HEADERS.get(col_id, '')
            if not label:
                continue
            surf = header_font.render(label, True, TEXT_MUTED)
            screen.blit(surf, surf.get_rect(midleft=(cx + int(8 * scale), table_top + header_h // 2)))

        pygame.draw.line(screen, BRASS_COLOR,
                         (table_x, table_top + header_h),
                         (table_x + table_w, table_top + header_h), 1)

        # Rows
        body_top = table_top + header_h
        row_font = self._font(max(12, int(16 * scale)))
        self._input_rects = {}
        self._send_rects = {}
        self._row_disabled_reason = {}

        gs = self.game.game_state
        sender_idx = self._get_sender_index()

        for i in range(gs.num_players):
            row_y = body_top + i * row_h
            row_rect = pygame.Rect(table_x, row_y, table_w, row_h)
            bg = ROW_BG_ALT if i % 2 == 1 else ROW_BG
            pygame.draw.rect(screen, bg, row_rect)

            self._draw_row(screen, i, sender_idx, row_y, row_h, col_x, row_font, scale)

        bottom_y = body_top + gs.num_players * row_h
        pygame.draw.line(screen, BRASS_COLOR,
                         (table_x, bottom_y),
                         (table_x + table_w, bottom_y), 1)

        # Feedback toast
        if self.feedback_message and self.feedback_timer_ms > 0:
            self._draw_feedback(screen, bottom_y + int(12 * scale), scale)

        # Tooltip rendering (last so it stays on top)
        self._draw_hover_tooltip(screen, scale, mouse_pos)

    def handle_click(self, pos):
        """Left-click handler. Always consumes while window is open."""
        if self.close_button_rect and self.close_button_rect.collidepoint(pos):
            self.close()
            return True

        # Click outside the panel closes the window
        if self.panel_rect and not self.panel_rect.collidepoint(pos):
            self.close()
            return True

        sender_idx = self._get_sender_index()
        gs = self.game.game_state

        # Input field focus (only for enabled rows)
        for recipient_idx, rect in self._input_rects.items():
            if rect.collidepoint(pos):
                if self._row_disabled_reason.get(recipient_idx) is None:
                    self.focused_recipient = recipient_idx
                    if recipient_idx not in self.input_texts:
                        self.input_texts[recipient_idx] = ''
                return True

        # Send buttons
        for recipient_idx, rect in self._send_rects.items():
            if rect.collidepoint(pos):
                if self._row_disabled_reason.get(recipient_idx) is None:
                    self._attempt_send(sender_idx, recipient_idx)
                return True

        # Clicked inside the panel but outside any focusable element — unfocus input
        self.focused_recipient = None
        return True

    def handle_key(self, event):
        """KEYDOWN handler. Returns True if consumed."""
        if event.key == pygame.K_ESCAPE:
            if self.focused_recipient is not None:
                # First ESC unfocuses; second closes
                self.focused_recipient = None
                return True
            self.close()
            return True

        if self.focused_recipient is None:
            return False

        recipient_idx = self.focused_recipient
        sender_idx = self._get_sender_index()
        current_text = self.input_texts.get(recipient_idx, '')

        if event.key == pygame.K_BACKSPACE:
            self.input_texts[recipient_idx] = current_text[:-1]
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            # Same guard as the Send button: a row that became disabled after it was
            # focused (greyed, with a tooltip reason) must not attempt a send
            if self._row_disabled_reason.get(recipient_idx) is None:
                self._attempt_send(sender_idx, recipient_idx)
            return True
        if event.key == pygame.K_TAB:
            # Move focus to the next enabled row (if any)
            self._focus_next_enabled_row()
            return True

        # Digit input only — ignore anything else
        ch = getattr(event, 'unicode', '')
        if ch and ch.isdigit():
            if len(current_text) >= MAX_INPUT_DIGITS:
                return True
            new_text = current_text + ch
            # Auto-clamp to cap on every keystroke
            cap = self.game.game_state.get_transfer_cap(sender_idx)
            try:
                if int(new_text) > cap:
                    new_text = str(cap)
            except ValueError:
                return True
            self.input_texts[recipient_idx] = new_text
            return True

        return False

    def handle_hover(self, mouse_pos):
        """Called from MOUSEMOTION. Nothing to do — draw() reads mouse pos directly."""
        return

    def close(self):
        """Close the window and reset transient state."""
        self.game.players_window_visible = False
        self.input_texts.clear()
        self.focused_recipient = None
        self.feedback_message = None
        self.feedback_timer_ms = 0

    # ------------------------------------------------------------------
    # Row rendering
    # ------------------------------------------------------------------

    def _draw_row(self, screen, recipient_idx, sender_idx, y, row_h, col_x, font, scale):
        gs = self.game.game_state
        mouse_pos = pygame.mouse.get_pos()

        # Determine interactability + reason for disabled
        if sender_idx == recipient_idx:
            # Your own row — never interactive, no tooltip needed.
            interactive, reason = False, None
        else:
            interactive, reason = gs.can_transfer_gold(sender_idx, recipient_idx)
            if interactive:
                reason = None
        self._row_disabled_reason[recipient_idx] = None if interactive else reason

        # --- Name --- (truncate if it would overflow the column and collide with Controller)
        name_col, name_w = col_x['name']
        pad = int(8 * scale)
        max_name_w = max(10, name_w - pad * 2)
        display_name = self._truncate_to_width(gs.get_player_name(recipient_idx), font, max_name_w)
        self._blit_text(screen, font, display_name, col_x['name'], y, row_h, TEXT_PRIMARY, scale)

        # --- Controller ---
        controller = "AI" if gs.player_is_ai[recipient_idx] else "Human"
        self._blit_text(screen, font, controller, col_x['controller'], y, row_h, TEXT_PRIMARY, scale)

        # --- Team ---
        team = gs.player_teams[recipient_idx] if recipient_idx < len(gs.player_teams) else recipient_idx
        self._blit_text(screen, font, str(team + 1), col_x['team'], y, row_h, TEXT_PRIMARY, scale)

        # --- Color swatch ---
        cx, _cw = col_x['color']
        swatch_w = int(28 * scale)
        swatch_h = int(18 * scale)
        swatch_rect = pygame.Rect(cx + int(8 * scale),
                                   y + (row_h - swatch_h) // 2,
                                   swatch_w, swatch_h)
        color = gs.player_colors[recipient_idx] if recipient_idx < len(gs.player_colors) else PLAYER_COLORS[recipient_idx % len(PLAYER_COLORS)]
        pygame.draw.rect(screen, color, swatch_rect, border_radius=3)
        pygame.draw.rect(screen, BRASS_COLOR, swatch_rect, 1, border_radius=3)

        # --- Status ---
        status = self.get_player_status(recipient_idx)
        status_color = TEXT_PRIMARY if status == 'Playing' else TEXT_MUTED
        self._blit_text(screen, font, status, col_x['status'], y, row_h, status_color, scale)

        # --- Transfer input ---
        cx, cw = col_x['transfer']
        input_w = cw - int(16 * scale)
        input_h = int(26 * scale)
        input_rect = pygame.Rect(cx + int(8 * scale),
                                  y + (row_h - input_h) // 2,
                                  input_w, input_h)
        self._input_rects[recipient_idx] = input_rect

        focused = (self.focused_recipient == recipient_idx) and interactive
        fill = INPUT_BG_FOCUSED if focused else INPUT_BG
        border = BRASS_COLOR if focused else GRAY
        pygame.draw.rect(screen, fill, input_rect, border_radius=3)
        pygame.draw.rect(screen, border, input_rect, 1, border_radius=3)

        text = self.input_texts.get(recipient_idx, '')
        # Placeholder cap hint in the input when empty and interactive
        if not text and interactive:
            cap_hint = f"max {gs.get_transfer_cap(sender_idx)}"
            hint_surf = font.render(cap_hint, True, DISABLED_TEXT)
            screen.blit(hint_surf, hint_surf.get_rect(midleft=(input_rect.x + int(6 * scale), input_rect.centery)))
        else:
            text_color = TEXT_PRIMARY if interactive else DISABLED_TEXT
            text_surf = font.render(text, True, text_color)
            screen.blit(text_surf, text_surf.get_rect(midleft=(input_rect.x + int(6 * scale), input_rect.centery)))
            # Simple caret when focused
            if focused:
                caret_x = input_rect.x + int(6 * scale) + text_surf.get_width() + 2
                caret_y1 = input_rect.y + int(4 * scale)
                caret_y2 = input_rect.bottom - int(4 * scale)
                if (pygame.time.get_ticks() // 500) % 2 == 0:
                    pygame.draw.line(screen, TEXT_PRIMARY, (caret_x, caret_y1), (caret_x, caret_y2), 1)

        # --- Send button ---
        cx, cw = col_x['send']
        btn_w = cw - int(16 * scale)
        btn_h = int(28 * scale)
        btn_rect = pygame.Rect(cx + int(8 * scale),
                                y + (row_h - btn_h) // 2,
                                btn_w, btn_h)
        self._send_rects[recipient_idx] = btn_rect

        if interactive:
            hovered = btn_rect.collidepoint(mouse_pos)
            btn_bg = SEND_BTN_BG_HOVER if hovered else SEND_BTN_BG
            btn_border = BRASS_COLOR
            label_color = TEXT_PRIMARY
        else:
            btn_bg = SEND_BTN_DISABLED
            btn_border = GRAY
            label_color = DISABLED_TEXT
        pygame.draw.rect(screen, btn_bg, btn_rect, border_radius=4)
        pygame.draw.rect(screen, btn_border, btn_rect, 1, border_radius=4)
        btn_label = font.render("Send", True, label_color)
        screen.blit(btn_label, btn_label.get_rect(center=btn_rect.center))

    # ------------------------------------------------------------------
    # Send / feedback
    # ------------------------------------------------------------------

    def _show_send_error(self, code):
        """
        Refused send: denial sound + the message in this window's own feedback line.

        The in-game error toast draws underneath this modal (behind its dark overlay),
        so it would not be seen here. The text still comes from the shared table in
        config/action_error_messages.py.
        """
        from config.action_error_messages import format_action_error
        from global_sound import play_action_denied
        play_action_denied()
        self.feedback_message = format_action_error(code)
        self.feedback_is_error = True
        self.feedback_timer_ms = FEEDBACK_DURATION_MS

    def _attempt_send(self, sender_idx, recipient_idx):
        # Empty / zero amount: Send used to do nothing at all — say why
        text = self.input_texts.get(recipient_idx, '').strip()
        try:
            amount = int(text) if text else 0
        except ValueError:
            amount = 0  # non-digit keys are filtered on input, so this is a safeguard
        if amount <= 0:
            self._show_send_error('transfer_no_amount')
            return

        # Route through the game-level wrapper so multiplayer networking can
        # hook in without PlayersWindow needing to know the details.
        executor = getattr(self.game, 'execute_gold_transfer', None)
        if executor is None:
            sent = self.game.game_state.transfer_gold(sender_idx, recipient_idx, amount)
        else:
            sent = executor(sender_idx, recipient_idx, amount)

        if sent > 0:
            self.feedback_message = "Transfer successful."
            self.feedback_is_error = False
            self.feedback_timer_ms = FEEDBACK_DURATION_MS
            self.input_texts[recipient_idx] = ''
            self.focused_recipient = None

    def _tick_feedback(self):
        now = pygame.time.get_ticks()
        delta = now - self._last_tick_ms
        self._last_tick_ms = now
        if self.feedback_timer_ms > 0:
            self.feedback_timer_ms = max(0, self.feedback_timer_ms - delta)
            if self.feedback_timer_ms == 0:
                self.feedback_message = None

    def _draw_feedback(self, screen, y, scale):
        font = self._font(max(14, int(20 * scale)), bold=True)
        color = ERROR_COLOR if self.feedback_is_error else SUCCESS_COLOR
        surf = font.render(self.feedback_message, True, color)
        rect = surf.get_rect(midtop=(self.panel_rect.centerx, y))
        screen.blit(surf, rect)

    # ------------------------------------------------------------------
    # Tooltip
    # ------------------------------------------------------------------

    def _draw_hover_tooltip(self, screen, scale, mouse_pos):
        """If hovering a disabled input/button, show a tooltip with the reason."""
        reason = None
        anchor_rect = None
        for recipient_idx, rect in list(self._input_rects.items()):
            if rect.collidepoint(mouse_pos):
                reason = self._row_disabled_reason.get(recipient_idx)
                anchor_rect = rect
                break
        if reason is None:
            for recipient_idx, rect in list(self._send_rects.items()):
                if rect.collidepoint(mouse_pos):
                    reason = self._row_disabled_reason.get(recipient_idx)
                    anchor_rect = rect
                    break

        if reason is None or anchor_rect is None:
            return

        font = self._font(max(11, int(14 * scale)))
        text_surf = font.render(reason, True, (255, 220, 150))
        tw, th = text_surf.get_size()
        pad = int(8 * scale)
        tx = anchor_rect.centerx - (tw + pad * 2) // 2
        ty = anchor_rect.top - th - pad * 2 - int(4 * scale)
        # Keep tooltip on-screen horizontally
        screen_w = screen.get_width()
        tx = max(int(4 * scale), min(tx, screen_w - tw - pad * 2 - int(4 * scale)))
        bg_rect = pygame.Rect(tx, ty, tw + pad * 2, th + pad * 2)
        pygame.draw.rect(screen, (30, 30, 30), bg_rect, border_radius=4)
        pygame.draw.rect(screen, (100, 100, 100), bg_rect, 1, border_radius=4)
        screen.blit(text_surf, (tx + pad, ty + pad))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_sender_index(self):
        """Return the index of the player who's currently allowed to send.

        In multiplayer, that's the local player. In singleplayer sequential,
        it's the current player. In singleplayer sim mode, it's also the
        "local" player concept (current_player as a fallback).
        """
        if self.game.multiplayer_mode and self.game.local_player_index is not None:
            return self.game.local_player_index
        if self.game.sim_state is not None and getattr(self.game, 'local_player_index', None) is not None:
            return self.game.local_player_index
        return self.game.game_state.current_player

    def _focus_next_enabled_row(self):
        gs = self.game.game_state
        sender_idx = self._get_sender_index()
        start = 0 if self.focused_recipient is None else (self.focused_recipient + 1)
        for offset in range(gs.num_players):
            idx = (start + offset) % gs.num_players
            if idx == sender_idx:
                continue
            ok, _ = gs.can_transfer_gold(sender_idx, idx)
            if ok:
                self.focused_recipient = idx
                if idx not in self.input_texts:
                    self.input_texts[idx] = ''
                return

    def get_player_status(self, player_idx):
        """Return 'Playing', 'Eliminated', or 'Left'."""
        gs = self.game.game_state
        if player_idx in getattr(gs, 'disconnect_eliminations', set()):
            return 'Left'
        if player_idx in gs.eliminated_players:
            return 'Eliminated'
        return 'Playing'

    def _blit_text(self, screen, font, text, col, y, row_h, color, scale):
        cx, _cw = col
        surf = font.render(text, True, color)
        screen.blit(surf, surf.get_rect(midleft=(cx + int(8 * scale), y + row_h // 2)))

    def _truncate_to_width(self, text, font, max_width):
        """Truncate `text` with an ellipsis so its rendered width fits max_width."""
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = "…"
        # Binary-search the longest prefix that fits with ellipsis appended
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate = text[:mid] + ellipsis
            if font.size(candidate)[0] <= max_width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + ellipsis if lo > 0 else ellipsis

    def _font(self, size, bold=False):
        try:
            path = 'assets/fonts/Cinzel-SemiBold.ttf' if bold else 'assets/fonts/Cinzel-Regular.ttf'
            return pygame.font.Font(path, max(10, size))
        except (FileNotFoundError, pygame.error, OSError):
            return pygame.font.SysFont('arial', max(10, size), bold=bold)
