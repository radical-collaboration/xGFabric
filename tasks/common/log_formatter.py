import os
import logging
import socket
from radical.asyncflow.logging import init_default_logger
import datetime
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(__file__)

load_dotenv(SCRIPT_DIR + "/config.sh")


def register_log_main(config, log_level=logging.INFO):
    file_path_libs = config["PLAYGROUND_DIR"] + "/libs.log"
    file_path_rose = config["PLAYGROUND_DIR"] + "/rose.log"

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
    log_tmp = logging.getLogger(env["FULL_TASK_NAME"])
    log_tmp.propagate = False

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    logger = init_default_logger(
        log_level,
        output_file=env["LOG_DIR"] + f"/task_log.txt",
        logger_name=env["FULL_TASK_NAME"],
        clear_handlers=True,
        file_log_level=log_level,
    )
    logger.info(f"Task {env['FULL_TASK_NAME']} started on {socket.gethostname()}!")
    return logger
