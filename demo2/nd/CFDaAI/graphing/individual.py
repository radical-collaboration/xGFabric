#!/bin/python3
import subprocess, os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

paths = []
with open('paths.txt', 'r') as file:
    for line in file.readlines():
        paths.append(line.strip())


for i in range(len(paths)):
    path = paths[i]
    path = path.split("/")[1:]
    save_path = f"outputs/{path[1]}/{path[3]}"
    os.makedirs(save_path, exist_ok=True)
    # subprocess.run(
    #     ["makeflow_graph_log", f"..{paths[i][1:]}", f"{save_path}/graph.png"],
    #     # capture_output=True,
    #     # text=True
    # )

    log_path = "../" + "/".join(path[:-1])
    makeflow_path = log_path + "/cfdaai.makeflow"
    makeflow_log_path = log_path + "/cfdaai.makeflow.makeflowlog"

    with open(makeflow_path, 'r') as file:
        lines = file.readlines()
        num_cores = lines[7].strip().split("=")[1]

    # For reference:
    # https://cctools.readthedocs.io/en/latest/makeflow/#transaction-log
    # https://github.com/cooperative-computing-lab/cctools/blob/master/makeflow/src/makeflow_graph_log
    # https://github.com/cooperative-computing-lab/cctools/blob/master/makeflow/src/makeflow_log.c
    with open(makeflow_log_path, 'r') as log_file:
        lines = log_file.readlines()
        with open(f'{save_path}/makeflowlog.csv', 'w') as new_file:
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
    df.to_csv(f'{save_path}/data.csv', index=False)

    # fig, ax = plt.subplots()
    # ax.plot(df["datetime"], df["tasks_running"], label="Running")
    # ax.plot(df["datetime"], df["tasks_complete"], label="Complete")

    # ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    # # ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))
    # fig.autofmt_xdate()  # rotates labels nicely

    # plt.grid()

    # ax.set_xlabel("Time")
    # ax.set_ylabel("Jobs Submitted / Complete")
    # ax.set_title(f"Run {str(df.datetime.iloc[0]).split(' ')[0]} with {num_cores} cores")

    # plt.legend()

    # plt.savefig(f'{save_path}/graph2.png', dpi=300, bbox_inches='tight')
    # plt.show()
    # plt.close()