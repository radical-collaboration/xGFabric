#!/bin/bash
#SBATCH --job-name=fno_train
#SBATCH --account=m5290
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --qos=debug
#SBATCH --time=00:15:00
#SBATCH --output=/global/homes/k/kurl/jobs_logs/%x_%j.out
#SBATCH --error=/global/homes/k/kurl/jobs_logs/%x_%j.err
#
# fno_train_slurm_debug.sh - DEBUG queue FNO training (minimal params)
#
# Submit:
#   sbatch slurm/fno_train_slurm_debug.sh <data_dir> <output_dir>

set -x

WORK_DIR="${WORK_DIR:-/global/common/software/m5290/kurl_system/intheloop}"
TRAIN_WORK_DIR="${NERSC_TRAIN_WORK_DIR:-${WORK_DIR}}"

DATA_DIR="${1:?Data directory required}"
OUTPUT_DIR="${2:?Output directory required}"
TRAIN_SCRIPT="${3:-${TRAIN_WORK_DIR}/training/fno/train_fno.py}"
EXTRA_ARGS="${4:-}"

echo "======================================================="
echo "SLURM job ${SLURM_JOB_ID}  FNO Training [DEBUG]"
echo "Data dir       : ${DATA_DIR}"
echo "Output dir     : ${OUTPUT_DIR}"
echo "Node           : $(hostname)  started at $(date)"
echo "======================================================="

module load conda || true
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate cfdai_intheloop

set -e
export TF_CPP_MIN_LOG_LEVEL=2

echo "Environment loaded: $(which python3)"
echo "TensorFlow: $(python3 -c 'import tensorflow as tf; print(tf.__version__)')"

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$TRAIN_SCRIPT" ]]; then
    echo "ERROR: Training script not found: ${TRAIN_SCRIPT}"
    exit 1
fi

srun -n 1 python3 "$TRAIN_SCRIPT" \
    --data-dir "${DATA_DIR}" \
    --output-dir "${OUTPUT_DIR}" \
    --epochs 2 \
    --batch 4 \
    --lr 2e-3 \
    --patience 1 \
    $EXTRA_ARGS

echo "======================================================="
echo "Job ${SLURM_JOB_ID} finished at $(date)"
echo "======================================================="
