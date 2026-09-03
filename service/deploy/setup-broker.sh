#!/usr/bin/env bash
# DTaaS broker host for the xGFabric service twin (e.g. radical.3).
# Run there.  Adapted from the AmSC dt-complete deploy kit, which
# carries the debugged install/launch lore; deltas here: numpy for the
# by-value components, and rhapsody from the cancel-fix branch (the
# broker-side engine is what showed the teardown KeyError noise).
#
# Once per host: broker_cert.pem / broker_key.pem / broker.token in
# ~/.radical/orbit/.  DT_DIR overrides the checkout+venv location.
set -euo pipefail
DT_DIR="${DT_DIR:-$HOME/digital_twins}"

[ -d "$DT_DIR" ] || git clone https://github.com/radical-cybertools/digital.twins.git "$DT_DIR"
cd "$DT_DIR" && git checkout devel && git pull

./deploy/install.sh broker                        # pinned stack -> ./ve.demo
./ve.demo/bin/pip install -q numpy
# idempotent cancels (dragon+orbit backends); main-based, includes pools
./ve.demo/bin/pip install -q --force-reinstall --no-deps \
  "rhapsody-py[telemetry] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-and-traceback"

echo "done.  start the broker with:"
echo "  cd $DT_DIR && ./deploy/run-broker.sh \$PWD/ve.demo"
