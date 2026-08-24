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

def run_command(cmd, retries=3, retry_delay=60):
    """Execute a shell command and return output, retrying on transient CSPOT errors."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            last_exc = Exception(f"Command failed: {cmd}\nError: {e.stderr}")
            stderr_lower = (e.stderr or "").lower()
            transient = "temporarily unavailable" in stderr_lower or "couldn't recv msg" in stderr_lower
            if transient and attempt < retries:
                log_warn(f"CSPOT transient error (attempt {attempt}/{retries}), retrying in {retry_delay}s ...")
                time.sleep(retry_delay)
            else:
                raise last_exc
    raise last_exc

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

def fetch_batch_from_woof(woof_url, start_seq, count):
    """
    Fetch up to `count` consecutive records starting at start_seq (senspot-get's
    -C walks FORWARD in seq_no) in a single subprocess call, instead of one
    call per record. Same linear scan as fetch_data_from_woof(), just batched
    to cut subprocess-call count (and exposure to occasional slow/transient
    CSPOT responses) by ~`count`x for wide windows.

    Returns a list of (data_string, timestamp_unix, seq_no) tuples, ascending
    by seq_no. May return fewer than `count` if start_seq+count-1 exceeds the
    latest available record.
    """
    senspot_path = find_senspot_get()
    cmd = f"{senspot_path} -W {woof_url} -S {start_seq} -C {count}"

    output = run_command(cmd)

    records = []
    for line in output.splitlines():
        match = re.search(r'time:\s+([\d.]+)\s+[\d.]+\s+seq_no:\s+(\d+)', line)
        if match:
            records.append((line, float(match.group(1)), int(match.group(2))))
    return records

def unix_to_datetime(unix_timestamp):
    """Convert Unix timestamp to datetime"""
    return datetime.fromtimestamp(unix_timestamp, timezone.utc)

def parse_flexible_dt(s):
    """Parse 'YYYY-MM-DD HH:MM[:SS][ UTC]' or ISO8601 into a UTC-aware datetime."""
    s = s.strip()
    if s.upper().endswith(" UTC"):
        s = s[:-4].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

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
            # A failed fetch within [0, latest_seq_no] only happens because mid
            # has been evicted from the circular buffer (too old) -- latest_seq_no
            # itself is already confirmed valid, so "too new" can't be the cause.
            # Search higher, same direction as the timestamp_unix-is-None case above.
            lo = mid + 1

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


def load_data_in_window(woof_url, t_start, t_end, output_dir="./data", safety_cap=5000,
                        batch_size=50):
    """
    Fetch ALL records in [t_start, t_end] from CSPOT -- nothing older, nothing newer.

    Pure linear walk backward from the latest seq_no: skip (don't save) records
    newer than t_end, then once time <= t_end save records one by one until
    time < t_start, then stop. No binary search -- just a single backward pass.

    Fetched in batches of `batch_size` consecutive records per subprocess call
    (via senspot-get's -C) rather than one record per call: for wide windows
    this is still exactly the same record-by-record scan, just far fewer
    subprocess calls, which matters because each call has some independent
    chance of hitting a multi-second CSPOT-side stall -- O(N) calls each with
    a small stall probability adds up to minutes of dead time for N in the
    hundreds, while O(N/batch_size) calls do not.

    Exit codes:
        0 - success (sensor_data.txt written, possibly with 0 records)
        2 - CSPOT has no data reaching back to t_start, or the window is entirely
            after the newest CSPOT record, or t_end is older than the whole
            retained buffer
    """
    now = datetime.now()
    run_name = now.strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"run_{run_name}"
    output_path.mkdir(parents=True, exist_ok=True)

    log_info(f"Loading CSPOT data in window: {t_start} -> {t_end}")
    log_info(f"Run directory: {output_path}")

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

    if latest_time < t_start:
        log_error(f"CSPOT's newest record ({latest_time}) predates window start ({t_start})")
        sys.exit(2)

    sensor_file = output_path / "sensor_data.txt"
    total_records = 0
    skipped_after_window = 0
    reached_window = False
    current_seq = latest_seq_no
    consecutive_failures = 0
    max_consecutive_failures = 50

    log_info(f"Walking backward from the latest record in batches of {batch_size} "
             f"(linear, no binary search) ...")
    while current_seq >= 0 and consecutive_failures < max_consecutive_failures:
        if total_records >= safety_cap:
            log_warn(f"Hit safety cap of {safety_cap} records -- window wider than "
                     f"expected, stopping early")
            break

        batch_start = max(current_seq - batch_size + 1, 0)
        try:
            batch = fetch_batch_from_woof(woof_url, batch_start, current_seq - batch_start + 1)
        except Exception:
            # Whole batch call failed -- fall back to a single-record probe so
            # eviction is detected at record granularity, same as before.
            consecutive_failures += 1
            current_seq -= 1
            continue

        if not batch:
            consecutive_failures += 1
            current_seq = batch_start - 1
            continue
        consecutive_failures = 0

        hit_window_start = False
        for data, timestamp_unix, seq in sorted(batch, key=lambda r: r[2], reverse=True):
            data_time = unix_to_datetime(timestamp_unix)

            if data_time > t_end:
                # Still newer than the window -- skip and keep walking back.
                skipped_after_window += 1
                continue

            reached_window = True

            if data_time < t_start:
                log_info(f"Reached data before window start at seq {seq}: "
                         f"{data_time} < {t_start}")
                hit_window_start = True
                break

            with open(sensor_file, 'a') as f:
                f.write(data + '\n')
            total_records += 1
            if total_records >= safety_cap:
                break

        if hit_window_start or total_records >= safety_cap:
            break
        current_seq = batch_start - 1

    log_info(f"Window fetch complete: {total_records} records in [{t_start}, {t_end}] "
             f"(skipped {skipped_after_window} newer than window end)")

    if not reached_window:
        log_error(f"CSPOT has no data at or before window end: {t_end} "
                  f"(buffer evicted past this point)")
        sys.exit(2)

    created = total_records > 0 and sensor_file.exists()
    all_files = {"sensor_data": ["sensor_data.txt"] if created else [], "run_dir": str(output_path)}
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
    parser.add_argument(
        "--window-start",
        help="Start of a bounded time window (ISO8601 or 'YYYY-MM-DD HH:MM[:SS]'[ UTC]). "
             "Requires --window-end. Fetches ONLY records inside [window-start, window-end]."
    )
    parser.add_argument(
        "--window-end",
        help="End of a bounded time window. See --window-start."
    )
    parser.add_argument(
        "--window-safety-cap",
        type=int, default=5000,
        help="Max records to collect in windowed mode before aborting early (default: 5000)."
    )
    parser.add_argument(
        "--window-batch-size",
        type=int, default=200,
        help="Consecutive records fetched per senspot-get call in windowed mode "
             "(default: 200). Higher-rate sensors need more subprocess calls for "
             "the same time window, so a bigger batch keeps the call count (and "
             "exposure to occasional slow CSPOT responses) down."
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

    # Windowed mode: fetch ONLY records in [window_start, window_end]
    if args.window_start and args.window_end:
        w_start = parse_flexible_dt(args.window_start)
        w_end   = parse_flexible_dt(args.window_end)
        log_info(f"Mode: window — fetching records in [{w_start}, {w_end}]")
        load_data_in_window(
            args.woof_url,
            w_start,
            w_end,
            args.output_dir,
            safety_cap=args.window_safety_cap,
            batch_size=args.window_batch_size,
        )
        return  # load_data_in_window prints RUN_DIR/SENSOR_FILES and exits on error

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
