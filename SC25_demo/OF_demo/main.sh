#!/bin/bash

################################################################################
# OpenFOAM Simulation Manager
# 
# Main entry point for running simulations with custom windspeed parameters.
# Workflow: unzip -> setup -> submit job (OF_simulation.sh runs in queue)
#
# Usage: ./main.sh <zip-file> <threads> <windspeed> <winddir>
# Example: ./main.sh cups_structure.zip 16 2.5 NW
################################################################################

# Set defaults if no arguments provided
if [ "$#" -eq 0 ]; then
    set -- "cups_structure.zip" "64"
fi

# Show help if requested
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << EOF
OpenFOAM Simulation Manager

Usage: $0 [<zip-file> <threads> <windspeed> <winddir>]

Arguments (all optional, defaults shown):
  zip-file        Input zip file (default: cups_structure.zip)
  threads         Number of threads (default: 64)
  windspeed       Wind speed in m/s (default: 5)
  winddir         Wind direction in cardinal coordinates (default: NW)

Examples:
  $0                              # Uses defaults: cups_structure.zip 64 5 NW
  $0 cups_structure.zip 16 2.5 NW # Custom threads and windspeed

EOF
    exit 0
fi

ZIP_FILE="$1"
THREADS="$2"
WIND_SPEED="$3"
WIND_DIR="${4}"

# Check sub-directories
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}/utils"

if conda env list | grep -q "xgfabric"
then
    echo "xGFabric conda environment has already been installed"
else
    echo "creating fabric environment"
    conda env create -f environment.yml
fi
# activate xgfabric conda environment
conda activate xgfabric 2>/dev/null || true


# Make sure that the environment is setup
cd "$UTILS_DIR"
sh env_setup.sh || exit 1
cd ..

set -e

# Validation
[ -f "$ZIP_FILE" ] || { echo "Error: zip file not found: $ZIP_FILE"; exit 1; }
[[ "$THREADS" =~ ^[0-9]+$ ]] && [ "$THREADS" -gt 0 ] || { echo "Error: threads must be positive integer"; exit 1; }

# Load most recent online data
b=$(senspot-get -W woof://169.231.230.76/sharedfs/unl-data/daviscupsout)
vals=$(awk -F" " '{print $1}' <<< "$b")

# check if values came from args
if [ -z "$WIND_SPEED" ]; then
    WIND_SPEED=$(awk -F":" '{print $4}' <<< "$vals")
fi

if [ -z "$WIND_DIR" ]; then
    WIND_DIR=$(awk -F":" '{print $7}' <<< "$vals")
fi

# Woof might be down, so hard-code the values
if [ -z "$WIND_SPEED" ]; then
    WIND_SPEED=5
fi

if [ -z "$WIND_DIR" ]; then
    WIND_DIR="NW"
fi

# Create case directory with timestamp (in same directory as main.sh)
CASE_DIR="${WORK_DIR}/cups_structure_ws${WIND_SPEED}_${WIND_DIR}_$(date '+%y-%m-%d_%H_%M_%S')"
START=$(date '+%s.%N')

echo "================================================"
echo "OpenFOAM Simulation Setup"
echo "================================================"
echo "Case:      $CASE_DIR"
echo "Threads:   $THREADS"
echo "Windspeed: $WIND_SPEED m/s"
echo "Wind direction: $WIND_DIR"
echo "================================================"

# Step 1: Extract zip file
echo "Extracting case..."
unzip -q "$ZIP_FILE" -d "$CASE_DIR"
if [ -d "$CASE_DIR/cups_structure" ]; then
    mv "$CASE_DIR/cups_structure"/* "$CASE_DIR"/ 2>/dev/null || true
    rmdir "$CASE_DIR/cups_structure" 2>/dev/null || true
fi

# Step 2: Set windspeed
echo "Setting windspeed to $WIND_SPEED..."
python3 $UTILS_DIR/set_windspeed.py $CASE_DIR $WIND_SPEED $WIND_DIR

# Step 3: Configure parallel decomposition
echo "Configuring for $THREADS threads..."
python3 "$UTILS_DIR/replace.py" "$CASE_DIR/system/decomposeParDict" "$CASE_DIR/system/decomposeParDict" @ "$THREADS"

# Step 4: Submit simulation job to queue
echo "Submitting simulation job to queue..."
QSUB_SCRIPT="/tmp/of_sim_$$.sh"
cat > "$QSUB_SCRIPT" << EOF
#!/bin/bash
#\$ -q long
#\$ -pe smp $THREADS
#\$ -o $CASE_DIR/job.out
#\$ -e $CASE_DIR/job.err

bash $UTILS_DIR/OF_simulation.sh "$CASE_DIR"
EOF

chmod +x "$QSUB_SCRIPT"
JOB_OUTPUT=$(qsub "$QSUB_SCRIPT" 2>&1)


JOB_ID=$(echo "$JOB_OUTPUT" | grep -oE '[0-9]+' | head -1)
echo "$JOB_OUTPUT"

if [ -z "$JOB_ID" ]; then
    echo "Error: Failed to extract job ID"
    exit 1
fi

echo "Job ID: $JOB_ID"

# Step 5: Monitor job completion
echo "Monitoring job $JOB_ID..."
while true; do
    if ! qstat -j "$JOB_ID" >/dev/null 2>&1; then
        echo "Job $JOB_ID completed"
        break
    fi
    sleep 10
done

rm "$QSUB_SCRIPT" || echo "Couldn't remove Qsub Script"
# Step 6: Process results and create export/GIF
echo "Processing results (export to CSV and create GIF)..."
bash "$UTILS_DIR/process_results.sh" "$CASE_DIR" "$WORK_DIR"

END=$(date '+%s.%N')
ELAPSED=$(bc -l <<< "$END - $START")

echo "================================================"
echo "Simulation complete in $ELAPSED seconds"
echo "Case directory: $CASE_DIR"
echo "================================================"
