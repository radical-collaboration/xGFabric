#!/usr/bin/env python3
"""Create animated GIF from PNG sequence.

Usage: python3 create_gif.py <images_directory> [output_name]
"""

import re
import os
from PIL import Image
import sys

if len(sys.argv) < 2:
    print("Usage: python3 create_gif.py <images_directory> [output_name]")
    sys.exit(1)

images_dir = sys.argv[1]
case_name = os.path.basename(os.path.dirname(images_dir)) if images_dir.endswith('images') else os.path.basename(images_dir)
output_gif = sys.argv[2] if len(sys.argv) > 2 else f"{case_name}.gif"

def extract_number(filename):
    """Extract numerical value from filename for sorting."""
    numbers = re.findall(r'\d+', filename)
    return int(numbers[-1]) if numbers else 0

# Check if input is a directory or case directory
if not os.path.exists(images_dir):
    print(f"Error: Directory not found: {images_dir}")
    sys.exit(1)

# If given case directory, look for png_outputs inside
if os.path.isdir(images_dir) and not any(f.endswith('.png') for f in os.listdir(images_dir)):
    # Try png_outputs subdirectory
    png_folder = os.path.join(images_dir, "png_outputs")
    if os.path.exists(png_folder):
        images_dir = png_folder
    # Try images subdirectory
    else:
        images_dir_alt = os.path.join(images_dir, "images")
        if os.path.exists(images_dir_alt):
            images_dir = images_dir_alt

if not os.path.exists(images_dir):
    print(f"Error: No images directory found: {images_dir}")
    sys.exit(1)

# Get a numerically sorted list of PNG files
png_files = sorted(
    [f for f in os.listdir(images_dir) if f.endswith(".png")],
    key=extract_number
)

# Ensure there are images to process
if not png_files:
    print(f"No PNG files found in {images_dir}")
    sys.exit(1)

png_files = png_files[2:]

print(f"Creating GIF from {len(png_files)} PNG files...")
print(f"Output: {output_gif}")

# Open images and create the GIF
image_sequence = [Image.open(os.path.join(images_dir, f)) for f in png_files]

image_sequence[0].save(
    output_gif,
    save_all=True,
    append_images=image_sequence[1:],
    duration=100,  # Frame duration in milliseconds
    loop=0  # Infinite loop
)

print(f"GIF saved as {output_gif}")
