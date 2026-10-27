# -*- coding: utf-8 -*-
# tests/test_wishlist.py
# OPEN BETA ONLY (remove at full release, with wishlist.py): the main menu's Wishlist
# button and the one-time wishlist prompt on a campaign victory recap.

import os
import types

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

import wishlist  # noqa: E402
from steam_integration import MAIN_GAME_APP_ID, STEAM_APP_ID, SteamManager  # noqa: E402

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


class _Settings:
    """A settings stand-in (never this PC's config.json)."""
    def __init__(self, **values):
        self.values = dict(values)
        self.saves = 0

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.saves += 1


class _Steam:
    def __init__(self, overlay=False, raises=False):
        self.overlay = overlay
        self.raises = raises
        self.asked = []

    def open_store_overlay(self, app_id):
        self.asked.append(app_id)
        if self.raises:
            raise RuntimeError('overlay broke')
        return self.overlay


@pytest.fixture
def opened(monkeypatch):
    """Records what os.startfile / webbrowser.open were asked to open."""
    calls = {'startfile': [], 'browser': []}

    def startfile(url):
        calls['startfile'].append(url)
        if calls.get('startfile_fails'):
            raise OSError('no Steam client')

    def browser(url):
        calls['browser'].append(url)
        return not calls.get('browser_fails')

    monkeypatch.setattr(wishlist.os, 'startfile', startfile, raising=False)
    monkeypatch.setattr(wishlist.webbrowser, 'open', browser)
    return calls


# --- Opening the store page ----------------------------------------------------------------

class TestOpenWishlistPage:

    def test_the_full_game_not_the_playtest(self):
        assert MAIN_GAME_APP_ID == 4518100 and STEAM_APP_ID == 4518130
        for url in (wishlist.STEAM_STORE_URL, wishlist.WEB_STORE_URL):
            assert '4518100' in url and '4518130' not in url
        assert wishlist.STEAM_STORE_URL == 'steam://store/4518100'
        assert wishlist.WEB_STORE_URL == 'https://store.steampowered.com/app/4518100/'

    def test_overlay_when_it_is_hooked(self, opened):
        steam = _Steam(overlay=True)
        assert wishlist.open_wishlist_page(steam) == 'overlay'
        assert steam.asked == [4518100]
        assert opened['startfile'] == [] and opened['browser'] == []

    def test_steam_client_when_the_overlay_is_not_hooked(self, opened):
        steam = _Steam(overlay=False)
        assert wishlist.open_wishlist_page(steam) == 'steam'
        assert opened['startfile'] == ['steam://store/4518100'] and opened['browser'] == []

    def test_a_broken_overlay_still_opens_the_page(self, opened):
        assert wishlist.open_wishlist_page(_Steam(raises=True)) == 'steam'

    def test_browser_when_the_steam_client_link_fails(self, opened):
        opened['startfile_fails'] = True
        assert wishlist.open_wishlist_page(_Steam()) == 'browser'
        assert opened['browser'] == ['https://store.steampowered.com/app/4518100/']

    def test_never_raises(self, opened):
        opened['startfile_fails'] = True
        opened['browser_fails'] = True
        assert wishlist.open_wishlist_page(_Steam(raises=True)) == 'failed'


class TestSteamOverlay:
    """SteamManager.open_store_overlay: the overlay only when it is hooked."""

    def _manager(self, enabled):
        calls = []
        utils = types.SimpleNamespace(IsOverlayEnabled=lambda: enabled)
        friends = types.SimpleNamespace(ActivateGameOverlayToStore=lambda app: calls.append(app))
        manager = SteamManager()
        manager._initialized = True
        manager._steamworks = types.SimpleNamespace(Utils=utils, Friends=friends)
        return manager, calls

    def test_without_steam(self):
        assert SteamManager().open_store_overlay(MAIN_GAME_APP_ID) is False

    def test_unhooked_overlay_is_not_asked(self):
        manager, calls = self._manager(enabled=False)
        assert manager.open_store_overlay(MAIN_GAME_APP_ID) is False
        assert calls == []

    def test_hooked_overlay_shows_the_store(self):
        manager, calls = self._manager(enabled=True)
        assert manager.open_store_overlay(MAIN_GAME_APP_ID) is True
        assert calls == [4518100]

    def test_a_failing_call_is_not_an_error(self):
        manager, _ = self._manager(enabled=True)
        manager._steamworks.Friends = types.SimpleNamespace()     # no such method
        assert manager.open_store_overlay(MAIN_GAME_APP_ID) is False


# --- The one-time prompt: when ------------------------------------------------------------

def _game(mission_id='mission_3', won=True, phase='ended'):
    gs = types.SimpleNamespace(phase=phase, num_players=2, player_is_ai=[False, True],
                               is_winner=lambda i: won and i == 0)
    mission = types.SimpleNamespace(mission_id=mission_id) if mission_id else None
    return types.SimpleNamespace(game_state=gs, tutorial_mission=mission)


class TestPromptDue:

    def test_after_three_different_missions(self):
        two = _Settings(campaign_missions_xp_claimed=['mission_1', 'mission_2', 'mission_2'])
        three = _Settings(campaign_missions_xp_claimed=['mission_1', 'mission_2', 'tale_1'])
        assert wishlist.WISHLIST_PROMPT_AFTER == 3
        assert not wishlist.prompt_due(_game(), two)
        assert wishlist.prompt_due(_game(), three)                       # Book of Tales count too

    def test_only_once(self):
        shown = _Settings(campaign_missions_xp_claimed=['mission_1', 'mission_2', 'mission_3'],
                          wishlist_prompt_shown=True)
        assert not wishlist.prompt_due(_game(), shown)

    def test_never_on_a_defeat_custom_game_or_early_exit(self):
        s = _Settings(campaign_missions_xp_claimed=['mission_1', 'mission_2', 'mission_3'])
        assert not wishlist.prompt_due(_game(won=False), s)
        assert not wishlist.prompt_due(_game(mission_id=None), s)            # Custom / multiplayer
        assert not wishlist.prompt_due(_game(phase='playing'), s)

    def test_not_outside_the_open_beta(self, monkeypatch):
        monkeypatch.setattr(wishlist, 'OPEN_BETA', False)
        s = _Settings(campaign_missions_xp_claimed=['mission_1', 'mission_2', 'mission_3'])
        assert not wishlist.prompt_due(_game(), s)

    def test_shown_is_remembered(self):
        s = _Settings()
        wishlist.mark_prompt_shown(s)
        assert s.values['wishlist_prompt_shown'] is True and s.saves == 1

    def test_the_setting_survives_validation(self):
        from settings_manager import SETTING_TYPES, settings
        assert SETTING_TYPES['wishlist_prompt_shown'] == (bool,)
        assert settings.defaults['wishlist_prompt_shown'] is False


# --- The main menu button -----------------------------------------------------------------

@pytest.fixture
def clicks(monkeypatch):
    from global_sound import sound_manager
    calls = []
    monkeypatch.setattr(sound_manager, 'play_ui_click', lambda *a, **k: calls.append(1))
    return calls


@pytest.fixture
def opens(monkeypatch):
    calls = []
    monkeypatch.setattr(wishlist, 'open_wishlist_page', lambda *a, **k: calls.append(1) or 'steam')
    return calls


def _fresh_display(size):
    """A display of exactly this size: an earlier test module can leave a fullscreen one
    behind, and set_mode then keeps its size (see test_map_top_bar)."""
    pygame.init()
    pygame.display.quit()
    pygame.display.init()
    return pygame.display.set_mode(size)


def _menu(size):
    import main_menu
    return main_menu.MainMenu(_fresh_display(size))


def _brightness(screen, rect):
    sub = pygame.surfarray.array3d(screen)[rect.x:rect.right, rect.y:rect.bottom]
    return float(sub.mean())


@pytest.mark.parametrize('size', RESOLUTIONS)
def test_button_sits_in_the_free_bottom_left_corner(size):
    menu = _menu(size)
    rect = menu.wishlist_button_rect
    assert rect is not None
    assert pygame.Rect(0, 0, *size).contains(rect)
    assert rect.x < size[0] // 4 and rect.bottom > size[1] * 3 // 4               # bottom-left
    for other in (menu.replays_button_rect, menu.achievement_button_rect, menu.profile_button_rect):
        assert not rect.colliderect(other)
    for button in menu.buttons.values():
        assert not rect.colliderect(button['rect'])
    version = menu.tooltip_font.render('Version: 1.0.0', True, (255, 255, 255))
    version_rect = version.get_rect(topleft=(10, size[1] - version.get_height() - 10))
    assert not rect.colliderect(version_rect)                                   # above the version text


@pytest.mark.parametrize('icon', ['shipped', 'missing'])
def test_hover_and_click_feedback(monkeypatch, icon):
    if icon == 'missing':
        monkeypatch.setattr(wishlist, 'WISHLIST_ICON_PATH', 'assets/no-such-wishlist-icon.png')
    menu = _menu((1600, 900))
    assert (menu.wishlist_button_icon_scaled is None) == (icon == 'missing')
    rect = menu.wishlist_button_rect
    levels = []
    for hovered, clicked in ((None, None), ('wishlist', None), ('wishlist', 'wishlist')):
        menu.screen.fill((0, 0, 0))
        menu.hovered_button, menu.clicked_button = hovered, clicked
        menu._draw_wishlist_button()
        levels.append(_brightness(menu.screen, rect))
    assert levels[0] > 5                                                        # the icon or the fallback tile
    assert levels[0] < levels[1] < levels[2]                                    # idle < hover < flash


def test_navy_glow_round_the_button():
    """A subtle navy halo just outside the button, fading out, stronger while hovered."""
    menu = _menu((1600, 900))
    rect = menu.wishlist_button_rect
    reach = menu.wishlist_glow[False][1]

    def glow_at(hovered, dx):
        menu.screen.fill((0, 0, 0))
        menu.hovered_button = 'wishlist' if hovered else None
        menu.clicked_button = None
        menu._draw_wishlist_button()
        return menu.screen.get_at((rect.right + dx, rect.centery))[:3]

    near = glow_at(False, 2)
    r, g, b = near
    assert b > 60 and b > r and b > g                                           # navy, not black
    far = glow_at(False, reach - 1)
    assert sum(far) < sum(near)                                                 # it fades out
    assert glow_at(False, reach + 2) == (0, 0, 0)                               # and ends
    assert glow_at(True, 2)[2] > b                                              # stronger on hover


def test_tooltip(monkeypatch):
    menu = _menu((1600, 900))
    shown = []
    monkeypatch.setattr(menu, '_draw_tooltip', lambda screen, text, pos, font: shown.append(text))
    menu.hovered_button = 'wishlist'
    menu.render()
    assert shown == ['Wishlist the full game on Steam']


def test_click_opens_the_store_page_once(clicks, opens):
    menu = _menu((1600, 900))
    menu.handle_click(menu.wishlist_button_rect.center)
    assert opens == [1] and clicks == [1]
    assert menu.result is None                                                  # the menu stays


def test_the_shipped_icon_is_in_assets_under_its_exact_name():
    """Windows finds a file whatever the case of its name, a build or another system may
    not: the name in WISHLIST_ICON_PATH must be the file's own, letter for letter."""
    import os
    folder, name = os.path.split(wishlist.WISHLIST_ICON_PATH)
    assert name in os.listdir(folder)
    icon = pygame.image.load(wishlist.WISHLIST_ICON_PATH)
    assert icon.get_width() == icon.get_height() >= 256                         # square, sharp when scaled


def test_icon_is_drawn_not_the_tile(monkeypatch, tmp_path):
    icon = tmp_path / 'WishlistIcon.png'
    surface = pygame.Surface((64, 64))
    surface.fill((200, 10, 10))
    pygame.image.save(surface, str(icon))
    monkeypatch.setattr(wishlist, 'WISHLIST_ICON_PATH', str(icon))
    menu = _menu((1600, 900))
    assert menu.wishlist_button_icon_scaled is not None
    menu.screen.fill((0, 0, 0))
    menu.hovered_button = menu.clicked_button = None
    menu._draw_wishlist_button()
    r, g, b = menu.screen.get_at(menu.wishlist_button_rect.center)[:3]
    assert r > 150 and g < 60                                                   # the icon, not the tile


def test_no_button_outside_the_open_beta(monkeypatch, clicks, opens):
    import main_menu
    monkeypatch.setattr(main_menu, 'OPEN_BETA', False)
    menu = _menu((1600, 900))
    assert menu.wishlist_button_rect is None
    menu.handle_click((40, 900 - 80))
    assert opens == []


# --- The prompt on the recap -------------------------------------------------------------

def _recap(size=(1600, 900), prompt=True, xp_result=None):
    from recap_screen import RecapScreen
    screen = _fresh_display(size)
    stats = {0: {}, 1: {}}
    return RecapScreen(screen, stats, ['Human', 'AI'], [(200, 40, 40), (40, 40, 200)], 0, 2,
                       newly_earned_achievements=[], xp_result=xp_result, replay_recorder=None,
                       wishlist_prompt=prompt)


@pytest.fixture
def marked(monkeypatch):
    calls = []
    monkeypatch.setattr(wishlist, 'mark_prompt_shown', lambda *a, **k: calls.append(1))
    return calls


def _click(pos):
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def _key(key):
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))


class TestRecapPrompt:

    def test_opens_after_the_popups_and_counts_as_shown(self, marked):
        xp = {'xp_earned': 50, 'old_level': 1, 'new_level': 1, 'old_xp': 0, 'new_xp': 50}
        recap = _recap(xp_result=xp)
        recap._update_wishlist_prompt(5.0)
        assert recap.wishlist_phase == 'waiting' and marked == []               # the XP bar first
        recap.xp_bar_phase = 'xp_done'
        recap._update_wishlist_prompt(0.3)
        assert recap.wishlist_phase == 'waiting'                                # a short pause
        recap._update_wishlist_prompt(0.4)
        assert recap.wishlist_phase == 'open' and marked == [1]

    def test_off_without_the_flag(self, marked):
        recap = _recap(prompt=False)
        recap._update_wishlist_prompt(5.0)
        assert recap.wishlist_phase == 'off' and marked == []

    @pytest.mark.parametrize('size', RESOLUTIONS)
    def test_layout(self, size, marked):
        recap = _recap(size)
        panel = recap.wishlist_panel_rect
        assert pygame.Rect(0, 0, *size).contains(panel)
        yes, later = recap.wishlist_buttons['wishlist_yes'], recap.wishlist_buttons['wishlist_later']
        assert panel.contains(yes) and panel.contains(later) and not yes.colliderect(later)
        recap._update_wishlist_prompt(5.0)
        recap.render()                                                          # draws without errors

    def test_wishlist_opens_the_page_and_closes(self, marked, opens, clicks, monkeypatch):
        recap = _recap()
        recap._update_wishlist_prompt(5.0)
        pos = recap.wishlist_buttons['wishlist_yes'].center
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pos)
        _click(pos)
        recap.handle_events()
        assert opens == [1] and clicks == [1]
        assert recap.wishlist_phase == 'closed' and not recap.done

    def test_not_now_closes_without_opening(self, marked, opens, clicks, monkeypatch):
        recap = _recap()
        recap._update_wishlist_prompt(5.0)
        pos = recap.wishlist_buttons['wishlist_later'].center
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pos)
        _click(pos)
        recap.handle_events()
        assert opens == [] and clicks == [1] and recap.wishlist_phase == 'closed'

    def test_modal_escape_closes_only_the_prompt(self, marked, opens, monkeypatch):
        recap = _recap()
        recap._update_wishlist_prompt(5.0)
        pos = recap.return_button_rect.center                                   # under the dimming
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pos)
        _click(pos)
        recap.handle_events()
        assert not recap.done and recap.wishlist_phase == 'open'                # the recap waits
        _key(pygame.K_ESCAPE)
        recap.handle_events()
        assert recap.wishlist_phase == 'closed' and not recap.done and opens == []
        _key(pygame.K_ESCAPE)
        recap.handle_events()
        assert recap.done                                                       # then Escape leaves as before
