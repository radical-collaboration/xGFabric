#!/bin/python3
import asyncio, os, re, subprocess, time, sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

def log_info(input: str):
    print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} {input}")

def log_action(input: str):
    print(f"[ACTION] {datetime.now().strftime('%H:%M:%S')} {input}")

def log_update(input: str):
    print(f"[UPDATE] {datetime.now().strftime('%H:%M:%S')} {input}")

@dataclass
class Job:
    job_id: str
    status: str  # 'submitted', 'started', 'exited'
    submission_time: float

class JobCoordinator:
    def __init__(self, wait_time_minutes: float, log_file_path: str):
        self.active_jobs: Dict[str, Job] = {}
        self.log_file_path = log_file_path
        self.last_job_id: Optional[str] = None
        self.wait_time_seconds = wait_time_minutes * 60

    def process_log_update(self, job_id: str, new_status: str):
        """Updates job status in O(1) time when logs are consumed."""
        if job_id in self.active_jobs:
            self.active_jobs[job_id].status = new_status
            
            # If the job exited, remove it to free up memory
            if new_status == 'exited':
                del self.active_jobs[job_id]
                # If the last submitted job just exited, clear the pointer
                if self.last_job_id == job_id:
                    self.last_job_id = None

    def can_submit_new_job(self) -> bool:
        """Checks prior job started AND N minutes elapsed."""
        # If no jobs have been submitted yet, or the last one exited
        if self.last_job_id is None or self.last_job_id not in self.active_jobs:
            return True
        last_job = self.active_jobs[self.last_job_id]
        
        # Condition 1: Has the prior job started running?
        if last_job.status == 'started' or last_job.status == 'submitted':
            # print(f"[Log] Cannot submit new job. Current job is still in queue.")
            return False

        # Condition 2: Have N minutes elapsed?
        time_elapsed = time.time() - last_job.submission_time
        if time_elapsed < self.wait_time_seconds:
            # time_left = self.wait_time_seconds - time_elapsed
            # print("[Log] Cannot submit new job. Not enough time has past. ", end="")
            # print(f"{time_left:.0f} seconds remaining.")
            return False

        return True

    def submit_job(self, job_id: str):
        """Adds a new job to the tracking dictionary."""
        new_job = Job(
            job_id=job_id,
            status='submitted',
            submission_time=time.time()
        )
        self.active_jobs[job_id] = new_job
        self.last_job_id = job_id
        log_action(f"Job {job_id} launched.")

async def monitor_logs(log_file_path: str, coordinator: JobCoordinator):
    """Asynchronously reads log files as they are written (like 'tail -f')."""
    if not os.path.exists(log_file_path):
        open(log_file_path, 'a').close()

    log_info(f"Monitoring logs at: {log_file_path}...")
    
    with open(log_file_path, 'r') as f:
        f.seek(0, 2)  # Jump to the end of the file so we only read new logs
        
        while True:
            line = f.readline()
            if not line:
                # If no new line, yield control back to the event loop for 1 second
                await asyncio.sleep(1)
                continue
            
            match = re.search(r'Job (\w+):\s*(started|submitted|running|exited)', line)
            if match:
                job_id, status = match.groups()
                coordinator.process_log_update(job_id, status)
                log_update(f"Job {job_id} updated to: {status}")

async def job_submission_loop(coordinator: JobCoordinator):
    """Periodically checks if a new job can be submitted."""
    job_counter = 1
    
    while True:
        if coordinator.can_submit_new_job():
            job_id = f"{job_counter}"
            log_action("Submitting new job...")

            shell_args = sys.argv[1:]
            shell_args.extend(['--job_number', job_id])
            shell_args.extend(['--coord_log_file', coordinator.log_file_path])

            subprocess.Popen(
                ["sh", "cfdaai.sh"] + shell_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            coordinator.submit_job(job_id)
            job_counter += 1

        # Wait 10 seconds before checking the conditions again
        await asyncio.sleep(10)

async def main():
    # Initialize coordinator
    curr_time = datetime.now().strftime("%y-%m-%d_%H_%M_%S")
    log_file = f"jobs_logs/simulation_logs_{curr_time}.out"
    coordinator = JobCoordinator(5, log_file)
    
    # asyncio.gather runs both the log monitor and submission loop concurrently
    await asyncio.gather(
        monitor_logs(log_file, coordinator),
        job_submission_loop(coordinator)
    )

if __name__ == "__main__":
    # Start the event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_info("\nCoordinator shut down safely.")
