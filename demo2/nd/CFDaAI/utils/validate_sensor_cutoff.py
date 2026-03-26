#!/usr/bin/env python3
"""
Validate that sensor data timestamps are consistent with a given cutoff date.
Logs the sensor time range and warns if any records are dated AFTER the cutoff
(all records should be at or before the cutoff when using historical data).

Usage: validate_sensor_cutoff.py <sensor_csv> <cutoff_date>
"""
import sys
from datetime import datetime

ts = lambda: datetime.now().strftime('%H:%M:%S')


def main():
    if len(sys.argv) < 3:
        print(f"[ERROR] {ts()} Usage: validate_sensor_cutoff.py <sensor_csv> <cutoff_date>",
              file=sys.stderr)
        sys.exit(1)

    sensor_file = sys.argv[1]
    cutoff_str  = sys.argv[2]

    try:
        import pandas as pd
        df = pd.read_csv(sensor_file)
        if 'dt' not in df.columns:
            print(f"[INFO] {ts()} Sensor file has no 'dt' column - skipping cutoff check")
            sys.exit(0)
        df['dt'] = pd.to_datetime(df['dt'], utc=True, errors='coerce')
        df = df.dropna(subset=['dt'])
        if df.empty:
            print(f"[WARN] {ts()} Sensor file parsed but all timestamps invalid - skipping cutoff check",
                  file=sys.stderr)
            sys.exit(0)
        cutoff = pd.Timestamp(cutoff_str.replace('Z', '+00:00'))
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize('UTC')
        data_min = df['dt'].min()
        data_max = df['dt'].max()
        print(f"[INFO] {ts()} Sensor data time range: {data_min} to {data_max}")
        print(f"[INFO] {ts()} Data cutoff used: {cutoff}")
        after = (df['dt'] > cutoff).sum()
        if after > 0:
            print(f"[WARN] {ts()} {after}/{len(df)} sensor records are AFTER cutoff {cutoff} "
                  f"— data contains records beyond the intended cutoff",
                  file=sys.stderr)
        else:
            print(f"[INFO] {ts()} All {len(df)} sensor records are at or before cutoff — OK")

        # Staleness check: warn/error if most recent record is far before cutoff
        gap = cutoff - data_max
        gap_hours = gap.total_seconds() / 3600
        if gap_hours > 24:
            print(f"[ERROR] {ts()} Most recent sensor record is {gap_hours:.1f}h before cutoff "
                  f"({data_max} vs {cutoff}) — data appears stale",
                  file=sys.stderr)
            sys.exit(1)
        elif gap_hours > 2:
            print(f"[WARN] {ts()} Most recent sensor record is {gap_hours:.1f}h before cutoff "
                  f"({data_max} vs {cutoff}) — possible data gap",
                  file=sys.stderr)
    except Exception as e:
        print(f"[WARN] {ts()} Could not validate sensor data against cutoff: {e}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
