#!/bin/bash
#SBATCH --job-name=pcr_train
#SBATCH --account=m5290
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=00:05:00
#SBATCH --output=/global/homes/k/kurl/jobs_logs/%x_%A_%a.out
#SBATCH --error=/global/homes/k/kurl/jobs_logs/%x_%A_%a.err
#
# pcr_train_slurm.sh - SLURM job for PCR training partition
#
# Submit as array job:
#   sbatch --array=0-N slurm/pcr_train_slurm.sh <partitions_dir> <output_dir>
# Or single partition:
#   sbatch slurm/pcr_train_slurm.sh <partitions_dir> <output_dir>

# Don't exit on error during module loading
set -x

################################################################################
# Configuration
################################################################################

# Use absolute path - SLURM copies scripts to compute nodes
WORK_DIR="/global/common/software/m5290/kurl_system/intheloop"

# Arguments
PARTITIONS_DIR="${1:?Partitions directory required}"
OUTPUT_DIR="${2:?Output directory required}"

# SLURM array index (default 0 for non-array jobs)
PARTITION_ID="${SLURM_ARRAY_TASK_ID:-0}"

echo "======================================================="
echo "SLURM job ${SLURM_JOB_ID}  PCR Training - Partition ${PARTITION_ID}"
echo "Partitions dir : ${PARTITIONS_DIR}"
echo "Output dir     : ${OUTPUT_DIR}"
echo "Node           : $(hostname)  started at $(date)"
echo "======================================================="

################################################################################
# Environment - Simple: just conda
################################################################################

module load conda || true
source "$(conda info --base)/etc/profile.d/conda.sh"
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
DATA_FILE="${PARTITIONS_DIR}/machine_${PARTITION_ID}_data.pkl"

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
echo "Job ${SLURM_JOB_ID} Partition ${PARTITION_ID} finished at $(date)"
echo "======================================================="
