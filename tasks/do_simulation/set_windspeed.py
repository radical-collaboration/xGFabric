#!/usr/bin/env python3

"""Replace windspeed in OpenFOAM case inlet boundary condition.

Usage: set_windspeed.py <case_dir> <x_windspeed> [<y_windspeed>] [<z_windspeed>]

This script updates the inlet velocity vector in 0/U file.
If y_windspeed is not provided, it defaults to 0.0
If z_windspeed is not provided, it defaults to 0.0
"""

import sys
import os
import re

# Check command line arguments
if len(sys.argv) < 3 or len(sys.argv) > 5:
    print("Usage: set_windspeed.py <case_dir> <x_windspeed> [<y_windspeed>] [<z_windspeed>]")
    sys.exit(2)

case_dir = sys.argv[1]
x_windspeed = float(sys.argv[2])
y_windspeed = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
z_windspeed = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0

if not os.path.isdir(case_dir):
    print(f"Case directory not found: {case_dir}")
    sys.exit(1)


def replace_inlet_velocity(content, x_speed, y_speed, z_speed):
    """Replace inlet velocity while preserving OpenFOAM formatting."""
    # Pattern matches 'uniform (<number> <number> <number>)' in the inlet section
    inlet_pattern = r'(inlet\s*{[^}]*?uniform\s*\()(\d+\.?\d*)(\s+)(\d+\.?\d*)(\s+)(\d+\.?\d*)(\))'

    def replace_in_inlet(match):
        prefix = match.group(1)
        space1 = match.group(3)
        space2 = match.group(5)
        suffix = match.group(7)
        return f"{prefix}{x_speed:.1f}{space1}{y_speed:.1f}{space2}{z_speed:.1f}{suffix}"
    
    new_content = re.sub(inlet_pattern, replace_in_inlet, content, flags=re.DOTALL)
    if new_content == content:
        print("Warning: Could not find inlet velocity pattern to replace")
    return new_content

# Look specifically for 0/U file which contains inlet velocity
u_file = os.path.join(case_dir, "0", "U")
if not os.path.isfile(u_file):
    print(f"Warning: Could not find 0/U file in {case_dir}")
    sys.exit(1)

try:
    with open(u_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = replace_inlet_velocity(content, x_windspeed, y_windspeed, z_windspeed)
    if new_content == content:
        print(f"Warning: No inlet velocity was changed in {u_file}")
        sys.exit(1)
    
    with open(u_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Updated inlet velocity to ({x_windspeed}, {y_windspeed}, {z_windspeed}) in {u_file}")
except Exception as e:
    print(f"Error updating {u_file}: {e}")
    sys.exit(1)
