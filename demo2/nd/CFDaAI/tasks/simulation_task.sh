#!/bin/bash
#
# simulation_task.sh - Single simulation task execution
#
# Wrapper that runs ONE CFD simulation via the main ./runme.sh script.
# Extracts cups_structure.zip, sets wind parameters, runs OpenFOAM,
# processes results to CSV, and saves to experiment output directory.
#
# Usage:
#   ./tasks/simulation_task.sh <parameter_file> <output_dir>
#
# Arguments:
#   parameter_file  - JSON with {sim_id, wind_speed, wind_direction}
#   output_dir      - Experiment simulation directory
#                     (e.g., /pscratch/.../experiment_2026-03-15_01-04-19/iteration_1/simulations)
#
# Workflow:
#   1. Extract parameters (ID, wind speed, direction) from JSON
#   2. Find cups_structure.zip in simulation/ directory
#   3. Call runme.sh with:
#      - zip file path
#      - wind speed (X component only, Y/Z default to 0)
#      - output directory
#      - simulation ID and wind direction for CSV naming
#   4. runme.sh handles:
#      - Extraction to working directory
#      - Wind speed configuration
#      - OpenFOAM execution
#      - CSV generation from results
#      - Working directory cleanup
#      - Error handling (keeps dir if error)
#   5. CSV files saved directly to output_dir by runme.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"

################################################################################
# Initialization
################################################################################

# Load environment
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"

init_system || {
    echo "ERROR: Failed to initialize system environment"
    exit 1
}

################################################################################
# Argument Parsing  
################################################################################

if [[ $# -lt 2 ]]; then
    cat <<EOF
Usage: $(basename "$0") <parameter_file> <output_dir>

Arguments:
  parameter_file  - JSON file with {sim_id, wind_speed, wind_direction}
  output_dir      - Experiment simulation output directory
                    (e.g., /pscratch/.../experiment_.../iteration_1/simulations)

The script will:
  1. Extract sim parameters from JSON
  2. Invoke runme.sh with cups_structure.zip
  3. runme.sh extracts zip, sets windspeed, runs OpenFOAM, generates CSV
  4. Results (CSV only) saved to output_dir
  5. Errors: simulation working directory kept for debugging
EOF
    exit 1
fi

PARAM_FILE="$1"
OUTPUT_DIR="$2"

require_file "$PARAM_FILE" "Parameter file"
ensure_dir "$OUTPUT_DIR"

################################################################################
# Configuration & Parameter Extraction
################################################################################

# Locate the master cups_structure.zip
CUPS_ARCHIVE="${WORK_DIR}/simulation/cups_structure.zip"
require_file "$CUPS_ARCHIVE" "CFD template archive"

extract_param() {
    local key="$1"
    python3 -c "import json; d=json.load(open('$PARAM_FILE')); print(d.get('$key', ''))"
}

# Parse simulation parameters from JSON
SIM_ID=$(extract_param "sim_id")
WIND_SPEED=$(extract_param "wind_speed")
WIND_DIRECTION=$(extract_param "wind_direction")

if [[ -z "$SIM_ID" || -z "$WIND_SPEED" || -z "$WIND_DIRECTION" ]]; then
    log_error "Missing required parameters in: ${PARAM_FILE}"
    log_error "Required: sim_id, wind_speed, wind_direction"
    exit 1
fi

log_info "Simulation ${SIM_ID}: wind_speed=${WIND_SPEED} m/s, wind_dir=${WIND_DIRECTION}°"

# Convert wind speed + direction to x/y components
# x = north, y = east; wd = compass bearing wind blows towards (0=N, 90=E)
read UX UY < <(python3 -c "
import math
ws = float('${WIND_SPEED}')
wd = math.radians(float('${WIND_DIRECTION}'))
print(f'{ws * math.cos(wd):.6f} {ws * math.sin(wd):.6f}')
")
log_info "  Wind components: Ux=${UX} m/s, Uy=${UY} m/s"

################################################################################
# Simulation Execution via runme.sh
################################################################################

timer_start "simulation_${SIM_ID}"

# Locate runme script
RUNME_SCRIPT="${WORK_DIR}/simulation/runme.sh"
require_file "$RUNME_SCRIPT" "Simulation execution script"

log_info "Starting simulation..."
log_info "  Archive: ${CUPS_ARCHIVE}"
log_info "  Output: ${OUTPUT_DIR}"
log_info "  Parameters: ws=$WIND_SPEED m/s, wd=$WIND_DIRECTION°, Ux=$UX, Uy=$UY, sim_id=$SIM_ID"

# Change to simulation directory (runme.sh uses relative paths to find helper scripts)
ORIG_DIR="$(pwd)"
cd "${WORK_DIR}/simulation" || exit 1

# Call runme.sh with parameters:
#   arg1: zip file path (absolute)
#   arg2: thread count
#   arg3-5: x/y/z windspeed components
#   arg6: output_results_dir
#   arg7: decomposition config
#   arg8: SIM_INDEX (for CSV naming)
#   arg9: WIND_DIR (for CSV naming)

THREADS="${SIMULATION_THREADS:-32}"

if bash runme.sh \
    "$CUPS_ARCHIVE" \
    "$THREADS" \
    "$UX" \
    "$UY" \
    "0.0" \
    "$OUTPUT_DIR" \
    "1 4 1" \
    "$SIM_ID" \
    "$WIND_DIRECTION" \
    "$WIND_SPEED"; then
    
    log_info "✓ Simulation ${SIM_ID} completed successfully"
    timer_end "simulation_${SIM_ID}"
    cd "$ORIG_DIR"
    
else
    log_error "✗ Simulation ${SIM_ID} failed"
    log_error "Working directory kept for debugging"
    cd "$ORIG_DIR"
    exit 1
fi

log_info "Simulation ${SIM_ID} - results saved to: ${OUTPUT_DIR}"
