import re
import os
from PIL import Image

# Define the input and output paths
png_folder = "png_outputs"
output_gif = "damBreak_simulation.gif"

# Extract numerical value from filename
def extract_number(filename):
    match = re.search(r"(\d+)", filename)  # Find the first number in the filename
    return int(match.group(1)) if match else float("inf")  # Convert to integer or set to a high number if no match

# Get a numerically sorted list of PNG files
png_files = sorted(
    [f for f in os.listdir(png_folder) if f.endswith(".png")],
    key=extract_number
)

# Ensure there are images to process
if not png_files:
    print("No PNG files found in the folder!")
    exit(1)

# Open images and create the GIF
image_sequence = [Image.open(os.path.join(png_folder, f)) for f in png_files]
image_sequence[0].save(
    output_gif,
    save_all=True,
    append_images=image_sequence[1:],  # Add the rest of the images
    duration=100,  # Frame duration in milliseconds
    loop=0  # Infinite loop
)

print(f"GIF saved as {output_gif}")
