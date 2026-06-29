#!/usr/bin/env python3
"""
Load historical data from CSPOT with date range filtering.
Fetches data from a specified cutoff date and saves to multiple files.
"""

import subprocess
import sys
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

def log_info(msg):
    from datetime import datetime
    print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} {msg}")

def log_error(msg):
    from datetime import datetime
    print(f"[ERROR] {datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr)

def log_warn(msg):
    from datetime import datetime
    print(f"[WARN] {datetime.now().strftime('%H:%M:%S')} {msg}")

def run_command(cmd):
    """Execute a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Command failed: {cmd}\nError: {e.stderr}")

def find_senspot_get():
    """
    Find senspot-get binary in various locations.
    
    Search order:
    1. SENSPOT_PATH environment variable
    2. PATH (command -v senspot-get)
    3. ~/common/cspot/build/bin/senspot-get (NERSC user build)
    4. /global/common/software/m5290/cspot/build/bin/senspot-get (NERSC shared)
    5. ~/bin/senspot-get (UCSB default)
    
    Returns:
        Path to senspot-get binary or raises FileNotFoundError
    """
    import shutil
    
    # Check environment variable first
    if os.environ.get('SENSPOT_PATH'):
        path = os.environ['SENSPOT_PATH']
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    
    # Check if in PATH
    which_path = shutil.which('senspot-get')
    if which_path:
        return which_path
    
    # Check known locations
    home = os.path.expanduser('~')
    candidates = [
        f"{home}/common/cspot/build/bin/senspot-get",  # NERSC user build
        "/global/common/software/m5290/cspot/build/bin/senspot-get",  # NERSC shared
        f"{home}/bin/senspot-get",  # UCSB default
    ]
    
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    
    raise FileNotFoundError(
        f"senspot-get not found. Checked: {', '.join(candidates)}\n"
        "Set SENSPOT_PATH environment variable or install CSPOT."
    )

def fetch_data_from_woof(woof_url, seq_no=None):
    """
    Fetch data from CSPOT using senspot-get.
    
    Args:
        woof_url: The WOOF URL to fetch from
        seq_no: Optional sequence number to fetch specific entry
    
    Returns:
        Tuple of (data_string, timestamp_unix, seq_no)
    """
    senspot_path = find_senspot_get()
    cmd = f"{senspot_path} -W {woof_url}"
    if seq_no:
        cmd += f" -S {seq_no}"
    
    try:
        output = run_command(cmd)
        
        # Parse the output format:
        # data_fields... time: 1765234540.8291339874 10.10.4.34 seq_no: 531141
        match = re.search(r'time:\s+([\d.]+)\s+[\d.]+\s+seq_no:\s+(\d+)', output)
        if match:
            timestamp_unix = float(match.group(1))
            actual_seq_no = int(match.group(2))
            return output, timestamp_unix, actual_seq_no
        else:
            return output, None, None
            
    except Exception as e:
        raise e

def unix_to_datetime(unix_timestamp):
    """Convert Unix timestamp to datetime"""
    return datetime.fromtimestamp(unix_timestamp, timezone.utc)

def binary_search_cutoff_seq(woof_url, cutoff_date, latest_seq_no):
    """
    Binary search the CSPOT sequence-number space to find the highest seq_no
    whose timestamp is <= cutoff_date.  O(log N) network requests.

    Returns:
        int: the best seq_no found, or None if ALL records in CSPOT are after cutoff_date
    """
    lo, hi = 0, latest_seq_no
    best = None
    consecutive_failures = 0

    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            _, timestamp_unix, _ = fetch_data_from_woof(woof_url, seq_no=mid)
            consecutive_failures = 0
            if timestamp_unix is None:
                lo = mid + 1
                continue
            mid_time = unix_to_datetime(timestamp_unix)
            if mid_time <= cutoff_date:
                best = mid       # mid is a valid candidate; try higher seq_nos
                lo = mid + 1
            else:
                hi = mid - 1    # mid is after cutoff; search lower
        except Exception:
            consecutive_failures += 1
            if consecutive_failures >= 10:
                log_warn(f"Binary search: {consecutive_failures} consecutive failures near seq {mid}, aborting early")
                break
            hi = mid - 1        # treat failure as "too new", look earlier

    return best


def load_data_at_or_before_cutoff(woof_url, cutoff_date, output_dir="./data", limit=50):
    """
    Fetch up to `limit` records from CSPOT that are AT OR BEFORE cutoff_date.

    Uses a binary search to locate the correct region of the sequence-number
    space before walking backwards — O(log N + limit) network requests rather
    than O(N).

    Exit codes:
        0  – success, data written to sensor_data.txt
        2  – CSPOT has no records at or before cutoff_date (caller should fall
             back to a local historical archive)
    """
    now = datetime.now()
    run_name = now.strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"run_{run_name}"
    output_path.mkdir(parents=True, exist_ok=True)

    log_info(f"Loading CSPOT data AT OR BEFORE cutoff: {cutoff_date}")
    log_info(f"Run directory: {output_path}")
    log_info(f"Fetching up to {limit} records")

    # Get latest seq_no
    try:
        _, timestamp_unix, latest_seq_no = fetch_data_from_woof(woof_url)
        if not latest_seq_no:
            log_error("Could not get latest sequence number from CSPOT")
            sys.exit(1)
        latest_time = unix_to_datetime(timestamp_unix)
        log_info(f"Latest CSPOT record: seq_no={latest_seq_no}, time={latest_time}")
    except Exception as e:
        log_error(f"Failed to reach CSPOT: {e}")
        sys.exit(1)

    # Binary search for the starting seq_no
    log_info("Binary-searching for cutoff position in sequence space...")
    start_seq = binary_search_cutoff_seq(woof_url, cutoff_date, latest_seq_no)

    if start_seq is None:
        log_error(f"CSPOT has no data at or before cutoff date: {cutoff_date}")
        log_error(f"Oldest CSPOT records are newer than the cutoff.")
        log_error(f"Caller should fall back to historical archive.")
        sys.exit(2)

    log_info(f"Binary search result: starting seq_no={start_seq}")

    # Collect up to `limit` records walking backwards from start_seq
    sensor_file = output_path / "sensor_data.txt"
    total_records = 0
    current_seq = start_seq
    consecutive_failures = 0
    max_consecutive_failures = 50

    while current_seq >= 0 and consecutive_failures < max_consecutive_failures:
        try:
            data, timestamp_unix, _ = fetch_data_from_woof(woof_url, seq_no=current_seq)
            if timestamp_unix is None:
                consecutive_failures += 1
                current_seq -= 1
                continue

            data_time = unix_to_datetime(timestamp_unix)
            consecutive_failures = 0

            if data_time <= cutoff_date:
                with open(sensor_file, 'a') as f:
                    f.write(data + '\n')
                total_records += 1
                if total_records >= limit:
                    log_info(f"Collected {limit} records at or before cutoff")
                    break
            # else: skip (shouldn't happen after binary search, but be safe)

            current_seq -= 1

        except Exception:
            consecutive_failures += 1
            current_seq -= 1

    if total_records == 0:
        log_error(f"No records collected at or before cutoff {cutoff_date}")
        log_error(f"CSPOT data does not reach back that far.")
        sys.exit(2)

    log_info(f"Data load complete: {total_records} records")
    log_info(f"  sensor_data.txt: {total_records} records ({sensor_file.stat().st_size} bytes)")

    all_files = {"sensor_data": ["sensor_data.txt"], "run_dir": str(output_path)}
    print(f"\nRUN_DIR={output_path}")
    print(f"SENSOR_FILES={json.dumps(all_files['sensor_data'])}")
    return all_files


def load_data_until_cutoff(woof_url, cutoff_date, output_dir="./data", max_lookback_days=30, limit=None):
    """
    Load data from CSPOT backwards from latest until reaching cutoff date or limit.
    Creates sensor historical data file in a timestamped run directory:
    - output_dir/run_YYYYMMDD_HHMMSS/sensor_data.txt

    Args:
        woof_url: The WOOF URL to fetch from
        cutoff_date: datetime object representing the cutoff date (start date for filtering)
        output_dir: Parent directory to save output files
        max_lookback_days: Maximum days to look back
        limit: Maximum number of records to fetch

    Behavior:
        - If both cutoff_date and limit: fetch most recent N records (ignores date)
        - If only limit: fetch most recent N records
        - If only cutoff_date: fetch all records after that date
        - If neither: fetch recent records (default behavior)

    Returns:
        Dict with file info and 'run_dir'
    """
    # Create unique run directory with current timestamp
    now = datetime.now()
    run_name = now.strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"run_{run_name}"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Define date range
    sensor_start = None
    sensor_end = None
    
    # If cutoff_date is provided, use it as the starting point
    if cutoff_date is not None:
        sensor_start = cutoff_date
        sensor_end = cutoff_date + timedelta(days=max_lookback_days)
    
    log_info(f"Loading historical data")
    log_info(f"Run directory: {output_path}")
    if limit and sensor_start:
        log_info(f"Fetching up to {limit} records after {cutoff_date}")
    elif limit:
        log_info(f"Fetching up to {limit} most recent records")
    elif sensor_start:
        log_info(f"Sensor data range: {sensor_start} to {sensor_end}")
    else:
        log_info(f"Fetching recent data")
    
    # First, fetch the latest data to get current seq_no
    try:
        data, timestamp_unix, latest_seq_no = fetch_data_from_woof(woof_url)
        if not latest_seq_no:
            log_error("Could not extract sequence number from latest data")
            return {"training": [], "test": []}
        
        latest_time = unix_to_datetime(timestamp_unix)
        log_info(f"Latest data: seq_no={latest_seq_no}, time={latest_time}")
        
    except Exception as e:
        log_error(f"Failed to fetch latest data: {e}")
        return {"training": [], "test": []}
    
    # Collect data
    created_files = {"sensor_data": None}
    total_records = {"sensor_data": 0}
    
    # Create single file for sensor historical data (used for CFD simulations)
    sensor_file = output_path / "sensor_data.txt"
    
    # Start from latest and step backwards
    log_info("Fetching data from CSPOT...")
    
    current_seq = latest_seq_no
    step = 1
    consecutive_failures = 0
    max_consecutive_failures = 50
    
    while current_seq >= 0 and consecutive_failures < max_consecutive_failures:
        try:
            data, timestamp_unix, actual_seq = fetch_data_from_woof(woof_url, seq_no=current_seq)
            
            if timestamp_unix is None:
                consecutive_failures += 1
                current_seq -= step
                continue
            
            data_time = unix_to_datetime(timestamp_unix)
            consecutive_failures = 0  # Reset on success
            
            # Log progress every 500 records (reduced verbosity)
            if total_records["sensor_data"] % 500 == 0 and total_records["sensor_data"] > 0:
                log_info(f"Progress: {total_records['sensor_data']} records collected (seq {current_seq})")
            
            # Collect sensor data with different strategies:
            # 1. If both limit and cutoff_date: collect up to limit records AFTER cutoff_date
            # 2. If only limit: collect most recent N records (ignores date)
            # 3. If only cutoff_date: collect all records in date range
            # 4. If neither: collect recent records
            
            if limit is not None and sensor_start is not None:
                # Both limit and date: collect records after cutoff_date, up to limit
                if data_time >= sensor_start:
                    with open(sensor_file, 'a') as f:
                        f.write(data + '\n')
                    total_records["sensor_data"] += 1
                    created_files["sensor_data"] = "sensor_data.txt"
                    if total_records["sensor_data"] >= limit:
                        log_info(f"Reached limit of {limit} records after cutoff date {cutoff_date}")
                        break
                elif data_time < sensor_start:
                    # We've gone past the cutoff date, stop
                    log_info(f"Reached data before cutoff date at seq {current_seq}: {data_time} < {sensor_start}")
                    break
            elif limit is not None:
                # Only limit, no date restriction - collect most recent N records
                with open(sensor_file, 'a') as f:
                    f.write(data + '\n')
                total_records["sensor_data"] += 1
                created_files["sensor_data"] = "sensor_data.txt"
                if total_records["sensor_data"] >= limit:
                    log_info(f"Reached limit of {limit} records")
                    break
            elif sensor_start is not None and sensor_end is not None:
                # Only date range, no limit
                if sensor_start <= data_time < sensor_end:
                    with open(sensor_file, 'a') as f:
                        f.write(data + '\n')
                    total_records["sensor_data"] += 1
                    created_files["sensor_data"] = "sensor_data.txt"
                elif data_time < sensor_start:
                    # We've gone too far back, stop
                    log_info(f"Reached data before sensor data range at seq {current_seq}: {data_time}")
                    break
                # Otherwise skip (data is in the future)
            else:
                # No restrictions, collect everything
                with open(sensor_file, 'a') as f:
                    f.write(data + '\n')
                total_records["sensor_data"] += 1
                created_files["sensor_data"] = "sensor_data.txt"
            
            current_seq -= step
            
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures % 10 == 0:
                log_warn(f"Failed {consecutive_failures} consecutive times at seq {current_seq}")
            current_seq -= step
    
    log_info(f"Data load complete:")
    log_info(f"  Sensor data: {total_records['sensor_data']} records")

    # Print file summary
    all_files = {"sensor_data": [], "run_dir": str(output_path)}

    log_info("=== Sensor Historical Data ===")
    if created_files["sensor_data"] and sensor_file.exists():
        size = sensor_file.stat().st_size
        log_info(f"  {created_files['sensor_data']}: {total_records['sensor_data']} records ({size} bytes)")
        all_files["sensor_data"].append(created_files["sensor_data"])
    else:
        log_info("  No sensor data")
    
    return all_files

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Load historical data from CSPOT. Supports loading by date, limit, or both."
    )
    parser.add_argument(
        "-W", "--woof-url",
        default="woof://128.111.45.61/davisstations/daviscupsin",
        help="WOOF URL for CSPOT data source"
    )
    parser.add_argument(
        "-c", "--cutoff-date",
        help="Cutoff date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS). Load all data after this date."
    )
    parser.add_argument(
        "-d", "--days-back",
        type=int,
        help="Number of days to load back from today"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./data",
        help="Output directory for data files"
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=50,
        help="Maximum number of records to fetch (default: 50)."
    )
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Fetch N records AT OR BEFORE --cutoff-date (historical mode). "
             "Exits with code 2 if CSPOT has no data that old."
    )

    args = parser.parse_args()
    
    # Determine cutoff date (can be used with or without limit)
    cutoff_date = None
    if args.cutoff_date:
        try:
            # Accept trailing 'Z' and normalize all cutoffs to UTC-aware datetimes.
            cutoff_raw = args.cutoff_date.replace("Z", "+00:00")
            cutoff_date = datetime.fromisoformat(cutoff_raw)
        except ValueError:
            cutoff_date = datetime.strptime(args.cutoff_date, "%Y-%m-%d")

        if cutoff_date.tzinfo is None:
            cutoff_date = cutoff_date.replace(tzinfo=timezone.utc)
        else:
            cutoff_date = cutoff_date.astimezone(timezone.utc)
    elif args.days_back:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days_back)
    
    log_info(f"WOOF URL: {args.woof_url}")

    # Historical mode: fetch N records AT OR BEFORE cutoff_date
    if args.historical:
        if not cutoff_date:
            log_error("--historical requires --cutoff-date")
            sys.exit(1)
        log_info(f"Mode: historical — fetching up to {args.limit} records at/before {cutoff_date}")
        load_data_at_or_before_cutoff(
            args.woof_url,
            cutoff_date,
            args.output_dir,
            limit=args.limit
        )
        return  # load_data_at_or_before_cutoff prints RUN_DIR/SENSOR_FILES and exits on error

    # Online mode: fetch most recent N records (ignoring cutoff direction)
    if args.limit and cutoff_date:
        log_info(f"Mode: online — fetching last {args.limit} measurements")
    elif args.limit:
        log_info(f"Mode: online — fetching last {args.limit} measurements (most recent)")
    elif cutoff_date:
        log_info(f"Mode: online — fetching all measurements after {cutoff_date}")
    else:
        log_info("Mode: online — using default: last 50 measurements")

    files = load_data_until_cutoff(
        args.woof_url,
        cutoff_date,
        args.output_dir,
        limit=args.limit
    )

    # Return file info and run directory for shell script to consume
    print(f"\nRUN_DIR={files['run_dir']}")
    print(f"SENSOR_FILES={json.dumps(files['sensor_data'])}")

if __name__ == "__main__":
    main()
