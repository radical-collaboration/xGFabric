# xGFabric twin, service mode

`../twin_service.py` runs twin.py's graph on a DTaaS broker: the twin
lives in the ORBIT `dt` plugin, its tasks run on a rhapsody endpoint,
the sensor is an external channel publisher.  Physics is faked at the
same seams twin.py already fakes (sensor records, simulation); the
selection story is real — three surrogate architectures with different
costs, ranked by profiler-predicted Pi runtime.

## Local run (three terminals + stack)

Stack (from a digital.twins checkout with `./deploy/install.sh` done,
venv `ve3`/`ve.demo`):

    ./deploy/run-broker.sh $PWD/<venv>
    ./deploy/run-endpoint.sh dt_inference_ep localhost $PWD/<venv>

Client terminals (each):

    export RADICAL_ORBIT_BROKER_URL=wss://localhost:8000
    export DT_STREAM_BACKEND=orbit

    <venv>/bin/python service/sensor_publisher.py     # terminal 1
    <venv>/bin/python twin_service.py --runtime 240   # terminal 2

Dashboard: `https://localhost:8000/broker/dt/ui?live=1` (broker token).
Heatmaps land in `$XGF_WORKSPACE` (default `~/xgf_twin/`) on the host
running the endpoint tasks.

Placement: `DT_INFERENCE_ENDPOINT` / `DT_INFERENCE_BACKEND` override
the defaults (`dt_inference_ep` / `concurrent`).

## Remote run (broker on radical.3, endpoint on Perlmutter)

`service/deploy/` adapts the AmSC dt-complete deploy kit (same debugged
constraints: dragon launcher requirement, python >= 3.12.1,
SLURM_EXPORT_ENV, cert staging), pinning rhapsody's
`fix/dragon-cancel-and-traceback` branch on every tier for the
idempotent-cancel fixes this demo surfaced.

    # broker host, once
    service/deploy/setup-broker.sh
    cd ~/digital_twins && ./deploy/run-broker.sh $PWD/ve.demo

    # Perlmutter login node, once
    service/deploy/setup-hpc-endpoint.sh <broker-host>
    # then inside salloc -N1 -C cpu -q interactive -t 2:00:00 -A <account>:
    service/deploy/run-hpc-endpoint.sh <broker-host>     # registers as 'hpc'

    # client terminals (driver + sensor), each:
    source service/deploy/client-env.sh <broker-host> remote
    <ve.demo>/bin/python service/sensor_publisher.py     # terminal 1
    <ve.demo>/bin/python twin_service.py --runtime 240   # terminal 2

The client venv must be the same Python minor (digital.twins
`./deploy/install.sh client` + `pip install numpy`); a 3.13 venv is
rejected at the first verb.

## What maps to what

| twin.py (standalone)             | twin_service.py (DTaaS)              |
|----------------------------------|--------------------------------------|
| local WorkflowEngine + backend   | session engine on the broker, tasks on the endpoint (ENGINES config) |
| DavisWind persistent component   | external `ChannelPublisher` + `add_input` binding |
| WindFieldAgent + FNO/PINN/PCR    | `ServiceWindFieldAgent` + fake `SurrogateInvestigator`s (same selection logic) |
| profiler subprocess + Pi learner | `ServiceProfiler` (inline timed run) + `ServicePiPredictor` |
| CUPS_Sink                        | `ServiceSink` (runtime-resolved workspace) |
| ZMQ stream                       | ORBIT data plane                     |
| asyncflow telemetry + reports    | not yet — see the telemetry branch   |
