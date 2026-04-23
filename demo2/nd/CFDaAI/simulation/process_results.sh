#!/bin/bash

set -e

# Process OpenFOAM results: export VTK, convert to CSV, cleanup
# Usage: ./process_results.sh <case_directory> <windspeed> <output_directory>
#
# CSV output: <output_directory>/cups_structure_ws{windspeed}.csv

# Timing utility
format_duration() {
    local duration="$1"
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))
    echo "${hours}h ${minutes}m ${seconds}s"
}

PROCESS_START_TIME=$(date '+%s')
echo "[TIMER] Results processing started at $(date '+%Y-%m-%d %H:%M:%S')"

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <case_directory> <windspeed> <output_directory>"
    echo "  case_directory: OpenFOAM case directory"
    echo "  windspeed: Wind speed value for naming the output CSV"
    echo "  output_directory: Directory where CSV will be saved"
    exit 1
fi

CASE_DIR="$1"
WINDSPEED="$2"
OUTPUT_DIR="$3"
CASE_NAME=$(basename "$CASE_DIR")

echo "================================================"
echo "Processing Results for: $CASE_NAME"
echo "  Windspeed: $WINDSPEED m/s"
echo "  Output: $OUTPUT_DIR"
echo "================================================"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create output directory
mkdir -p "$OUTPUT_DIR"

cd "$CASE_DIR"
echo "Working directory: $(pwd)"

# Find the latest time directory with simulation data
LATEST_TIME=$(ls -d [0-9]* 2>/dev/null | sort -n | tail -1)
echo "Latest simulation time directory: $LATEST_TIME"

if [ -z "$LATEST_TIME" ]; then
    echo "ERROR: No simulation time directories found"
    exit 1
fi

if [ "$SYSTEM_TYPE" == "nd" ]; then
    module --force purge
    module add openfoam/10.0/gcc/11.5.0 > /dev/null 2>&1
    module add paraview/5.11.2
elif [ "$SYSTEM_TYPE" == "nersc" ]; then
    module --force purge
    module load spack
    . /global/common/software/nersc9/spack/1.1.0/share/spack/setup-env.sh
    module load conda
    module load paraview || true  # paraview may not be needed at runtime
    spack load openmpi@4.1.5
    group_num=$(groups | awk -F" " '{print $2}')
    export OPENFOAM_ROOT="/global/common/software/$group_num/openfoam"
    source "$OPENFOAM_ROOT/OpenFOAM-dev/etc/bashrc" || true  # non-fatal: OF env may already be set
    export LD_LIBRARY_PATH=$(spack location -i openmpi@4.1.5)/lib:$LD_LIBRARY_PATH
fi

# Export to VTK format
VTK_START=$(date '+%s')
echo "[TIMER] VTK export started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "Exporting results to VTK format..."
if foamToVTK -latestTime; then
    MAIN_VTK=$(find ./VTK -maxdepth 1 -name "*.vtk" -type f | sort -n | tail -1)
    if [ -z "$MAIN_VTK" ]; then
        echo "ERROR: VTK export ran but no VTK file found"
        exit 1
    fi
    VTK_END=$(date '+%s')
    VTK_ELAPSED=$((VTK_END - VTK_START))
    echo "[TIMER] VTK export completed - Duration: ${VTK_ELAPSED}s"
    echo "VTK export successful: $MAIN_VTK"
else
    echo "ERROR: VTK export failed!"
    echo "ERROR: Make sure OpenFOAM environment is sourced"
    echo "ERROR: Check log file: $(pwd)/log"
    exit 1
fi

# Convert VTK to CSV with proper naming
# CSV name uses underscore instead of dot to avoid parsing issues
# e.g., cups_structure_ws2_00.csv instead of cups_structure_ws2.00.csv
WINDSPEED_SAFE=$(echo "$WINDSPEED" | tr '.' '_')
CSV_FILENAME="cups_structure_ws${WINDSPEED_SAFE}.csv"
CSV_OUTPUT="${OUTPUT_DIR}/${CSV_FILENAME}"

CSV_START=$(date '+%s')
echo "[TIMER] VTK to CSV conversion started at $(date '+%Y-%m-%d %H:%M:%S')"
echo "Converting VTK to CSV..."
echo "  Input:  $MAIN_VTK"
echo "  Output: $CSV_OUTPUT"

# Activate conda environment if available (try multiple common environment names)
# First, ensure conda is initialized for non-interactive shells
if [ -f /local/home/liubov_kurafeeva/miniforge3/etc/profile.d/conda.sh ]; then
    source /local/home/liubov_kurafeeva/miniforge3/etc/profile.d/conda.sh
elif [ -f ~/miniforge3/etc/profile.d/conda.sh ]; then
    source ~/miniforge3/etc/profile.d/conda.sh
elif [ -f ~/miniconda3/etc/profile.d/conda.sh ]; then
    source ~/miniconda3/etc/profile.d/conda.sh
fi

if command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook)" 2>/dev/null || true
    # Try meshio_env first (common on remote machines), then cfdaai
    conda activate meshio_env 2>/dev/null || conda activate cfdaai 2>/dev/null || true
fi

# Convert VTK to CSV
if python3 "$SCRIPT_DIR/vtk_to_csv.py" "$MAIN_VTK" "$CSV_OUTPUT" 2>&1; then
    if [ -f "$CSV_OUTPUT" ]; then
        CSV_END=$(date '+%s')
        CSV_ELAPSED=$((CSV_END - CSV_START))
        echo "[TIMER] VTK to CSV conversion completed - Duration: ${CSV_ELAPSED}s"
        echo "CSV created successfully: $CSV_OUTPUT"
        
        # Immediately delete VTK files - we have the CSV now
        echo "Deleting VTK files..."
        rm -rf ./VTK 2>/dev/null || true
        find . -type f -name "*.vtk" -delete 2>/dev/null || true
        echo "VTK files deleted"
    else
        echo "ERROR: CSV file was not created: $CSV_OUTPUT"
        exit 1
    fi
else
    echo "ERROR: VTK to CSV conversion failed"
    echo "ERROR: Check if vtk_to_csv.py exists and meshio is installed"
    exit 1
fi

PROCESS_END_TIME=$(date '+%s')
PROCESS_ELAPSED=$((PROCESS_END_TIME - PROCESS_START_TIME))

echo "================================================"
echo "Results processing complete"
echo "  CSV: $CSV_OUTPUT"
echo "[TIMER] Total results processing time: $(format_duration $PROCESS_ELAPSED) (${PROCESS_ELAPSED}s)"
echo "[TIMER] Results processing completed at $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"

exit 0

