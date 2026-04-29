#!/bin/bash
#
# pcr_train_uge.sh - UGE job for PCR training partition
#
# Submit as array job:
#   qsub --array=0-N uge/pcr_train_uge.sh <data_dir> <output_dir>
# Or single partition:
#   qsub uge/pcr_train_uge.sh <data_dir> <output_dir>

# Don't exit on error during module loading
# set -x

################################################################################
# Configuration
################################################################################

# Use absolute path - UGE copies scripts to compute nodes
WORK_DIR="$(pwd)"

# Arguments
data_dir="${1:?Partitions directory required}"
OUTPUT_DIR="${2:?Output directory required}"

################################################################################
# Environment - Simple: just conda
################################################################################

conda activate cfdaai

# Now enable exit on error
set -e

echo "Environment loaded: $(which python3)"

################################################################################
# Prepare PCR Training
################################################################################
CONFIG_FILE="${WORK_DIR}/config.sh"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"
# Get sensor data directory from environment (set by main.sh)
sensor_dir="${SENSOR_DATA_DIR:-${RESULTS_DIR}/data}"
grid_config="${WORK_DIR}/training/pcr/grid_config.json"
require_file "$grid_config" "Grid configuration"

if [[ -z "$sensor_dir" || ! -d "$sensor_dir" ]]; then
    log_error "SENSOR_DATA_DIR not set or directory not found"
    log_error "PCR training requires sensor data. Use --use-sensor <dir>"
    exit 1
fi

# Verify sensor_out.csv exists
if [[ ! -f "${sensor_dir}/sensor_out.csv" ]]; then
    log_error "sensor_out.csv not found in ${sensor_dir}"
    log_error "Expected CSV with columns: dt, windspeed, windavg"
    exit 1
fi

log_info "Sensor data: ${sensor_dir}"
log_info "Simulation data: ${data_dir}"
log_info "Grid config: ${grid_config}"

partitions_dir="${OUTPUT_DIR}/partitions"
ensure_dir "$partitions_dir"

# Step 1: Generate partitions from grid config
# Default to 1 partition for single-node training
num_partitions="${PCR_NUM_PARTITIONS:-1}"
partition_script="${WORK_DIR}/training/pcr/partition_pcr_grid.py"
partitions_file="${partitions_dir}/pcr_partitions_full.json"

if [[ -f "$partition_script" ]]; then
    log_info "Partitioning grid into ${num_partitions} partitions..."
    export GRID_CONFIG_PATH="$grid_config"
    pushd "$partitions_dir" > /dev/null
    python3 "$partition_script" "$num_partitions"
    popd > /dev/null
    
    if [[ ! -f "$partitions_file" ]]; then
        log_error "✗ Partitioning failed - ${partitions_file} not created"
        exit 1
    fi
    log_info "✓ Grid partitioned into ${num_partitions} partitions"
else
    log_error "✗ Partition script not found: ${partition_script}"
    exit 1
fi

# Step 2: Prepare data for all partitions
prep_script="${WORK_DIR}/training/pcr/prepare_pcr_data.py"

if [[ -f "$prep_script" ]]; then
    log_info "Preparing PCR data partitions..."
    # Args: sensor_folder simulations_folder partitions_file output_dir
    python3 "$prep_script" "$sensor_dir" "$data_dir" "$partitions_file" "$partitions_dir"
else
    log_error "Data preparation script not found: ${prep_script}"
    exit 1
fi

################################################################################
# Run Training
################################################################################
echo "======================================================="
echo "UGE job ${JOB_ID} PCR Training"
echo "Partitions dir : ${partitions_dir}"
echo "Output dir     : ${OUTPUT_DIR}"
echo "Node           : $(hostname) started at $(date)"
echo "======================================================="

TRAIN_SCRIPT="${WORK_DIR}/training/pcr/train_pcr_chunk.py"

if [[ ! -f "$TRAIN_SCRIPT" ]]; then
    echo "ERROR: Training script not found: ${TRAIN_SCRIPT}"
    exit 1
fi

# Find the pre-prepared data file for this partition
DATA_FILE="${partitions_dir}/machine_0_data.pkl"

if [[ ! -f "$DATA_FILE" ]]; then
    echo "ERROR: Data file not found: ${DATA_FILE}"
    echo "Available files in ${partitions_dir}:"
    ls -la "$partitions_dir/"
    exit 1
fi

# Save coefficients directly to output_dir (no partition subdirectory)
mkdir -p "$OUTPUT_DIR"

# train_pcr_chunk.py expects: <data_file> <output_dir>
python3 "$TRAIN_SCRIPT" "$DATA_FILE" "$OUTPUT_DIR"

echo "======================================================="
echo "Job ${JOB_ID} Partition 0 finished at $(date)"
echo "======================================================="

# Create archive directory
archive_dir="${OUTPUT_DIR}/archives"
ensure_dir "$archive_dir"

# Generate archive filename with timestamp
timestamp=$(date +%Y%m%d_%H%M%S)
archive_name="pcr.tar.gz"
archive_path="${archive_dir}/${archive_name}"

# Determine which files to archive based on model type
files_to_archive=()
mapfile -t files_to_archive < <(find "$OUTPUT_DIR" -type f \( -name 'pcr_coefficients_*.csv' -o -name 'training_summary.json' \) 2>/dev/null)

# Check if we found any files
if [[ ${#files_to_archive[@]} -eq 0 ]]; then
    log_warn "No model files found to archive in: ${OUTPUT_DIR}"
    exit 1
fi

log_info "Found ${#files_to_archive[@]} files to archive"

# Create tar archive (use relative paths within output_dir)
relative_files=()
for file in "${files_to_archive[@]}"; do
    # Use path relative to output_dir, not just basename
    rel_path="${file#$OUTPUT_DIR/}"
    relative_files+=("$rel_path")
done

if tar -czf "$archive_path" -C "$OUTPUT_DIR" "${relative_files[@]}"; then
    archive_size=$(du -h "$archive_path" | cut -f1)
    log_info "✓ Created archive: ${archive_name} (${archive_size})"
else
    log_error "✗ Failed to create archive: ${archive_path}"
    return 1
fi

echo "======================================================="
echo "Finished archiving at $(date)"
echo "======================================================="
