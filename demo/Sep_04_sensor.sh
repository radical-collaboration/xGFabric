#!/usr/bin/env bash
# xGFabric demo -- external wind sensor (fake Davis).  Run on the client.
# Publishes to the twin's input channel over the ORBIT data plane.
#
#   demo/Sep_04_sensor.sh [broker-ip]
set -euo pipefail

BROKER_IP="${1:-95.217.193.116}"

# --- demo/site specific ----------------------------------------------------
VENV="${DT_VENV:-$HOME/radical/digital_twins/ve.demo}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"     # xGFabric checkout root
# ---------------------------------------------------------------------------

echo "--------------------------"
echo "xGFabric Demo September 04"
echo "Sensor davis-wind ($(hostname -f)) -> broker $BROKER_IP"
echo "--------------------------"

export RADICAL_ORBIT_BROKER_URL="wss://$BROKER_IP:8000"
export RADICAL_ORBIT_BROKER_CERT="$HOME/.radical/orbit/broker_cert.pem"
export DT_STREAM_BACKEND=orbit

cd "$HERE"
echo "publishing davis-wind to channel xgf/davis ..."
exec "$VENV/bin/python" service/sensor_publisher.py
