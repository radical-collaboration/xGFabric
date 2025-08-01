from paraview.simple import *
import os, gc
import sys

# Define input and output folders
vtk_folder = f"{sys.argv[1]}/VTK"
output_folder = "../figures"

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Create a render view once to reuse
render_view = GetActiveViewOrCreate('RenderView')
render_view.OrientationAxesVisibility = 0

# Process each VTK file
files = sorted(os.listdir(vtk_folder))

# Remove 'allPatches' from the list
if 'allPatches' in files:
    files.remove('allPatches')

dir_length = len(files)
idx = 0

while idx < dir_length:
    if files[idx].endswith("200.vtk"):
        filepath = os.path.join(vtk_folder, files[idx])
        output_png = os.path.join(output_folder, files[idx].replace(".vtk", ".png"))

        try:
            # Load VTK file
            data = LegacyVTKReader(FileNames=[filepath])
            slice_obj = Slice(Input=data)
            slice_obj.SliceType = "Plane"
            slice_obj.SliceType.Origin = [0.0, 1.0, 0.0]
            slice_obj.SliceType.Normal = [0.0, 1.0, 0.0]
            transform = Transform(Input=slice_obj)
            transform.Transform.Rotate = [-90, 0, 0]
            display = Show(transform, render_view)
            # Ensure correct color mapping
            scalar_variables = data.PointData.keys()
            if scalar_variables:
                ColorBy(display, ('POINTS', "U"))  # Use the first scalar variable
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

