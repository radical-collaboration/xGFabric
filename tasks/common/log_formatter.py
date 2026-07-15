import os
import logging
import socket
from radical.asyncflow.logging import init_default_logger
import datetime
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(__file__)

load_dotenv(SCRIPT_DIR + "/config.sh")


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
    env["TASK_ID"] = str(task_number)

    env_main = os.environ.copy()
    env_main.update(env)
    env_main["PREVIOUS_CWD"] = os.getcwd()
    os.chdir(env["INTERIM_DIR"])

    return env_main


def register_log_main(file_path_rose, file_path_libs, log_level=logging.INFO):
    # workaround for preventing double logging:
    root_logger = logging.getLogger()
    root_logger.setLevel(
        logging.DEBUG
    )  # debug as the most verbose as root. Other loggers can filter upon it.

    logger_root = init_default_logger(
        log_level,
        output_file=file_path_libs,
        clear_handlers=True,
        file_log_level=log_level,
    )

    log_tmp = logging.getLogger("rose_app")
    log_tmp.propagate = False
    logger = init_default_logger(
        log_level,
        output_file=file_path_rose,
        logger_name="rose_app",
        clear_handlers=True,
        file_log_level=log_level,
    )
    return logger


def register_log(env, log_level=logging.INFO):
    # workaround for preventing double logging:
    # only for concurrent backend
    # log_tmp = logging.getLogger(env["TASK_NAME"])
    # log_tmp.propagate = False

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    logger = init_default_logger(
        log_level,
        output_file=env["LOG_DIR"] + f"/task_log.txt",
        logger_name=env["TASK_NAME"] + "_" + env["TASK_ID"],
        clear_handlers=True,
        file_log_level=log_level,
    )
    logger.info(f"Task {env["TASK_NAME"]} started on {socket.gethostname()}!")
    return logger


def close_task(env):
    logger = logging.getLogger(env["TASK_NAME"] + "_" + env["TASK_ID"])
    logger.info(f"Task {env["TASK_NAME"]} finished!")
    os.chdir(env["PREVIOUS_CWD"])
    task_name = env["TASK_NAME"]
    task_number = env["TASK_ID"]
    pipeline_number = env["PIPELINE_ID"]
    # print(f"\n\nRETURN_VALUE: {pipeline_number},{task_name},{task_number},{retval}")
