#!/usr/bin/env python3
"""
Extract wind speed range (min/max in m/s) from a sensor CSV.
Prints "ws_min,ws_max" to stdout, e.g. "3.2,12.5".

Usage: compute_wind_stats.py <sensor_csv>
Exit code 1 on failure (caller should fall back to a default range).
"""
import sys
import pandas as pd


def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    sensor_csv = sys.argv[1]
    df = pd.read_csv(sensor_csv)
    col = 'windspeed_ms' if 'windspeed_ms' in df.columns else ('windspeed' if 'windspeed' in df.columns else df.columns[1])
    vals = pd.to_numeric(df[col], errors='coerce').dropna()
    print(f'{max(2.0, vals.min()):.1f},{vals.max():.1f}')


if __name__ == "__main__":
    main()
