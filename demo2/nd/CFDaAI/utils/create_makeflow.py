#!/bin/python3
import os, subprocess

def print_phase(file, message: str) -> None:
    file.write("# ============================================================\n")
    file.write(f"# {message}\n")
    file.write("# ============================================================\n")


def print_prologue(file, workflow_location: str, global_vars: dict, config: dict) -> None:
    file.write("# --- Configuration ---\n")
    file.write("WORK_DIR=.\n")
    file.write(f"WORKFLOW_NUMBER={global_vars['workflow_counter']}\n")
    file.write(f"WORKFLOW_LOCATION={workflow_location}\n")
    file.write(f"RESULTS_DIR=results/run_{global_vars['start_time']}/workflow_{global_vars['workflow_counter']}\n")
    file.write(f"START_TIME={global_vars['start_time']}\n")
    file.write(f"LOGS_DIR={global_vars['log_location']}\n")
    file.write(f"SIMULATION_THREADS={config['number_of_cores']}\n")
    file.write(f"NUM_SIMULATIONS={config['number_of_simulations']}\n")
    file.write("export WORK_DIR\n")
    file.write("export WORKFLOW_NUMBER\n")
    file.write("export WORKFLOW_LOCATION\n")
    file.write("export RESULTS_DIR\n")
    file.write("export LOGS_DIR\n")
    file.write("export SIMULATION_THREADS\n")
    file.write("export NUM_SIMULATIONS\n")
    file.write("\n")


def print_data_acq(file, system: tuple, config: dict) -> None:
    if config['workqueue_mode']:
        file.write("CATEGORY=\"data_acquisition\"\n")
        file.write("CORES=1\n")
        file.write("GPUS=0\n")
        file.write("$(WORKFLOW_LOCATION)/pipeline.0 $(RESULTS_DIR) $(RESULTS_DIR)/data $(RESULTS_DIR)/params/sim_params.csv")
        for i in range(config["number_of_simulations"]):
            file.write(f" $(RESULTS_DIR)/params/sim_{i}.json")
        file.write(":\n")
    else:
        file.write("$(WORKFLOW_LOCATION)/pipeline.0:\n")
    file.write("\tLOCAL ./utils/get_data.sh > $(WORKFLOW_LOCATION)/pipeline.0 2>&1\n")
    file.write("\n")


def print_simulations(file, system: tuple, config: dict) -> None:
    if config['workqueue_mode']:
        file.write("CATEGORY=\"simulations\"\n")
        file.write(f"CORES={config['number_of_cores']}\n")
        file.write("GPUS=0\n")
    for i in range(config["number_of_simulations"]):
        if config['workqueue_mode']:
            file.write(f"$(RESULTS_DIR)/simulations/sim_{i}.csv $(WORKFLOW_LOCATION)/simulations/of_sim_{i}.log: $(WORKFLOW_LOCATION)/pipeline.0 $(WORK_DIR)/{system[1]}/simulation_{system[1]}.sh $(RESULTS_DIR)/params/sim_{i}.json $(RESULTS_DIR)/data tasks env simulation lib\n")
            file.write(f"\tmkdir -p $(WORKFLOW_LOCATION)/simulations && mkdir -p $(RESULTS_DIR)/simulations && bash $(WORK_DIR)/{system[1]}/simulation_{system[1]}.sh $(RESULTS_DIR)/params $(RESULTS_DIR)/simulations {i} > $(WORKFLOW_LOCATION)/simulations/of_sim_{i}.log 2>&1\n")
        else:
            if system[0] == "nersc":
                file.write(f"BATCH_OPTIONS=--qos=regular --constraint=cpu --ntasks={config['number_of_cores']} --time=00:15:00 --job-name=cfd_sim_{i}\n")
            elif system[0] == "nd":
                file.write(f"BATCH_OPTIONS=-terse -pe smp {config['number_of_cores']} -q long -N cfd_sim_{i}\n")

            file.write(f"$(WORKFLOW_LOCATION)/simulations/of_sim.{i}: $(WORKFLOW_LOCATION)/pipeline.0\n")
            file.write(f"\tsh $(WORK_DIR)/{system[1]}/simulation_{system[1]}.sh $(RESULTS_DIR)/params $(RESULTS_DIR)/simulations {i} > $(WORKFLOW_LOCATION)/simulations/of_sim.{i} 2>&1\n")
        file.write("\n")


def print_training(file, system: tuple, models, config: dict) -> None:
    nersc_group = ""
    if system[0] == "nersc":
        nersc_group = subprocess.run(
            ["groups"],
            capture_output=True,
            text=True
        )

        nersc_group = str(nersc_group.stdout).strip().split(" ")[1]

    nersc_batch_options = {
        "pcr" : f"BATCH_OPTIONS=--job-name=pcr_train --qos=regular --constraint=cpu --ntasks={config['number_of_cores']} --time=00:05:00",
        "pinn": f"BATCH_OPTIONS=--job-name=pinn_train --constraint=gpu -G 1 -A {nersc_group} --ntasks={config['number_of_cores']} --qos=regular --time=00:10:00",
        "fno" : f"BATCH_OPTIONS=--job-name=fno_train --constraint=gpu -G 1 -A {nersc_group} --ntasks={config['number_of_cores']} --qos=regular --time=00:10:00",
    }

    nd_batch_options = {
        "pcr" : f"BATCH_OPTIONS=-terse -pe smp {config['number_of_cores']} -q long -N pcr_train",
        "pinn": f"BATCH_OPTIONS=-terse -pe smp {config['number_of_cores']} -q gpu -l gpu_card=1 -N pinn_train",
        "fno" : f"BATCH_OPTIONS=-terse -pe smp {config['number_of_cores']} -q gpu -l gpu_card=1 -N fno_train"
    }

    if config['workqueue_mode']:
        file.write("CATEGORY=\"training\"\n")
        file.write(f"CORES={config['number_of_cores']}\n")
        for model in models:
            file.write(f"$(RESULTS_DIR)/models/{model}/archives/{model}.tar.gz $(WORKFLOW_LOCATION)/training/{model}_train.log: {system[1]}/{model}_train_{system[1]}.sh training/cfd_common.py training/{model} env lib $(RESULTS_DIR)/data $(RESULTS_DIR)/params/sim_params.csv")
            for i in range(config["number_of_simulations"]):
                file.write(f" $(RESULTS_DIR)/simulations/sim_{i}.csv")
            file.write("\n")
            file.write(f"\tmkdir -p $(WORKFLOW_LOCATION)/training && bash {system[1]}/{model}_train_{system[1]}.sh $(RESULTS_DIR)/simulations $(RESULTS_DIR)/models/{model} > $(WORKFLOW_LOCATION)/training/{model}_train.log 2>&1\n")
            file.write("\n")
    else:
        for model in models:
            if system[0] == "nersc":
                file.write(f"{nersc_batch_options[model]}\n")
            elif system[0] == "nd":
                file.write(f"{nd_batch_options[model]}\n")

            file.write(f"$(WORKFLOW_LOCATION)/training/{model}_train.log:")
            for i in range(config["number_of_simulations"]):
                file.write(f" $(WORKFLOW_LOCATION)/simulations/of_sim.{i}")
            file.write("\n")
            file.write(f"\tbash {system[1]}/{model}_train_{system[1]}.sh $(RESULTS_DIR)/simulations $(RESULTS_DIR)/models/{model} > $(WORKFLOW_LOCATION)/training/{model}_train.log 2>&1\n")
            file.write("\n")


def detect_system() -> tuple:
    result = subprocess.run(
        ["hostname", "-f"],
        capture_output=True,
        text=True
    )
    hostname = str(result.stdout).strip()

    if "nersc.gov" in hostname:
        return ("nersc", "slurm")
    elif "nd.edu" in hostname:
        return ("nd", "uge")
    else:
        return ("ucsb", "slurm")


def create_makeflow(global_vars: dict, config: dict) -> None:
    workflow_location = f"{global_vars['log_location']}/workflows/{global_vars['workflow_counter']}"
    makeflow_file = f"{workflow_location}/cfdaai.makeflow"

    system = detect_system()

    models = []
    with open("config.sh", "r") as file:
        for line in file:
            if line.strip().startswith("TRAIN_MODELS"):
                models = line.split("=")[1].strip().strip('"').split(" ")

    with open(makeflow_file, "w") as file:
        print_prologue(file, workflow_location, global_vars, config)
        print_phase(file, "CFDaAI Pipeline - Makeflow")
        file.write("\n")

        # phase 1
        print_phase(file, "Phase 1: Data Acquisition")
        print_data_acq(file, system, config)
        file.write("\n")

        # phase 2
        if config["mode"] == "sim-only" or config["mode"] == "full":
            print_phase(file, "Phase 2: Simulations")
            print_simulations(file, system, config)
            file.write("\n\n")

        # phase 3
        if config["mode"] == "train-only" or config["mode"] == "full":
            print_phase(file, "Phase 3: Training")
            print_training(file, system, models, config)
            file.write("\n\n")
	
        # phase 4
        if config["mode"] == "full":
            print_phase(file, "Phase 4: Evaluation")
            if config['workqueue_mode']:
                file.write("CATEGORY=\"evaluation\"\n")
                file.write("CORES=1\n")
                file.write("GPUS=0\n")
            file.write("$(WORKFLOW_LOCATION)/pipeline.3: bin")
            for model in models:
                if config['workqueue_mode']:
                    file.write(f" $(RESULTS_DIR)/models/{model}/archives/{model}.tar.gz")
                else:
                    file.write(f" $(WORKFLOW_LOCATION)/training/{model}_train.log")
            file.write("\n")
            file.write("\tLOCAL ./utils/evaluation.sh > $(WORKFLOW_LOCATION)/pipeline.3 2>&1\n")
            file.write("\n")


if __name__ == "__main__":
    from datetime import datetime
    start_time = datetime.now().strftime("%y-%m-%d_%H_%M_%S")
    config = {
        "max_concurrent_workflows" : None,   # total number of workflows that can run concurrently
        "max_number_of_workflows"  : 1,   # total number of workflows that will be submitted
        "time_between_workflows"   : 5,      # minimum time (in seconds) between workflow submissions.
        "time_check_workflows"     : 1,      # how often the program should check if it can submit new workflows (in seconds)
        "number_of_cores"          : 16,     # how many cores the simulations should run on
        "number_of_simulations"    : 5,     # how many OpenFOAM simulations per workflow
        "workqueue_mode"           : True     # 
    }

    global_vars = {
        "workflow_counter"     : 1,
        "start_time"           : start_time,
        "log_location"         : f"logs/run_{start_time}",
        "workflow_status_file" : f"logs/run_{start_time}/coordinator/workflow_status_log.csv",
        "coordinator_output"   : f"logs/run_{start_time}/coordinator/coordinator_output.log",
    }

    workflow_location = f"{global_vars['log_location']}/workflows/{global_vars['workflow_counter']}"

    os.makedirs(f"{workflow_location}", exist_ok=True)
    os.makedirs(f"{workflow_location}/simulations", exist_ok=True)
    os.makedirs(f"{workflow_location}/training", exist_ok=True)

    create_makeflow(global_vars, config)
