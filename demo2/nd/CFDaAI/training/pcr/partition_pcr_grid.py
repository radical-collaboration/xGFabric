#!/usr/bin/env python3
"""
Partition PCR grid into equal-sized chunks for distributed training.

This script divides the full PCR grid into equal-sized chunks that can be 
trained on separate machines. It reads grid configuration from grid_config.json.

The partitioning is done by flattening the 3D grid to 1D and dividing evenly,
ensuring each machine gets approximately the same number of points.

Usage:
    python partition_pcr_grid.py <num_machines> [grid_nx] [grid_ny] [grid_nz]

Arguments:
    num_machines: Number of machines to partition grid across
    grid_nx: Grid points in X direction (default: from grid_config.json)
    grid_ny: Grid points in Y direction (default: from grid_config.json)
    grid_nz: Grid points in Z direction (default: from grid_config.json)

Output:
    JSON file (pcr_partitions.json) with partition information for each machine
"""

import json
import os
import sys
import numpy as np


def load_grid_config():
    """Load grid configuration from grid_config.json.
    
    Search order:
    1. GRID_CONFIG_PATH environment variable
    2. Current directory
    3. Script directory
    4. Parent directories up to 3 levels
    5. Fall back to defaults
    """
    # Check environment variable first
    env_path = os.environ.get('GRID_CONFIG_PATH')
    if env_path and os.path.exists(env_path):
        with open(env_path, 'r') as f:
            return json.load(f)
    
    # Search locations
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [
        os.getcwd(),
        script_dir,
        os.path.dirname(script_dir),  # training/
        os.path.dirname(os.path.dirname(script_dir)),  # intheloop/
        os.path.dirname(os.path.dirname(os.path.dirname(script_dir))),  # one more level
    ]
    
    for d in search_dirs:
        config_file = os.path.join(d, 'grid_config.json')
        if os.path.exists(config_file):
            print(f"[INFO] Using grid config: {config_file}")
            with open(config_file, 'r') as f:
                return json.load(f)
    
    print(f"Warning: grid_config.json not found in any search path, using defaults")
    return {
        'boundaries': {'x_min': 8.3, 'x_max': 176.5, 'y_min': 8.1, 'y_max': 82.1, 'z_min': 1.0, 'z_max': 7.0},
        'grid': {'nx': 85, 'ny': 38, 'nz': 4},
        'cfd_averaging': {'radius': 1.5}
    }


# Load configuration
CONFIG = load_grid_config()
X_MIN, X_MAX = CONFIG['boundaries']['x_min'], CONFIG['boundaries']['x_max']
Y_MIN, Y_MAX = CONFIG['boundaries']['y_min'], CONFIG['boundaries']['y_max']
Z_MIN, Z_MAX = CONFIG['boundaries']['z_min'], CONFIG['boundaries']['z_max']
DEFAULT_NX = CONFIG['grid']['nx']
DEFAULT_NY = CONFIG['grid']['ny']
DEFAULT_NZ = CONFIG['grid']['nz']
AVERAGING_RADIUS = CONFIG['cfd_averaging']['radius']


def create_grid(nx, ny, nz):
    """Create grid of points in 3D space and return as list of (x, y, z, flat_idx)."""
    x_points = np.linspace(X_MIN, X_MAX, nx)
    y_points = np.linspace(Y_MIN, Y_MAX, ny)
    z_points = np.linspace(Z_MIN, Z_MAX, nz) if nz > 1 else np.array([Z_MIN])
    
    grid_points = []
    flat_idx = 0
    for xi, x in enumerate(x_points):
        for yi, y in enumerate(y_points):
            for zi, z in enumerate(z_points):
                grid_points.append({
                    'x': round(float(x), 2),
                    'y': round(float(y), 2),
                    'z': round(float(z), 2),
                    'xi': xi,
                    'yi': yi,
                    'zi': zi,
                    'flat_idx': flat_idx
                })
                flat_idx += 1
    
    return grid_points


def partition_grid_equally(num_machines, nx, ny, nz):
    """
    Partition 3D grid into equal-sized chunks for different machines.
    
    Strategy: Flatten the grid to 1D and divide evenly among machines.
    This ensures each machine gets approximately the same number of points.
    
    Returns:
        dict: Partition information including grid points for each machine
    """
    total_points = nx * ny * nz
    
    # Create full grid
    grid_points = create_grid(nx, ny, nz)
    
    # Calculate chunk sizes (distribute remainder across first machines)
    base_chunk_size = total_points // num_machines
    remainder = total_points % num_machines
    
    print(f"[INFO] partition_pcr_grid: {nx}x{ny}x{nz}={total_points}pts -> {num_machines} machines ({base_chunk_size}+{remainder}r pts/machine)")
    
    partitions = []
    current_idx = 0
    
    for m in range(num_machines):
        # Calculate this machine's chunk size
        chunk_size = base_chunk_size + (1 if m < remainder else 0)
        
        if chunk_size == 0:
            print(f"[WARN]   Machine {m}: no points (too many machines)")
            continue
        
        # Get the points for this machine
        start_idx = current_idx
        end_idx = current_idx + chunk_size
        machine_points = grid_points[start_idx:end_idx]
        
        pct = (chunk_size / total_points) * 100
        
        partition = {
            'machine_id': m,
            'start_idx': start_idx,
            'end_idx': end_idx,
            'num_points': chunk_size,
            'pct_of_total': round(pct, 2),
            'points': machine_points  # Full point info for data preparation
        }
        partitions.append(partition)
        
        current_idx = end_idx
    
    return {
        'grid': {
            'nx': nx,
            'ny': ny,
            'nz': nz,
            'total_points': total_points,
            'x_range': [X_MIN, X_MAX],
            'y_range': [Y_MIN, Y_MAX],
            'z_range': [Z_MIN, Z_MAX],
            'averaging_radius': AVERAGING_RADIUS
        },
        'num_machines': num_machines,
        'partitions': partitions
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python partition_pcr_grid.py <num_machines> [nx] [ny] [nz]")
        print()
        print("Arguments:")
        print("  num_machines: Number of machines to distribute across")
        print(f"  nx: Grid points in X (default: {DEFAULT_NX} from grid_config.json)")
        print(f"  ny: Grid points in Y (default: {DEFAULT_NY} from grid_config.json)")
        print(f"  nz: Grid points in Z (default: {DEFAULT_NZ} from grid_config.json)")
        print()
        print(f"Grid boundaries from grid_config.json:")
        print(f"  X: {X_MIN} to {X_MAX}")
        print(f"  Y: {Y_MIN} to {Y_MAX}")
        print(f"  Z: {Z_MIN} to {Z_MAX}")
        print(f"  Averaging radius: {AVERAGING_RADIUS}m")
        sys.exit(1)
    
    num_machines = int(sys.argv[1])
    nx = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_NX
    ny = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_NY
    nz = int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_NZ
    
    if num_machines < 1:
        print("Error: num_machines must be at least 1")
        sys.exit(1)
    
    result = partition_grid_equally(num_machines, nx, ny, nz)
    
    # Save to JSON (but strip the full points list for the file - just keep indices)
    output_result = {
        'grid': result['grid'],
        'num_machines': result['num_machines'],
        'partitions': []
    }
    
    for p in result['partitions']:
        output_result['partitions'].append({
            'machine_id': p['machine_id'],
            'start_idx': p['start_idx'],
            'end_idx': p['end_idx'],
            'num_points': p['num_points'],
            'pct_of_total': p['pct_of_total']
        })
    
    output_file = 'pcr_partitions.json'
    with open(output_file, 'w') as f:
        json.dump(output_result, f, indent=2)
    
    print(f"Partition info saved to: {output_file}")
    
    # Also save full points info for data preparation
    full_output_file = 'pcr_partitions_full.json'
    with open(full_output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Full partition data saved to: {full_output_file}")


if __name__ == '__main__':
    main()
