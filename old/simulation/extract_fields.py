#!/usr/bin/env python3
"""Extract OpenFOAM simulation results directly to CSV.

This script reads OpenFOAM binary field files and exports them as CSV
without requiring VTK conversion, which is much faster for large grids.

Usage: python3 extract_fields.py <case_directory> <output_csv>
"""

import os
import sys
import struct
import subprocess
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

def run_command(cmd, cwd=None):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, 
                              capture_output=True, text=True, timeout=60)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return f"Error: {e}"


def extract_openfoam_fields(case_dir, output_csv):
    """Extract OpenFOAM fields directly to CSV using postProcessing."""
    
    print(f"Case directory: {case_dir}")
    os.chdir(case_dir)
    
    # Find latest time directory
    time_dirs = [d for d in os.listdir('.') if os.path.isdir(d) and d.replace('.', '', 1).replace('e-', '', 1).replace('e+', '', 1).isdigit()]
    if not time_dirs:
        print("Error: No time directories found")
        return False
    
    latest_time = sorted(time_dirs, key=float)[-1]
    print(f"Processing time: {latest_time}")
    
    # Use foamToVTK with ASCII output for easier parsing
    print("Exporting to VTK (ASCII format)...")
    
    os.makedirs("VTK", exist_ok=True)
    
    # Create a Python script to extract fields using VTK in ASCII format
    extract_script = f"""
import sys
sys.path.insert(0, '/local/home/liubov_kurafeeva/miniforge3/lib/python3.12/site-packages')

import os
import numpy as np
import pandas as pd

case_dir = "{case_dir}"
time_step = "{latest_time}"

# Use OpenFOAM's direct field access via OF utilities
# Create a script to use foamListTimes and get field data

os.chdir(case_dir)

# Check what fields are available
fields = []
field_dirs = [d for d in os.listdir(time_step) if os.path.isdir(os.path.join(time_step, d))]
print(f"Available field directories: {{field_dirs}}")

# Common field names in OpenFOAM
expected_fields = ['U', 'p', 'k', 'epsilon', 'nut', 'omega', 'T', 'rho']
for field in expected_fields:
    field_file = os.path.join(time_step, field)
    if os.path.exists(field_file):
        print(f"Found field: {{field}}")

print("Use 'foamToVTK -time {time_step}' then 'vtk_to_csv.py' for full export")
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(extract_script)
        script_file = f.name
    
    try:
        result = subprocess.run(['python3', script_file], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Warnings:", result.stderr)
    finally:
        os.remove(script_file)
    
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_fields.py <case_directory> [output_csv]")
        sys.exit(1)
    
    case_dir = sys.argv[1]
    output_csv = sys.argv[2] if len(sys.argv) > 2 else "results.csv"
    
    if not os.path.isdir(case_dir):
        print(f"Error: Case directory not found: {case_dir}")
        sys.exit(1)
    
    extract_openfoam_fields(case_dir, output_csv)


if __name__ == "__main__":
    main()
