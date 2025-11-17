#!/usr/bin/env python3
from PIL import Image
import os
import sys

if len(sys.argv) != 2:
    print("Usage: python crop_image.py <case_directory>")
    sys.exit(1)

# Define input and output folders
case_dir = sys.argv[1]
output_folder = os.path.join(case_dir, "png_outputs")

files = sorted(os.listdir(output_folder))

png_files = [f for f in files if f.endswith(".png")]

if not png_files:
    print(f"No images found in {output_folder}")
    sys.exit(1)

cropped_dir = f"{output_folder}/cropped"
if not os.path.exists(cropped_dir):
    os.makedirs(cropped_dir)

print(f"Found {len(png_files)} PNG files to process")

for idx, filename in enumerate(png_files):
    filepath = os.path.join(output_folder, filename)
    
    out_image = cropped_dir+"/"+filename
    out_image = out_image.replace(".png", "_cropped.png")
    
    img = Image.open(filepath)
    img = img.convert("RGBA")

    # Automatically crop non-transparent or non-black areas
    bg = img.getpixel((0, 0))  # Top-left pixel (black background)
    bbox = img.getbbox()       # Bounding box of non-zero alpha or non-black pixels

    if bbox:
        cropped = img.crop(bbox)
        cropped.save(out_image)
        print("Cropped image saved")
    else:
        print("No content to crop.")