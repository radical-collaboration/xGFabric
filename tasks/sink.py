import asyncio

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from .common.dtypes import *

import logging

logger = logging.getLogger(__name__)


class CUPS_Sink(UtilityTask):
    def __init__(self, flow: WorkflowEngine, config):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        print(f"Received Inference: {in_data.data}")

        # if model_name == "pcr":
        #     endpoint = os.getenv("PCR_ENDPOINT")
        # elif model_name == "fno":
        #     endpoint = os.getenv("FNO_ENDPOINT")
        # elif model_name == "pinn":
        #     endpoint = os.getenv("PINN_ENDPOINT")

        # target = FileWooF(endpoint)
        # result = target.send(model)
