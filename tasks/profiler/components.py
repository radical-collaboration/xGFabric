import asyncio
import json
import os
import random
import shlex
from typing import Optional


import numpy as np
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import DataType, ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI
from digitaltwin.lru import LRUCache, freeze
from rose import Learner

import logging

try:
    from .profiler import export_inference_function
except:
    from profiler import export_inference_function

logger = logging.getLogger(__name__)

TASK_DESCRIPTION_DTYPE = DataType("TASK_INFO")
PROFILE_RESULTS = DataType("PROFILE_RESULT")

script_path = os.path.dirname(os.path.realpath(__file__))


class ProfilerInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine, workdir: str = "."):
        super().__init__(flow)
        self.flow = flow
        self.workdir = workdir
        # no makedirs here: the profiling runs in-process on the endpoint
        # (below), so there is no file to prepare on this (broker) side.

        @self.flow.function_task
        async def run_profiled(blob, example_data, model_kwargs):
            # runs on the endpoint: reconstruct the candidate's inference
            # callable and measure one call in-process -- no cloudpickle
            # file, no subprocess, nothing written on the broker.
            from .inproc import load_callable, profile_call

            func = load_callable(blob)
            return await profile_call(func, example_data, model_kwargs or {})

        sim_lock = asyncio.Lock()
        sim_lru = LRUCache(128)  # store 128 different sims

        async def do_inference(in_data: TypedData):
            async with sim_lock:
                task, example_data, model_kwargs = in_data.data
                key = freeze((task, model_kwargs))

                if await sim_lru.exists(key):
                    profile = await sim_lru.fetch_item(key)
                    return TypedData(PROFILE_RESULTS,
                                     {"profile": profile, "task": in_data.data})

                r = await run_profiled(task, example_data, model_kwargs)
                await sim_lru.put_item(key, r)
                return TypedData(PROFILE_RESULTS,
                                 {"profile": r, "task": in_data.data})

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model()


# on inference, return predicted time given NERSC time
#
# for simulation, run the inference and add to data set.
def safe_log(r):
    mask = r > 0
    result = np.zeros_like(r, dtype=np.float64)
    result[mask] = np.log2(r[mask])
    return result


PI_CPUS = 4


class EndpointInvestigator(ModelInvestigator):
    def __init__(
        self, flow: WorkflowEngine, name: str, datastore_path: Optional[str] = None
    ):
        super().__init__(flow)
        self.flow = flow
        self.name = name
        if datastore_path is None:
            self.datastore = f"./{name}"
        else:
            self.datastore = datastore_path

        # NOT created here: __init__ runs on the broker, but the datastore
        # is an endpoint path (where the tasks read/write it).  The
        # endpoint-side tasks makedirs it (stage_inf / append_row).
        try:
            os.makedirs(self.datastore, exist_ok=True)
        except OSError:
            pass

        self.callback_jobs: asyncio.Queue = asyncio.Queue()
        self.done_jobs: set = set()

        self.learner = Learner(flow)

        @self.flow.function_task
        async def exec_profiler(task_data):
            # the endpoint ("Pi") measurement, in-process on this endpoint:
            # run the candidate's inference and read the counters, no
            # cloudpickle file and no subprocess (approach 1).
            from .inproc import load_callable, profile_call

            task, example_data, model_kwargs = task_data
            func = load_callable(task)
            return await profile_call(func, example_data, model_kwargs or {})

        self.exec_profiler = exec_profiler

        @self.learner.training_task
        async def train_model():
            return shlex.join(
                [
                    "python3",
                    f"{script_path}/endpoint_trainer.py",
                    f"{self.datastore}/data.csv",
                    f"{self.datastore}/model.json",
                ]
            )

        self.train_task = train_model

        @self.flow.function_task
        async def append_row(datastore, row):
            # runs on the endpoint (a function_task body IS the task), so the
            # row lands in the same data.csv that train_model (executable,
            # also endpoint) reads -- see main_loop.  Doing this append in
            # main_loop instead would write it on the broker, on a different
            # filesystem from the training task.
            import os

            os.makedirs(datastore, exist_ok=True)
            with open(f"{datastore}/data.csv", "a") as fh:
                fh.write(row + "\n")

        self._append_row = append_row

        @self.flow.function_task
        async def stage_inf(datastore, pf):
            # write endpoint_eval's input on the endpoint (a function_task
            # body runs there), so the executable command below reads it on
            # the same host -- not the broker, where the executable-task
            # command-builder runs.
            import json as _json
            import os

            os.makedirs(datastore, exist_ok=True)
            with open(f"{datastore}/inf.json", "w") as fh:
                _json.dump(pf, fh)

        self._stage_inf = stage_inf

        @self.flow.executable_task
        async def call_inference(in_data: TypedData, model=None, name=""):
            pf = in_data.data["profile"]
            # stage the input endpoint-side before the command runs
            await self._stage_inf(self.datastore, pf)
            return shlex.join(
                [
                    "python3",
                    f"{script_path}/endpoint_eval.py",
                    model,
                    f"{self.datastore}/inf.json",
                ]
            )

        # inference de-duplication
        inf_cache = LRUCache()
        inf_lock = asyncio.Lock()

        async def do_inference(in_data: TypedData, model=None, name=""):
            async with inf_lock:
                key = freeze(in_data.data["profile"])
                if await inf_cache.exists(key):
                    return await inf_cache.fetch_item(key)

                # call inference
                result = await call_inference(in_data, model)
                out = TypedData(DataType(f"{self.name}_PREDICT_RUNTIME"), float(result))
                await inf_cache.put_item(key, out)
                return out

        self.inference_task = do_inference

    # inference callback

    async def input_callback(self, in_data: TypedData):
        # add nersc output to input_callback

        # only 10% of the time, run the actual inference task and add to csv
        if random.random() > 0.1:
            return

        # hold on.... check if already done!
        key = freeze(in_data.data["profile"])
        if key in self.done_jobs:
            return
        self.done_jobs.add(key)
        await self.callback_jobs.put(in_data.data)

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.input_callback)
        # create first model
        out = json.loads(await self.train_task())
        model = out["model"]
        mae = out["mae"]
        runtime.publish_new_model({"model": model, "name": self.name}, {"mae": mae})
        print(f"Baseline endpoint model MAE: {mae}, {model}")

        while True:
            item = await self.callback_jobs.get()
            # exec_profiler now returns the profile dict (in-process); the
            # Pi runtime is its wall time
            pi_profile = await self.exec_profiler(item["task"])
            pi_time = str(pi_profile["total_seconds"])

            # label the endpoint_time as "pi_seconds"
            nersc_profile = item["profile"]
            out = ",".join([str(f) for f in nersc_profile.values()]) + ","
            out += pi_time

            # append on the endpoint (where train_model reads data.csv), not
            # here on the broker -- see append_row
            await self._append_row(self.datastore, out)

            out = json.loads(await self.train_task())
            model = out["model"]
            mae = out["mae"]
            runtime.publish_new_model({"model": model, "name": self.name}, {"mae": mae})
            print(f"New endpoint model MAE: {mae}")


if __name__ == "__main__":
    # profiler tester
    from radical.asyncflow.logging import init_default_logger
    from rhapsody.backends import ConcurrentExecutionBackend
    from concurrent.futures import ProcessPoolExecutor
    from digitaltwin.streaming import connect_stream_client
    from digitaltwin.runtime import DTRuntime
    from digitaltwin.components import UtilityTask, TRUTHY, NULL_DTYPE
    from digitaltwin.streaming import PubSubConfig
    import time
    import cloudpickle

    class TestUtility(UtilityTask):
        def __init__(self, flow: WorkflowEngine):
            super().__init__(flow)
            self.flow = flow

            # @self.flow.function_task
            async def test(ps_config: PubSubConfig):
                ps = await ps_config.connect()
                for i in range(30):

                    def sample_task(in_data, a=0):
                        pass  # time.sleep(1)

                    task_description = (
                        cloudpickle.dumps(sample_task),
                        TypedData(DataType("A"), 1),
                        {"a": 2},
                    )
                    await ps.publish(TASK_DESCRIPTION_DTYPE, task_description)
                    await asyncio.sleep(5)

            self.task = test

        async def main_loop(self, runtime: RuntimeAPI, in_data):
            await self.task(runtime.stream_config)

    class TestSink(UtilityTask):
        def __init__(self, flow: WorkflowEngine):
            super().__init__(flow)
            self.flow = flow

            @self.flow.function_task
            async def echo(in_data):
                print(f"Received Inference: {in_data.dtype}: {in_data.data}")

            self.echo = echo

        async def main_loop(self, runtime, in_data):
            await self.echo(in_data)

    async def main():
        init_default_logger(logging.INFO)

        # create engine
        exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
        flow = await WorkflowEngine.create(backend=exe)

        # create the twin's namespaced stream client
        pubsub_client = await connect_stream_client("test_profiler")

        runtime = DTRuntime(flow, pubsub_client)

        prof = ProfilerInvestigator(flow, "./nersc_profiler")
        pi_endpoint = EndpointInvestigator(flow, "pi", "./pi_profiler")
        src = TestUtility(flow)
        dst = TestSink(flow)

        runtime.add_task(src, TRUTHY, TASK_DESCRIPTION_DTYPE, True)
        runtime.add_investigator(prof, TASK_DESCRIPTION_DTYPE, PROFILE_RESULTS)
        runtime.add_investigator(
            pi_endpoint, PROFILE_RESULTS, DataType("pi_PREDICT_RUNTIME")
        )
        runtime.add_task(dst, DataType("pi_PREDICT_RUNTIME"), NULL_DTYPE)
        # runtime.add_task(dst, PROFILE_RESULTS, NULL_DTYPE)

        runtime.print_graph()

        runtime.start()

        await asyncio.sleep(30)

        await runtime.stop()
        await flow.shutdown()

    asyncio.run(main())
