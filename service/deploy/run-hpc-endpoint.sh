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
#
# Two modes, same script:
#   faked demo   -- DT_VENV unset: uses $DT_DIR/ve.demo (setup-hpc-endpoint.sh)
#   real workload-- DT_VENV=<conda env>, XGF_DIR=<xGFabric checkout>: the
#                   real trainings need TensorFlow (Ben's cloned cfdaai env)
#                   and the profiler/task bodies import from the tasks tree
#                   (setup-hpc-endpoint-real.sh prints the exact invocation).
set -euo pipefail
BROKER="${1:?usage: $0 <broker-host>}"
DT_DIR="${DT_DIR:-${SCRATCH:-$HOME}/digital_twins}"
VENV="${DT_VENV:-$DT_DIR/ve.demo}"

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

# real workload: the profiler shells out to a script in the xGFabric tasks
# tree and the (lazy-imported) task bodies import tasks.* -- put the
# checkout on PYTHONPATH when XGF_DIR names one
if [ -n "${XGF_DIR:-}" ]; then
    export PYTHONPATH="$XGF_DIR:${PYTHONPATH:-}"
fi

"$VENV/bin/dragon" "$VENV/bin/radical-orbit-endpoint.py" -n hpc \
    2>&1 | tee endpoint.log
