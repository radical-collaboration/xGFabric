#!/bin/bash
#
# setup_racelab.sh - One-time bootstrap for racelab-gpu1 (rw-gpu1.cs.ucsb.edu)
#
# Run this once before using racelab as a hybrid training target:
#   bash env/setup_racelab.sh
#
# What it does:
#   1. Tests SSH connectivity
#   2. Installs Miniconda if not present
#   3. Creates or updates the cfdai_intheloop conda environment
#   4. Verifies GPU availability

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"

# Load config for RACELAB_* variables
source "${WORK_DIR}/config.sh" 2>/dev/null || true

SSH_HOST="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"
SSH_USER="${RACELAB_USER:-liubov_kurafeeva}"
SSH_KEY="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
REMOTE_WORK="${RACELAB_REMOTE_WORK_DIR:-/local/home/liubov_kurafeeva/intheloop_hybrid}"
LOGS_DIR="${RACELAB_LOGS_DIR:-/local/home/liubov_kurafeeva/jobs_logs}"
CONDA_ENV="${CONDA_ENV:-cfdai_tf310}"
ENV_FILE="${WORK_DIR}/utils/environment.yml"

SSH="ssh -i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15 ${SSH_USER}@${SSH_HOST}"
RSYNC="rsync -az --no-perms -e \"ssh -i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no\""

log() { echo "[setup_racelab] $*"; }
err() { echo "[setup_racelab] ERROR: $*" >&2; exit 1; }

################################################################################
# Step 1: SSH connectivity
################################################################################

log "Testing SSH connectivity to ${SSH_USER}@${SSH_HOST}..."
if [[ ! -f "$SSH_KEY" ]]; then
    err "SSH key not found: ${SSH_KEY}  —  place the racelabgpu key in ${WORK_DIR}/"
fi
chmod 600 "$SSH_KEY"
$SSH "echo ok" &>/dev/null || err "Cannot connect to ${SSH_HOST}. Check key and host."
log "  SSH: OK"

################################################################################
# Step 2: Check / install Miniconda
################################################################################

log "Checking conda on racelab..."
CONDA_FOUND=$($SSH "
    for p in \"\$HOME/miniconda3\" \"\$HOME/miniforge3\" \"\$HOME/anaconda3\" \"/opt/conda\"; do
        if [[ -f \"\${p}/bin/conda\" ]]; then echo \"\${p}/bin/conda\"; break; fi
    done
" 2>/dev/null || true)

if [[ -z "$CONDA_FOUND" ]]; then
    log "  Conda not found — installing Miniconda3..."
    $SSH "
        set -e
        cd /tmp
        wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda_install.sh
        bash miniconda_install.sh -b -p \$HOME/miniconda3
        rm miniconda_install.sh
        echo 'Miniconda installed at \$HOME/miniconda3'
    "
    CONDA_FOUND="\$HOME/miniconda3/bin/conda"
    log "  Miniconda installed"
else
    log "  Conda found: ${CONDA_FOUND}"
fi

################################################################################
# Step 3: Create / update conda environment
################################################################################

log "Checking conda environment '${CONDA_ENV}' on racelab..."

# Sync environment.yml first so the remote create can use it
if rsync -az --no-perms -e "ssh -i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "$ENV_FILE" "${SSH_USER}@${SSH_HOST}:/tmp/cfdai_environment.yml" 2>/dev/null; then
    log "  Synced environment.yml to racelab"
else
    log "  Warning: could not sync environment.yml, will use inline package list"
fi

# Check existence via conda info --envs (more reliable than env list | grep)
CONDA_INIT_PATH="$(dirname "${CONDA_FOUND}")/../etc/profile.d/conda.sh"
ENV_EXISTS=$($SSH "
    source '${CONDA_INIT_PATH}' 2>/dev/null || true
    if conda info --envs 2>/dev/null | awk '{print \$1}' | grep -qx '${CONDA_ENV}'; then
        echo yes
    else
        echo no
    fi
" 2>/dev/null || echo no)

log "  Environment exists: ${ENV_EXISTS}"

if [[ "$ENV_EXISTS" != "yes" ]]; then
    log "  Creating environment '${CONDA_ENV}'..."
    $SSH "
        set -e
        source '${CONDA_INIT_PATH}'
        # Accept Anaconda ToS non-interactively (required for newer conda)
        conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
        conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true
        if [[ -f /tmp/cfdai_environment.yml ]]; then
            conda env create -f /tmp/cfdai_environment.yml -n ${CONDA_ENV}
        else
            conda create -y -n ${CONDA_ENV} python=3.12 numpy pandas scikit-learn h5py matplotlib
        fi
        conda run -n ${CONDA_ENV} pip install -q meshio tensorflow keras tqdm
        echo 'Environment created'
    "
    log "  Environment created"
else
    log "  Environment '${CONDA_ENV}' already exists — updating pip packages..."
    $SSH "
        set -e
        source '${CONDA_INIT_PATH}'
        conda run -n ${CONDA_ENV} pip install -q --upgrade meshio tensorflow keras
        echo 'Packages updated'
    "
    log "  Packages up to date"
fi

################################################################################
# Step 4: Verify GPU
################################################################################

log "Checking GPU availability on racelab..."
GPU_INFO=$($SSH "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'none'" 2>/dev/null || echo "none")
if [[ "$GPU_INFO" == "none" ]]; then
    log "  WARNING: nvidia-smi not found or no GPU detected on racelab-gpu1"
else
    log "  GPU(s) found:"
    while IFS= read -r line; do log "    ${line}"; done <<< "$GPU_INFO"
fi

################################################################################
# Step 5: Create remote work directories
################################################################################

log "Creating remote directories..."
$SSH "mkdir -p '${REMOTE_WORK}' '${LOGS_DIR}'"
log "  Remote work dir: ${REMOTE_WORK}"
log "  Logs dir:        ${LOGS_DIR}"

################################################################################
# Step 6: Verify Python import
################################################################################

log "Verifying Python environment..."
$SSH "
    CONDA_BIN=\$(dirname ${CONDA_FOUND})
    source \"\${CONDA_BIN}/../etc/profile.d/conda.sh\"
    conda activate ${CONDA_ENV}
    python3 -c 'import numpy, pandas, sklearn, tensorflow; print(\"tensorflow\", tensorflow.__version__)'
" && log "  Python imports OK" || log "  WARNING: some imports failed — check manually"

log ""
log "racelab-gpu1 setup complete."
log "You can now set HYBRID_MODULE_PINN=racelab and HYBRID_MODULE_FNO=racelab in config.sh"
