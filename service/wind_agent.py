"""The WindField agent, service-safe.

Structure and selection logic mirror ``tasks.wind_agent.WindFieldAgent``:
three surrogate investigators under one agent, a shared (memoised)
simulation subtask, and a model selector that ranks published models by
their profiler-predicted Pi runtime -- fetched through the twin's own
``get_inference`` chain (task description -> profile -> predicted
runtime).  Only the physics behind those steps is faked.
"""

import asyncio
import random

import cloudpickle

from digitaltwin.components import SciAgent, TypedData, DataType
from digitaltwin.runtime import RuntimeAPI

from tasks.common.dtypes import SIM_MASTER, DAVIS_WIND_SENSOR
from service.investigators import SurrogateInvestigator
from service.profiler import PI_PREDICT_RUNTIME, PROFILE_RESULTS, \
    TASK_DESCRIPTION_DTYPE


class ServiceWindFieldAgent(SciAgent):
    def __init__(self, flow):
        super().__init__(flow)
        self.flow = flow

        self.fno = SurrogateInvestigator(flow, "fno")
        self.pinn = SurrogateInvestigator(flow, "pinn")
        self.pcr = SurrogateInvestigator(flow, "pcr")

        @flow.function_task
        async def simulate(sensor_pt):
            # twin.py's tk_do_simulation is already faked to a random
            # quality plus a precomputed-sim path; same here, local path
            await asyncio.sleep(1.0)
            return (random.random(), f"precalc_sims/{random.randint(0, 71)}.csv")

        self.sim_master = simulate

        @flow.function_task
        async def model_select(in_data: TypedData, models):
            # the demo's crown jewel: pick the model with the shortest
            # profiler-PREDICTED runtime on the Pi
            if not models:
                return 0
            best = min(models, key=lambda m: m["pi_runtime"])
            return best["investigator"]

        self.model_selector = model_select

        self.model_to_process: asyncio.Queue[dict] = asyncio.Queue()
        self.models: list[dict] = []

    async def model_publish_cb(self, inv, model_args: dict, acc: dict):
        await self.model_to_process.put({
            "investigator": inv.get_id(),
            "model_args": model_args,
            "metrics": acc,
        })

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.start_investigator(self.fno)
        runtime.start_investigator(self.pinn)
        runtime.start_investigator(self.pcr)

        runtime.register_shared_subtask(SIM_MASTER, self.sim_master, 64)
        runtime.subscribe_to_topic(runtime.ON_MODEL_PUBLISH,
                                   self.model_publish_cb)

        runtime.set_model_selection_task(self.model_selector)
        runtime.update_model_selector(models=[])

        while True:
            item = await self.model_to_process.get()
            if item["model_args"]["model"] == "na":
                continue

            raw = runtime.get_inference_tasks()[item["investigator"]]
            raw = getattr(raw, "__wrapped__", raw)

            probe_pt = {"dt": "probe", "wind_speed": 10.0,
                        "wind_avg": 8.0, "wind_dir": 180.0}
            description = (cloudpickle.dumps(raw),
                           TypedData(DAVIS_WIND_SENSOR, probe_pt),
                           item["model_args"])

            profile = await runtime.get_inference(
                TypedData(TASK_DESCRIPTION_DTYPE, description),
                PROFILE_RESULTS)
            pi = await runtime.get_inference(profile, PI_PREDICT_RUNTIME)

            item["pi_runtime"] = pi.data
            self.models.append(item)
            runtime.update_model_selector(models=self.models[-10:])
