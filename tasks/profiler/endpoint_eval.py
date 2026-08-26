import json
import sys

import pandas as pd
from xgboost import XGBRegressor
import numpy as np


def safe_log(r):
    mask = r > 0
    result = np.zeros_like(r, dtype=np.float64)
    result[mask] = np.log2(r[mask])
    return result


PI_CPUS = 4

if __name__ == "__main__":
    model = XGBRegressor()
    model.load_model(sys.argv[1])

    with open(sys.argv[2], "r") as f:
        data = pd.DataFrame([json.load(f)])

    # add calculated columns
    data["avg_cpu"] = data["cpu_seconds"] / data["total_seconds"]
    data["avg_log_mem"] = safe_log(data["memory_bytes"]) / data["total_seconds"]
    data["avg_log_sys_write_bytes"] = (
        safe_log(data["sys_write_bytes"]) / data["total_seconds"]
    )
    data["avg_log_sys_read_bytes"] = (
        safe_log(data["sys_read_bytes"]) / data["total_seconds"]
    )

    data["under_core_ct"] = data["avg_cpu"]
    data.loc[data["avg_cpu"] > PI_CPUS, "under_core_ct"] = PI_CPUS
    data["over_core_ct"] = data["avg_cpu"] * 0
    data.loc[data["avg_cpu"] > PI_CPUS, "over_core_ct"] = data["avg_cpu"] - PI_CPUS

    # drop unneeded columns
    data = data.drop(
        [
            "cpu_seconds",
            "disk_read_bytes",
            "disk_write_bytes",
            "sys_read_bytes",
            "sys_write_bytes",
            "memory_bytes",
            "avg_cpu",
        ],
        axis=1,
    )

    # predict
    predicted_pi_nersc_sec = model.predict(data.drop(["total_seconds"], axis=1))

    print((data["total_seconds"] * predicted_pi_nersc_sec)[0])
