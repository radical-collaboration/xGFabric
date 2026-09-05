#!/usr/bin/env bash
# xGFabric demo -- client driver.  Run on the client.  Ensures the light
# client-side deps, then drives the real twin against the HPC endpoint.
#
#   demo/Sep_04_client.sh [broker-ip]
set -euo pipefail

BROKER_IP="${1:-95.217.193.116}"

# --- demo/site specific ----------------------------------------------------
VENV="${DT_VENV:-$HOME/radical/digital_twins/ve.demo}"
DT_DIR="${DT_DIR:-$HOME/radical/digital_twins}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"     # xGFabric checkout root
RUNTIME="${RUNTIME:-600}"
# default to the fast fake-surrogate driver (CPU-friendly: sleeps + numpy,
# no TF/xgboost, heatmaps in seconds, learning lane built in).  RUN_REAL=1
# switches to the real TF workload (needs a GPU endpoint to be timely).
DRIVER="twin_service.py"
[ "${RUN_REAL:-}" = 1 ] && DRIVER="twin_service_real.py"
# ---------------------------------------------------------------------------

echo "--------------------------"
echo "xGFabric Demo September 04"
echo "Client $DRIVER ($(hostname -f)) -> broker $BROKER_IP, endpoint HPC 'hpc'"
echo "--------------------------"

cd "$HERE"

# client-side deps the real components import at packaging time (TF and
# matplotlib stay lazy / endpoint-only); pyspot submodule for the sensor.
"$VENV/bin/pip" install -q python-dotenv numpy pandas
git submodule update --init --recursive
# keep the client digitaltwin current (record_output etc.)
( cd "$DT_DIR" && git checkout devel && git pull ) && "$VENV/bin/pip" install -q "$DT_DIR"

# placement: run the twin's tasks on the HPC endpoint (dragon)
export RADICAL_ORBIT_BROKER_URL="wss://$BROKER_IP:8000"
export RADICAL_ORBIT_BROKER_CERT="$HOME/.radical/orbit/broker_cert.pem"
export DT_STREAM_BACKEND=orbit
export DT_INFERENCE_ENDPOINT=hpc
export DT_INFERENCE_BACKEND=dragon_v3
export DT_LEARNING_ENDPOINT=hpc
export DT_LEARNING_BACKEND=concurrent

echo "driving twin via $DRIVER (runtime ${RUNTIME}s) ..."
echo "dashboard: https://$BROKER_IP:8000/broker/dt/ui?live=1"
exec "$VENV/bin/python" "$DRIVER" --runtime "$RUNTIME"
