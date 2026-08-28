#!/bin/python3
import argparse, subprocess, sys, asyncio, os

def get_worker_count(project="xgfabric") -> int:
    try:
        res = subprocess.run(
            ["work_queue_status", "-M", project],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == project:
                    return int(parts[6])  # Workers column
    except Exception as e:
        print(f"Could not retrieve worker status: {e}")
        sys.exit(1)
    return 0


async def main():
    connected_workers = get_worker_count(project_name)
    while connected_workers < workers_needed:
        connected_workers = get_worker_count(project_name)
        await asyncio.sleep(20)
    result_path = os.getenv('WORKFLOW_LOCATION')
    with open(f"{result_path}/workers_ready.out", 'w') as file:
        file.write(f"All {workers_needed} workers are available!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Finds the number of workers connected to a given Work Queue project.')

    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="How many workers to wait for (default: 10)"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="The name of project that needs workers"
    )

    args = parser.parse_args()

    workers_needed = args.workers
    project_name = args.project

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Wait for workers shut down safely.")
    except SystemExit:
        print("Wait for workers has finished.")
    except Exception as e:
        print(f"Wait for workers stopped due to unexpected error: {e}")
