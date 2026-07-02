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
import numpy as np
import logging

logger = logging.getLogger(__name__)


def load_grid_config(path_to_config):

    if path_to_config is not None and os.path.isfile(path_to_config):
        with open(path_to_config) as f:
            data = json.load(f)
        return data
    logger.warning(f"grid_config.json not found in any search path, using defaults")
    return {
        "boundaries": {
            "x_min": 8.3,
            "x_max": 176.5,
            "y_min": 8.1,
            "y_max": 82.1,
            "z_min": 1.0,
            "z_max": 7.0,
        },
        "grid": {"nx": 85, "ny": 38, "nz": 4},
        "cfd_averaging": {"radius": 1.5},
    }


class PCR_Partition_Grid:
    def __init__(self, path_to_config):
        # Load configuration
        CONFIG = load_grid_config(path_to_config)
        self.X_MIN, self.X_MAX = (
            CONFIG["boundaries"]["x_min"],
            CONFIG["boundaries"]["x_max"],
        )
        self.Y_MIN, self.Y_MAX = (
            CONFIG["boundaries"]["y_min"],
            CONFIG["boundaries"]["y_max"],
        )
        self.Z_MIN, self.Z_MAX = (
            CONFIG["boundaries"]["z_min"],
            CONFIG["boundaries"]["z_max"],
        )
        self.DEFAULT_NX = CONFIG["grid"]["nx"]
        self.DEFAULT_NY = CONFIG["grid"]["ny"]
        self.DEFAULT_NZ = CONFIG["grid"]["nz"]
        self.AVERAGING_RADIUS = CONFIG["cfd_averaging"]["radius"]

    def create_grid(self, nx, ny, nz):
        """Create grid of points in 3D space and return as list of (x, y, z, flat_idx)."""
        x_points = np.linspace(self.X_MIN, self.X_MAX, nx)
        y_points = np.linspace(self.Y_MIN, self.Y_MAX, ny)
        z_points = (
            np.linspace(self.Z_MIN, self.Z_MAX, nz)
            if nz > 1
            else np.array([self.Z_MIN])
        )

        grid_points = []
        flat_idx = 0
        for xi, x in enumerate(x_points):
            for yi, y in enumerate(y_points):
                for zi, z in enumerate(z_points):
                    grid_points.append(
                        {
                            "x": round(float(x), 2),
                            "y": round(float(y), 2),
                            "z": round(float(z), 2),
                            "xi": xi,
                            "yi": yi,
                            "zi": zi,
                            "flat_idx": flat_idx,
                        }
                    )
                    flat_idx += 1

        return grid_points

    def partition_grid_equally(self, num_machines, nx=None, ny=None, nz=None):
        """
        Partition 3D grid into equal-sized chunks for different machines.

        Strategy: Flatten the grid to 1D and divide evenly among machines.
        This ensures each machine gets approximately the same number of points.

        Returns:
            dict: Partition information including grid points for each machine
        """
        if nx is None:
            nx = self.DEFAULT_NX
        if ny is None:
            ny = self.DEFAULT_NY
        if nz is None:
            nz = self.DEFAULT_NZ

        total_points = nx * ny * nz

        # Create full grid
        grid_points = self.create_grid(nx, ny, nz)

        # Calculate chunk sizes (distribute remainder across first machines)
        base_chunk_size = total_points // num_machines
        remainder = total_points % num_machines

        logger.info(
            f"partition_pcr_grid: {nx}x{ny}x{nz}={total_points}pts -> {num_machines} machines ({base_chunk_size}+{remainder}r pts/machine)"
        )

        partitions = []
        partitions_no_points = []
        current_idx = 0

        for m in range(num_machines):
            # Calculate this machine's chunk size
            chunk_size = base_chunk_size + (1 if m < remainder else 0)

            if chunk_size == 0:
                logger.warning(f"Machine {m}: no points (too many machines)")
                continue

            # Get the points for this machine
            start_idx = current_idx
            end_idx = current_idx + chunk_size
            machine_points = grid_points[start_idx:end_idx]

            pct = (chunk_size / total_points) * 100

            partition = {
                "machine_id": m,
                "start_idx": start_idx,
                "end_idx": end_idx,
                "num_points": chunk_size,
                "pct_of_total": round(pct, 2),
                "points": machine_points,  # Full point info for data preparation
            }
            partition_no_points = {
                "machine_id": m,
                "start_idx": start_idx,
                "end_idx": end_idx,
                "num_points": chunk_size,
                "pct_of_total": round(pct, 2),
                "points": machine_points,  # Full point info for data preparation
            }
            partitions.append(partition)
            partitions_no_points.append(partition_no_points)

            current_idx = end_idx

        out = {
            "grid": {
                "nx": nx,
                "ny": ny,
                "nz": nz,
                "total_points": total_points,
                "x_range": [self.X_MIN, self.X_MAX],
                "y_range": [self.Y_MIN, self.Y_MAX],
                "z_range": [self.Z_MIN, self.Z_MAX],
                "averaging_radius": self.AVERAGING_RADIUS,
            },
            "num_machines": num_machines,
            "partitions": partitions,
        }

        out_no_points = {"grid": out["grid"], "num_machines": num_machines}
        out_no_points["partitions"] = partitions_no_points

        return out_no_points, out
