#!/bin/python3
import asyncio, os, subprocess, time, sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from create_makeflow import create_makeflow

start_time = datetime.now().strftime("%y-%m-%d_%H_%M_%S")

# config
config = {
    "max_concurrent_workflows" : None,   # total number of workflows that can run concurrently
    "max_number_of_workflows"  : 1,   # total number of workflows that will be submitted
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

def log_info(input: str) -> None:
    log_string = f"[INFO] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(global_vars["coordinator_output"], 'a') as file:
        file.write(log_string + "\n")

def log_action(input: str) -> None:
    log_string = f"[ACTION] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(global_vars["coordinator_output"], 'a') as file:
        file.write(log_string + "\n")

def log_update(input: str) -> None:
    log_string = f"[UPDATE] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(global_vars["coordinator_output"], 'a') as file:
        file.write(log_string + "\n")

def setup_workflow() -> None:
    workflow_location = f"{global_vars["log_location"]}/workflows/{global_vars["workflow_counter"]}"

    os.makedirs(f"{workflow_location}", exist_ok=True)
    os.makedirs(f"{workflow_location}/simulations", exist_ok=True)
    os.makedirs(f"{workflow_location}/training", exist_ok=True)

    create_makeflow(global_vars, config)


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
        if config["max_concurrent_workflows"]:
            if len(self.active_workflows) >= config["max_concurrent_workflows"]:
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
    global global_vars
    logged_max_reached = False

    while True:
        if config["max_number_of_workflows"]:
            if global_vars["workflow_counter"] > config["max_number_of_workflows"]:
                if len(coordinator.active_workflows) == 0:
                    log_info("Maximum number of workflows reached and all jobs finished. Shutting down.")
                    sys.exit(0)
                else:
                    if not logged_max_reached:
                        log_info(f"Maximum workflows submitted. Waiting for {len(coordinator.active_workflows)} active job(s) to finish...")
                        logged_max_reached = True
                    await asyncio.sleep(config["time_check_workflows"])
                    continue

        if coordinator.can_submit_new_workflow():
            log_action("Submitting new workflow...")

            setup_workflow()
            makeflow_location = f"{global_vars["log_location"]}/workflows/{global_vars["workflow_counter"]}/cfdaai.makeflow"

            subprocess.run(
                ["makeflow", "-T", "uge", makeflow_location]
            )

            # subprocess.Popen(
            #     ["makeflow", "-T", "uge", makeflow_location],
            #     stdout=subprocess.DEVNULL,
            #     stderr=subprocess.DEVNULL
            # )

            coordinator.submit_workflow(global_vars["workflow_counter"])
            global_vars["workflow_counter"] += 1

        # Wait N seconds before checking the conditions again
        await asyncio.sleep(config["time_check_workflows"])

async def main():
    # ensure main log folder
    os.makedirs(f"{global_vars["log_location"]}/coordinator", exist_ok=True)
    os.makedirs(f"{global_vars["log_location"]}/workflows", exist_ok=True)

    # create the workflow status file
    if not os.path.exists(global_vars["workflow_status_file"]):
        with open(global_vars["workflow_status_file"], 'w') as file:
            file.write("workflow_id,task,status,unix_time\n")

    # create the log for the coordinator
    if not os.path.exists(global_vars["coordinator_output"]):
        open(global_vars["coordinator_output"], 'a').close()

    # Initialize coordinator
    coordinator = WorkflowCoordinator(config["time_between_workflows"], global_vars["workflow_status_file"])

    # asyncio.gather runs both the log monitor and submission loop concurrently
    await asyncio.gather(
        monitor_logs(global_vars["workflow_status_file"], coordinator),
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
