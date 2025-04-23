from paraview.simple import *
import os, gc

# Define input and output folders
vtk_folder = "damBreak/VTK"
output_folder = "png_outputs"

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Create a render view once to reuse
render_view = GetActiveViewOrCreate('RenderView')

# Process each VTK file
files = sorted(os.listdir(vtk_folder))

# Remove 'allPatches' from the list
if 'allPatches' in files:
    files.remove('allPatches')

dir_length = len(files)
idx = 0

while idx < dir_length:
    if files[idx].endswith(".vtk"):
        filepath = os.path.join(vtk_folder, files[idx])
        output_png = os.path.join(output_folder, files[idx].replace(".vtk", ".png"))

        try:
            # Load VTK file
            data = LegacyVTKReader(FileNames=[filepath])
            display = Show(data, render_view)

            # Ensure correct color mapping
            scalar_variables = data.PointData.keys()
            if scalar_variables:
                ColorBy(display, ('POINTS', scalar_variables[0]))  # Use the first scalar variable
            else:
                print(f"Warning: No scalar data found in {files[idx]}, skipping.")
                idx += 1  # Move to next file
                continue  

            Render()

            # Save Screenshot
            SaveScreenshot(output_png, render_view, ImageResolution=[1920, 1080], TransparentBackground=True)
            print(f"Saved: {output_png}")

        except Exception as e:
            print(f"Error processing {files[idx]}: {e}")

        finally:
            # Proper cleanup to prevent memory issues
            if 'data' in locals():
                Delete(data)  # Free VTK object
                del data

            gc.collect()  # Force garbage collection
        
    idx += 1  # Ensure index is always incremented
os._exit(0)