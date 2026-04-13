#!/bin/bash
#
# Grid configuration reader for shell scripts
# Reads values from grid_config.json and exports them as shell variables
#
# Usage: source $(dirname "$0")/read_grid_config.sh
#        or: eval "$(./read_grid_config.sh)"
#
# Exports:
#   GRID_X_MIN, GRID_X_MAX, GRID_Y_MIN, GRID_Y_MAX, GRID_Z_MIN, GRID_Z_MAX
#   GRID_NX, GRID_NY, GRID_NZ, GRID_TOTAL_POINTS
#   GRID_AVERAGING_RADIUS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/grid_config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Warning: grid_config.json not found at $CONFIG_FILE, using defaults" >&2
    # Default values
    export GRID_X_MIN=8.3
    export GRID_X_MAX=176.5
    export GRID_Y_MIN=8.1
    export GRID_Y_MAX=82.1
    export GRID_Z_MIN=1.0
    export GRID_Z_MAX=7.0
    export GRID_NX=85
    export GRID_NY=38
    export GRID_NZ=4
    export GRID_TOTAL_POINTS=12920
    export GRID_AVERAGING_RADIUS=1.5
else
    # Parse JSON with python (more reliable than jq which may not be installed)
    eval "$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    cfg = json.load(f)

print(f\"export GRID_X_MIN={cfg['boundaries']['x_min']}\")
print(f\"export GRID_X_MAX={cfg['boundaries']['x_max']}\")
print(f\"export GRID_Y_MIN={cfg['boundaries']['y_min']}\")
print(f\"export GRID_Y_MAX={cfg['boundaries']['y_max']}\")
print(f\"export GRID_Z_MIN={cfg['boundaries']['z_min']}\")
print(f\"export GRID_Z_MAX={cfg['boundaries']['z_max']}\")
print(f\"export GRID_NX={cfg['grid']['nx']}\")
print(f\"export GRID_NY={cfg['grid']['ny']}\")
print(f\"export GRID_NZ={cfg['grid']['nz']}\")
print(f\"export GRID_TOTAL_POINTS={cfg['grid']['total_points']}\")
print(f\"export GRID_AVERAGING_RADIUS={cfg['cfd_averaging']['radius']}\")
")"
fi

# Print summary if run directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Grid Configuration (from $CONFIG_FILE):"
    echo "  Boundaries: X=[${GRID_X_MIN}, ${GRID_X_MAX}] Y=[${GRID_Y_MIN}, ${GRID_Y_MAX}] Z=[${GRID_Z_MIN}, ${GRID_Z_MAX}]"
    echo "  Grid: ${GRID_NX}x${GRID_NY}x${GRID_NZ} = ${GRID_TOTAL_POINTS} points"
    echo "  Averaging radius: ${GRID_AVERAGING_RADIUS}m"
fi
