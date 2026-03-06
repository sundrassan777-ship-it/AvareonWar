# -*- coding: utf-8 -*-
# settings_manager.py
# Global settings management for the game

"""
Settings Manager
================

Centralized settings management system that:
- Loads settings from config.json at startup
- Provides default settings if config doesn't exist
- Saves settings when changed
- Shares settings across all game windows (main menu, game, etc.)
"""

import json
import os
import sys

from utils.logger import get_logger
logger = get_logger(__name__)


def get_config_path():
    """
    Get the path for config.json.

    When running as a PyInstaller bundle, config.json is stored next to the executable
    (not in the temp extraction folder) so settings persist between runs.
    When running as a script, config.json is in the script's directory.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - save config next to the .exe
        return os.path.join(os.path.dirname(sys.executable), 'config.json')
    else:
        # Running as script - save in script directory
        return 'config.json'


# Fallback resolution used when detected monitor resolution is invalid (0, negative, or too small)
_FALLBACK_RESOLUTION = (1600, 900)
# Minimum reasonable monitor resolution threshold
_MIN_VALID_RESOLUTION = (640, 480)

# Expected types for each setting key, used for type validation on set() and after JSON load.
# 'resolution' and 'default_resolution' are stored as lists in JSON but accepted as list or tuple.
SETTING_TYPES = {
    'resolution': (list, tuple),
    'default_resolution': (list, tuple),
    'fullscreen': (bool,),
    'edge_scrolling_enabled': (bool,),
    'edge_scrolling_mode': (str,),
    'tooltips_enabled': (bool,),
    'tooltip_delay_ms': (int, float),
    'camera_pan_speed': (int, float),
    'camera_zoom_speed': (int, float),
    'show_fps': (bool,),
    # Audio settings
    'master_volume': (int, float),
    'music_volume': (int, float),
    'sfx_volume': (int, float),
    'player_name': (str,),
    'player_icon': (int, str),  # int for hero icons (0-7), str path for reward icons
    # Achievement system persistence
    'achievement_stats': (dict,),
    'earned_achievements': (dict,),
    'selected_title': (str, type(None)),
    # Player Level system persistence
    'player_xp': (int,),
    'campaign_missions_xp_claimed': (list,),
}


class SettingsManager:
    """
    Global settings manager singleton.

    Handles loading, saving, and accessing game settings across
    all windows and menus.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # Use get_config_path() to determine config location (handles PyInstaller bundle)
        self.config_file = get_config_path()

        # Detect native resolution for first-time setup
        self.native_resolution = self._detect_native_resolution()

        # Choose closest supported resolution as default (1280x720, 1600x900, 1920x1080)
        self.default_resolution = self._choose_default_resolution()

        # Default settings (using chosen default resolution)
        self.defaults = {
            # Display settings
            'resolution': list(self.default_resolution),  # Use chosen default resolution
            'default_resolution': list(self.default_resolution),  # Store for "Reset to Defaults"
            'fullscreen': True,  # Default to fullscreen on first run

            # Gameplay settings
            'edge_scrolling_enabled': True,
            'edge_scrolling_mode': 'push',  # 'push' or 'jump'
            'tooltips_enabled': True,
            'tooltip_delay_ms': 500,
            'camera_pan_speed': 10.0,
            'camera_zoom_speed': 1.1,
            'show_fps': False,

            # Audio settings
            'master_volume': 0.8,
            'music_volume': 0.5,
            'sfx_volume': 0.5,

            # Profile settings
            'player_name': 'Human',
            'player_icon': 0,  # Icon index (0 = question mark, 1-7 = heroes, str = reward icon path)

            # Achievement system
            'achievement_stats': {},       # Cumulative stats: {'custom_game_ai_wins': 0, ...}
            'earned_achievements': {},     # Earned achievements: {'achievement_id': 'ISO_timestamp', ...}
            'selected_title': None,        # Currently selected title string or None

            # Player Level system
            'player_xp': 0,                    # Total accumulated player XP
            'campaign_missions_xp_claimed': [], # Mission IDs that granted first-time 100 XP bonus
        }

        # Current settings (loaded from file or defaults)
        self.settings = {}

        # Load settings
        self.load()

    def _detect_native_resolution(self):
        """
        Detect the native monitor resolution.

        Returns:
            tuple: (width, height) of native resolution
        """
        import pygame

        # Initialize pygame display module if not already done
        if not pygame.display.get_init():
            pygame.display.init()

        # Get display info
        display_info = pygame.display.Info()
        detected_resolution = (display_info.current_w, display_info.current_h)

        # L10: Validate detected resolution - fallback to 1600x900 if invalid
        # (handles 0x0 monitors, negative values, or unreasonably small resolutions)
        if (detected_resolution[0] < _MIN_VALID_RESOLUTION[0] or
                detected_resolution[1] < _MIN_VALID_RESOLUTION[1] or
                detected_resolution[0] <= 0 or detected_resolution[1] <= 0):
            logger.warning(f"Invalid detected resolution: {detected_resolution[0]}x{detected_resolution[1]}. "
                          f"Falling back to {_FALLBACK_RESOLUTION[0]}x{_FALLBACK_RESOLUTION[1]}")

            return _FALLBACK_RESOLUTION

        logger.info(f"Detected native resolution: {detected_resolution[0]}x{detected_resolution[1]}")

        return detected_resolution

    def _choose_default_resolution(self):
        """
        Choose the closest supported resolution to native resolution.

        Supported resolutions: 1280x720, 1600x900, 1920x1080

        If native is scaled (e.g. 125% scaling), this ensures we pick
        a standard resolution that the UI is designed for.

        Returns:
            tuple: (width, height) of chosen default resolution
        """
        supported_resolutions = [
            (1280, 720),
            (1600, 900),
            (1920, 1080)
        ]

        # If native is exactly one of our supported resolutions, use it
        if self.native_resolution in supported_resolutions:
            logger.info(f"Native resolution is supported, using as default: {self.native_resolution[0]}x{self.native_resolution[1]}")
            return self.native_resolution

        # Find closest supported resolution by calculating distance
        # (using euclidean distance)
        native_w, native_h = self.native_resolution
        closest_resolution = min(supported_resolutions,
                                key=lambda res: ((res[0] - native_w) ** 2 + (res[1] - native_h) ** 2) ** 0.5)

        logger.info(f"Native resolution not in supported list, choosing closest: {closest_resolution[0]}x{closest_resolution[1]}")
        return closest_resolution

    def load(self):
        """Load settings from config.json or use defaults"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded_settings = json.load(f)
                    # Merge with defaults (in case new settings were added)
                    self.settings = self.defaults.copy()
                    self.settings.update(loaded_settings)

                    # L8: Validate loaded settings - fix corrupted or unknown fields
                    self._validate_and_clean_settings()

                    logger.info(f"Settings loaded from {self.config_file}")
            except Exception as e:
                logger.warning(f"Could not load {self.config_file}: {e}")
                logger.warning("Using default settings")
                self.settings = self.defaults.copy()
        else:
            # First time setup - use defaults based on detected resolution
            logger.info("First-time setup detected")
            logger.info(f"Using native resolution: {self.native_resolution[0]}x{self.native_resolution[1]}")
            logger.info("Defaulting to fullscreen mode")
            self.settings = self.defaults.copy()

            # Save the defaults to config.json for future runs
            logger.info(f"Creating {self.config_file} with default settings")
            self.save()

    def save(self):
        """
        Save current settings to config.json with file locking.

        L9: Uses msvcrt.locking() on Windows to prevent multiple game instances
        from overwriting each other's config. Falls back to unlocked write on
        non-Windows platforms or if locking fails.
        """
        try:
            # A1+A2 fix: write to temp file first, then rename atomically.
            # Previous approach truncated config.json before lock was acquired,
            # risking data loss on lock failure or crash.
            import tempfile
            config_dir = os.path.dirname(os.path.abspath(self.config_file))
            fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(self.settings, f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                # Atomic rename (on Windows, need to remove target first)
                if os.path.exists(self.config_file):
                    os.replace(tmp_path, self.config_file)
                else:
                    os.rename(tmp_path, self.config_file)
            except Exception:
                # Clean up temp file on failure; original config.json is untouched
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

            logger.info(f"Settings saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Could not save settings: {e}")
            return False

    def _validate_and_clean_settings(self):
        """
        L8: Validate all settings after JSON load.

        - Checks each known field has the expected type
        - Removes unknown fields not in defaults
        - Resets corrupted fields to their default value
        - Logs what was corrected
        """
        corrections = []

        # Remove unknown keys (not in defaults)
        unknown_keys = [k for k in self.settings if k not in self.defaults]
        for key in unknown_keys:
            del self.settings[key]
            corrections.append(f"Removed unknown setting '{key}'")

        # Validate types for known keys
        for key, default_value in self.defaults.items():
            if key not in self.settings:
                # Missing key - restore default
                self.settings[key] = default_value
                corrections.append(f"Restored missing setting '{key}' to default: {default_value}")
                continue

            expected_types = SETTING_TYPES.get(key)
            if expected_types is not None:
                if not isinstance(self.settings[key], expected_types):
                    old_value = self.settings[key]
                    self.settings[key] = default_value
                    corrections.append(
                        f"Reset '{key}' from {type(old_value).__name__} ({old_value!r}) "
                        f"to default ({default_value!r}) - expected {'/'.join(t.__name__ for t in expected_types)}"
                    )

        # Log all corrections
        if corrections:
            for msg in corrections:
                logger.warning(f"Settings validation: {msg}")

    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)

    def set(self, key, value):
        """
        Set a setting value (doesn't auto-save).

        L7: Validates type before storing. If the value type does not match
        the expected type for the key, the value is rejected and a warning is logged.
        """
        # L7: Type validation - reject values with wrong type
        expected_types = SETTING_TYPES.get(key)
        if expected_types is not None and not isinstance(value, expected_types):
            type_names = '/'.join(t.__name__ for t in expected_types)
            logger.warning(
                f"[SETTINGS] Rejected set('{key}', {value!r}): expected {type_names}, "
                f"got {type(value).__name__}. Value not stored."
            )
            return

        self.settings[key] = value

    def get_resolution(self):
        """Get resolution as tuple"""
        res = self.settings.get('resolution', self.defaults['resolution'])
        return tuple(res)

    def set_resolution(self, width, height):
        """Set resolution"""
        self.settings['resolution'] = [width, height]

    def get_default_resolution(self):
        """Get default resolution as tuple (for Reset to Defaults button)"""
        res = self.settings.get('default_resolution', self.defaults['default_resolution'])
        return tuple(res)

    def is_fullscreen(self):
        """Get fullscreen setting"""
        return self.settings.get('fullscreen', self.defaults['fullscreen'])

    def set_fullscreen(self, fullscreen):
        """Set fullscreen"""
        self.settings['fullscreen'] = fullscreen

    def get_player_name(self):
        """Get player profile name"""
        return self.settings.get('player_name', self.defaults['player_name'])

    def set_player_name(self, name):
        """Set player profile name"""
        self.settings['player_name'] = name

    def get_player_icon(self):
        """Get player profile icon index"""
        return self.settings.get('player_icon', self.defaults['player_icon'])

    def set_player_icon(self, icon_index):
        """Set player profile icon index"""
        self.settings['player_icon'] = icon_index

    # --- Achievement system accessors ---

    def get_achievement_stats(self):
        """Get cumulative achievement stat counters"""
        return self.settings.get('achievement_stats', {})

    def set_achievement_stats(self, stats):
        """Set cumulative achievement stat counters"""
        self.settings['achievement_stats'] = stats

    def get_earned_achievements(self):
        """Get dict of earned achievement IDs to ISO timestamps"""
        return self.settings.get('earned_achievements', {})

    def set_earned_achievements(self, earned):
        """Set dict of earned achievement IDs to ISO timestamps"""
        self.settings['earned_achievements'] = earned

    def get_selected_title(self):
        """Get currently selected profile title (or None)"""
        return self.settings.get('selected_title', None)

    def set_selected_title(self, title):
        """Set currently selected profile title"""
        self.settings['selected_title'] = title

    # --- Player Level system accessors ---

    def get_player_xp(self):
        """Get total accumulated player XP"""
        return self.settings.get('player_xp', 0)

    def set_player_xp(self, xp):
        """Set total accumulated player XP"""
        self.settings['player_xp'] = xp

    def get_campaign_missions_xp_claimed(self):
        """Get list of campaign mission IDs that granted first-time XP bonus"""
        return self.settings.get('campaign_missions_xp_claimed', [])

    def set_campaign_missions_xp_claimed(self, missions):
        """Set list of campaign mission IDs that granted first-time XP bonus"""
        self.settings['campaign_missions_xp_claimed'] = missions

    def apply_to_game(self, game):
        """
        Apply settings to a Game instance.

        Updates the game's internal settings variables to match
        the global settings.
        """
        # Display settings
        game.current_resolution = self.get_resolution()
        game.is_fullscreen = self.is_fullscreen()

        # Gameplay settings
        game.edge_scrolling_enabled = self.get('edge_scrolling_enabled', True)
        game.edge_scrolling_mode = self.get('edge_scrolling_mode', 'push')
        game.tooltips_enabled = self.get('tooltips_enabled', True)
        game.tooltip_delay_ms = self.get('tooltip_delay_ms', 500)
        game.camera_pan_speed = self.get('camera_pan_speed', 10.0)
        game.camera_zoom_speed = self.get('camera_zoom_speed', 1.1)
        game.show_fps = self.get('show_fps', False)

        # Audio settings
        game.master_volume = self.get('master_volume', 0.8)
        game.music_volume = self.get('music_volume', 0.5)
        game.sfx_volume = self.get('sfx_volume', 0.5)

        # Also update temp settings for options menu
        game.temp_resolution = game.current_resolution
        game.temp_fullscreen = game.is_fullscreen
        game.temp_edge_scrolling_enabled = game.edge_scrolling_enabled
        game.temp_edge_scrolling_mode = game.edge_scrolling_mode
        game.temp_tooltips_enabled = game.tooltips_enabled
        game.temp_tooltip_delay_ms = game.tooltip_delay_ms
        game.temp_camera_pan_speed = game.camera_pan_speed
        game.temp_camera_zoom_speed = game.camera_zoom_speed
        game.temp_show_fps = game.show_fps
        game.temp_master_volume = game.master_volume
        game.temp_music_volume = game.music_volume
        game.temp_sfx_volume = game.sfx_volume

    def update_from_game(self, game):
        """
        Update global settings from a Game instance.

        Call this when settings are changed in the game's options menu.
        """
        # Display settings
        self.set_resolution(game.current_resolution[0], game.current_resolution[1])
        self.set_fullscreen(game.is_fullscreen)

        # Gameplay settings
        self.set('edge_scrolling_enabled', game.edge_scrolling_enabled)
        self.set('edge_scrolling_mode', game.edge_scrolling_mode)
        self.set('tooltips_enabled', game.tooltips_enabled)
        self.set('tooltip_delay_ms', game.tooltip_delay_ms)
        self.set('camera_pan_speed', game.camera_pan_speed)
        self.set('camera_zoom_speed', game.camera_zoom_speed)
        self.set('show_fps', game.show_fps)

        # Audio settings
        self.set('master_volume', game.master_volume)
        self.set('music_volume', game.music_volume)
        self.set('sfx_volume', game.sfx_volume)

        # Save immediately
        self.save()


# Global settings instance
settings = SettingsManager()
