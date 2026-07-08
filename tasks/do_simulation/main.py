import asyncio
import glob
import subprocess
import time
import random
import logging
import os
import math
from ..common.log_formatter import register_task, register_log, close_task
import datetime


async def tk_do_simulation_tmp(config, sensor_point, sim_id):
    env = register_task(config, "do_simulation", sim_id)
    logger = register_log(env, logging.INFO)

    skip_dir = "/pscratch/sd/b/bcarter/xgfabric-ryan/results/run_26-06-22_15_22_44/workflow_1/simulations"

    close_task(env)
    return sim_id, 0.0, skip_dir + f"/sim_{sim_id}.csv"


async def tk_do_simulation(config, sensor_point, sim_id):
    # config: dict
    # sensor_point: has wind_speed and wind_dir

    # return await tk_do_simulation_tmp(config, sensor_point, sim_id)

    # create directory for sims
    env = register_task(config, "do_simulation", sim_id)
    logger = register_log(env, logging.INFO)

    # sim_id

    wind_speed = float(sensor_point["wind_speed"])
    wind_direction = float(sensor_point["wind_dir"])

    # vectorize
    x = wind_speed * math.cos(wind_direction)
    y = wind_speed * math.sin(wind_direction)

    # with open("test_config.sh", "w") as f:
    #     for e in env:
    #         f.write(f"export {e}={env[e]}\n")

    script_dir = os.path.dirname(__file__)
    cmd = [
        "bash",
        f"{script_dir}/runme.sh",
        os.getenv("CUPS_STRUCTURE_ZIP"),
        os.getenv("SIM_THREADS", "32"),
        str(x),
        str(y),
        "0.0",
        env["OUTPUT_DIR"],
        "1 4 1",
        str(sim_id),
        str(wind_direction),
        str(wind_speed),
    ]

    print(" ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        cwd=script_dir,
    )

    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        logger.warning(f"simulation script returned non-zero code: {stderr}")

    task_dir = env["INTERIM_DIR"]
    with open(task_dir + "/stdout.txt", "w") as f:
        f.write(stdout)
    with open(task_dir + "/stderr.txt", "w") as f:
        f.write(stderr)

    # search for sims in OUTPUT_DIR
    close_task(env)
    return sim_id, wind_speed, env["OUTPUT_DIR"] + f"/sim_{sim_id}.csv"
