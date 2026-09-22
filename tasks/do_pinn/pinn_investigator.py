import asyncio
import types

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import Any, ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

# NOTE: `.main` pulls TensorFlow at import -- imported lazily in the task
# bodies below (which run on the endpoint) so client/broker stay TF-free.

from rose.al.active_learner import Learner

from ..common.dtypes import *

import logging

logger = logging.getLogger(__name__)


class PINNInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine, config: dict):
        super().__init__(flow)
        self.flow = flow

        self.learner = Learner(flow)

        # callback: trigger event
        self.incoming = asyncio.Event()
        self.batch: list[Any] = []
        self.batch_out = ()
        self.config = config.copy()
        self.config["INVESTIGATOR_NAME"] = "pinn"
        self.task_counter = 0

        async def incoming_cb(in_data: TypedData):
            if not self.incoming.is_set():
                self.batch.append(in_data.data)
                logger.info(f"PINN batch: {len(self.batch)} / {config['CSPOT_LIMIT']}")
            else:
                logger.info(f"PINN batch: Drop... already training...")
                return

            if (
                len(self.batch) == int(config["CSPOT_LIMIT"])
                and not self.incoming.is_set()
            ):
                self.incoming.set()
                self.batch_out = tuple(self.batch)
                self.batch = []

        self.incoming_callback = incoming_cb

        @self.flow.function_task
        async def do_inference(in_data: TypedData, config=None, model="na"):
            if model == "na" or config is None:
                # pass through, no model yet
                return TypedData(WIND_FIELD, {"arch": "na"})

            from .main import tk_pinn_eval

            # model available!
            wind = in_data.data["wind_speed"]
            result = tk_pinn_eval(config, model, wind)

            return TypedData(WIND_FIELD, {"arch": "pinn", "result": result, "w": wind})

        self.inference_task = do_inference

    # Training Pipeline
    async def do_train(self, runtime: RuntimeAPI, batch):
        # train: I need to simulate each of the points

        # this below is the sim task. It's shared, so it doesn't use
        # rose sim right here...
        sim_tasks = []
        for point in batch:
            sim_tasks.append(runtime.call_shared_subtask(SIM_MASTER, point))

        sim_fnames = await asyncio.gather(*sim_tasks)

        @self.learner.training_task(as_executable=False)
        async def do_pinn(config, sims):
            from .main import tk_do_pinn
            return tk_do_pinn(config, sims)

        self.config["TASK_COUNTER"] = self.task_counter
        pinn_tar = await do_pinn(self.config.copy(), sim_fnames)
        self.task_counter += 1

        return pinn_tar

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
