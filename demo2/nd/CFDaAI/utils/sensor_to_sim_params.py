#!/usr/bin/env python3
"""
Generate simulation parameter CSV from sensor data (direct mode).
Extracts unique wind speed / direction pairs from the sensor CSV,
limits to max_sims rows, and saves the result.

Usage: sensor_to_sim_params.py <sensor_csv> <output_file> <max_sims>
"""
import sys
import pandas as pd
import numpy as np
from datetime import datetime

ts = lambda: datetime.now().strftime('%H:%M:%S')


def main():
    if len(sys.argv) < 4:
        print(f"[ERROR] {ts()} Usage: sensor_to_sim_params.py <sensor_csv> <output_file> <max_sims>",
              file=sys.stderr)
        sys.exit(1)

    sensor_file = sys.argv[1]
    output_file = sys.argv[2]
    max_sims    = int(sys.argv[3])

    try:
        df = pd.read_csv(sensor_file)

        ws_col = None
        wd_col = None
        for col in df.columns:
            col_lower = col.lower()
            if 'windspeed' in col_lower or 'wind_speed' in col_lower:
                ws_col = col
            elif 'windavg' in col_lower and ws_col is None:
                ws_col = col
            elif 'winddir' in col_lower or 'wind_dir' in col_lower:
                wd_col = col

        if ws_col is None:
            print(f"[ERROR] {ts()} Could not find wind speed column in {sensor_file}",
                  file=sys.stderr)
            sys.exit(1)

        wind_speeds = pd.to_numeric(df[ws_col], errors='coerce').dropna()

        if wd_col:
            wind_dirs = pd.to_numeric(df[wd_col], errors='coerce').fillna(0)
        else:
            print(f"[WARN] {ts()} Wind direction column not found, using 0° for all",
                  file=sys.stderr)
            wind_dirs = pd.Series([0] * len(wind_speeds))

        params_df = pd.DataFrame({'wind_speed': wind_speeds, 'wind_dir': wind_dirs})
        params_df['wind_speed'] = params_df['wind_speed'].round(1)
        params_df['wind_dir']   = params_df['wind_dir'].round(0)

        if len(params_df) > max_sims:
            indices   = np.linspace(0, len(params_df) - 1, max_sims, dtype=int)
            params_df = params_df.iloc[indices]

        params_df.to_csv(output_file, index=False)

        print(f"[INFO] {ts()} Generated {len(params_df)} simulation parameter sets",
              file=sys.stderr)
        print(f"[INFO] {ts()} Wind speed range: "
              f"{params_df['wind_speed'].min():.1f} - {params_df['wind_speed'].max():.1f} m/s",
              file=sys.stderr)
        if wd_col:
            unique_dirs = params_df['wind_dir'].nunique()
            print(f"[INFO] {ts()} Wind directions: {unique_dirs} unique values", file=sys.stderr)

    except Exception as e:
        print(f"[ERROR] {ts()} Failed to generate parameters: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
