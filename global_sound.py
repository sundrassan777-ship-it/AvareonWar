# -*- coding: utf-8 -*-
# global_sound.py
# Global sound manager instance

"""
Global Sound Manager
====================

Provides a single global sound manager instance that can be imported
by all modules (menus, setup screens, main game) for consistent sound playback.

Usage:
    from global_sound import sound_manager
    sound_manager.play_ui_click()
"""

import os
import re
import pygame

from sound_manager import SoundManager
from utils.logger import get_logger

logger = get_logger(__name__)

# Global sound manager instance
# Initialize with sound enabled and default volume
sound_manager = SoundManager(enabled=True, volume=0.5)

# Transmission voice line state — keyed by filename stem (e.g. "T1", "M2T1") → pygame.mixer.Sound
_transmission_sounds = {}
_transmission_channel = None  # Currently playing transmission voice channel

def initialize_sounds():
    """
    Load all sound files into the global sound manager.
    Call this once during application startup.
    """
    num_general = sound_manager.load_sounds_from_folder('general', 'assets/sounds/general')
    num_armycomp = sound_manager.load_sounds_from_folder('armycomp', 'assets/sounds/armycomp')
    num_seledra = sound_manager.load_sounds_from_folder('seledra', 'assets/sounds/heroes/seledra')
    num_nextroy = sound_manager.load_sounds_from_folder('nextroy', 'assets/sounds/heroes/nextroy')
    num_narn = sound_manager.load_sounds_from_folder('narn', 'assets/sounds/heroes/narn')
    num_asford = sound_manager.load_sounds_from_folder('asford', 'assets/sounds/heroes/asford')
    num_hevilneu = sound_manager.load_sounds_from_folder('hevilneu', 'assets/sounds/heroes/hevilneu')
    num_nithieln = sound_manager.load_sounds_from_folder('nithieln', 'assets/sounds/heroes/nithieln')
    num_brennhen = sound_manager.load_sounds_from_folder('brennhen', 'assets/sounds/heroes/brennhen')
    num_silvyr = sound_manager.load_sounds_from_folder('silvyr', 'assets/sounds/heroes/silvyr')
    # Structure on-click sounds (Barracks, Construction, Farm, Keep, Mine, Square)
    num_structures = sound_manager.load_sounds_from_folder('structures', 'assets/sounds/structures')

    # Set volume for specific sounds in general category
    # We need to set individual volumes because different sounds need different levels
    sounds = sound_manager.sound_categories['general']
    if len(sounds) >= 3:
        sounds[0].set_volume(sound_manager.volume * 1.5)  # CastleCompleted - moderate volume
        sounds[1].set_volume(sound_manager.volume * 2.5)  # DefaultMouseClick - loud
        sounds[2].set_volume(sound_manager.volume * 2.0)  # ResearchCompleted - very loud

    # Set volume for hero sounds (individual multipliers for easy adjustment)
    # Seledra - default volume
    seledra_sounds = sound_manager.sound_categories.get('seledra', [])
    for sound in seledra_sounds:
        sound.set_volume(sound_manager.volume * 1.0)

    # Nextroy - quiet speaker, needs boost
    nextroy_sounds = sound_manager.sound_categories.get('nextroy', [])
    for sound in nextroy_sounds:
        sound.set_volume(sound_manager.volume * 3.5)

    # Narn - default volume
    narn_sounds = sound_manager.sound_categories.get('narn', [])
    for sound in narn_sounds:
        sound.set_volume(sound_manager.volume * 1.0)

    # Asford - default volume
    asford_sounds = sound_manager.sound_categories.get('asford', [])
    for sound in asford_sounds:
        sound.set_volume(sound_manager.volume * 1.0)

    # Hevilneu - default volume
    hevilneu_sounds = sound_manager.sound_categories.get('hevilneu', [])
    for sound in hevilneu_sounds:
        sound.set_volume(sound_manager.volume * 1.0)

    # Nithieln - quiet speaker, moderate boost
    nithieln_sounds = sound_manager.sound_categories.get('nithieln', [])
    for sound in nithieln_sounds:
        sound.set_volume(sound_manager.volume * 1.3)

    # Brennhen - default volume
    brennhen_sounds = sound_manager.sound_categories.get('brennhen', [])
    for sound in brennhen_sounds:
        sound.set_volume(sound_manager.volume * 1.0)

    # Silvyr - default volume
    silvyr_sounds = sound_manager.sound_categories.get('silvyr', [])
    for sound in silvyr_sounds:
        sound.set_volume(sound_manager.volume * 1.0)

    # Load campaign transmission voice lines (T1.mp3 - T27.mp3 etc.)
    num_transmissions = load_transmission_sounds()

    logger.info(f"Loaded {num_general} general sounds")
    logger.info(f"Loaded {num_armycomp} army composition sounds")
    logger.info(f"Loaded {num_seledra} Seledra sounds")
    logger.info(f"Loaded {num_nextroy} Nextroy sounds")
    logger.info(f"Loaded {num_narn} Narn sounds")
    logger.info(f"Loaded {num_asford} Asford sounds")
    logger.info(f"Loaded {num_hevilneu} Hevilneu sounds")
    logger.info(f"Loaded {num_nithieln} Nithieln sounds")
    logger.info(f"Loaded {num_brennhen} Brennhen sounds")
    logger.info(f"Loaded {num_silvyr} Silvyr sounds")
    logger.info(f"Loaded {num_transmissions} transmission voice lines")
    logger.info(f"Loaded {num_structures} structure sounds")

    return sound_manager

# Alphabetical index mapping for structure sounds in assets/sounds/structures/
_STRUCTURE_SOUND_INDEX = {
    'Barracks': 0,      # Barracks Sound.mp3
    'Construction': 1,  # Construction Sound.mp3 (empty plots & under-construction)
    'Farm': 2,          # Farm Sound.mp3
    'Keep': 3,          # Keep Sound.mp3
    'Mine': 4,          # Mine Sound.mp3
    'Square': 5,        # Square Sound.mp3
}

def play_structure_sound(building_type):
    """Play the on-click sound for a structure or plot.
    Pass a building name (e.g. 'Farm') for completed buildings,
    or 'Construction' for empty plots and under-construction buildings."""
    index = _STRUCTURE_SOUND_INDEX.get(building_type)
    if index is not None:
        sound_manager.play_specific('structures', index, allow_overlap=True)

def play_hero_recruit_sound(hero_name, use_queue=False):
    """
    Play the recruitment sound for a specific hero.

    Args:
        hero_name (str): Name of the hero (e.g., 'Seledra Rennervail', 'Halon Nextroy', 'Aidam Narn', 'Vearen Asford', 'Neil Hévilneu', 'Serthus Diarcess', 'Evain Nithieln', 'Darius Brennhen', 'Erec Silvyr')
        use_queue (bool): If True, queue the sound instead of playing immediately

    Returns:
        bool: True if sound played/queued successfully
    """
    if hero_name == 'Seledra Rennervail':
        # Play SeledraRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('seledra', 0)
            return True
        else:
            return sound_manager.play_specific('seledra', 0)
    elif hero_name == 'Halon Nextroy':
        # Play NextroyRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('nextroy', 0)
            return True
        else:
            return sound_manager.play_specific('nextroy', 0)
    elif hero_name == 'Aidam Narn':
        # Play NarnRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('narn', 0)
            return True
        else:
            return sound_manager.play_specific('narn', 0)
    elif hero_name == 'Vearen Asford':
        # Play AsfordRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('asford', 0)
            return True
        else:
            return sound_manager.play_specific('asford', 0)
    elif hero_name == 'Neil Hévilneu':
        # Play HevilneuRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('hevilneu', 0)
            return True
        else:
            return sound_manager.play_specific('hevilneu', 0)
    elif hero_name == 'Serthus Diarcess':
        # Campaign-only hero - uses Hevilneu sounds (same voicelines)
        if use_queue:
            sound_manager.queue_sound('hevilneu', 0)
            return True
        else:
            return sound_manager.play_specific('hevilneu', 0)
    elif hero_name == 'Evain Nithieln':
        # Play NithielnRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('nithieln', 0)
            return True
        else:
            return sound_manager.play_specific('nithieln', 0)
    elif hero_name == 'Darius Brennhen':
        # Play BrennhenRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('brennhen', 0)
            return True
        else:
            return sound_manager.play_specific('brennhen', 0)
    elif hero_name == 'Regnus Aevencourne':
        # Campaign-only hero — uses Narn's voicelines (more fitting tone)
        if use_queue:
            sound_manager.queue_sound('narn', 0)
            return True
        else:
            return sound_manager.play_specific('narn', 0)
    elif hero_name == 'Erec Silvyr':
        # Play SilvyrRecruit.mp3 (first file alphabetically, index 0)
        if use_queue:
            sound_manager.queue_sound('silvyr', 0)
            return True
        else:
            return sound_manager.play_specific('silvyr', 0)
    return False

def play_research_complete_sound(use_queue=False):
    """
    Play the research completion sound.

    Args:
        use_queue (bool): If True, queue the sound instead of playing immediately

    Returns:
        bool: True if sound played/queued successfully
    """
    # ResearchCompleted.mp3 (alphabetically: CastleCompleted, DefaultMouseClick, ResearchCompleted)
    # Index 2 in the general category
    if use_queue:
        sound_manager.queue_sound('general', 2)
        return True
    else:
        return sound_manager.play_specific('general', 2)

def play_castle_complete_sound(use_queue=False):
    """
    Play the castle completion sound.

    Args:
        use_queue (bool): If True, queue the sound instead of playing immediately

    Returns:
        bool: True if sound played/queued successfully
    """
    # CastleCompleted.mp3 (alphabetically first in 'general')
    # Index 0 in the general category
    if use_queue:
        sound_manager.queue_sound('general', 0)
        return True
    else:
        return sound_manager.play_specific('general', 0)

def play_hero_select_sound(hero_name):
    """
    Play a random selection voice line for a specific hero.
    Automatically prevents the same voice line from playing twice in a row.

    Args:
        hero_name (str): Name of the hero (e.g., 'Seledra Rennervail', 'Halon Nextroy', 'Aidam Narn', 'Vearen Asford', 'Neil Hévilneu', 'Serthus Diarcess', 'Evain Nithieln', 'Darius Brennhen', 'Erec Silvyr')

    Returns:
        bool: True if sound played successfully
    """
    if hero_name == 'Seledra Rennervail':
        # Play random SeledraSpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Seledra)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Seledra sound before
        if 'seledra' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['seledra']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('seledra', speech_index)
    elif hero_name == 'Halon Nextroy':
        # Play random NextroySpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Nextroy)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Nextroy sound before
        if 'nextroy' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['nextroy']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('nextroy', speech_index)
    elif hero_name == 'Aidam Narn':
        # Play random NarnSpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Narn)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Narn sound before
        if 'narn' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['narn']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('narn', speech_index)
    elif hero_name == 'Vearen Asford':
        # Play random AsfordSpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Asford)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played an Asford sound before
        if 'asford' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['asford']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('asford', speech_index)
    elif hero_name == 'Neil Hévilneu' or hero_name == 'Serthus Diarcess':
        # Play random HevilneuSpeech1-5 (indices 1-5)
        # Serthus Diarcess (campaign-only hero) uses same voicelines as Hévilneu
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Hevilneu)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Hevilneu sound before
        if 'hevilneu' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['hevilneu']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('hevilneu', speech_index)
    elif hero_name == 'Evain Nithieln':
        # Play random NithielnSpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Nithieln)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Nithieln sound before
        if 'nithieln' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['nithieln']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('nithieln', speech_index)
    elif hero_name == 'Darius Brennhen':
        # Play random BrennhenSpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Brennhen)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Brennhen sound before
        if 'brennhen' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['brennhen']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('brennhen', speech_index)
    elif hero_name == 'Regnus Aevencourne':
        # Campaign-only hero — uses Narn's voicelines (more fitting tone)
        import random
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]
        if 'narn' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['narn']
            if last_index in speech_indices:
                speech_indices.remove(last_index)
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('narn', speech_index)
    elif hero_name == 'Erec Silvyr':
        # Play random SilvyrSpeech1-5 (indices 1-5)
        # Get the last played index to avoid repeating
        import random

        # Get available speech indices (1-5 for Silvyr)
        speech_indices = list(range(1, 6))  # [1, 2, 3, 4, 5]

        # Check if we played a Silvyr sound before
        if 'silvyr' in sound_manager.last_played_index:
            last_index = sound_manager.last_played_index['silvyr']
            # Only filter if the last sound was a speech line (indices 1-5)
            if last_index in speech_indices:
                speech_indices.remove(last_index)

        # Pick a random speech that's different from last time
        speech_index = random.choice(speech_indices)
        return sound_manager.play_specific('silvyr', speech_index)
    return False


# ========================================================================
# TRANSMISSION VOICE LINES
# ========================================================================

def load_transmission_sounds():
    """
    Load campaign transmission voice lines from assets/sounds/transmissions/.
    Files keyed by filename stem (e.g. "T1", "M2T1", "M3T5").
    Supports all missions: T{n}.mp3 for Mission 1, M{m}T{n}.mp3 for later missions.

    Returns:
        int: Number of sounds successfully loaded.
    """
    global _transmission_sounds

    if not sound_manager.enabled:
        return 0

    folder = 'assets/sounds/transmissions'
    if not os.path.exists(folder):
        logger.warning(f"Transmission sounds folder not found: {folder}")
        return 0

    count = 0
    for filename in os.listdir(folder):
        if not filename.lower().endswith(('.mp3', '.wav', '.ogg')):
            continue
        # Use filename stem as key (e.g. "T1.mp3" → "T1", "M2T1.mp3" → "M2T1")
        key = os.path.splitext(filename)[0]
        file_path = os.path.join(folder, filename)
        try:
            sound = pygame.mixer.Sound(file_path)
            sound.set_volume(sound_manager.volume * 1.0)
            _transmission_sounds[key] = sound
            count += 1
        except pygame.error as e:
            logger.warning(f"Could not load transmission sound {filename}: {e}")

    return count


def play_transmission_sound(key):
    """
    Play a transmission voice line by its key.
    Stops any currently playing transmission voice first (cut-over behavior).

    Args:
        key (str or int): Sound key, e.g. "M2T1" or int (auto-converted: 5 → "T5")

    Returns:
        bool: True if sound played successfully.
    """
    global _transmission_channel

    if not sound_manager.enabled:
        return False

    # Backward compat: Mission 1 passes int → convert to "T{n}" string key
    if isinstance(key, int):
        key = f"T{key}"

    # Always stop any currently playing transmission voice before starting new one
    stop_transmission_sound()

    if key not in _transmission_sounds:
        logger.warning(f"Transmission sound {key} not loaded")
        return False

    try:
        _transmission_channel = _transmission_sounds[key].play()
        return _transmission_channel is not None
    except pygame.error as e:
        logger.error(f"Error playing transmission sound {key}: {e}")
        return False


def stop_transmission_sound():
    """Stop any currently playing transmission voice line."""
    global _transmission_channel
    if _transmission_channel and _transmission_channel.get_busy():
        _transmission_channel.stop()
    _transmission_channel = None


def pause_transmission_sound():
    """Pause the currently playing transmission voice line (resumable)."""
    if _transmission_channel and _transmission_channel.get_busy():
        _transmission_channel.pause()


def unpause_transmission_sound():
    """Resume a paused transmission voice line."""
    if _transmission_channel:
        _transmission_channel.unpause()
