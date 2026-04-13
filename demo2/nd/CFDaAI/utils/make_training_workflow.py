#!/bin/python3
import sys

def main():
    args = sys.argv[1:]
    models       = args[0]
    file_name    = args[1]
    num_cores    = args[2]
    work_dir     = args[3]

    pcr_options  = f"BATCH_OPTIONS=-terse -pe smp {num_cores} -q long -N pcr_train"
    pinn_options = f"BATCH_OPTIONS=-terse -pe smp {num_cores} -q gpu -l gpu_card=1 -N pinn_train"
    fno_options  = f"BATCH_OPTIONS=-terse -pe smp {num_cores} -q gpu -l gpu_card=1 -N fno_train"

    with open(file_name, "a") as file:
        file.write(f"CORES={num_cores}\n\n")

        model_arr = models.split(" ")
        for model in model_arr:
            file.write(f"CATEGORY=\"{model}\"\n")

            if model == "pcr":
                file.write(f"{pcr_options}\n")
            elif model == "pinn":
                file.write(f"{pinn_options}\n")
            elif model == "fno":
                file.write(f"{fno_options}\n")
            else:
                print(f"Unknown model {model}")
                sys.exit(1)

            file.write(f"$(WORKFLOW_LOCATION)/training/{model}_train.log:\n")
            file.write(f"\tsh {work_dir}/training/orchestrate_training.sh {model} $(RESULTS_DIR)/simulations $(RESULTS_DIR)/models/{model} > $(WORKFLOW_LOCATION)/training/{model}_train.log\n\n")

if __name__ == "__main__":
    main()
