"""A visible learning lane for the real twin.

The real workload's own learners (FNO/PINN/PCR and the Pi predictor) run
on the twin's default ('inference') engine, so the dashboard shows no
distinct learning lane.  This component adds one: it consumes the same
wind-sensor stream, and every window of points runs a training task
routed to the 'learning' backend -- exactly the labeling trick from the
service demo's SurrogateInvestigator (@function_task(backend=...)).  It
publishes to its own WIND_TREND dtype, so it never competes with the
real WIND_FIELD path feeding the sink.
"""

import asyncio
import random

from digitaltwin.components import DataType, ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

WIND_TREND = DataType("WindTrend_dt")

WINDOW = 4          # sensor points per training window
TRAIN_SECONDS = 4.0  # endpoint-side "training" cost, visible in the lane


class WindTrendLearner(ModelInvestigator):
    """Online mean-wind learner; its training runs in the learning lane."""

    def __init__(self, flow, learn_backend: str | None = None):
        super().__init__(flow)
        self.flow = flow
        self.batch: list = []

        # the label rides here: with learn_backend='learning' the training
        # task routes to the session's learning engine and shows in its own
        # lane; inference stays on the default engine.  backend=None is the
        # plain default (asyncflow has no aliasing -- a label is set only
        # when the caller declares the matching engine).
        @flow.function_task(backend=learn_backend)
        async def train(points):
            await asyncio.sleep(TRAIN_SECONDS)
            speeds = [p["wind_speed"] for p in points]
            return {"model": "wind_trend", "mean": sum(speeds) / len(speeds)}

        @flow.function_task
        async def infer(in_data, model="na", mean=0.0, **_):
            return TypedData(WIND_TREND, {"model": model, "mean": mean})

        self._train = train
        self._infer = infer

    async def _on_input(self, in_data: TypedData) -> None:
        self.batch.append(in_data.data)

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.subscribe_to_topic(runtime.ON_INPUT, self._on_input)
        runtime.set_inference_task(self._infer)
        runtime.publish_new_model({"model": "na", "mean": 0.0})

        while True:
            if len(self.batch) < WINDOW:
                await asyncio.sleep(1.0)
                continue

            points, self.batch = self.batch[:WINDOW], self.batch[WINDOW:]
            model = await self._train(points)
            runtime.publish_new_model(model, {"quality": random.random()})
