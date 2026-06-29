#!/bin/bash
#
# env_hybrid.sh - Hybrid mode environment setup (UCSB orchestrator + NERSC compute)
#
# This script is sourced by system_config.sh when SYSTEM_TYPE=hybrid.
# The orchestrator always runs on UCSB. This file configures:
#   - Local UCSB paths for simulations/data/pcr (same as env_ucsb.sh)
#   - NERSC SSH connection variables for dispatching pinn/fno remotely

log_info "Loading hybrid environment (UCSB orchestrator + NERSC compute)..."

################################################################################
# Shell Initialization
################################################################################

source ~/.bashrc 2>/dev/null || true

################################################################################
# Conda Setup (local UCSB side)
################################################################################

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

CONDA_ENV="${CONDA_ENV:-cfdaai}"
ENV_FILE="${WORK_DIR}/utils/environment.yml"

if conda env list | grep -q "^${CONDA_ENV}[[:space:]]"; then
    log_info "Using conda environment: ${CONDA_ENV}"
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
# OpenFOAM Setup (local UCSB side)
################################################################################

OPENFOAM_BASHRC="${OPENFOAM_ROOT}/etc/bashrc"

if [[ -f "$OPENFOAM_BASHRC" ]]; then
    log_info "OpenFOAM found at: ${OPENFOAM_ROOT}"
    log_info "Note: OpenFOAM will be sourced in simulation scripts, not globally"
    export FOAM_BASHRC="$OPENFOAM_BASHRC"
else
    log_warn "OpenFOAM bashrc not found at: ${OPENFOAM_BASHRC}"
    log_warn "Local simulations may fail if OpenFOAM is not available"
fi

################################################################################
# SSH Configuration (local UCSB parallel execution)
################################################################################

if [[ "$HAS_MACHINE_LIST" == "true" ]]; then
    if [[ -f "$SSH_KEY_PATH" ]]; then
        chmod 600 "$SSH_KEY_PATH" 2>/dev/null || true
    fi
    export SSH_OPTIONS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -i ${SSH_KEY_PATH}"
    export REMOTE_USER="$(whoami)"
    log_info "SSH configured for local parallel execution (${MACHINE_COUNT} machines)"
fi

################################################################################
# MPI Configuration
################################################################################

export MPI_RUNNER="mpirun"

################################################################################
# NERSC SSH Connection Variables
################################################################################

# These pull from config.sh values with safe defaults.
# config.sh is already sourced before this file runs.
# NOTE: NERSC_SSH_HOST (not NERSC_HOST) is used to avoid collision with the
# NERSC_HOST env var that NERSC itself exports on login nodes.
export NERSC_SSH_HOST="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"
export NERSC_USER="${NERSC_USER:-kurl}"
export NERSC_SSH_KEY="${NERSC_SSH_KEY:-${WORK_DIR}/id_rsa}"
export NERSC_REMOTE_WORK_DIR="${NERSC_REMOTE_WORK_DIR:-/global/homes/k/kurl/intheloop}"
export NERSC_SCRATCH_DIR="${NERSC_SCRATCH_DIR:-/pscratch/sd/k/kurl}"

# Ensure NERSC SSH key has correct permissions
if [[ -f "$NERSC_SSH_KEY" ]]; then
    chmod 600 "$NERSC_SSH_KEY" 2>/dev/null || true
else
    log_warn "NERSC SSH key not found at: ${NERSC_SSH_KEY}"
    log_warn "NERSC-assigned modules will fail at dispatch time"
fi

################################################################################
# Verify Setup
################################################################################

verify_hybrid_env() {
    local errors=0

    if ! python3 --version &>/dev/null; then
        log_error "Python3 not available"
        errors=$((errors + 1))
    fi

    if command -v foamToVTK &>/dev/null; then
        log_info "OpenFOAM tools verified (local)"
    else
        log_warn "OpenFOAM foamToVTK not found (local simulations may fail)"
    fi

    if [[ ! -f "$NERSC_SSH_KEY" ]]; then
        log_warn "NERSC SSH key not found: ${NERSC_SSH_KEY}"
        log_warn "NERSC-assigned modules will fail at dispatch time"
    fi

    return $errors
}

verify_hybrid_env || log_warn "Some hybrid environment checks failed"

log_info "Hybrid environment setup complete"
log_info "NERSC target: ${NERSC_USER}@${NERSC_SSH_HOST}"
log_info "NERSC scratch: ${NERSC_SCRATCH_DIR}"
