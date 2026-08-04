# Contains the DAG (more like ROSE structure) connecting the tasks together.
#
print("TOP OF FILE")

#
# # Example standalone implementation of RBF surrogate modeling from xGFabric project.
#
#
# 1. Gather raw input data.
# 2. Generate simulations given input data
# 3. Train three models (in parallel)


import glob
import inspect
from pathlib import Path
import shlex

from dotenv import load_dotenv

from reports.plot_workflow_dashboard import plot_split
from reports.plot_workflow_gantt import plot as plot_gantt

from tasks.common.communicator import (
    CommunicatorOpen,
    DirectCommunicator,
    FileWooFCommunicator,
    PyStorage,
)
from tasks.common.log_formatter import register_log_main

load_dotenv("tasks/common/config.sh")
import rhapsody
import logging

rhapsody.enable_logging(
    level=logging.INFO,
)

import asyncio
import os
from radical.asyncflow import WorkflowEngine
import logging
from rose.al.active_learner import Learner

from utils_architecture import verify_config, get_fdate

# Load backends:
from resources.local_cpu import LocalCPU
from resources.nersc_cpu import NerscCPU
from resources.nersc_gpu import NerscGPU

# Tasks:
import wrapper

verify_config()

# Telemetry must be disabled for LocalCPU backend
ENABLE_TELEMETRY = True
NODE_COUNT = 1
CONCURRENCY_LIMIT = 4

WRAPPER_CMD = "python3 wrapper.py"

# for testing the entire pipeline but only on 1 sim for speed
SHORT_RUN = True


async def main():
    # Setup environment
    # Create interim directory for storing logs / outputs
    dt_str = get_fdate()
    os.makedirs(os.getenv("PLAYGROUND_DIR") + f"/run_{dt_str}")
    os.environ["PLAYGROUND_DIR"] = os.getenv("PLAYGROUND_DIR") + f"/run_{dt_str}"

    workflow_file = os.environ["PLAYGROUND_DIR"] + "/workflow.sh"
    with open(workflow_file, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("# Recorded exec calls: \n\n")

    # Get backends
    nersc_cpu = NerscCPU(node_count=NODE_COUNT)
    backend_nersc_cpu = await nersc_cpu.get_backend()
    asyncflow = await WorkflowEngine.create(
        backend=[backend_nersc_cpu],
    )

    if ENABLE_TELEMETRY:
        telemetry = await asyncflow.start_telemetry(
            resource_poll_interval=0.5,
            checkpoint_path=os.getenv("PLAYGROUND_DIR") + "/telemetry",
        )

    logger = register_log_main(
        os.getenv("PLAYGROUND_DIR") + "/rose.log",
        os.getenv("PLAYGROUND_DIR") + "/libs.log",
        logging.INFO,
    )

    # Setup environment
    logger.info("Warming up post engine creation....")

    # Define ROSE APP style
    acl = Learner(asyncflow)

    # Define tasks
    @acl.utility_task
    async def get_data(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)
        storage = PyStorage(inputs_complete)
        comm = DirectCommunicator("")
        input_url = comm.send(storage.serialize())
        comm.close()
        # bash is required for the dragon backend as dragon messes with a plain
        # python executable.
        cmd = f"{WRAPPER_CMD} get_data {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.simulation_task
    async def do_sim(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)
        storage = PyStorage(inputs_complete)
        comm = DirectCommunicator("")
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} do_sim {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.training_task
    async def do_pinn(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)
        storage = PyStorage(inputs_complete)
        comm = DirectCommunicator("")
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} do_pinn {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.training_task
    async def do_fno(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)

        storage = PyStorage(inputs_complete)
        comm = DirectCommunicator("")
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} do_fno {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.training_task
    async def do_pcr_partition(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)
        storage = PyStorage(inputs_complete)
        comm = DirectCommunicator("")
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} do_pcr_partition {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.training_task
    async def do_pcr(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)
        storage = PyStorage(inputs_complete)
        # inputs are too large for direct - assumes log can handle at least 72
        # PCR inputs
        comm = FileWooFCommunicator(os.getenv("TK_DO_PCR_SRC"))
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} do_pcr {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.training_task
    async def do_pcr_pack(*inputs):
        inputs_complete = []
        for input in inputs:
            if inspect.isawaitable(input):
                inputs_complete.append(await input)
            else:
                inputs_complete.append(input)
        storage = PyStorage(inputs_complete)
        # inputs are too large for direct
        comm = FileWooFCommunicator(os.getenv("TK_DO_PCR_PACK_SRC"))
        assert len(os.getenv("TK_DO_PCR_PACK_SRC")) > 0
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} do_pcr_pack {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    @acl.utility_task
    async def to_edge(*inputs):
        logger.debug(f"Inputs to_edge: {inputs}")
        storage = PyStorage(inputs)
        comm = DirectCommunicator("")
        input_url = comm.send(storage.serialize())
        comm.close()
        cmd = f"{WRAPPER_CMD} to_edge {shlex.quote(input_url)}"
        logger.info(f"Call {cmd}")
        # write out
        with open(workflow_file, "a") as f:
            f.write(cmd + "\n")
        return cmd

    # Create pipeline
    async def pipeline(pipeline_id):
        async with asyncflow.workflow_scope(1):
            # if True:
            logger.info("Start pipeline!")

            # Create directory to store logs and results
            pipeline_playground = f"{os.getenv('PLAYGROUND_DIR')}/{pipeline_id}"
            os.makedirs(pipeline_playground)
            config = {"PIPELINE_DIR": pipeline_playground, "PIPELINE_ID": pipeline_id}

            # Pass in data to get_data
            ret = await get_data(config)
            url_to_sensor_data = wrapper.fetch_url(ret)

            # Extract sensor data and split into individual jobs

            comm = CommunicatorOpen(url_to_sensor_data)
            storage = PyStorage.loads(comm.recv())
            sensor_data = storage.retrieve()
            comm.close()

            # sensor_data spits out 72 points. Run one sim per point.

            sim_jobs = []
            sims = []
            counter = 0
            policies = nersc_cpu.create_cpu_policies(policy_count=CONCURRENCY_LIMIT)
            for policy in policies:
                logger.info(f"Simulation Policy: {policy}")
            for i, data_point in enumerate(sensor_data):
                sim_jobs.append(
                    do_sim(
                        config,
                        data_point,
                        i,
                        task_description={
                            "process_template": {"policy": policies[i % len(policies)]}
                        },
                    )
                )
                if SHORT_RUN:
                    break
                counter += 1
                if counter == CONCURRENCY_LIMIT:
                    logger.info(f"Awaiting based on concurrency limit")
                    sims += await asyncio.gather(*sim_jobs)
                    logger.debug(f"Sims: {sims}")
                    sim_jobs = []
                    counter = 0

            logger.debug(f"Awaiting remaining {sim_jobs}")
            sims += await asyncio.gather(*sim_jobs)

            # barrier. Wait for all sims to complete

            sim_ids = ""
            data_list = []
            for ret in sims:
                url = wrapper.fetch_url(ret)

                comm = CommunicatorOpen(url)
                storage = PyStorage.loads(comm.recv())
                sim_id, wind_speed, sim_csv = storage.retrieve()
                comm.close()

                sim_ids = str(sim_id) + ","
                data_list.append((wind_speed, sim_csv))

            # now, train using the results form the sims
            # then push to edge when complete

            train_jobs = []

            @asyncflow.block
            async def fno_block(config, data_list, sensor_data_url):
                t_policy = nersc_cpu.create_cpu_policies(
                    policy_count=CONCURRENCY_LIMIT, core_count=128
                )
                for policy in t_policy:
                    logger.info(f"FNO Policy: {policy}")

                fno = await do_fno(
                    config,
                    data_list,
                    task_description={
                        "process_template": {"policy": t_policy[0 % len(t_policy)]}
                    },
                )
                fno_out = wrapper.fetch_url(fno)

                return await to_edge(
                    config,
                    fno_out,
                    "fno",
                )

            train_jobs.append(fno_block(config, data_list, url_to_sensor_data))

            @asyncflow.block
            async def pinn_block(config, data_list, sensor_data_url):
                t_policy = nersc_cpu.create_cpu_policies(
                    policy_count=CONCURRENCY_LIMIT, core_count=128
                )
                for policy in t_policy:
                    logger.info(f"PINN Policy: {policy}")

                pinn = await do_pinn(
                    config,
                    data_list,
                    task_description={
                        "process_template": {"policy": t_policy[0 % len(t_policy)]}
                    },
                )
                pinn_out = wrapper.fetch_url(pinn)

                return await to_edge(
                    config,
                    pinn_out,
                    "pinn",
                )

            train_jobs.append(pinn_block(config, data_list, url_to_sensor_data))

            @asyncflow.block
            async def pcr_block(config, data_list, sensor_data_url):
                # do this independently of the workflow

                pcr_policy = nersc_cpu.create_cpu_policies(
                    policy_count=int(os.getenv("PCR_MACHINE_SPLITS")), core_count=2
                )

                partitions = await do_pcr_partition(
                    config,
                    data_list,
                    sensor_data_url,
                )

                url = wrapper.fetch_url(partitions)
                comm = CommunicatorOpen(url)
                storage = PyStorage.loads(comm.recv())
                partitions = storage.retrieve()

                pcr_jobs = []
                logger.info(f"{len(partitions)} jobs created by partitioned")
                # logger.info(f"{len(pcr_policy)} policies created")
                for i, partition in enumerate(partitions):
                    pcr_jobs.append(
                        do_pcr(
                            config,
                            partition,
                            task_description={
                                "process_template": {"policy": pcr_policy[i]}
                            },
                        )
                    )
                    if SHORT_RUN:
                        break

                all_jobs = await asyncio.gather(*pcr_jobs)
                out = []
                for i in all_jobs:
                    out.append(wrapper.fetch_url(i))

                pcr_finish = await do_pcr_pack(config, *out)
                pcr_out = wrapper.fetch_url(pcr_finish)
                return await to_edge(config, pcr_out, "pcr")

            train_jobs.append(pcr_block(config, data_list, url_to_sensor_data))

            edge_result = await asyncio.gather(*train_jobs)

            logger.info(f"Pipeline completed!")

    results = await pipeline(1)

    await asyncio.sleep(1)
    logger.info(f"Program complete! Results: {results}")

    if ENABLE_TELEMETRY:
        logger.info(f"Telemetry summary: {telemetry.summary()}")
        await telemetry.stop()
        await acl.shutdown()

        # Call reports
        for f in glob.glob(
            os.getenv("PLAYGROUND_DIR") + "/telemetry/*.telemetry.jsonl"
        ):
            plot_split(f)

        for f in glob.glob(
            os.getenv("PLAYGROUND_DIR") + "/telemetry/*.telemetry.jsonl"
        ):
            plot_gantt(Path(f))
    else:
        await acl.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
