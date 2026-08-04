import asyncio
from collections import defaultdict
from rhapsody.backends import DragonExecutionBackendV3

# You must run this below before running program.
# dragon-config add --ofi-runtime-lib=/opt/cray/libfabric/1.22.0/lib64

from dragon.native.machine import Policy, System, Node
import multiprocessing as mp

CORES_PER_MACHINE = 128


class NerscCPU:
    def __init__(self, node_count=1):
        self.node_count = node_count

    def get_backend(self):
        # you must call await to this function, although the function isn't
        # async, as the ConcurrentExecutionBackend returns a future.
        mp.set_start_method("dragon")

        # because the sim task will spawn 32 cores, and NERSC is 128 core
        return DragonExecutionBackendV3(
            # defaults to full number of nodes
            batch_kwargs={
                "scheduler_workers": self.node_count * CORES_PER_MACHINE // 32,
                "num_nodes": self.node_count,
            }
        )

    def find_cpus(self):
        all_cpus = defaultdict(list)
        all_hosts = []
        # loop through all nodes Dragon is running on
        for huid in System().nodes:
            node = Node(huid)
            all_hosts.append(node.hostname)
            # loop through however many CPUs it may have
            for cpu_id in node.cpus:
                all_cpus[node.hostname].append(cpu_id)
        return all_hosts, all_cpus

    def create_cpu_policies(self, core_count=32, policy_count=16):
        """Create per-process policies with round-robin CPU assignment."""

        all_hosts, all_cpus = self.find_cpus()

        machine_task_number = defaultdict(int)
        tasks_per_machine = max(CORES_PER_MACHINE // core_count, 1)
        policies = []
        for policy_id in range(policy_count):
            machine = policy_id % self.node_count
            cpu_range = machine_task_number[machine] % tasks_per_machine
            cpus = list(range(cpu_range * core_count, (cpu_range + 1) * core_count))

            cpu_policy = []
            for cpu in cpus:
                cpu_policy.append(all_cpus[all_hosts[machine]][cpu])

            # create policy
            policies.append(
                Policy(
                    placement=Policy.Placement.HOST_NAME,
                    host_name=all_hosts[machine],
                    cpu_affinity=cpu_policy,
                )
            )

            machine_task_number[machine] += 1
            # figure out the core number

        return policies
