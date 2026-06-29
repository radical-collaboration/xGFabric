#!/bin/bash
# Exit immediately on any error
set -e

# OpenFOAM Simulation Runner
# Usage: ./runme.sh <zip-file> <threads> <x_windspeed> [y_windspeed] [z_windspeed]
#
# Example: ./runme.sh cups_structure.zip 32 2.5 0.0 0.0

# Timing utility
format_duration() {
    local duration="$1"
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))
    echo "${hours}h ${minutes}m ${seconds}s"
}

show_usage() {
    echo "Usage: $0 <zip-file> <threads> <x_windspeed> [y_windspeed] [z_windspeed]"
    echo
    echo "Required arguments:"
    echo "  zip-file        Input zip file containing the simulation setup"
    echo "  threads         Number of threads for parallel processing"
    echo "  x_windspeed     Wind speed X component (m/s)"
    echo
    echo "Optional arguments:"
    echo "  y_windspeed     Wind speed Y component (m/s, default: 0.0)"
    echo "  z_windspeed     Wind speed Z component (m/s, default: 0.0)"
    echo
    echo "Example:"
    echo "  $0 cups_structure.zip 32 2.5"
    echo "  $0 cups_structure.zip 32 3.0 0.5 0.0"
}

# Show help if requested
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_usage
    exit 0
fi

# Check required parameters
if [ "$#" -lt 3 ]; then
    show_usage
    exit 1
fi

# Set up parameters
folder_name="$1"
threads="$2"
x_windspeed="$3"
y_windspeed="${4:-0.0}"
z_windspeed="${5:-0.0}"
output_results_dir="${6:-.}"  # Optional: directory where to save results (default: current directory)
decomp_n="${7:-1 4 1}"        # Optional: hierarchical decomposition n-tuple (default: 1 4 1)
# For parallel execution: simulation index and wind direction for CSV naming
SIM_INDEX="${8:-$SIM_INDEX}"   # Use arg if provided, else fall back to env var
WIND_DIR="${9:-$WIND_DIR}"     # Use arg if provided, else fall back to env var
# Wind speed label for CSV naming: original magnitude (always positive), defaults to x_windspeed
WS_LABEL="${10:-$x_windspeed}"

if [ ! -f "$folder_name" ]; then
    echo "Error: zip file $folder_name not found"
    exit 1
fi

# Create descriptive directory name with short unique identifier
# Use process ID for uniqueness to avoid OpenFOAM filename length limits
if [ "$y_windspeed" != "0.0" ] || [ "$z_windspeed" != "0.0" ]; then
    destination="ws${x_windspeed}_${y_windspeed}_${z_windspeed}_$$"
else
    destination="ws${x_windspeed}_$$"
fi

# Use scratch directory within experiment for working directory (same pscratch filesystem)
# This avoids read-only filesystem issues and keeps work scoped to experiment
working_dir=$INTERIM_DIR
mkdir -p "$working_dir" || {
    echo "Error: Failed to create working directory: $working_dir"
    exit 1
}

# Trap to clean up working directory on exit (unless error)
trap "rm -rf '$working_dir'" EXIT

start=$(date '+%s.%N')
start_int=$(date '+%s')

echo "================================================"
echo "OpenFOAM Simulation Setup"
echo "================================================"
echo "Case name:      $destination"
echo "Work dir:       $working_dir"
echo "Threads:        $threads"
echo "Windspeed:      ($x_windspeed, $y_windspeed, $z_windspeed) m/s"
echo "[TIMER] Simulation started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"

# Extract zip file to working directory
extract_start=$(date '+%s')
echo "[TIMER] Case extraction started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "Extracting case from $folder_name to $working_dir..."
if ! unzip -q "$folder_name" -d "$working_dir"; then
    echo "Error: Failed to extract zip file to $working_dir"
    exit 1
fi
mv "$working_dir/cups_structure"/* "$working_dir"/ 2>/dev/null || true
rmdir "$working_dir/cups_structure" 2>/dev/null || true
extract_end=$(date '+%s')
extract_elapsed=$((extract_end - extract_start))
echo "[TIMER] Case extraction completed - Duration: ${extract_elapsed}s"

# Set windspeed using the helper script
windspeed_start=$(date '+%s')
echo "[TIMER] Windspeed configuration started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "Setting windspeed to ($x_windspeed, $y_windspeed, $z_windspeed)..."
if ! python3 set_windspeed.py "$working_dir" "$x_windspeed" "$y_windspeed" "$z_windspeed"; then
    echo "Error: Failed to set windspeed"
    exit 1
fi

# Update thread count in decomposition dictionary
echo "Configuring for $threads threads..."
if ! python3 replace.py "$working_dir/system/decomposeParDict" "$working_dir/system/decomposeParDict" @ "$threads"; then
    echo "Error: Failed to configure thread count"
    exit 1
fi
windspeed_end=$(date '+%s')
windspeed_elapsed=$((windspeed_end - windspeed_start))
echo "[TIMER] Configuration completed - Duration: ${windspeed_elapsed}s"

# Run the simulation
sim_start=$(date '+%s')
echo "[TIMER] OpenFOAM solver phase started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "Starting simulation..."
if ! bash run_simulation.sh "$working_dir" "$threads"; then
    echo "Error: Simulation failed"
    exit 1
fi
sim_end=$(date '+%s')
sim_elapsed=$((sim_end - sim_start))
echo "[TIMER] OpenFOAM solver phase completed - Duration: $(format_duration $sim_elapsed) (${sim_elapsed}s)"

stop=$(date '+%s.%N')
stop_int=$(date '+%s')
elapsed=$(bc -l <<< "$stop - $start")
elapsed_int=$((stop_int - start_int))

echo "================================================"
echo "Simulation completed in $elapsed seconds"
echo "[TIMER] Total simulation time: $(format_duration $elapsed_int) (${elapsed_int}s)"
echo "================================================"

# Process results: VTK -> CSV (passing working directory and output directory)
results_start=$(date '+%s')
echo "[TIMER] Results processing started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "Processing results..."
if bash process_results.sh "$working_dir" "$x_windspeed" "$output_results_dir"; then
    results_end=$(date '+%s')
    results_elapsed=$((results_end - results_start))
    echo "[TIMER] Results processing completed - Duration: $(format_duration $results_elapsed) (${results_elapsed}s)"
    echo "Results processed successfully"
else
    echo "ERROR: Failed to process results"
    echo "ERROR: Keeping simulation directory for debugging: $working_dir"
    exit 1
fi

# Verify CSV exists in output directory before cleanup
WINDSPEED_SAFE=$(echo "$x_windspeed" | tr '.' '_')
CSV_FILE="${output_results_dir}/cups_structure_ws${WINDSPEED_SAFE}.csv"
if [ ! -f "$CSV_FILE" ]; then
    echo "ERROR: Expected CSV not found: $CSV_FILE"
    echo "ERROR: Keeping simulation directory for debugging: $working_dir"
    exit 1
fi
echo "Verified CSV exists: $CSV_FILE"

# For parallel execution: rename CSV to include simulation index, windspeed, and wind direction
# Format: sim_{INDEX}_ws_{WINDSPEED}_wd_{WINDDIR}.csv
# This allows the parallel orchestrator to identify which simulation produced which results
echo "DEBUG: SIM_INDEX='$SIM_INDEX' WIND_DIR='$WIND_DIR'"
if [ -n "$SIM_INDEX" ] && [ -n "$WIND_DIR" ]; then
    # SIM_INDEX and WIND_DIR should be passed by the caller (parallel orchestrator)
    # Keep the original values (with dots) for consistency with parallel orchestrator
    RENAMED_CSV="${output_results_dir}/sim_${SIM_INDEX}.csv"
    mv "$CSV_FILE" "$RENAMED_CSV"
    echo "Renamed CSV for parallel tracking: $RENAMED_CSV"
    CSV_FILE="$RENAMED_CSV"
fi

# Clean up happens via trap on EXIT - working_dir will be removed automatically

# Calculate total end time
total_end=$(date '+%s')
total_elapsed=$((total_end - start_int))

echo "================================================"
echo "All done!"
echo "================================================"
echo "[TIMER] ======================================"
echo "[TIMER] SINGLE SIMULATION TIMING SUMMARY"
echo "[TIMER] ======================================"
echo "[TIMER] Case extraction:    ${extract_elapsed}s"
echo "[TIMER] Configuration:      ${windspeed_elapsed}s"
echo "[TIMER] OpenFOAM solver:    $(format_duration $sim_elapsed) (${sim_elapsed}s)"
echo "[TIMER] Results processing: $(format_duration $results_elapsed) (${results_elapsed}s)"
echo "[TIMER] Total elapsed:      $(format_duration $total_elapsed) (${total_elapsed}s)"
echo "[TIMER] Completed at:       $(date '+%Y-%m-%d %H:%M:%S')"
echo "[TIMER] ======================================"
