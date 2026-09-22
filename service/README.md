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
`fix/dragon-cancel-idempotent` branch (e491cd2-based) on every tier: it
carries the dragon cancel + traceback fixes and stays compatible with
the pinned dragonhpc 0.14.1 (rhapsody main's dragon backend passes
`task_logs=` to `Batch()`, which that dragon rejects).

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

## Real workload (Level A: real training, faked simulation)

The fake `service/*` components run the DTaaS mechanics end to end.  The
real path swaps in the actual FNO/PINN/PCR investigators (TensorFlow /
scikit-learn) and the real profiler, still on precalc simulation data
(`/global/cfs/cdirs/m5290/precalc_sims`) -- real OpenFOAM (Level B,
`cups_structure.zip`) is a later step.

Only the **endpoint** changes: the trainings need TensorFlow, so it runs
in a clone of Ben's `cfdaai` conda env (which carries the stack) with our
runtime installed into the clone -- built by `setup-hpc-endpoint-real.sh`,
then launched via `run-hpc-endpoint.sh` with `DT_VENV`/`XGF_DIR` set (the
setup script prints the exact line).  Broker and client stay on `ve.demo`
and need no TensorFlow.

    # Perlmutter login node, once (clones cfdaai, installs our runtime,
    # checks out the tasks tree, stages the profiler dataset)
    service/deploy/setup-hpc-endpoint-real.sh <broker-host>
    # then in an allocation, per the line it prints:
    DT_VENV=<clone> XGF_DIR=<xgf checkout> \
      service/deploy/run-hpc-endpoint.sh <broker-host>

Driver: `twin_service_real.py` wires the real components (done, but
experimental -- not yet validated end to end; it is the on-Perlmutter
starting point).  The lazy-import refactor is in place, so the real
investigators import TF-free on the client/broker; TF loads only in the
task bodies on the endpoint.

Client/broker still need the light deps the real components carry:

    git submodule update --init --recursive          # pyspot (sensor)
    <ve.demo>/bin/pip install python-dotenv numpy pandas

Two items remain open before a real run is trustworthy:

- **Shared filesystem.**  The real components write to
  `config['PLAYGROUND_DIR']` from both main_loops (broker) and tasks
  (endpoint); those line up only on a shared filesystem, so run the
  **broker on Perlmutter too** for the real workload (PLAYGROUND_DIR on
  `$SCRATCH`).  A broker on radical.3 splits the playground across hosts.
- **cloudpickle parity.**  The cloned conda env and `ve.demo` may carry
  different cloudpickle versions; align them or unpickling the shipped
  classes can fail.

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
