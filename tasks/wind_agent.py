import asyncio
import datetime
import random


import cloudpickle
import pandas as pd
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData, SciAgent, DataType
from digitaltwin.runtime import RuntimeAPI

from .davis import strip_cols
from .profiler.components import PROFILE_RESULTS, TASK_DESCRIPTION_DTYPE

from .do_pinn.pinn_investigator import PINNInvestigator
from .do_fno.fno_investigator import FNOInvestigator
from .do_pcr.pcr_investigator import PCRInvestigator

from .do_simulation import tk_do_simulation
from .common.dtypes import *

import logging

logger = logging.getLogger(__name__)


class WindFieldAgent(SciAgent):
    def __init__(self, flow: WorkflowEngine, config: dict):
        super().__init__(flow)
        self.flow = flow
        self.config = config.copy()
        self.config["AGENT_NAME"] = "WindField"
        self.sim_counter = -1

        @self.flow.function_task
        async def simulate(config, sensor_pt):
            print("Do simulation")
            wind, fname = tk_do_simulation(config, sensor_pt)
            return wind, fname

        async def wrapper(sensor_pt):
            self.sim_counter += 1
            self.config["TASK_COUNTER"] = self.sim_counter
            return await simulate(self.config.copy(), sensor_pt)

        self.sim_master = wrapper

        # Investigators:
        self.fno = FNOInvestigator(flow, self.config)
        self.pinn = PINNInvestigator(flow, self.config)
        self.pcr = PCRInvestigator(flow, self.config)

        @self.flow.function_task
        async def model_select(in_data: TypedData, models):
            # select the model with the shortest compute time.
            if len(models) == 0:
                # assume first investigator
                return 0

            shortest = models[0]
            for model in models:
                if model["pi_runtime"] < shortest["pi_runtime"]:
                    shortest = model

            return shortest["investigator"]  # default to latest model

        self.model_selector = model_select

        # resource allocation vars
        self.model_to_process: asyncio.Queue[dict] = asyncio.Queue()
        self.models: list[dict] = []

    async def model_publish_cb(
        self, inv: ModelInvestigator, model_args: dict, acc_metrics: dict
    ):
        await self.model_to_process.put(
            {
                "investigator": inv.get_id(),
                "model_args": model_args,
                "metrics": acc_metrics,
            }
        )

    async def main_loop(self, runtime: RuntimeAPI):

        runtime.start_investigator(self.fno)
        runtime.start_investigator(self.pinn)
        runtime.start_investigator(self.pcr)

        # allow up to 4 full runs before stop dropping.
        runtime.register_shared_subtask(
            SIM_MASTER, self.sim_master, int(self.config["CSPOT_LIMIT"]) * 4
        )
        runtime.subscribe_to_topic(runtime.ON_MODEL_PUBLISH, self.model_publish_cb)

        # set model selector. Set FNO as first.
        runtime.set_model_selection_task(self.model_selector)
        runtime.update_model_selector(models=[])

        # now, for model selection, do an analysis

        while True:
            item = await self.model_to_process.get()

            if item["model_args"]["model"] == "na":
                continue  # ignore null

            infs = runtime.get_inference_tasks()

            raw_inference_task = infs[item["investigator"]].__wrapped__

            # fake sensor
            r = random.random()
            fake = [(datetime.datetime.now(), r * 20, r * 15, r * 360)]
            df = pd.DataFrame(
                fake, columns=["dt", "wind_speed", "wind_avg", "wind_dir"]
            )

            outputs = strip_cols(df)
            example_data = TypedData(
                DAVIS_WIND_SENSOR, outputs.to_dict(orient="records")[0]
            )

            task_description = (
                cloudpickle.dumps(raw_inference_task),
                example_data,
                item["model_args"],
            )
            profile = await runtime.get_inference(
                TypedData(TASK_DESCRIPTION_DTYPE, task_description), PROFILE_RESULTS
            )

            # now, get Pi reading
            pi_runtime = await runtime.get_inference(
                profile, DataType("pi_PREDICT_RUNTIME")
            )

            item["pi_runtime"] = pi_runtime.data
            self.models.append(item)

            if len(self.models) < 10:
                runtime.update_model_selector(models=self.models)
            else:
                # send only last ten.
                runtime.update_model_selector(models=self.models[-10:])
