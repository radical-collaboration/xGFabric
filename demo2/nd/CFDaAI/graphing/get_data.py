#!/bin/python3
import os, subprocess, re
import pandas as pd

paths = subprocess.run(
    [
        "find", "../logs/", "-name", "*.makeflowlog"
    ],
    capture_output=True,
    text=True,
).stdout.strip().split("\n")

for i in range(len(paths)):
    path = paths[i]
    path = path.split("/")[1:]
    save_path = f"outputs/runs/{path[1]}/{path[3]}"
    os.makedirs(save_path, exist_ok=True)

    log_path = "../" + "/".join(path[:-1])
    makeflow_path = log_path + "/cfdaai.makeflow"
    makeflow_log_path = log_path + "/cfdaai.makeflow.makeflowlog"
    wq_log_path = log_path + "/cfdaai.makeflow.wqlog"

    with open(makeflow_path, 'r') as file:
        lines = file.readlines()
        num_cores = lines[7].strip().split("=")[1]


    # For reference:
    # https://cctools.readthedocs.io/en/latest/makeflow/#transaction-log
    # https://github.com/cooperative-computing-lab/cctools/blob/master/makeflow/src/makeflow_log.c
    if not os.path.exists(f'{save_path}/makeflowlog.csv'):
        with open(makeflow_log_path, 'r') as log_file:
            lines = log_file.readlines()
            with open(f'{save_path}/makeflowlog.csv', 'w') as new_file:
                print(f"Writing {save_path}/makeflowlog.csv")
                new_file.write("timestamp,task_id,new_state,job_id,tasks_waiting,tasks_running,tasks_complete,tasks_failed,tasks_aborted,task_id_counter,num_cores\n")
                for line in lines:
                    if line.startswith("#") == False:
                        line = line.strip().split(" ")
                        line = ",".join(line)
                        line += f",{num_cores}\n"
                        new_file.write(line)

        df = pd.read_csv(f'{save_path}/makeflowlog.csv')
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="us")
        df["normalized_datetime"] = (df["timestamp"] - df["timestamp"].iloc[0]) / 1000000
        df.to_csv(f'{save_path}/makeflowlog.csv', index=False)


    # For reference:
    # https://cctools.readthedocs.io/en/stable/work_queue/#transactions-log
    # create the work queue csv file
    if not os.path.exists(f'{save_path}/wq_log.csv'):
        with open(wq_log_path, 'r') as log_file:
            lines = log_file.readlines()
            print(f"Writing {save_path}/wq_log.csv")
            with open(f'{save_path}/wq_log.csv', 'w') as new_file:
                header = lines[0][2:]
                header = header.strip().split(" ")
                header = ",".join(header)
                new_file.write(f"{header}\n")
                del lines[0]

                for line in lines:
                    line = line.strip().split(" ")
                    line = ",".join(line)
                    new_file.write(f"{line}\n")

        df = pd.read_csv(f'{save_path}/wq_log.csv')
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="us")
        df["normalized_datetime"] = (df["timestamp"] - df["timestamp"].iloc[0]) / 1000000
        df["num_cores"] = num_cores
        df.to_csv(f'{save_path}/wq_log.csv', index=False)


    sim_folder = f"{log_path}/simulations"
    if not os.path.exists(f'{save_path}/of_sims.csv'):
        with open(f'{save_path}/of_sims.csv', 'w') as new_file:
            print(f"Writing {save_path}/of_sims.csv")
            new_file.write("sim_number,execution_time,num_cores\n")
            for i in range(72):
                sim_path = f"{sim_folder}/of_sim_{i}.log"
                try:
                    with open(sim_path, "r") as file:
                        lines = file.readlines()
                        time = lines[-7].strip()
                        match = re.search(r"\((\d+)s\)", time)
                        if match:
                            seconds = int(match.group(1))
                            new_file.write(f"of_sim_{i}.log,{seconds},{num_cores}\n")
                except FileNotFoundError:
                    break
