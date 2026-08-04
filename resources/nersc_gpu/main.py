import asyncio
from rhapsody.backends import DragonExecutionBackendV3

# You must run this below before running program.
# dragon-config add --ofi-runtime-lib=/opt/cray/libfabric/1.22.0/lib64

from dragon.native.machine import Policy, System, Node


class NerscGPU:
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

    def find_gpus(self):
        all_gpus = []
        # loop through all nodes Dragon is running on
        for huid in System().nodes:
            node = Node(huid)
            # loop through however many GPUs it may have
            for gpu_id in node.gpus:
                all_gpus.append((node.hostname, gpu_id))
        return all_gpus

    def make_gpu_policy(self, policy_count=2):
        """Create per-process policies with round-robin GPU assignment."""
        policies = []
        all_gpus = self.find_gpus()
        for i in range(policy_count):
            policies.append(
                Policy(
                    placement=Policy.Placement.HOST_NAME,
                    host_name=all_gpus[i % len(all_gpus)][0],
                    gpu_affinity=[all_gpus[i % len(all_gpus)][1]],
                )
            )
        return policies
