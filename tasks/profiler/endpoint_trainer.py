import json
import sys

import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor


def safe_log(r):
    mask = r > 0
    result = np.zeros_like(r, dtype=np.float64)
    result[mask] = np.log2(r[mask])
    return result


PI_CPUS = 4


def sim():
    # a CSV with all entries.
    data = pd.read_csv(sys.argv[1])
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

    data["pi_nersc_sec"] = data["pi_seconds"] / data["total_seconds"]
    return data


def train(data):
    X = data.drop(
        [
            "cpu_seconds",
            "disk_read_bytes",
            "disk_write_bytes",
            "sys_read_bytes",
            "sys_write_bytes",
            "memory_bytes",
            "avg_cpu",
            "pi_seconds",
            "pi_nersc_sec",
        ],
        axis=1,
    )
    y = data[["pi_nersc_sec", "pi_seconds"]]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=101
    )

    # put t_sec in a different column
    X_train = X_train.drop(["total_seconds"], axis=1)
    t_sec_test = X_test["total_seconds"]
    X_test = X_test.drop(["total_seconds"], axis=1)

    # put pi_sec in a different column
    y_train = y_train.drop(["pi_seconds"], axis=1)
    final_test = y_test["pi_seconds"]
    y_test = y_test.drop(["pi_seconds"], axis=1)

    model = XGBRegressor(
        objective="reg:absoluteerror",
        n_estimators=300,
        max_depth=8,
        learning_rate=0.1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    y_pred_final = t_sec_test * y_pred

    model.save_model(sys.argv[2])

    return json.dumps(
        {
            "model": sys.argv[2],
            "mae": mean_absolute_error(final_test, y_pred_final),
        }
    )


if __name__ == "__main__":
    # print(f"Training xgboost regression for {sys.argv[1]}")
    out = train(sim())
    print(out)
