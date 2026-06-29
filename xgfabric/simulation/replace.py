#!/usr/bin/env python3
"""Simple text replacement utility for OpenFOAM configuration files.

Usage: replace.py <input_file> <output_file> <search_string> <replace_string> [<search2> <replace2> ...]
"""

import sys

if len(sys.argv) < 5:
    print("Usage: replace.py <input_file> <output_file> <search_string> <replace_string> [...]")
    sys.exit(1)

filepath = sys.argv[1]
file_future_path = sys.argv[2]

with open(filepath, "rt") as f:
    text = f.read()

if len(sys.argv) % 2 != 1:
    raise Exception(f"Wrong number of arguments: {sys.argv}")

# Process all search/replace pairs
for i in range(3, len(sys.argv), 2):
    text = text.replace(sys.argv[i], sys.argv[i+1])

with open(file_future_path, "wt") as f:
    f.write(text)

print(f"Replaced text in {filepath} -> {file_future_path}")
