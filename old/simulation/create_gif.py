#!/usr/bin/env python3
"""Create animated GIF from PNG sequence.

Usage: python3 create_gif.py <case_directory>
"""

import re
import os
from PIL import Image
import sys

if len(sys.argv) != 2:
    print("Usage: python3 create_gif.py <case_directory>")
    sys.exit(1)

case_dir = sys.argv[1]
png_folder = os.path.join(case_dir, "png_outputs")
output_gif = f"{case_dir}.gif"


def extract_number(filename):
    """Extract numerical value from filename for sorting."""
    numbers = re.findall(r'\d+', filename)
    return int(numbers[-1]) if numbers else 0


if not os.path.exists(png_folder):
    print(f"Error: PNG folder not found: {png_folder}")
    sys.exit(1)

# Get a numerically sorted list of PNG files
png_files = sorted(
    [f for f in os.listdir(png_folder) if f.endswith(".png")],
    key=extract_number
)

# Ensure there are images to process
if not png_files:
    print(f"No PNG files found in {png_folder}")
    sys.exit(1)

print(f"Creating GIF from {len(png_files)} PNG files...")

# Open images and create the GIF
image_sequence = [Image.open(os.path.join(png_folder, f)) for f in png_files]

image_sequence[0].save(
    output_gif,
    save_all=True,
    append_images=image_sequence[1:],
    duration=100,  # Frame duration in milliseconds
    loop=0  # Infinite loop
)

print(f"GIF saved as {output_gif}")
