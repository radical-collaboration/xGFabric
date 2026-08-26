#!/usr/bin/env python3


# Given a python func via cloudpickle, load and profile it!

#
# IO note: disk_read_bytes and disk_write_bytes DO NOT INCLUDE CACHE!
#

import argparse
import asyncio
import json
import os
import shlex
import psutil
import subprocess
import sys
import time

from dataclasses import dataclass, field

from digitaltwin.components import TypedData
import cloudpickle


def export_inference_function(out_file, func, example_data: TypedData, **kwargs):
    payload = {"func": func, "in_data": example_data, "kwargs": kwargs}

    with open(out_file, "wb") as f:
        cloudpickle.dump(payload, f)


@dataclass
class ProcessSnapshot:
    cpu_time: float = 0.0
    read_bytes: int = 0
    write_bytes: int = 0
    sys_read_bytes: int = 0
    sys_write_bytes: int = 0
    peak_pss: int = 0


@dataclass
class Metrics:
    combined_cpu_time: float = 0.0
    combined_read_bytes: int = 0
    combined_write_bytes: int = 0
    sys_read_bytes: int = 0
    sys_write_bytes: int = 0
    wall_time: float = 0.0
    peak_pss: int = 0
    processes: dict[psutil.Process, ProcessSnapshot] = field(default_factory=dict)


def get_process_group_members(pgid: int) -> list[psutil.Process]:
    """
    Return all processes currently belonging to pgid.

    This scans /proc so it continues to work even after the original
    benchmark process has exited and its children have been reparented.
    """

    try:
        entries = os.listdir("/proc")
    except OSError:
        return []

    processes = []
    for entry in entries:
        if not entry.isdigit():
            continue

        pid = int(entry)

        try:
            if os.getpgid(pid) != pgid:
                continue
            processes.append(psutil.Process(pid))

        except (ProcessLookupError, PermissionError, OSError):
            # Process may have exited between listing /proc and
            # calling os.getpgid().
            continue

    return processes


def get_pss(process: psutil.Process) -> int:
    """
    Return proportional set size (PSS) in bytes.

    Linux-specific. PSS is read from /proc/<pid>/smaps_rollup.
    """
    try:
        with open(f"/proc/{process.pid}/smaps_rollup", "r") as f:
            for line in f:
                if line.startswith("Pss:"):
                    # smaps_rollup reports kB.
                    return int(line.split()[1]) * 1024

    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        pass

    return 0


def get_process_io(process: psutil.Process) -> tuple[int, int]:
    """
    Return (rchar, wchar) for a process.

    Linux-specific.

    rchar = bytes read by the process through read-like syscalls.
    wchar = bytes written by the process through write-like syscalls.
    """
    try:
        with open(f"/proc/{process.pid}/io", "r") as f:
            rchar = 0
            wchar = 0

            for line in f:
                key, value = line.split(":", 1)

                if key == "rchar":
                    rchar = int(value.strip())

                elif key == "wchar":
                    wchar = int(value.strip())

            return rchar, wchar

    except (
        FileNotFoundError,
        ProcessLookupError,
        PermissionError,
        OSError,
    ):
        return 0, 0


async def monitor(
    pgid: int,
    usage: Metrics,
    interval: float,
):
    """
    Continuously monitor the benchmark process group.

    Every process observed is retained in usage.processes. This means
    processes that exit during the benchmark are still accounted for.
    """
    while True:
        try:
            processes = get_process_group_members(pgid)
        except (psutil.NoSuchProcess, FileNotFoundError):
            return False

        if not processes:
            return False

        are_any_running = False
        for p in processes:
            # update counters:
            try:
                if p.status() == psutil.STATUS_ZOMBIE:
                    continue
                are_any_running = True

                # brand new process.... Get CPU Timers.
                if p not in usage.processes:
                    usage.processes[p] = ProcessSnapshot()

                prior = usage.processes[p].peak_pss
                current = get_pss(p)
                usage.processes[p].peak_pss = max(prior, current)
                cpu = p.cpu_times()
                io = p.io_counters()
                usage.processes[p].cpu_time = cpu.user + cpu.system
                usage.processes[p].read_bytes = io.read_bytes
                usage.processes[p].write_bytes = io.write_bytes
                rchar, wchar = get_process_io(p)
                usage.processes[p].sys_read_bytes = rchar
                usage.processes[p].sys_write_bytes = wchar

            except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
                continue

        if not are_any_running:
            return False
        await asyncio.sleep(interval)


async def profile(payload_path: str, interval: float, raw=False) -> dict:

    if not raw:
        command = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "executor.py"),
            payload_path,
        ]
    else:
        command = shlex.split(payload_path)

    # start_new_session=True creates a new session and process group.
    #
    # The profiler remains outside this process group and therefore
    # contributes nothing to the measurements.

    start_time = time.monotonic()
    benchmark = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    pgid = os.getpgid(benchmark.pid)

    usage = Metrics()
    monitor_task = asyncio.create_task(monitor(pgid, usage, interval))
    try:
        await monitor_task
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except (asyncio.CancelledError, psutil.NoSuchProcess):
            pass

    usage.wall_time = time.monotonic() - start_time

    # sum it up
    for snapshots in usage.processes.values():
        usage.combined_cpu_time += snapshots.cpu_time
        usage.combined_read_bytes += snapshots.read_bytes
        usage.combined_write_bytes += snapshots.write_bytes
        usage.sys_write_bytes += snapshots.sys_write_bytes
        usage.sys_read_bytes += snapshots.sys_read_bytes
        usage.peak_pss += snapshots.peak_pss

    return {
        "total_seconds": usage.wall_time,
        "cpu_seconds": usage.combined_cpu_time,
        "disk_read_bytes": usage.combined_read_bytes,
        "disk_write_bytes": usage.combined_write_bytes,
        "sys_read_bytes": usage.sys_read_bytes,
        "sys_write_bytes": usage.sys_write_bytes,
        "memory_bytes": usage.peak_pss,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--interval",
        type=float,
        default=0.01,
        help="Resource sampling interval in seconds.",
    )

    parser.add_argument("--csv", action="store_true", help="Output as csv string")
    parser.add_argument("--exe", action="store_true", help="Execute raw cmd")

    parser.add_argument(
        "payload",
    )

    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be greater than zero")

    result = asyncio.run(profile(args.payload, args.interval, args.exe))

    # stdout is reserved exclusively for the result.

    if args.csv:
        print(",".join([str(f) for f in result.values()]))
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
