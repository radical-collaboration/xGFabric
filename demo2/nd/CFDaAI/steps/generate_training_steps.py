#!/usr/bin/env python3
"""
generate_training_steps.py - Build training steps from historical sensor data.

Reads davis_cupsout_north.csv (the davisstations/daviscupsout station used by
the pipeline), sorts all records by timestamp, then chunks them into non-overlapping
windows of exactly 24 records each.

For each step the pipeline will:
  - Set DATA_CUTOFF_DATE = cutoff_date  (24th record's timestamp)
  - Set CSPOT_LIMIT = 24
  - Set HISTORICAL_DATA_PATH so the fallback reader can find the archived CSVs
  (live CSPOT won't have data from 2021-2023, so it always falls back)

Output: steps/training_steps.csv
  step_id     : zero-padded integer (00001 …)
  start_date  : ISO timestamp of first record in window
  cutoff_date : ISO timestamp of last (24th) record in window
  n_records   : always 24 (last chunk may be smaller and is dropped)
  status      : pending / running / done / error
  archive_path: filled in by run_training_steps.sh after each step completes

Usage:
    python3 generate_training_steps.py [--data-dir PATH] [--out PATH]
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

DEFAULT_DATA_DIR = "/local/home/liubov_kurafeeva/storage/cups_historical"
DEFAULT_SENSOR_FILE = "davis_cupsout_north.csv"
CHUNK_SIZE = 24


def load_timestamps(data_dir: str, filename: str) -> list[str]:
    """Return sorted list of unique ISO datetime strings from the sensor CSV."""
    filepath = os.path.join(data_dir, filename)
    if not os.path.exists(filepath):
        sys.exit(f"ERROR: sensor file not found: {filepath}")

    seen = set()
    rows = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        if "dt" not in reader.fieldnames:
            sys.exit(f"ERROR: no 'dt' column in {filepath}")
        for row in reader:
            dt_str = row["dt"].strip()
            if dt_str and dt_str not in seen:
                seen.add(dt_str)
                rows.append(dt_str)

    rows.sort()
    return rows


def to_iso(dt_str: str) -> str:
    """Normalise a raw timestamp string to a clean ISO-8601 string (no TZ = UTC assumed)."""
    # Timestamps look like "2021-06-15 06:21:06.727162" — strip microseconds for readability
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return dt_str  # keep as-is if parsing fails


def build_steps(timestamps: list[str]) -> list[dict]:
    steps = []
    total = len(timestamps)
    step_id = 1
    i = 0
    while i + CHUNK_SIZE <= total:
        chunk = timestamps[i : i + CHUNK_SIZE]
        steps.append(
            {
                "step_id": f"{step_id:05d}",
                "start_date": to_iso(chunk[0]),
                "cutoff_date": to_iso(chunk[-1]),
                "n_records": len(chunk),
                "status": "pending",
                "archive_path": "",
            }
        )
        step_id += 1
        i += CHUNK_SIZE

    # Last partial chunk (if any) is skipped — need exactly 24 for reliable training
    remaining = total - i
    if remaining > 0:
        print(
            f"Note: {remaining} trailing records (< {CHUNK_SIZE}) dropped — not enough for a full step."
        )

    return steps


def write_steps(steps: list[dict], out_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fieldnames = ["step_id", "start_date", "cutoff_date", "n_records", "status", "archive_path"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(steps)
    print(f"Wrote {len(steps)} steps to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate training steps from historical sensor data")
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing historical CSV files (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--sensor-file",
        default=DEFAULT_SENSOR_FILE,
        help=f"Sensor CSV filename inside data-dir (default: {DEFAULT_SENSOR_FILE})",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "training_steps.csv"),
        help="Output CSV path (default: steps/training_steps.csv)",
    )
    args = parser.parse_args()

    print(f"Loading timestamps from {os.path.join(args.data_dir, args.sensor_file)} ...")
    timestamps = load_timestamps(args.data_dir, args.sensor_file)
    print(f"  {len(timestamps)} unique records, {args.sensor_file[:30]}")
    print(f"  Range: {to_iso(timestamps[0])}  →  {to_iso(timestamps[-1])}")

    steps = build_steps(timestamps)
    print(f"  {len(steps)} steps of {CHUNK_SIZE} records each")

    write_steps(steps, args.out)


if __name__ == "__main__":
    main()
