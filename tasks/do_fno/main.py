import glob
import subprocess
import logging

from utils_architecture import register_task, close_task
from ..common.log_formatter import register_log
from .train_fno import fno_main_entry, FNO_Config


def tk_do_fno(config, sims_list):

    env = register_task(
        config,
        config["AGENT_NAME"],
        config["INVESTIGATOR_NAME"],
        "",
        config["TASK_COUNTER"],
    )
    logger = register_log(env, logging.INFO)

    logging.getLogger("matplotlib.font_manager").setLevel(logging.INFO)
    logging.getLogger("matplotlib.colorbar").setLevel(logging.INFO)

    # Short
    close_task(env)
    return env["OUTPUT_DIR"] + "/fno.tar.gz"

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
    return env["OUTPUT_DIR"] + "/fno.tar.gz"
