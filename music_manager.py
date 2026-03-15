"""
Music Manager - Background music playback system.

Three categories:
- Menu Music: plays across all menus, uninterrupted between screens
- Game Music: plays during gameplay
- Recap Music: randomly picks from RECAP_TRACKS and loops during recap screen

Uses pygame.mixer.music for streaming playback (one track at a time).
"""

import os
import random
from collections import deque
import pygame


# Music asset directory
MUSIC_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'music')

# Special tracks
RECAP_TRACKS = [
    'Northern Honour - Recap Screen.mp3',
    'Northern Warrior Cmaj - 12.3..mp3',
]
INTRO_TRACK = 'War in the North 1 - Intro Main Menu.mp3'

# No repeat within last N songs
REPEAT_WINDOW = 2

# Custom event for music track ending
MUSIC_END_EVENT = pygame.USEREVENT + 10


class MusicManager:
    """Manages background music playback with three categories: menu, game, recap."""

    def __init__(self):
        self.current_category = None  # 'menu', 'game', 'recap', or None
        self.current_track = None  # filename of currently playing track
        self.music_volume = 0.5
        self.master_volume = 0.8

        # Track repeat prevention — last N tracks played
        self.recent_tracks = deque(maxlen=REPEAT_WINDOW)

        # Discover all music files
        self.all_tracks = []
        self.general_tracks = []  # All except recap track
        if os.path.isdir(MUSIC_DIR):
            for f in sorted(os.listdir(MUSIC_DIR)):
                if f.lower().endswith(('.mp3', '.wav', '.ogg')):
                    self.all_tracks.append(f)
                    # Exclude recap-only tracks from menu/game rotation
                    if f not in RECAP_TRACKS:
                        self.general_tracks.append(f)

        # Register end-of-track event
        try:
            pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
        except pygame.error:
            pass

    def _effective_volume(self):
        """Calculate effective music volume = music_volume * master_volume."""
        return self.music_volume * self.master_volume

    def _apply_volume(self):
        """Apply current volume to pygame.mixer.music."""
        try:
            pygame.mixer.music.set_volume(self._effective_volume())
        except pygame.error:
            pass

    def _pick_next_track(self, first_track=None):
        """Pick next track, avoiding recent_tracks. If first_track given, use it."""
        if first_track and first_track in self.general_tracks:
            return first_track

        if not self.general_tracks:
            return None

        # Filter out recently played tracks
        candidates = [t for t in self.general_tracks if t not in self.recent_tracks]
        # Fallback if all tracks are in recent (shouldn't happen with enough tracks)
        if not candidates:
            candidates = list(self.general_tracks)

        return random.choice(candidates)

    def _play_track(self, filename, loop=False):
        """Load and play a music track."""
        if not filename:
            return

        filepath = os.path.join(MUSIC_DIR, filename)
        if not os.path.isfile(filepath):
            return

        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play(-1 if loop else 0)
            self._apply_volume()
            self.current_track = filename
            # Add to recent tracks (not for looping recap)
            if not loop:
                self.recent_tracks.append(filename)
        except pygame.error:
            pass

    def start_menu_music(self):
        """Start menu music category. First track is always the intro song."""
        self.current_category = 'menu'
        self.recent_tracks.clear()
        track = self._pick_next_track(first_track=INTRO_TRACK)
        self._play_track(track)

    def start_game_music(self):
        """Start game music category. Random first track, but never the intro menu song."""
        self.current_category = 'game'
        self.recent_tracks.clear()
        # Exclude the intro track from being the first game song
        candidates = [t for t in self.general_tracks if t != INTRO_TRACK]
        if not candidates:
            candidates = list(self.general_tracks)
        track = random.choice(candidates)
        self._play_track(track)

    def start_recap_music(self):
        """Start recap music — randomly picks a recap track and loops it."""
        self.current_category = 'recap'
        track = random.choice(RECAP_TRACKS) if RECAP_TRACKS else None
        self._play_track(track, loop=True)

    def stop(self):
        """Stop music playback and unload."""
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except pygame.error:
            pass
        self.current_category = None
        self.current_track = None
        # Clear any stale MUSIC_END events from the queue — stop() triggers one,
        # and if start_*_music() is called right after, the stale event would
        # cause handle_music_end_event() to skip to a random track immediately.
        pygame.event.clear(MUSIC_END_EVENT)

    def handle_music_end_event(self):
        """Called when MUSIC_END_EVENT fires. Advances to next track for menu/game."""
        if self.current_category in ('menu', 'game'):
            track = self._pick_next_track()
            self._play_track(track)
        # Recap loops via play(-1), so no action needed

    def set_music_volume(self, vol):
        """Set music volume (0.0-1.0). Applied immediately."""
        self.music_volume = max(0.0, min(1.0, vol))
        self._apply_volume()

    def set_master_volume(self, vol):
        """Set master volume (0.0-1.0). Applied immediately to music."""
        self.master_volume = max(0.0, min(1.0, vol))
        self._apply_volume()

    def is_playing(self):
        """Check if music is currently playing."""
        try:
            return pygame.mixer.music.get_busy()
        except pygame.error:
            return False


# Global singleton
music_manager = MusicManager()
