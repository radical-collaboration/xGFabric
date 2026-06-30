import asyncio
import glob
import os
import subprocess
import time
import logging
import random

from .MPWB2_CFD import PINN_Config, pinn_main_entry

logger = logging.getLogger(__name__)


async def tk_do_pinn(config, sims_list):
    unique_id = random.randint(0, 40000)
    logger.info(
        f"Task do_pinn fired: {time.time()}. Unique ID: {unique_id}. Called by: {config['PARENT_UNIQUE_ID']}"
    )

    # Require conda cfdaai

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

    # Start conda and then call main()

    pinn_config = PINN_Config()

    # quick train:
    pinn_config.max_points_per_file = 600
    pinn_config.epochs = 1

    cwd = os.getcwd()
    os.chdir(env["INTERIM_DIR"])
    pinn_main_entry(sims_list, env["OUTPUT_DIR"], pinn_config)
    os.chdir(cwd)

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

    return unique_id, env["OUTPUT_DIR"] + "/pinn.tar.gz"
