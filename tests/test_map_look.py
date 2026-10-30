# -*- coding: utf-8 -*-
"""
Map looks: 2D (the painted maps) or 3D (AvareonWorldEditor's looks in maps/<id>/3d and
assets/CampaignMaps/3d) - map_data "Map looks", CODE_GUIDE "Map looks: 2D / 3D".

Locked (MAP_3D_AVAILABLE False): every screen is exactly as before, whatever config.json
says, and the Options have no row. With the lock patched open: every map view - the game,
Custom Game setup, the lobby, replays, campaign missions with their cloud covers, Book of
Tales - shows the 3D look, its picture and its outlines from the same look; anything
missing or out of date is 2D. Mixed 2D / 3D multiplayer: tests/test_mp_map_look.py.
"""

import inspect
import json
import os
import sys

import pytest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

import config.constants as constants  # noqa: E402
import map_data  # noqa: E402
from settings_manager import settings  # noqa: E402

AVAREON_3D = 'maps/avareon/3d/map.png'
HIGHLANDS_2D = 'maps/azincournean_highlands/map.png'
HIGHLANDS_3D = 'maps/azincournean_highlands/3d/map.png'
CAMPAIGN = 'assets/CampaignMaps'


def _config(map_id='avareon'):
    return {'map_id': map_id, 'num_players': 2, 'player_is_ai': [False, True],
            'player_ai_difficulty': [0, 0], 'player_teams': [0, 1], 'win_condition': 'Total Conquest',
            'taxation_level': 0}


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield
    map_data.load_map('avareon')
    pygame.quit()


@pytest.fixture
def style(monkeypatch):
    """style('3d' / '2d'): the map_style saved in config.json (restored afterwards)."""
    before = settings.settings.get('map_style')

    def set_style(value):
        settings.settings['map_style'] = value
    yield set_style
    settings.settings['map_style'] = before


@pytest.fixture
def unlocked(monkeypatch, style):
    """The switch unhidden (as if MAP_3D_AVAILABLE were True) and 3D chosen."""
    import main_menu
    from ui import options_panel
    monkeypatch.setattr(constants, 'MAP_3D_AVAILABLE', True)
    monkeypatch.setattr(main_menu, 'MAP_3D_AVAILABLE', True)
    monkeypatch.setattr(options_panel, 'MAP_3D_AVAILABLE', True)   # The Options window's row
    style('3d')
    yield
    map_data._look_cache.clear()


def _game(map_id='avareon', campaign_map=None):
    from main import Game
    game = Game(campaign_map=campaign_map)
    game.initialize_game(_config(map_id))
    return game


def _file_polygons(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _scaled(game, polygons, name):
    return [(round(x * game.scale_factor), round(y * game.scale_factor)) for x, y in polygons[name]]


# --- Locked: nothing changes ---------------------------------------------------------------

def test_reminder_hide_before_the_next_patch_release():
    """The owner unhid the switch for testing (2026-10-26) and wants it hidden again for the
    next patch release: every test run says so while MAP_3D_AVAILABLE is True."""
    if constants.MAP_3D_AVAILABLE:
        import warnings
        warnings.warn('The 3D map look is UNHIDDEN (MAP_3D_AVAILABLE = True in config/constants.py): '
                      'hide it again before the next patch release.', UserWarning)


class TestLocked:
    """The switch locked (MAP_3D_AVAILABLE False, whatever the constant says right now)."""

    @pytest.fixture(autouse=True)
    def locked(self, monkeypatch):
        import main_menu
        from ui import options_panel
        monkeypatch.setattr(constants, 'MAP_3D_AVAILABLE', False)
        monkeypatch.setattr(main_menu, 'MAP_3D_AVAILABLE', False)
        monkeypatch.setattr(options_panel, 'MAP_3D_AVAILABLE', False)   # The Options window's row

    def test_config_json_cannot_turn_3d_on(self, style, monkeypatch):
        style('3d')
        def no_reading(map_id):
            raise AssertionError('a look.json was read while locked')
        monkeypatch.setattr(map_data, 'look_info', no_reading)
        assert map_data.map_look() == '2d'
        for map_id in ('avareon', 'azincournean_highlands'):
            picture = map_data.default_picture(map_id)
            assert map_data.choose_look(map_id, map_data.pictures_needed(picture)) == '2d'
            assert map_data.look_picture(picture, map_id) == picture

    def test_todays_pictures(self):
        assert map_data.default_picture('avareon') == 'assets/map.png'
        assert map_data.default_picture('azincournean_highlands') == HIGHLANDS_2D
        assert map_data.default_picture('naragonthid') is None              # no background: dark map

    def test_a_game_is_2d(self, style):
        style('3d')
        game = _game('azincournean_highlands')
        assert game.map_look == '2d' and game.map_background_path == HIGHLANDS_2D
        polygons = _file_polygons('maps/azincournean_highlands/territory_polygons.json')
        name = next(iter(polygons))
        assert game.scaled_polygons[name] == _scaled(game, polygons, name)
        assert map_data.current_map_draws_borders() is True                   # the manifest's

    def test_a_campaign_game_keeps_its_picture(self, style):
        style('3d')
        game = _game(campaign_map=f'{CAMPAIGN}/Campaign3Map.png')
        assert game.map_look == '2d' and game.map_background_path == f'{CAMPAIGN}/Campaign3Map.png'
        assert map_data.look_picture(f'{CAMPAIGN}/CampaignMission1Cover.png') == f'{CAMPAIGN}/CampaignMission1Cover.png'

    def test_no_options_row(self, style):
        import main_menu
        style('3d')
        menu = main_menu.MainMenu(pygame.display.get_surface())
        menu._open_options()
        rows = [row.key for row in menu.options_panel.rows]
        assert 'map_look' not in rows
        assert 'show_fps' in rows

    def test_saved_style_is_validated(self):
        settings.settings['map_style'] = 'isometric'
        before = dict(settings.settings)
        try:
            settings._validate_and_clean_settings()
            assert settings.settings['map_style'] == '2d'
        finally:
            settings.settings.clear()
            settings.settings.update(before)
            settings.settings['map_style'] = '2d'


# --- Unlocked: every view in 3D --------------------------------------------------------------

class TestUnlocked:

    def test_the_options_choose_the_look(self, unlocked, style):
        assert map_data.map_look() == '3d'
        style('2d')
        assert map_data.map_look() == '2d'

    def test_a_game_shows_the_3d_look(self, unlocked):
        game = _game('avareon')
        assert game.map_look == '3d' and game.map_background_path == AVAREON_3D
        polygons = _file_polygons('maps/avareon/3d/territory_polygons.json')
        for name in list(polygons)[:5]:
            assert game.scaled_polygons[name] == _scaled(game, polygons, name)
        plots = _file_polygons('maps/avareon/3d/plots.json')
        name = next(n for n in plots if plots[n])
        assert game.scaled_plots[name][0] == (round(plots[name][0][0] * game.scale_factor),
                                              round(plots[name][0][1] * game.scale_factor))
        assert map_data.current_map_draws_borders() is False

    def test_highlands_borders_are_baked_in(self, unlocked):
        game = _game('azincournean_highlands')
        assert game.map_background_path == HIGHLANDS_3D
        assert map_data.current_map_draws_borders() is False                  # look.json: baked

    def test_every_campaign_picture_has_its_twin(self, unlocked):
        for n in range(1, 7):
            picture = f'{CAMPAIGN}/Campaign{n}Map.png'
            assert map_data.choose_look('avareon', map_data.pictures_needed(picture)) == '3d'
            assert map_data.look_picture(picture, 'avareon', '3d') == f'{CAMPAIGN}/3d/Campaign{n}Map.png'

    def test_a_campaign_game_shows_the_chapters_twin_and_cover(self, unlocked):
        game = _game(campaign_map=f'{CAMPAIGN}/Campaign1Map.png')
        assert game.map_look == '3d'
        assert game.map_background_path == f'{CAMPAIGN}/3d/Campaign1Map.png'
        assert map_data.look_picture(f'{CAMPAIGN}/CampaignMission1Cover.png') == \
            f'{CAMPAIGN}/3d/CampaignMission1Cover.png'

    def test_the_tutorial_lays_its_3d_cover(self, unlocked, monkeypatch):
        """The tutorial's own cover code, as main.py runs it, reads the 3D cover."""
        import tutorial_mission
        game = _game(campaign_map=f'{CAMPAIGN}/Campaign1Map.png')
        loaded = []
        real_load = pygame.image.load
        monkeypatch.setattr(pygame.image, 'load', lambda path, *a: loaded.append(path) or real_load(path, *a))
        mission = object.__new__(tutorial_mission.TutorialMission)
        mission.main_game = game
        tutorial_mission.TutorialMission._bake_cloud_cover(mission)
        assert loaded == [f'{CAMPAIGN}/3d/CampaignMission1Cover.png']

    def test_book_of_tales_on_the_highlands(self, unlocked):
        game = _game('azincournean_highlands', campaign_map=HIGHLANDS_2D)    # Tale I
        assert game.map_look == '3d' and game.map_background_path == HIGHLANDS_3D

    def test_setup_lobby_and_replay_show_3d(self, unlocked):
        from integrated_setup import IntegratedSetup
        from network.territory_selector import TerritorySelector
        from tests.test_map_top_bar import _StubConnection
        surface = pygame.display.get_surface()
        map_data.load_map('avareon')
        IntegratedSetup(surface)
        assert map_data.get_current_look() == '3d'
        map_data.load_map('avareon')
        TerritorySelector(surface, _StubConnection(), is_host=True, local_player_index=0)
        assert map_data.get_current_look() == '3d'
        import replay_viewer
        source = inspect.getsource(replay_viewer.ReplayViewer._load_map_assets)
        assert 'choose_look' in source and 'look_picture' in source

    def test_a_changed_2d_outline_makes_it_2d(self, unlocked, monkeypatch):
        real = map_data._read_json

        def edited(path):
            data = real(path)
            if path.replace('\\', '/') == 'maps/avareon/territory_polygons.json':
                name = next(iter(data))
                data[name] = data[name][:-1]                                  # someone edited the map
            return data
        monkeypatch.setattr(map_data, '_read_json', edited)
        map_data._look_cache.clear()
        assert map_data.look_info('avareon') is None
        game = _game('avareon')
        assert game.map_look == '2d' and game.map_background_path == 'assets/map.png'

    def test_a_missing_cover_twin_keeps_the_whole_game_2d(self, unlocked, monkeypatch):
        real_exists = os.path.exists
        monkeypatch.setattr(map_data.os.path, 'exists',
                            lambda p: False if 'CampaignMission1Cover' in str(p) and '/3d/' in str(p).replace('\\', '/')
                            else real_exists(p))
        assert map_data.choose_look('avareon', map_data.pictures_needed(f'{CAMPAIGN}/Campaign1Map.png')) == '2d'
        assert map_data.choose_look('avareon', map_data.pictures_needed(f'{CAMPAIGN}/Campaign3Map.png')) == '3d'

    def test_a_changed_2d_picture_makes_it_2d(self, unlocked, monkeypatch):
        real_hash = map_data._file_hash
        monkeypatch.setattr(map_data, '_file_hash',
                            lambda p: 'changed' if 'Campaign3Map' in str(p) else real_hash(p))
        assert map_data.choose_look('avareon', map_data.pictures_needed(f'{CAMPAIGN}/Campaign3Map.png')) == '2d'
        assert map_data.choose_look('avareon', ['assets/map.png']) == '3d'

    def test_options_row_main_menu_only(self, unlocked, monkeypatch):
        import main_menu
        from main import Game
        from global_sound import sound_manager
        monkeypatch.setattr(sound_manager, 'play_ui_click', lambda *a, **k: None)
        monkeypatch.setattr(settings, 'save', lambda *a, **k: None)
        menu = main_menu.MainMenu(pygame.display.get_surface())
        menu._open_options()
        menu.options_panel.anim.finish()
        assert menu.temp_map_3d is True
        rect = menu.options_panel.part_rect(('choice', 'map_look', 0))    # "2D"
        menu.handle_click(rect.center)
        assert menu.temp_map_3d is False
        menu._apply_options()
        assert settings.get('map_style') == '2d'
        menu._reset_to_defaults()
        assert menu.temp_map_3d is False
        # Never in the in-game options: the look is read when a screen loads its map
        assert 'map_style' not in inspect.getsource(Game.handle_options_menu_click)


# --- The shipped looks ----------------------------------------------------------------------

@pytest.mark.parametrize('map_id', ['avareon', 'azincournean_highlands'])
def test_shipped_looks_are_current(map_id):
    """The looks in the repo were made from the 2D outlines and plots the maps have now
    (re-export from AvareonWorldEditor after editing them), every twin is current, and
    the 3D geometry stays inside the picture."""
    map_data._look_cache.clear()
    info = map_data.look_info(map_id)
    assert info is not None, f'{map_id}: re-export its 3D look (AvareonWorldEditor --export-looks)'
    for picture, entry in info['pictures'].items():
        assert map_data._twin(info, picture) == entry['path'], picture
    polygons = _file_polygons(os.path.join(info['dir'], 'territory_polygons.json'))
    plots = _file_polygons(os.path.join(info['dir'], 'plots.json'))
    for name, points in list(polygons.items()) + list(plots.items()):
        for x, y in points:
            assert 0 <= x <= 4096 and 0 <= y <= 3072, name


@pytest.mark.parametrize('map_id', ['avareon', 'azincournean_highlands'])
def test_3d_plots_stay_in_their_territory(map_id):
    """A plot inside its territory in 2D is inside it in 3D too: clicks find it."""
    look_dir = os.path.join(map_data.get_map_directory(map_id), '3d')
    map_dir = map_data.get_map_directory(map_id)
    polygons_2d = _file_polygons(os.path.join(map_dir, 'territory_polygons.json'))
    plots_2d = _file_polygons(os.path.join(map_dir, 'plots.json'))
    polygons_3d = _file_polygons(os.path.join(look_dir, 'territory_polygons.json'))
    plots_3d = _file_polygons(os.path.join(look_dir, 'plots.json'))
    checked = 0
    for name, points in plots_2d.items():
        for k, point in enumerate(points):
            if map_data.point_in_polygon(point, polygons_2d[name]):
                assert map_data.point_in_polygon(plots_3d[name][k], polygons_3d[name]), f'{name} plot {k + 1}'
                checked += 1
    assert checked > 50
