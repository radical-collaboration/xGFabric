# Client-side environment for the xGFabric service twin -- source me in
# EVERY client terminal (driver and sensor):
#
#   source service/deploy/client-env.sh <broker-host> [remote]
#
# With `remote`, task placement targets the HPC endpoint ('hpc' on
# dragon_v3, as run-hpc-endpoint.sh launches it); without it the local
# defaults apply (dt_inference_ep / concurrent).
#
# The client venv is digital.twins' `./deploy/install.sh client` plus
# `pip install numpy` -- same Python minor as broker and endpoint.
# DT_BROKER_CERT overrides the pinned-cert path when this machine runs
# a broker of its own.
BROKER="${1:?usage: source client-env.sh <broker-host> [remote]}"

export RADICAL_ORBIT_BROKER_URL="wss://$BROKER:8000"
export RADICAL_ORBIT_BROKER_CERT="${DT_BROKER_CERT:-$HOME/.radical/orbit/broker_cert.pem}"
export DT_STREAM_BACKEND=orbit

if [ "${2:-}" = "remote" ]; then
    export DT_INFERENCE_ENDPOINT=hpc
    export DT_INFERENCE_BACKEND=dragon_v3
fi
