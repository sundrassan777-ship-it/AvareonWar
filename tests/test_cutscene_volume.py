# -*- coding: utf-8 -*-
"""
Tests: cutscenes honour the game's master volume.

Cutscene voice and music clips used to play at their authored per-slide volumes
whatever the master volume was, so muting the game (master 0%) still played the
campaign intro/outro audio. CutscenePlayer now multiplies both by `master_volume`;
the game passes music_manager.master_volume, the Cutscene Tool / MP4 export keep 1.0.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLIP = 'assets/sounds/general/BattleSound.mp3'


@pytest.fixture(scope="module")
def screen():
    import pygame
    pygame.init()
    if pygame.mixer.get_init() is None:
        try:
            pygame.mixer.init()
        except pygame.error:
            pytest.skip("no audio device for pygame.mixer")
    surface = pygame.display.set_mode((640, 360))
    yield surface
    pygame.quit()


def _player(screen, monkeypatch, master_volume=None):
    """A CutscenePlayer with one slide carrying a voice and a music clip."""
    from cutscene_player import CutscenePlayer

    def fake_load(self, cutscene_id):
        self.cutscene_data = {'slides': []}
        self.slides = [{'audio': CLIP, 'audio_volume': 1.0, 'music': CLIP, 'music_volume': 0.4,
                        'duration': 2.0}]

    monkeypatch.setattr(CutscenePlayer, '_load_cutscene_data', fake_load)
    if master_volume is None:
        return CutscenePlayer(screen, 'test_cutscene')
    return CutscenePlayer(screen, 'test_cutscene', master_volume=master_volume)


def test_muted_master_silences_voice_and_music(screen, monkeypatch):
    player = _player(screen, monkeypatch, master_volume=0.0)
    assert player._voices[0].get_volume() == 0.0
    assert player._music[0].get_volume() == 0.0


def test_master_volume_scales_authored_levels(screen, monkeypatch):
    player = _player(screen, monkeypatch, master_volume=0.5)
    assert player._voices[0].get_volume() == pytest.approx(0.5, abs=0.01)
    assert player._music[0].get_volume() == pytest.approx(0.2, abs=0.01)


def test_default_keeps_authored_levels(screen, monkeypatch):
    """The Cutscene Tool / exporter construct it without a master volume."""
    player = _player(screen, monkeypatch)
    assert player._voices[0].get_volume() == pytest.approx(1.0, abs=0.01)
    assert player._music[0].get_volume() == pytest.approx(0.4, abs=0.01)


def test_game_passes_the_live_master_volume():
    """Every in-game CutscenePlayer is built with master_volume=music_manager.master_volume."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py'),
                  encoding='utf-8').read()
    calls = source.count('CutscenePlayer(screen,')
    assert calls >= 3
    assert source.count('master_volume=music_manager.master_volume') == calls
