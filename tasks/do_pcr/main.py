import asyncio
import glob
import os
import subprocess
import time
import logging
import random
import datetime

import pandas as pd

from ..common.log_formatter import register_task, register_log, close_task

# step 1
from .partition_pcr_grid import PCR_Partition_Grid

# step 2
from .prepare_pcr_data import prepare_machine_data

# step 3
from .train_pcr_chunk import train_chunk

logger = logging.getLogger(__name__)


async def tk_pcr_partition(config, sims_list, sensor_values):
    env = register_task(config, "do_pcr_partition", 0)
    logger = register_log(env, logging.INFO)

    # partition PCR grid
    machinecount = int(env["PCR_MACHINE_SPLITS"])

    script_dir = os.path.dirname(__file__)
    grid = PCR_Partition_Grid(script_dir + "/grid_config.json")
    data, data_w_points = grid.partition_grid_equally(machinecount)

    sensor_df = pd.DataFrame(sensor_values)

    machine_data_outputs = prepare_machine_data(
        sensor_df, sims_list, data_w_points, env["OUTPUT_DIR"]
    )

    close_task(env)
    return machine_data_outputs


async def tk_do_pcr(config, machine_data_output):
    u_id = machine_data_output["machine_id"]

    env = register_task(config, "do_pcr", u_id)
    logger = register_log(env, logging.INFO)

    train_chunk(machine_data_output, env["OUTPUT_DIR"])

    close_task(env)
    return env["OUTPUT_DIR"]


async def tk_do_pcr_pack(config, *pcr_output_dirs):
    env = register_task(config, "do_pcr_pack", 0)
    logger = register_log(env, logging.INFO)

    # results should be in env['OUTPUT_DIR']
    files_to_archive = []
    for pcr_output in pcr_output_dirs:
        files_to_archive += list(glob.glob(pcr_output + "/pcr_coefficients_*.csv"))
        files_to_archive += list(glob.glob(pcr_output + "/*.json"))

    cmd_tar = [
        "tar",
        "-czf",
        f"{env['OUTPUT_DIR']}/pcr.tar.gz",
        "--transform=s|.*/||",  # Strip directories, keep only filename
        "-T",
        "-",  # Read file list from stdin
    ]

    tarproc = subprocess.Popen(
        cmd_tar,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    tarproc.communicate(input="\n".join(files_to_archive))

    if tarproc.returncode != 0:
        logger.warning("Error executing tar!")
        raise ValueError(f"Error executing tar! Files: {files_to_archive}")

    close_task(env)
    return env["OUTPUT_DIR"] + "/pcr.tar.gz"
