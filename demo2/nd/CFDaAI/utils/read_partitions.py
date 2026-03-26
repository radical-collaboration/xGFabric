#!/usr/bin/env python3
"""
Read a partitions JSON file and print each partition's machine_id, one per line.
Used by orchestrate_training.sh to populate a bash array.

Usage: read_partitions.py <partitions_json_file>
"""
import json
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    data = json.load(open(sys.argv[1]))
    for p in data.get('partitions', []):
        print(p.get('machine_id', 0))


if __name__ == "__main__":
    main()
