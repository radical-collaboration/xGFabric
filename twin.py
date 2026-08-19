import asyncio
import glob
import os
from pathlib import Path
from radical.asyncflow import WorkflowEngine

from digitaltwin.runtime import DTRuntime, PubSubClient
from digitaltwin.streaming import ZMQ_PS_Client
from digitaltwin.components import TRUTHY, NULL_DTYPE

from reports.plot_workflow_dashboard import plot_split
from reports.plot_workflow_gantt import plot as plot_gantt

from tasks.davis import DavisWind
from tasks.common.dtypes import *
from tasks.sink import CUPS_Sink
from tasks.wind_agent import WindFieldAgent

from radical.asyncflow.logging import init_default_logger
import logging
import dotenv

logger = logging.getLogger(__name__)

dotenv.load_dotenv("tasks/common/config.sh")

import rhapsody

rhapsody.enable_logging(level=logging.INFO)
from utils_architecture import register_master_run, verify_config, get_fdate
from tasks.common.log_formatter import register_log_main

# Load backends:
from resources.local_cpu import LocalCPU

# from resources.nersc_cpu import NerscCPU
# from resources.nersc_gpu import NerscGPU

ENABLE_TELEMETRY = True


async def main():
    config = register_master_run()
    logger = register_log_main(config, logging.INFO)
    logging.getLogger("radical.asyncflow").setLevel(logging.WARNING)
    logging.getLogger("rhapsody").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

    # Get backends
    exe = LocalCPU()  # node_count=config["NODE_COUNT"]
    backend = await exe.get_backend()
    flow = await WorkflowEngine.create(backend=[backend])

    if ENABLE_TELEMETRY:
        telemetry = await flow.start_telemetry(
            resource_poll_interval=0.5,
            checkpoint_path=config["PLAYGROUND_DIR"] + "/telemetry",
        )

    # Create stream
    ZMQ_PUB_ADDR = config.get("DT_STREAM_PUB_ADDR", "tcp://127.0.0.1:5000")
    ZMQ_SUB_ADDR = config.get("DT_STREAM_SUB_ADDR", "tcp://127.0.0.1:5001")

    # create the twin's namespaced stream client
    stream_backend = ZMQ_PS_Client(ZMQ_PUB_ADDR, ZMQ_SUB_ADDR)
    await stream_backend.connect()
    ps_client = PubSubClient(stream_backend, "cups")

    # create runtime.
    runtime = DTRuntime(flow, ps_client)

    # start a telemetry scope

    # xGFabric Graph....
    wind_sensor = DavisWind(flow, config)
    field = WindFieldAgent(flow, config)
    sink = CUPS_Sink(flow, config)

    async with flow.workflow_scope(1):

        runtime.add_task(wind_sensor, TRUTHY, DAVIS_WIND_SENSOR, is_persistent=True)
        runtime.add_agent(field, DAVIS_WIND_SENSOR, WIND_FIELD)
        runtime.add_task(sink, WIND_FIELD, NULL_DTYPE)

        runtime.print_graph()
        runtime.start()

        # let it run
        await asyncio.sleep(5 * 60)  # 5 minutes
        print("DONE======================")
        await runtime.stop()

    if ENABLE_TELEMETRY:
        logger.info(f"Telemetry summary: {telemetry.summary()}")
        await telemetry.stop()

        # Call reports
        for f in glob.glob(config["PLAYGROUND_DIR"] + "/telemetry/*.telemetry.jsonl"):
            plot_split(f)

        for f in glob.glob(config["PLAYGROUND_DIR"] + "/telemetry/*.telemetry.jsonl"):
            plot_gantt(Path(f))

    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
