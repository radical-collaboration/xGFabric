#!/usr/bin/env python3
"""
Compute basic statistics from a sensor CSV and save sensor_metrics.json.

Usage: compute_sensor_metrics.py <sensor_file> <output_dir>
"""
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

ts = lambda: datetime.now().strftime('%H:%M:%S')


def main():
    if len(sys.argv) < 3:
        print(f"[ERROR] {ts()} Usage: compute_sensor_metrics.py <sensor_file> <output_dir>",
              file=sys.stderr)
        sys.exit(1)

    sensor_file = sys.argv[1]
    output_dir  = Path(sys.argv[2])

    try:
        df = pd.read_csv(sensor_file)

        wind_cols = [c for c in df.columns if 'wind' in c.lower()]

        metrics = {
            'sensor_file': sensor_file,
            'n_records': len(df),
            'time_range': {
                'start': df['dt'].min() if 'dt' in df.columns else None,
                'end':   df['dt'].max() if 'dt' in df.columns else None,
            },
            'wind_metrics': {},
        }

        for col in wind_cols:
            if df[col].dtype in [np.float64, np.int64]:
                metrics['wind_metrics'][col] = {
                    'mean':   float(df[col].mean()),
                    'std':    float(df[col].std()),
                    'min':    float(df[col].min()),
                    'max':    float(df[col].max()),
                    'median': float(df[col].median()),
                }

        metrics_file = output_dir / 'sensor_metrics.json'
        with open(metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)

        print(f"[INFO] {ts()} Metrics saved to: {metrics_file}")
        print(f"[INFO] {ts()} Wind data stats:")
        for col, stats in metrics['wind_metrics'].items():
            print(f"[INFO] {ts()}   {col}: mean={stats['mean']:.2f}, std={stats['std']:.2f}, "
                  f"range=[{stats['min']:.2f}, {stats['max']:.2f}]")

    except Exception as e:
        print(f"[ERROR] {ts()} Failed to compute metrics: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
