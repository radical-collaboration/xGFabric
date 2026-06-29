#!/usr/bin/env python3
"""Render OpenFOAM VTK results to PNG images using ParaView.

Usage: pvpython render_foam.py <case_directory>
"""

from paraview.simple import *
import os
import gc
import sys

if len(sys.argv) != 2:
    print("Usage: pvpython render_foam.py <case_directory>")
    sys.exit(1)

# Define input and output folders
case_dir = sys.argv[1]
vtk_folder = os.path.join(case_dir, "VTK")
output_folder = os.path.join(case_dir, "png_outputs")

if not os.path.exists(vtk_folder):
    print(f"Error: VTK folder not found: {vtk_folder}")
    sys.exit(1)

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Create a render view once to reuse
render_view = GetActiveViewOrCreate('RenderView')
render_view.OrientationAxesVisibility = 0  # Remove coordinate axes

# Process each VTK file
files = sorted(os.listdir(vtk_folder))

# Remove 'allPatches' directory from the list if present
if 'allPatches' in files:
    files.remove('allPatches')

# Filter to only .vtk files
vtk_files = [f for f in files if f.endswith(".vtk")]

if not vtk_files:
    print(f"No VTK files found in {vtk_folder}")
    sys.exit(1)

print(f"Found {len(vtk_files)} VTK files to process")

for idx, filename in enumerate(vtk_files):
    filepath = os.path.join(vtk_folder, filename)
    output_png = os.path.join(output_folder, filename.replace(".vtk", ".png"))

    try:
        # Load VTK file
        data = LegacyVTKReader(FileNames=[filepath])
        
        # Create slice through the data
        slice_obj = Slice(Input=data)
        slice_obj.SliceType = "Plane"
        slice_obj.SliceType.Origin = [0.0, 1.0, 0.0]
        slice_obj.SliceType.Normal = [0.0, 1.0, 0.0]
        
        # Transform the slice
        transform = Transform(Input=slice_obj)
        transform.Transform.Rotate = [-90, 0, 0]
        
        # Display the transformed data
        display = Show(transform, render_view)
        
        # Set up coloring
        scalar_variables = data.PointData.keys()
        if scalar_variables:
            # Color by velocity magnitude if available
            if "U" in scalar_variables:
                ColorBy(display, ('POINTS', "U"))
            else:
                ColorBy(display, ('POINTS', scalar_variables[0]))
        else:
            print(f"Warning: No scalar data found in {filename}, using default coloring")

        # Render the view
        Render()
        
        # Set up camera
        render_view.ResetCamera()
        render_view.CameraPosition = [0, 5, 0]
        render_view.CameraFocalPoint = [0, 0, 0]
        render_view.CameraViewUp = [0, 0, 1]
        render_view.CameraParallelScale = 1

        # Save screenshot
        SaveScreenshot(output_png, render_view, 
                      ImageResolution=[1920, 1080], 
                      TransparentBackground=True)
        
        print(f"[{idx+1}/{len(vtk_files)}] Saved: {output_png}")

    except Exception as e:
        print(f"Error processing {filename}: {e}")

    finally:
        # Clean up to prevent memory issues
        if 'data' in locals():
            Delete(data)
            del data
        gc.collect()

print(f"\nRendering complete. {len(vtk_files)} images saved to {output_folder}")
