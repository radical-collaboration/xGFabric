import json

import logging
import os
import re

import numpy as np

x_min, x_max = 8.3, 176.5  # Based on the CFD domain bounds
xn = 85
y_min, y_max = 8.1, 82.1  # Based on the CFD domain bounds
yn = 38
z_min, z_max = 0.5, 5.0  # 0.5m from ground, 0.5m from roof (5.5m structure height)
z_partitions = [1, 3, 5, 7]


def parse_filename(filename):
    """
    Parse pcr_coefficients_X_Y_Z.csv filename to extract coordinates.
    Format: pcr_coefficients_000p09_10p65_0p5.csv
    """
    match = re.match(r"pcr_coefficients_(.+)_(.+)_(.+)\.csv", filename)
    if not match:
        return None

    def parse_coord(s):
        # Replace 'p' with '.', 'm' with '-'
        s = s.replace("p", ".").replace("m", "-")
        return float(s)

    try:
        x = parse_coord(match.group(1))
        y = parse_coord(match.group(2))
        z = parse_coord(match.group(3))
        return x, y, z
    except:
        return None


# Process args for a point
def parse_coeff(filename):
    properties = {}
    counter = 0
    out = np.zeros((13,))
    with open(filename, "r") as f:
        line = f.readline()
        if line != "# PCR Coefficients (from pcr binary)\n":
            f.close()
            return None, None
        line = f.readline()
        while line != "":
            if line[0] == "#":
                tokens = line[2:].split(": ")
                properties[tokens[0]] = float(tokens[1])
                line = f.readline()
                continue
            tokens = line.split(",")
            value = tokens[1]
            try:
                out[counter] = value
            except:
                print("ERROR PROCESSING")
                print(filename)
                print(counter)
            counter += 1
            line = f.readline()
    return out, properties


def prepare(pcr_dir, logger: logging.Logger):
    # Find all coefficient files
    coef_files = [
        f
        for f in os.listdir(pcr_dir)
        if f.startswith("pcr_coefficients_") and f.endswith(".csv")
    ]
    logger.info(f"Found {len(coef_files)} coefficient files")

    # Parse all files
    out = np.zeros((xn + 1, yn + 1, len(z_partitions), 13))

    counter = 0
    for filename in coef_files:
        coords = parse_filename(filename)
        coeff, properties = parse_coeff(pcr_dir + "/" + filename)
        if coeff is None:
            continue
        if coords:
            x, y, z = coords
            if z not in z_partitions:
                continue
            # convert coordinates to 0
            x_index = int(((x - x_min) / (x_max - x_min)) * xn)
            y_index = int(((y - y_min) / (y_max - y_min)) * yn)
            z_index = z_partitions.index(z)
            out[x_index, y_index, z_index, :] = coeff
            counter += 1

    logger.info(f"Successfully parsed {counter} files")

    # Create DataFrame and sort
    return out


def get_bounding_points(df, x_bound, y_bound, z_bound, x_len, y_len, z_len):
    # Ref point of 0,0,0
    return df[
        x_bound : x_bound + x_len, y_bound : y_bound + y_len, z_bound : z_bound + z_len
    ]


def predict_all(df, wind):
    wind[0] = 1
    out = np.tensordot(df, wind, axes=([3], [0]))
    return out


def predict_at_z(df, wind, z):
    z_index = z_partitions.index(z)
    query = get_bounding_points(df, 0, 0, z_index, xn, yn, 1)
    wind[0] = 1

    return np.tensordot(query, wind, axes=([3], [0]))[:, :, 0].T
