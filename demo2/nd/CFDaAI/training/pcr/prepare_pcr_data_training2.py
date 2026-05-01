#!/usr/bin/env python3
"""
Prepare data files for the PCR binary (training2/pcr).

This script prepares data in the format required by the pcr binary:
- X file: Feature matrix with space-separated values per row (sequences)
- Y file: Target values, one per row

Usage:
    python prepare_pcr_data.py <sensor_folder> <simulations_folder> [options]

Arguments:
    sensor_folder: Path to folder containing sensor_out.csv
    simulations_folder: Path to folder containing simulation CSVs

Options:
    --target-x: X coordinate for target point (default: 41.0)
    --target-y: Y coordinate for target point (default: 48.0)  
    --target-z: Z coordinate for target point (default: 4.0)
    --column: Column to use from sensor_out.csv ('windavg' or 'windspeed', default: 'windavg')
    --sequence_length: Sequence length for features (default: 12)
    --output_dir: Output directory for data files (default: current directory)

Output:
    Creates X.txt (sequences) and Y.txt (targets) files for pcr binary
"""

import argparse
import json
import pandas as pd
import numpy as np
import os
import re
import sys
from typing import Dict, List, Tuple


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
AVERAGING_RADIUS = _CONFIG['cfd_averaging']['radius']


def load_all_simulations(simulations_folder: str) -> Dict[float, pd.DataFrame]:
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


def get_u_magnitude_at_point(simulations: Dict[float, pd.DataFrame], 
                             target_x: float, target_y: float, target_z: float,
                             averaging_radius: float = AVERAGING_RADIUS) -> Dict[float, float]:
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


def get_closest_simulation_ws(ws_value: float, available_ws: List[float]) -> float:
    """Find the simulation windspeed closest to the given windspeed."""
    return min(available_ws, key=lambda x: abs(x - ws_value))


def prepare_pcr_data(sensor_folder: str, simulations_folder: str,
                     target_x: float = 41.0, target_y: float = 48.0, target_z: float = 4.0,
                     column: str = 'windavg', sequence_length: int = 12,
                     output_dir: str = None) -> Tuple[str, str]:
    """
    Prepare data files for the PCR binary.
    
    Args:
        sensor_folder: Path to folder containing sensor_out.csv
        simulations_folder: Path to folder containing simulation CSVs
        target_x, target_y, target_z: Coordinates for target point
        column: Column to use from sensor_out.csv
        sequence_length: Length of feature sequences
        output_dir: Directory to save output files
    
    Returns:
        Tuple of (x_file_path, y_file_path)
    """
    if output_dir is None:
        output_dir = os.getcwd()
    os.makedirs(output_dir, exist_ok=True)
    
    # Load sensor data
    sensor_file = os.path.join(sensor_folder, 'sensor_out.csv')
    if not os.path.exists(sensor_file):
        raise FileNotFoundError(f"sensor_out.csv not found in {sensor_folder}")
    
    sensor_data = pd.read_csv(sensor_file).sort_values(by='dt')
    
    sensor_data['windspeed_ms'] = sensor_data['windspeed_ms'].round()
    sensor_data['windavg_ms'] = sensor_data['windavg_ms'].round()

    out_values = sensor_data[column].values
    print(f"Loaded {len(sensor_data)} sensor readings, using column: {column}")
    print(f"Windspeed range: {out_values.min():.1f} - {out_values.max():.1f} m/s")
    
    # Load simulations
    simulations = load_all_simulations(simulations_folder)
    available_ws = sorted(simulations.keys())
    
    # Get U_Magnitude lookup for the target point
    u_mag_lookup = get_u_magnitude_at_point(simulations, target_x, target_y, target_z)
    print(f"Target point: ({target_x}, {target_y}, {target_z})")
    print(f"U_Magnitude lookup table created for {len(u_mag_lookup)} windspeeds")
    
    # Create target values by matching out_values to simulations
    target_values = []
    for out_val in out_values:
        closest_ws = get_closest_simulation_ws(out_val, available_ws)
        target_values.append(u_mag_lookup[closest_ws])
    target_values = np.array(target_values)
    
    # Build sequences (X matrix) and targets (Y vector)
    X_sequences = []
    Y_targets = []
    
    for i in range(len(target_values) - sequence_length + 1):
        # Sequence of target values (CFD U_Magnitude) as features
        seq = target_values[i:i + sequence_length]
        # Input windspeed as target to predict
        y = out_values[i + sequence_length - 1]
        X_sequences.append(seq)
        Y_targets.append(y)
    
    X_sequences = np.array(X_sequences)
    Y_targets = np.array(Y_targets)
    
    print(f"Created {len(X_sequences)} sequences of length {sequence_length}")
    print(f"X matrix shape: {X_sequences.shape}")
    print(f"Y vector shape: {Y_targets.shape}")
    
    # Generate unique name for output files based on target coordinates
    xyz_name = f"{target_x}_{target_y}_{target_z}".replace('.', 'p')
    
    # Write X file (space-separated sequences)
    x_file = os.path.join(output_dir, f"X_{xyz_name}.txt")
    with open(x_file, 'w') as f:
        for seq in X_sequences:
            f.write(' '.join(f'{v:.6f}' for v in seq) + '\n')
    
    # Write Y file (one value per line)
    y_file = os.path.join(output_dir, f"Y_{xyz_name}.txt")
    with open(y_file, 'w') as f:
        for y in Y_targets:
            f.write(f'{y:.6f}\n')
    
    print(f"Saved X file: {x_file}")
    print(f"Saved Y file: {y_file}")
    
    return x_file, y_file


def prepare_pcr_data_for_grid(sensor_folder: str, simulations_folder: str,
                               grid_points: List[Tuple[float, float, float]],
                               column: str = 'windavg', sequence_length: int = 12,
                               output_dir: str = None) -> List[Tuple[str, str, float, float, float]]:
    """
    Prepare data files for the PCR binary for multiple grid points.
    
    Returns:
        List of (x_file_path, y_file_path, x, y, z) tuples
    """
    if output_dir is None:
        output_dir = os.getcwd()
    os.makedirs(output_dir, exist_ok=True)
    
    # Load sensor data once
    sensor_file = os.path.join(sensor_folder, 'sensor_out.csv')
    if not os.path.exists(sensor_file):
        raise FileNotFoundError(f"sensor_out.csv not found in {sensor_folder}")
    
    sensor_data = pd.read_csv(sensor_file).sort_values(by='dt')
    sensor_data['windspeed_ms'] = sensor_data['windspeed_ms'].round()
    sensor_data['windavg_ms'] = sensor_data['windavg_ms'].round()
    out_values = sensor_data[column].values
    print(f"Loaded {len(sensor_data)} sensor readings, using column: {column}")
    
    # Load simulations once
    simulations = load_all_simulations(simulations_folder)
    available_ws = sorted(simulations.keys())
    
    results = []
    
    for target_x, target_y, target_z in grid_points:
        # Get U_Magnitude lookup for this point
        u_mag_lookup = get_u_magnitude_at_point(simulations, target_x, target_y, target_z)
        
        # Create target values
        target_values = []
        for out_val in out_values:
            closest_ws = get_closest_simulation_ws(out_val, available_ws)
            target_values.append(u_mag_lookup[closest_ws])
        target_values = np.array(target_values)
        
        # Build sequences and targets
        X_sequences = []
        Y_targets = []
        
        for i in range(len(target_values) - sequence_length + 1):
            seq = target_values[i:i + sequence_length]
            y = out_values[i + sequence_length - 1]
            X_sequences.append(seq)
            Y_targets.append(y)
        
        X_sequences = np.array(X_sequences)
        Y_targets = np.array(Y_targets)
        
        # Generate filenames
        xyz_name = f"{target_x}_{target_y}_{target_z}".replace('.', 'p')
        
        x_file = os.path.join(output_dir, f"X_{xyz_name}.txt")
        y_file = os.path.join(output_dir, f"Y_{xyz_name}.txt")
        
        # Write files
        with open(x_file, 'w') as f:
            for seq in X_sequences:
                f.write(' '.join(f'{v:.6f}' for v in seq) + '\n')
        
        with open(y_file, 'w') as f:
            for y in Y_targets:
                f.write(f'{y:.6f}\n')
        
        results.append((x_file, y_file, target_x, target_y, target_z))
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Prepare data files for the PCR binary',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
    # Single point preparation
    python prepare_pcr_data.py /path/to/sensor_folder /path/to/simulations --target-x 41 --target-y 48
    
    # Then run pcr binary:
    ./pcr -x X_41_48_4.txt -y Y_41_48_4.txt -c 12
        """
    )
    parser.add_argument('sensor_folder', help='Path to folder containing sensor_out.csv')
    parser.add_argument('simulations_folder', help='Path to folder containing simulation CSVs')
    parser.add_argument('--target-x', type=float, default=41.0, help='X coordinate for target point (default: 41.0)')
    parser.add_argument('--target-y', type=float, default=48.0, help='Y coordinate for target point (default: 48.0)')
    parser.add_argument('--target-z', type=float, default=4.0, help='Z coordinate for target point (default: 4.0)')
    parser.add_argument('--column', default='windavg_ms', choices=['windavg_ms', 'windspeed_ms'],
                        help='Column to use from sensor_out.csv (default: windavg_ms)')
    parser.add_argument('--sequence_length', type=int, default=12, help='Sequence length (default: 12)')
    parser.add_argument('--output_dir', '-o', help='Output directory for data files')
    
    args = parser.parse_args()
    
    prepare_pcr_data(
        args.sensor_folder,
        args.simulations_folder,
        target_x=args.target_x,
        target_y=args.target_y,
        target_z=args.target_z,
        column=args.column,
        sequence_length=args.sequence_length,
        output_dir=args.output_dir
    )


if __name__ == '__main__':
    main()
