# -*- coding: utf-8 -*-
# input/camera_handler.py
# Camera system for panning, zooming, and coordinate conversion

"""
Camera Handler
==============

This module provides the camera system for War of Avareon:
- Coordinate conversion (screen ↔ world)
- Camera panning (drag, edge scroll, keyboard)
- Camera zooming (mouse wheel with zoom-to-cursor)
- Bounds enforcement

Extracted from main.py during Phase 2 of refactoring.
"""

import math

import pygame
from config.constants import *

# Exponential smoothing rate for mouse-wheel zoom (higher = snappier).
# 16.0 reaches ~99% of the target in roughly 0.29s, which keeps the zoom
# responsive while removing the per-notch jump.
ZOOM_SMOOTHING_RATE = 16.0
# Below this difference the zoom snaps to the target and interpolation stops.
ZOOM_SNAP_EPSILON = 0.0005


class CameraHandler:
    """
    Manages camera position, zoom, and all camera-related input.
    
    The camera system allows players to:
    - Pan the view (drag with middle mouse, edge scrolling, arrow keys)
    - Zoom in/out (mouse wheel with zoom-to-cursor)
    - Navigate large maps smoothly
    
    Coordinate Systems:
        - Screen coordinates: Pixel positions on the window (where things are drawn)
        - World coordinates: Actual map positions (independent of camera/zoom)
        
    Camera State:
        - offset: [x, y] world position of top-left corner of viewport
        - zoom: Magnification level (1.0 = 100%, 2.0 = 200%, etc.)
    """
    
    def __init__(self, map_width, map_height, window_width, window_height, map_height_ui,
                 initial_zoom=1.65, min_zoom=1.65, max_zoom=4.0):
        """
        Initialize camera handler.
        
        Args:
            map_width: Width of the map in pixels (scaled)
            map_height: Height of the map in pixels (scaled)
            window_width: Window width
            window_height: Window height (used for visible area calculation)
            map_height_ui: Height of map area (excluding UI panels)
            initial_zoom: Starting zoom level (default 1.65)
            min_zoom: Minimum zoom level (default 1.65)
            max_zoom: Maximum zoom level (default 4.0)
        """
        # Map dimensions
        self.map_width = map_width
        self.map_height = map_height
        self.window_width = window_width
        self.window_height = window_height
        self.map_height_ui = map_height_ui
        
        # Camera state
        self.offset = [0.0, 0.0]  # [x, y] in world coordinates
        self.zoom = initial_zoom  # Start at initial zoom
        self.drag_start = None  # For middle-mouse drag tracking
        
        # Camera configuration — L6: validate zoom bounds at init
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        assert min_zoom <= max_zoom, f"min_zoom ({min_zoom}) must be <= max_zoom ({max_zoom})"
        assert min_zoom <= initial_zoom <= max_zoom, (
            f"initial_zoom ({initial_zoom}) must be between min_zoom ({min_zoom}) and max_zoom ({max_zoom})")
        self.edge_scroll_margin = 20  # Pixels from edge to trigger scrolling
        
        # Debug state
        self.debug_edge_scroll = None
        self.debug_keyboard_scroll = None

        # FPS OPT: Zoom settle timer — brief period after a mouse-wheel zoom during
        # which the renderer treats the camera as "animating"
        self._zoom_settle_timer = 0.0

        # Smooth zoom: the wheel sets a TARGET and update_zoom() eases toward it,
        # instead of the zoom jumping a full notch per event.
        self.target_zoom = initial_zoom
        self._zoom_interpolating = False
        # Screen point to keep fixed while easing (the cursor at the time of the
        # wheel event), so zoom-to-cursor holds for the whole interpolation rather
        # than only on the frame the event arrived.
        self._zoom_anchor_screen = None
        self._zoom_anchor_panel = 0
    
    def update_map_dimensions(self, map_width, map_height, window_width, window_height, map_height_ui):
        """
        Update map and window dimensions (called during resolution changes).

        Args:
            map_width: New map width
            map_height: New map height
            window_width: New window width
            window_height: New window height
            map_height_ui: New map area height
        """
        self.map_width = map_width
        self.map_height = map_height
        self.window_width = window_width
        self.window_height = window_height
        self.map_height_ui = map_height_ui
        # M1 fix: Clamp camera offset so user doesn't see black area after resolution change
        self.clamp_to_bounds()
    
    def reset_camera(self):
        """Reset camera to default position and zoom."""
        self.offset = [0.0, 0.0]
        self.zoom = 1.65
        self.drag_start = None
        self.cancel_zoom_interpolation()

    def cancel_zoom_interpolation(self):
        """
        Stop any in-flight smooth zoom and adopt the current zoom as the target.

        Call this before driving `zoom` directly (camera animations, resets), so a
        pending wheel-zoom target does not immediately pull the camera back.
        """
        self.target_zoom = self.zoom
        self._zoom_interpolating = False
        self._zoom_anchor_screen = None
    
    # ========================================
    # COORDINATE CONVERSION
    # ========================================
    
    def screen_to_world(self, screen_pos, top_panel_height):
        """
        Convert screen coordinates to world coordinates.
        
        Applies camera offset and zoom to transform screen position
        (where the mouse is) to the corresponding world position
        (actual map coordinates).
        
        Args:
            screen_pos: (x, y) tuple in screen coordinates (pixels on window)
            top_panel_height: Height of top panel (to convert screen Y to map-relative Y)
        
        Returns:
            (x, y) tuple in world coordinates (actual map positions)
        """
        screen_x, screen_y = screen_pos
        
        # Subtract top panel offset from Y coordinate (convert to map-relative)
        map_relative_y = screen_y - top_panel_height
        
        # Undo zoom (divide by zoom), then undo offset (add offset)
        world_x = (screen_x / self.zoom) + self.offset[0]
        world_y = (map_relative_y / self.zoom) + self.offset[1]
        
        return (world_x, world_y)
    
    def world_to_screen(self, world_pos, top_panel_height):
        """
        Convert world coordinates to screen coordinates.
        
        Applies camera offset and zoom to transform world position
        (actual map coordinates) to the corresponding screen position
        (where to draw on window).
        
        Args:
            world_pos: (x, y) tuple in world coordinates (actual map positions)
            top_panel_height: Height of top panel (to convert map-relative Y to screen Y)
        
        Returns:
            (x, y) tuple in screen coordinates (pixels on window)
        """
        world_x, world_y = world_pos
        
        # Apply offset (subtract offset), then apply zoom (multiply by zoom)
        screen_x = (world_x - self.offset[0]) * self.zoom
        screen_y = (world_y - self.offset[1]) * self.zoom + top_panel_height
        
        return (screen_x, screen_y)
    
    @property
    def is_zoom_settling(self):
        """True while a mouse-wheel zoom is still easing (or just finished)."""
        return self._zoom_settle_timer > 0 or self._zoom_interpolating

    def update_zoom_settle(self, delta_time):
        """Tick down the zoom settle timer. Call once per frame from main loop."""
        if self._zoom_settle_timer > 0:
            self._zoom_settle_timer = max(0, self._zoom_settle_timer - delta_time)

    def update_zoom(self, delta_time):
        """
        Ease the camera toward target_zoom. Call once per frame from the main loop.

        Uses frame-rate independent exponential smoothing, so the feel is the same
        at 60 and 165 FPS. The zoom-to-cursor anchor is re-applied on every step:
        the world point under the cursor is sampled before the step and restored
        after it, which keeps that point fixed for the whole interpolation and
        stays correct even if the camera is panned mid-zoom.

        Returns:
            bool: True if the zoom changed this frame.
        """
        if not self._zoom_interpolating:
            return False

        remaining = self.target_zoom - self.zoom
        if abs(remaining) < ZOOM_SNAP_EPSILON or delta_time <= 0:
            self.zoom = self.target_zoom
            self._zoom_interpolating = False
            self._zoom_anchor_screen = None
            self.clamp_to_bounds()
            return True

        anchor = self._zoom_anchor_screen
        panel = self._zoom_anchor_panel
        if anchor is None:
            anchor = (self.window_width / 2.0, self.map_height_ui / 2.0 + panel)

        world_before = self.screen_to_world(anchor, panel)

        # 1 - exp(-rate * dt) is the frame-rate independent form of a lerp
        factor = 1.0 - math.exp(-ZOOM_SMOOTHING_RATE * delta_time)
        self.zoom += remaining * factor
        # Guard against overshoot from a large delta_time spike
        if (remaining > 0 and self.zoom > self.target_zoom) or \
           (remaining < 0 and self.zoom < self.target_zoom):
            self.zoom = self.target_zoom
        self.zoom = max(self.min_zoom, min(self.max_zoom, self.zoom))

        world_after = self.screen_to_world(anchor, panel)
        self.offset[0] += world_before[0] - world_after[0]
        self.offset[1] += world_before[1] - world_after[1]
        self.clamp_to_bounds()
        return True

    def get_ui_scale_factor(self):
        """
        Get UI element scale factor based on current zoom level.

        Makes UI elements (army circles, plots, building icons) scale with zoom
        for better visibility and easier clicking when zoomed in.

        Returns:
            float: Scale multiplier for UI element sizes (1.0 to 1.5)
        """
        # Calculate normalized zoom position (0.0 to 1.0)
        zoom_range = self.max_zoom - self.min_zoom
        zoom_position = (self.zoom - self.min_zoom) / zoom_range

        # Scale from 1.0 (at min zoom) to 1.5 (at max zoom)
        scale_factor = 1.0 + (0.5 * zoom_position)

        return scale_factor
    
    # ========================================
    # BOUNDS ENFORCEMENT
    # ========================================
    
    def clamp_to_bounds(self):
        """
        Clamp camera offset to keep view within map bounds.
        
        Prevents camera from scrolling too far off the edge of the map.
        """
        # Calculate visible area size in world units
        visible_width = self.window_width / self.zoom
        visible_height = self.map_height_ui / self.zoom
        
        # Clamp horizontal offset
        min_x = 0
        max_x = max(0, self.map_width - visible_width)
        self.offset[0] = max(min_x, min(max_x, self.offset[0]))
        
        # Clamp vertical offset
        min_y = 0
        max_y = max(0, self.map_height - visible_height)
        self.offset[1] = max(min_y, min(max_y, self.offset[1]))
    
    # ========================================
    # INPUT HANDLING
    # ========================================
    
    def handle_drag(self, pos, buttons, bottom_ui_y):
        """
        Handle camera dragging with middle mouse button.
        
        Args:
            pos: (x, y) tuple of current mouse position
            buttons: pygame.mouse.get_pressed() result
            bottom_ui_y: Y position where bottom UI starts (to check if in map area)
        """
        # Only allow dragging in map area (not in bottom UI)
        if pos[1] >= bottom_ui_y:
            self.drag_start = None
            return
        
        if buttons[1]:  # Middle mouse button
            if self.drag_start is not None:
                # Calculate drag delta
                dx = pos[0] - self.drag_start[0]
                dy = pos[1] - self.drag_start[1]
                
                # Update camera offset
                # Invert delta: dragging right means view moves left
                # Divide by zoom to keep drag speed consistent
                self.offset[0] -= dx / self.zoom
                self.offset[1] -= dy / self.zoom
                
                # Enforce map bounds
                self.clamp_to_bounds()
            
            # Update drag start for next frame
            self.drag_start = pos
        else:
            # Middle mouse released - end drag
            self.drag_start = None
    
    def handle_edge_scrolling(self, pos, enabled, mode, pan_speed, 
                             top_panel_height, bottom_ui_y):
        """
        Handle edge scrolling when mouse is near map area edges.
        
        Args:
            pos: (x, y) tuple of current mouse position
            enabled: Whether edge scrolling is enabled
            mode: "map_edge" or "window_edge"
            pan_speed: Configurable pan speed (5-20)
            top_panel_height: Height of top panel
            bottom_ui_y: Y position where bottom UI starts
        """
        # Check if edge scrolling is enabled
        if not enabled:
            return
        
        # For map edge mode, only scroll if mouse in map area
        if mode == "map_edge":
            if pos[1] < top_panel_height or pos[1] >= bottom_ui_y:
                return
        
        x, y = pos
        scroll_x = 0
        scroll_y = 0
        
        # Calculate base scroll speed (scales with zoom and configurable speed)
        base_speed = pan_speed * (self.zoom / self.min_zoom)
        
        # Determine edge boundaries based on mode
        if mode == "window_edge":
            left_edge = 0
            right_edge = self.window_width
            top_edge = 0
            bottom_edge = self.window_height
        else:  # map_edge
            left_edge = 0
            right_edge = self.window_width
            top_edge = top_panel_height
            bottom_edge = bottom_ui_y
        
        # Check horizontal edges
        if x < left_edge + self.edge_scroll_margin:
            distance_from_edge = self.edge_scroll_margin - (x - left_edge)
            distance_from_edge = max(0, distance_from_edge)
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_x = -base_speed * speed_multiplier
        elif x > right_edge - self.edge_scroll_margin:
            distance_from_edge = x - (right_edge - self.edge_scroll_margin)
            speed_multiplier = min(1.0, distance_from_edge / self.edge_scroll_margin)
            scroll_x = base_speed * speed_multiplier
        
        # Check vertical edges
        if mode == "window_edge":
            if y < top_edge + self.edge_scroll_margin:
                distance_from_edge = self.edge_scroll_margin - (y - top_edge)
                distance_from_edge = max(0, distance_from_edge)
                speed_multiplier = distance_from_edge / self.edge_scroll_margin
                scroll_y = -base_speed * speed_multiplier
            elif y > bottom_edge - self.edge_scroll_margin:
                distance_from_edge = y - (bottom_edge - self.edge_scroll_margin)
                speed_multiplier = min(1.0, distance_from_edge / self.edge_scroll_margin)
                scroll_y = base_speed * speed_multiplier
        else:  # map_edge
            map_relative_y = y - top_panel_height
            
            if map_relative_y < self.edge_scroll_margin:
                distance_from_edge = self.edge_scroll_margin - map_relative_y
                speed_multiplier = distance_from_edge / self.edge_scroll_margin
                scroll_y = -base_speed * speed_multiplier
            elif map_relative_y > self.map_height_ui - self.edge_scroll_margin and map_relative_y < self.map_height_ui:
                distance_from_edge = map_relative_y - (self.map_height_ui - self.edge_scroll_margin)
                speed_multiplier = distance_from_edge / self.edge_scroll_margin
                scroll_y = base_speed * speed_multiplier
        
        # Apply scrolling
        if scroll_x != 0 or scroll_y != 0:
            self.offset[0] += scroll_x / self.zoom
            self.offset[1] += scroll_y / self.zoom
            
            # Debug state
            self.debug_edge_scroll = f"Edge: ({int(scroll_x)}, {int(scroll_y)})"
            
            # Enforce map bounds
            self.clamp_to_bounds()
        else:
            self.debug_edge_scroll = None
    
    def handle_keyboard(self, keys, pan_speed):
        """
        Handle keyboard camera panning (arrow keys).
        
        Args:
            keys: pygame.key.get_pressed() result
            pan_speed: Configurable pan speed (5-20)
        """
        scroll_x = 0
        scroll_y = 0
        
        # Horizontal movement
        if keys[pygame.K_LEFT]:
            scroll_x = -pan_speed
        if keys[pygame.K_RIGHT]:
            scroll_x = pan_speed
        
        # Vertical movement
        if keys[pygame.K_UP]:
            scroll_y = -pan_speed
        if keys[pygame.K_DOWN]:
            scroll_y = pan_speed
        
        # Apply scrolling
        if scroll_x != 0 or scroll_y != 0:
            self.offset[0] += scroll_x / self.zoom
            self.offset[1] += scroll_y / self.zoom
            
            # Debug state
            self.debug_keyboard_scroll = f"Arrows: ({scroll_x}, {scroll_y})"
            
            # Enforce map bounds
            self.clamp_to_bounds()
        else:
            self.debug_keyboard_scroll = None
    
    def handle_zoom(self, delta, mouse_pos, zoom_speed, top_panel_height):
        """
        Handle camera zoom with mouse wheel (zoom-to-cursor).
        
        Args:
            delta: Mouse wheel delta (positive = zoom in, negative = zoom out)
            mouse_pos: Current mouse position
            zoom_speed: Configurable zoom speed (0.05-0.30)
            top_panel_height: Height of top panel
            
        Returns:
            bool: True if zoom was applied, False if at zoom limits
        """
        # Compound from the TARGET, not the current zoom, so several wheel notches
        # in quick succession accumulate instead of each restarting from wherever
        # the easing happened to be.
        base_zoom = self.target_zoom if self._zoom_interpolating else self.zoom

        if delta > 0:
            zoom_factor = 1.0 + zoom_speed
        else:
            zoom_factor = 1.0 - zoom_speed

        new_target = max(self.min_zoom, min(self.max_zoom, base_zoom * zoom_factor))

        # Already at the limit in this direction — nothing to do
        if abs(new_target - base_zoom) < ZOOM_SNAP_EPSILON:
            return False

        self.target_zoom = new_target
        self._zoom_interpolating = True
        # Anchor zoom-to-cursor at the pointer position for the whole interpolation
        self._zoom_anchor_screen = tuple(mouse_pos)
        self._zoom_anchor_panel = top_panel_height
        # Keep the renderer in "zoom activity" state a moment after easing ends
        self._zoom_settle_timer = 0.2
        return True