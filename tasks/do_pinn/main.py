import asyncio
import datetime
import glob
import os
import subprocess
import time
import logging
import random
from ..common.log_formatter import register_task, register_log, close_task
from .MPWB2_CFD import PINN_Config, pinn_main_entry

logger = logging.getLogger(__name__)


async def tk_do_pinn(config, sims_list):
    env = register_task(config, "do_pinn", 0)
    logger = register_log(env, logging.INFO)

    # Require conda cfdaai

    pinn_config = PINN_Config()

    # quick train:
    pinn_config.max_points_per_file = 600
    pinn_config.epochs = 1

    pinn_main_entry(sims_list, env["OUTPUT_DIR"], pinn_config)

    # results should be in env['OUTPUT_DIR']
    files_to_archive = list(glob.glob(env["OUTPUT_DIR"] + "/*.weights.h5"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.normalization.json"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.model_meta.json"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.run.json"))

    # keep everything after OUTPUT_DIR
    for i in range(len(files_to_archive)):
        files_to_archive[i] = files_to_archive[i][len(env["OUTPUT_DIR"]) + 1 :]

    # launch tar.
    cmd_tar = [
        "tar",
        "-czf",
        env["OUTPUT_DIR"] + "/pinn.tar.gz",
        "-C",
        env["OUTPUT_DIR"],
    ] + files_to_archive
    logger.info(f"Running tar: {' '.join(cmd_tar)}")

    tarproc = subprocess.Popen(
        cmd_tar,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tarproc.communicate()

    if tarproc.returncode != 0:
        logger.warning(f"Error executing tar!")
        raise ValueError(f"Error executing tar! Files: {files_to_archive}")

    close_task(env)
    return env["OUTPUT_DIR"] + "/pinn.tar.gz"
