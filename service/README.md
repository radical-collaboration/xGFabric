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

## What maps to what

| twin.py (standalone)             | twin_service.py (DTaaS)              |
|----------------------------------|--------------------------------------|
| local WorkflowEngine + backend   | session engine on the broker, tasks on the endpoint (ENGINES config) |
| DavisWind persistent component   | external `ChannelPublisher` + `add_input` binding |
| WindFieldAgent + FNO/PINN/PCR    | `ServiceWindFieldAgent` + fake `SurrogateInvestigator`s (same selection logic) |
| profiler subprocess + Pi learner | `ServiceProfiler` (inline timed run) + `ServicePiPredictor` |
| CUPS_Sink                        | `ServiceSink` (runtime-resolved workspace) |
| ZMQ stream                       | ORBIT data plane                     |
| asyncflow telemetry + reports    | endpoint-side rhapsody telemetry + `collect_reports.py` |

## Telemetry and reports

Nothing to enable: the rhapsody plugin on the endpoint records every
task plus a resource poll on its own (the `[telemetry]` extra), into
`telemetry-output/session.*.telemetry.jsonl` under the endpoint's
working directory.  After (or during) a run:

    <venv>/bin/python service/collect_reports.py [telemetry-dir]

renders twin.py's report set — task waterfall, dependency wait, stage
timers, swimlane, concurrency/resources, and the gantt — next to the
jsonl.  For a remote endpoint, scp the jsonl files first.

Known gap: per-workflow grouping in the gantt needs
`asyncflow.workflow_id`, which only `workflow_scope()` stamps — the
service engine does not run one.  That is an engine-side telemetry
feature for the DT service (digital.twins), tracked there; every other
report is complete without it.
