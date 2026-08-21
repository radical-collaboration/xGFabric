import logging
import os
import datetime
import shutil


def verify_config():
    if os.environ.get("INTERIM_DIR") is not None:
        os.makedirs(os.environ.get("INTERIM_DIR"), exist_ok=True)
    else:
        os.environ["INTERIM_DIR"] = "."

    # if len(tf.config.list_physical_devices("GPU")) == 0:
    #     print(tf.config.list_physical_devices("GPU"))
    #     raise ValueError("Missing GPUs")


def get_fdate():
    now = datetime.datetime.now()
    return datetime.datetime.strftime(now, "%m-%d-%Y_%H_%M_%S")


# Folder structure:


def register_master_run() -> dict:
    config = os.environ.copy()
    dt_str = get_fdate()
    complete = config.get("PLAYGROUND_DIR", ".") + f"/run_{dt_str}"
    os.makedirs(complete)
    config["PLAYGROUND_DIR"] = complete

    workflow_file = config["PLAYGROUND_DIR"] + "/workflow.sh"
    with open(workflow_file, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("# Recorded exec calls: \n\n")

    return config


def register_task(
    env,
    agent_name: str,
    investigator_name: str,
    task_name: str,
    task_number: int | str = 0,
    exist_ok: bool = False,
):
    fpath = "/"
    if agent_name != "":
        fpath += agent_name + "/"

    if investigator_name != "":
        fpath += investigator_name + "/"

    if task_name != "":
        fpath += task_name + "/"

    if task_number != "":
        fpath += str(task_number) + "/"

    fpath = fpath[:-1]
    env["FULL_TASK_NAME"] = fpath

    task_dir = env["PLAYGROUND_DIR"] + fpath
    os.makedirs(task_dir, exist_ok=exist_ok)
    os.makedirs(task_dir + "/results", exist_ok=exist_ok)
    os.makedirs(task_dir + "/logs", exist_ok=exist_ok)
    os.makedirs(task_dir + "/interim", exist_ok=exist_ok)

    env["OUTPUT_DIR"] = task_dir + "/results"
    env["LOG_DIR"] = task_dir + "/logs"
    env["INTERIM_DIR"] = task_dir + "/interim"
    env["TASK_NAME"] = task_name
    env["TASK_ID"] = str(task_number)

    env_main = os.environ.copy()
    env_main.update(env)
    env_main["PREVIOUS_CWD"] = os.getcwd()
    os.chdir(env["INTERIM_DIR"])
    return env_main


def close_task(env, clean=False):
    logger = logging.getLogger(env["FULL_TASK_NAME"])
    logger.info(f"Task {env['FULL_TASK_NAME']} finished!")
    os.chdir(env["PREVIOUS_CWD"])

    # clean up interim!
    if clean:
        shutil.rmtree(env["INTERIM_DIR"])
