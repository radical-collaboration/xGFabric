import glob
import subprocess
import logging

import cloudpickle
import numpy as np

from utils_architecture import register_task, close_task
from ..common.log_formatter import register_log
from .MPWB2_CFD import PINN_Config, pinn_main_entry
from .inference import (
    pinn_predict_field,
    prepare,
    x_min,
    x_max,
    y_min,
    y_max,
    z_min,
    z_max,
)


def tk_do_pinn(config, sims_list):
    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        "",
        config["TASK_COUNTER"],
    )

    # Short
    # close_task(env)
    # return env["OUTPUT_DIR"] + "/pinn.tar.gz"

    logger = register_log(env, logging.INFO)

    logging.getLogger("matplotlib.font_manager").setLevel(logging.INFO)
    logging.getLogger("matplotlib.colorbar").setLevel(logging.INFO)

    # Require conda cfdaai

    pinn_config = PINN_Config()

    # quick train:
    # pinn_config.max_points_per_file = 600
    # pinn_config.epochs = 1

    pinn_main_entry(sims_list, env["OUTPUT_DIR"], pinn_config, logger)

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


def tk_pinn_eval(config, path_to_pinn_tar, wind):
    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        "INFERENCE",
        "",
        exist_ok=True,
    )
    logger = register_log(env, logging.INFO)

    cmd_tar = ["tar", "-xf", path_to_pinn_tar, "-C", env["INTERIM_DIR"]]

    tarproc = subprocess.Popen(
        cmd_tar,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if tarproc.returncode != 0:
        logger.warning(f"Error executing tar!")
        raise ValueError(f"Error executing tar! {' '.join(cmd_tar)}")

    # Now, files are in env['INTERIM_DIR']
    model, metadata = prepare(
        env["INTERIM_DIR"] + "/model.weights.h5",
        env["INTERIM_DIR"] + "/model_meta.json",
        logger,
    )

    # wind = (np.random.rand(1) * metadata["WS_MAX"])[0]

    x = np.linspace(x_min, x_max, 85)  # PCR counts
    y = np.linspace(y_min, y_max, 38)  # PCR counts
    pts_interested = np.meshgrid(x, y)
    out = []
    out.append(pinn_predict_field(model, metadata, pts_interested, wind, z=1.0))
    out.append(pinn_predict_field(model, metadata, pts_interested, wind, z=3.0))
    out.append(pinn_predict_field(model, metadata, pts_interested, wind, z=5.0))

    close_task(env, clean=True)
    return out
