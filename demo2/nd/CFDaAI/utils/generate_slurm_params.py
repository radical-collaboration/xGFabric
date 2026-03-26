#!/usr/bin/env python3
"""
Expand a simulation CSV params file into per-task JSON files for SLURM arrays.
Writes sim_0.json, sim_1.json, ... to the params directory.

Usage: generate_slurm_params.py <csv_file> <params_dir>
"""
import csv
import json
import sys
import pathlib
from datetime import datetime

ts = lambda: datetime.now().strftime('%H:%M:%S')


def main():
    if len(sys.argv) < 3:
        print(f"[ERROR] {ts()} Usage: generate_slurm_params.py <csv_file> <params_dir>",
              file=sys.stderr)
        sys.exit(1)

    csv_file = sys.argv[1]
    out_dir  = pathlib.Path(sys.argv[2])

    with open(csv_file) as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            ws  = row.get("wind_speed", row.get("windspeed", "")).strip()
            wd  = row.get("wind_dir",   row.get("winddir",   "0")).strip()
            out = out_dir / f"sim_{idx}.json"
            out.write_text(json.dumps({"sim_id": str(idx),
                                       "wind_speed": ws,
                                       "wind_direction": wd}))
            print(f"[INFO] {ts()}   wrote {out.name}  (ws={ws}, wd={wd})")


if __name__ == "__main__":
    main()
