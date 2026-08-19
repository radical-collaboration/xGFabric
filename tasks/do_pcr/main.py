import asyncio
import glob
import os
import subprocess
import time
import logging
import random
import datetime

import cloudpickle
import numpy as np
import pandas as pd

from utils_architecture import register_task, close_task
from ..common.log_formatter import register_log

# step 1
from .partition_pcr_grid import PCR_Partition_Grid

# step 2
from .prepare_pcr_data import prepare_machine_data

# step 3
from .train_pcr_chunk import train_chunk

# inference
from .inference import predict_at_z, prepare


def tk_pcr_partition(config, sims_list, sensor_values):
    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        config["TASK_NAME"],
        config["TASK_COUNTER"],
    )
    logger = register_log(env, logging.INFO)

    # close_task(env)
    # return [1, 2, 3]

    # partition PCR grid
    machinecount = int(env["PCR_MACHINE_SPLITS"])

    script_dir = os.path.dirname(__file__)
    grid = PCR_Partition_Grid(script_dir + "/grid_config.json")
    data, data_w_points = grid.partition_grid_equally(machinecount)

    sensor_df = pd.DataFrame(sensor_values)

    machine_data_outputs = prepare_machine_data(
        sensor_df, sims_list, data_w_points, env["OUTPUT_DIR"], logger
    )

    close_task(env)
    # with open(
    #     "/global/homes/b/bcarter/pppl/repos/xGFabric-radical/debug.pkl", "wb"
    # ) as f:
    #     cloudpickle.dump((config, machine_data_outputs), f)
    return machine_data_outputs


def tk_do_pcr(config, machine_data_output):
    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        config["TASK_NAME"],
        config["TASK_COUNTER"],
    )
    logger = register_log(env, logging.INFO)

    # close_task(env)
    # return env["OUTPUT_DIR"]

    u_id = machine_data_output["machine_id"]

    train_chunk(machine_data_output, env["OUTPUT_DIR"], logger)

    close_task(env)
    return env["OUTPUT_DIR"]


def tk_do_pcr_pack(config, *pcr_output_dirs):
    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        config["TASK_NAME"],
        config["TASK_COUNTER"],
    )
    logger = register_log(env, logging.INFO)

    # close_task(env)
    # return env["OUTPUT_DIR"] + "/pcr.tar.gz"

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


def tk_pcr_eval(config, path_to_pcr_tar, wind):
    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        "INFERENCE",
        "",
        exist_ok=True,
    )
    logger = register_log(env, logging.INFO)

    cmd_tar = ["tar", "-xf", path_to_pcr_tar, "-C", env["INTERIM_DIR"]]

    tarproc = subprocess.Popen(
        cmd_tar,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tarproc.communicate()

    if tarproc.returncode != 0:
        logger.warning(f"Error executing tar!")
        raise ValueError(f"Error executing tar! {' '.join(cmd_tar)}")

    df = prepare(env["INTERIM_DIR"] + "/pcr_coefficients", logger)

    out = []
    out.append(predict_at_z(df, wind, 1))
    out.append(predict_at_z(df, wind, 3))
    out.append(predict_at_z(df, wind, 5))
    close_task(env, clean=True)
    return out
