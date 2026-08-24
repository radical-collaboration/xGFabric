#!/usr/bin/env python3
"""
Load sensor data from a local historical CSV archive up to a cutoff date.

Reads all CSV files in HISTORICAL_DATA_PATH, filters to records whose 'dt'
timestamp is at or before the cutoff date, and writes the N most recent
matching records to an output CSV file in the same format as sensor_out.csv
(dt,windspeed,windavg,winddir).

Exit codes:
    0  – success, output file written
    1  – error (path not found, no matching data, bad arguments, etc.)
"""

import sys
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path


def log_info(msg):
    print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} {msg}")


def log_warn(msg):
    print(f"[WARN] {datetime.now().strftime('%H:%M:%S')} {msg}")


def log_error(msg):
    print(f"[ERROR] {datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr)


def parse_dt(dt_str):
    """Parse a datetime string to a UTC-aware datetime. Returns None on failure."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def load_csv_records(historical_path):
    """
    Read all CSV files under historical_path and return a list of
    (datetime, row_dict) tuples for rows that have a parseable 'dt' column.

    Preference: files containing 'cupsout' in their name (matching the CSPOT
    endpoint 'daviscupsout'). Falls back to all CSV files with a warning.
    """
    path = Path(historical_path)
    all_csvs = sorted(path.glob("**/*.csv"))

    preferred = [f for f in all_csvs if 'cupsout' in f.name.lower()]
    candidates = preferred if preferred else all_csvs

    if not candidates:
        log_error(f"No CSV files found in: {historical_path}")
        return []

    if not preferred and all_csvs:
        log_warn("No 'cupsout' CSV files found; reading all CSV files in archive")

    log_info(f"Reading {len(candidates)} CSV file(s) from historical archive")

    records = []
    for csv_file in candidates:
        try:
            with open(csv_file, newline='') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or 'dt' not in reader.fieldnames:
                    log_warn(f"Skipping {csv_file.name}: no 'dt' column")
                    continue
                for row in reader:
                    dt = parse_dt(row.get('dt', ''))
                    if dt is not None:
                        records.append((dt, row))
        except Exception as e:
            log_warn(f"Could not read {csv_file.name}: {e}")

    log_info(f"Loaded {len(records)} total records from historical archive")
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Load historical sensor CSV records at or before a cutoff date."
    )
    parser.add_argument("--data-dir", required=True,
                        help="Path to historical data directory (HISTORICAL_DATA_PATH)")
    parser.add_argument("--output-file", required=True,
                        help="Destination CSV file (sensor_out.csv)")
    parser.add_argument("--cutoff-date", required=True,
                        help="Cutoff date in ISO format; only records <= this date are used")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max number of records to return (default: 50)")
    args = parser.parse_args()

    # Parse cutoff
    try:
        cutoff = datetime.fromisoformat(args.cutoff_date.replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
    except ValueError:
        log_error(f"Invalid cutoff date: {args.cutoff_date}")
        sys.exit(1)

    log_info(f"Historical data path : {args.data_dir}")
    log_info(f"Cutoff date          : {cutoff}")
    log_info(f"Limit                : {args.limit} records")

    if not Path(args.data_dir).is_dir():
        log_error(f"Historical data directory not found: {args.data_dir}")
        sys.exit(1)

    # Load and filter
    records = load_csv_records(args.data_dir)
    before_cutoff = [(dt, row) for dt, row in records if dt <= cutoff]

    if not before_cutoff:
        log_error(f"No historical records found at or before cutoff: {cutoff}")
        log_error(f"The archive may not cover this time period.")
        sys.exit(1)

    # N most recent at or before cutoff, then sort ascending for output
    before_cutoff.sort(key=lambda x: x[0], reverse=True)
    selected = before_cutoff[:args.limit]
    selected.sort(key=lambda x: x[0])

    log_info(f"Selected {len(selected)} record(s) from archive")
    log_info(f"  Date range: {selected[0][0].isoformat()} → {selected[-1][0].isoformat()}")

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sample_row = selected[0][1]
    cols = list(sample_row.keys())

    # Detect format:
    #   "parsed"  - simplified column names (dt,windspeed,windavg,winddir)
    #   "davis"   - raw Davis station export (rtWindSpeed,rtWindAvgSpeed,rtWindDir)
    #               as found in cups_historical/ CSVs on pscratch
    #   "raw"     - raw CSPOT archive with a single packed 'data' field
    has_parsed = all(c in cols for c in ('windspeed', 'windavg', 'winddir'))
    has_davis  = all(c in cols for c in ('rtWindSpeed', 'rtWindAvgSpeed', 'rtWindDir'))
    has_raw    = 'data' in cols

    if not has_parsed and not has_davis and not has_raw:
        log_error(f"Historical CSV has unrecognised columns: {cols}")
        log_error(f"Expected one of:")
        log_error(f"  (dt,windspeed,windavg,winddir)          - pre-parsed")
        log_error(f"  (dt,rtWindSpeed,rtWindAvgSpeed,rtWindDir) - Davis station raw")
        log_error(f"  (seqno,dt,ip,data)                      - CSPOT raw")
        sys.exit(1)

    if has_davis:
        log_info("Detected Davis station column format (rtWindSpeed/rtWindAvgSpeed/rtWindDir)")
    elif has_raw:
        log_info("Detected raw CSPOT data field format")
    else:
        log_info("Detected pre-parsed windspeed/windavg/winddir format")

    with open(output_path, 'w', newline='') as f:
        f.write('dt,windspeed_ms,windavg_ms,winddir\n')
        written = 0
        for _, row in selected:
            if has_parsed:
                windspeed = float(row['windspeed']) * 0.44704  # mph -> m/s
                windavg   = float(row['windavg'])   * 0.44704
                f.write(f"{row['dt']},{windspeed},{windavg},{row['winddir']}\n")
                written += 1
            elif has_davis:
                # Davis station raw export: mph -> m/s
                try:
                    windspeed = float(row['rtWindSpeed'])    * 0.44704
                    windavg   = float(row['rtWindAvgSpeed']) * 0.44704
                    winddir   = float(row['rtWindDir'])
                    f.write(f"{row['dt']},{windspeed},{windavg},{winddir}\n")
                    written += 1
                except (ValueError, KeyError):
                    continue
            else:
                # Raw CSPOT format: parse data field (fields[3]=windspeed, [4]=windavg, [5]=winddir)
                try:
                    fields = row['data'].split(':')
                    if len(fields) < 6:
                        continue
                    windspeed = float(fields[3]) * 0.44704  # mph -> m/s
                    windavg   = float(fields[4]) * 0.44704
                    winddir   = float(fields[5])
                    f.write(f"{row['dt']},{windspeed},{windavg},{winddir}\n")
                    written += 1
                except (ValueError, IndexError):
                    continue

    log_info(f"Wrote {written} records to: {args.output_file}")


if __name__ == "__main__":
    main()
