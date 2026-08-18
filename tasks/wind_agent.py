import asyncio


from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData, SciAgent
from digitaltwin.runtime import RuntimeAPI

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
        self.sim_counter = 0

        @self.flow.function_task
        async def simulate(config, sensor_pt):
            print("Do simulation")
            wind, fname = tk_do_simulation(config, sensor_pt)
            return wind, fname

        async def wrapper(sensor_pt):
            ct = self.sim_counter
            self.sim_counter += 1
            self.config["TASK_COUNTER"] = self.sim_counter
            return await simulate(self.config, sensor_pt)

        self.sim_master = wrapper

        # Investigators:
        self.fno = FNOInvestigator(flow, self.config)
        self.pinn = PINNInvestigator(flow, self.config)
        self.pcr = PCRInvestigator(flow, self.config)

        @self.flow.function_task
        async def model_select(in_data: TypedData, i):
            return i  # default to latest model

        self.model_selector = model_select

    async def main_loop(self, runtime: RuntimeAPI):

        runtime.start_investigator(self.fno)
        runtime.start_investigator(self.pinn)
        runtime.start_investigator(self.pcr)

        runtime.register_shared_subtask(
            SIM_MASTER, self.sim_master, int(self.config["CSPOT_LIMIT"])
        )

        # set model selector. Set FNO as first.
        runtime.set_model_selection_task(self.model_selector)
        runtime.update_model_selector(i=self.fno.get_id())
