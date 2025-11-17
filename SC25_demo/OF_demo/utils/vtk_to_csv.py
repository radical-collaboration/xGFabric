#!/usr/bin/env python3
"""Convert OpenFOAM VTK output to CSV format.

Usage: python3 vtk_to_csv.py <case_directory> <num_files>

Processes the latest N VTK files and extracts data at y=48 plane.
"""

import os
import sys
import meshio
import pandas as pd
import re

# Usage: python vtk_to_csv.py /path/to/case/directory num_files


def get_vtk_filenames(case_path, how_many):
    """Get the N most recent VTK files from the case VTK directory."""
    vtk_dir = os.path.join(case_path, "VTK")
    if not os.path.exists(vtk_dir):
        return []
    
    vtk_files = [os.path.join(vtk_dir, file) 
                 for file in os.listdir(vtk_dir) 
                 if file.endswith(".vtk")]
    
    # Sort by the numerical suffix in filename
    def get_number(filepath):
        basename = os.path.basename(filepath)
        numbers = re.findall(r'\d+', basename)
        return int(numbers[-1]) if numbers else 0
    
    return sorted(vtk_files, key=get_number, reverse=True)[:how_many]


def vtk_to_csv(vtk_path, output_csv=None):
    """
    Convert VTK file to CSV, extracting points at y=48.
    
    Args:
        vtk_path: Path to input VTK file
        output_csv: Path to output CSV file (auto-generated if None)
    
    Returns:
        True if successful, False otherwise
    """
    # Generate output CSV name if not provided
    if output_csv is None:
        output_csv = f"{vtk_path[:-4]}.csv"
    
    try:
        mesh = meshio.read(vtk_path)
        
        # Extract coordinates
        coords = mesh.points
        
        # Filter for points where y = 48 (with small tolerance for floating point)
        y_mask = abs(coords[:, 1] - 48.0) < 0.1
        filtered_coords = coords[y_mask]
        
        if len(filtered_coords) == 0:
            print(f"Warning: No points with y=48 found in {vtk_path}")
            # Try without filtering as fallback
            filtered_coords = coords
            y_mask = slice(None)
        
        # Build DataFrame for filtered coordinates
        df = pd.DataFrame(filtered_coords, columns=['x', 'y', 'z'])
        
        # Extract point data and filter with same mask
        point_data = mesh.point_data
        for key, arr in point_data.items():
            if hasattr(y_mask, '__len__'):
                filtered_arr = arr[y_mask]
            else:
                filtered_arr = arr
                
            if filtered_arr.ndim == 1:
                df[key] = filtered_arr
            elif filtered_arr.ndim == 2:
                # Vector data - split into components
                for i in range(filtered_arr.shape[1]):
                    df[f"{key}_{i}"] = filtered_arr[:, i]
        
        print(f"Filtered {len(filtered_coords)} points from {len(coords)} total")
        
        # Save to CSV
        df.to_csv(output_csv, index=False)
        print(f"CSV saved to {output_csv}")
        return True
        
    except Exception as e:
        print(f"Error processing {vtk_path}: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 vtk_to_csv.py <case_directory> <num_files>")
        sys.exit(1)
    
    print("Starting VTK to CSV conversion")
    case_path = sys.argv[1]
    how_many = int(sys.argv[2])
    
    files = get_vtk_filenames(case_path, how_many)
    
    if not files:
        print(f"No VTK files found in {case_path}/VTK")
        sys.exit(1)
    
    print(f"Processing {len(files)} VTK files:")
    for file in files:
        print(f"  - {os.path.basename(file)}")
    
    success_count = 0
    for file in files:
        print(f"\nProcessing {os.path.basename(file)}...")
        if vtk_to_csv(file, f"{file[:-4]}.csv"):
            success_count += 1
    
    print(f"\nConversion complete: {success_count}/{len(files)} files processed successfully")
    
    if success_count == 0:
        sys.exit(1)
