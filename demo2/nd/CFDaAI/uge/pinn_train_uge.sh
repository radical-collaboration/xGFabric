#!/bin/bash
#$ -N pinn_train
#
# pinn_train_uge.sh - UGE job for PINN training on CPU
#
# Submit:
#   qsub uge/pinn_train_uge.sh <data_dir> <output_dir>

# Don't exit on error during module loading
# set -x

################################################################################
# Configuration
################################################################################

# Use absolute path - UGE copies scripts to compute nodes
WORK_DIR="$(pwd)"

# Arguments
DATA_DIR="${1:?Data directory required}"
OUTPUT_DIR="${2:?Output directory required}"
TRAIN_SCRIPT="${3:-${WORK_DIR}/training/pinn/train_pinn.py}"
EXTRA_ARGS="${4:-}"

echo "======================================================="
echo "UGE job ${JOB_ID}  PINN Training"
echo "Data dir       : ${DATA_DIR}"
echo "Output dir     : ${OUTPUT_DIR}"
echo "Node           : $(hostname)  started at $(date)"
echo "======================================================="

################################################################################
# Environment - Simple: just conda for TensorFlow
# (No spack/openmpi/OpenFOAM needed for training)
################################################################################
module load cuda 2>/dev/null || true
module load cudnn 2>/dev/null || true
conda activate cfdai_intheloop

# Now enable exit on error
set -e

export TF_CPP_MIN_LOG_LEVEL=2
export TF_ENABLE_ONEDNN_OPTS=0

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
cd "$WORK_DIR"

python3 "$TRAIN_SCRIPT" \
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
echo "Job ${JOB_ID} finished at $(date)"
echo "======================================================="
