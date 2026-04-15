#!/usr/bin/env python3
"""
csv_logger.py
Safe CSV logging with exclusive file locking via fcntl.flock.
"""

import csv
import fcntl
import os
import sys
import time


def log_workflow_update(workflow_id: str, task: str, status: str, status_file: str) -> None:
    """
    Append one CSV row to status_file under an exclusive flock lock.
    Creates the file (with a header) if it does not already exist.

    Args:
        workflow_id: Unique identifier for the workflow.
        task:        Task name or label.
        status:      Current status string.
        status_file: Path to the target CSV file.
    """
    # --- Sanitize fields: strip embedded commas and double-quotes ----------
    def sanitize(value: str) -> str:
        return value.replace(",", "").replace('"', "")

    safe_workflow_id = sanitize(str(workflow_id))
    safe_task        = sanitize(str(task))
    safe_status      = sanitize(str(status))

    # High-resolution timestamp (matches bash's date '+%s.%N')
    timestamp = f"{time.time():.9f}"

    lock_file = status_file + ".lock"

    # Open (or create) the lock file, acquire an exclusive lock,
    # then write — lock is released automatically when the fd is closed.
    lock_fd = open(lock_file, "w")
    try:
        # Block until the lock is acquired, timeout after 10 seconds
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break  # Lock acquired
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lock on {lock_file} within 10 s"
                    )
                time.sleep(0.05)

        # Write header on first use (file absent or empty)
        write_header = not os.path.exists(status_file) or os.path.getsize(status_file) == 0

        with open(status_file, "a", newline="") as csv_file:
            writer = csv.writer(csv_file)
            if write_header:
                writer.writerow(["workflow_id", "task", "status", "timestamp"])
            writer.writerow([safe_workflow_id, safe_task, safe_status, timestamp])

    finally:
        # Always release the lock and close the fd
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: csv_logger.py <workflow_id> <task> <status> <status_file>",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        log_workflow_update(*sys.argv[1:])
    except TimeoutError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)