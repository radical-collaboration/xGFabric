#!/usr/bin/env python3
"""
Convert OpenFOAM VTK output to CSV format.
Preserves entire 3D spatial data including coordinates, velocity, and pressure.

Usage: python3 vtk_to_csv.py <vtk_file> <output_csv>
"""

import os
import sys
import meshio
import pandas as pd
import numpy as np


def vtk_to_csv(vtk_path, output_csv):
    """
    Convert VTK file to CSV, preserving entire 3D spatial domain.
    
    Args:
        vtk_path: Path to VTK file
        output_csv: Path to output CSV file
    
    Returns:
        True if successful, False otherwise
    """
    
    if not os.path.exists(vtk_path):
        print(f"Error: VTK file not found: {vtk_path}")
        return False
    
    try:
        print(f"Reading VTK file: {vtk_path}")
        mesh = meshio.read(vtk_path)
        
        # Extract coordinates (keep entire 3D space)
        coords = mesh.points
        print(f"Total points in mesh: {len(coords)}")
        print(f"X range: {coords[:, 0].min():.2f} to {coords[:, 0].max():.2f}")
        print(f"Y range: {coords[:, 1].min():.2f} to {coords[:, 1].max():.2f}")
        print(f"Z range: {coords[:, 2].min():.2f} to {coords[:, 2].max():.2f}")
        
        # Build DataFrame for all coordinates (no filtering)
        df = pd.DataFrame(coords, columns=['x', 'y', 'z'])
        
        # Extract point data (keep all points)
        point_data = mesh.point_data
        
        for key, arr in point_data.items():
            if arr.ndim == 1:
                # Scalar field (like pressure)
                df[key] = arr
            elif arr.ndim == 2:
                # Vector field (like velocity)
                for i in range(arr.shape[1]):
                    df[f"{key}_{i}"] = arr[:, i]
        
        # Calculate velocity magnitude if U components exist
        if 'U_0' in df.columns and 'U_1' in df.columns and 'U_2' in df.columns:
            df['U_Magnitude'] = np.sqrt(df['U_0']**2 + df['U_1']**2 + df['U_2']**2)
            print(f"Velocity magnitude range: {df['U_Magnitude'].min():.3f} to {df['U_Magnitude'].max():.3f} m/s")
        
        # Check for pressure field
        if 'p' in df.columns:
            print(f"Pressure range: {df['p'].min():.3f} to {df['p'].max():.3f} Pa")
        elif 'p_rgh' in df.columns:
            print(f"Pressure (p_rgh) range: {df['p_rgh'].min():.3f} to {df['p_rgh'].max():.3f} Pa")
        
        # Save to CSV
        df.to_csv(output_csv, index=False)
        print(f"CSV saved to: {output_csv}")
        print(f"Columns: {', '.join(df.columns)}")
        
        return True
        
    except Exception as e:
        print(f"Error processing {vtk_path}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 vtk_to_csv.py <vtk_file> <output_csv>")
        print("\nConverts OpenFOAM VTK output to CSV format")
        print("Preserves entire 3D spatial domain for training")
        sys.exit(1)
    
    vtk_path = sys.argv[1]
    output_csv = sys.argv[2]
    
    success = vtk_to_csv(vtk_path, output_csv)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
