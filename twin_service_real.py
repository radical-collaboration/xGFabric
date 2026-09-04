#!/usr/bin/env python3
"""The xGFabric twin as a service, with the REAL workload.

twin.py's graph, run on a DTaaS broker like twin_service.py -- but the
field agent, its FNO/PINN/PCR surrogates, the profiler and the Pi
predictor are the real components from tasks/, not the service/* fakes.
Physics stays where twin.py already fakes it (the sensor, and
tk_do_simulation's precalc-CSV shortcut); the trainings, the profiler
timing, and the selection are real.

STATUS: experimental scaffold, NOT yet validated end to end.  It is the
starting point for the on-Perlmutter test cycle, not a proven driver.
Known open items (see service/README.md "Real workload"):

  * Endpoint must run in a TF-carrying env (Ben's cfdaai clone) --
    setup-hpc-endpoint-real.sh.  The lazy-import refactor keeps the
    client/broker TF-free, but they still need dotenv + numpy + pandas
    and the pyspot submodule (`git submodule update --init`).
  * Shared-filesystem assumption: the real components write to
    config['PLAYGROUND_DIR'] both from main_loops (broker side) and
    from tasks (endpoint side).  Those line up only if broker and
    endpoint share a filesystem -- so run the BROKER on Perlmutter too
    for the real workload, with PLAYGROUND_DIR on $SCRATCH.  A broker on
    radical.3 will split the playground across two hosts.
  * Backends default to 'concurrent' here: real TF/sklearn under dragon
    is untested (joblib's mp bridge, TF process model).  Flip to
    dragon_v3 via the env knobs once it is proven.

Environment: config.sh (tasks/common/config.sh) supplies PLAYGROUND_DIR,
CSPOT_LIMIT, endpoint/model paths etc., loaded via dotenv as in twin.py.
Client wire env as usual: RADICAL_ORBIT_BROKER_URL(+_CERT),
DT_STREAM_BACKEND=orbit, DT_SERVICE_HOST.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dotenv

from radical.orbit import EndpointRuntime

from digitaltwin.components import NULL_DTYPE, DataType, TypedData
from digitaltwin.service import register_user_modules

# real components (TF is deferred to the task bodies -- import is light)
import tasks
import tasks.common
import tasks.common.dtypes
import tasks.wind_agent
import tasks.wind_learner
import tasks.sink
import tasks.profiler.components
import tasks.do_fno.fno_investigator
import tasks.do_pinn.pinn_investigator
import tasks.do_pcr.pcr_investigator

from tasks.common.dtypes import DAVIS_WIND_SENSOR, WIND_FIELD
from tasks.wind_agent import WindFieldAgent
from tasks.wind_learner import WindTrendLearner, WIND_TREND
from tasks.sink import CUPS_Sink
from tasks.profiler.components import (
    ProfilerInvestigator,
    EndpointInvestigator,
    TASK_DESCRIPTION_DTYPE,
    PROFILE_RESULTS,
)
from service.sensor_publisher import DAVIS_CHANNEL

PI_PREDICT_RUNTIME = DataType("pi_PREDICT_RUNTIME")

dotenv.load_dotenv("tasks/common/config.sh")

# Ship every user module in the agent's reference graph by value: the
# broker has no xGFabric checkout, so anything pickled by reference
# (tasks.davis -> utils_architecture, tasks.do_simulation, the common
# helpers, ...) fails to import there.  Sweep the whole tasks.* subtree
# plus the repo-root helpers rather than curate a list that drifts.
register_user_modules([
    m for name, m in list(sys.modules.items())
    if m is not None and (name == "tasks" or name.startswith("tasks.")
                          or name == "utils_architecture")
])

DT_HOST = os.environ.get("DT_SERVICE_HOST", "broker")

INFERENCE_EP = os.environ.get("DT_INFERENCE_ENDPOINT", "hpc")
INFERENCE_BE = os.environ.get("DT_INFERENCE_BACKEND", "concurrent")
LEARNING_EP = os.environ.get("DT_LEARNING_ENDPOINT", INFERENCE_EP)
LEARNING_BE = os.environ.get("DT_LEARNING_BACKEND", "concurrent")

ENGINES = {
    "engines": {
        "inference": {"endpoint_name": INFERENCE_EP, "backends": [INFERENCE_BE]},
        "learning": {"endpoint_name": LEARNING_EP, "backends": [LEARNING_BE]},
    }
}


def main(args) -> int:
    config = dict(os.environ)
    playground = config.get("PLAYGROUND_DIR", os.path.expanduser("~/xgf_twin"))

    runtime = EndpointRuntime()
    runtime.start(wait=True)
    try:
        dt = runtime.get_plugin(DT_HOST, "dt", config=ENGINES)
        print(f"[client] session: {dt.sid}  (reattach with this sid)")

        twin = dt.create_twin()
        print(f"[client] twin: {twin}")

        field = dt.package(WindFieldAgent, config)
        sink = dt.package(CUPS_Sink, config)
        # a visible learning lane on the wind stream (see wind_learner.py);
        # its training routes to the 'learning' engine declared in ENGINES
        learner = dt.package(WindTrendLearner, learn_backend="learning")
        base_profiler = dt.package(
            ProfilerInvestigator, playground + "/profiler/nersc_profiler")
        pi_profiler = dt.package(
            EndpointInvestigator, "pi", playground + "/profiler/pi_profiler")

        # sensor is external (fake Davis, as twin.py fakes it); bind its
        # channel to the input dtype
        dt.add_input(twin, DAVIS_WIND_SENSOR, DAVIS_CHANNEL)

        dt.add_agent(twin, field, DAVIS_WIND_SENSOR, WIND_FIELD)
        dt.add_task(twin, sink, WIND_FIELD, NULL_DTYPE)

        dt.add_investigator(twin, base_profiler,
                            TASK_DESCRIPTION_DTYPE, PROFILE_RESULTS)
        dt.add_investigator(twin, pi_profiler,
                            PROFILE_RESULTS, PI_PREDICT_RUNTIME)

        # visible learning lane, fed by the same sensor stream
        dt.add_investigator(twin, learner, DAVIS_WIND_SENSOR, WIND_TREND)

        dt.start(twin)

        deadline = time.time() + args.runtime
        while time.time() < deadline:
            time.sleep(10)
            info = dt.twin(twin)
            print(f"[client] state={info['state']}"
                  f" calls={info.get('calls') or {}}", flush=True)
            if info["state"] == "failed":
                print(f"[client] twin failed: {info.get('last_error')}")
                return 1

        print("SHUTDOWN")
        dt.twin_close(twin)
        return 0
    finally:
        runtime.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="xGFabric twin, service mode, REAL workload")
    parser.add_argument("--runtime", type=int, default=600,
                        help="seconds to keep the twin running")
    sys.exit(main(parser.parse_args()))
