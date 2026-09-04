#!/usr/bin/env bash
# xGFabric demo -- Perlmutter endpoint RUN.  Run INSIDE the compute
# allocation (no pip here; Sep_04_endpoint_setup.sh did that on the login
# node).  Launches the rhapsody endpoint under the dragon launcher.
#
#   demo/Sep_04_endpoint.sh [broker-ip] [endpoint-name]
set -euo pipefail

BROKER_IP="${1:-95.217.193.116}"
EP="${2:-hpc}"

# --- demo/site specific ----------------------------------------------------
ENV_PREFIX="${DT_ENV:-$SCRATCH/dt-endpoint-env}"
XGF_DIR="${XGF_DIR:-$SCRATCH/xgfabric}"
PLAYGROUND_DIR="${PLAYGROUND_DIR:-$SCRATCH/xgf_playground}"
# ---------------------------------------------------------------------------

echo "--------------------------"
echo "xGFabric Demo September 04"
echo "Endpoint HPC '$EP' on $(hostname -f) -> broker $BROKER_IP"
echo "--------------------------"

# dragon resolves its helpers BY NAME via srun on the task side
export PATH="$ENV_PREFIX/bin:$PATH"
export PYTHONPATH="$XGF_DIR:${PYTHONPATH:-}"
export RADICAL_ORBIT_BROKER_URL="wss://$BROKER_IP:8000"
export RADICAL_ORBIT_BROKER_CERT="$HOME/.radical/orbit/broker_cert.pem"
export RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_v3
export RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0
export SLURM_EXPORT_ENV=ALL          # inner sruns must not scrub the env
export DT_STREAM_BACKEND=orbit
export XGF_WORKSPACE="$PLAYGROUND_DIR"
# keep the orbit log off HOME (tiny NERSC quota) and modest
export RADICAL_ORBIT_LOG_LVL="${RADICAL_ORBIT_LOG_LVL:-WARNING}"
export RADICAL_ORBIT_LOG_FILE="$SCRATCH/orbit-logs/$EP.log"
mkdir -p "$SCRATCH/orbit-logs" "$PLAYGROUND_DIR"
rm -f "$HOME/.radical/orbit/logs/"*.log 2>/dev/null || true

# --- GPU: expose the NVIDIA driver + CUDA to the TF tasks ------------------
# Ben's cfdaai TF fell back to CPU ("Could not find cuda drivers") because
# libcuda.so.1 was not on the task LD_LIBRARY_PATH.  Load PM's CUDA module
# and prepend the compute-node driver path + the env's own CUDA libs.  All
# best-effort (|| true) so a CPU allocation still launches -- the nvidia-smi
# line below records whether a GPU is actually present.
module load cudatoolkit 2>/dev/null || true
export LD_LIBRARY_PATH="/usr/lib64:$ENV_PREFIX/lib:${LD_LIBRARY_PATH:-}"
echo "GPU check (nvidia-smi -L):"
nvidia-smi -L 2>&1 | sed 's/^/  /' || echo "  no GPU visible -- CPU allocation? (need salloc -C gpu)"

echo "launching endpoint '$EP' under dragon ..."
exec "$ENV_PREFIX/bin/dragon" "$ENV_PREFIX/bin/radical-orbit-endpoint.py" -n "$EP" \
    2>&1 | tee "$SCRATCH/orbit-logs/$EP.console.log"
