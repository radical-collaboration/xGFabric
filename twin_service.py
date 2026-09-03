#!/usr/bin/env python3
"""The xGFabric twin as a service: twin.py's graph on a DTaaS broker.

Same story as twin.py -- Davis wind sensor, a field agent whose three
surrogate architectures compete on profiler-predicted Pi runtime, a
heatmap sink -- but the twin lives on an ORBIT broker and its tasks run
on a rhapsody endpoint.  The sensor is an external channel publisher
(service/sensor_publisher.py); components ship by value (service/*,
fake physics, see service/__init__.py).

Environment (client side):
    RADICAL_ORBIT_BROKER_URL(+_CERT)   the broker
    DT_STREAM_BACKEND=orbit            the data plane
    DT_SERVICE_HOST                    participant hosting `dt` (broker)
    DT_INFERENCE_ENDPOINT / _BACKEND   task placement (local endpoint /
                                       concurrent by default)
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radical.orbit import EndpointRuntime

from digitaltwin.components import NULL_DTYPE, TypedData
from digitaltwin.service import register_user_modules

import service
import service.investigators
import service.profiler
import service.sink
import service.wind_agent
import tasks
import tasks.common
import tasks.common.dtypes

from tasks.common.dtypes import DAVIS_WIND_SENSOR, WIND_FIELD
from service.profiler import (
    PI_PREDICT_RUNTIME,
    PROFILE_RESULTS,
    TASK_DESCRIPTION_DTYPE,
    ServicePiPredictor,
    ServiceProfiler,
)
from service.sensor_publisher import DAVIS_CHANNEL
from service.sink import ServiceSink
from service.wind_agent import ServiceWindFieldAgent

register_user_modules([
    tasks, tasks.common, tasks.common.dtypes,
    service, service.investigators, service.profiler,
    service.sink, service.wind_agent,
])

DT_HOST = os.environ.get("DT_SERVICE_HOST", "broker")

INFERENCE_EP = os.environ.get("DT_INFERENCE_ENDPOINT", "dt_inference_ep")
INFERENCE_BE = os.environ.get("DT_INFERENCE_BACKEND", "concurrent")
# learning defaults to the same endpoint on the concurrent executor: its
# own dashboard lane for the surrogate retraining, no second dragon
# runtime, and the training tasks stay clear of dragon's mp bridge
LEARNING_EP = os.environ.get("DT_LEARNING_ENDPOINT", INFERENCE_EP)
LEARNING_BE = os.environ.get("DT_LEARNING_BACKEND", "concurrent")

ENGINES = {
    "engines": {
        "inference": {"endpoint_name": INFERENCE_EP,
                      "backends": [INFERENCE_BE]},
        "learning": {"endpoint_name": LEARNING_EP,
                     "backends": [LEARNING_BE]},
    }
}


def main(args) -> int:
    runtime = EndpointRuntime()
    runtime.start(wait=True)

    try:
        dt = runtime.get_plugin(DT_HOST, "dt", config=ENGINES)
        print(f"[client] session: {dt.sid}  (reattach with this sid)")

        twin = dt.create_twin()
        print(f"[client] twin: {twin}")

        agent = dt.package(ServiceWindFieldAgent, learn_backend="learning")
        profiler = dt.package(ServiceProfiler)
        pi = dt.package(ServicePiPredictor)
        sink = dt.package(ServiceSink)

        # sensor is external: bind its channel to the input dtype
        dt.add_input(twin, DAVIS_WIND_SENSOR, DAVIS_CHANNEL)

        dt.add_agent(twin, agent, DAVIS_WIND_SENSOR, WIND_FIELD)
        dt.add_task(twin, sink, WIND_FIELD, NULL_DTYPE)

        # the profiling chain the agent's selector queries
        dt.add_investigator(twin, profiler, TASK_DESCRIPTION_DTYPE,
                            PROFILE_RESULTS)
        dt.add_investigator(twin, pi, PROFILE_RESULTS, PI_PREDICT_RUNTIME)

        dt.start(twin)

        # client-side feedback: the pipeline is stream driven, so poll the
        # twin and probe the field inference -- a stuck twin shows in 10s
        probe_pt = {"dt": "probe", "wind_speed": 12.0, "wind_avg": 9.0,
                    "wind_dir": 90.0}
        deadline = time.time() + args.runtime
        while time.time() < deadline:
            time.sleep(10)

            info = dt.twin(twin)
            print(f"[client] state={info['state']}"
                  f" calls={info.get('calls') or {}}", flush=True)
            if info["state"] == "failed":
                print(f"[client] twin failed: {info.get('last_error')}")
                return 1

            answer = dt.get_inference(
                twin, TypedData(DAVIS_WIND_SENSOR, probe_pt), WIND_FIELD,
                timeout=60)
            arch = answer.data["arch"]
            print(f"[client] field probe -> arch={arch}"
                  f" w={answer.data.get('w')}", flush=True)

        print("SHUTDOWN")
        dt.twin_close(twin)
        return 0

    finally:
        runtime.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="xGFabric twin, service mode")
    parser.add_argument("--runtime", type=int, default=240,
                        help="seconds to keep the twin running")
    sys.exit(main(parser.parse_args()))
