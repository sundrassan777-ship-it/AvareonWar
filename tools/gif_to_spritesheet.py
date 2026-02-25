#!/usr/bin/env python3
# tools/gif_to_spritesheet.py
# Converts a GIF file to a PNG sprite sheet

"""
GIF to Sprite Sheet Converter
==============================

Converts an animated GIF into a horizontal sprite sheet (PNG).

Usage:
    python tools/gif_to_spritesheet.py input.gif output.png

Optional arguments:
    --columns N     Number of columns (default: auto - single row)
    --scale FACTOR  Scale factor (e.g., 0.5 for half size)
"""

import sys
from PIL import Image
import math


def resize_and_crop(image, target_size):
    """
    Resize and crop image to target size, maintaining aspect ratio.
    Uses 'cover' mode - scales to fill, then crops excess.

    Args:
        image: PIL Image
        target_size: Tuple (width, height)

    Returns:
        PIL Image at exact target size
    """
    target_width, target_height = target_size
    target_aspect = target_width / target_height
    img_aspect = image.width / image.height

    if img_aspect > target_aspect:
        # Image is wider - fit height, crop width
        new_height = target_height
        new_width = int(new_height * img_aspect)
    else:
        # Image is taller - fit width, crop height
        new_width = target_width
        new_height = int(new_width / img_aspect)

    # Resize
    resized = image.resize((new_width, new_height), Image.LANCZOS)

    # Crop to center
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height

    return resized.crop((left, top, right, bottom))


def gif_to_spritesheet(gif_path, output_path, columns=None, scale=1.0, target_size=None):
    """
    Convert a GIF to a sprite sheet.

    Args:
        gif_path: Path to input GIF file
        output_path: Path to output PNG sprite sheet
        columns: Number of columns (None = single row)
        scale: Scale factor (1.0 = original size)
        target_size: Tuple (width, height) to resize/crop each frame to
    """
    print(f"Loading {gif_path}...")
    gif = Image.open(gif_path)

    # Extract all frames
    frames = []
    try:
        while True:
            frame = gif.copy().convert("RGBA")

            # Resize to target size if specified (with aspect ratio handling)
            if target_size:
                frame = resize_and_crop(frame, target_size)
            elif scale != 1.0:
                # Scale if needed
                new_size = (int(frame.width * scale), int(frame.height * scale))
                frame = frame.resize(new_size, Image.LANCZOS)

            frames.append(frame)
            gif.seek(len(frames))
    except EOFError:
        pass

    total_frames = len(frames)
    print(f"Extracted {total_frames} frames")

    if total_frames == 0:
        print("Error: No frames found!")
        return

    # Get frame dimensions (all frames should be same size)
    frame_width = frames[0].width
    frame_height = frames[0].height

    # Calculate grid layout
    if columns is None:
        # Single row
        cols = total_frames
        rows = 1
    else:
        cols = columns
        rows = math.ceil(total_frames / cols)

    print(f"Creating {cols}x{rows} sprite sheet...")
    print(f"Frame size: {frame_width}x{frame_height}")

    # Create sprite sheet
    sheet_width = frame_width * cols
    sheet_height = frame_height * rows
    sprite_sheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))

    # Paste frames
    for i, frame in enumerate(frames):
        col = i % cols
        row = i // cols
        x = col * frame_width
        y = row * frame_height
        sprite_sheet.paste(frame, (x, y))

    # Save
    print(f"Saving to {output_path}...")
    sprite_sheet.save(output_path, "PNG")

    print(f"Done! Sprite sheet size: {sheet_width}x{sheet_height}")
    print(f"Layout: {cols} columns x {rows} rows")

    return {
        'total_frames': total_frames,
        'frame_width': frame_width,
        'frame_height': frame_height,
        'columns': cols,
        'rows': rows
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python gif_to_spritesheet.py input.gif output.png [OPTIONS]")
        print("\nOptions:")
        print("  --columns N              Number of columns (default: auto - single row)")
        print("  --scale FACTOR           Scale factor (e.g., 0.5 for half size)")
        print("  --size WIDTHxHEIGHT      Resize and crop to exact size (e.g., 1920x1080)")
        print("\nExamples:")
        print("  python gif_to_spritesheet.py bg.gif bg_sheet.png --columns 10")
        print("  python gif_to_spritesheet.py bg.gif bg_sheet.png --size 1920x1080")
        sys.exit(1)

    gif_path = sys.argv[1]
    output_path = sys.argv[2]

    # Parse optional arguments
    columns = None
    scale = 1.0
    target_size = None

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == '--columns' and i + 1 < len(sys.argv):
            columns = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--scale' and i + 1 < len(sys.argv):
            scale = float(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--size' and i + 1 < len(sys.argv):
            # Parse WIDTHxHEIGHT format
            parts = sys.argv[i + 1].split('x')
            if len(parts) == 2:
                target_size = (int(parts[0]), int(parts[1]))
            i += 2
        else:
            i += 1

    gif_to_spritesheet(gif_path, output_path, columns, scale, target_size)
