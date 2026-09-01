"""Profiling chain, service-safe: measure, then predict for the Pi.

``ServiceProfiler`` really profiles: it unpickles the surrogate's
inference function and times a run with the example input -- inline as a
flow task on the endpoint, instead of twin.py's exported-pickle +
subprocess round trip (whose script path does not survive shipping by
value).  Results are memoised per (function, model) exactly like the
original.

``ServicePiPredictor`` stands in for the Pi endpoint's learned runtime
model: predicted Pi runtime = measured runtime x a Pi/HPC slowdown
factor with mild noise.  The real EndpointInvestigator's training on
recorded Pi profiles is the phase-2 story.
"""

import time

import cloudpickle

from digitaltwin.components import DataType, ModelInvestigator, TypedData
from digitaltwin.lru import LRUCache, freeze
from digitaltwin.runtime import RuntimeAPI

TASK_DESCRIPTION_DTYPE = DataType("TASK_INFO")
PROFILE_RESULTS = DataType("PROFILE_RESULT")
PI_PREDICT_RUNTIME = DataType("pi_PREDICT_RUNTIME")

PI_SLOWDOWN = 7.5  # a Raspberry Pi against one HPC core, rough


class ServiceProfiler(ModelInvestigator):
    """Times one run of a shipped inference function; memoises per model."""

    def __init__(self, flow):
        super().__init__(flow)
        self.flow = flow

        @flow.function_task
        async def run_profiled(blob, example, model_kwargs):
            fn = cloudpickle.loads(blob)
            t0 = time.monotonic()
            await fn(example, **(model_kwargs or {}))
            return {"runtime": time.monotonic() - t0}

        cache = LRUCache(128)

        async def do_inference(in_data: TypedData):
            blob, example, model_kwargs = in_data.data
            key = freeze((blob, tuple(sorted((model_kwargs or {}).items()))))

            if await cache.exists(key):
                profile = await cache.fetch_item(key)
            else:
                profile = await run_profiled(blob, example, model_kwargs)
                await cache.put_item(key, profile)

            return TypedData(PROFILE_RESULTS,
                             {"profile": profile, "task": in_data.data})

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model()


class ServicePiPredictor(ModelInvestigator):
    """PROFILE_RESULT -> predicted runtime on the Pi endpoint."""

    def __init__(self, flow):
        super().__init__(flow)
        self.flow = flow

        @flow.function_task
        async def predict(in_data):
            import random
            measured = in_data.data["profile"]["runtime"]
            return measured * PI_SLOWDOWN * random.uniform(0.9, 1.1)

        async def do_inference(in_data: TypedData):
            return TypedData(PI_PREDICT_RUNTIME, await predict(in_data))

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model()
