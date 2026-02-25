# -*- coding: utf-8 -*-
# utils/logger.py
# Structured logging module for AvareonWar
#
# Provides configurable file+console output with per-module loggers.
# Usage:
#   from utils.logger import get_logger
#   logger = get_logger(__name__)
#   logger.debug("Detailed info for development")
#   logger.info("Normal operational messages")
#   logger.warning("Something unexpected but recoverable")
#   logger.error("Something failed")

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Log directory — next to the .exe in frozen builds, next to project root otherwise
if getattr(sys, 'frozen', False):
    LOG_DIR = os.path.join(os.path.dirname(sys.executable), 'logs')
else:
    LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')

# Default configuration
DEFAULT_CONSOLE_LEVEL = logging.INFO
DEFAULT_FILE_LEVEL = logging.DEBUG
LOG_FILE = 'avareonwar.log'
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB per log file
BACKUP_COUNT = 3  # Keep 3 rotated log files

# Format strings
CONSOLE_FORMAT = '%(levelname)-8s %(name)-25s %(message)s'
FILE_FORMAT = '%(asctime)s %(levelname)-8s %(name)-25s %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Track whether logging has been initialized
_initialized = False


def setup_logging(console_level=None, file_level=None, enable_file=True):
    """
    Initialize the logging system. Call once at application startup (main.py).

    Args:
        console_level: Logging level for console output (default: INFO)
        file_level: Logging level for file output (default: DEBUG)
        enable_file: Whether to write to a log file (default: True)
    """
    global _initialized
    if _initialized:
        return

    if console_level is None:
        console_level = DEFAULT_CONSOLE_LEVEL
    if file_level is None:
        file_level = DEFAULT_FILE_LEVEL

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, handlers filter

    # Console handler - shows INFO and above by default
    # Force UTF-8 on Windows console to prevent mojibake on arrow chars (→) etc.
    if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError):
            pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler - captures DEBUG and above for diagnostics
    if enable_file:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            log_path = os.path.join(LOG_DIR, LOG_FILE)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=MAX_LOG_SIZE,
                backupCount=BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setLevel(file_level)
            file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
            root_logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            # If we can't create log file, continue with console only
            console_handler.setLevel(logging.DEBUG)
            root_logger.warning(f"Could not create log file: {e}. Logging to console only.")

    # Suppress noisy third-party loggers
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    _initialized = True


def get_logger(name):
    """
    Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        logging.Logger instance
    """
    # Shorten module paths for cleaner output
    # e.g. "rendering.map_renderer" instead of full path
    if name.startswith('__'):
        name = name.replace('__', '')
    return logging.getLogger(name)


def set_level(level):
    """Change the console logging level at runtime (e.g., for debug toggle)."""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
            handler.setLevel(level)
