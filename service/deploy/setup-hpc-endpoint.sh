#!/usr/bin/env bash
# HPC-endpoint venv for the xGFabric service twin (e.g. Perlmutter).
# Run on a login node.  Adapted from the AmSC dt-complete deploy kit.
#
#   ./setup-hpc-endpoint.sh <broker-host>
#
# DT_DIR overrides the checkout+venv location; the default lands on
# $SCRATCH -- the venv is far too big for a Perlmutter home quota.
set -euo pipefail
BROKER="${1:?usage: $0 <broker-host>}"
DT_DIR="${DT_DIR:-${SCRATCH:-$HOME}/digital_twins}"

# same Python minor as every other host -- the service rejects skew, and
# exactly 3.12.0 breaks dragon's transport import (needs >= 3.12.1)
module load python/3.12 2>/dev/null || true

[ -d "$DT_DIR" ] || git clone https://github.com/radical-cybertools/digital.twins.git "$DT_DIR"
cd "$DT_DIR" && git checkout devel && git pull

./deploy/install.sh endpoint                      # pinned stack -> ./ve.demo
# the surrogate/sink task bodies unpickle and run here
./ve.demo/bin/pip install -q numpy matplotlib
# dragon backend + idempotent cancels + failure-traceback logging
./ve.demo/bin/pip install -q --force-reinstall --no-deps \
  "rhapsody-py[telemetry,dragon] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-and-traceback"

mkdir -p ~/.radical/orbit
scp "$BROKER:.radical/orbit/broker_cert.pem" "$BROKER:.radical/orbit/broker.token" ~/.radical/orbit/

echo "done.  get an allocation (salloc -N1 -C cpu -q interactive -t 2:00:00 -A <account>),"
echo "then run:  service/deploy/run-hpc-endpoint.sh $BROKER"
