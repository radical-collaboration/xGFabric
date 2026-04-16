#!/bin/python3
import sys

def main():
    args = sys.argv[1:]

    num_sims     = int(args[0])
    file_name    = args[1]
    num_cores    = args[2]
    work_dir     = args[3]
    param_dir    = args[4]
    sim_output   = args[5]

    sim_options  = f"BATCH_OPTIONS=-terse -pe smp {num_cores} -q long"

    with open(file_name, "a") as file:
        file.write(f"CORES={num_cores}\n\n")

        for i in range(num_sims):
            file.write(f"{sim_options} -N cfd_sim_{i}\n")
            file.write(f"$(WORKFLOW_LOCATION)/simulations/of_sim.{i}:\n")
            file.write(f"\tsh {work_dir}/uge/simulation_uge.sh {param_dir} {sim_output} {i} > $(WORKFLOW_LOCATION)/simulations/of_sim.{i} 2> $(WORKFLOW_LOCATION)/simulations/of_sim.{i}.err\n\n")

        for i in range(num_sims):
            file.write(f"LOCAL $(WORKFLOW_LOCATION)/simulations/of_sim.{i}.done: $(WORKFLOW_LOCATION)/simulations/of_sim.{i}\n")
            file.write(f"\tpython3 $(WORK_DIR)/utils/csv_logger.py $(WORKFLOW_NUMBER) openfoam_{i} completed $(STATUS_FILE) && touch $(WORKFLOW_LOCATION)/simulations/of_sim.{i}.done\n\n")

if __name__ == "__main__":
    main()
