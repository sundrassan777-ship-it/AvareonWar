# tests/conftest.py
# Shared pytest setup: one video driver for every run, the settings and the log kept away
# from this PC's own files, map data reset before each test, pictures decoded once per run.

"""
Session setup (pytest_configure, before any test module is imported):

- SDL_VIDEODRIVER=dummy for every run: no windows, no fullscreen switches, and a test file run
  alone sees the same driver as the full suite (a test module used to set it while being
  collected, so the full suite ran on the dummy driver and single files on real windows).
  A benchmark run keeps the real driver: the FPS benchmarks measure the real display.
- settings (settings_manager) read and write a temp config.json, never the game folder's.
  A normal run starts from the defaults (a fresh install) in a 1600x900 window, so this PC's
  profile, monitor and display options decide nothing. A benchmark run starts from this PC's
  settings, as the benchmarks always have, but saves nothing either.
- the game log (utils.logger, set up when main.py is imported) goes to a temp folder, so a
  test run does not push the player's own log out of logs/avareonwar.log.
- pygame.image.load decodes each picture inside the project once and hands out copies: a
  test Game decodes the same 82 pictures (about 1.9 s), and some 1,300 tests build one.
- the FPS benchmarks (@pytest.mark.benchmark) run only when asked for: name
  tests/test_fps_benchmark.py on the command line, or pass -m benchmark.

Per test:

- map_data is reloaded and campaign territory filtering cleared (campaign_mission_4 calls
  set_enabled_territories(), which filters 57 territories down to 21).
- the settings are put back afterwards (a test that earns an achievement, changes an option
  or replaces the SettingsManager singleton leaves nothing behind), and every test starts in
  the 2D map look (tests that want 3D set it themselves, tests/test_map_look.py).
"""

import collections
import copy
import logging
import os
import shutil
import sys
import tempfile

import pytest

# Ensure project root is on sys.path for all test files
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import map_data

# What every normal run plays with on top of the defaults
TEST_SETTINGS = {
    'fullscreen': False,
    'resolution': [1600, 900],
    'default_resolution': [1600, 900],
    'vsync': False,
    'map_style': '2d',
}

_session = {}


def _is_benchmark_run(config):
    """The run asks for the FPS benchmarks: their file is named, or -m selects them."""
    markexpr = config.getoption('markexpr') or ''
    if 'benchmark' in markexpr.replace('not benchmark', ''):
        return True
    return any('test_fps_benchmark' in str(arg) for arg in config.args)


class _DecodeCache:
    """pygame.image.load for the test run. A picture inside the project is decoded once and
    every call gets a copy (the same pixels and format as a fresh decode, free to change).
    Anything else - file objects, a namehint, pictures outside the project such as tmp_path
    ones, a missing file - goes straight to the real load. Tests that count decodes wrap this
    function and still see every call the game makes."""

    LIMIT_BYTES = 600 * 2 ** 20

    def __init__(self, load):
        self.load = load
        self.root = os.path.normcase(ROOT) + os.sep
        self.surfaces = collections.OrderedDict()
        self.held = 0

    def __call__(self, file, *args, **kwargs):
        if args or kwargs or not isinstance(file, (str, os.PathLike)):
            return self.load(file, *args, **kwargs)
        path = os.path.normcase(os.path.abspath(os.fspath(file)))
        if not path.startswith(self.root):
            return self.load(file)
        try:
            stat = os.stat(path)
        except OSError:
            return self.load(file)
        key = (path, stat.st_mtime_ns, stat.st_size)
        surface = self.surfaces.get(key)
        if surface is None:
            surface = self.load(file)
            self.surfaces[key] = surface
            self.held += self._bytes(surface)
            while self.held > self.LIMIT_BYTES and len(self.surfaces) > 1:
                _, oldest = self.surfaces.popitem(last=False)
                self.held -= self._bytes(oldest)
        else:
            self.surfaces.move_to_end(key)
        return surface.copy()

    @staticmethod
    def _bytes(surface):
        return surface.get_width() * surface.get_height() * surface.get_bytesize()


def pytest_configure(config):
    benchmark_run = _is_benchmark_run(config)
    _session['benchmark_run'] = benchmark_run
    if not benchmark_run:
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

    temp_dir = tempfile.mkdtemp(prefix='avareonwar-tests-')
    _session['temp_dir'] = temp_dir

    import utils.logger
    utils.logger.LOG_DIR = os.path.join(temp_dir, 'logs')

    # Importing settings_manager loads the game folder's config.json (read only)
    import settings_manager
    from settings_manager import settings
    config_path = os.path.join(temp_dir, 'config.json')
    settings_manager.get_config_path = lambda: config_path   # a fresh SettingsManager() too
    settings.config_file = config_path
    if not benchmark_run:
        settings.settings = copy.deepcopy(settings.defaults)
        settings.settings.update(copy.deepcopy(TEST_SETTINGS))
        settings.default_resolution = tuple(TEST_SETTINGS['default_resolution'])
    settings.save()

    import pygame
    _session['real_image_load'] = pygame.image.load
    pygame.image.load = _DecodeCache(pygame.image.load)


def pytest_unconfigure(config):
    if 'real_image_load' in _session:
        import pygame
        pygame.image.load = _session.pop('real_image_load')
    temp_dir = _session.pop('temp_dir', None)
    if temp_dir:
        # The log file is still open: close it so the folder can go
        root = logging.getLogger()
        inside = os.path.normcase(os.path.abspath(temp_dir)) + os.sep
        for handler in list(root.handlers):
            log_path = getattr(handler, 'baseFilename', None)
            if log_path and os.path.normcase(os.path.abspath(log_path)).startswith(inside):
                handler.close()
                root.removeHandler(handler)
        shutil.rmtree(temp_dir, ignore_errors=True)


def pytest_collection_modifyitems(config, items):
    if _session.get('benchmark_run'):
        return
    benchmarks = [item for item in items if item.get_closest_marker('benchmark')]
    if benchmarks:
        config.hook.pytest_deselected(items=benchmarks)
        items[:] = [item for item in items if not item.get_closest_marker('benchmark')]


@pytest.fixture(autouse=True)
def clean_map_data():
    """Reset map_data state before each test to prevent contamination.

    Campaign missions call map_data.set_enabled_territories() which filters
    the territory list globally. This fixture ensures every test starts with
    the full 57-territory map.
    """
    map_data.load_polygons()
    map_data.clear_enabled_territories()
    yield
    # Post-test cleanup: restore full territory list
    map_data.clear_enabled_territories()


@pytest.fixture(autouse=True)
def isolated_settings():
    """Every test starts from the session's settings in the 2D map look, and leaves nothing
    behind: the values (restored in place - code keeps the dict), the dict itself, the file
    and the SettingsManager singleton (some tests make a fresh one)."""
    from settings_manager import SettingsManager, settings
    values = settings.settings
    saved = copy.deepcopy(values)
    config_file = settings.config_file
    instance = SettingsManager._instance
    values['map_style'] = '2d'
    yield
    SettingsManager._instance = instance
    settings.config_file = config_file
    settings.settings = values
    values.clear()
    values.update(saved)
