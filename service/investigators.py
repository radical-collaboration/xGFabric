"""Service-safe surrogate investigators: FNO / PINN / PCR stand-ins.

Each keeps the real investigators' shape -- batch sensor windows, run a
"training" flow task on the endpoint, publish the model, serve field
inference -- with fake physics: training sleeps an architecture-typical
time and inference synthesizes a wind field.  What stays real is the
part the demo is about: three architectures with different costs
competing for selection, and the shared simulation subtask feeding all
of them (memoised once per sensor window, see SIM_MASTER).
"""

import asyncio
import random

import numpy as np

from digitaltwin.components import ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

from tasks.common.dtypes import SIM_MASTER, WIND_FIELD

# architecture-typical (train_seconds, inference_seconds) -- the spread is
# what makes profiler-driven selection visible
ARCH_COST = {
    "fno": (6.0, 0.20),
    "pinn": (9.0, 0.60),
    "pcr": (3.0, 0.05),
}

WINDOW = 4  # sensor points per training window


class SurrogateInvestigator(ModelInvestigator):
    """One fake surrogate; ``arch`` picks its cost profile."""

    def __init__(self, flow, arch: str):
        super().__init__(flow)
        self.flow = flow
        self.arch = arch
        self.batch: list = []
        train_s, infer_s = ARCH_COST[arch]

        @flow.function_task
        async def train(arch, points, sim):
            # endpoint-side "training": cost is the architecture's
            await asyncio.sleep(train_s)
            speeds = [p["wind_speed"] for p in points]
            return {"model": arch, "w": float(np.mean(speeds)) / 20.0,
                    "sim": sim[1]}

        @flow.function_task
        async def infer(in_data, model="na", w=0.0, **_):
            await asyncio.sleep(infer_s)
            if model == "na":
                return TypedData(WIND_FIELD,
                                 {"arch": "na", "w": w, "result": None})
            # synthesized field: smooth bump scaled by the model weight
            x = np.linspace(-2, 2, 32)
            xx, yy = np.meshgrid(x, x)
            field = (2.5 * w) * np.exp(-(xx ** 2 + yy ** 2))
            field += np.random.default_rng().normal(0, 0.05, field.shape)
            return TypedData(WIND_FIELD,
                             {"arch": model, "w": w, "result": (3, field)})

        self._train = train
        self._infer = infer

    async def _on_input(self, in_data: TypedData) -> None:
        self.batch.append(in_data.data)

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.subscribe_to_topic(runtime.ON_INPUT, self._on_input)
        runtime.set_inference_task(self._infer)
        runtime.publish_new_model({"model": "na", "w": 0.0})

        while True:
            if len(self.batch) < WINDOW:
                await asyncio.sleep(1.0)
                continue

            points, self.batch = self.batch[:WINDOW], self.batch[WINDOW:]
            # one simulation per window, shared and memoised across the
            # three investigators -- the SIM_MASTER contract from twin.py
            sim = await runtime.call_shared_subtask(SIM_MASTER, points[0])
            model = await self._train(self.arch, points, sim)
            runtime.publish_new_model(model, {"quality": random.random()})
