#!/bin/bash
#$ -N fno_train
#
# fno_train_uge.sh - UGE job for FNO training on CPU
#
# Submit:
#   qsub uge/fno_train_uge.sh <data_dir> <output_dir>
#
# Optional iteration range (via --export):
#   qsub --export=ALL,ITER_MIN=200,ITER_MAX=500 uge/fno_train_uge.sh <data_dir> <output_dir>

# Don't exit on error during module loading
# set -x

echo "workflow_$WORKFLOW_NUMBER,fno_train,running,$(date '+%s.%N')" >> "$STATUS_FILE"

################################################################################
# Configuration
################################################################################

# Use absolute path - UGE copies scripts to compute nodes
WORK_DIR="$(pwd)"

# Arguments
DATA_DIR="${1:?Data directory required}"
OUTPUT_DIR="${2:?Output directory required}"
TRAIN_SCRIPT="${3:-${WORK_DIR}/training/fno/train_fno.py}"
EXTRA_ARGS="${4:-}"

# Iteration range (optional, for multi-iteration format)
ITER_MIN=${ITER_MIN:-}
ITER_MAX=${ITER_MAX:-}

echo "======================================================="
echo "UGE job ${JOB_ID}  FNO Training"
if [[ -n "$ITER_MIN" && -n "$ITER_MAX" ]]; then
    echo "Iteration range: [${ITER_MIN}, ${ITER_MAX}]"
else
    echo "Mode: single-file (no iteration range)"
fi
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

# Build command arguments
CMD_ARGS="--data-dir ${DATA_DIR} --output-dir ${OUTPUT_DIR}"
if [[ -n "$ITER_MIN" && -n "$ITER_MAX" ]]; then
    CMD_ARGS="$CMD_ARGS --iter-min ${ITER_MIN} --iter-max ${ITER_MAX}"
fi

python3 "$TRAIN_SCRIPT" \
    $CMD_ARGS \
    --epochs 5 \
    --batch 4 \
    --lr 2e-3 \
    --patience 3 \
    $EXTRA_ARGS

echo "======================================================="
echo "Job ${JOB_ID} finished at $(date)"
echo "======================================================="
