#!/usr/bin/env python3
"""
Convert raw CSPOT sensor data to CSV with columns: dt,windspeed,windavg,winddir.

CSPOT format: field1:field2:...:fieldN time: <unix_ts> <ip> seq_no: <seq>
Field indices (0-based): 3=windspeed(mph), 4=windavg(mph), 5=winddir(degrees)

Usage: convert_cspot_to_csv.py <input_file> [output_file]
       If output_file is omitted, writes to stdout.
"""
import sys
from datetime import datetime


def convert(input_file, out):
    out.write('dt,windspeed_ms,windavg_ms,winddir\n')
    count = 0
    with open(input_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                if ' time: ' not in line:
                    continue
                data_part, meta_part = line.split(' time: ', 1)
                fields = data_part.split(':')
                if len(fields) < 6:
                    continue
                timestamp_str = meta_part.split()[0]
                dt = datetime.fromtimestamp(float(timestamp_str)).isoformat()
                windspeed = float(fields[3]) * 0.44704  # mph -> m/s
                windavg   = float(fields[4]) * 0.44704  # mph -> m/s
                winddir   = float(fields[5])
                out.write(f'{dt},{windspeed},{windavg},{winddir}\n')
                count += 1
            except (ValueError, IndexError):
                continue
    return count


def main():
    if len(sys.argv) < 2:
        print("Usage: convert_cspot_to_csv.py <input_file> [output_file]", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]

    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'w') as f:
            count = convert(input_file, f)
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[INFO] {ts} Converted {count} records to {sys.argv[2]}", file=sys.stderr)
    else:
        count = convert(input_file, sys.stdout)


if __name__ == "__main__":
    main()
