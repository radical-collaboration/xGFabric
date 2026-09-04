#!/usr/bin/env bash
# xGFabric demo -- Perlmutter endpoint SETUP.  Run on a LOGIN NODE (it
# pip-installs and clones; the allocation cannot).  Idempotent.
#
#   demo/Sep_04_endpoint_setup.sh [broker-ip]   (broker-ip only for the banner)
#
# Assumes keys/token already staged in ~/.radical/orbit/.
set -euo pipefail

BROKER_IP="${1:-95.217.193.116}"
EP=hpc

# --- demo/site specific ----------------------------------------------------
BRANCH=feature/dtaas-twin-real
DT_DIR="${DT_DIR:-$SCRATCH/digital_twins}"
XGF_DIR="${XGF_DIR:-$SCRATCH/xgfabric}"
ENV_PREFIX="${DT_ENV:-$SCRATCH/dt-endpoint-env}"
PLAYGROUND_DIR="${PLAYGROUND_DIR:-$SCRATCH/xgf_playground}"
BEN_ENVS="/global/common/software/m5290/bcarter/mconda/envs"
BASE_ENV=cfdaai
RH="rhapsody-py[telemetry,dragon] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"
ROSE="rose @ git+https://github.com/radical-cybertools/ROSE@64330d9cb43c3e13ca67daf0d8ae84a2ae6c3f17"
# ---------------------------------------------------------------------------

echo "--------------------------"
echo "xGFabric Demo September 04 -- ENDPOINT SETUP (login node)"
echo "Broker $BROKER_IP | Endpoint '$EP' | env $ENV_PREFIX | playground $PLAYGROUND_DIR"
echo "--------------------------"

module load python/3.12 2>/dev/null || true
command -v conda >/dev/null || { echo "ERROR: conda not on PATH" >&2; exit 1; }

# checkouts
[ -d "$DT_DIR" ]  || git clone https://github.com/radical-cybertools/digital.twins.git "$DT_DIR"
( cd "$DT_DIR"  && git checkout devel  && git pull )
[ -d "$XGF_DIR" ] || git clone https://github.com/radical-collaboration/xGFabric.git "$XGF_DIR"
( cd "$XGF_DIR" && git checkout "$BRANCH" && git pull && git submodule update --init --recursive )

# conda env: a clone of Ben's cfdaai (TensorFlow + CFD/ML stack), never his
conda config --add envs_dirs "$BEN_ENVS" 2>/dev/null || true
[ -d "$ENV_PREFIX" ] || conda create -y -p "$ENV_PREFIX" --clone "$BEN_ENVS/$BASE_ENV"
PY="$ENV_PREFIX/bin/python"

ver="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
[ "$ver" = "3.12" ] || { echo "ERROR: $BASE_ENV is Python $ver, need 3.12" >&2; exit 1; }

# our runtime into the clone.  orbit force-reinstalled (a clone may carry a
# stale one that hides the endpoint script), then deps backfilled.
echo "==> installing runtime into $ENV_PREFIX"
"$PY" -m pip install -q "$ROSE"
"$PY" -m pip install -q --force-reinstall --no-deps "radical.orbit>=0.7"
"$PY" -m pip install -q "radical.orbit>=0.7"
"$PY" -m pip install -q "$DT_DIR"
# rhapsody LAST so the dragon-compatible branch wins over what digitaltwin
# pulled (main passes task_logs= to Batch(), which the pinned dragonhpc
# rejects); extras step backfills opentelemetry + dragonhpc.
"$PY" -m pip install -q --force-reinstall --no-deps \
    "rhapsody-py @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"
"$PY" -m pip install -q "$RH"

# data dirs: seed the Pi-predictor dataset at the RUNTIME datastore (where
# endpoint_trainer.py reads it)
mkdir -p "$PLAYGROUND_DIR/profiler/pi_profiler"
cp -n "$XGF_DIR/tasks/profiler/pi_profiler/data.csv.sample" \
      "$PLAYGROUND_DIR/profiler/pi_profiler/data.csv" 2>/dev/null || true

# sanity
echo "==> verify"
"$PY" -c "import radical.orbit, digitaltwin, rhapsody, opentelemetry; print('  imports ok')"
"$PY" -c "import rhapsody.backends.execution.dragon as d; n=open(d.__file__).read().count('task_logs'); print('  dragon task_logs (want 0):', n)"
[ -x "$ENV_PREFIX/bin/radical-orbit-endpoint.py" ] && echo "  endpoint script ok" || echo "  WARN: endpoint script missing"
[ -x "$ENV_PREFIX/bin/dragon" ] && echo "  dragon ok" || echo "  WARN: dragon missing"

echo "--------------------------"
echo "done.  get an allocation, then run:"
echo "  $XGF_DIR/demo/Sep_04_endpoint.sh $BROKER_IP $EP"
echo "--------------------------"
