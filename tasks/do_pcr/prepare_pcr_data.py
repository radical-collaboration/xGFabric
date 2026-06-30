#!/usr/bin/env python3
"""
Prepare PCR training data for distributed processing.

This script pre-processes sensor data and CFD simulation results to create
compact data files for each machine's chunk of grid points. Instead of
deploying all CFD CSVs to every machine, this creates a single pickle file
per machine containing only the data needed for its assigned points.

OPTIMIZED ALGORITHM:
- Load each CFD simulation CSV once
- Build KD-Tree spatial index for O(log n) nearest-neighbor queries
- Query ALL grid points at once per simulation (vectorized)
- Process all machines in memory after single data extraction pass

Usage:
    python prepare_pcr_data.py <sensor_folder> <simulations_folder> <partitions_file> <output_dir>

Arguments:
    sensor_folder: Path to folder containing sensor_out.csv
    simulations_folder: Path to folder containing simulation CSVs
    partitions_file: Path to pcr_partitions_full.json from partition_pcr_grid.py
    output_dir: Directory to save machine-specific data files

Output:
    Creates machine_N_data.pkl for each machine with pre-computed:
    - Grid points for this machine
    - U_Magnitude lookup table for each point (windspeed -> value)
    - Sensor time series data
"""

import argparse
import json
import os
import pickle
import re
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from tqdm import tqdm

# Default proximity radius for averaging CFD data around each grid point
# Will be overridden by value from pcr_partitions.json if available
DEFAULT_AVERAGING_RADIUS = 1.5  # meters


def format_duration(seconds):
    """Format duration in seconds to human-readable string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"


def extract_u_magnitude_for_all_points_kdtree(
    sim_file, grid_points, averaging_radius=DEFAULT_AVERAGING_RADIUS
):
    """
    Extract U_Magnitude for ALL grid points from a single simulation file using KD-Tree.

    This is MUCH faster than the naive approach because:
    1. KD-Tree query is O(log n) instead of O(n) for each point
    2. We process all grid points in a single pass per simulation
    3. Vectorized distance calculations within radius

    Args:
        sim_file: Path to simulation CSV
        grid_points: numpy array of shape (N, 3) with [x, y, z] coordinates
        averaging_radius: Radius for averaging nearby CFD points

    Returns:
        numpy array of U_Magnitude values for each grid point
    """
    # Load simulation data
    df = pd.read_csv(sim_file)

    # Extract CFD mesh coordinates and values
    cfd_coords = df[["x", "y", "z"]].values
    cfd_u_mag = df["U_Magnitude"].values

    # Build KD-Tree for CFD mesh (done once per simulation)
    tree = cKDTree(cfd_coords)

    n_points = len(grid_points)
    result = np.zeros(n_points)

    # Query all points within radius (ball query)
    # This returns list of indices for each query point
    indices_list = tree.query_ball_point(grid_points, r=averaging_radius)

    for i, indices in enumerate(indices_list):
        if len(indices) > 0:
            # Average U_Magnitude of points within radius
            result[i] = cfd_u_mag[indices].mean()
        else:
            # Fallback: find single nearest neighbor
            _, nearest_idx = tree.query(grid_points[i], k=1)
            result[i] = cfd_u_mag[nearest_idx]

    return result


def prepare_machine_data(
    sensor_data: pd.DataFrame,
    sim_data,
    full_partitions_data,
    output_dir,
    n_components=12,
    sequence_length=12,
):
    """
    Prepare pre-processed data files for each machine.

    OPTIMIZED: Instead of loading all simulations into memory and then querying
    each point individually, we:
    1. Collect ALL unique grid points from ALL partitions
    2. For each simulation file, load once and extract U_Magnitude for ALL points
    3. Then distribute results to machine-specific files

    Creates a pickle file for each machine containing:
    - points: List of grid points (x, y, z) to train
    - u_mag_lookups: Dict mapping point coords -> windspeed -> U_Magnitude
    - sensor_values: The sensor time series values
    - available_ws: List of available wind speeds
    - config: Training configuration (n_components, sequence_length, etc.)
    """
    overall_start = time.time()
    ts = lambda: datetime.now().strftime("%H:%M:%S")

    print(f"[{ts()}] [INFO] prepare_pcr_data: Starting (KD-Tree optimized)")

    os.makedirs(output_dir, exist_ok=True)

    num_machines = full_partitions_data["num_machines"]
    total_points = full_partitions_data["grid"]["total_points"]
    partitions = full_partitions_data["partitions"]
    nx, ny, nz = (
        full_partitions_data["grid"]["nx"],
        full_partitions_data["grid"]["ny"],
        full_partitions_data["grid"]["nz"],
    )
    averaging_radius = full_partitions_data["grid"].get(
        "averaging_radius", DEFAULT_AVERAGING_RADIUS
    )

    print(
        f"[{ts()}] [INFO]   Grid: {nx}x{ny}x{nz}={total_points}pts, {num_machines} machines, radius={averaging_radius}m"
    )

    # Collect ALL unique grid points from ALL partitions
    all_points_lst = []
    point_to_idx = {}  # Map "x_y_z" -> index in all_points array

    for partition in partitions:
        for pt in partition["points"]:
            key = f"{pt['x']}_{pt['y']}_{pt['z']}"
            if key not in point_to_idx:
                point_to_idx[key] = len(all_points_lst)
                all_points_lst.append([pt["x"], pt["y"], pt["z"]])

    all_points = np.array(all_points_lst)

    # Load sensor data
    sensor_data = sensor_data.sort_values(by="dt")
    sensor_data["wind_speed"] = sensor_data["wind_speed"].round()
    sensor_values = sensor_data["wind_speed"].values.tolist()

    print(f"[{ts()}] [INFO]   Loaded {len(sensor_data)} sensor readings")

    # Dictionary to store U_Magnitude for each windspeed
    u_mag_by_ws = {}
    available_ws = []

    sim_start = time.time()
    for ws, sim_file in sim_data:
        available_ws.append(ws)

        u_mag_values = extract_u_magnitude_for_all_points_kdtree(
            sim_file, all_points, averaging_radius=averaging_radius
        )
        u_mag_by_ws[ws] = u_mag_values

    available_ws = sorted(available_ws)
    sim_end = time.time()

    print(
        f"[{ts()}] [INFO]   Processed {len(available_ws)} sims in {format_duration(sim_end - sim_start)}, ws={available_ws}"
    )

    # Create machine-specific data files
    machine_data_outputs = []

    for partition in tqdm(partitions, desc="Creating machine files", unit="machine"):
        machine_id = partition["machine_id"]
        points = partition["points"]
        num_points = partition["num_points"]

        # Build U_Magnitude lookup for this machine's points
        u_mag_lookups = {}

        for pt in points:
            key = f"{pt['x']}_{pt['y']}_{pt['z']}"
            idx = point_to_idx[key]

            # Create windspeed -> U_Magnitude mapping
            u_mag_lookups[key] = {
                ws: float(u_mag_by_ws[ws][idx]) for ws in available_ws
            }

        # Create machine data package
        machine_data = {
            "machine_id": machine_id,
            "points": points,
            "num_points": num_points,
            "u_mag_lookups": u_mag_lookups,
            "sensor_values": sensor_values,
            "available_ws": available_ws,
            "config": {
                "column": "wind_speed",
                "n_components": n_components,
                "sequence_length": sequence_length,
            },
        }
        machine_data_outputs.append(machine_data)
    overall_end = time.time()

    return machine_data_outputs
