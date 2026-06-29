"""
cfd_common.py - Shared utilities for CFD data processing

Contains domain bounds, spatial filtering, and data loading functions
used by both PINN and FNO training pipelines.
"""
import logging
import glob
import os
import re
import pandas as pd

# -----------------------------
# Domain bounds (meters) - CFD simulation domain
# -----------------------------
x_min, x_max = 8.3, 176.5   # X-axis bounds (meters)
y_min, y_max = 8.1, 82.1    # Y-axis bounds (meters)
z_min, z_max = 0.5, 5.0     # Z-axis bounds (0.5m from ground, 0.5m from roof)

# Domain dimensions
Lx = x_max - x_min  # Domain length in x
Ly = y_max - y_min  # Domain length in y
Lz = z_max - z_min  # Domain length in z


def filter_spatial_bounds(df, x_bounds=None, y_bounds=None, z_bounds=None):
    """
    Filter CFD data to spatial bounds (3D volume restriction).
    Applies x, y, and z coordinate limits to restrict training data to specific region.
    
    Args:
        df: DataFrame with x, y, z coordinates
        x_bounds: Tuple (x_min, x_max) or None to use global bounds
        y_bounds: Tuple (y_min, y_max) or None to use global bounds
        z_bounds: Tuple (z_min, z_max) or None to use global bounds (default: 0.5m to 5.0m)
    
    Returns:
        Filtered DataFrame within specified 3D volume bounds
    """
    df_filtered = df.copy()
    initial_count = len(df_filtered)
    
    # Apply x bounds
    if x_bounds is None:
        x_bounds = (x_min, x_max)
    df_filtered = df_filtered[
        (df_filtered["x"] >= x_bounds[0]) & (df_filtered["x"] <= x_bounds[1])
    ]
    
    # Apply y bounds
    if y_bounds is None:
        y_bounds = (y_min, y_max)
    df_filtered = df_filtered[
        (df_filtered["y"] >= y_bounds[0]) & (df_filtered["y"] <= y_bounds[1])
    ]
    
    # Apply z bounds (0.5m from ground, 0.5m from roof)
    if z_bounds is None:
        z_bounds = (z_min, z_max)
    df_filtered = df_filtered[
        (df_filtered["z"] >= z_bounds[0]) & (df_filtered["z"] <= z_bounds[1])
    ]
    
    filtered_count = len(df_filtered)
    
    if initial_count > 0:
        logging.debug(
            f"Spatial filtering: {initial_count} -> {filtered_count} points "
            f"(kept {filtered_count/initial_count*100:.1f}% within "
            f"x=[{x_bounds[0]:.1f},{x_bounds[1]:.1f}], "
            f"y=[{y_bounds[0]:.1f},{y_bounds[1]:.1f}], "
            f"z=[{z_bounds[0]:.1f},{z_bounds[1]:.1f}]m)"
        )
    
    df_filtered = df_filtered.sort_values(by="x")
    return df_filtered


def read_cfd_data(filepath_or_dir, pattern="cups_structure_ws*.csv"):
    """
    Read and preprocess CFD data from single file or directory.
    
    Args:
        filepath_or_dir: Path to single CSV file or directory containing multiple files
        pattern: Glob pattern to match CSV files if directory is provided
    
    Returns:
        List of tuples (wind_speed, DataFrame) for each file
    """
    data_list = []
    
    # Convert to absolute path
    filepath_or_dir = os.path.abspath(filepath_or_dir)
    
    logging.info(f"Reading CFD data from: {filepath_or_dir}")
    
    if not os.path.exists(filepath_or_dir):
        raise ValueError(f"Path does not exist: {filepath_or_dir}")
    
    if os.path.isdir(filepath_or_dir):
        # Try primary pattern, then fallback to new naming convention
        files = sorted(glob.glob(os.path.join(filepath_or_dir, pattern)))
        if not files:
            files = sorted(glob.glob(os.path.join(filepath_or_dir, 'sim_*.csv')))
            if files:
                logging.info(f"Found {len(files)} files matching new naming pattern 'sim_*.csv'")
        else:
            logging.info(f"Found {len(files)} files matching pattern '{pattern}'")
        if not files:
            raise ValueError(f"No CFD CSV files found in {filepath_or_dir}")
    else:
        # If single file
        logging.info(f"Reading single file: {filepath_or_dir}")
        files = [filepath_or_dir]

    params_file = str(filepath_or_dir).split("simulations")[0]
    params_file += "params/sim_params.csv"
    with open(params_file, 'r') as param_file:
        lines = param_file.readlines()

    for file in files:
        try:
            # Extract wind speed from filename
            # Supports: cups_structure_ws10_*.csv  OR  sim_N_ws_2.00_wd_Y.csv
            filename = os.path.basename(file)
            sim_number = int(re.search(r'\d+', filename).group())       
            ws = float(lines[sim_number + 1].split(",")[0])
            
            # Read and process file
            df = pd.read_csv(file)
            df.columns = [i.replace(":", "_") for i in df.columns]

            # Coerce all columns to numeric, turning empty strings / bad values into NaN
            numeric_cols = [c for c in df.columns if c not in ("file",)]
            for col in numeric_cols:
                if df[col].dtype == object:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Drop rows where any critical column is NaN
            critical = [c for c in ("x", "y", "z", "U_0", "U_1", "U_2") if c in df.columns]
            n_before = len(df)
            df = df.dropna(subset=critical)
            n_dropped = n_before - len(df)
            if n_dropped > 0:
                logging.warning(f"Dropped {n_dropped}/{n_before} rows with empty/invalid values in {filename}")
            if df.empty:
                logging.warning(f"File has no valid rows after cleaning, skipping: {filename}")
                continue

            # Calculate velocity magnitude if not present
            if "U_Magnitude" not in df.columns:
                df["U_Magnitude"] = (df["U_0"]**2 + df["U_1"]**2 + df["U_2"]**2)**0.5
            
            # Add wind speed as metadata
            df['wind_speed'] = ws
            data_list.append((ws, df))
            
        except Exception as e:
            logging.warning(f"Error processing file {file}: {str(e)}")
            continue
    
    if not data_list:
        raise ValueError("No valid data files were processed")
    
    return data_list


def filter_zero_velocity(df, umag_min=0.10):
    """
    Remove zero/near-zero velocity points (inside solids + stagnation zones).
    These points dilute the training signal and hurt model quality.
    
    Args:
        df: DataFrame with U_Magnitude column
        umag_min: Minimum velocity magnitude threshold (m/s)
    
    Returns:
        Filtered DataFrame with only points above threshold
    """
    if 'U_Magnitude' not in df.columns:
        if all(c in df.columns for c in ['U_0', 'U_1', 'U_2']):
            df = df.copy()
            df['U_Magnitude'] = (df['U_0']**2 + df['U_1']**2 + df['U_2']**2)**0.5
        else:
            logging.warning("No U_Magnitude or velocity components found; skipping velocity filter")
            return df
    
    n_before = len(df)
    df_filtered = df[df['U_Magnitude'] >= 0].copy()
    n_after = len(df_filtered)

    if n_before > 0:
        logging.debug(
            f"Velocity filter: {n_before} -> {n_after} points "
            f"(removed {n_before - n_after} with |U| < 0 m/s)"
        )
    
    return df_filtered


def normalize(x, min_val, max_val):
    """Normalize value to [0, 1] range."""
    return (x - min_val) / (max_val - min_val)


def denormalize(x_norm, min_val, max_val):
    """Denormalize value from [0, 1] range."""
    return x_norm * (max_val - min_val) + min_val
