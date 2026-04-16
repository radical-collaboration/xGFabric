#!/bin/python3
import asyncio, os, subprocess, time, sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

# config
max_concurrent_workflows = None   # total number of workflows that can run concurrently
max_number_of_workflows  = None   # total number of workflows that will be submitted
time_between_workflows   = 5      # minimum time (in seconds) between workflow submissions.
time_check_workflows     = 1      # how often the program should check if it can submit new workflows (in seconds)
number_of_cores          = 32     # how many cores the simulations should run on
print_err_files          = False  # should makeflow print the error files associated with each step of the pipeline

# global variables
workflow_counter     = 1
start_time           = datetime.now().strftime("%y-%m-%d_%H_%M_%S")
log_location         = f"logs/run_{start_time}"
workflow_status_file = f"{log_location}/coordinator/workflow_status_log.csv"
coordinator_output   = f"{log_location}/coordinator/coordinator_output.log"

def log_info(input: str) -> None:
    log_string = f"[INFO] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(coordinator_output, 'a') as file:
        file.write(log_string + "\n")

def log_action(input: str) -> None:
    log_string = f"[ACTION] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(coordinator_output, 'a') as file:
        file.write(log_string + "\n")

def log_update(input: str) -> None:
    log_string = f"[UPDATE] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(coordinator_output, 'a') as file:
        file.write(log_string + "\n")

def setup_workflow() -> None:
    workflow_location = f"{log_location}/workflows/{workflow_counter}"

    os.makedirs(f"{workflow_location}", exist_ok=True)
    os.makedirs(f"{workflow_location}/simulations", exist_ok=True)
    os.makedirs(f"{workflow_location}/training", exist_ok=True)

    with open(f"{workflow_location}/cfdaai.makeflow", "w") as file:
        file.write("# --- Configuration ---\n")
        file.write("WORK_DIR=.\n")
        file.write(f"WORKFLOW_NUMBER={workflow_counter}\n")
        file.write(f"WORKFLOW_LOCATION={workflow_location}\n")
        file.write(f"RESULTS_DIR=results/run_{start_time}/workflow_{workflow_counter}\n")
        file.write(f"START_TIME={start_time}\n")
        file.write(f"LOGS_DIR={log_location}\n")
        file.write(f"SIMULATION_THREADS={number_of_cores}\n\n")

        file.write(open("utils/cfdaai.makeflow").read())


    if print_err_files:
        with open(f"{workflow_location}/cfdaai.makeflow", "r") as file:
            lines = file.readlines() 

        new_lines = []
        for line in lines:
            if line.strip().startswith("./utils/"):
                split_line = line.strip().split(" > ")
                line = f"\t{split_line[0]} > {split_line[1]} 2> {split_line[1]}.err\n"
            new_lines.append(line)

        with open(f"{workflow_location}/cfdaai.makeflow", "w") as file:
            file.writelines(new_lines)


@dataclass
class Workflow:
    workflow_id: str
    status: str
    current_task: str
    submission_time: float

class WorkflowCoordinator:
    def __init__(self, wait_time_seconds: float, log_file_path: str):
        self.active_workflows: Dict[int, Workflow] = {}
        self.log_file_path = log_file_path
        self.last_workflow_id: Optional[int] = None
        self.wait_time_seconds = wait_time_seconds

    def process_log_update(self, workflow_id: int, curr_task: str, new_status: str):
        """Updates workflow status in O(1) time when logs are consumed."""
        if workflow_id in self.active_workflows:
            self.active_workflows[workflow_id].status = new_status
            self.active_workflows[workflow_id].current_task = curr_task

            # If the workflow exited, remove it to free up memory
            if new_status == 'exited':
                del self.active_workflows[workflow_id]
                # If the last submitted workflow just exited, clear the pointer
                if self.last_workflow_id == workflow_id:
                    self.last_workflow_id = None

    def can_submit_new_workflow(self) -> bool:
        """Checks prior workflow started AND N seconds elapsed."""
        # If no workflows have been submitted yet, or the last one exited
        if self.last_workflow_id is None or self.last_workflow_id not in self.active_workflows:
            return True
        last_workflow = self.active_workflows[self.last_workflow_id]

        # Condition 1: Has the prior workflow started running?
        if last_workflow.status != 'exited':
                # log_update(f"Cannot submit new workflow. Current workflow task is: {last_workflow.current_task}.")
                return False

        # Condition 2: Have N seconds elapsed?
        time_elapsed = time.time() - last_workflow.submission_time
        if time_elapsed < self.wait_time_seconds:
            time_left = self.wait_time_seconds - time_elapsed
            # log_update("[Log] Cannot submit new workflow. Not enough time has past.", end=" ")
            # print(f"{time_left:.0f} seconds remaining.")
            return False

        # Condition 3: Too many concurrent workflows?
        if max_concurrent_workflows:
            if len(self.active_workflows) >= max_concurrent_workflows:
                return False

        return True

    def submit_workflow(self, workflow_id: int):
        """Adds a new workflow to the tracking dictionary."""
        new_workflow = Workflow(
            workflow_id=workflow_id,
            status='submitted',
            current_task='',
            submission_time=time.time()
        )
        self.active_workflows[workflow_id] = new_workflow
        self.last_workflow_id = workflow_id
        log_action(f"Workflow {workflow_id} launched.")

async def monitor_logs(log_file_path: str, coordinator: WorkflowCoordinator):
    """Asynchronously reads log files as they are written (like 'tail -f')."""
    log_info(f"Monitoring logs at: {log_file_path}")

    with open(log_file_path, 'r') as f:
        f.seek(0, 2)  # Jump to the end of the file so we only read new logs

        while True:
            line = f.readline()
            if not line:
                # If no new line, yield control back to the event loop for 1 second
                await asyncio.sleep(1)
                continue

            line = line.split(",")
            workflow_id = int(line[0])
            curr_task = str(line[1]).strip()
            status = str(line[2]).strip()

            coordinator.process_log_update(workflow_id, curr_task, status)
            log_update(f"Workflow {workflow_id} ==> {curr_task} ==> {status}")

async def workflow_submission_loop(coordinator: WorkflowCoordinator):
    """Periodically checks if a new workflow can be submitted."""
    global workflow_counter
    logged_max_reached = False

    while True:
        if max_number_of_workflows:
            if workflow_counter > max_number_of_workflows:
                if len(coordinator.active_workflows) == 0:
                    log_info("Maximum number of workflows reached and all jobs finished. Shutting down.")
                    sys.exit(0)
                else:
                    if not logged_max_reached:
                        log_info(f"Maximum workflows submitted. Waiting for {len(coordinator.active_workflows)} active job(s) to finish...")
                        logged_max_reached = True
                    await asyncio.sleep(time_check_workflows)
                    continue

        if coordinator.can_submit_new_workflow():
            log_action("Submitting new workflow...")

            setup_workflow()
            makeflow_location = f"{log_location}/workflows/{workflow_counter}/cfdaai.makeflow"

            subprocess.Popen(
                ["makeflow", makeflow_location],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            coordinator.submit_workflow(workflow_counter)
            workflow_counter += 1

        # Wait N seconds before checking the conditions again
        await asyncio.sleep(time_check_workflows)

async def main():
    # ensure main log folder
    os.makedirs(f"{log_location}/coordinator", exist_ok=True)
    os.makedirs(f"{log_location}/workflows", exist_ok=True)

    # create the workflow status file
    if not os.path.exists(workflow_status_file):
        with open(workflow_status_file, 'w') as file:
            file.write("workflow_id,task,status,unix_time\n")

    # create the log for the coordinator
    if not os.path.exists(coordinator_output):
        open(coordinator_output, 'a').close()

    # Initialize coordinator
    coordinator = WorkflowCoordinator(time_between_workflows, workflow_status_file)

    # asyncio.gather runs both the log monitor and submission loop concurrently
    await asyncio.gather(
        monitor_logs(workflow_status_file, coordinator),
        workflow_submission_loop(coordinator),
        return_exceptions=True
    )

if __name__ == "__main__":
    # Start the event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_info("Coordinator shut down safely.")
    except SystemExit:
        log_info("Coordinator has finished.")
