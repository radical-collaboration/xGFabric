import os
import logging
from radical.asyncflow.logging import init_default_logger
import datetime


def register_task(env, task_name: str, task_number: int | str = 0):
    task_dir = env["PIPELINE_DIR"] + f"/{task_name}/{task_number}"
    os.makedirs(task_dir)
    os.makedirs(task_dir + "/results")
    os.makedirs(task_dir + "/logs")
    os.makedirs(task_dir + "/interim")

    env["OUTPUT_DIR"] = task_dir + "/results"
    env["LOG_DIR"] = task_dir + "/logs"
    env["INTERIM_DIR"] = task_dir + "/interim"
    env["TASK_NAME"] = task_name

    env_main = os.environ.copy()
    env_main.update(env)
    env_main["PREVIOUS_CWD"] = os.getcwd()
    os.chdir(env["INTERIM_DIR"])

    return env_main


def register_log_main(file_path_rose, file_path_libs, log_level=logging.INFO):
    # workaround for preventing double logging:
    logger_root = init_default_logger(
        log_level,
        output_file=file_path_libs,
        clear_handlers=True,
    )

    log_tmp = logging.getLogger("rose_app")
    log_tmp.propagate = False
    logger = init_default_logger(
        log_level,
        output_file=file_path_rose,
        logger_name="rose_app",
        clear_handlers=True,
    )
    return logger


def register_log(env, log_level=logging.INFO):
    # workaround for preventing double logging:
    log_tmp = logging.getLogger(env["TASK_NAME"])
    log_tmp.propagate = False
    logger = init_default_logger(
        log_level,
        output_file=env["LOG_DIR"] + f"/task_log.txt",
        logger_name=env["TASK_NAME"],
        clear_handlers=True,
    )
    return logger


def close_task(env):
    logger = logging.getLogger(env["TASK_NAME"])
    logger.info(f"Task {env["TASK_NAME"]} finished!")
    os.chdir(env["PREVIOUS_CWD"])
