import os
import sys
import meshio
import pandas as pd
import tqdm
import re

# Usage: python vtk_to_csv.py /path/to/case/directory time_step [output_csv]
# Example: python vtk_to_csv.py cups_structure_25-07-19_20_56_47 0.83

def get_vtk_filenames(case_path, how_many):
    """
    """
    return sorted([os.path.join(case_path, "VTK", file) 
    for file in os.listdir(os.path.join(case_path, "VTK")) if file.endswith(".vtk")],
                    key = lambda x: x[:-4].split("_")[-1], reverse=True)[:how_many]
    
    

def vtk_to_csv(vtk_path, output_csv=None):
    """
    Convert VTK file to CSV for a specific time step.
    """
    
    # Generate output CSV name if not provided
    if output_csv is None:
        case_name = os.path.basename(case_path)
        output_csv = f"{filepath[:-4]}.csv"
    
    try:
        mesh = meshio.read(vtk_path)
        # Extract coordinates
        coords = mesh.points
        
        # Filter for points where y = 48 (with small tolerance for floating point)
        y_mask = abs(coords[:, 1] - 48.0) < 0.1
        filtered_coords = coords[y_mask]
        
        if len(filtered_coords) == 0:
            print(f"No points with y=48 found in {vtk_path}")
            return False
            
        # Build DataFrame for filtered coordinates
        df = pd.DataFrame(filtered_coords, columns=['x', 'y', 'z'])
        
        # Extract point data and filter with same mask
        point_data = mesh.point_data
        for key, arr in point_data.items():
            filtered_arr = arr[y_mask]
            if filtered_arr.ndim == 1:
                df[key] = filtered_arr
            elif filtered_arr.ndim == 2:
                for i in range(filtered_arr.shape[1]):
                    df[f"{key}_{i}"] = filtered_arr[:, i]
        
        # df['source_file'] = os.path.basename(vtk_path)
        # df['time_step'] = time_step
        
        print(f"Filtered {len(filtered_coords)} points from {len(coords)} total")
        
        # Save to CSV
        df.to_csv(output_csv, index=False)
        print(f"CSV saved to {output_csv}")
        return True
        
    except Exception as e:
        print(f"Error processing {vtk_path}: {e}")
        return False

if __name__ == "__main__":
    print("Starting processing")
    case_path = sys.argv[1]
    how_many = int(sys.argv[2])
    # Ensure case_path is absolute
    
    files = get_vtk_filenames(case_path, how_many)
    print(files)
    for file in files:
        print(f"processing {file}")
        su = vtk_to_csv(file, f"{file[:-4]}.csv")
        if not su:
            print(f"Failed to process {file}")
            sys.exit(1)
    
