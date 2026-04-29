#!/bin/bash
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
conda activate cfdaai

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
    "pinn" \
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

# Load system libraries
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"

# Create archive directory
archive_dir="${OUTPUT_DIR}/archives"
ensure_dir "$archive_dir"

# Generate archive filename with timestamp
timestamp=$(date +%Y%m%d_%H%M%S)
archive_name="pinn.tar.gz"
archive_path="${archive_dir}/${archive_name}"

# Determine which files to archive based on model type
files_to_archive=()
mapfile -t files_to_archive < <(find "$OUTPUT_DIR" -type f \( -name '*.weights.h5' -o -name '*.normalization.json' -o -name '*.model_meta.json' -o -name '*.run.json' \) 2>/dev/null)

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
