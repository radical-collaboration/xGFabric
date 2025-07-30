
import os
import sys
import pandas as pd
import numpy as np

def get_line(pathname):
    """Extract data along the line at y=48 with height variation based on sensor positions"""
    df = pd.read_csv(pathname)
    df.columns = [i.replace(":", "_") for i in df.columns]
    
    # Calculate U_Magnitude if not present
    if "U_Magnitude" not in df.columns:
        df["U_Magnitude"] = (df["U_0"]**2 + df["U_1"]**2 + df["U_2"]**2)**0.5
    
    # Sensor coordinates from exploration notebook
    points = [(-110, 48, 9.144), (41, 48, 4.57), (104, 48, 1.524), (166, 48, 1.524), (192, 48, 1.524)]
    
    # Height profile parameters
    a1 = 0  # Slope for first segment
    b1 = points[1][2] - a1*points[1][0]  # Height at first segment
    
    a2 = (points[2][2]-points[1][2])/(points[2][0]-points[1][0])  # Slope for second segment
    b2 = points[2][2] - a2*points[2][0]  # Height at second segment
    
    # Extract line data based on height profile
    df_line = df[(df["y"] == 48) &
             (  (((-df["z"]+b1+df['x']*a1).abs() < 0.1) & (df["x"] <= points[1][0])) |
                (((-df["z"]+b2+df['x']*a2).abs() < 0.1) & (df["x"] > points[1][0]) & (df["x"] <= points[2][0])) |
                (((df["z"] - 1.5).abs() < 0.1) & (df["x"] > points[2][0]))
                )].sort_values(by="x")
    
    return df_line

def load_and_average_csv_files(dest_folder):
    """Load all CSV files from VTK folder and average their U_Magnitude values"""
    vtk_folder = os.path.join(dest_folder, "VTK")
    
    if not os.path.exists(vtk_folder):
        raise FileNotFoundError(f"VTK folder not found in {dest_folder}")
    
    csv_files = [f for f in os.listdir(vtk_folder) if f.endswith('.csv')]
    
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {vtk_folder}")
    
    print(f"Found {len(csv_files)} CSV files to process")
    
    # Load and process all CSV files
    all_lines = []
    for csv_file in csv_files:
        file_path = os.path.join(vtk_folder, csv_file)
        try:
            df_line = get_line(file_path)
            if not df_line.empty:
                all_lines.append(df_line[["x", "U_Magnitude"]])
        except Exception as e:
            print(f"Warning: Could not process {csv_file}: {e}")
            continue
    
    if not all_lines:
        raise ValueError("No valid data could be extracted from CSV files")
    
    # Average across all files
    # Concatenate all dataframes and group by x coordinate
    combined_df = pd.concat(all_lines, ignore_index=True)
    averaged_df = combined_df.groupby("x").mean().reset_index()
    
    return averaged_df

def find_closest_values(df, xs):
    """Find U_Magnitude values at x coordinates closest to xs"""
    results = []
    
    for target_x in xs:
        # Find the closest x value in the dataframe
        closest_idx = (df["x"] - target_x).abs().idxmin()
        closest_x = df.loc[closest_idx, "x"]
        closest_value = df.loc[closest_idx, "U_Magnitude"]
        
        results.append(closest_value)
    
    return results

def main():

    
    dest_folder = sys.argv[1]
    xs = [-110, 41, 104, 166, 192]
    compare_to = [5.42407185, 2.08618148, 2.44381259, 2.44381259, 1.60934]
    
    try:
        # Load and average CSV files
        averaged_df = load_and_average_csv_files(dest_folder)

        # Find values at target x coordinates
        results = find_closest_values(averaged_df, xs)
        
        for i, (x, calc, exp) in enumerate(zip(xs, results, compare_to)):
            diff = calc - exp
            rel_error = (diff / exp * 100) if exp != 0 else float('inf')
   
        # Summary statistics
        differences = np.array(results) - np.array(compare_to)
        rel_errors = (differences / np.array(compare_to)) * 100

        # Validation check: sum of absolute differences must be less than 5
        sum_abs_diff = np.sum(np.abs(differences))
        print(f"Sum of absolute differences: {sum_abs_diff:.8f}")
        
        if sum_abs_diff >= 5.0:
            raise ValueError(f"Validation failed")
        else:
            print("✓ Validation passed")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()