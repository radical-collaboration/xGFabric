#!/bin/bash
#
# env_ucsb.sh - UCSB local cluster environment setup
#
# This script is sourced by system_config.sh when SYSTEM_TYPE=ucsb
# Sets up: conda, OpenFOAM, SSH configuration

# Note: We don't use strict error checking here because conda and OpenFOAM
# activation scripts may have unbound variables
# set -e

log_info "Loading UCSB environment..."

################################################################################
# Shell Initialization
################################################################################

# Source user's bashrc for any custom setup
source ~/.bashrc 2>/dev/null || true

################################################################################
# Conda Setup
################################################################################

# Find and initialize conda
CONDA_INITIALIZED=false
for conda_path in \
    "$HOME/miniforge3/etc/profile.d/conda.sh" \
    "$HOME/miniconda3/etc/profile.d/conda.sh" \
    "$HOME/anaconda3/etc/profile.d/conda.sh" \
    "/local/home/$USER/miniforge3/etc/profile.d/conda.sh" \
    "/opt/conda/etc/profile.d/conda.sh"; do
    if [[ -f "$conda_path" ]]; then
        source "$conda_path"
        CONDA_INITIALIZED=true
        log_info "Conda initialized from: ${conda_path}"
        break
    fi
done

if [[ "$CONDA_INITIALIZED" != "true" ]]; then
    log_error "Conda not found. Please install miniconda/miniforge."
    return 1
fi

# Activate environment
CONDA_ENV="${CONDA_ENV:-cfdaai}"
ENV_FILE="${WORK_DIR}/utils/environment.yml"

# Check if environment exists
if conda env list | grep -q "^${CONDA_ENV}[[:space:]]"; then
    log_info "Using conda environment: ${CONDA_ENV}"
    # Get the environment path and add to PATH instead of activating
    # This avoids issues with conda activate in sourced scripts
    CONDA_ENV_PATH=$(conda env list | grep "^${CONDA_ENV}[[:space:]]" | awk '{print $NF}')
    export PATH="${CONDA_ENV_PATH}/bin:$PATH"
    export PYTHONPATH="${CONDA_ENV_PATH}/lib/python3.*/site-packages:${PYTHONPATH:-}"
else
    log_warn "Conda environment '${CONDA_ENV}' not found"
    if [[ -f "$ENV_FILE" ]]; then
        log_info "Please create environment first: conda env create -f ${ENV_FILE} -n ${CONDA_ENV}"
        return 1
    else
        log_error "Environment file not found: ${ENV_FILE}"
        return 1
    fi
fi

################################################################################
# OpenFOAM Setup
################################################################################

OPENFOAM_BASHRC="${OPENFOAM_ROOT}/etc/bashrc"

if [[ -f "$OPENFOAM_BASHRC" ]]; then
    log_info "OpenFOAM found at: ${OPENFOAM_ROOT}"
    log_info "Note: OpenFOAM will be sourced in simulation scripts, not globally"
    # Don't source OpenFOAM globally as it can interfere with other tools
    # Export the path for simulation scripts to use
    export FOAM_BASHRC="$OPENFOAM_BASHRC"
else
    log_warn "OpenFOAM bashrc not found at: ${OPENFOAM_BASHRC}"
    log_warn "Simulations may fail if OpenFOAM is not available"
fi

################################################################################
# SSH Configuration (for parallel execution)
################################################################################

if [[ "$HAS_MACHINE_LIST" == "true" ]]; then
    # Ensure SSH key has correct permissions
    if [[ -f "$SSH_KEY_PATH" ]]; then
        chmod 600 "$SSH_KEY_PATH" 2>/dev/null || true
    fi
    
    # SSH options for parallel execution
    export SSH_OPTIONS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -i ${SSH_KEY_PATH}"
    export REMOTE_USER="$(whoami)"
    
    log_info "SSH configured for parallel execution (${MACHINE_COUNT} machines)"
fi

################################################################################
# MPI Configuration
################################################################################

# Set MPI runner for local execution
export MPI_RUNNER="mpirun"

################################################################################
# Verify Setup
################################################################################

verify_ucsb_env() {
    local errors=0
    
    # Check Python
    if ! python3 --version &>/dev/null; then
        log_error "Python3 not available"
        errors=$((errors + 1))
    fi
    
    # Check critical Python packages (skip for now to avoid hanging)
    # for pkg in numpy pandas scikit-learn meshio; do
    #     if ! python3 -c "import ${pkg//-/_}" &>/dev/null; then
    #         log_warn "Python package ${pkg} not available, installing..."
    #         pip install "${pkg}" 2>/dev/null || true
    #     fi
    # done
    
    # Check OpenFOAM
    if command -v foamToVTK &>/dev/null; then
        log_info "OpenFOAM tools verified"
    else
        log_warn "OpenFOAM foamToVTK not found"
    fi
    
    return $errors
}

# Run verification (non-blocking)
verify_ucsb_env || log_warn "Some environment checks failed"

log_info "UCSB environment setup complete"
