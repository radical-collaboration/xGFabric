#!/usr/bin/env python3

"""Replace windspeed in OpenFOAM case inlet boundary condition.

Usage: set_windspeed.py <case_dir> <wind_speed> <wind_dir>

This script updates the inlet velocity vector in 0/U file.
"""

import sys, os, re, math

# Check command line arguments
if len(sys.argv) < 3 or len(sys.argv) > 5:
    print("Usage: set_windspeed.py <case_dir> <wind_speed> <wind_dir>")
    sys.exit(2)

case_dir = sys.argv[1]
wind_speed = float(sys.argv[2])
wind_dir = sys.argv[3]

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


def parse_wind(wind_speed, wind_dir):
    """
    Parse weather station string and convert wind to x, y, z components.
    
    Returns:
        (x, y, z) where x,y,z are in m/s on same plane as speed_and_dir_2_xyz
    """
    # convert from mph to m/s
    wind_speed *= 0.44704
    
    # Convert compass degrees (0=N, 90=E, 180=S, 270=W) to match cardinal method's coordinate system
    # The cardinal method angle system: angle = compass_deg * π / 180 (direct conversion, no inversion)
    # This produces x = speed*cos(angle), y = speed*sin(angle) in the same coordinate system
    if wind_dir == "N":
        angle = 0
    elif wind_dir == "NNE":
        angle = math.radians(22.5)
    elif wind_dir == "NE":
        angle = math.radians(45)
    elif wind_dir == "ENE":
        angle = math.radians(67.5)
    elif wind_dir == "E":
        angle = math.radians(90)
    elif wind_dir == "ESE":
        angle = math.radians(112.5)
    elif wind_dir == "SE":
        angle = math.radians(135)
    elif wind_dir == "SSE":
        angle = math.radians(157.5)
    elif wind_dir == "S":
        angle = math.radians(180)
    elif wind_dir == "SSW":
        angle = math.radians(202.5)
    elif wind_dir == "SW":
        angle = math.radians(225)
    elif wind_dir == "WSW":
        angle = math.radians(247.5)
    elif wind_dir == "W":
        angle = math.radians(270)
    elif wind_dir == "WNW":
        angle = math.radians(292.5)
    elif wind_dir == "NW":
        angle = math.radians(315)
    elif wind_dir == "NNW":
        angle = math.radians(337.5)
    else:
        angle = None  # or handle unknown directions
    
    # Calculate x,y,z components (same as speed_and_dir_2_xyz)
    x = wind_speed * math.cos(angle)
    y = wind_speed * math.sin(angle)
    z = 0.0

    return x, y, z

# Look specifically for 0/U file which contains inlet velocity
u_file = os.path.join(case_dir, "0", "U")
if not os.path.isfile(u_file):
    print(f"Warning: Could not find 0/U file in {case_dir}")
    sys.exit(1)

try:
    with open(u_file, 'r', encoding='utf-8') as f:
        content = f.read()

    x_windspeed, y_windspeed, z_windspeed = parse_wind(wind_speed, wind_dir)
    new_content = replace_inlet_velocity(content, x_windspeed, y_windspeed, z_windspeed)
    if new_content == content:
        print(f"Warning: No inlet velocity was changed in {u_file}")
        sys.exit(1)
    
    with open(u_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Updated inlet velocity to ({x_windspeed} m/s, {y_windspeed} m/s, {z_windspeed} m/s) in {u_file}")
except Exception as e:
    print(f"Error updating {u_file}: {e}")
    sys.exit(1)
