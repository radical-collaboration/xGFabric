import sys
import os
from paraview.simple import *

pwd = sys.argv[1]
# Disable automatic camera reset on 'Show'
paraview.simple._DisableFirstRenderCameraReset()

# Create a new 'OpenFOAMReader'
foam_file = f'{pwd}/open.foam'

# Create foam file if it doesn't exist
if not os.path.exists(foam_file):
    with open(foam_file, 'w') as f:
        f.write('')

# Load the OpenFOAM case
reader = OpenFOAMReader(FileName=foam_file)
reader.MeshRegions = ['internalMesh']

# Get available fields
reader.UpdatePipelineInformation()
available_arrays = reader.CellArrays.Available
print(f"Available fields: {available_arrays}")

# Common fields to visualize (adjust based on your case)
fields_to_plot = ['p', 'U', 'k', 'epsilon', 'nut']
actual_fields = [field for field in fields_to_plot if field in available_arrays]

if not actual_fields:
    actual_fields = available_arrays[:3]  # Take first 3 available fields

print(f"Visualizing fields: {actual_fields}")

# Get animation scene
animationScene1 = GetAnimationScene()
animationScene1.UpdateAnimationUsingDataTimeSteps()

# Go to last time step
time_steps = animationScene1.TimeKeeper.TimestepValues
if time_steps:
    animationScene1.AnimationTime = time_steps[-1]
    print(f"Using final time step: {time_steps[-1]}")

# Create render view
renderView1 = CreateView('RenderView')
renderView1.ViewSize = [1200, 800]
renderView1.CameraPosition = [0.0, 0.0, 1.0]
renderView1.CameraFocalPoint = [0.0, 0.0, 0.0]
renderView1.CameraViewUp = [0.0, 1.0, 0.0]

# Show data in view
display = Show(reader, renderView1)

# Create visualizations for each field
for i, field in enumerate(actual_fields):
    print(f"Creating visualization for {field}")
    
    # Set the field to color by
    ColorBy(display, ('CELLS', field))
    
    # Get color transfer function
    field_LUT = GetColorTransferFunction(field)
    field_LUT.ApplyPreset('Cool to Warm (Extended)', True)
    
    # Add color bar
    field_LUTColorBar = GetScalarBar(field_LUT, renderView1)
    field_LUTColorBar.Title = field
    field_LUTColorBar.ComponentTitle = ''
    field_LUTColorBar.TitleFontSize = 16
    field_LUTColorBar.LabelFontSize = 12
    
    # Show color bar
    display.SetScalarBarVisibility(renderView1, True)
    
    # Reset camera to fit data
    renderView1.ResetCamera()
    
    # Render and save
    Render()
    
    # Save screenshot
    output_file = f'{sys.argv[1]}/png_outputs/{field}_{pwd}_final.png'
    SaveScreenshot(output_file, renderView1, ImageResolution=[1200, 800])
    print(f"Saved: {output_file}")
    
    # Hide color bar for next iteration
    display.SetScalarBarVisibility(renderView1, False)

# Create a pressure contour plot if pressure exists
if 'p' in actual_fields:
    print("Creating pressure contour visualization")
    
    # Create contour filter
    contour1 = Contour(Input=reader)
    contour1.ContourBy = ['CELLS', 'p']
    contour1.Isosurfaces = [0.0]  # Adjust based on your pressure range
    
    # Show contour
    contour_display = Show(contour1, renderView1)
    ColorBy(contour_display, ('CELLS', 'p'))
    
    # Get color transfer function
    p_LUT = GetColorTransferFunction('p')
    p_LUT.ApplyPreset('Cool to Warm (Extended)', True)
    
    # Show color bar
    p_LUTColorBar = GetScalarBar(p_LUT, renderView1)
    p_LUTColorBar.Title = 'Pressure'
    contour_display.SetScalarBarVisibility(renderView1, True)
    
    # Reset camera and render
    renderView1.ResetCamera()
    Render()
    
    # Save contour plot
    SaveScreenshot(f'{sys.argv[1]}/png_outputs/pressure_contour_{pwd}_final.png', renderView1, ImageResolution=[1200, 800])
    print(f"Saved: {sys.argv[1]}/png_outputs/pressure_contour_{pwd}_final.png")

# -------------------------------------------------------------------

vtk_dir = f'{pwd}/VTK'

# Find all VTK files in the directory
vtk_files = [f for f in os.listdir(vtk_dir) if f.endswith('.vtk')]

if not vtk_files:
    print("No VTK files found in VTK directory.")
    exit(1)

print(f"Found VTK files: {vtk_files}")

# Create a new render view for VTK files
renderView2 = CreateView('RenderView')
renderView2.ViewSize = [1200, 800]
renderView2.CameraPosition = [0.0, 0.0, 1.0]
renderView2.CameraFocalPoint = [0.0, 0.0, 0.0]
renderView2.CameraViewUp = [0.0, 1.0, 0.0]

# Process each VTK file
for vtk_file in sorted(vtk_files):
    vtk_path = os.path.join(vtk_dir, vtk_file)
    print(f"Processing VTK file: {vtk_file}")
    
    try:
        # Load VTK file
        vtk_reader = LegacyVTKReader(FileNames=[vtk_path])
        vtk_reader.UpdatePipelineInformation()
        
        # Get available arrays
        point_arrays = vtk_reader.PointData.GetArrayNames() if hasattr(vtk_reader.PointData, 'GetArrayNames') else []
        cell_arrays = vtk_reader.CellData.GetArrayNames() if hasattr(vtk_reader.CellData, 'GetArrayNames') else []
        
        print(f"  Point arrays: {point_arrays}")
        print(f"  Cell arrays: {cell_arrays}")
        
        # Show the VTK data
        vtk_display = Show(vtk_reader, renderView2)
        
        # Try to color by pressure first, then velocity, then first available array
        colored = False
        
        # Check for common fields in both point and cell data
        common_fields = ['p', 'U', 'pressure', 'velocity', 'k', 'epsilon']
        
        for field in common_fields:
            if field in point_arrays:
                ColorBy(vtk_display, ('POINTS', field))
                field_name = field
                colored = True
                break
            elif field in cell_arrays:
                ColorBy(vtk_display, ('CELLS', field))
                field_name = field
                colored = True
                break
        
        # If no common fields found, use first available
        if not colored:
            if point_arrays:
                ColorBy(vtk_display, ('POINTS', point_arrays[0]))
                field_name = point_arrays[0]
                colored = True
            elif cell_arrays:
                ColorBy(vtk_display, ('CELLS', cell_arrays[0]))
                field_name = cell_arrays[0]
                colored = True
        
        if colored:
            # Set up color transfer function
            field_LUT = GetColorTransferFunction(field_name)
            field_LUT.ApplyPreset('Cool to Warm (Extended)', True)
            
            # Add color bar
            field_LUTColorBar = GetScalarBar(field_LUT, renderView2)
            field_LUTColorBar.Title = field_name
            field_LUTColorBar.ComponentTitle = ''
            field_LUTColorBar.TitleFontSize = 16
            field_LUTColorBar.LabelFontSize = 12
            
            # Show color bar
            vtk_display.SetScalarBarVisibility(renderView2, True)
            
            # Set representation to surface
            vtk_display.Representation = 'Surface'
        else:
            # Just show geometry without coloring
            vtk_display.Representation = 'Surface'
            print(f"  No suitable fields found for coloring, showing geometry only")
        
        # Reset camera to fit data
        renderView2.ResetCamera()
        
        # Render and save
        Render()
        
        # Save screenshot
        base_name = os.path.splitext(vtk_file)[0]
        output_file = f'{pwd}/png_outputs/patch_{base_name}.png'
        SaveScreenshot(output_file, renderView2, ImageResolution=[1200, 800])
        print(f"  Saved: {output_file}")
        
        # Hide this data before next iteration
        Hide(vtk_reader, renderView2)
        
    except Exception as e:
        print(f"  Error processing {vtk_file}: {str(e)}")
        continue

print("VTK patch rendering complete!")

print("Visualizations complete!")