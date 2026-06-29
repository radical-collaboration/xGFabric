#!/bin/bash
#
# env_racelab.sh - RaceLab GPU1 environment setup (rw-gpu1.cs.ucsb.edu)
#
# This script is sourced by system_config.sh when SYSTEM_TYPE=hybrid
# and at least one module is routed to racelab. It sets up SSH variables
# and verifies connectivity — conda/Python on racelab itself is set up
# remotely by env/setup_racelab.sh (run once before the pipeline).

log_info "Loading racelab-gpu1 environment..."

################################################################################
# SSH Configuration
################################################################################

export RACELAB_SSH_HOST="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"
export RACELAB_USER="${RACELAB_USER:-liubov_kurafeeva}"
export RACELAB_SSH_KEY="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
export RACELAB_REMOTE_WORK_DIR="${RACELAB_REMOTE_WORK_DIR:-/home/liubov_kurafeeva/intheloop_hybrid}"

if [[ ! -f "$RACELAB_SSH_KEY" ]]; then
    log_warn "Racelab SSH key not found: ${RACELAB_SSH_KEY}"
    log_warn "Training jobs routed to racelab will fail — run env/setup_racelab.sh first"
else
    chmod 600 "$RACELAB_SSH_KEY" 2>/dev/null || true
    log_info "Racelab SSH key: ${RACELAB_SSH_KEY}"
fi

export RACELAB_SSH_OPTS="-i ${RACELAB_SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15"
export RACELAB_CONDA_ENV="${RACELAB_CONDA_ENV:-cfdai_tf310}"

log_info "Racelab environment configured: ${RACELAB_USER}@${RACELAB_SSH_HOST}"
