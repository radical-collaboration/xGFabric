#!/bin/bash
#SBATCH --job-name=pinn_train
#SBATCH --account=m5290
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --qos=regular
#SBATCH --time=00:30:00
#SBATCH --output=/global/homes/k/kurl/jobs_logs/%x_%j.out
#SBATCH --error=/global/homes/k/kurl/jobs_logs/%x_%j.err
#
# pinn_train_slurm.sh - SLURM job for PINN training on CPU
#
# Submit:
#   sbatch slurm/pinn_train_slurm.sh <data_dir> <output_dir>

# Don't exit on error during module loading
set -x

################################################################################
# Configuration
################################################################################

# Use absolute path - SLURM copies scripts to compute nodes
WORK_DIR="${WORK_DIR:-/global/common/software/m5290/kurl_system/intheloop}"
# NERSC_TRAIN_WORK_DIR: read-only installation with Python training scripts
TRAIN_WORK_DIR="${NERSC_TRAIN_WORK_DIR:-${WORK_DIR}}"

# Arguments
DATA_DIR="${1:?Data directory required}"
OUTPUT_DIR="${2:?Output directory required}"
TRAIN_SCRIPT="${3:-${TRAIN_WORK_DIR}/training/pinn/train_pinn.py}"
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

module load conda || true
source "$(conda info --base)/etc/profile.d/conda.sh"
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

################################################################################
# Send model artifacts via CSPOT (runs on NERSC before results sync back)
# Controlled by SENSPOT_SEND_MODELS env var (passed via sbatch --export).
################################################################################

SENSPOT_SEND_MODELS="${SENSPOT_SEND_MODELS:-true}"
SENSPOT_MODELS_ENDPOINT="${SENSPOT_MODELS_ENDPOINT:-woof://169.231.230.76/sharedfs/models}"
SENSPOT_KEEP_ARCHIVES="${SENSPOT_KEEP_ARCHIVES:-false}"

if [[ "$SENSPOT_SEND_MODELS" == "true" ]]; then
    echo "[SENSPOT] Locating senspot-file-send..."
    SENSPOT_BIN=""
    for _spath in \
        "$HOME/common/cspot/build/bin" \
        "$HOME/bin" \
        "/global/common/software/m5290/cspot/build/bin"; do
        if [[ -x "${_spath}/senspot-file-send" ]]; then
            SENSPOT_BIN="${_spath}/senspot-file-send"
            break
        fi
    done
    command -v senspot-file-send &>/dev/null && SENSPOT_BIN="$(command -v senspot-file-send)"

    if [[ -z "$SENSPOT_BIN" ]]; then
        echo "[SENSPOT] senspot-file-send not found — skipping model upload"
    else
        echo "[SENSPOT] Using: ${SENSPOT_BIN}"
        ARCHIVE_NAME="pinn_${SLURM_JOB_ID}_$(date +%Y%m%d_%H%M%S).tar.gz"
        ARCHIVE_PATH="${OUTPUT_DIR}/${ARCHIVE_NAME}"
        WOOF_ENDPOINT="${SENSPOT_MODELS_ENDPOINT}/pinn.sb.woof"

        # Gather PINN model files
        mapfile -t _PINN_FILES < <(find "$OUTPUT_DIR" -maxdepth 4 -type f \( \
            -name "*.weights.h5" \
            -o -name "*.normalization.json" \
            -o -name "*.model_meta.json" \
            -o -name "*.run.json" \
        \) 2>/dev/null)

        if [[ ${#_PINN_FILES[@]} -eq 0 ]]; then
            echo "[SENSPOT] No PINN model files found in ${OUTPUT_DIR} — skipping archive"
        else
            echo "[SENSPOT] Archiving ${#_PINN_FILES[@]} files → ${ARCHIVE_NAME}"
            pushd "$OUTPUT_DIR" > /dev/null
            _REL_FILES=()
            for _f in "${_PINN_FILES[@]}"; do _REL_FILES+=("${_f#${OUTPUT_DIR}/}"); done
            tar -czf "$ARCHIVE_PATH" "${_REL_FILES[@]}" 2>/dev/null && echo "[SENSPOT] Archive created: $(du -h "$ARCHIVE_PATH" | cut -f1)"
            popd > /dev/null

            echo "[SENSPOT] Sending to: ${WOOF_ENDPOINT}"
            SEND_LOG="${OUTPUT_DIR}/senspot_pinn_${SLURM_JOB_ID}.log"
            if "$SENSPOT_BIN" -f "$ARCHIVE_PATH" -W "$WOOF_ENDPOINT" -V > "$SEND_LOG" 2>&1; then
                echo "[SENSPOT] ✓ Model sent successfully"
                [[ "$SENSPOT_KEEP_ARCHIVES" != "true" ]] && rm -f "$ARCHIVE_PATH" && echo "[SENSPOT] Local archive removed"
            else
                echo "[SENSPOT] ✗ Send failed — archive kept at: ${ARCHIVE_PATH}"
                echo "[SENSPOT] Details: ${SEND_LOG}"
            fi
        fi
    fi
fi

echo "======================================================="
echo "Job ${SLURM_JOB_ID} finished at $(date)"
echo "======================================================="
