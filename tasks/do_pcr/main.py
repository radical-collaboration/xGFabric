import asyncio
import glob
import os
import subprocess
import time
import logging
import random

import pandas as pd

# step 1
from .partition_pcr_grid import PCR_Partition_Grid

# step 2
from .prepare_pcr_data import prepare_machine_data

# step 3
from .train_pcr_chunk import train_chunk

logger = logging.getLogger(__name__)


async def tk_do_pcr(config, sims_list, sensor_values):
    unique_id = random.randint(0, 40000)
    logger.info(
        f"Task do_pinn fired: {time.time()}. Unique ID: {unique_id}. Called by: {config['PARENT_UNIQUE_ID']}"
    )

    # create directory for models
    task_dir = config["PIPELINE_DIR"] + "/models/pinn"
    os.makedirs(task_dir)
    os.makedirs(task_dir + "/results")
    os.makedirs(task_dir + "/logs")
    os.makedirs(task_dir + "/interim")

    env = os.environ.copy()
    env.update(config)

    env["OUTPUT_DIR"] = task_dir + "/results"
    env["LOG_DIR"] = task_dir + "/logs"
    env["INTERIM_DIR"] = task_dir + "/interim"

    cwd = os.getcwd()
    os.chdir(env["INTERIM_DIR"])

    # partition PCR grid
    machinecount = int(env["PCR_MACHINE_SPLITS"])

    script_dir = os.path.dirname(__file__)
    grid = PCR_Partition_Grid(script_dir + "/grid_config.json")
    data, data_w_points = grid.partition_grid_equally(machinecount)

    sensor_df = pd.DataFrame(sensor_values)

    machine_data_outputs = prepare_machine_data(
        sensor_df, sims_list, data_w_points, env["OUTPUT_DIR"]
    )

    # eventually parallelize this
    for i, machine in enumerate(machine_data_outputs):
        logger.info(f"Processing machine {i}")
        train_chunk(machine, env["OUTPUT_DIR"])
    # outputs are in env['OUTPUT_DIR']/pcr_coefficients_*.csv

    os.chdir(cwd)

    # results should be in env['OUTPUT_DIR']
    files_to_archive = list(glob.glob(env["OUTPUT_DIR"] + "/pcr_coefficients_*.csv"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.json"))

    # keep everything after OUTPUT_DIR
    for i in range(len(files_to_archive)):
        files_to_archive[i] = files_to_archive[i][len(env["OUTPUT_DIR"]) + 1 :]

    # launch tar.
    cmd_tar = [
        "tar",
        "-czf",
        env["OUTPUT_DIR"] + "/pcr.tar.gz",
        "-C",
        env["OUTPUT_DIR"],
    ] + files_to_archive
    # logger.info(f"Running tar: {' '.join(cmd_tar)}")

    tarproc = subprocess.Popen(
        cmd_tar,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tarproc.communicate()

    if tarproc.returncode != 0:
        logger.warning(f"Error executing tar!")
        raise ValueError(f"Error executing tar! Files: {files_to_archive}")

    return unique_id, env["OUTPUT_DIR"] + "/pcr.tar.gz"
