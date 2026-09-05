#!/usr/bin/env bash
# xGFabric demo -- DTaaS broker.  Run on the broker host (radical.3).
# Sets up (install + fixes) then starts the broker.  Idempotent.
#
#   demo/Sep_04_broker.sh [broker-ip]
#
# Assumes broker_cert.pem / broker_key.pem / broker.token in ~/.radical/orbit/.
set -euo pipefail

BROKER_IP="${1:-95.217.193.116}"

# --- demo/site specific ----------------------------------------------------
DT_DIR="${DT_DIR:-$HOME/digital_twins}"
RH="rhapsody-py[telemetry] @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"
# ---------------------------------------------------------------------------

echo "--------------------------"
echo "xGFabric Demo September 04"
echo "Broker on $BROKER_IP ($(hostname -f))"
echo "--------------------------"

# checkout + install the pinned stack, then pin the dragon-compatible
# rhapsody branch (extras backfilled)
[ -d "$DT_DIR" ] || git clone https://github.com/radical-cybertools/digital.twins.git "$DT_DIR"
( cd "$DT_DIR" && git checkout devel && git pull )
( cd "$DT_DIR"
  ./deploy/install.sh broker
  # install.sh compares by version string and skips when it is unchanged,
  # so it can leave stale digitaltwin code (e.g. missing record_output).
  # Force the checked-out devel tip over whatever it left.
  ./ve.demo/bin/pip install -q --force-reinstall --no-deps "$DT_DIR"
  ./ve.demo/bin/pip install -q numpy pandas    # the agent runs broker-side
  ./ve.demo/bin/pip install -q --force-reinstall --no-deps \
      "rhapsody-py @ git+https://github.com/radical-cybertools/rhapsody@fix/dragon-cancel-idempotent"
  ./ve.demo/bin/pip install -q "$RH" )

echo "starting broker (wss://0.0.0.0:8000) ..."
exec "$DT_DIR/deploy/run-broker.sh" "$DT_DIR/ve.demo"
