#!/bin/python3
import sys, os

def print_phase(file, message: str) -> None:
    file.write("# ============================================================\n")
    file.write(f"# {message}\n")
    file.write("# ============================================================\n")

def create_makeflow(global_vars: dict, config: dict) -> None:
    workflow_location = f"{global_vars["log_location"]}/workflows/{global_vars["workflow_counter"]}"
    makeflow_file = f"{workflow_location}/cfdaai.makeflow"
    sim_options  = f"BATCH_OPTIONS=-terse -pe smp {config["number_of_cores"]} -q long"
    pcr_options  = f"BATCH_OPTIONS=-terse -pe smp {config["number_of_cores"]} -q long -N pcr_train"
    pinn_options = f"BATCH_OPTIONS=-terse -pe smp {config["number_of_cores"]} -q gpu -l gpu_card=1 -N pinn_train"
    fno_options  = f"BATCH_OPTIONS=-terse -pe smp {config["number_of_cores"]} -q gpu -l gpu_card=1 -N fno_train"

    with open("config.sh", "r") as file:
        for line in file:
            if line.strip().startswith("TRAIN_MODELS"):
                models = line.split("=")[1].strip().strip('"').split(" ")

    with open(makeflow_file, "w") as file:
        file.write("# --- Configuration ---\n")
        file.write("WORK_DIR=.\n")
        file.write(f"WORKFLOW_NUMBER={global_vars["workflow_counter"]}\n")
        file.write(f"WORKFLOW_LOCATION={workflow_location}\n")
        file.write(f"RESULTS_DIR=results/run_{global_vars["start_time"]}/workflow_{global_vars["workflow_counter"]}\n")
        file.write(f"START_TIME={global_vars["start_time"]}\n")
        file.write(f"LOGS_DIR={global_vars["log_location"]}\n")
        file.write(f"SIMULATION_THREADS={config["number_of_cores"]}\n")
        file.write(f"NUM_SIMULATIONS={config["number_of_simulations"]}\n")
        file.write("export WORK_DIR\n")
        file.write("export WORKFLOW_NUMBER\n")
        file.write("export WORKFLOW_LOCATION\n")
        file.write("export RESULTS_DIR\n")
        file.write("export LOGS_DIR\n")
        file.write("export SIMULATION_THREADS\n")
        file.write("export NUM_SIMULATIONS\n")
        file.write("\n\n")
       
        print_phase(file, "CFDaAI Pipeline - Makeflow")
        file.write("\n\n")

        # phase 1
        print_phase(file, "Phase 1: Data Acquisition")
        file.write("$(WORKFLOW_LOCATION)/pipeline.0:\n")
        file.write("\tLOCAL ./utils/get_data.sh > $(WORKFLOW_LOCATION)/pipeline.0 2>&1\n")
        file.write("\n")
        



        # phase 2
        print_phase(file, "Phase 2: Simulations")
        for i in range(config["number_of_simulations"]):
            file.write(f"{sim_options} -N cfd_sim_{i}\n")
            file.write(f"$(WORKFLOW_LOCATION)/simulations/of_sim.{i}: $(WORKFLOW_LOCATION)/pipeline.0\n")
            file.write(f"\tsh $(WORK_DIR)/uge/simulation_uge.sh $(RESULTS_DIR)/params $(RESULTS_DIR)/simulations {i} > $(WORKFLOW_LOCATION)/simulations/of_sim.{i} 2>&1\n")
        file.write("\n")



        # phase 3
        print_phase(file, "Phase 3: Training")
        for model in models:
            if model == "pcr":
                file.write(f"{pcr_options}\n")
            elif model == "pinn":
                file.write(f"{pinn_options}\n")
            elif model == "fno":
                file.write(f"{fno_options}\n")
            else:
                print(f"Unknown model {model}")
                sys.exit(1)

            file.write(f"$(WORKFLOW_LOCATION)/training/{model}_train.log:")
            for i in range(config["number_of_simulations"]):
                file.write(f" $(WORKFLOW_LOCATION)/simulations/of_sim.{i}")
            file.write("\n")
            file.write(f"\tsh uge/{model}_train_uge.sh $(RESULTS_DIR)/simulations $(RESULTS_DIR)/models/{model} > $(WORKFLOW_LOCATION)/training/{model}_train.log 2>&1\n")
            file.write("\n")
            
	
        # phase 4
        print_phase(file, "Phase 4: Evaluation")
        file.write("$(WORKFLOW_LOCATION)/pipeline.3:")
        for model in models:
            file.write(f" $(WORKFLOW_LOCATION)/training/{model}_train.log")
        file.write("\n")
        file.write("\t LOCAL ./utils/evaluation.sh > $(WORKFLOW_LOCATION)/pipeline.3 2>&1\n")
        file.write("\n")




if __name__ == "__main__":
    from datetime import datetime
    import os
    start_time = datetime.now().strftime("%y-%m-%d_%H_%M_%S")
    config = {
        "max_concurrent_workflows" : None,   # total number of workflows that can run concurrently
        "max_number_of_workflows"  : None,   # total number of workflows that will be submitted
        "time_between_workflows"   : 5,      # minimum time (in seconds) between workflow submissions.
        "time_check_workflows"     : 1,      # how often the program should check if it can submit new workflows (in seconds)
        "number_of_cores"          : 32,     # how many cores the simulations should run on
        "number_of_simulations"    : 10,     # how many OpenFOAM simulations per workflow
    }
    global_vars = {
        "workflow_counter"     : 1,
        "start_time"           : start_time,
        "log_location"         : f"logs/run_{start_time}",
        "workflow_status_file" : f"logs/run_{start_time}/coordinator/workflow_status_log.csv",
        "coordinator_output"   : f"logs/run_{start_time}/coordinator/coordinator_output.log"
    }

    workflow_location = f"{global_vars["log_location"]}/workflows/{global_vars["workflow_counter"]}"

    os.makedirs(f"{workflow_location}", exist_ok=True)
    os.makedirs(f"{workflow_location}/simulations", exist_ok=True)
    os.makedirs(f"{workflow_location}/training", exist_ok=True)

    create_makeflow(global_vars, config)
