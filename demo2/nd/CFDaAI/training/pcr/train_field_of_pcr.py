#!/usr/bin/env python3
"""
Train PCR models for a field of points in 3D space.

Usage:
    python train_field_of_pcr.py <sensor_folder> <simulations_folder> [options]

Arguments:
    sensor_folder: Path to folder containing sensor_out.csv
    simulations_folder: Path to folder containing simulation CSVs

Options:
    --nx: Number of points in X direction (default: 10)
    --ny: Number of points in Y direction (default: 5)
    --nz: Number of points in Z direction (default: 1)
    --column: Column to use from sensor_out.csv ('windavg' or 'windspeed', default: 'windavg')
    --n_components: Number of PCA components (default: 12)
    --sequence_length: Sequence length for PCR (default: 12)
    --output_dir: Output directory for coefficients (default: training/data)

Output:
    Creates PCR coefficient files for each grid point in output_dir
"""

import argparse
import json
import pandas as pd
import numpy as np
import os
import re
import sys
import time
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm


def format_duration(seconds):
    """Format duration in seconds to human-readable string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"


def load_grid_config():
    """Load grid configuration from grid_config.json."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Config is in parent directory
    config_file = os.path.join(script_dir, '..', 'grid_config.json')
    
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    
    # Fallback defaults
    return {
        'boundaries': {'x_min': 8.3, 'x_max': 176.5, 'y_min': 8.1, 'y_max': 82.1, 'z_min': 1.0, 'z_max': 7.0},
        'grid': {'nx': 85, 'ny': 38, 'nz': 4},
        'cfd_averaging': {'radius': 1.5}
    }


# Load grid configuration from grid_config.json
_CONFIG = load_grid_config()
X_MIN, X_MAX = _CONFIG['boundaries']['x_min'], _CONFIG['boundaries']['x_max']
Y_MIN, Y_MAX = _CONFIG['boundaries']['y_min'], _CONFIG['boundaries']['y_max']
Z_MIN, Z_MAX = _CONFIG['boundaries']['z_min'], _CONFIG['boundaries']['z_max']
AVERAGING_RADIUS = _CONFIG['cfd_averaging']['radius']


def load_all_simulations(simulations_folder):
    """
    Load all simulation CSVs once and return them as a dictionary.
    
    Returns:
        dict: windspeed -> DataFrame mapping
    """
    simulations = {}
    
    csv_files = [f for f in os.listdir(simulations_folder) if f.endswith('.csv')]
    
    for csv_file in csv_files:
        match = re.search(r'ws_([\d.]+)_wd', csv_file)
        if match:
            ws_value = float(match.group(1))
            df = pd.read_csv(os.path.join(simulations_folder, csv_file))
            simulations[ws_value] = df
    
    print(f"Loaded {len(simulations)} simulation files")
    print(f"Available windspeeds: {sorted(simulations.keys())}")
    
    return simulations


def get_u_magnitude_at_point(simulations, target_x, target_y, target_z, averaging_radius=AVERAGING_RADIUS):
    """
    Extract U_Magnitude at target point from all simulations.
    
    Gathers and averages data from CFD CSV within proximity radius around the grid point.
    If no points found within radius, falls back to finding the single closest point.
    
    Args:
        simulations: dict of windspeed -> DataFrame mappings
        target_x, target_y, target_z: Target grid point coordinates
        averaging_radius: Radius (meters) within which to average CFD data points
    
    Returns:
        dict: windspeed -> averaged U_Magnitude mapping
    """
    lookup = {}
    
    for ws_value, df in simulations.items():
        # Calculate distance from each point in the simulation to the target
        distances = np.sqrt((df['x'] - target_x)**2 + 
                            (df['y'] - target_y)**2 + 
                            (df['z'] - target_z)**2)
        
        # Find points within the averaging radius
        within_radius_mask = distances <= averaging_radius
        points_within = df[within_radius_mask]
        
        if len(points_within) > 0:
            # Average U_Magnitude of all points within radius
            lookup[ws_value] = points_within['U_Magnitude'].mean()
        else:
            # Fallback: find the single closest point
            closest_idx = distances.idxmin()
            lookup[ws_value] = df.loc[closest_idx, 'U_Magnitude']
    
    return lookup


def get_closest_simulation_ws(ws_value, available_ws):
    """Find the simulation windspeed closest to the given windspeed."""
    return min(available_ws, key=lambda x: abs(x - ws_value))


def train_pcr_for_point(out_values, target_values, n_components=12, sequence_length=12):
    """
    Train PCR model for a single point.
    
    Returns:
        dict: coefficient data or None if training fails
    """
    # Build sequences
    X = []
    y = []
    for i in range(len(out_values) - sequence_length + 1):
        seq = out_values[i:i + sequence_length]
        target = target_values[i + sequence_length - 1]
        X.append(seq)
        y.append(target)
    
    X = np.array(X)
    y = np.array(y)
    
    if len(X) == 0:
        return None
    
    # Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # PCA
    n_comp = min(n_components, sequence_length)
    pca = PCA(n_components=n_comp)
    X_pca = pca.fit_transform(X_scaled)
    
    # Linear Regression
    regressor = LinearRegression()
    regressor.fit(X_pca, y)
    
    return {
        'scaler_mean': scaler.mean_,
        'scaler_scale': scaler.scale_,
        'pca_components': pca.components_,
        'pca_mean': pca.mean_,
        'n_components': n_comp,
        'sequence_length': sequence_length,
        'reg_coef': regressor.coef_,
        'reg_intercept': regressor.intercept_
    }


def save_coefficients(coefficients, output_file):
    """Save PCR coefficients to CSV file."""
    flat_data = []
    flat_data.append(['scaler_mean'] + list(coefficients['scaler_mean']))
    flat_data.append(['scaler_scale'] + list(coefficients['scaler_scale']))
    flat_data.append(['pca_mean'] + list(coefficients['pca_mean']))
    for i, comp in enumerate(coefficients['pca_components']):
        flat_data.append([f'pca_component_{i}'] + list(comp))
    flat_data.append(['reg_coef'] + list(coefficients['reg_coef']))
    flat_data.append(['reg_intercept', coefficients['reg_intercept']])
    flat_data.append(['n_components', coefficients['n_components']])
    flat_data.append(['sequence_length', coefficients['sequence_length']])
    
    # Pad rows to same length
    max_len = max(len(row) for row in flat_data)
    for row in flat_data:
        while len(row) < max_len:
            row.append('')
    
    out_df = pd.DataFrame(flat_data)
    out_df.to_csv(output_file, index=False, header=False)


def create_grid(nx, ny, nz):
    """Create grid of points in 3D space."""
    x_points = np.linspace(X_MIN, X_MAX, nx)
    y_points = np.linspace(Y_MIN, Y_MAX, ny)
    z_points = np.linspace(Z_MIN, Z_MAX, nz) if nz > 1 else np.array([Z_MIN])
    
    grid_points = []
    for x in x_points:
        for y in y_points:
            for z in z_points:
                grid_points.append((round(x, 2), round(y, 2), round(z, 2)))
    
    return grid_points


def train_field_of_pcr(sensor_folder, simulations_folder, nx=10, ny=5, nz=1,
                       column='windavg', n_components=12, sequence_length=12, output_dir=None):
    """
    Train PCR models for all points on a 3D grid.
    """
    # Overall timing
    overall_start = time.time()
    
    # Setup output directory
    if output_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, 'data')
    
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output: {output_dir}")
    
    # Load sensor data once
    sensor_load_start = time.time()
    sensor_file = os.path.join(sensor_folder, 'sensor_out.csv')
    if not os.path.exists(sensor_file):
        raise FileNotFoundError(f"sensor_out.csv not found in {sensor_folder}")
    
    sensor_data = pd.read_csv(sensor_file).sort_values(by='dt')
    sensor_data['windspeed'] = (sensor_data['windspeed'] * 0.44704).round()
    sensor_data['windavg'] = (sensor_data['windavg'] * 0.44704).round()
    out_values = sensor_data[column].values
    sensor_load_end = time.time()
    sensor_load_elapsed = sensor_load_end - sensor_load_start
    
    print(f"Sensor: {len(sensor_data)} records, column={column}")
    
    # Load all simulations once
    sim_load_start = time.time()
    simulations = load_all_simulations(simulations_folder)
    available_ws = list(simulations.keys())
    sim_load_end = time.time()
    sim_load_elapsed = sim_load_end - sim_load_start
    print(f"Simulations: {len(simulations)} loaded")
    
    # Create grid
    grid_points = create_grid(nx, ny, nz)
    total_points = len(grid_points)
    print(f"Grid: {nx}x{ny}x{nz} = {total_points} points")
    
    # Train PCR for each grid point
    successful = 0
    failed = 0
    
    # Save grid info
    grid_info = []
    
    # Timing for model training
    train_start = time.time()
    
    # Track per-point timing
    point_times = []
    
    # Use tqdm for progress bar with unbuffered output
    for x, y, z in tqdm(grid_points, desc="Training PCR models", unit="point", file=sys.stdout):
        point_start = time.time()
        
        # Get U_Magnitude lookup for this point
        u_mag_lookup = get_u_magnitude_at_point(simulations, x, y, z)
        
        # Create target values by matching out_values to simulations
        target_values = []
        for out_val in out_values:
            closest_ws = get_closest_simulation_ws(out_val, available_ws)
            target_values.append(u_mag_lookup[closest_ws])
        target_values = np.array(target_values)
        
        # Train PCR model
        coefficients = train_pcr_for_point(out_values, target_values, n_components, sequence_length)
        
        if coefficients is not None:
            # Save coefficients
            xyz_name = f"{x}_{y}_{z}".replace('.', 'p')
            output_file = os.path.join(output_dir, f'pcr_coefficients_{xyz_name}.csv')
            save_coefficients(coefficients, output_file)
            successful += 1
            grid_info.append({
                'x': x, 'y': y, 'z': z,
                'coefficient_file': f'pcr_coefficients_{xyz_name}.csv',
                'status': 'success'
            })
        else:
            failed += 1
            grid_info.append({
                'x': x, 'y': y, 'z': z,
                'coefficient_file': '',
                'status': 'failed'
            })
        
        # Track point timing
        point_end = time.time()
        point_times.append(point_end - point_start)
    
    # Training complete timing
    train_end = time.time()
    train_elapsed = train_end - train_start
    
    print(f"\nComplete: {successful} ok, {failed} failed")
    
    # Statistics on per-point timing
    if point_times:
        avg_time = sum(point_times) / len(point_times)
        print(f"Per-point: avg={avg_time:.3f}s min={min(point_times):.3f}s max={max(point_times):.3f}s")
    
    # Save grid index file
    grid_index_file = os.path.join(output_dir, 'grid_index.csv')
    pd.DataFrame(grid_info).to_csv(grid_index_file, index=False)
    
    # Overall timing summary
    overall_end = time.time()
    overall_elapsed = overall_end - overall_start
    
    print(f"[TIMER] sensor_load={sensor_load_elapsed:.1f}s sim_load={sim_load_elapsed:.1f}s train={train_elapsed:.1f}s total={overall_elapsed:.1f}s")
    
    return grid_info


def main():
    parser = argparse.ArgumentParser(description='Train PCR models for a field of points')
    parser.add_argument('sensor_folder', help='Path to folder containing sensor_out.csv')
    parser.add_argument('simulations_folder', help='Path to folder containing simulation CSVs')
    parser.add_argument('--nx', type=int, default=10, help='Number of points in X direction (default: 10)')
    parser.add_argument('--ny', type=int, default=5, help='Number of points in Y direction (default: 5)')
    parser.add_argument('--nz', type=int, default=1, help='Number of points in Z direction (default: 1)')
    parser.add_argument('--column', default='windavg', choices=['windavg', 'windspeed'],
                        help='Column to use from sensor_out.csv (default: windavg)')
    parser.add_argument('--n_components', type=int, default=12, help='Number of PCA components (default: 12)')
    parser.add_argument('--sequence_length', type=int, default=12, help='Sequence length (default: 12)')
    parser.add_argument('--output_dir', '-o', help='Output directory for coefficients')
    
    args = parser.parse_args()
    
    train_field_of_pcr(
        args.sensor_folder,
        args.simulations_folder,
        nx=args.nx,
        ny=args.ny,
        nz=args.nz,
        column=args.column,
        n_components=args.n_components,
        sequence_length=args.sequence_length,
        output_dir=args.output_dir
    )


if __name__ == '__main__':
    main()
