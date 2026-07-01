import asyncio
import glob
import subprocess
import time
import random
import logging
import os
import math

logger = logging.getLogger(__name__)


async def tk_do_simulation_tmp(config, sensor_point, sim_id):
    logger.info(f"Task do_sim fired: {time.time()}.")

    # create directory for sims
    task_dir = config["PIPELINE_DIR"] + "/simulations" + f"/{sim_id}"
    os.makedirs(task_dir)
    os.makedirs(task_dir + "/results")
    os.makedirs(task_dir + "/logs")
    os.makedirs(task_dir + "/interim")

    env = os.environ.copy()
    env.update(config)

    env["OUTPUT_DIR"] = task_dir + "/results"
    env["LOG_DIR"] = task_dir + "/logs"
    env["INTERIM_DIR"] = task_dir + "/interim"

    skip_dir = "/pscratch/sd/b/bcarter/xgfabric-ryan/results/run_26-06-22_15_22_44/workflow_1/simulations"

    return sim_id, 0.0, skip_dir + f"/sim_{sim_id}.csv"


async def tk_do_simulation(config, sensor_point, sim_id):
    # config: dict
    # sensor_point: has wind_speed and wind_dir

    # return await tk_do_simulation_tmp(config, sensor_point, sim_id)

    logger.info(f"Task do_sim fired: {time.time()}.")

    # create directory for sims
    task_dir = config["PIPELINE_DIR"] + "/simulations" + f"/{sim_id}"
    os.makedirs(task_dir)
    os.makedirs(task_dir + "/results")
    os.makedirs(task_dir + "/logs")
    os.makedirs(task_dir + "/interim")

    env = os.environ.copy()
    env.update(config)

    env["OUTPUT_DIR"] = task_dir + "/results"
    env["LOG_DIR"] = task_dir + "/logs"
    env["INTERIM_DIR"] = task_dir + "/interim"

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

    with open(task_dir + "/stdout.txt", "w") as f:
        f.write(stdout)
    with open(task_dir + "/stderr.txt", "w") as f:
        f.write(stderr)

    # search for sims in OUTPUT_DIR

    return sim_id, wind_speed, env["OUTPUT_DIR"] + f"/sim_{sim_id}.csv"
