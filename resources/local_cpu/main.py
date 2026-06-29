import asyncio
from concurrent.futures import ProcessPoolExecutor
from rhapsody.backends import ConcurrentExecutionBackend


class LocalCPU:
    def __init__(self):
        pass

    def get_backend(self):
        # you must call await to this function, although the function isn't
        # async, as the ConcurrentExecutionBackend returns a future.

        # because the sim task will spawn 32 cores.
        return ConcurrentExecutionBackend(
            ProcessPoolExecutor(max_workers=1, max_tasks_per_child=1)
        )
