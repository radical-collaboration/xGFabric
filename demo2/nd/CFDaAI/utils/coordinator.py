#!/bin/python3
import asyncio, os, subprocess, time, sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

# config
max_concurrent_workflows = None   # total number of workflows that can run concurrently
max_number_of_workflows  = None   # total number of workflows that will be submitted
time_between_workflows   = 300    # minimum time (in seconds) between workflow submissions.
time_check_workflows     = 10     # how often the program should check if it can submit new workflows (in seconds)
input_flags              = "--mode full --system nd --threads 32 --iterations 1"

# global variables
workflow_counter     = 1
start_time           = datetime.now().strftime("%y-%m-%d_%H_%M_%S")
log_location         = f"logs/run_{start_time}"
workflow_status_file = f"{log_location}/coordinator/workflow_status_log.csv"
coordinator_output   = f"{log_location}/coordinator/coordinator_output.log"

def log_info(input: str):
    log_string = f"[INFO] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(coordinator_output, 'a') as file:
        file.write(log_string + "\n")

def log_action(input: str):
    log_string = f"[ACTION] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(coordinator_output, 'a') as file:
        file.write(log_string + "\n")

def log_update(input: str):
    log_string = f"[UPDATE] {datetime.now().strftime('%H:%M:%S')} {input}"
    print(log_string)
    with open(coordinator_output, 'a') as file:
        file.write(log_string + "\n")

@dataclass
class Workflow:
    workflow_id: str
    status: str  # 'submitted', 'started', 'exited'
    submission_time: float

class WorkflowCoordinator:
    def __init__(self, wait_time_seconds: float, log_file_path: str):
        self.active_workflows: Dict[str, Workflow] = {}
        self.log_file_path = log_file_path
        self.last_workflow_id: Optional[str] = None
        self.wait_time_seconds = wait_time_seconds

    def process_log_update(self, workflow_id: str, new_status: str):
        """Updates workflow status in O(1) time when logs are consumed."""
        if workflow_id in self.active_workflows:
            self.active_workflows[workflow_id].status = new_status

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
        if last_workflow.status == 'started' or last_workflow.status == 'submitted':
            # print(f"[Log] Cannot submit new workflow. Current workflow is still in queue.")
            return False

        # Condition 2: Have N seconds elapsed?
        time_elapsed = time.time() - last_workflow.submission_time
        if time_elapsed < self.wait_time_seconds:
            # time_left = self.wait_time_seconds - time_elapsed
            # print("[Log] Cannot submit new workflow. Not enough time has past. ", end="")
            # print(f"{time_left:.0f} seconds remaining.")
            return False

        # Condition 3: Too many concurrent workflows?
        if max_concurrent_workflows:
            if len(self.active_workflows) >= max_concurrent_workflows:
                return False

        return True

    def submit_workflow(self, workflow_id: str):
        """Adds a new workflow to the tracking dictionary."""
        new_workflow = Workflow(
            workflow_id=workflow_id,
            status='submitted',
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
            workflow_id = line[0].split("_")[1]
            curr_job = line[1]
            status = line[2]
            coordinator.process_log_update(workflow_id, status)
            log_update(f"Workflow {workflow_id} ==> {curr_job} ==> {status}")

async def workflow_submission_loop(coordinator: WorkflowCoordinator):
    """Periodically checks if a new workflow can be submitted."""
    global workflow_counter
    logged_max_reached = False

    while True:
        if (max_number_of_workflows) and (workflow_counter > max_number_of_workflows):
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
            workflow_id = f"{workflow_counter}"
            log_action("Submitting new workflow...")

            shell_args = input_flags.split(" ")
            shell_args.extend(['--workflow_number', workflow_id])
            shell_args.extend(['--coord_run_name', f"run_{start_time}"])

            os.mkdir(f"logs/run_{start_time}/workflows/{workflow_id}")
            os.mkdir(f"logs/run_{start_time}/workflows/{workflow_id}/simulations")
            os.mkdir(f"logs/run_{start_time}/workflows/{workflow_id}/training")

            subprocess.Popen(
                ["sh", "cfdaai.sh"] + shell_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            coordinator.submit_workflow(workflow_id)
            workflow_counter += 1

        # Wait N seconds before checking the conditions again
        await asyncio.sleep(time_check_workflows)

async def main():
    # ensure main log folder
    os.makedirs(f"{log_location}/coordinator")
    os.makedirs(f"{log_location}/workflows")

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
