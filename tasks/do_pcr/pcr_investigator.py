import asyncio
import types

import numpy as np
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import Any, ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

from .main import tk_pcr_eval, tk_pcr_partition
from .main import tk_do_pcr
from .main import tk_do_pcr_pack

from rose.al.active_learner import Learner

from ..common.dtypes import *

import logging

logger = logging.getLogger(__name__)


class PCRInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine, config):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task
        async def do_inference(in_data: TypedData, config=None, model="na"):
            if model == "na" or config is None:
                # pass through, no model yet
                return TypedData(WIND_FIELD, {"arch": "na"})

            # PCR works on a range rather than a single data point.
            # for now, assume the wind is stable.
            wind_single = in_data.data["wind_speed"]
            wind = np.ones(13) * wind_single
            result = tk_pcr_eval(config, model, wind)

            return TypedData(
                WIND_FIELD, {"arch": "pcr", "result": result, "w": wind_single}
            )

        self.inference_task = do_inference

        # callback: trigger event
        self.incoming = asyncio.Event()
        self.batch: list[Any] = []
        self.batch_out = ()
        self.config = config.copy()
        self.config["INVESTIGATOR_NAME"] = "pcr"
        self.task_counter = 0

        async def incoming_cb(in_data: TypedData):
            self.batch.append(in_data.data)
            logger.info(f"PCR batch: {len(self.batch)} / {config['CSPOT_LIMIT']}")
            if len(self.batch) == int(config["CSPOT_LIMIT"]):
                self.incoming.set()
                self.batch_out = tuple(self.batch)
                self.batch = []

        self.incoming_callback = incoming_cb

        # Training Pipeline

    async def do_train(self, runtime: RuntimeAPI, batch):

        # train: I need to simulate each of the points

        # this below is the sim task. It's shared, so it doesn't use
        # rose sim right here...

        sim_tasks = []
        for point in batch:
            sim_tasks.append(runtime.call_shared_subtask(SIM_MASTER, point))

        sim_fnames = await asyncio.gather(*sim_tasks)

        # now, given the sims, create a PCR dataflow.

        @self.flow.function_task
        async def partition(config, sims, sensor_vals):
            return tk_pcr_partition(config, sims, sensor_vals)

        @self.flow.function_task
        async def do_pcr(config, machine_data_output):
            return tk_do_pcr(config, machine_data_output)

        @self.flow.function_task
        async def do_pack(config, *pcr_output_dirs):
            return tk_do_pcr_pack(config, *pcr_output_dirs)

        self.config["TASK_NAME"] = "partition"
        self.config["TASK_COUNTER"] = self.task_counter
        parts = await partition(self.config.copy(), sim_fnames, batch)

        self.config["TASK_NAME"] = f"do_pcr/{self.task_counter}"

        tk = []
        for i, part in enumerate(parts):
            self.config["TASK_COUNTER"] = i
            tk.append(do_pcr(self.config.copy(), part))

        results = await asyncio.gather(*tk)

        self.config["TASK_NAME"] = "pack"
        self.config["TASK_COUNTER"] = self.task_counter
        finish = do_pack(self.config.copy(), *results)
        self.task_counter += 1

        return {"model": finish}

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)

        # register callback
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.incoming_callback)
        runtime.publish_new_model({"config": None, "model": "na"})

        # Main loop: drain on the queue
        while True:
            await self.incoming.wait()
            batch = self.batch_out

            model = await self.do_train(runtime, batch)
            cpy = self.config.copy()
            runtime.publish_new_model({"config": cpy, "model": model})
            self.incoming.clear()
