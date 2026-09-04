#!/usr/bin/env bash
# Real-workload HPC endpoint for the xGFabric service twin (Perlmutter).
# Run on a login node.
#
#   ./setup-hpc-endpoint-real.sh <broker-host>
#
# Unlike setup-hpc-endpoint.sh (faked components, plain ve.demo), the real
# FNO/PINN/PCR trainings need TensorFlow + the CFD/ML stack.  Rather than
# build that, we CLONE Ben's cfdaai conda env (which has it) and install
# our runtime into the clone -- never into his shared env.
#
# Prerequisites (read access): /global/common/software/m5290 (Ben's envs
# + cups_structure.zip) and /global/cfs/cdirs/m5290/precalc_sims.
# `conda` must be on PATH (module load, or source Ben's mconda).
#
# Overrides: DT_DIR (our checkout), XGF_DIR (xGFabric checkout),
# DT_ENV (clone location), DT_BASE_ENV (base env name, default cfdaai).
set -euo pipefail
BROKER="${1:?usage: $0 <broker-host>}"
DT_DIR="${DT_DIR:-${SCRATCH:-$HOME}/digital_twins}"
XGF_DIR="${XGF_DIR:-${SCRATCH:-$HOME}/xGFabric}"
ENV_PREFIX="${DT_ENV:-${SCRATCH:-$HOME}/dt-endpoint-env}"
BEN_ENVS="/global/common/software/m5290/bcarter/mconda/envs"
BASE_ENV="${DT_BASE_ENV:-cfdaai}"

command -v conda >/dev/null || {
    echo "ERROR: conda not on PATH -- module load python, or source Ben's" >&2
    echo "       mconda, then re-run." >&2; exit 1; }

# clone Ben's env (never install into his shared copy)
conda config --add envs_dirs "$BEN_ENVS" 2>/dev/null || true
if [ ! -d "$ENV_PREFIX" ]; then
    echo "==> cloning $BASE_ENV -> $ENV_PREFIX (this is large; once)"
    conda create -y -p "$ENV_PREFIX" --clone "$BEN_ENVS/$BASE_ENV"
fi
PY="$ENV_PREFIX/bin/python"

# wire contract: the same Python minor on every tier
ver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$ver" != "3.12" ]; then
    echo "ERROR: $BASE_ENV is Python $ver; the DT wire contract pins 3.12" >&2
    echo "       on every host.  Set DT_BASE_ENV to a 3.12 env (try" >&2
    echo "       xgfabric), or rebuild from its environment.yml on 3.12." >&2
    exit 1
fi

# our runtime into the clone -- git-pinned deps first (as deploy/install.sh
# does), then digitaltwin resolves the rest (asyncflow, orbit) from PyPI
[ -d "$DT_DIR" ] || git clone https://github.com/radical-cybertools/digital.twins.git "$DT_DIR"
( cd "$DT_DIR" && git checkout devel && git pull )
"$PY" -m pip install -q \
    "rose @ git+https://github.com/radical-cybertools/ROSE@64330d9cb43c3e13ca67daf0d8ae84a2ae6c3f17"
"$PY" -m pip install -q --force-reinstall --no-deps \
    "rhapsody-py[telemetry,dragon] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"
# force-reinstall orbit: a cloned env may already carry a stale radical.orbit
# that pip would treat as satisfied, leaving the endpoint script uninstalled
"$PY" -m pip install -q --force-reinstall --no-deps "radical.orbit>=0.7"
"$PY" -m pip install -q "$DT_DIR"

# xGFabric tasks tree: the profiler shells out to a script here, and the
# real task bodies import tasks.* at run time (run-hpc-endpoint.sh puts
# XGF_DIR on PYTHONPATH)
[ -d "$XGF_DIR" ] || git clone https://github.com/radical-collaboration/xGFabric.git "$XGF_DIR"
( cd "$XGF_DIR" && git checkout feature/dtaas-twin-real && git pull \
    && git submodule update --init --recursive )   # pyspot (davis/sensor)
# the Pi predictor's clean-slate dataset (Ben: the sample IS the real one)
cp -n "$XGF_DIR/tasks/profiler/pi_profiler/data.csv.sample" \
      "$XGF_DIR/tasks/profiler/pi_profiler/data.csv" 2>/dev/null || true

# broker cert + token
mkdir -p ~/.radical/orbit
scp "$BROKER:.radical/orbit/broker_cert.pem" "$BROKER:.radical/orbit/broker.token" ~/.radical/orbit/

cat <<EOF
done.  in an allocation, run the endpoint with the clone + tasks tree:

  DT_VENV=$ENV_PREFIX XGF_DIR=$XGF_DIR \\
    $XGF_DIR/service/deploy/run-hpc-endpoint.sh $BROKER

precalc sims: /global/cfs/cdirs/m5290/precalc_sims  (config.sh path)
cups zip (Level B only): /global/common/software/m5290/cups_structure.zip
EOF
