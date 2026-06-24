#!/bin/python3
import asyncio, os, subprocess, time, sys, threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from create_makeflow import create_makeflow, detect_system
from dotenv import load_dotenv

load_dotenv(dotenv_path="config.sh")


start_time = datetime.now().strftime("%y-%m-%d_%H_%M_%S")

config = {
"max_concurrent_workflows" : int(os.getenv("MAX_PARALLEL_WORKFLOWS", 1)),   # total number of workflows that can run concurrently
"max_number_of_workflows"  : int(os.getenv("MAX_NUMBER_OF_WORKFLOWS", 1)),   # total number of workflows that will be submitted (None = endless)
"time_between_workflows"   : int(os.getenv("TIME_BETWEEN_WORKFLOWS", 60)),      # minimum time (in seconds) between workflow submissions
"time_check_workflows"     : 60,      # how often the program checks if it can submit new workflows (seconds)
"number_of_cores"          : int(os.getenv("NUM_OF_CORES_PER_SIM", 32)),     # cores per simulation / per node
"number_of_simulations"    : int(os.getenv("NUM_SIMULATIONS", 72)),      # OpenFOAM simulations per workflow (== number of nodes)
"workqueue_mode"           : True,   # always True for Work Queue / Makeflow
# --- Node allocation ---
"wq_project_name"          : os.getenv("WORK_QUEUE_PROJECT_NAME", "wq_default_proj"),   # -N name shared by workers and makeflow
"node_poll_interval"       : 60,     # seconds between "are all workers connected?" checks
"node_ready_timeout"       : int(os.getenv("AWAIT_WORK_QUEUE_WORKERS_TIMEOUT",72000)),   # seconds to wait for all workers before giving up (20 h)
"worker_walltime"          : os.getenv("MAX_WORK_QUEUE_WORKER_WALLTIME", "01:00:00"),
"worker_qos"               : os.getenv("WORK_QUEUE_QOS", "regular"),
"worker_constraint"     : os.getenv("WORK_QUEUE_CONSTRAINT", "cpu"),
"worker_nodes"          : int(os.getenv("WORK_QUEUE_NUM_NODES", 1)),
"worker_cores"          : int(os.getenv("WORK_QUEUE_WORKER_CORES", 128)),
}

scratch_path = os.getenv("SCRATCHSPACE", ".")

config['scratchspace'] = scratch_path

global_vars = {
    "workflow_counter"     : 1,
    "start_time"           : start_time,
    "log_location"         : f"{scratch_path}/logs/run_{start_time}",
    "workflow_status_file" : f"{scratch_path}/logs/run_{start_time}/coordinator/workflow_status_log.csv",
    "coordinator_output"   : f"{scratch_path}/logs/run_{start_time}/coordinator/coordinator_output.log",
}

def log_info(msg: str) -> None:
    s = f"[INFO]   {datetime.now().strftime('%H:%M:%S')} {msg}"
    print(s)
    with open(global_vars['coordinator_output'], 'a') as f:
        f.write(s + "\n")

def log_status(msg: str) -> None:
    s = f"[Status] {datetime.now().strftime('%H:%M:%S')} {msg}"
    sys.stdout.write(f"\r{s}")
    sys.stdout.flush()
    with open(global_vars['coordinator_output'], 'a') as f:
        f.write(s + "\n")

def log_action(msg: str) -> None:
    s = f"[ACTION] {datetime.now().strftime('%H:%M:%S')} {msg}"
    print(s)
    with open(global_vars['coordinator_output'], 'a') as f:
        f.write(s + "\n")

def log_update(msg: str) -> None:
    s = f"[UPDATE] {datetime.now().strftime('%H:%M:%S')} {msg}"
    print(s)
    with open(global_vars['coordinator_output'], 'a') as f:
        f.write(s + "\n")

def log_warn(msg: str) -> None:
    s = f"[WARN]   {datetime.now().strftime('%H:%M:%S')} {msg}"
    print(s)
    with open(global_vars['coordinator_output'], 'a') as f:
        f.write(s + "\n")

# ---------------------------------------------------------------------------
# Node allocation
# ---------------------------------------------------------------------------

class NodeAllocator:
    """
    Manages a single `salloc … srun work_queue_worker` reservation.

    The salloc command blocks until the allocation is granted, then immediately
    runs `srun work_queue_worker` on every allocated node. When the allocation
    ends (wall-clock limit, preemption, or explicit cancel) the process exits
    and `is_alive()` returns False, triggering a fresh submission.
    """

    def __init__(self):
        self._proc:  Optional[subprocess.Popen] = None
        self.job_id: Optional[str] = None

    # ------------------------------------------------------------------
    def is_alive(self) -> bool:
        """True when the salloc/srun process is still running."""
        if self._proc is None:
            return False
        return self._proc.poll() is None   # None == still running

    # ------------------------------------------------------------------
    def submit(self) -> None:
        """
        Launch the salloc reservation + workers in the background.
        Captures stderr (where salloc prints 'Granted job allocation <ID>')
        so we can record the SLURM job ID for later squeue polling.
        Returns immediately; use is_alive() / job_id to track it.
        """
        n_nodes    = config["worker_nodes"]
        n_cores    = config["worker_cores"]
        project    = config["wq_project_name"]
        walltime   = config["worker_walltime"]
        qos        = config["worker_qos"]
        constraint = config["worker_constraint"]
        node_ready_timeout = config["node_ready_timeout"]
        print(config)

        # total cores
        max_sims_per_node = config["worker_cores"] // config["number_of_cores"]
        if(max_sims_per_node == 0):
            log_warn(f"Too few worker cores to run a simulation with rank={config['number_of_cores']}!")
        

        cmd = [
            "salloc",
            f"--nodes={n_nodes}",
            f"--ntasks={n_cores}",
            f"--qos={qos}",
            f"--constraint={constraint}",
            f"--time={walltime}",
            "--job-name=ben_openfoam_wq",
            "srun",
            "work_queue_worker",
            "-M", project,
            "--max-backoff=10", # reconnect quickly
            f"--timeout={node_ready_timeout}", 
            f"--cores={n_cores}",
        ]

        # Script calls: bash $(WORK_DIR)/slurm/simulation_slurm.sh
        # $(RESULTS_DIR)/params $(RESULTS_DIR)/simulations 67
        log_action(f"Submitting node allocation: {' '.join(cmd)}")

        # salloc writes "Granted job allocation <JOBID>" to stderr.
        # We pipe stderr through a thread so we can parse the ID without
        # blocking the event loop, while the process keeps running.
        self._proc  = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.job_id = None

        threading.Thread(target=self._parse_job_id, daemon=True).start()

    # ------------------------------------------------------------------
    def _parse_job_id(self) -> None:
        """
        Runs in a background thread. Reads salloc stderr line-by-line
        until it finds the 'Granted job allocation' message, then stores
        the numeric job ID.  Any remaining stderr is silently discarded.

        salloc output example:
            salloc: Granted job allocation 12345678
        """
        if self._proc is None or self._proc.stderr is None:
            return
        for raw_line in self._proc.stderr:
            line = raw_line.decode(errors="replace").strip()
            if "job allocation" in line:
                parts = line.split()
                if parts:
                    self.job_id = parts[-1]
                    log_info(f"SLURM job ID captured: {self.job_id}")
                break
        # Drain any remaining stderr so the pipe buffer never blocks salloc
        for _ in self._proc.stderr:
            pass

    # ------------------------------------------------------------------
    def cancel(self) -> None:
        """Terminate the salloc process (releases the SLURM reservation)."""
        if self._proc and self._proc.poll() is None:
            log_action("Cancelling existing node allocation.")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc  = None
        self.job_id = None

    # ------------------------------------------------------------------
    async def ensure_alive(self) -> None:
        """
        Called before each workflow. If the reservation has died (preempted,
        wall-clock expired, etc.) submit a fresh one.
        """
        if not self.is_alive():
            log_warn("Node allocation is not active. Re-submitting...")
            self.submit()
        else:
            log_info(f"Node allocation is active (SLURM job {self.job_id}).")

# ---------------------------------------------------------------------------
# SLURM helpers
# ---------------------------------------------------------------------------

def get_slurm_job_state(job_id: str) -> str:
    """
    Return the SLURM state string for `job_id` (e.g. 'R', 'PD', 'CG'),
    or '' if the job is no longer visible in squeue.

    Uses:  squeue -j <job_id> -h -o %t
      -h  suppress header
      %t  state code only
    """
    try:
        result = subprocess.run(
            ["squeue", "-j", job_id, "-h", "-o", "%t"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        log_warn("squeue not found on PATH.")
        return ""
    except subprocess.TimeoutExpired:
        log_warn("squeue timed out.")
        return ""
    except Exception as e:
        log_warn(f"squeue error: {e}")
        return ""


async def wait_for_nodes_running(node_allocator: NodeAllocator) -> bool:
    """
    Poll squeue until the SLURM job moves from PD (pending) to R (running),
    meaning all nodes are allocated and the work_queue_workers have started.

    Returns True  once the job state is 'R'.
    Returns False if:
      - the job ID is still unknown after node_ready_timeout seconds
        (salloc hasn't printed 'Granted job allocation' yet), or
      - the job disappears from squeue without ever reaching 'R'
        (cancelled, failed, etc.), or
      - node_ready_timeout seconds elapse without reaching 'R'.
    """
    poll_interval = config["node_poll_interval"]
    timeout       = config["node_ready_timeout"]
    deadline      = time.time() + timeout

    log_info("Waiting for SLURM job to reach state R (running)...")

    while True:
        job_id = node_allocator.job_id

        if job_id is None:
            log_status("Waiting for SLURM job ID (salloc not yet granted)...")
        else:
            state = get_slurm_job_state(job_id)
            log_status(f"SLURM job {job_id} state: '{state}'")

            if state == "R":
                log_action(f"SLURM job {job_id} is running. All nodes are ready.")
                return True

            if state == "":
                # Job vanished from squeue – it never ran or was cancelled.
                log_warn(f"SLURM job {job_id} no longer in squeue. Allocation lost.")
                return False

        if time.time() > deadline:
            log_warn(f"Timed out after {timeout}s waiting for nodes to reach state R.")
            return False

        await asyncio.sleep(poll_interval)

# ---------------------------------------------------------------------------
# Workflow dataclass + coordinator
# ---------------------------------------------------------------------------

def setup_workflow() -> str:
    workflow_location = (
        f"{global_vars['log_location']}/workflows/{global_vars['workflow_counter']}"
    )
    os.makedirs(f"{workflow_location}",             exist_ok=True)
    os.makedirs(f"{workflow_location}/simulations", exist_ok=True)
    os.makedirs(f"{workflow_location}/training",    exist_ok=True)
    return create_makeflow(global_vars, config)


@dataclass
class Workflow:
    workflow_id:     int
    status:          str
    current_task:    str
    submission_time: float
    makeflow_proc:   Optional[subprocess.Popen] = field(default=None, repr=False)


class WorkflowCoordinator:
    def __init__(self, wait_time_seconds: float, log_file_path: str):
        self.active_workflows: Dict[int, Workflow] = {}
        self.log_file_path         = log_file_path
        self.last_workflow_id:     Optional[int]   = None
        self.last_submission_time: Optional[float] = None
        self.wait_time_seconds     = wait_time_seconds

    # ------------------------------------------------------------------
    def process_log_update(self, workflow_id: int, curr_task: str, new_status: str):
        """Updates workflow status in O(1) time when logs are consumed."""
        if workflow_id not in self.active_workflows:
            return

        self.active_workflows[workflow_id].status       = new_status
        self.active_workflows[workflow_id].current_task = curr_task

        if new_status == 'exited':
            del self.active_workflows[workflow_id]
            if self.last_workflow_id == workflow_id:
                self.last_workflow_id = None

    # ------------------------------------------------------------------
    def can_submit_new_workflow(self) -> bool:
        """True when the previous workflow has exited and enough time has elapsed."""
        # Previous workflow is still active → not ready
        if self.last_workflow_id is not None and self.last_workflow_id in self.active_workflows:
            last = self.active_workflows[self.last_workflow_id]
            if last.status != 'exited':
                return False

        # Minimum gap between submissions (uses recorded time, survives workflow removal)
        if self.last_submission_time is not None:
            if time.time() - self.last_submission_time < self.wait_time_seconds:
                return False

        # Optional concurrency cap
        if config["max_concurrent_workflows"]:
            if len(self.active_workflows) >= config["max_concurrent_workflows"]:
                return False

        return True

    # ------------------------------------------------------------------
    def submit_workflow(self, workflow_id: int, proc: subprocess.Popen):
        """Register a newly launched workflow."""
        self.active_workflows[workflow_id] = Workflow(
            workflow_id=workflow_id,
            status='submitted',
            current_task='',
            submission_time=time.time(),
            makeflow_proc=proc,
        )
        self.last_workflow_id     = workflow_id
        self.last_submission_time = time.time()
        log_action(f"Workflow {workflow_id} launched.")


# ---------------------------------------------------------------------------
# Async tasks
# ---------------------------------------------------------------------------

async def monitor_logs(log_file_path: str, coordinator: WorkflowCoordinator):
    """Tail the workflow status CSV and forward updates to the coordinator."""
    log_info(f"Monitoring logs at: {log_file_path}")

    with open(log_file_path, 'r') as f:
        f.seek(0, 2)   # start at end – only read new lines

        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(1)
                continue

            parts = line.split(",")
            if len(parts) < 3:
                continue

            workflow_id = int(parts[0])
            curr_task   = str(parts[1]).strip()
            status      = str(parts[2]).strip()

            coordinator.process_log_update(workflow_id, curr_task, status)
            log_update(f"Workflow {workflow_id} ==> {curr_task} ==> {status}")


async def workflow_submission_loop(coordinator: WorkflowCoordinator, node_allocator: NodeAllocator, generate_makeflow_only=False):
    """
    Endless loop:
      1. Ensure SLURM nodes are allocated (re-submit if dead).
      2. Wait until all Work Queue workers have connected.
      3. Run Makeflow non-blocking so both simulations and this loop continue.
      4. Wait for Makeflow to finish before repeating.
    """
    global global_vars


    # check makeflow dependency
    proc_test = subprocess.Popen(
            [
                "makeflow",
                "--version"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    # Communicate with the process to get the output and error
    stdout, stderr = proc_test.communicate()

    # Print the output and error
    log_info(f"Makeflow Version: {stdout.decode()} {stderr}")

    if(generate_makeflow_only):
        log_info("Generating makeflow file only")
        makeflow_file = setup_workflow()
        log_info(f"Makeflow workflow saved at {makeflow_file}")
        sys.exit(0)
        return


    while True:
        if config["max_number_of_workflows"]:
            if global_vars['workflow_counter'] > config["max_number_of_workflows"]:
                if not coordinator.active_workflows:
                    log_info("Max workflows reached and all jobs done. Shutting down.")
                    sys.exit(0)
                await asyncio.sleep(config["time_check_workflows"])
                continue

        if not coordinator.can_submit_new_workflow():
            await asyncio.sleep(config["time_check_workflows"])
            continue

        # ---- Step 1: ensure nodes are allocated ----
        await node_allocator.ensure_alive()

        # ---- Step 2: wait until the SLURM job is in state R ----
        nodes_ready = await wait_for_nodes_running(node_allocator)
        if not nodes_ready:
            # Job never started, vanished, or timed out – cancel and retry
            node_allocator.cancel()
            log_warn("Will re-allocate nodes and try again...")
            await asyncio.sleep(config["time_check_workflows"])
            continue

        # ---- Step 3: build workflow directory + Makeflow file ----
        log_action(f"Submitting workflow {global_vars['workflow_counter']}...")
        setup_workflow()

        makeflow_location = (
            f"{global_vars['log_location']}/workflows/"
            f"{global_vars['workflow_counter']}/cfdaai.makeflow"
        )
        makeflow_log = (
            f"{global_vars['log_location']}/workflows/"
            f"{global_vars['workflow_counter']}/makeflow.debug"
        )

        # ---- Step 4: launch Makeflow non-blocking ----
        proc = subprocess.Popen(
            [
                "makeflow",
                "-T", "wq",
                "-N", config["wq_project_name"],
                makeflow_location,
                "-d", "all",
                "--retry-count=5",
                "-P", str(global_vars['workflow_counter']),
                "-o", makeflow_log,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        coordinator.submit_workflow(global_vars['workflow_counter'], proc)
        wf_id = global_vars['workflow_counter']
        global_vars['workflow_counter'] += 1

        # ---- Step 5: wait for this Makeflow to finish ----
        log_info(f"Waiting for workflow {wf_id} Makeflow process to complete...")
        while True:
            if wf_id not in coordinator.active_workflows:
                log_info(f"Workflow {wf_id} complete.")
                break
            # Fallback: detect silent crashes where the log never writes 'exited'
            if proc.poll() is not None:
                log_warn(f"Workflow {wf_id} Makeflow process exited (rc={proc.returncode}) "
                         f"without a log status update. Marking complete.")
                coordinator.process_log_update(wf_id, 'unknown', 'exited')
                break
            await asyncio.sleep(config["time_check_workflows"])

        # Brief pause before the next iteration
        await asyncio.sleep(config["time_between_workflows"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    os.makedirs(f"{global_vars['log_location']}/coordinator", exist_ok=True)
    os.makedirs(f"{global_vars['log_location']}/workflows",   exist_ok=True)
    log_info("Coordinator Startup")

    if not os.path.exists(global_vars['workflow_status_file']):
        with open(global_vars['workflow_status_file'], 'w') as f:
            f.write("workflow_id,task,status,unix_time\n")

    if not os.path.exists(global_vars['coordinator_output']):
        open(global_vars['coordinator_output'], 'a').close()

    coordinator    = WorkflowCoordinator(config["time_between_workflows"], global_vars['workflow_status_file'])
    node_allocator = NodeAllocator()

    generate_makeflow_only = False
    if(len(sys.argv) == 2 and sys.argv[1] == "--generate-makeflow-only"):
        generate_makeflow_only = True

    if(len(sys.argv) == 2 and sys.argv[1] == "--help"):
        print("\nPass no parameters to run normal coordinator.py.")
        print("Pass --generate-makeflow-only to only generate a makeflow workflow script")
        print("Pass --help to see this message\n")
        return

    # exp = await asyncio.gather(
    #     monitor_logs(global_vars['workflow_status_file'], coordinator),
    #     workflow_submission_loop(coordinator, node_allocator,generate_makeflow_only),
    #     return_exceptions=True,
    # )
    
    monitor_task = asyncio.create_task(
        monitor_logs(global_vars['workflow_status_file'], coordinator)
    )
    submission_task = asyncio.create_task(
        workflow_submission_loop(coordinator, node_allocator, generate_makeflow_only)
    )

    done, pending = await asyncio.wait(
        {monitor_task, submission_task},
        return_when=asyncio.FIRST_EXCEPTION,
    )

    for task in pending:
        task.cancel()
    for task in done:
        if task.exception() is not None:
            raise task.exception()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_info("Coordinator shut down safely.")
    except SystemExit:
        log_info("Coordinator has finished.")