import asyncio
from concurrent.futures import ProcessPoolExecutor
from rhapsody.backends import ConcurrentExecutionBackend


class LocalCPU:
    def __init__(self):
        pass

    def get_backend(self):
        # you must call await to this function, although the function isn't
        # async, as the ConcurrentExecutionBackend returns a future.

        return ConcurrentExecutionBackend(ProcessPoolExecutor())
