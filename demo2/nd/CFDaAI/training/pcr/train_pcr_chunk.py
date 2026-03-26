#!/usr/bin/env python3
"""
Train PCR models from pre-prepared chunk data file.

This script is designed to run on remote machines during distributed PCR training.
It reads a pre-prepared pickle file containing all the data needed to train PCR
models for its assigned grid points.

Uses scikit-learn for PCR training (PCA + LinearRegression).

Usage:
    python train_pcr_chunk.py <data_file> <output_dir>

Arguments:
    data_file: Path to machine_N_data.pkl file created by prepare_pcr_data.py
    output_dir: Directory to save PCR coefficient files

Output:
    Creates pcr_coefficients_X_Y_Z.csv for each grid point in the chunk
"""

import argparse
import os
import pickle
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_squared_error


def format_duration(seconds):
    """Format duration in seconds to human-readable string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"


def get_closest_ws(ws_value, available_ws):
    """Find the simulation windspeed closest to the given value."""
    return min(available_ws, key=lambda x: abs(x - ws_value))


def train_pcr_sklearn(X, y, n_components=12):
    """
    Train PCR model using scikit-learn.
    
    Args:
        X: Feature matrix (n_samples, sequence_length)
        y: Target values (n_samples,)
        n_components: Number of PCA components
    
    Returns:
        dict with model parameters and metrics
    """
    if len(X) == 0:
        return None
    
    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # PCA dimensionality reduction
    n_comp = min(n_components, X.shape[1], X.shape[0])
    pca = PCA(n_components=n_comp)
    X_pca = pca.fit_transform(X_scaled)
    
    # Linear regression on principal components
    regressor = LinearRegression()
    regressor.fit(X_pca, y)
    
    # Compute metrics
    y_pred = regressor.predict(X_pca)
    r_squared = r2_score(y, y_pred)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    
    return {
        'scaler_mean': scaler.mean_,
        'scaler_scale': scaler.scale_,
        'pca_components': pca.components_,
        'pca_mean': pca.mean_,
        'pca_explained_variance': pca.explained_variance_ratio_,
        'n_components': n_comp,
        'reg_coef': regressor.coef_,
        'reg_intercept': regressor.intercept_,
        'r_squared': r_squared,
        'rmse': rmse
    }


def train_pcr_for_point(out_values, target_values, n_components, sequence_length):
    """
    Train PCR model for a single point.
    
    Args:
        out_values: Sensor output values (time series)
        target_values: Target CFD values at each timestep
        n_components: Number of PCA components
        sequence_length: Length of input sequences
    
    Returns:
        dict: model parameters and metrics, or None if training fails
    """
    # Build sequences (cap sequence_length if fewer readings than default)
    sequence_length = min(sequence_length, len(out_values))
    X_sequences = []
    Y_targets = []
    for i in range(len(out_values) - sequence_length + 1):
        seq = out_values[i:i + sequence_length]
        target = target_values[i + sequence_length - 1]
        X_sequences.append(seq)
        Y_targets.append(target)
    
    if len(X_sequences) == 0:
        return None
    
    X = np.array(X_sequences)
    y = np.array(Y_targets)
    
    return train_pcr_sklearn(X, y, n_components)


def save_coefficients(result, sequence_length, output_file):
    """
    Save PCR coefficients to CSV file.
    
    Format compatible with prediction code.
    """
    flat_data = []
    flat_data.append(['scaler_mean'] + list(result['scaler_mean']))
    flat_data.append(['scaler_scale'] + list(result['scaler_scale']))
    flat_data.append(['pca_mean'] + list(result['pca_mean']))
    for i, comp in enumerate(result['pca_components']):
        flat_data.append([f'pca_component_{i}'] + list(comp))
    flat_data.append(['reg_coef'] + list(result['reg_coef']))
    flat_data.append(['reg_intercept', result['reg_intercept']])
    flat_data.append(['n_components', result['n_components']])
    flat_data.append(['sequence_length', sequence_length])
    flat_data.append(['r_squared', result['r_squared']])
    flat_data.append(['rmse', result['rmse']])
    
    # Pad rows to same length
    max_len = max(len(row) for row in flat_data)
    for row in flat_data:
        while len(row) < max_len:
            row.append('')
    
    out_df = pd.DataFrame(flat_data)
    out_df.to_csv(output_file, index=False, header=False)


def train_chunk(data_file, output_dir):
    """
    Train PCR models for all points in the chunk using sklearn.
    
    Provides detailed timing metrics for:
    - Data loading
    - Setup/initialization
    - Training (with per-point statistics)
    - Coefficient file saving
    """
    overall_start = time.time()
    ts = lambda: datetime.now().strftime('%H:%M:%S')
    
    print(f"[{ts()}] [INFO] train_pcr_chunk: Starting (sklearn mode)")
    
    # ==== TIMING: Initialization ====
    init_start = time.time()
    init_end = time.time()
    init_time = init_end - init_start
    
    # ==== TIMING: Data Loading ====
    load_start = time.time()
    
    file_size_mb = os.path.getsize(data_file) / (1024 * 1024)
    
    with open(data_file, 'rb') as f:
        data = pickle.load(f)
    
    load_end = time.time()
    load_time = load_end - load_start
    
    machine_id = data['machine_id']
    points = data['points']
    num_points = data['num_points']
    u_mag_lookups = data['u_mag_lookups']
    sensor_values = data['sensor_values']
    available_ws = data['available_ws']
    config = data['config']
    
    n_components = config['n_components']
    sequence_length = config['sequence_length']
    
    print(f"[{ts()}] [INFO]   Machine {machine_id}: {num_points} points, {len(sensor_values)} readings, {len(available_ws)} windspeeds")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Convert sensor values to numpy
    out_values = np.array(sensor_values)
    
    # Train PCR for each point
    train_start = time.time()
    
    successful = 0
    failed = 0
    point_times = []
    r_squared_values = []
    rmse_values = []
    
    for i, pt in enumerate(points):
        point_start = time.time()
        
        x, y, z = pt['x'], pt['y'], pt['z']
        key = f"{x}_{y}_{z}"
        xyz_name = f"{x}_{y}_{z}".replace('.', 'p')
        
        # Get pre-computed U_Magnitude lookup
        u_mag_lookup = u_mag_lookups[key]
        
        # Create target values by matching sensor values to simulations
        target_values = []
        for out_val in out_values:
            closest_ws = get_closest_ws(out_val, available_ws)
            target_values.append(u_mag_lookup[closest_ws])
        target_values = np.array(target_values)
        
        # Train PCR model using sklearn
        result = train_pcr_for_point(out_values, target_values, n_components, sequence_length)
        
        if result is not None:
            # Save coefficients
            output_file = os.path.join(output_dir, f'pcr_coefficients_{xyz_name}.csv')
            save_coefficients(result, sequence_length, output_file)
            successful += 1
            if result['r_squared'] is not None:
                r_squared_values.append(result['r_squared'])
            if result['rmse'] is not None:
                rmse_values.append(result['rmse'])
        else:
            failed += 1
        
        point_end = time.time()
        point_times.append(point_end - point_start)
        
        # Progress every 500 points or at completion
        progress_pct = (i + 1) / num_points * 100
        if (i + 1) % 500 == 0 or (i + 1) == num_points:
            avg_time = sum(point_times) / len(point_times)
            eta = avg_time * (num_points - i - 1)
            print(f"[{ts()}] [INFO]   Progress: {i+1}/{num_points} ({progress_pct:.0f}%) eta={format_duration(eta)}")
    
    train_end = time.time()
    train_elapsed = train_end - train_start
    
    # ==== TIMING: Final Summary ====
    overall_end = time.time()
    overall_elapsed = overall_end - overall_start
    
    # Compute stats
    avg_time = sum(point_times) / len(point_times) if point_times else 0
    throughput = num_points / overall_elapsed if overall_elapsed > 0 else 0
    avg_r2 = np.mean(r_squared_values) if r_squared_values else 0
    avg_rmse = np.mean(rmse_values) if rmse_values else 0
    
    print(f"[{ts()}] [INFO] train_pcr_chunk: Machine {machine_id} done - ok={successful} fail={failed} R²={avg_r2:.3f} RMSE={avg_rmse:.3f}")
    print(f"[{ts()}] [TIMER] init={init_time:.1f}s load={load_time:.1f}s train={train_elapsed:.1f}s total={overall_elapsed:.1f}s ({throughput:.1f} pts/s)")
    
    # Save detailed summary
    import json
    summary = {
        'machine_id': machine_id,
        'num_points': num_points,
        'successful': successful,
        'failed': failed,
        'timing': {
            'initialization_seconds': round(init_time, 3),
            'data_load_seconds': round(load_time, 3),
            'training_seconds': round(train_elapsed, 3),
            'total_seconds': round(overall_elapsed, 3)
        },
        'data_file_size_mb': round(file_size_mb, 2),
        'throughput_points_per_second': round(throughput, 2),
        'avg_time_per_point': round(avg_time, 4) if point_times else None,
        'avg_r_squared': float(np.mean(r_squared_values)) if r_squared_values else None,
        'avg_rmse': float(np.mean(rmse_values)) if rmse_values else None,
        'completed_at': datetime.now().isoformat()
    }
    
    summary_file = os.path.join(output_dir, 'training_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    return successful, failed


def main():
    parser = argparse.ArgumentParser(description='Train PCR models from pre-prepared chunk data')
    parser.add_argument('data_file', help='Path to machine_N_data.pkl file')
    parser.add_argument('output_dir', help='Output directory for coefficient files')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.data_file):
        print(f"Error: Data file not found: {args.data_file}")
        sys.exit(1)
    
    successful, failed = train_chunk(args.data_file, args.output_dir)
    
    if failed > 0:
        print(f"\nWarning: {failed} points failed to train")
        sys.exit(1 if successful == 0 else 0)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
