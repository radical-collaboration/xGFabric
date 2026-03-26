#!/bin/bash
#
# env_nersc.sh - NERSC Perlmutter environment setup
#
# This script is sourced by system_config.sh when SYSTEM_TYPE=nersc
# Sets up: modules, OpenFOAM, conda, GPU support

# Don't use set -e here - we want partial failures to be ok
# set -e

log_info "Loading NERSC environment..."

################################################################################
# Module Setup
################################################################################

# Purge existing modules for clean slate
module purge 2>/dev/null || true

# Load required modules (continue on failure)
module load gcc/12.2.0 2>/dev/null || true
module load cmake/3.30.2 2>/dev/null || true

# Only load spack/openmpi for simulation jobs, not training
if [[ "${SKIP_SPACK_LOAD:-false}" != "true" ]]; then
    module load spack 2>/dev/null || true
    spack load openmpi@4.1.5 2>/dev/null || true
fi

# Paraview (optional, for visualization)
module load paraview 2>/dev/null || true

################################################################################
# CSPOT Setup
################################################################################

CSPOT_BIN="/global/common/software/m5290/cspot/build/bin"
if [[ -d "$CSPOT_BIN" ]]; then
    case ":$PATH:" in
        *:${CSPOT_BIN}:*)
            ;;
        *)
            export PATH="${CSPOT_BIN}${PATH:+:${PATH}}"
            ;;
    esac
    log_info "CSPOT loaded from: ${CSPOT_BIN}"
    export HAS_CSPOT=true
else
    log_warn "CSPOT not found at: ${CSPOT_BIN}"
    export HAS_CSPOT=false
fi

################################################################################
# Conda Setup
################################################################################

# Load conda module if not already available
if ! command -v conda &>/dev/null; then
    module load conda
fi

# Initialize conda for this shell
source "$(conda info --base)/etc/profile.d/conda.sh"

# Activate environment
CONDA_ENV="${CONDA_ENV:-cfdai_intheloop}"
ENV_FILE="${WORK_DIR}/utils/environment.yml"

if conda env list | grep -q "^${CONDA_ENV}[[:space:]]"; then
    log_info "Activating conda environment: ${CONDA_ENV}"
    conda activate "${CONDA_ENV}"
else
    log_warn "Conda environment '${CONDA_ENV}' not found"
    if [[ -f "$ENV_FILE" ]]; then
        log_info "Creating environment from: ${ENV_FILE}"
        conda env create -f "$ENV_FILE" -n "${CONDA_ENV}"
        conda activate "${CONDA_ENV}"
    else
        log_error "Environment file not found: ${ENV_FILE}"
        return 1
    fi
fi

################################################################################
# OpenFOAM Setup
################################################################################

# OpenFOAM bashrc references ZSH_NAME which may be unset
export ZSH_NAME=""

# Temporarily disable strict mode for OpenFOAM sourcing
set +u
if [[ -f "${OPENFOAM_ROOT}/OpenFOAM-dev/etc/bashrc" ]]; then
    source "${OPENFOAM_ROOT}/OpenFOAM-dev/etc/bashrc" 2>/dev/null || true
    log_info "OpenFOAM loaded from: ${OPENFOAM_ROOT}"
else
    log_warn "OpenFOAM bashrc not found at: ${OPENFOAM_ROOT}/OpenFOAM-dev/etc/bashrc"
fi
set -u

################################################################################
# GPU Setup (if requested)
################################################################################

if [[ "${NEED_GPU:-false}" == "true" ]] || [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
    log_info "Setting up GPU environment..."
    module load cudatoolkit 2>/dev/null || true
    module load cudnn/8.9.3_cuda12 2>/dev/null || true
    
    # TensorFlow configuration
    export TF_CPP_MIN_LOG_LEVEL=2
    export TF_FORCE_GPU_ALLOW_GROWTH=true
fi

################################################################################
# SLURM-specific Configuration
################################################################################

# Set MPI runner for SLURM environment
export MPI_RUNNER="srun"

# Job logs directory
export JOBS_LOG_DIR="${JOBS_LOG_DIR:-/global/homes/${USER:0:1}/${USER}/jobs_logs}"
mkdir -p "$JOBS_LOG_DIR" 2>/dev/null || true

################################################################################
# Verify Setup
################################################################################

# Auto-install missing Python packages
install_missing_packages() {
    local env_file="${WORK_DIR}/utils/environment.yml"
    local missing_packages=()
    
    # Required packages (must be importable)
    local required_packages=(
        "numpy"
        "pandas"
        "sklearn:scikit-learn"  # import_name:package_name
        "h5py"
        "matplotlib"
    )
    
    for pkg_spec in "${required_packages[@]}"; do
        # Parse import_name:package_name format
        local import_name="${pkg_spec%%:*}"
        local package_name="${pkg_spec##*:}"
        
        if ! python3 -c "import ${import_name}" &>/dev/null 2>&1; then
            log_warn "Python package ${package_name} not available - will install"
            missing_packages+=("$package_name")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        log_info "Installing missing packages: ${missing_packages[*]}"
        
        # Try conda first, fall back to pip
        for pkg in "${missing_packages[@]}"; do
            if conda install -y "$pkg" 2>/dev/null; then
                log_info "Installed ${pkg} via conda"
            elif pip install "$pkg" 2>/dev/null; then
                log_info "Installed ${pkg} via pip"
            else
                log_error "Failed to install ${pkg}"
            fi
        done
    fi
}

verify_nersc_env() {
    local errors=0
    
    # Check Python
    if ! python3 --version &>/dev/null; then
        log_error "Python3 not available"
        errors=$((errors + 1))
    fi
    
    # Auto-install missing packages
    install_missing_packages
    
    # Verify critical packages are now available
    for pkg in numpy pandas sklearn; do
        if ! python3 -c "import ${pkg}" &>/dev/null 2>&1; then
            log_error "Python package ${pkg} still not available after install attempt"
            errors=$((errors + 1))
        fi
    done
    
    # Check OpenFOAM (optional for some tasks)
    if command -v foamToVTK &>/dev/null; then
        log_info "OpenFOAM tools verified"
    else
        log_warn "OpenFOAM foamToVTK not found"
    fi
    
    return $errors
}

# Run verification
verify_nersc_env || log_warn "Some environment checks failed"

log_info "NERSC environment setup complete"
