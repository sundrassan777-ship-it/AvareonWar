# -*- coding: utf-8 -*-
# simultaneous/__init__.py
# Simultaneous Turns Mode Module

"""
Simultaneous Turns Mode
=======================

This module implements simultaneous turn gameplay where all players plan
their moves at the same time, then all orders execute together.

Key Components:
    - SimultaneousGameState: Wrapper around GameState for simultaneous mode
    - SimPhaseManager: Manages planning/execution/resolution phases
    - SimConflictResolver: Handles crossing armies and multi-army battles
    - SimAllianceHandler: Handles allied territory capture and ownership choice
    - SimProtocol: Network message types for simultaneous mode

Design Philosophy:
    This module is designed as a WRAPPER around the existing GameState class
    to minimize changes to the core sequential turn logic. The simultaneous
    mode is isolated in this module to prevent regressions in sequential mode.
"""

from .sim_state import SimultaneousGameState
from .sim_phase_manager import SimPhaseManager
from .sim_conflict_resolver import SimConflictResolver
from .sim_alliance_handler import SimAllianceHandler
from .sim_ai import SimultaneousAI
from .sim_debug import (
    sim_log, SimDebugLevel, set_debug_level, set_multiplayer_context,
    enable_verbose, enable_sync_only, enable_minimal, disable_debug
)

__all__ = [
    'SimultaneousGameState',
    'SimPhaseManager',
    'SimConflictResolver',
    'SimAllianceHandler',
    'SimultaneousAI',
    # Debug utilities
    'sim_log',
    'SimDebugLevel',
    'set_debug_level',
    'set_multiplayer_context',
    'enable_verbose',
    'enable_sync_only',
    'enable_minimal',
    'disable_debug'
]
