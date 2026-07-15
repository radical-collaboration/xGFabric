import asyncio
import datetime
import glob
import os
import subprocess
import time
import logging
import random
from ..common.log_formatter import register_task, register_log, close_task
from .train_fno import fno_main_entry, FNO_Config


def main():
    sims_list = [
        (
            0.0,
            "/pscratch/sd/b/bcarter/xgfabric-ryan/results/run_26-06-22_15_22_44/workflow_1/simulations/sim_0.csv",
        )
    ]
    out_dir = (
        "/pscratch/sd/b/bcarter/playground/run_07-02-2026_12_50_05/1/do_fno/0/results"
    )
    fno_config = FNO_Config()
    fno_main_entry(sims_list, out_dir, fno_config)


def tk_do_fno(config, sims_list):
    env = register_task(config, "do_fno", 0)
    logger = register_log(env, logging.INFO)

    logging.getLogger("matplotlib.font_manager").setLevel(logging.INFO)
    logging.getLogger("matplotlib.colorbar").setLevel(logging.INFO)

    # Require conda cfdaai

    # Start conda and then call main()

    fno_config = FNO_Config()

    # quick train:
    fno_config.epochs = 1

    fno_main_entry(sims_list, env["OUTPUT_DIR"], fno_config, logger)

    # results should be in env['OUTPUT_DIR']
    files_to_archive = list(glob.glob(env["OUTPUT_DIR"] + "/*.weights.h5"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.json"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.json"))
    files_to_archive += list(glob.glob(env["OUTPUT_DIR"] + "/*.csv"))

    # keep everything after OUTPUT_DIR
    for i in range(len(files_to_archive)):
        files_to_archive[i] = files_to_archive[i][len(env["OUTPUT_DIR"]) + 1 :]

    # launch tar.
    cmd_tar = [
        "tar",
        "-czf",
        env["OUTPUT_DIR"] + "/fno.tar.gz",
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
    return env["TK_DO_FNO"], env["OUTPUT_DIR"] + "/fno.tar.gz"
