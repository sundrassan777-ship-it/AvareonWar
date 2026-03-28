# -*- coding: utf-8 -*-
# cutscene_exporter.py
# Export cutscenes to MP4 video files using ffmpeg

"""
Cutscene Exporter
=================

Renders cutscenes frame-by-frame to an offscreen surface and pipes raw frames
to ffmpeg for H.264 encoding. Audio tracks (voiceover + music) are muxed in a
second pass using ffmpeg's filter_complex.

Requires: imageio-ffmpeg (pip install imageio-ffmpeg)
    This package bundles a static ffmpeg binary -- no manual install needed.

Usage (from Cutscene_Tool.py):
    from cutscene_exporter import CutsceneExporter, export_all_cutscenes
    exporter = CutsceneExporter("mission_1_intro")
    exporter.export("output.mp4", progress_callback=my_callback)

    # Export all cutscenes concatenated into one video:
    export_all_cutscenes(["mission_1_intro", ...], "all.mp4", progress_callback=cb)
"""

import pygame
import subprocess
import os
import shutil
import tempfile

from utils.logger import get_logger
logger = get_logger(__name__)


# Export constants
EXPORT_WIDTH = 1920
EXPORT_HEIGHT = 1080
EXPORT_FPS = 60


def _get_ffmpeg_path():
    """
    Locate the ffmpeg binary. Tries imageio-ffmpeg first (bundled binary),
    then falls back to PATH lookup.

    Returns:
        Path string to ffmpeg executable, or None if not found.
    """
    # Try imageio-ffmpeg bundled binary first
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.exists(path):
            return path
    except ImportError:
        pass

    # Fallback: check if ffmpeg is on PATH
    ffmpeg_on_path = shutil.which('ffmpeg')
    if ffmpeg_on_path:
        return ffmpeg_on_path

    return None


class _ExportableCutscenePlayer:
    """
    Lightweight wrapper around CutscenePlayer internals for offscreen rendering.
    Subclasses CutscenePlayer to disable skip hints and provide frame-at-time rendering.

    We use delayed import + subclassing to avoid circular imports and to keep
    cutscene_player.py untouched.
    """

    def __init__(self, surface, cutscene_id):
        """
        Initialize the exportable player with an offscreen surface.

        Args:
            surface: pygame.Surface to render frames onto (offscreen, not the display).
            cutscene_id: String key into cutscene_data.json.
        """
        # Import CutscenePlayer here to avoid top-level circular dependency
        from cutscene_player import CutscenePlayer
        self._player = CutscenePlayer.__new__(CutscenePlayer)

        # Manually initialize the player with our offscreen surface
        # (mirrors CutscenePlayer.__init__ but skips event loop setup)
        p = self._player
        p.screen = surface
        p.screen_width = surface.get_width()
        p.screen_height = surface.get_height()
        p.screen_aspect = p.screen_width / p.screen_height
        p.clock = pygame.time.Clock()

        # Load cutscene data
        p.cutscene_data = None
        p.slides = []
        p._load_cutscene_data(cutscene_id)

        # Asset containers (images only -- audio is handled by the exporter)
        p._images = {}
        p._voices = {}
        p._music = {}
        p._voice_channel = None
        p._music_channel = None
        p._current_music_path = None

        # Playback state
        p._current_slide = 0
        p._slide_elapsed = 0.0
        p._global_elapsed = 0.0
        p._slide_start_times = []
        p._slide_end_times = []
        p._voice_triggered = set()
        p._music_triggered = set()

        # Skip/exit state -- not used during export, but needed by _render_cutscene_frame
        p._skipping = False
        p._skip_fade_elapsed = 0.0
        p._fade_duration = CutscenePlayer.SKIP_FADE_DURATION
        p._done = False

        # Reusable rendering surfaces
        p._render_surface_a = pygame.Surface((p.screen_width, p.screen_height))
        p._render_surface_b = pygame.Surface((p.screen_width, p.screen_height))
        p._fade_overlay = pygame.Surface((p.screen_width, p.screen_height))

        # Fonts
        p._subtitle_font = None
        p._hint_font = None
        p._init_fonts()

        # Pre-load images (but not audio -- exporter handles audio via ffmpeg)
        if p.has_cutscene:
            # Only load images, skip audio loading
            self._preload_images_only()
            p._compute_timeline()

        # Store constants from class for easy access
        self.FADE_IN_DURATION = CutscenePlayer.FADE_IN_DURATION
        self.FADE_OUT_DURATION = CutscenePlayer.FADE_OUT_DURATION

    def _preload_images_only(self):
        """Pre-load only image assets (skip audio -- handled by ffmpeg muxing)."""
        p = self._player
        for i, slide in enumerate(p.slides):
            image_path = slide.get('image', '')
            if image_path and os.path.exists(image_path):
                try:
                    img = pygame.image.load(image_path).convert_alpha()
                    p._images[i] = img
                except pygame.error as e:
                    logger.warning(f"Could not load image {image_path}: {e}")

    @property
    def has_cutscene(self):
        return self._player.has_cutscene

    @property
    def total_duration(self):
        return self._player._total_duration

    @property
    def slides(self):
        return self._player.slides

    @property
    def slide_start_times(self):
        return self._player._slide_start_times

    def render_frame_at_time(self, t, render_subtitles=True):
        """
        Render a single cutscene frame at the given time to the offscreen surface.

        Args:
            t: Time in seconds from cutscene start.
            render_subtitles: If False, subtitles are suppressed.
        """
        p = self._player
        p._global_elapsed = t

        # Fill black background
        p.screen.fill((0, 0, 0))

        if not render_subtitles:
            # Temporarily replace subtitle renderer with no-op
            original_render_subtitle = p._render_subtitle
            p._render_subtitle = lambda *a, **kw: None

        # Render the Ken Burns frame (skip hint is harmless -- it checks
        # _global_elapsed > SKIP_HINT_DURATION which will be true for most frames)
        # But we override it anyway to be safe
        original_render_skip_hint = p._render_skip_hint
        p._render_skip_hint = lambda: None

        p._render_cutscene_frame()

        # Restore original methods
        p._render_skip_hint = original_render_skip_hint
        if not render_subtitles:
            p._render_subtitle = original_render_subtitle

        # Apply fade-in from black at the start
        if t < self.FADE_IN_DURATION:
            fade_in_progress = t / self.FADE_IN_DURATION
            p._fade_overlay.fill((0, 0, 0))
            p._fade_overlay.set_alpha(int(255 * (1.0 - fade_in_progress)))
            p.screen.blit(p._fade_overlay, (0, 0))

        # Apply fade-out to black at the end
        fade_out_start = p._total_duration - self.FADE_OUT_DURATION
        if t > fade_out_start and p._total_duration > 0:
            fade_out_progress = (t - fade_out_start) / self.FADE_OUT_DURATION
            p._fade_overlay.fill((0, 0, 0))
            p._fade_overlay.set_alpha(int(255 * min(1.0, fade_out_progress)))
            p.screen.blit(p._fade_overlay, (0, 0))


class CutsceneExporter:
    """
    Exports a cutscene to MP4 using ffmpeg.

    Two-pass approach:
    1. Render all frames offscreen and pipe raw RGB to ffmpeg -> silent .mp4
    2. Mux audio tracks (voiceover + music per slide with timing offsets) -> final .mp4
    """

    def __init__(self, cutscene_id, include_subtitles=True, include_audio=True):
        """
        Args:
            cutscene_id: String key into cutscene_data.json (e.g. "mission_1_intro").
            include_subtitles: Whether to render subtitle text overlays.
            include_audio: Whether to include voiceover and music audio tracks.
        """
        self.cutscene_id = cutscene_id
        self.include_subtitles = include_subtitles
        self.include_audio = include_audio

        # Locate ffmpeg binary
        self._ffmpeg_path = _get_ffmpeg_path()

        # Create offscreen rendering surface
        self._surface = pygame.Surface((EXPORT_WIDTH, EXPORT_HEIGHT))

        # Initialize the exportable player
        self._player = _ExportableCutscenePlayer(self._surface, cutscene_id)

    @property
    def has_cutscene(self):
        return self._player.has_cutscene

    def export(self, output_path, progress_callback=None):
        """
        Export the cutscene to an MP4 file.

        Args:
            output_path: Destination .mp4 file path.
            progress_callback: Optional callable(progress_float) where 0.0-1.0.
                Returns False to cancel the export.

        Returns:
            True on success, False on failure or cancellation.
        """
        if not self._ffmpeg_path:
            logger.error("ffmpeg not found. Install imageio-ffmpeg: pip install imageio-ffmpeg")
            return False

        if not self.has_cutscene:
            logger.error(f"No cutscene data for '{self.cutscene_id}'")
            return False

        # Determine if we need audio muxing (second pass)
        audio_tracks = self._compute_audio_timeline() if self.include_audio else []
        needs_audio = len(audio_tracks) > 0

        # If audio needed, render silent video to temp file first
        if needs_audio:
            # Create temp file in same directory as output for predictable location
            output_dir = os.path.dirname(os.path.abspath(output_path))
            temp_fd, temp_video_path = tempfile.mkstemp(suffix='.mp4', dir=output_dir)
            os.close(temp_fd)
        else:
            temp_video_path = None

        try:
            # Pass 1: Render frames to video (silent or final)
            video_target = temp_video_path if needs_audio else output_path
            success = self._render_frames_to_video(video_target, progress_callback)
            if not success:
                return False

            # Pass 2: Mux audio if needed
            if needs_audio:
                success = self._mux_audio(temp_video_path, output_path, audio_tracks)
                if not success:
                    # Audio mux failed -- keep the silent video as fallback
                    logger.warning("Audio muxing failed, saving silent video instead")
                    try:
                        shutil.move(temp_video_path, output_path)
                    except OSError:
                        pass
                    return True

            return True

        finally:
            # Clean up temp file
            if temp_video_path and os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except OSError:
                    pass

    def _render_frames_to_video(self, output_path, progress_callback=None):
        """
        Pass 1: Render all frames and pipe raw RGB data to ffmpeg for encoding.

        Returns True on success, False on cancellation or error.
        """
        total_duration = self._player.total_duration
        # Fade-out already occurs within total_duration (last FADE_OUT_DURATION seconds),
        # so no extra time needed -- just render up to total_duration
        total_frames = max(1, int(total_duration * EXPORT_FPS))

        # Build ffmpeg command for raw frame input -> H.264 output
        cmd = [
            self._ffmpeg_path,
            '-y',                       # Overwrite output
            '-f', 'rawvideo',           # Input format: raw RGB frames
            '-pix_fmt', 'rgb24',        # Pixel format: 24-bit RGB
            '-s', f'{EXPORT_WIDTH}x{EXPORT_HEIGHT}',  # Frame size
            '-r', str(EXPORT_FPS),      # Frame rate
            '-i', 'pipe:0',            # Read from stdin
            '-c:v', 'libx264',         # H.264 codec
            '-preset', 'medium',        # Encoding speed/quality tradeoff
            '-crf', '18',              # Quality (lower = better, 18 is visually lossless)
            '-pix_fmt', 'yuv420p',     # Output pixel format (compatibility)
            '-movflags', '+faststart',  # Enable streaming-friendly MP4
            output_path
        ]

        try:
            # Launch ffmpeg subprocess with stdin pipe for frame data
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
        except FileNotFoundError:
            logger.error(f"Could not launch ffmpeg at: {self._ffmpeg_path}")
            return False

        try:
            for frame_idx in range(total_frames):
                t = frame_idx / EXPORT_FPS

                # Render the frame to the offscreen surface
                self._player.render_frame_at_time(t, render_subtitles=self.include_subtitles)

                # Extract raw RGB bytes and pipe to ffmpeg
                frame_bytes = pygame.image.tobytes(self._surface, 'RGB')
                process.stdin.write(frame_bytes)

                # Report progress every 10 frames (avoid excessive callback overhead)
                if progress_callback and frame_idx % 10 == 0:
                    progress = frame_idx / total_frames
                    result = progress_callback(progress)
                    if result is False:
                        # User cancelled -- kill ffmpeg and clean up
                        process.stdin.close()
                        process.kill()
                        process.communicate()  # Drain pipes to avoid zombie
                        # Remove partial output file
                        if os.path.exists(output_path):
                            try:
                                os.remove(output_path)
                            except OSError:
                                pass
                        return False

            # Close stdin to signal end of input, then wait for ffmpeg to finish.
            # Use communicate() instead of stdin.close() + wait() to avoid deadlock
            # when ffmpeg's stderr pipe buffer fills up.
            if progress_callback:
                progress_callback(0.99)  # Show "almost done" while ffmpeg finalizes
            process.stdin.close()
            _, stderr_data = process.communicate()

            if process.returncode != 0:
                stderr_output = stderr_data.decode('utf-8', errors='replace') if stderr_data else ''
                logger.error(f"ffmpeg video encoding failed (code {process.returncode}): {stderr_output[:500]}")
                return False

            # Final progress update
            if progress_callback:
                progress_callback(1.0)

            return True

        except (BrokenPipeError, OSError) as e:
            logger.error(f"Error piping frames to ffmpeg: {e}")
            process.kill()
            process.communicate()  # Drain pipes to avoid zombie process
            return False

    def _compute_audio_timeline(self):
        """
        Build a list of audio tracks with their timing offsets for ffmpeg muxing.

        Returns:
            List of dicts: [{'path': str, 'start_ms': int, 'volume': float}, ...]
        """
        tracks = []
        player = self._player

        for i, slide in enumerate(player.slides):
            start_time = player.slide_start_times[i]

            # Voiceover track
            audio_path = slide.get('audio', '')
            if audio_path and os.path.exists(audio_path):
                voice_delay = slide.get('audio_start_delay', 0.0)
                trigger_time = start_time + voice_delay
                tracks.append({
                    'path': audio_path,
                    'start_ms': int(trigger_time * 1000),
                    'volume': slide.get('audio_volume', 1.0),
                })

            # Music track
            music_path = slide.get('music', '')
            if music_path and os.path.exists(music_path):
                music_delay = slide.get('music_start_delay', 0.0)
                trigger_time = start_time + music_delay
                # Avoid duplicate music tracks (same file at same time)
                is_duplicate = any(
                    t['path'] == music_path and abs(t['start_ms'] - int(trigger_time * 1000)) < 100
                    for t in tracks
                )
                if not is_duplicate:
                    tracks.append({
                        'path': music_path,
                        'start_ms': int(trigger_time * 1000),
                        'volume': slide.get('music_volume', 0.4),
                    })

        return tracks

    def _mux_audio(self, silent_video_path, output_path, audio_tracks):
        """
        Pass 2: Combine silent video with audio tracks using ffmpeg filter_complex.

        Each audio track gets an adelay filter (for timing offset) and a volume filter,
        then all audio tracks are mixed together with amix.

        Returns True on success, False on error.
        """
        if not audio_tracks:
            # No audio to mux -- just rename the silent video
            shutil.move(silent_video_path, output_path)
            return True

        # Build ffmpeg command with multiple audio inputs
        cmd = [self._ffmpeg_path, '-y']

        # Input 0: silent video
        cmd.extend(['-i', silent_video_path])

        # Inputs 1..N: audio files
        for track in audio_tracks:
            cmd.extend(['-i', track['path']])

        # Build filter_complex string
        # Each audio input gets: adelay for timing + volume adjustment
        filter_parts = []
        mix_inputs = []

        for i, track in enumerate(audio_tracks):
            input_idx = i + 1  # Input 0 is the video
            delay_ms = track['start_ms']
            volume = track['volume']

            # Apply delay and volume to each audio track
            # adelay delays both channels by the specified ms
            # Use 'all=1' to delay all channels uniformly
            filter_label = f'a{i}'
            filter_parts.append(
                f'[{input_idx}:a]adelay={delay_ms}|{delay_ms},volume={volume:.2f}[{filter_label}]'
            )
            mix_inputs.append(f'[{filter_label}]')

        # Mix all audio tracks together
        n_tracks = len(audio_tracks)
        mix_input_str = ''.join(mix_inputs)

        if n_tracks == 1:
            # Single track -- no amix needed, just use it directly
            filter_complex = filter_parts[0].replace(f'[a0]', '[aout]')
        else:
            # Multiple tracks -- mix them
            filter_complex = ';'.join(filter_parts)
            filter_complex += f';{mix_input_str}amix=inputs={n_tracks}:normalize=0[aout]'

        cmd.extend(['-filter_complex', filter_complex])

        # Map video from input 0 (copy, no re-encode) and mixed audio
        cmd.extend(['-map', '0:v', '-c:v', 'copy'])

        if n_tracks == 1:
            # Single track output label
            single_filter = filter_parts[0]
            # Re-build with proper output label
            cmd_filter = single_filter.replace('[a0]', '[aout]')
            # Replace the filter_complex we already added
            fc_idx = cmd.index('-filter_complex')
            cmd[fc_idx + 1] = cmd_filter

        cmd.extend(['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k'])
        cmd.extend(['-movflags', '+faststart'])
        cmd.append(output_path)

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                stderr_output = result.stderr.decode('utf-8', errors='replace')
                logger.error(f"ffmpeg audio mux failed (code {result.returncode}): {stderr_output[:500]}")
                return False

            return True

        except FileNotFoundError:
            logger.error(f"Could not launch ffmpeg for audio mux: {self._ffmpeg_path}")
            return False


# ============================================================================
# EXPORT ALL CUTSCENES (concatenated into one video)
# ============================================================================

def export_all_cutscenes(cutscene_ids, output_path, include_subtitles=True,
                         include_audio=True, progress_callback=None):
    """
    Export multiple cutscenes concatenated into a single MP4 file.

    Each cutscene is rendered in order. Between cutscenes, a brief black gap
    (1 second) is inserted for visual separation.

    Args:
        cutscene_ids: List of cutscene ID strings to export (in order).
        output_path: Destination .mp4 file path.
        include_subtitles: Whether to render subtitle text overlays.
        include_audio: Whether to include voiceover and music audio tracks.
        progress_callback: Optional callable(progress_float) returning False to cancel.

    Returns:
        True on success, False on failure or cancellation.
    """
    ffmpeg_path = _get_ffmpeg_path()
    if not ffmpeg_path:
        logger.error("ffmpeg not found. Install imageio-ffmpeg: pip install imageio-ffmpeg")
        return False

    # Create offscreen surface (shared across all cutscenes)
    surface = pygame.Surface((EXPORT_WIDTH, EXPORT_HEIGHT))

    # Build list of players for cutscenes that have data
    segments = []
    for cid in cutscene_ids:
        player = _ExportableCutscenePlayer(surface, cid)
        if player.has_cutscene:
            segments.append((cid, player, player.total_duration))

    if not segments:
        logger.error("No cutscene data found for any of the specified IDs")
        return False

    # Black gap duration between cutscenes (seconds)
    GAP_DURATION = 1.0
    gap_frames = int(GAP_DURATION * EXPORT_FPS)

    # Compute total frames across all segments + gaps
    total_frames = 0
    segment_time_offsets = []  # cumulative start time in seconds for each segment
    for i, (cid, player, duration) in enumerate(segments):
        segment_time_offsets.append(total_frames / EXPORT_FPS)
        total_frames += max(1, int(duration * EXPORT_FPS))
        if i < len(segments) - 1:
            total_frames += gap_frames

    if total_frames == 0:
        return False

    # Collect audio tracks with cumulative time offsets
    audio_tracks = []
    if include_audio:
        for i, (cid, player, duration) in enumerate(segments):
            time_offset = segment_time_offsets[i]
            tracks = _compute_audio_timeline_for_player(player, time_offset)
            audio_tracks.extend(tracks)

    needs_audio = len(audio_tracks) > 0

    # If audio needed, render silent video to temp file first
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if needs_audio:
        temp_fd, temp_video_path = tempfile.mkstemp(suffix='.mp4', dir=output_dir)
        os.close(temp_fd)
    else:
        temp_video_path = None

    try:
        # Pass 1: Render all frames to video
        video_target = temp_video_path if needs_audio else output_path
        success = _render_all_frames_to_video(
            ffmpeg_path, surface, segments, gap_frames, total_frames,
            video_target, include_subtitles, progress_callback
        )
        if not success:
            return False

        # Pass 2: Mux audio if needed (reuse CutsceneExporter._mux_audio)
        if needs_audio:
            dummy_exporter = CutsceneExporter.__new__(CutsceneExporter)
            dummy_exporter._ffmpeg_path = ffmpeg_path
            success = dummy_exporter._mux_audio(temp_video_path, output_path, audio_tracks)
            if not success:
                logger.warning("Audio muxing failed, saving silent video instead")
                try:
                    shutil.move(temp_video_path, output_path)
                except OSError:
                    pass
                return True

        return True

    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except OSError:
                pass


def _compute_audio_timeline_for_player(player, time_offset_seconds):
    """
    Build audio tracks for a single player with a cumulative time offset.

    Args:
        player: _ExportableCutscenePlayer instance.
        time_offset_seconds: Seconds to add to all start times.

    Returns:
        List of dicts: [{'path': str, 'start_ms': int, 'volume': float}, ...]
    """
    tracks = []
    offset_ms = int(time_offset_seconds * 1000)

    for i, slide in enumerate(player.slides):
        start_time = player.slide_start_times[i]

        # Voiceover track
        audio_path = slide.get('audio', '')
        if audio_path and os.path.exists(audio_path):
            voice_delay = slide.get('audio_start_delay', 0.0)
            trigger_time = start_time + voice_delay
            tracks.append({
                'path': audio_path,
                'start_ms': int(trigger_time * 1000) + offset_ms,
                'volume': slide.get('audio_volume', 1.0),
            })

        # Music track
        music_path = slide.get('music', '')
        if music_path and os.path.exists(music_path):
            music_delay = slide.get('music_start_delay', 0.0)
            trigger_time = start_time + music_delay
            is_duplicate = any(
                t['path'] == music_path and abs(t['start_ms'] - (int(trigger_time * 1000) + offset_ms)) < 100
                for t in tracks
            )
            if not is_duplicate:
                tracks.append({
                    'path': music_path,
                    'start_ms': int(trigger_time * 1000) + offset_ms,
                    'volume': slide.get('music_volume', 0.4),
                })

    return tracks


def _render_all_frames_to_video(ffmpeg_path, surface, segments, gap_frames,
                                total_frames, output_path, include_subtitles,
                                progress_callback):
    """
    Render all cutscene segments + black gaps into one ffmpeg pipe.

    Returns True on success, False on cancellation or error.
    """
    cmd = [
        ffmpeg_path,
        '-y',
        '-f', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', f'{EXPORT_WIDTH}x{EXPORT_HEIGHT}',
        '-r', str(EXPORT_FPS),
        '-i', 'pipe:0',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '18',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        output_path
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
    except FileNotFoundError:
        logger.error(f"Could not launch ffmpeg at: {ffmpeg_path}")
        return False

    # Pre-render a black frame for gaps (avoids re-rendering each gap frame)
    surface.fill((0, 0, 0))
    black_frame_bytes = pygame.image.tobytes(surface, 'RGB')

    try:
        frame_counter = 0

        for seg_idx, (cid, player, duration) in enumerate(segments):
            seg_frames = max(1, int(duration * EXPORT_FPS))

            # Render this cutscene's frames
            for f in range(seg_frames):
                t = f / EXPORT_FPS
                player.render_frame_at_time(t, render_subtitles=include_subtitles)
                frame_bytes = pygame.image.tobytes(surface, 'RGB')
                process.stdin.write(frame_bytes)

                frame_counter += 1
                if progress_callback and frame_counter % 10 == 0:
                    result = progress_callback(frame_counter / total_frames)
                    if result is False:
                        process.stdin.close()
                        process.kill()
                        process.communicate()
                        if os.path.exists(output_path):
                            try:
                                os.remove(output_path)
                            except OSError:
                                pass
                        return False

            # Write black gap frames between cutscenes (not after the last)
            if seg_idx < len(segments) - 1:
                for _ in range(gap_frames):
                    process.stdin.write(black_frame_bytes)
                    frame_counter += 1

        # Finalize
        if progress_callback:
            progress_callback(0.99)
        process.stdin.close()
        _, stderr_data = process.communicate()

        if process.returncode != 0:
            stderr_output = stderr_data.decode('utf-8', errors='replace') if stderr_data else ''
            logger.error(f"ffmpeg video encoding failed (code {process.returncode}): {stderr_output[:500]}")
            return False

        if progress_callback:
            progress_callback(1.0)
        return True

    except (BrokenPipeError, OSError) as e:
        logger.error(f"Error piping frames to ffmpeg: {e}")
        process.kill()
        process.communicate()
        return False
