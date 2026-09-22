#!/usr/bin/env bash
# DTaaS broker host for the xGFabric service twin (e.g. radical.3).
# Run there.  Adapted from the AmSC dt-complete deploy kit, which
# carries the debugged install/launch lore; delta here: numpy for the
# by-value components.
#
# Once per host: broker_cert.pem / broker_key.pem / broker.token in
# ~/.radical/orbit/.  DT_DIR overrides the checkout+venv location.
set -euo pipefail
DT_DIR="${DT_DIR:-$HOME/digital_twins}"

[ -d "$DT_DIR" ] || git clone https://github.com/radical-cybertools/digital.twins.git "$DT_DIR"
cd "$DT_DIR" && git checkout devel && git pull

./deploy/install.sh broker                        # pinned stack -> ./ve.demo
./ve.demo/bin/pip install -q numpy
# match the endpoint's rhapsody exactly (e491cd2-based): main breaks the
# endpoint's dragon backend (task_logs= to Batch), so both tiers pin the
# proven branch.  The dragon cancel fix on it is a no-op broker-side; the
# orbit-backend cancel fix lives only on the main-based #91 branch, so a
# harmless KeyError-cancel line may appear on teardown here.
./ve.demo/bin/pip install -q --force-reinstall --no-deps \
  "rhapsody-py[telemetry] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"
# backfill the telemetry extra's deps (opentelemetry) in case a fresh
# install did not carry them
./ve.demo/bin/pip install -q \
  "rhapsody-py[telemetry] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"

echo "done.  start the broker with:"
echo "  cd $DT_DIR && ./deploy/run-broker.sh \$PWD/ve.demo"
