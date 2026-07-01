import asyncio
from rhapsody.backends import DragonExecutionBackendV3

# You must run this below before running program.
# dragon-config add --ofi-runtime-lib=/opt/cray/libfabric/1.22.0/lib64


class NerscCPU:
    def __init__(self, node_count=1):
        self.node_count = node_count

    def get_backend(self):
        # you must call await to this function, although the function isn't
        # async, as the ConcurrentExecutionBackend returns a future.

        # because the sim task will spawn 32 cores, and NERSC is 128 core
        return DragonExecutionBackendV3(
            # defaults to full number of nodes
            batch_kwargs={
                "scheduler_workers": self.node_count * 4,
            }
        )
