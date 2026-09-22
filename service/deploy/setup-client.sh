#!/usr/bin/env bash
# Client-side deps for the real service twin, on top of digital.twins'
# `./deploy/install.sh client` (which provides the DT stack + rose).
#
#   ./setup-client.sh [ve.demo path]
#
# The real components import these at packaging time -- TensorFlow and
# matplotlib stay lazy (endpoint-only), so the client needs only the
# light ones plus the pyspot submodule the sensor uses.
set -euo pipefail
VENV="${1:-$HOME/radical/digital_twins/ve.demo}"

"$VENV/bin/pip" install -q python-dotenv numpy pandas

# pyspot (tasks/common/pyspot) is a git submodule -- davis.py imports it
git submodule update --init --recursive

echo "done.  run from this checkout:"
echo "  source service/deploy/client-env.sh <broker-host> remote"
echo "  $VENV/bin/python service/sensor_publisher.py    # terminal 1"
echo "  $VENV/bin/python twin_service_real.py           # terminal 2"
