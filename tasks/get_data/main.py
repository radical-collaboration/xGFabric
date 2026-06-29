# Fetch data from cspot

import asyncio
import glob
import subprocess
import os
import logging
import time
import random
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Get_Data_Input:
    LOGS_DIR: str
    COMMON_DIR: str
    WORK_DIR: str
    RESULTS_DIR: str
    PIPELINE_INTERIM_TASK_DIR: str
    PARENT_UNIQUE_ID: str


async def tk_get_data(config):
    my_unique_id = random.randint(0, 40000)

    logger.info(
        f"Task get_data fired: {time.time()}. Unique ID: {my_unique_id}. Called by: {config['PARENT_UNIQUE_ID']}"
    )

    # create directory for interim results
    config["LOGS_DIR"] = config["PIPELINE_INTERIM_TASK_DIR"] + "/get_data"
    os.makedirs(config["LOGS_DIR"])

    # create directory for main results
    config["RESULTS_DIR"] = config["LOGS_DIR"]

    # Model get_data.sh
    # - needs: csv_logger.py
    # - needs: config.sh
    # - needs: env/system_config.sh
    # - needs: lib/common.sh
    # - needs: lib/simulations.sh
    # - needs: data/data_source.sh

    # config contains env's for the run.

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config["WORK_DIR"] = f"{script_dir}/../../xgfabric"  # script_dir

    env = os.environ.copy()
    env.update(config)

    with open("test_config.sh", "w") as f:
        for c in config:
            f.write(f"export {c}={config[c]}\n")

    script = subprocess.Popen(
        [f"{config['WORK_DIR']}/utils/get_data.sh"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = script.communicate()

    if script.returncode != 0:
        logger.warning(f"get_data returned non-zero status: {stderr}")

    stdout_file = config["LOGS_DIR"] + f"/output.txt"
    stderr_file = config["LOGS_DIR"] + f"/err.txt"

    # Return data points.
    with open(stdout_file, "w") as f:
        f.write(stdout)
    with open(stderr_file, "w") as f:
        f.write(stderr)

    # return array of filenames of parameters
    return list(glob.glob(f"{config['RESULTS_DIR']}/params/sim_*.json"))
