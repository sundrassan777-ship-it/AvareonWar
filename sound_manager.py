# -*- coding: utf-8 -*-
# sound_manager.py
# Sound effects management system

"""
Sound Manager Module

Handles loading and playing sound effects for game events.
Provides simple interface for playing random sounds from a category.

Usage:
    sound_mgr = SoundManager()
    sound_mgr.play_random('armycomp')  # Plays random army composition sound
"""

import pygame
import random
import os

from utils.logger import get_logger

logger = get_logger(__name__)


class SoundManager:
    """
    Manages game sound effects with support for random sound selection.

    Attributes:
        enabled (bool): Whether sound is enabled globally
        volume (float): Master volume (0.0 to 1.0)
        sound_categories (dict): Cached sounds organized by category
    """

    def __init__(self, enabled=True, volume=0.5):
        """
        Initialize the sound manager.

        Args:
            enabled (bool): Whether to enable sound playback
            volume (float): Master volume level (0.0 to 1.0)
        """
        self.enabled = enabled
        self.volume = volume
        self.sound_categories = {}
        self.currently_playing = {}  # Track currently playing sounds per category
        self.last_played_index = {}  # Track last played sound index per category to prevent repeats
        self.sound_queue = []  # Queue for sequential sound playback [(category, index), ...]

        # Initialize pygame mixer if not already initialized
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except pygame.error as e:
                logger.warning(f"Could not initialize sound system: {e}")
                self.enabled = False

    def load_sounds_from_folder(self, category, folder_path):
        """
        Load all sound files from a folder into a category.

        Args:
            category (str): Category name for these sounds (e.g., 'armycomp')
            folder_path (str): Path to folder containing sound files

        Returns:
            int: Number of sounds successfully loaded
        """
        if not self.enabled:
            return 0

        sounds = []

        if not os.path.exists(folder_path):
            logger.warning(f"Sound folder not found: {folder_path}")
            return 0

        # Load all .mp3, .wav, and .ogg files
        try:
            for filename in os.listdir(folder_path):
                if filename.lower().endswith(('.mp3', '.wav', '.ogg')):
                    file_path = os.path.join(folder_path, filename)
                    try:
                        sound = pygame.mixer.Sound(file_path)
                        sound.set_volume(self.volume)
                        sounds.append(sound)
                    except pygame.error as e:
                        logger.warning(f"Could not load sound {filename}: {e}")

            self.sound_categories[category] = sounds
            return len(sounds)

        except Exception as e:
            logger.error(f"Error loading sounds from {folder_path}: {e}")
            return 0

    def play_random(self, category, allow_overlap=False, prevent_repeat=True):
        """
        Play a random sound from the specified category.

        Args:
            category (str): Category name (e.g., 'armycomp')
            allow_overlap (bool): If False, won't play if a sound from this category is already playing
            prevent_repeat (bool): If True, won't play the same sound that was played last time

        Returns:
            bool: True if sound played successfully, False otherwise
        """
        if not self.enabled:
            return False

        if category not in self.sound_categories:
            return False

        sounds = self.sound_categories[category]
        if not sounds:
            return False

        # Check if a sound from this category is already playing (unless overlap allowed)
        if not allow_overlap and category in self.currently_playing:
            # Check if the channel is still actually playing
            channel = self.currently_playing[category]
            if channel and channel.get_busy():
                return False  # Sound still playing, don't overlap

        try:
            # Select random sound, avoiding last played if requested and if there are multiple sounds
            if prevent_repeat and len(sounds) > 1 and category in self.last_played_index:
                # Get list of all indices except the last played one
                last_index = self.last_played_index[category]
                available_indices = [i for i in range(len(sounds)) if i != last_index]
                selected_index = random.choice(available_indices)
            else:
                # First time playing or repeat allowed - pick any sound
                selected_index = random.randint(0, len(sounds) - 1)

            sound = sounds[selected_index]
            channel = sound.play()

            # Store the channel to track if sound is still playing
            if channel:
                self.currently_playing[category] = channel
                # Store the index to prevent repeat next time
                self.last_played_index[category] = selected_index

            return True
        except pygame.error as e:
            logger.error(f"Error playing sound: {e}")
            return False

    def play_specific(self, category, index, allow_overlap=False):
        """
        Play a specific sound by index from a category.

        Args:
            category (str): Category name
            index (int): Sound index (0-based)
            allow_overlap (bool): If False, won't play if a sound from this category is already playing

        Returns:
            bool: True if sound played successfully, False otherwise
        """
        if not self.enabled:
            return False

        if category not in self.sound_categories:
            return False

        sounds = self.sound_categories[category]
        if index < 0 or index >= len(sounds):
            return False

        # Check if a sound from this category is already playing (unless overlap allowed)
        if not allow_overlap and category in self.currently_playing:
            # Check if the channel is still actually playing
            channel = self.currently_playing[category]
            if channel and channel.get_busy():
                return False  # Sound still playing, don't overlap

        try:
            channel = sounds[index].play()
            # Store the channel to track if sound is still playing
            if channel:
                self.currently_playing[category] = channel
                # Store the index to track for preventing repeats
                self.last_played_index[category] = index
            return True
        except pygame.error as e:
            logger.error(f"Error playing sound: {e}")
            return False

    def set_volume(self, volume):
        """
        Set master volume for all sounds.

        Args:
            volume (float): Volume level (0.0 to 1.0)
        """
        self.volume = max(0.0, min(1.0, volume))

        # Update volume for all loaded sounds
        for sounds in self.sound_categories.values():
            for sound in sounds:
                sound.set_volume(self.volume)

    def set_category_volume(self, category, volume_multiplier):
        """
        Set volume for a specific sound category relative to master volume.

        Args:
            category (str): Category name (e.g., 'general')
            volume_multiplier (float): Volume multiplier (0.0 to 2.0, where 1.0 = master volume)
        """
        if category not in self.sound_categories:
            return

        # Clamp multiplier to reasonable range
        multiplier = max(0.0, min(2.0, volume_multiplier))
        target_volume = self.volume * multiplier

        # Update volume for all sounds in this category
        for sound in self.sound_categories[category]:
            sound.set_volume(target_volume)

    def set_enabled(self, enabled):
        """
        Enable or disable sound playback.

        Args:
            enabled (bool): Whether to enable sound
        """
        self.enabled = enabled

    def play_ui_click(self):
        """
        Play the default UI click sound from 'general' category.
        This is a convenience method for button clicks.
        Mouse clicks are short and can overlap with other sounds.

        Returns:
            bool: True if sound played successfully, False otherwise
        """
        # Play DefaultMouseClick.mp3 (alphabetically: BattleSound, CastleCompleted, DefaultMouseClick, ResearchCompleted)
        # Index 2 in the general category
        # Allow overlap since mouse clicks are short
        return self.play_specific('general', 2, allow_overlap=True)

    def queue_sound(self, category, index):
        """
        Add a sound to the queue for sequential playback.
        Queued sounds play one after another without overlap.

        Args:
            category (str): Category name
            index (int): Sound index (0-based)
        """
        self.sound_queue.append((category, index))

    def process_sound_queue(self):
        """
        Process the sound queue - play next sound if no sound is currently playing.
        Call this method regularly (e.g., in game loop) to process queued sounds.

        Returns:
            bool: True if a sound was played, False otherwise
        """
        if not self.enabled:
            return False

        # Check if any sound is currently playing
        for category, channel in list(self.currently_playing.items()):
            if channel and channel.get_busy():
                return False  # Still playing, don't start next sound

        # No sounds playing - check queue
        if self.sound_queue:
            category, index = self.sound_queue.pop(0)  # Get first queued sound
            # Play with overlap allowed since we checked nothing is playing
            self.play_specific(category, index, allow_overlap=True)
            return True

        return False

    def clear_sound_queue(self):
        """Clear all queued sounds."""
        self.sound_queue.clear()
