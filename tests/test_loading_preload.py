# -*- coding: utf-8 -*-
"""
The loading screen's preloading (2026-10-31): work that waited for its first use during
play is done under the progress bar, and work that was repeated is done once.

- every task after "Initializing game" only prepares this PC's pictures: the shared random
  numbers and the multiplayer state checksum are the same before and after them, so
  multiplayer PCs stay identical
- a campaign mission's loading_tasks() run on the loading screen, after the game is
  initialized (the cloud cover); multiplayer games get none
- Game.__init__ decodes no map picture for a non-campaign game (initialize_game does)
- the battle window decodes none of its pictures; the splash holds the kept picture,
  pixel-identical
- the Technology tab's icons are decoded on the loading screen, pixel-identical at the
  largest button; opening the tab decodes none
- the cloud cover's alpha bake is byte-identical to the per-pixel loop it replaces, once
  per game
- the Transmission Board's art is decoded once per process, at the old sizes
- game sounds are decoded once per process; a later game only sets their volume
- the Players window keeps its fonts and backdrop between frames
"""

import os
import random
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield


@pytest.fixture(autouse=True)
def no_saving(monkeypatch):
    from settings_manager import settings
    monkeypatch.setattr(settings, 'save', lambda *a, **k: None)


def _spy_loads(monkeypatch):
    """Record the path of every pygame.image.load from now on (normalised)."""
    loads = []
    real_load = pygame.image.load
    monkeypatch.setattr(pygame.image, 'load',
                        lambda path, *a: loads.append(os.path.normpath(str(path))) or real_load(path, *a))
    return loads


def _pixels(surface):
    return pygame.image.tostring(surface, 'RGBA')


@pytest.fixture(scope='module')
def custom_game():
    """
    A custom game (a human and an AI) through the loading screen's tasks - all but the
    sounds - with every picture decode recorded, and the shared random numbers and the
    state checksum taken right after "Initializing game" and at the end.
    """
    from loading_screen import LoadingScreen
    from main import Game
    from rendering import ui_renderer
    from settings_manager import settings
    ui_renderer._tech_icon_sources.clear()      # as in a new process (kept for the process)
    loads = []
    real_load, real_save = pygame.image.load, settings.save
    pygame.image.load = lambda path, *a: loads.append(os.path.normpath(str(path))) or real_load(path, *a)
    settings.save = lambda *a, **k: None
    try:
        game = Game()
        loads_in_init = list(loads)
        config = {'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]}
        tasks = LoadingScreen(pygame.display.get_surface(), game, config)._build_task_list()
        labels = [label for label, _ in tasks]
        record = {}
        for label, task in tasks[labels.index('Initializing game'):]:
            task()
            if label == 'Initializing game':
                record['after_init'] = (random.getstate(), game.game_state.calculate_state_checksum())
                record['loads_after_init'] = len(loads)
        record['at_end'] = (random.getstate(), game.game_state.calculate_state_checksum())
    finally:
        pygame.image.load, settings.save = real_load, real_save
    game.game_state.phase = 'playing'
    return SimpleNamespace(game=game, labels=labels, loads=loads, loads_in_init=loads_in_init, **record)


class TestTheLoadingScreen:

    def test_preloading_after_initializing_is_render_only(self, custom_game):
        after = custom_game.labels[custom_game.labels.index('Initializing game') + 1:]
        assert after == ['Preparing the battle screen', 'Preparing the technology tree',
                         'Preparing the computer players']
        # The same random numbers and game state as right after "Initializing game"
        assert custom_game.at_end == custom_game.after_init

    def test_a_mission_task_runs_after_initializing(self, display):
        from loading_screen import LoadingScreen
        game = SimpleNamespace(local_player_index=0, campaign_map='x.png')
        tasks = LoadingScreen(pygame.display.get_surface(), game,
                              {'num_players': 2, 'player_is_ai': [False, False]},
                              extra_tasks=[('Drawing the cloud cover', lambda: None)])._build_task_list()
        labels = [label for label, _ in tasks]
        # No AI player: no AI task; the mission's task last, after the game is initialized
        assert 'Preparing the computer players' not in labels
        assert labels.index('Initializing game') < labels.index('Drawing the cloud cover') == len(labels) - 1

    def test_campaign_paths_pass_the_missions_tasks_and_multiplayer_none(self):
        with open(os.path.join(ROOT, 'main.py'), encoding='utf-8') as f:
            source = f.read()
        assert source.count('extra_tasks=_mission_loading_tasks(MissionClass, game)') == 2
        multiplayer = source[source.index('def _play_multiplayer_game'):]
        call = multiplayer[multiplayer.index('LoadingScreen('):multiplayer.index('loading.run()')]
        assert 'extra_tasks' not in call

    def test_the_tutorial_and_mission_2_bake_their_cover_while_loading(self):
        import tutorial_mission
        import campaign_mission_2
        for mission in (tutorial_mission.TutorialMission, campaign_mission_2.Mission2):
            tasks = mission.loading_tasks(SimpleNamespace())
            assert [label for label, _ in tasks] == ['Drawing the cloud cover']


class TestAMultiplayerGameLoads:
    """
    Every PC of a multiplayer game (real Games over the real server / client code,
    tests/mp_harness.py) through the loading screen's tasks after "Initializing game":
    each PC keeps the state it had, all PCs have the same, and the game then plays in
    step - turns, and a battle resolved on one PC replayed on the other.
    """

    @staticmethod
    def _load_every_pc(session):
        """Each PC's loading screen as _play_multiplayer_game() builds it (with its network
        connection), then its tasks after "Initializing game" (the harness initialized the
        games). Returns the task labels. The screen itself picks its tip with the shared
        random numbers - as it always did, before the game is initialized - so the random
        state is compared around the tasks only."""
        from loading_screen import LoadingScreen
        screens = {index: LoadingScreen(pygame.display.get_surface(), peer.game, session.config,
                                        network_connection=session.net.server if index == 0
                                        else session.net.clients[index])
                   for index, peer in session.peers.items()}
        rng = random.getstate()
        labels = []
        for screen in screens.values():
            tasks = screen._build_task_list()
            labels = [label for label, _ in tasks]
            for _label, task in tasks[labels.index('Initializing game') + 1:]:
                task()
        assert random.getstate() == rng
        return labels

    @staticmethod
    def _same_everywhere(session):
        """
        What the players have - owners, gold, buildings and every garrison unit (type,
        level, xp, status, id, the moved / unmoved counts) - the same on every PC. The raw
        checksum is not compared across PCs: a unit's missing 'order' key and 'order': None
        hash differently, and the host's units come from snapshots without the key.
        """
        def garrisons(gs):
            return {t: {str(p): {**{k: v for k, v in g.items() if k != 'units'},
                                 'units': [{k: v for k, v in u.items() if k != 'order'}
                                           for u in g.get('units', [])]}
                        for p, g in players.items() if g.get('units') or g.get('unmoved') or g.get('moved')}
                    for t, players in gs.territory_garrisons.items()}
        views = [(dict(gs.territory_owners), list(gs.player_gold), dict(gs.buildings), garrisons(gs))
                 for gs in (peer.gs for peer in session.peers.values())]
        assert all(view == views[0] for view in views)

    @pytest.mark.parametrize('turn_mode', ['sequential', 'simultaneous'])
    def test_every_pc_loads_and_the_game_stays_in_step(self, make_session, turn_mode):
        import mp_harness as h
        session = make_session(num_players=3, ai_slots=(2,), turn_mode=turn_mode)
        before = {i: peer.gs.calculate_state_checksum() for i, peer in session.peers.items()}
        labels = self._load_every_pc(session)
        assert 'Preparing the technology tree' in labels and 'Preparing the computer players' in labels
        # Each PC has the state it had before the tasks, and all PCs the same
        assert {i: peer.gs.calculate_state_checksum() for i, peer in session.peers.items()} == before
        self._same_everywhere(session)
        # The game plays on in step
        if turn_mode == 'sequential':
            h.click_end_turn(session.game(0))
            session.run_until_quiet()
            assert session.gs(0).current_player == session.gs(1).current_player == 1
        self._same_everywhere(session)

    def test_a_battle_after_loading_is_replayed_in_step(self, make_session):
        import mp_harness as h
        from test_mp_battles import client_attacks_host, fight_it_out
        session = make_session(num_players=2)
        self._load_every_pc(session)
        # The client attacks the host; its battle window (the shared, prewarmed pictures)
        # resolves it and the host replays it from the seed
        _, b = client_attacks_host(session)
        h.click_end_turn(session.game(1))
        session.step_until(lambda: any(bt.territory == b for bt in session.gs(1).pending_battles))
        fight_it_out(session, b)
        session.run_until_quiet()
        assert session.gs(0).territory_owners[b] == session.gs(1).territory_owners[b] == 1
        self._same_everywhere(session)


class TestTheMapPicture:

    def test_a_custom_game_decodes_its_map_picture_once(self, custom_game):
        picture = os.path.normpath(custom_game.game.map_background_path)
        assert picture not in custom_game.loads_in_init      # Game() no longer decodes it
        assert custom_game.loads.count(picture) == 1          # initialize_game() does

    def test_a_campaign_game_decodes_its_picture_as_before(self, monkeypatch):
        from main import Game
        loads = _spy_loads(monkeypatch)
        picture = 'assets/CampaignMaps/Campaign1Map.png'
        game = Game(campaign_map=picture)
        assert os.path.normpath(picture) in loads
        assert game.map_image_original.get_size() == pygame.image.load(picture).get_size()

    def test_main_py_lets_the_multiplayer_menus_game_go(self):
        with open(os.path.join(ROOT, 'main.py'), encoding='utf-8') as f:
            source = f.read()
        branch = source.index("elif action == 'multiplayer':")
        released = source.index('game = None', branch)
        assert released < source.index('_play_multiplayer_game(screen, mode', branch)


class TestTheBattleWindow:

    def test_a_battle_window_decodes_none_of_its_pictures(self, monkeypatch):
        from ui.effects import battle_interface as bi
        from tests.test_battle_report_screen import _battle_window
        screen = pygame.display.get_surface()
        bi.prewarm_battle_screen(screen.get_size())
        loads = _spy_loads(monkeypatch)
        for _ in range(2):
            ui, _gs, _battle = _battle_window(screen)
            assert ui.battle_icon is not None and ui._scaled_bar_border is not None
            assert ui.victory_img is not None and ui.defeat_img is not None
        arts = {os.path.normpath(p) for p in (bi.BATTLE_ICON_ART, bi.BATTLE_BAR_ART,
                                              bi.VICTORY_SPLASH_ART, bi.DEFEAT_SPLASH_ART)}
        assert not arts & set(loads)

    def test_the_icon_and_frame_are_the_old_pixels(self):
        from ui import battle_screen_kit
        from ui.effects import battle_interface as bi
        icon = pygame.image.load(bi.BATTLE_ICON_ART).convert_alpha()
        old_icon = pygame.transform.smoothscale(icon, (int(icon.get_width() * 0.255), int(icon.get_height() * 0.255)))
        assert _pixels(bi.battle_icon_art(1.0)) == _pixels(old_icon)
        bar = pygame.image.load(bi.BATTLE_BAR_ART).convert_alpha()
        size = (int(1600 * bi.BAR_PNG_WIDTH_RATIO), bi.BAR_PNG_HEIGHT_REF)
        assert _pixels(battle_screen_kit.art(bi.BATTLE_BAR_ART, size)) == \
            _pixels(pygame.transform.smoothscale(bar, size))

    @pytest.mark.parametrize('path_name', ['VICTORY_SPLASH_ART', 'DEFEAT_SPLASH_ART'])
    def test_the_splash_holds_the_kept_picture(self, path_name):
        from ui.effects import battle_interface as bi
        path = getattr(bi, path_name)
        full = pygame.image.load(path).convert_alpha()
        kept, base = bi.splash_art(path)
        assert base == full.get_size()
        assert kept.get_size() == (int(base[0] * bi.SPLASH_TARGET_SCALE), int(base[1] * bi.SPLASH_TARGET_SCALE))
        frames = []
        for image, base_size in ((full, None), (kept, base)):
            splash = bi.BattleSplashEffect(image, 1600, 900, base_size=base_size)
            looks = []
            for elapsed in (0.25, 1.5, 2.75):          # growing, holding, shrinking
                splash.elapsed = elapsed
                surface = pygame.Surface((1600, 900))
                splash.render(surface)
                looks.append(surface)
            frames.append(looks)
        (old_grow, old_hold, old_shrink), (new_grow, new_hold, new_shrink) = frames
        # The hold - two of its three seconds - is pixel-identical; growing and shrinking
        # draw the same size in the same place (scaled from the kept picture)
        assert pygame.image.tostring(new_hold, 'RGB') == pygame.image.tostring(old_hold, 'RGB')
        for old, new in ((old_grow, new_grow), (old_shrink, new_shrink)):
            assert new.get_bounding_rect() == old.get_bounding_rect()


class TestTheTechnologyTab:

    def test_its_icons_are_decoded_on_the_loading_screen(self, custom_game, monkeypatch):
        from rendering.ui_renderer import TECH_BUTTON_MAX
        game = custom_game.game
        paths = sorted({t['icon'] for t in game.game_state.technologies
                        if t.get('icon') and os.path.exists(t['icon'])})
        assert len(paths) == 21
        while_loading = custom_game.loads[custom_game.loads_after_init:]
        assert all(os.path.normpath(p) in while_loading for p in paths)
        # Opening the tab decodes none of them
        loads = _spy_loads(monkeypatch)
        game.game_state.active_sidebar_tab = 'technology'
        game.game_state.sidebar_expanded = True
        game.draw()
        assert not {os.path.normpath(p) for p in paths} & set(loads)
        assert len(game.ui_renderer.tech_icons) >= 21
        # At the largest button, the old decode's pixels
        monkeypatch.undo()
        old = pygame.transform.scale(pygame.image.load(paths[0]).convert_alpha(), (TECH_BUTTON_MAX,) * 2)
        assert _pixels(game.ui_renderer._tech_icon_source(paths[0])) == _pixels(old)


class TestTheCloudCover:

    def _cover(self, tmp_path):
        rng = random.Random(20261031)
        cover = pygame.Surface((37, 23))           # odd sizes: no row or pixel alignment luck
        for x in range(37):
            for y in range(23):
                cover.set_at((x, y), (rng.randrange(256), rng.randrange(256), rng.randrange(256)))
        path = str(tmp_path / 'cover.png')
        pygame.image.save(cover, path)
        return path

    def test_the_bake_is_byte_identical_to_the_old_loop_and_runs_once(self, tmp_path, monkeypatch):
        import campaign_utils
        path = self._cover(tmp_path)
        # The old per-pixel loop
        raw = pygame.image.load(path).convert()
        pixels = bytearray(pygame.image.tostring(raw, 'RGBA'))
        for i in range(0, len(pixels), 4):
            pixels[i + 3] = max(pixels[i], pixels[i + 1], pixels[i + 2])
        expected = pygame.Surface((37, 23))
        expected.fill((40, 80, 120))
        expected.blit(pygame.image.fromstring(bytes(pixels), (37, 23), 'RGBA'), (0, 0))

        invalidated = []
        game = SimpleNamespace(map_image_original=pygame.Surface((37, 23)),
                               _invalidate_map_background_caches=lambda: invalidated.append(1))
        game.map_image_original.fill((40, 80, 120))
        campaign_utils.bake_cloud_cover(game, path)
        assert pygame.image.tostring(game.map_image_original, 'RGB') == pygame.image.tostring(expected, 'RGB')
        assert invalidated == [1]
        # Baked on the loading screen: the mission's own call does nothing
        loads = _spy_loads(monkeypatch)
        campaign_utils.bake_cloud_cover(game, path)
        assert loads == [] and invalidated == [1]


class TestTheTransmissionBoard:

    def test_its_art_is_decoded_once_at_the_old_sizes(self, monkeypatch):
        import campaign_utils
        import tutorial_mission
        monkeypatch.setattr(campaign_utils, '_board_art', {})
        loads = _spy_loads(monkeypatch)
        boards = [campaign_utils.TransmissionOverlay(1600, 900, 'Text', 60, 'Speaker'),
                  campaign_utils.TransmissionOverlay(1600, 900, 'Other', 60),
                  tutorial_mission.TransmissionOverlay(1600, 900, 'Text', 60, 'Speaker')]
        assert loads.count(os.path.normpath('assets/TransmissionBG.png')) == 1
        assert loads.count(os.path.normpath('assets/SpeakerBG.png')) == 1
        monkeypatch.undo()
        bg = pygame.image.load('assets/TransmissionBG.png')
        header = pygame.image.load('assets/SpeakerBG.png')
        width = int(1600 * 0.29)
        visible = width - 2 * int(width * 0.069)
        for board in boards:
            assert board.bg_surface.get_size() == (width, int(width * (bg.get_height() / bg.get_width())))
            assert board.body_height == board.bg_surface.get_height()
            assert board.header_surface.get_size() == (
                visible, int(int(visible * (header.get_height() / header.get_width())) * 0.2))


class TestTheSounds:

    @pytest.fixture
    def sound_manager(self):
        from global_sound import sound_manager
        if not sound_manager.enabled or not pygame.mixer.get_init():
            pytest.skip('no sound device')
        return sound_manager

    def test_a_category_is_decoded_once_and_its_volume_set_again(self, sound_manager, monkeypatch):
        import global_sound
        monkeypatch.delitem(sound_manager.sound_categories, 'armycomp', raising=False)
        (load,) = [task for label, task in global_sound.get_game_sound_tasks()
                   if label == 'Loading army composition sounds']
        made = []
        real_sound = pygame.mixer.Sound
        monkeypatch.setattr(pygame.mixer, 'Sound', lambda *a, **k: made.append(1) or real_sound(*a, **k))
        load()
        first = len(made)
        assert first > 0
        sounds = list(sound_manager.sound_categories['armycomp'])
        monkeypatch.setattr(sound_manager, 'volume', 0.2)
        load()                                     # the next game
        assert len(made) == first
        assert sound_manager.sound_categories['armycomp'] == sounds
        assert all(abs(s.get_volume() - 0.2) < 0.01 for s in sounds)

    def test_transmissions_are_decoded_once(self, sound_manager, monkeypatch):
        import global_sound
        volumes = []
        loaded = {'T1': SimpleNamespace(set_volume=volumes.append)}
        monkeypatch.setattr(global_sound, '_transmission_sounds', loaded)
        monkeypatch.setattr(pygame.mixer, 'Sound', lambda *a, **k: pytest.fail('decoded again'))
        assert global_sound.load_transmission_sounds() == 1
        assert volumes == [sound_manager.volume]


class TestThePlayersWindow:

    def test_it_keeps_its_fonts_and_backdrop(self, custom_game, monkeypatch):
        from players_window import PlayersWindow
        window = PlayersWindow(custom_game.game)
        screen = pygame.display.get_surface()
        window.draw(screen)
        backdrop = window._dim
        made = []
        real_font = pygame.font.Font
        monkeypatch.setattr(pygame.font, 'Font', lambda *a, **k: made.append(a) or real_font(*a, **k))
        window.draw(screen)
        assert made == []
        assert window._dim is backdrop and backdrop.get_size() == screen.get_size()
        assert window._font(9) is window._font(10)          # sizes below 10 are 10
