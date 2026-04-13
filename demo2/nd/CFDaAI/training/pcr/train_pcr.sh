#!/bin/bash

set -e

log_info() { echo "[INFO] $(date '+%H:%M:%S') $1"; }
log_warn() { echo "[WARN] $(date '+%H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $1" >&2; }

# Timing utilities
SCRIPT_START_TIME=$(date +%s)

log_time_start() {
    local section="$1"
    START_TIME=$(date +%s)
}

log_time_end() {
    local section="$1"
    local end_time=$(date +%s)
    local duration=$((end_time - START_TIME))
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))
    log_info "[TIMER] $section: ${hours}h ${minutes}m ${seconds}s"
}

# Get script directory
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load grid configuration from grid_config.json
source "${WORK_DIR}/training/pcr/read_grid_config.sh"

################################################################################
# Usage and Argument Parsing
################################################################################
usage() {
    echo "Usage: $0 <sensor_folder> [options]"
    echo ""
    echo "Arguments:"
    echo "  sensor_folder         Path to folder containing sensor_out.csv"
    echo ""
    echo "Options:"
    echo "  --simulations-dir     Path to simulations CSVs (default: data/simulations)"
    echo "  --nx                  Number of points in X (default: ${GRID_NX} from grid_config.json)"
    echo "  --ny                  Number of points in Y (default: ${GRID_NY} from grid_config.json)"
    echo "  --nz                  Number of points in Z (default: ${GRID_NZ} from grid_config.json)"
    echo "  --column              Column to use: windavg or windspeed (default: windavg)"
    echo "  --output-dir          Output directory for coefficients (default: training/data)"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 /local/foam/cases/data/case4/period1"
    echo "  $0 /local/foam/cases/data/case4/period1 --nx 20 --ny 10 --nz 5"
    exit 1
}

# Default values
SENSOR_FOLDER=""
SIMULATIONS_DIR="${WORK_DIR}/data/simulations"
# Grid configuration from grid_config.json
NX=$GRID_NX
NY=$GRID_NY
NZ=$GRID_NZ
# TEST GRID: 6x3x2 = 36 points (~2 per machine)
# NX=6
# NY=3
# NZ=2
COLUMN="windavg"
OUTPUT_DIR="${WORK_DIR}/training/data"

if [ $# -lt 1 ]; then
    usage
fi

SENSOR_FOLDER="$1"
shift

while [ $# -gt 0 ]; do
    case "$1" in
        --simulations-dir)
            SIMULATIONS_DIR="$2"
            shift 2
            ;;
        --nx)
            NX="$2"
            shift 2
            ;;
        --ny)
            NY="$2"
            shift 2
            ;;
        --nz)
            NZ="$2"
            shift 2
            ;;
        --column)
            COLUMN="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --training-mode)
            TRAINING_MODE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate arguments
if [ ! -d "$SENSOR_FOLDER" ]; then
    log_error "Sensor folder does not exist: $SENSOR_FOLDER"
    exit 1
fi

if [ ! -d "$SIMULATIONS_DIR" ]; then
    log_error "Simulations directory does not exist: $SIMULATIONS_DIR"
    exit 1
fi

################################################################################
# Environment Setup
################################################################################
log_time_start "Environment Setup"
log_info "--- Environment Setup ---"

source ~/.bashrc 2>/dev/null || true

# Conda environment setup
CONDA_ENV_NAME="cfdaai"
CONDA_ENV_FILE="${WORK_DIR}/utils/environment.yml"

log_info "Checking for conda environment: ${CONDA_ENV_NAME}"

# Check if conda is available
if ! command -v conda &> /dev/null; then
    log_error "conda is not available. Please install conda/miniconda/miniforge first."
    exit 1
fi

# Initialize conda for bash
eval "$(conda shell.bash hook)" 2>/dev/null || true

# Check if environment exists
if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
    log_info "Conda environment '${CONDA_ENV_NAME}' found. Activating..."
else
    log_info "Conda environment '${CONDA_ENV_NAME}' not found. Creating..."
    if [ -f "$CONDA_ENV_FILE" ]; then
        log_info "Creating environment from ${CONDA_ENV_FILE}"
        conda env create -f "$CONDA_ENV_FILE" -n "${CONDA_ENV_NAME}"
        log_info "Environment created successfully"
    else
        log_error "Environment file not found: ${CONDA_ENV_FILE}"
        exit 1
    fi
fi
conda activate "${CONDA_ENV_NAME}"

# Verify critical packages are installed
log_info "Verifying critical packages..."
for pkg in pandas numpy scikit-learn; do
    if ! python3 -c "import ${pkg//-/_}" 2>/dev/null; then
        log_warn "${pkg} not found, installing..."
        pip install "${pkg}"
    fi
done

log_info "Environment setup complete (using conda env: ${CONDA_ENV_NAME})"
log_time_end "Environment Setup"

################################################################################
# PCR Training
################################################################################
log_time_start "PCR Field Training"
log_info "--- PCR Field Training ---"

log_info "Configuration:"
log_info "  Sensor folder: $SENSOR_FOLDER"
log_info "  Simulations directory: $SIMULATIONS_DIR"
log_info "  Grid: ${NX} x ${NY} x ${NZ}"
log_info "  Column: $COLUMN"
log_info "  Output directory: $OUTPUT_DIR"

# Create output directory
mkdir -p "$OUTPUT_DIR"

TRAINING_LOG="${OUTPUT_DIR}/pcr_training.log"
log_info "Log file: $TRAINING_LOG"

# Use Python scikit-learn based training
log_info "Using Python scikit-learn for training..."

cd "$WORK_DIR"

if python3 training/pcr/train_field_of_pcr.py \
        "$SENSOR_FOLDER" \
        "$SIMULATIONS_DIR" \
        --nx "$NX" \
        --ny "$NY" \
        --nz "$NZ" \
        --column "$COLUMN" \
        --output_dir "$OUTPUT_DIR" \
        > "$TRAINING_LOG" 2>&1; then
        
        log_info "PCR training (Python) completed successfully"
        
        # Count generated coefficient files
        COEF_COUNT=$(find "$OUTPUT_DIR" -name "pcr_coefficients_*.csv" 2>/dev/null | wc -l)
        log_info "Generated $COEF_COUNT coefficient files"
        
else
    log_error "PCR training failed - check logs: $TRAINING_LOG"
    tail -30 "$TRAINING_LOG"
    exit 1
fi

log_time_end "PCR Field Training"

################################################################################
# Summary
################################################################################
log_info "PCR training complete: ${NX}x${NY}x${NZ} grid -> $OUTPUT_DIR"
log_info "Coefficients: $(ls "$OUTPUT_DIR"/pcr_coefficients_*.csv 2>/dev/null | wc -l) files"

# Calculate and display total execution time
SCRIPT_END_TIME=$(date +%s)
TOTAL_DURATION=$((SCRIPT_END_TIME - SCRIPT_START_TIME))
TOTAL_HOURS=$((TOTAL_DURATION / 3600))
TOTAL_MINUTES=$(((TOTAL_DURATION % 3600) / 60))
TOTAL_SECONDS=$((TOTAL_DURATION % 60))

log_info "[TIMER] Total: ${TOTAL_HOURS}h ${TOTAL_MINUTES}m ${TOTAL_SECONDS}s"
