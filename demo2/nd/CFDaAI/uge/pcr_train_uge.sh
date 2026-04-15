#!/bin/bash
#$ -N pcr_train
#
# pcr_train_uge.sh - UGE job for PCR training partition
#
# Submit as array job:
#   qsub --array=0-N uge/pcr_train_uge.sh <partitions_dir> <output_dir>
# Or single partition:
#   qsub uge/pcr_train_uge.sh <partitions_dir> <output_dir>

# Don't exit on error during module loading
# set -x

python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "pcr_train" "running" "${STATUS_FILE}"

################################################################################
# Configuration
################################################################################

# Use absolute path - UGE copies scripts to compute nodes
WORK_DIR="$(pwd)"

# Arguments
PARTITIONS_DIR="${1:?Partitions directory required}"
OUTPUT_DIR="${2:?Output directory required}"

echo "======================================================="
echo "UGE job ${JOB_ID} PCR Training"
echo "Partitions dir : ${PARTITIONS_DIR}"
echo "Output dir     : ${OUTPUT_DIR}"
echo "Node           : $(hostname)  started at $(date)"
echo "======================================================="

################################################################################
# Environment - Simple: just conda
################################################################################

conda activate cfdaai

# Now enable exit on error
set -e

echo "Environment loaded: $(which python3)"

################################################################################
# Run Training
################################################################################

TRAIN_SCRIPT="${WORK_DIR}/training/pcr/train_pcr_chunk.py"

if [[ ! -f "$TRAIN_SCRIPT" ]]; then
    echo "ERROR: Training script not found: ${TRAIN_SCRIPT}"
    exit 1
fi

# Find the pre-prepared data file for this partition
DATA_FILE="${PARTITIONS_DIR}/machine_0_data.pkl"

if [[ ! -f "$DATA_FILE" ]]; then
    echo "ERROR: Data file not found: ${DATA_FILE}"
    echo "Available files in ${PARTITIONS_DIR}:"
    ls -la "$PARTITIONS_DIR/"
    exit 1
fi

# Save coefficients directly to output_dir (no partition subdirectory)
mkdir -p "$OUTPUT_DIR"

# train_pcr_chunk.py expects: <data_file> <output_dir>
python3 "$TRAIN_SCRIPT" "$DATA_FILE" "$OUTPUT_DIR"

echo "======================================================="
echo "Job ${JOB_ID} Partition 0 finished at $(date)"
echo "======================================================="
