#!/bin/bash
#
# pinn_train_slurm.sh - SLURM job for PINN training on CPU
#
# Submit:
#   sbatch slurm/pinn_train_slurm.sh <data_dir> <output_dir>

# Don't exit on error during module loading
# set -x

################################################################################
# Configuration
################################################################################

# Arguments
DATA_DIR="${1:?Data directory required}"
OUTPUT_DIR="${2:?Output directory required}"
TRAIN_SCRIPT="${3:-${WORK_DIR}/training/pinn/train_pinn.py}"
EXTRA_ARGS="${4:-}"

echo "======================================================="
echo "SLURM job ${SLURM_JOB_ID}  PINN Training"
echo "Data dir       : ${DATA_DIR}"
echo "Output dir     : ${OUTPUT_DIR}"
echo "Node           : $(hostname)  started at $(date)"
echo "======================================================="

################################################################################
# Environment - Simple: just conda for TensorFlow
# (No spack/openmpi/OpenFOAM needed for training)
################################################################################

conda activate cfdaai

# Now enable exit on error
set -e

export TF_CPP_MIN_LOG_LEVEL=2

echo "Environment loaded: $(which python3)"
echo "TensorFlow: $(python3 -c 'import tensorflow as tf; print(tf.__version__)')"

################################################################################
# Run Training
################################################################################

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$TRAIN_SCRIPT" ]]; then
    echo "ERROR: Training script not found: ${TRAIN_SCRIPT}"
    exit 1
fi

# Run from WORK_DIR, not OUTPUT_DIR
cd "$TRAIN_WORK_DIR"

srun -n 1 python3 "$TRAIN_SCRIPT" \
    "$DATA_DIR" \
    "pinn_model" \
    --output_dir "$OUTPUT_DIR" \
    --subsample 20 \
    --epochs 5 \
    --cpoints 500 \
    --learning_rate 1e-4 \
    --patience 3 \
    --test_size 0.15 \
    --val_size 0.1 \
    $EXTRA_ARGS

echo "======================================================="
echo "Job ${SLURM_JOB_ID} training finished at $(date)"
echo "======================================================="
