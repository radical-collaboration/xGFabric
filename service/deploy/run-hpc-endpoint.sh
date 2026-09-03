#!/usr/bin/env bash
# Run the xGFabric twin's HPC endpoint -- INSIDE a compute allocation.
# Adapted from the AmSC dt-complete deploy kit; the launch constraints
# (dragon launcher, PATH-by-name helpers, SLURM_EXPORT_ENV) are the
# debugged ones from there.
#
#   ./run-hpc-endpoint.sh <broker-host>
#
# The endpoint registers as 'hpc' -- what the client's remote profile
# (client-env.sh remote) asks for.  DT_DIR as in setup-hpc-endpoint.sh.
set -euo pipefail
BROKER="${1:?usage: $0 <broker-host>}"
DT_DIR="${DT_DIR:-$HOME/digital_twins}"
VENV="$DT_DIR/ve.demo"

# dragon resolves its helpers BY NAME through srun on the task side
export PATH="$VENV/bin:$PATH"
export RADICAL_ORBIT_BROKER_URL="wss://$BROKER:8000"
export RADICAL_ORBIT_BROKER_CERT="$HOME/.radical/orbit/broker_cert.pem"
export RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_v3
export RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0
export SLURM_EXPORT_ENV=ALL          # inner sruns must not scrub the env
export DT_STREAM_BACKEND=orbit
# heatmaps land on scratch where available
export XGF_WORKSPACE="${XGF_WORKSPACE:-${SCRATCH:-$HOME}/xgf_twin}"

"$VENV/bin/dragon" "$VENV/bin/radical-orbit-endpoint.py" -n hpc \
    2>&1 | tee endpoint.log
